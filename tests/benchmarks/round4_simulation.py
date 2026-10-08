"""Controller tool (not a unittest module): the binding Round 4 pre-T checkpoint (AC-R3-01) plus a synthetic H
lifecycle simulation, generalizing tests/benchmarks/round2_simulation.py.

    python tests/benchmarks/round4_simulation.py --phase pre-T --cache-dir S --work DIR
    python tests/benchmarks/round4_simulation.py --phase H [--keep]

--phase pre-T runs the EXACT working-tree policy (ranking, aliases, verb inventory) against a real snapshot S and
appends a `pre_t_checkpoint` event to DIR/controller-events.jsonl; exit 0 iff AC-R3-01 passes (seed >= 36/39,
regression raw >= 10/14 and effective == 14/14, every fixture query passing, and the memoized GridEvaluator used by
the tuning pipeline agreeing with search_operations on a deterministic grid-point sample).

--phase H applies the Round 4 commits (T, B, then branches C+D / F / X and X_preB per hidden state 2-5) on a throwaway `git archive HEAD` copy
and runs the full offline suite after each one, so the frozen integrity tests are known to support every branch
before H is declared. Only synthetic data is used: no real snapshot, no sealed plaintext, no network;
ATLASSIAN_DOCS_* variables are removed from the subprocess environment.
"""
import argparse, copy, dataclasses, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid

ROUND = 4
SIM_DIR = ".round4-sim"                       # inside the temp tree: synthetic snapshot and plaintext
LEXICON_WORD, LEXICON_TARGET = "zzsynthetic", "issue"
LEXICON_PHRASE, LEXICON_PHRASE_TARGET = "zzalpha zzbeta", "issue"          # v1.24: synthetic phrase -> when_all rule (spec §6)
DATA_REL = "tools/atlassian_docs/intelligence/data"
STEPS_COMMON = ("T", "B")
BRANCHES = ("D", "F", "X", "XpreB2", "XpreB3", "XpreB4", "XpreB5")   # Round 4 spec §9.4: X_preB per hidden state
FAILING = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)
ROOT = pathlib.Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ driver (runs in the real checkout)
def _env():
    return {k: v for k, v in os.environ.items() if not k.startswith("ATLASSIAN_DOCS_")}


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=sim", "-c", "user.email=sim@example.invalid", *args], cwd=cwd, check=True,
                   capture_output=True)


def _suite(tree):
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=tree, env=_env(),
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    ran = re.search(r"^Ran (\d+) tests", out, re.M)
    ids = sorted({q if q.endswith("." + n) else f"{q}.{n}" for n, q in FAILING.findall(out)})
    return r.returncode, (int(ran.group(1)) if ran else None), ids, out


def _run_suite_step(tree, step, label):
    r = subprocess.run([sys.executable, "tests/benchmarks/round4_simulation.py", "--apply", step], cwd=tree,
                       env=_env(), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[{label}] APPLY FAILED\n{r.stdout}{r.stderr}")
        return False
    _git(tree, "add", "-A"); _git(tree, "commit", "-q", "-m", f"simulated {label}")
    code, ran, ids, _ = _suite(tree)
    print(f"[{label}] {'PASS' if code == 0 else 'FAIL'}  Ran {ran} tests  ({r.stdout.strip()})"
          + "".join(f"\n      {i}" for i in ids))
    return code == 0


def drive(keep: bool) -> int:
    repo = pathlib.Path(__file__).resolve().parents[2]
    tree = pathlib.Path(tempfile.mkdtemp(prefix="round4-sim-"))
    try:
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=repo, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
        _git(tree, "init", "-q"); _git(tree, "add", "-A"); _git(tree, "commit", "-q", "-m", "H (archive of HEAD)")
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        print(f"simulation tree: {tree} (git archive {head})")
        code, ran, ids, _ = _suite(tree)
        print(f"[archive] {'PASS' if code == 0 else 'FAIL'}  Ran {ran} tests" + "".join(f"\n      {i}" for i in ids))
        all_ok = code == 0
        tree_after_t = None
        for step in STEPS_COMMON:
            all_ok &= _run_suite_step(tree, step, step)
            if not all_ok:
                return 1
            if step == "T":                                              # X_preB branches start from the post-T tree (no B)
                tree_after_t = pathlib.Path(tempfile.mkdtemp(prefix="round4-sim-afterT-")); shutil.rmtree(tree_after_t); shutil.copytree(tree, tree_after_t)
        for branch in BRANCHES:
            btree = pathlib.Path(tempfile.mkdtemp(prefix=f"round4-sim-{branch}-"))
            shutil.rmtree(btree)
            shutil.copytree(tree_after_t if branch.startswith("XpreB") else tree, btree)
            try:
                all_ok &= _run_suite_step(btree, branch, branch)
            finally:
                if keep:
                    print(f"kept {btree}")
                else:
                    shutil.rmtree(btree, ignore_errors=True)
        print("ALL STEPS PASS" if all_ok else "SOME STEPS FAILED")
        return 0 if all_ok else 1
    finally:
        if keep:
            print(f"kept {tree}")
        else:
            shutil.rmtree(tree, ignore_errors=True)
            if tree_after_t is not None:
                shutil.rmtree(tree_after_t, ignore_errors=True)


# ------------------------------------------------------------------ pre-T checkpoint (AC-R3-01, spec §5 v1.22)
def pre_t_verdict(seed_passed, reg_raw, reg_eff, fixture_failing) -> bool:
    """AC-R3-01: seed >= 36/39, fixture 23/23 · 6/6 (raw), regression raw >= 10/14, effective == 14/14."""
    return seed_passed >= 36 and reg_raw >= 10 and reg_eff == 14 and not fixture_failing


def pre_t_event(seed_res, reg_res, fixture_failing, inputs, at=None) -> dict:
    return {"event": "pre_t_checkpoint", "seed": seed_res["passed"], "regression_raw": reg_res["raw_passed"], "regression_effective": reg_res["effective_passed"],
            "fixture_failing": list(fixture_failing), "inputs": inputs, "pass": pre_t_verdict(seed_res["passed"], reg_res["raw_passed"], reg_res["effective_passed"], fixture_failing),
            "at": at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def equivalence_mismatches(state, rp, bench, ap, n=20, seed=20261005) -> list:
    """spec §5 v1.22 preflight: the memoized grid evaluator must rank exactly like search_operations on the ACTUAL S and fixture
    registry for a deterministic sample of grid points (plus the baseline) and every seed/regression/fixture query."""
    import random
    from unittest import mock
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy, search
    pts = random.Random(seed).sample(tune.grid_points(rp.tuning_grid), n) + [dict(rp.baseline)]
    fx_state, fx_bench = tune.fixture_state(), tune.fixture_bench(bench)
    pairs = [(state, [r["query"] for r in bench["seed"] + bench["regression_negative"]]), (fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]])]
    out = []
    for st, queries in pairs:
        ge = tune.GridEvaluator(st, queries, ap, rp.ordering_rules["terminal_alias_full_weight"])
        for p in pts:
            rpp = tune.ranking_with(rp, p)
            with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=ap):
                for q in queries:
                    o = search.search_operations(st, q, limit=5)
                    if ge.ranked(q, rpp) != ([r["key"] for r in o["results"]], o["actionable"]):
                        out.append({"point": p, "query": q})
    return out


def run_pre_t(cache: pathlib.Path, work: pathlib.Path) -> int:
    """Binding checkpoint on the EXACT working-tree policy (ranking, aliases, inventory) against S; appends the event to the ledger."""
    from tests import tune_search_ranking as tune
    from tests.benchmarks import evaluator as ev, round_seal as rs
    from tools.atlassian_docs.intelligence import policy
    rp, bench = policy.load_ranking(tune.RANKING_PATH), tune._BENCH
    aliases_raw, ranking_raw = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    ap = tune._alias_policy(aliases_raw)
    def body(state):
        s, r = tune.evaluate_point(state, rp, dict(rp.constants), bench, ap)
        return s, r, state.registry.fingerprint, {n: p.active_spec_sha256 for n, p in state.provenance.items()}
    seed_res, reg_res, fp, spec = tune._with_state(cache, body)
    failing = tune.fixture_failures(tune.fixture_state(), rp, dict(rp.constants), tune.fixture_bench(bench), ap)
    inputs = {"ranking_sha256": policy.canonical_sha256(ranking_raw), "aliases_sha256": policy.canonical_sha256(aliases_raw),
              "verb_inventory_sha256": policy.canonical_sha256(ranking_raw["verb_methods"]), "registry_fingerprint": fp, "spec_sha256": spec,
              "fixture_benchmark_sha256": policy.canonical_sha256(tune.fixture_bench(bench)), "evaluation_code_sha256": ev.evaluation_code_sha256(ROOT),
              "tuning_grid_sha256": ev.tuning_grid_sha256(ranking_raw)}
    e = pre_t_event(seed_res, reg_res, failing, inputs)
    e["equivalence_mismatches"] = tune._with_state(cache, lambda state: equivalence_mismatches(state, rp, bench, ap))
    e["pass"] = e["pass"] and not e["equivalence_mismatches"]
    # Round 4 spec §4.1: exact, write-free dry-run of the production pipeline (run_pipeline_result) → pre_t_blockers
    cands_doc = json.loads(tune.CANDIDATES_PATH.read_text(encoding="utf-8"))
    result, diag = tune._with_state(cache, lambda state: dry_run_pipeline(state, rp, bench, aliases_raw, cands_doc, seed_res))
    blockers = pre_t_blockers(result, e, diag)
    e.update({"pre_t_blockers": blockers, "blocking_reasons": [b["kind"] for b in blockers], "known_unreachable_seeds": [s for b in blockers if b["kind"] == "unreachable_seed" for s in b["seeds"]],
              "known_unreachable_seed_count": sum(len(b["seeds"]) for b in blockers if b["kind"] == "unreachable_seed"),
              "dry_run": {"tuning_accept": result.tuning_accept, "validation_errors": result.validation_errors, "selected_point": result.selected_point,
                          "seed": result.seed_result["passed"], "regression_effective": result.regression_result["effective_passed"], "fixture_final": result.fixture_result["final"]},
              "pipeline_input_sha256": policy.canonical_sha256({"ranking": ranking_raw, "aliases": aliases_raw, "candidates": cands_doc, "bench": bench, "grid": rp.tuning_grid}),
              "pipeline_result_sha256": policy.canonical_sha256(dataclasses.asdict(result)), "result": "pass" if (e["pass"] and not blockers) else "stop_for_amendment"})
    work.mkdir(parents=True, exist_ok=True)
    with open(work / "controller-events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(e) + "\n")
    print(json.dumps(e, indent=1)); return 0 if e["result"] == "pass" else 1


def dry_run_pipeline(state, rp, bench, aliases_raw, cands_doc, baseline_seed_res):
    """The production orchestration (tune.run_pipeline_result) with the pre-T policy as the B state; no file is written
    (write_constants/_write_log are patched to raise). Returns (PipelineResult, diagnostics)."""
    from unittest import mock
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy
    b_sha = policy.canonical_sha256(aliases_raw)
    queries = [r["query"] for r in bench["seed"] + bench["regression_negative"]]
    fx_state, fx_bench = tune.fixture_state(), tune.fixture_bench(bench)
    tf = rp.ordering_rules["terminal_alias_full_weight"]
    ge = tune.GridEvaluator(state, queries, tune._alias_policy(aliases_raw), tf)
    ge_fx = tune.GridEvaluator(fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]], tune._alias_policy(aliases_raw), tf)
    cache = {}
    def raw_sha(raw):
        return cache.setdefault(id(raw), policy.canonical_sha256(raw))
    def evaluate_fn(point, raw):
        return tune.evaluate_point_fast(ge, rp, point, bench) if raw_sha(raw) == b_sha else tune.evaluate_point(state, rp, point, bench, tune._alias_policy(raw))
    def fixture_fn(point, raw):
        return tune.fixture_failures_fast(ge_fx, rp, point, fx_bench) if raw_sha(raw) == b_sha else tune.fixture_failures(fx_state, rp, point, fx_bench, tune._alias_policy(raw))
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run must not write"))
    with mock.patch.object(tune, "write_constants", boom), mock.patch.object(tune, "_write_log", boom):
        result = tune.run_pipeline_result(evaluate_fn, bench, aliases_raw, cands_doc, rp.tuning_grid, dict(rp.baseline), fixture_fn,
                                          {r["id"]: r["query"] for r in bench["seed"]}, {r["id"]: r["failure_classes"] for r in bench["seed"]})
    failing_after = {f["id"] for f in result.seed_result["failed"]}
    failing_before = {f["id"] for f in baseline_seed_res["failed"]}
    by_id = {r["id"]: r for r in bench["seed"]}
    ok_points = {tuple(sorted(pt.items())) for pt, s_pass, r_pass in result.grid_results if r_pass == tune.REGRESSION_TOTAL}   # regression effective intact, fixture-admissible
    reach = {}
    for sid in sorted(failing_after):
        rec = by_id[sid]; reach[sid] = False
        for pt, _, r_pass in result.grid_results:
            if tuple(sorted(pt.items())) not in ok_points:
                continue
            keys, _ = ge.ranked(rec["query"], tune.ranking_with(rp, pt))
            if keys and keys[0] in rec["expected_top1_any"]:
                reach[sid] = True; break
    return result, {"reachable_by_grid": reach, "dry_run_fixed": sorted(failing_before - failing_after)}


# ------------------------------------------------------------------ synthetic hidden records (apply_B)
VERB_FOR_METHOD = {"GET": "show", "POST": "create", "PUT": "update", "DELETE": "delete"}
PRODUCT_PREFIX = {"jira-platform": "jira", "jira-software": "jira", "confluence": "confluence"}
# Deterministic 16-op selection satisfying round_seal.MIN_SOURCE / MIN_METHOD on the fixture catalog (spec §4 v1.22
# distribution rule): (source, method) -> how many of that cell's sorted-by-key operations to take.
_SELECT_QUOTA = {("jira-platform", "DELETE"): 1, ("jira-platform", "GET"): 3, ("jira-platform", "POST"): 2, ("jira-platform", "PUT"): 1,
                 ("confluence", "DELETE"): 1, ("confluence", "GET"): 2, ("confluence", "POST"): 1, ("confluence", "PUT"): 1,
                 ("jira-software", "GET"): 2, ("jira-software", "POST"): 2}
NATO_WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo", "lima",
             "mike", "november", "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey", "xray"]


def _select_ops(internal) -> list:
    by_cell = {}
    for r in sorted(internal, key=lambda r: r["key"]):
        by_cell.setdefault((r["source"], r["method"]), []).append(r)
    ops = []
    for cell, n in sorted(_SELECT_QUOTA.items()):
        ops += by_cell[cell][:n]
    ops.sort(key=lambda r: r["key"])
    if len(ops) != 16:
        raise ValueError(f"expected 16 ops from the fixture catalog, selected {len(ops)}")
    return ops


def synthetic_hidden_records(internal, verb_methods) -> dict:
    """Deterministic Round 4 synthetic hidden set over the fixture catalog (spec §4 v1.22): 16 held_out (4 of them
    product-named) + 8 negative (4 actionable / 4 verb-less) that pass round_seal.machine_check(round=3)."""
    for method, verb in VERB_FOR_METHOD.items():
        if verb_methods.get(verb) != [method]:
            raise ValueError(f"verb {verb!r} must map to exactly [{method!r}] in the live inventory")
    ops = _select_ops(internal)
    words = iter(NATO_WORDS)
    held = []
    for i, op in enumerate(ops):
        word, verb = next(words), VERB_FOR_METHOD[op["method"]]
        query = f"{verb} probe {word} item"
        if i < 4:
            query = f"{PRODUCT_PREFIX[op['source']]} {query}"
        held.append({"id": f"h-{i + 1:03d}", "query": query, "expected_top1_any": [op["key"]], "forbidden_top1": [],
                     "origin": f"held_out-r{ROUND}", "failure_classes": [], "ambiguous": False})
    negs = []
    for i, op in enumerate(ops[:4]):                                  # actionable negatives: verb matches the forbidden op's method
        word, verb = next(words), VERB_FOR_METHOD[op["method"]]
        negs.append({"id": f"n-{i + 1:03d}", "query": f"{verb} decoy {word} item", "expected_top1_any": [],
                     "forbidden_top1": [op["key"]], "origin": f"negative-r{ROUND}", "failure_classes": [], "ambiguous": False})
    for i, op in enumerate(ops[4:8]):                                 # verb-less negatives: abstained regardless of forbidden_top1
        word = next(words)
        negs.append({"id": f"n-{5 + i:03d}", "query": f"decoy {word} item", "expected_top1_any": [],
                     "forbidden_top1": [op["key"]], "origin": f"negative-r{ROUND}", "failure_classes": [], "ambiguous": False})
    plain = {"held_out": held, "negative": negs}
    from tests.benchmarks import round_seal as rs
    violations = rs.machine_check(plain, {"seed": [], "regression_negative": []}, internal, round=ROUND, verb_methods=verb_methods)
    assert not violations, f"synthetic_hidden_records violates machine_check: {violations}"
    return plain


def _reference_plain(internal) -> dict:
    """Synthetic round2-origin reference plaintext for apply_D's --reference append (one invalid key, to exercise
    the invalid_key path too)."""
    ops = _select_ops(internal)
    a, b = ops[0], ops[1]
    va, vb = VERB_FOR_METHOD[a["method"]], VERB_FOR_METHOD[b["method"]]
    held = [{"id": "h-201", "query": f"{va} probe mirage item", "expected_top1_any": [a["key"]], "forbidden_top1": [],
             "origin": "held_out-r2", "failure_classes": [], "ambiguous": False},
            {"id": "h-202", "query": f"{vb} probe oasis item", "expected_top1_any": ["nope:GET:/x"], "forbidden_top1": [],
             "origin": "held_out-r2", "failure_classes": [], "ambiguous": False}]
    neg = [{"id": "n-201", "query": f"{va} decoy mirage item", "expected_top1_any": [], "forbidden_top1": [a["key"]],
            "origin": "negative-r2", "failure_classes": [], "ambiguous": False}]
    return {"held_out": held, "negative": neg}


# ------------------------------------------------------------------ steps (run inside the temp tree)
def _read(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _fixture_cache():
    from tools.atlassian_docs import storage
    from unittest import mock
    cache = ROOT / SIM_DIR / "cache"
    if not cache.exists():
        with mock.patch.object(storage, "CACHE_DIR", cache):
            md = {}
            for s in ("jira-platform", "jira-software", "confluence"):
                spec = json.loads((ROOT / "tests" / "fixtures" / "openapi" / f"{s}-openapi.json").read_text(encoding="utf-8"))
                storage.write_cache_spec(s, spec)
                md[s] = {"sha256": storage.sha256_of_spec(spec), "api_version": "v3", "last_checked": "2026-10-05T00:00:00Z",
                         "last_updated": "2026-10-05T00:00:00Z", "resolved_documentation_url": "https://d/"}
            storage.write_metadata(md)
    return cache


def apply_T():
    """T: synthetic lexicon-r4 merge, candidates --round 4, R5/R6 classification, synthetic frozen texts, synthetic
    archived Round 2 ciphertext, round_freeze round 3 entry (ev.round_freeze_hashes). The live verb inventory /
    tuning grid are already in the committed tree (Tasks 1-7); T does not touch them."""
    from tests.benchmarks import alias_candidates_tool as act, concept_lexicon_check as clc, round_seal as rs
    from tests.benchmarks.evaluator import canonical_sha256
    cache = _fixture_cache()
    _, internal, fp, shas = rs.load_catalogs_from_cache(cache, ROUND)
    ranking = _read(f"{DATA_REL}/search_ranking.json")
    aliases = _read(f"{DATA_REL}/search_aliases.json")
    # Additive merge: concept_lexicon.json / alias_candidates.json already carry the real, catalog_df-scale Round
    # 1/2 documents (hundreds of entries the live search_aliases.json's words/targets are justified by, spec §10.2
    # TestPolicyVocabularyProvenance); the synthetic lexicon-r4 word is merged IN rather than replacing them.
    synthetic = {LEXICON_WORD: [LEXICON_TARGET], LEXICON_PHRASE: [LEXICON_PHRASE_TARGET]}
    raw, review = dict(synthetic), {k: True for k in synthetic}
    lexicon = _read(f"{DATA_REL}/concept_lexicon.json")
    lexicon["lexicon"] = {**lexicon.get("lexicon", {}), **synthetic}
    lexicon["round"] = ROUND
    lexicon["generated_from"] = act.provenance(fp, shas, {
        "verb_inventory": canonical_sha256(ranking["verb_methods"]), "aliases": canonical_sha256(aliases),
        "raw_generation": canonical_sha256(raw), "semantic_review": canonical_sha256(review)})
    act._write(ROOT / DATA_REL / "concept_lexicon.json", lexicon)              # 1. synthetic lexicon, merged as lexicon-r4
    merged, skipped = clc.merge(aliases, synthetic, ROUND)
    assert not skipped
    (ROOT / DATA_REL / "search_aliases.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bench = _read("tests/benchmarks/search_queries.json")
    doc = act.candidates(bench, internal, ranking, merged, ROUND)              # 2. candidates after the merge (fixture-scale)
    old_doc = _read(f"{DATA_REL}/alias_candidates.json")
    doc["candidates"] = {**old_doc.get("candidates", {}), **doc["candidates"]}
    doc["generated_from"] = act.provenance(fp, shas, {"ranking": canonical_sha256(ranking), "aliases": canonical_sha256(merged),
                                                      "bench": canonical_sha256(bench), "verb_inventory": canonical_sha256(ranking["verb_methods"])})
    act._write(ROOT / DATA_REL / "alias_candidates.json", doc)
    cls = act.classify(bench, internal, ranking, merged)                       # 3. R5/R6
    for rec in bench["seed"]:
        rec["failure_classes"] = [c for c in rec["failure_classes"] if c not in ("R5", "R6")] + cls[rec["id"]]
    # Round 2's hidden set stays sealed forever (it becomes the archived reference_set, spec §9) rather than being
    # demoted into seed/regression_negative; held_out/negative reset to [] as Round 4's own pending slots (commit B
    # fills them; round2_seal keeps the historical round 2 hashes).
    bench["held_out"], bench["negative"] = [], []
    rs._write_bench(ROOT / "tests" / "benchmarks" / "search_queries.json", bench)
    for name in ("worker-brief", "hidden-generation-prompt", "hidden-reviewer-prompt"):   # 4. synthetic frozen texts
        text = f"# synthetic round{ROUND} {name}\n<generator catalog lines>\n<verb methods json>\n"
        (ROOT / "tests" / "benchmarks" / f"round{ROUND}-{name}.md").write_text(text, encoding="utf-8")
    sim_dir = ROOT / SIM_DIR; sim_dir.mkdir(exist_ok=True)                      # 5. synthetic archived Round 2 ciphertext
    enc_path = sim_dir / "round2-sealed.json.enc"
    enc_path.write_bytes(b"synthetic archived round2 ciphertext (round4_simulation.py phase H)")
    from tests.benchmarks import doc_titles as dt                              # 6. synthetic doc-title bundle + snapshot (Round 4 spec §5)
    bundle = synthetic_doc_bundle(sim_dir / "doc-title-sources")
    snap_path = sim_dir / "doc-titles-snapshot.json"
    snap_path.write_text(json.dumps(dt.snapshot(bundle), sort_keys=True, indent=1) + "\n", encoding="utf-8")
    with open(os.devnull, "w") as null:                                        # 7. freeze entry (ev.round_freeze_hashes + Round 4 keys)
        old, sys.stdout = sys.stdout, null
        try:
            code = rs.main(["freeze", "--round", str(ROUND), "--cache-dir", str(cache), "--reference-enc", str(enc_path),
                            "--doc-title-sources", str(bundle), "--doc-titles", str(snap_path), "--base-commit", "HEAD"])
        finally:
            sys.stdout = old
    assert code == 0
    print(f"lexicon-r{ROUND} {LEXICON_WORD}->{LEXICON_TARGET} + phrase rule {LEXICON_PHRASE}->{LEXICON_PHRASE_TARGET}; {len(doc['candidates'])} candidates; "
          f"R6 seeds {sum('R6' in v for v in cls.values())}; round_freeze round {ROUND} added")


def apply_B():
    """B: synthetic Round 4 hidden records (16 held_out + 8 negative), the needle manifest over their queries, and
    round_seal `seal` (binds needle_manifest_sha256)."""
    from tests.benchmarks import round_seal as rs
    cache = _fixture_cache()
    _, internal, _, _ = rs.load_catalogs_from_cache(cache, ROUND)
    vm = _read(f"{DATA_REL}/search_ranking.json")["verb_methods"]
    plain = synthetic_hidden_records(internal, vm)
    sim_dir = ROOT / SIM_DIR; sim_dir.mkdir(exist_ok=True)
    plain_path = sim_dir / "round4-plain.json"
    plain_path.write_text(json.dumps(plain, indent=2), encoding="utf-8")
    manifest = rs.needle_manifest([r["query"] for r in plain["held_out"] + plain["negative"]])
    manifest_path = sim_dir / "needle-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    bench_path = ROOT / "tests" / "benchmarks" / "search_queries.json"
    with open(os.devnull, "w") as null:
        old, sys.stdout = sys.stdout, null
        try:
            code = rs.main(["seal", "--round", str(ROUND), "--plain", str(plain_path), "--bench", str(bench_path),
                            "--cache-dir", str(cache), "--needle-manifest", str(manifest_path)])
        finally:
            sys.stdout = old
    assert code == 0
    print(f"round{ROUND}_seal over {len(plain['held_out'])}+{len(plain['negative'])} synthetic records; "
          f"needle manifest {len(manifest)} entries")


def apply_C():
    """C (branch D only): one fixture-admissible tuning constant + one frozen-candidate alias, written directly as
    an adopted log line (as round2_simulation.py's apply_C did for Round 2)."""
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy
    assert tune.ROUND == ROUND
    rp, bench = policy.load_ranking(tune.RANKING_PATH), tune._BENCH
    b_aliases, b_ranking = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    cands_doc = json.loads(tune.CANDIDATES_PATH.read_text(encoding="utf-8"))
    state, fb = tune.fixture_state(), tune.fixture_bench(bench)
    grid, base = rp.tuning_grid, dict(rp.baseline)
    near = sorted((p for p in tune.grid_points(grid) if tune.l1_index_distance(p, base, grid) == 1),
                  key=lambda p: tuple(p[k] for k in tune.CONSTANT_KEYS))
    point = next(p for p in near if not tune.fixture_failures(state, rp, p, fb, tune._alias_policy(b_aliases)))
    queries = {r["id"]: r["query"] for r in bench["seed"]}
    classes = {r["id"]: r["failure_classes"] for r in bench["seed"]}
    chosen = None
    for word, c in sorted(cands_doc["candidates"].items()):
        for sid in c["seed_ids"]:
            if "R6" not in classes[sid]:
                continue
            for target in c["targets_by_seed"][sid]:
                trial = copy.deepcopy(b_aliases)
                trial["aliases"][word] = [target]; trial["notes"][word] = tune.round_note(word, sid, target)
                if not tune.validate_alias_change(b_aliases, trial, cands_doc["candidates"], queries, classes) \
                        and not tune.fixture_failures(state, rp, point, fb, tune._alias_policy(trial)):
                    chosen = (word, sid, target, trial); break
            if chosen: break
        if chosen: break
    assert chosen, "no fixture-admissible round4 alias among the frozen candidates"
    word, sid, target, working = chosen
    tune.write_constants(point)
    tune.ALIASES_PATH.write_text(json.dumps(working, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    policy.load_aliases(tune.ALIASES_PATH)
    patch = {**tune.alias_patch(b_aliases, working), "resolved_by_prior_change": [], "not_r6": [], "unresolved": [],
             "fixture_fail": [], "trials": 1}
    fp = cands_doc["generated_from"]["registry_fingerprint"]
    diag = tune.fixture_negative_diagnostic(state, rp, point, fb, tune._alias_policy(working))
    line = {"run_id": str(uuid.uuid4()), "run_at": "2026-10-05T00:00:00Z", "git_commit": "0" * 40, "round": ROUND,
            "registry_fingerprint": fp, "baseline_sha256": tune.baseline_sha256(b_aliases, b_ranking, fp, cands_doc, bench),
            "events": list(tune.EVENTS), "constants_selected": point, "grid_size": len(tune.grid_points(grid)),
            "grid_runtime_s": 0.1, "fixture_fail": {"constants": [], "final": []}, "passing_combos": 1,
            "aliases_proposed": patch, "seed": f"{tune.SEED_TOTAL}/{tune.SEED_TOTAL}",
            "regression_negative": f"{tune.REGRESSION_TOTAL}/{tune.REGRESSION_TOTAL}",
            "regression_raw": f"{tune.REGRESSION_TOTAL}/{tune.REGRESSION_TOTAL}",
            "fixture_positive": f"{tune.FIXTURE_COUNTS[0]}/{tune.FIXTURE_COUNTS[0]}",
            "fixture_negative_raw": f"{tune.FIXTURE_COUNTS[1]}/{tune.FIXTURE_COUNTS[1]}",
            "fixture_negative_effective_diagnostic": f"{diag['effective_passed']}/{tune.FIXTURE_COUNTS[1]}",
            "tuning_accept": True, "tuning_failed": False, "result_sha256": tune.result_sha256(point, patch),
            "dirty": [], "note": "simulated", "ranking_structure_sha256": rp.structure_sha256, "baseline": base}
    line["run_log_sha256"] = policy.canonical_sha256(tune.log_core(line))
    line["status"], line["adopted"] = "adopted", True
    tune._write_log([line])
    changed = {k: v for k, v in point.items() if v != base[k]}
    print(f"constants {changed}; round{ROUND} alias {word}->{target} ({sid}); adopted log line")


def apply_D():
    """D: diag --round 4 --bench <plain> --json round4-final.json, then --reference append of a synthetic
    round2-origin plaintext."""
    from tests import diag_search_queries as diag
    from tests.benchmarks import round_seal as rs
    cache = _fixture_cache()
    plain_path = ROOT / SIM_DIR / "round4-plain.json"
    out = ROOT / "tests" / "benchmarks" / f"round{ROUND}-final.json"
    with open(os.devnull, "w") as null:
        old, sys.stdout = sys.stdout, null
        try:
            code, _ = diag.run(["--cache-dir", str(cache), "--round", str(ROUND), "--bench", str(plain_path), "--json", str(out)])
        finally:
            sys.stdout = old
    assert code == 0, "diag run for round4-final.json failed"
    _, internal, _, _ = rs.load_catalogs_from_cache(cache, ROUND)
    ref = _reference_plain(internal)
    ref_path = ROOT / SIM_DIR / "round4-reference-r2.json"
    ref_path.write_text(json.dumps(ref, indent=2), encoding="utf-8")
    with open(os.devnull, "w") as null:
        old, sys.stdout = sys.stdout, null
        try:
            code2, _ = diag.run(["--cache-dir", str(cache), "--reference", str(ref_path), "--reference-round", "2", "--append-to", str(out)])
        finally:
            sys.stdout = old
    assert code2 == 0, "diag --reference append failed"
    print(f"tests/benchmarks/round{ROUND}-final.json written; reference_round2 appended")


def _synthetic_tuning_line(status: str) -> dict:
    """Shared shape for the F/X branches (spec §5.5 v1.22 log schema), bypassing the full real pipeline: there is no
    real snapshot large enough to answer the production seed/regression bench, so - like round2_simulation.py's
    apply_C - the fields are written directly rather than computed."""
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy
    assert tune.ROUND == ROUND
    rp = policy.load_ranking(tune.RANKING_PATH)
    b_aliases, b_ranking = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    cands_doc = json.loads(tune.CANDIDATES_PATH.read_text(encoding="utf-8"))
    bench, point = tune._BENCH, dict(rp.baseline)
    fp = cands_doc["generated_from"]["registry_fingerprint"]
    patch = {"aliases": {}, "rules": [], "notes": {}, "resolved_by_prior_change": [], "not_r6": [], "unresolved": [],
             "fixture_fail": [], "trials": 0}
    accept = status == "adopted"
    line = {"run_id": str(uuid.uuid4()), "run_at": "2026-10-05T00:00:00Z", "git_commit": "0" * 40, "round": ROUND,
            "registry_fingerprint": fp, "baseline_sha256": tune.baseline_sha256(b_aliases, b_ranking, fp, cands_doc, bench),
            "events": list(tune.EVENTS), "constants_selected": point, "grid_size": 1, "grid_runtime_s": 0.1,
            "fixture_fail": {"constants": [], "final": [] if accept else ["s-001"]},
            "passing_combos": 1 if accept else 0, "aliases_proposed": patch,
            "seed": f"{tune.SEED_TOTAL if accept else tune.SEED_TOTAL - 1}/{tune.SEED_TOTAL}",
            "regression_negative": f"{tune.REGRESSION_TOTAL}/{tune.REGRESSION_TOTAL}",
            "regression_raw": f"{tune.REGRESSION_TOTAL}/{tune.REGRESSION_TOTAL}",
            "fixture_positive": f"{tune.FIXTURE_COUNTS[0] if accept else tune.FIXTURE_COUNTS[0] - 1}/{tune.FIXTURE_COUNTS[0]}",
            "fixture_negative_raw": f"{tune.FIXTURE_COUNTS[1]}/{tune.FIXTURE_COUNTS[1]}",
            "fixture_negative_effective_diagnostic": f"{tune.FIXTURE_COUNTS[1]}/{tune.FIXTURE_COUNTS[1]}",
            "tuning_accept": accept, "tuning_failed": not accept, "result_sha256": tune.result_sha256(point, patch),
            "dirty": [], "note": f"simulated {status}", "ranking_structure_sha256": rp.structure_sha256, "baseline": dict(rp.baseline)}
    line["run_log_sha256"] = policy.canonical_sha256(tune.log_core(line))
    return line


def apply_F():
    """F: one failed tuning log line (tuning_accept: false); no policy files touched."""
    from tests import tune_search_ranking as tune
    line = _synthetic_tuning_line("failed")
    line["status"], line["adopted"] = "failed", False
    tune._write_log([line])
    print("synthetic failed tuning log line written (tuning_accept=false)")


def apply_X():
    """X: one rejected tuning log line with reject_evidence; policy files remain at B (no C applied in this branch)."""
    from tests import tune_search_ranking as tune
    line = _synthetic_tuning_line("adopted")                        # was accepted by the pipeline, then rejected by the full suite
    line["status"], line["adopted"] = "rejected", False
    line["reject_reason"] = "full-suite-failed"
    line["reject_evidence"] = {"exit_code": 1, "failing_tests": ["tests.simulated.TestSimulated.test_simulated"],
                               "output_sha256": hashlib.sha256(b"simulated red suite output").hexdigest(), "evidence_path": "simulated"}
    tune._write_log([line])
    print("synthetic rejected tuning log line written (policy files remain at B)")



# ------------------------------------------------------------------ Round 4: synthetic doc-title bundle (spec §5)
def synthetic_doc_bundle(out_dir) -> pathlib.Path:
    """20 fake support pages whose <h1> contain fixture-catalog resource tokens, served through a fake fetch into a real bundle."""
    from tests.benchmarks import doc_titles as dt, round_seal as rs, alias_candidates_tool as act
    _, internal, _, _ = rs.load_catalogs_from_cache(_fixture_cache(), ROUND)
    noise = frozenset(_read(f"{DATA_REL}/search_ranking.json")["path_noise"])
    toks = list(act.concept_tokens(internal, noise))[:20]
    src = dict(dt.DOC_SOURCES[0]); locs = [f"{src['allowed_loc_prefix']}what-is-{t}-{i}/" for i, t in enumerate(toks)]
    pages = {u: f"<html><head><title>What is {t}? | Jira Cloud | Atlassian Support</title></head><body><h1>What is a {t}?</h1></body></html>".encode()
             for u, t in zip(locs, toks)}
    sm = ("<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in locs) + "</urlset>").encode()
    fetch = lambda url: (200, url, sm if url == src["sitemap_url"] else pages[url])
    dt.acquire([src], out_dir, fetch, delay=0)
    return pathlib.Path(out_dir)


# ------------------------------------------------------------------ Round 4: pre-T blockers and outcomes (spec §4.1, §9.1)
def pre_t_blockers(result, event, diagnostics=None) -> list:
    """spec §4.1: the four blocker kinds, computed independently; any → STOP_FOR_AMENDMENT (non-terminal)."""
    out = []
    unreachable = sorted(f["id"] for f in result.seed_result["failed"])
    if unreachable:
        out.append({"kind": "unreachable_seed", "seeds": unreachable, "diagnostics": diagnostics or {}})
    broken = {"regression_effective": result.regression_result["effective_passed"],
              "regression_failed": sorted(f["id"] for f in result.regression_result.get("failed", [])), "fixture_final": list(result.fixture_result["final"])}
    if result.regression_result["effective_passed"] != 14 or result.fixture_result["final"]:
        out.append({"kind": "tuning_accept_false", "invariants": broken})
    if result.validation_errors:
        out.append({"kind": "alias_validation_error", "errors": list(result.validation_errors)})
    if not event["pass"]:
        out.append({"kind": "inherited_ac_r3_01_failure", "event": {k: event[k] for k in ("seed", "regression_raw", "regression_effective", "fixture_failing", "equivalence_mismatches") if k in event}})
    return out


def append_outcome(work, record, outcomes_path=None, freeze=None):
    """pre-T not reached: only after a user decision ledgered AFTER the last pre-T checkpoint (STOP_FOR_AMENDMENT is not terminal).
    aborted-pre-B: no STOP check (the round has a T) but the strict compound shape against the real freeze (spec §9.1)."""
    from tests.benchmarks import evaluator as ev
    events = [json.loads(l) for l in (pathlib.Path(work) / "controller-events.jsonl").read_text(encoding="utf-8").splitlines()]
    if record["outcome"] == "pre-T not reached":
        idx = [i for i, e in enumerate(events) if e.get("event") == "pre_t_checkpoint"]
        if not idx:
            raise SystemExit("REFUSED: no pre_t_checkpoint event; a pre-T terminal needs a checkpoint and a user decision")
        decided = any(e.get("event") == "user_decision" and e.get("decision") == "TERMINAL_PRE_T_NOT_REACHED" for e in events[idx[-1] + 1:])
        if not decided:
            raise SystemExit("REFUSED: pre-T terminal requires a user_decision TERMINAL_PRE_T_NOT_REACHED event after the last pre_t_checkpoint")
    path = pathlib.Path(outcomes_path or ev.OUTCOMES); cur = ev.load_round_outcomes(path) if path.exists() else []
    fz = freeze if freeze is not None else ev.load_round_freeze()
    ev.round_states(fz, cur + [record])                        # strict shape check against the REAL freeze (aborted-pre-B needs freeze[N])
    path.write_text(json.dumps(cur + [record], indent=1) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ Round 4: X_preB lifecycle (spec §9.4, AC-R4-09)
def _t_commit(tree) -> str:
    out = subprocess.run(["git", "log", "--format=%H", "-S", f'"round": {ROUND}', "--", "tests/benchmarks/round_freeze.json"], cwd=tree, capture_output=True, text=True).stdout.split()
    assert out, "no T commit (freeze entry) in history"
    return out[-1]


def apply_XpreB(state=2):
    """X_preB on the post-T tree (no B): hidden hygiene for spec §9.4 state `state`, restore the T tree, outcomes sha chain,
    readiness block; then validate-terminal must pass (the driver commits and runs the suite afterwards)."""
    from tests.benchmarks import round_seal as rs, evaluator as ev
    work = ROOT / SIM_DIR; sealed = work / "sealed"; plain = work / "plain"; led = work / "hidden_attempt_needles.jsonl"
    for d in (work, sealed, plain): d.mkdir(parents=True, exist_ok=True)
    T = _t_commit(ROOT); HK = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()[0]
    ev_path = work / "controller-events.jsonl"
    log = lambda e: ev_path.open("a", encoding="utf-8").write(json.dumps(e, sort_keys=True) + "\n")
    log({"event": "xpreb_start", "reason": "synthetic acquisition defect after T", "found_at_commit": T, "t_commit": T, "invalidates_policy": True,
         "invalid_doc_titles_source_bundle_sha256": ev.freeze_for(ROUND)["doc_titles_source_bundle_sha256"], "freeze_entry_sha256": ev.canonical_sha256(ev.freeze_for(ROUND))})
    qw = [NATO_WORDS[i] for i in (10, 3, 7, 1, 5)]; q = " ".join(qw)        # synthetic 5-word hidden query (never a literal in any source file)
    if state == 2:                                                   # generator/review plaintext only (no standard manifest)
        (plain / "gen-attempt-1.txt").write_text(f"candidate answer is: {' '.join(qw[:3])}\n{' '.join(qw[3:])} because ...\n", encoding="utf-8")
        (plain / "review-input.json").write_text(json.dumps({"records": [{"id": "h-001", "query": q}]}), encoding="utf-8")
        rs.append_attempt_needles(led, [plain / "gen-attempt-1.txt", plain / "review-input.json"])
    if state in (3, 4, 5):                                           # sealed plaintext, ledgered at seal time
        (sealed / f"round{ROUND}-sealed.json").write_text(json.dumps({"held_out": [{"id": "h-001", "query": q}], "negative": []}), encoding="utf-8")
        rs.append_attempt_needles(led, [sealed / f"round{ROUND}-sealed.json"])
    if state in (4, 5):                                              # standard needle manifest already written
        (work / "needle-manifest.json").write_text(json.dumps(rs.needle_manifest([q])), encoding="utf-8")
    if state == 5:                                                   # user encrypted and deleted the plaintext: ciphertext + ledger + manifest remain
        (sealed / f"round{ROUND}-sealed.json.enc").write_bytes(b"synthetic ciphertext"); (sealed / f"round{ROUND}-sealed.json").unlink()
    e = rs.xpreb_cleanup(work, sealed, ROUND)
    log(e)
    if e.get("cleanup_manifest_sha256"):
        allow = [str(work / "xpreb_cleanup_manifest.json"), str(ROOT / ".git")] + rs.t_baseline_identical_files(ROOT, T)   # files unchanged since T cannot leak post-T text
        hits = rs.scan_for_needles([str(ROOT)], json.loads((work / "xpreb_cleanup_manifest.json").read_text(encoding="utf-8")), allow=allow)
        log({"event": "xpreb_cleanup_scan", "manifest_sha256": e["cleanup_manifest_sha256"], "unexpected_hits": hits})
        assert not hits, hits
    subprocess.run(["git", "checkout", T, "--", DATA_REL, "tests/benchmarks/search_queries.json"], cwd=ROOT, check=True)     # restore the T tree
    at = ev.file_sha256(ROOT / "tests/benchmarks/round_outcomes.json")
    assert at == ev.freeze_for(ROUND)["round_outcomes_sha256"], "round_outcomes.json changed since T"
    log({"event": "round_outcomes_sha256_at_T", "sha256": at})
    append_outcome(work, {"round": ROUND, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": True,
                          "reject_reason": "synthetic acquisition defect after T", "t_commit": T}, outcomes_path=ROOT / "tests/benchmarks/round_outcomes.json")
    log({"event": "round_outcomes_sha256_after_append", "sha256": ev.file_sha256(ROOT / "tests/benchmarks/round_outcomes.json")})
    with (ROOT / "docs/phase3-readiness.md").open("a", encoding="utf-8") as fh:
        fh.write(f"\n## Search Quality Round 4 — aborted before B (synthetic)\nhousekeeping_commit: {HK}\nt_commit: {T}\nterminal_branch: X_preB\nhidden_state: {state}\n")
    code = rs.main(["validate-terminal", "--round", str(ROUND), "--state", "X_preB", "--work", str(work), "--sealed-dir", str(sealed)])
    assert code == 0, "validate-terminal failed"
    print(f"X_preB state {state}: cleanup {e.get('cleanup_manifest', e.get('cleanup_manifest_sha256'))}; terminal ok")


def simulate_xpreb_in_temp_tree(td, state):
    """Unit-test helper: git-archive HEAD into td, apply T then XpreB<state>; -> (validate-terminal problems, ledgered-before-delete flag)."""
    tree = pathlib.Path(td) / "tree"; tree.mkdir()
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split("\n")
    for rel in files:                                                   # working tree (tracked + untracked), so uncommitted tooling is simulated too
        if rel and (ROOT / rel).is_file():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / rel, tree / rel)
    _git(tree, "init", "-q"); _git(tree, "add", "-A"); _git(tree, "commit", "-q", "-m", "H (working tree copy)")
    for step in ("T", f"XpreB{state}"):
        r = subprocess.run([sys.executable, "tests/benchmarks/round4_simulation.py", "--apply", step], cwd=tree, env=_env(), capture_output=True, text=True)
        if r.returncode != 0:
            return [f"apply {step} failed: {r.stdout[-800:]}{r.stderr[-800:]}"], False
        if step == "T":
            _git(tree, "add", "-A"); _git(tree, "commit", "-q", "-m", "simulated T")
    work = tree / SIM_DIR
    r = subprocess.run([sys.executable, "tests/benchmarks/round_seal.py", "validate-terminal", "--round", str(ROUND), "--state", "X_preB", "--work", str(work), "--sealed-dir", str(work / "sealed")],
                       cwd=tree, env=_env(), capture_output=True, text=True)
    problems = [l for l in r.stdout.splitlines() if l.startswith("PROBLEM")]
    events = [json.loads(l) for l in (work / "controller-events.jsonl").read_text(encoding="utf-8").splitlines()]
    flag = any(e.get("event") == "xpreb_cleanup" and e.get("all_artifacts_ledgered") is True for e in events)
    return problems, flag


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--phase", choices=("pre-T", "H"))
    ap.add_argument("--apply", choices=("T", "B", "D", "F", "X", "XpreB2", "XpreB3", "XpreB4", "XpreB5"))
    ap.add_argument("--apply-outcome", default=None, metavar="JSON", help="append a round_outcomes.json record (controller CLI, spec §9.1/§9.4)")
    ap.add_argument("--cache-dir", type=pathlib.Path)
    ap.add_argument("--work", type=pathlib.Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    if args.apply_outcome:
        if not args.work:
            print("error: --apply-outcome needs --work", file=sys.stderr); return 2
        append_outcome(args.work, json.loads(args.apply_outcome)); return 0
    if args.apply:
        sys.path.insert(0, str(ROOT))
        if args.apply == "D":
            apply_C(); apply_D()
        elif args.apply.startswith("XpreB"):
            apply_XpreB(state=int(args.apply[-1]))
        else:
            {"T": apply_T, "B": apply_B, "F": apply_F, "X": apply_X}[args.apply]()
        return 0
    if args.phase == "pre-T":
        if not args.cache_dir or not args.work:
            print("error: --phase pre-T needs --cache-dir and --work", file=sys.stderr); return 2
        return run_pre_t(args.cache_dir, args.work)
    if args.phase == "H":
        return drive(args.keep)
    print("error: --phase pre-T|H required", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main())
