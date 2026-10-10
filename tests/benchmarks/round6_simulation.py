"""Controller tool (not a unittest module): the binding Round 6 pre-T checkpoint (Round 6 spec §4.2 metric-vector acceptance,
§3.5 scorer-rule counterexample, §4.3 training-split pin) plus a synthetic H lifecycle simulation and the real-data T rehearsal
(spec §5.2), copied from tests/benchmarks/round5_simulation.py.

    python tests/benchmarks/round6_simulation.py --phase pre-T --cache-dir S --work DIR
    python tests/benchmarks/round6_simulation.py --phase rehearsal --cache-dir S --work DIR
    python tests/benchmarks/round6_simulation.py --phase H [--keep]

--phase pre-T runs the EXACT working-tree policy against a real snapshot S (dry-run tuning pipeline, usage equivalence of the
memoized GridEvaluator, scorer-rule binding, pre-T ledger evidence) and appends a `pre_t_checkpoint` event to DIR/controller-events.jsonl;
exit 0 iff no blocker.

--phase rehearsal runs the T command sequence, the full suite and the pre-T dry-run on a throwaway `git archive HEAD` tree with a
temp work dir seeded with the pre-T evidence; it appends `rehearsal_report` and never writes the checkout.

--phase H applies the Round 6 commits (T, B, then branches C+D / F / X and X_preB per hidden state 2-5) on a throwaway `git archive HEAD` copy
and runs the full offline suite after each one, so the frozen integrity tests are known to support every branch
before H is declared. Only synthetic data is used: no real snapshot, no sealed plaintext, no network;
ATLASSIAN_DOCS_* variables are removed from the subprocess environment.
"""
import argparse, copy, dataclasses, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid

ROUND = 6
SIM_DIR = ".round6-sim"                       # inside the temp tree: synthetic snapshot and plaintext
LEXICON_WORD, LEXICON_TARGET = "zzsynthetic", "issue"
LEXICON_PHRASE, LEXICON_PHRASE_TARGET = "zzalpha zzbeta", "issue"          # v1.24: synthetic phrase -> when_all rule (spec §6)
DATA_REL = "tools/atlassian_docs/intelligence/data"
STEPS_COMMON = ("T", "B")
BRANCHES = ("D", "F", "X", "XpreB2", "XpreB3", "XpreB4", "XpreB5")   # Round 4 spec §9.4: X_preB per hidden state
FAILING = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
from tests.benchmarks import evaluator as ev  # noqa: E402


INPUT_SHA256 = {}                                                   # Round 6 plan PR-6: no lexicon resolution inputs


def input_blockers(work) -> list:
    bad = [n for n, sha in INPUT_SHA256.items() if not (work / "inputs" / n).exists() or ev.file_sha256(work / "inputs" / n) != sha]
    return [{"kind": "input_sha_mismatch", "files": bad}] if bad else []


def counterexample_reference_problems(ref, work, registry_fp) -> list:
    """Round 5 spec §8/§9 + Round 6 plan PR-6: the T-committed reference is internally consistent and bound to this run's inputs."""
    from tests.benchmarks import counterexample as cx
    out = []
    cmap = {json.dumps(list(k)): list(v) for k, v in cx.canonical_policy_map(ref["policy"]).items()}
    if ev.canonical_sha256(ref["policy"]) != ref.get("policy_canonical_sha256"):
        out.append("policy_canonical_sha256")
    if cmap != ref.get("canonical_policy_map") or ev.canonical_sha256(cmap) != ref.get("canonical_policy_map_sha256"):
        out.append("canonical_policy_map")
    titles = sorted(({"product": t["product"], "url": t["url"], "title": t["title"]} for t in ref.get("titles") or []), key=lambda t: (t["product"], t["url"]))
    if ev.canonical_sha256(titles) != ref.get("titles_sha256"):
        out.append("titles_sha256")
    snap_p = work / "inputs/round4/doc-titles-snapshot.json"
    if snap_p.exists():
        snap = json.loads(snap_p.read_text(encoding="utf-8"))
        want = sorted(({"product": t["product"], "url": t["url"], "title": t["title"]} for t in snap["titles"]), key=lambda t: (t["product"], t["url"]))
        if titles != want:
            out.append("titles differ from the bound snapshot")
    inputs = ref.get("inputs") or {}                                   # Round 6 plan PR-6: the H alias policy and the registry
    expected = set(INPUT_SHA256) | {"aliases_h_sha256", "registry_fingerprint"}
    if set(inputs) != expected:
        out.append(f"input keys {sorted(set(inputs) ^ expected)}")
    f = work / "aliases-h.json"
    if not f.exists() or inputs.get("aliases_h_sha256") != ev.file_sha256(f):
        out.append("aliases_h_sha256")
    if inputs.get("registry_fingerprint") != registry_fp:
        out.append("registry_fingerprint")
    return out


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
    r = subprocess.run([sys.executable, "tests/benchmarks/round6_simulation.py", "--apply", step], cwd=tree,
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
    tree = pathlib.Path(tempfile.mkdtemp(prefix="round6-sim-"))
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
                tree_after_t = pathlib.Path(tempfile.mkdtemp(prefix="round6-sim-afterT-")); shutil.rmtree(tree_after_t); shutil.copytree(tree, tree_after_t)
        for branch in BRANCHES:
            btree = pathlib.Path(tempfile.mkdtemp(prefix=f"round6-sim-{branch}-"))
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
from tests import tune_search_ranking as tune  # noqa: E402  (module-level: tests use sim.tune)

BOUNDS = (("wv", "== 0"), ("fr", "== 0"), ("sr3", "10·sr3 ≥ 9·|seed|"), ("src", "10·src ≥ 9·|seed|"), ("srk", "10·srk ≥ 9·src"),
          ("rp3", "== |regression_positive|"), ("rpk", "== |regression_positive|"), ("nab", "8·nab ≥ 7·|regression_negative|"))


def metric_violations(m) -> list:
    ok = {"wv": m["wv"] == 0, "fr": m["fr"] == 0, "sr3": 10 * m["sr3"] >= 9 * m["n_seed"], "src": 10 * m["src"] >= 9 * m["n_seed"],
          "srk": 10 * m["srk"] >= 9 * m["src"], "rp3": m["rp3"] == m["n_rp"], "rpk": m["rpk"] == m["n_rp"], "nab": 8 * m["nab"] >= 7 * m["n_rn"]}
    return [{"item": k, "value": m[k], "bound": b} for k, b in BOUNDS if not ok[k]]


def equivalence_mismatches(state, rp, bench, ap, n=20, seed=20261011) -> list:
    """GridEvaluator.usage == search_operations (keys AND recommendation) on S and the fixture registry, sampled grid points + baseline."""
    import random
    from unittest import mock
    from tools.atlassian_docs.intelligence import policy, search
    pts = random.Random(seed).sample(tune.grid_points(rp.tuning_grid), n) + [dict(rp.baseline)]
    fx_state, fx_bench = tune.fixture_state(), tune.fixture_bench(bench)
    pairs = [(state, [r["query"] for s in ev.TRAINING_SECTIONS for r in bench.get(s) or []]),
             (fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]])]
    out = []
    for st, queries in pairs:
        ge = tune.GridEvaluator(st, queries, ap, rp.ordering_rules["terminal_alias_full_weight"])
        for p in pts:
            rpp = tune.ranking_with(rp, p)
            with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=ap):
                for q in queries:
                    o = search.search_operations(st, q, limit=5)
                    if ge.usage(q, rpp) != ([r["key"] for r in o["results"]], o["recommended_operation"]):
                        out.append({"point": p, "query_sha256": ev.canonical_sha256(q)})
    return out


def pre_t_blockers_r6(result, event, equivalence, extra=()) -> list:
    """Round 6 spec §4.2: tuning_accept on the dry-run result; every failing term is a blocker with its evidence."""
    out = []
    mv = metric_violations(result.metrics)
    if mv:
        out.append({"kind": "metric_threshold", "violations": mv})
    if not (result.scorer_rule or {}).get("ok"):
        out.append({"kind": "scorer_rule_violation", "scorer_rule": {k: v for k, v in (result.scorer_rule or {}).items() if k != "loss_list"},
                    "loss_list": (result.scorer_rule or {}).get("loss_list", [])})
    if result.fixture_result["final"]:
        out.append({"kind": "fixture_fail", "failing": list(result.fixture_result["final"])})
    if result.validation_errors:
        out.append({"kind": "alias_validation_error", "errors": list(result.validation_errors)})
    cxr = result.counterexample_result or {}
    if cxr.get("losses"):
        out.append({"kind": "counterexample_loss", "losses": cxr["losses"]})
    if (cxr.get("classes") or {}).get("uncovered_proposer"):
        out.append({"kind": "counterexample_uncovered_proposer", "keys": cxr["classes"]["uncovered_proposer"]})
    if equivalence:
        out.append({"kind": "equivalence_mismatch", "count": len(equivalence), "first": equivalence[:5]})
    if not result.tuning_accept and not out:
        out.append({"kind": "tuning_accept_false", "invariants": {"reason": "dry-run tuning_accept false with no other blocker"}})
    return out + list(extra)


def dry_run_pipeline_r6(state, rp, bench, aliases_raw, cands_doc, corpus):
    from unittest import mock
    from tests.benchmarks import scorer_rule_cx as cx6
    from tools.atlassian_docs.intelligence import policy
    b_sha = policy.canonical_sha256(aliases_raw)
    queries = [r["query"] for s in ev.TRAINING_SECTIONS for r in bench.get(s) or []]
    fx_state, fx_bench = tune.fixture_state(), tune.fixture_bench(bench)
    tf = rp.ordering_rules["terminal_alias_full_weight"]
    ge = tune.GridEvaluator(state, queries, tune._alias_policy(aliases_raw), tf)
    ge_fx = tune.GridEvaluator(fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]], tune._alias_policy(aliases_raw), tf)
    shas = {}
    raw_sha = lambda raw: shas.setdefault(id(raw), policy.canonical_sha256(raw))
    evaluate_fn = lambda p, raw: tune.evaluate_usage_fast(ge, rp, p, bench) if raw_sha(raw) == b_sha else tune.evaluate_usage_point(state, rp, p, bench, tune._alias_policy(raw))
    fixture_fn = lambda p, raw: tune.fixture_failures_fast(ge_fx, rp, p, fx_bench) if raw_sha(raw) == b_sha else tune.fixture_failures(fx_state, rp, p, fx_bench, tune._alias_policy(raw))
    scorer_fn = lambda p, raw: cx6.compare(state, rp, p, tune._alias_policy(raw), corpus, bound_fingerprint=state.registry.fingerprint, aliases_sha256=raw_sha(raw))
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run must not write"))
    with mock.patch.object(tune, "write_constants", boom), mock.patch.object(tune, "_write_log", boom):
        return tune.run_pipeline_result_r6(evaluate_fn, bench, aliases_raw, cands_doc, rp.tuning_grid, dict(rp.baseline), fixture_fn, scorer_fn,
                                           {r["id"]: r["query"] for s in ("seed", "regression_positive") for r in bench.get(s) or []},
                                           counterexample_fn=tune.final_counterexample_fn(state, rp, aliases_raw, round=ROUND, root=ROOT))


PRE_T_EVENTS = ("scorer_rule_corpus_pinned", "relabel_applied")       # promotion_sealed is historical pre-relabel evidence (plan review 2 P1-1)
PRE_T_FILES = ("aliases-h.json", "inputs/round4/doc-titles-snapshot.json")


def load_pre_t_evidence(work) -> tuple:
    """Everything run_pre_t reads from the work dir: the latest of each PRE_T_EVENTS ledger event and the PRE_T_FILES."""
    work, probs = pathlib.Path(work), []
    led = work / "controller-events.jsonl"
    lines = [json.loads(l) for l in led.read_text(encoding="utf-8").splitlines() if l.strip()] if led.exists() else []
    out = {}
    for name in PRE_T_EVENTS:
        e = next((x for x in reversed(lines) if x.get("event") == name), None)
        if e is None:
            probs.append(f"ledger event {name} missing")
        out[name] = e
    for rel in PRE_T_FILES:
        if not (work / rel).is_file():
            probs.append(f"file {rel} missing")
    probs += relabel_chain_problems(lines)
    return out, probs


RULING_KEYS = {"event", "from_training_split_sha256", "immutable_split_sha256", "reason", "thread", "review_output_sha256"}
REVIEW_THREAD = "6ac7eb56-eed8-83e8-a55e-a4b67e3088de"            # review thread 2 (plan review 4 P1-1: canonical authority)
_HEX64 = re.compile(r"[0-9a-f]{64}")


def _ruling_ok(r) -> bool:
    return (set(r) == RULING_KEYS and isinstance(r["reason"], str) and r["reason"].strip() != "" and r["thread"] == REVIEW_THREAD
            and all(isinstance(r[k], str) and _HEX64.fullmatch(r[k]) for k in ("from_training_split_sha256", "immutable_split_sha256", "review_output_sha256")))


def relabel_chain_problems(lines) -> list:
    """plan review 2 P0-2 / review 3 P0-1 + P1-1: a later relabel_applied needs, between it and the previous one, a well-formed
    relabel_rerun_ruling bound to the previous generation (its split) and to the unchanged immutable projection; the new generation
    must keep that immutable projection. Only relabel-managed fields can therefore ever be re-baselined."""
    probs, idx = [], [i for i, x in enumerate(lines) if x.get("event") == "relabel_applied"]
    for i in idx:
        if not lines[i].get("immutable_split_sha256") or not lines[i].get("training_split_sha256"):
            probs.append("relabel_applied lacks training_split_sha256 / immutable_split_sha256")
    for prev, cur in zip(idx, idx[1:]):
        rulings = [x for x in lines[prev + 1:cur] if x.get("event") == "relabel_rerun_ruling"]
        if len(rulings) != 1 or not _ruling_ok(rulings[0]):
            probs.append("relabel_applied re-ledgered without exactly one well-formed relabel_rerun_ruling"); continue
        r, a, b = rulings[0], lines[prev], lines[cur]
        if r["from_training_split_sha256"] != a.get("training_split_sha256"):
            probs.append("relabel_rerun_ruling does not name the previous generation's training split")
        if not (r["immutable_split_sha256"] == a.get("immutable_split_sha256") == b.get("immutable_split_sha256")):
            probs.append("relabel rerun changed the immutable training projection (only relabel-managed fields may change)")
    return probs


def seed_rehearsal_work(real_work, temp_work) -> dict:
    """plan review 1 P0-3: copy exactly the pre-T evidence (latest PRE_T_EVENTS lines, PRE_T_FILES) into the rehearsal work dir and
    verify every copied sha; returns {name: sha256}."""
    real_work, temp_work = pathlib.Path(real_work), pathlib.Path(temp_work)
    evidence, probs = load_pre_t_evidence(real_work)
    if probs:
        raise SystemExit(f"error: real work dir lacks pre-T evidence: {probs}")
    temp_work.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(evidence[n]) for n in PRE_T_EVENTS]           # latest event of each kind (already validated on the real ledger)
    (temp_work / "controller-events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shas = {}
    for rel in PRE_T_FILES:
        dst = temp_work / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real_work / rel, dst)
        if ev.file_sha256(dst) != ev.file_sha256(real_work / rel):
            raise SystemExit(f"error: copy of {rel} differs")
        shas[rel] = ev.file_sha256(dst)
    copied, _ = load_pre_t_evidence(temp_work)
    if any(copied[n] != evidence[n] for n in PRE_T_EVENTS):
        raise SystemExit("error: seeded ledger events differ from the real ledger")
    return shas


def run_pre_t(cache: pathlib.Path, work: pathlib.Path) -> int:
    from tests.benchmarks import scorer_rule_cx as cx6
    from tools.atlassian_docs.intelligence import policy
    work = pathlib.Path(work)
    rp, bench = policy.load_ranking(tune.RANKING_PATH), tune._BENCH
    aliases_raw, ranking_raw = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    ap, cands_doc = tune._alias_policy(aliases_raw), json.loads(tune.CANDIDATES_PATH.read_text(encoding="utf-8"))
    evidence, ev_problems = load_pre_t_evidence(work)
    corpus_meta = evidence.get("scorer_rule_corpus_pinned")
    ref = json.loads((ROOT / f"tests/benchmarks/round{ROUND}-counterexample-reference.json").read_text(encoding="utf-8"))

    def body(state):
        corpus = cx6.corpus(state)
        extra = [{"kind": "pre_t_evidence_missing", "problems": ev_problems}] if ev_problems else []
        from tests.benchmarks import round6_labels as labels
        pinned_split = (evidence.get("relabel_applied") or {}).get("training_split_sha256")
        pinned_imm = (evidence.get("relabel_applied") or {}).get("immutable_split_sha256")
        if pinned_split != labels.training_split_sha256(bench) or pinned_imm != labels.immutable_split_sha256(bench):   # latest authorized == pre-T
            extra.append({"kind": "training_split_mismatch", "pinned": [pinned_split, pinned_imm],
                          "current": [labels.training_split_sha256(bench), labels.immutable_split_sha256(bench)]})
        if corpus_meta is None or corpus_meta["registry_fingerprint"] != state.registry.fingerprint or corpus_meta["corpus_sha256"] != ev.canonical_sha256(corpus):
            extra.append({"kind": "scorer_rule_binding", "problems": ["corpus metadata missing or differs from the ledger pin"]})
        result = dry_run_pipeline_r6(state, rp, bench, aliases_raw, cands_doc, corpus)
        return state.registry.fingerprint, result, equivalence_mismatches(state, rp, bench, ap), extra
    fp, result, eq, extra = tune._with_state(cache, body)
    problems = counterexample_reference_problems(ref, work, fp)
    if problems:
        extra.append({"kind": "counterexample_reference_mismatch", "problems": problems})
    blockers = pre_t_blockers_r6(result, {"pass": True}, eq, extra=extra)
    e = {"event": "pre_t_checkpoint", "round": ROUND, "registry_fingerprint": fp, "metrics": result.metrics, "selection": result.selection,
         "scorer_rule": {k: v for k, v in (result.scorer_rule or {}).items() if k != "loss_list"},
         "pre_t_blockers": blockers, "blocking_reasons": [b["kind"] for b in blockers], "equivalence_mismatches": len(eq),
         "dry_run": {"tuning_accept": result.tuning_accept, "selected_point": result.selected_point, "fixture_final": result.fixture_result["final"],
                     "validation_errors": result.validation_errors},
         "pipeline_input_sha256": pipeline_input_sha256(ranking_raw, aliases_raw, cands_doc, bench),
         "pipeline_result_sha256": policy.canonical_sha256(dataclasses.asdict(result)),
         "result": "pass" if not blockers else "stop_for_amendment",
         "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    work.mkdir(parents=True, exist_ok=True)
    with open(work / "controller-events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(e) + "\n")
    print(json.dumps(e, indent=1)); return 0 if e["result"] == "pass" else 1


def pipeline_input_sha256(ranking_raw, aliases_raw, cands_doc, bench) -> str:
    """Hash of the dry-run's inputs, built from JSON data only (the loaded policy's grid is a read-only mapping proxy)."""
    from tools.atlassian_docs.intelligence import policy
    return policy.canonical_sha256({"ranking": ranking_raw, "aliases": aliases_raw, "candidates": cands_doc, "bench": bench, "grid": ranking_raw["tuning_grid"]})


def _run_in_tree(tree, argv):
    r = subprocess.run(argv, cwd=tree, env=_env(), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def t_commands(cache, work, tree) -> list:
    """The T sequence (Task C5 runs the same list in the real checkout): candidates, classify, carry, freeze."""
    py, d = sys.executable, DATA_REL
    return [[py, "tests/benchmarks/alias_candidates_tool.py", "candidates", "--cache-dir", str(cache), "--round", str(ROUND)],
            [py, "tests/benchmarks/alias_candidates_tool.py", "classify", "--cache-dir", str(cache), "--round", str(ROUND)],
            [py, "tests/benchmarks/concept_lexicon_check.py", "carry", "--lexicon", f"{d}/concept_lexicon.json", "--candidates", f"{d}/alias_candidates.json",
             "--prior-lexicon", str(work / "prior-concept_lexicon.json"), "--prior-candidates", str(work / "prior-alias_candidates.json")],
            [py, "tests/benchmarks/round_seal.py", "freeze", "--round", str(ROUND), "--cache-dir", str(cache),
             "--reference-enc", str(pathlib.Path.home() / ".atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc")]]


def run_rehearsal(cache, work, dry=False) -> int:
    """spec §5.2: on a throwaway `git archive HEAD` tree — T commands, full suite in the T state, pre-T dry-run, worker-brief
    handshake format; the working tree is never written. Appends rehearsal_report to work/controller-events.jsonl."""
    tree = pathlib.Path(tempfile.mkdtemp(prefix="round6-rehearsal-"))
    temp_work = pathlib.Path(tempfile.mkdtemp(prefix="round6-rehearsal-work-"))
    steps = []
    try:
        if not dry:
            archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
            subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
            for f in sorted((pathlib.Path(work) / "frozen").glob("round6-*")):
                shutil.copyfile(f, tree / "tests/benchmarks" / f.name)
            try:
                seeded = seed_rehearsal_work(work, temp_work); steps.append({"argv": ["seed_rehearsal_work"], "exit": 0, "output_sha256": ev.canonical_sha256(seeded)})
            except SystemExit as exc:                                 # plan review 2 P1-4: a seeding failure is a recorded rehearsal failure
                steps.append({"argv": ["seed_rehearsal_work"], "exit": 1, "output_sha256": hashlib.sha256(str(exc).encode("utf-8")).hexdigest()})
        for argv in ([] if steps and steps[-1]["exit"] else t_commands(cache, work, tree) + [[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                                                     [sys.executable, "tests/benchmarks/round6_simulation.py", "--phase", "pre-T",
                                                      "--cache-dir", str(cache), "--work", str(temp_work)]]):
            code, out = _run_in_tree(tree, argv)
            steps.append({"argv": argv[1:3], "exit": code, "output_sha256": hashlib.sha256(out.encode("utf-8")).hexdigest()})
            if code != 0:
                break
        brief = tree / f"tests/benchmarks/round{ROUND}-worker-brief.md"
        hs_ok = dry or (brief.exists() and handshake_format_ok(brief.read_text(encoding="utf-8")))
        report = {"event": "rehearsal_report", "round": ROUND, "steps": steps, "handshake_format_ok": hs_ok,
                  "failures": sum(1 for s in steps if s["exit"] != 0) + (0 if hs_ok else 1),
                  "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        pathlib.Path(work).mkdir(parents=True, exist_ok=True)
        with open(pathlib.Path(work) / "controller-events.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report) + "\n")
        print(json.dumps(report, indent=1))
        return 0 if report["failures"] == 0 else 1
    finally:
        shutil.rmtree(tree, ignore_errors=True); shutil.rmtree(temp_work, ignore_errors=True)


def handshake_format_ok(text) -> bool:
    return f"ROUND{ROUND}-WORKER-HANDSHAKE" in text and "Acceptance (Round 6 spec §4.2, byte-for-byte)" in text


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
    """Deterministic Round 5 synthetic hidden set (Round 4 generator) over the fixture catalog (spec §4 v1.22): 16 held_out (4 of them
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
                     "forbidden_top1": [op["key"]], "origin": f"negative-r{ROUND}", "failure_classes": [], "ambiguous": False, "no_answer": True})
    for i, op in enumerate(ops[4:8]):                                 # verb-less negatives: abstained regardless of forbidden_top1
        word = next(words)
        negs.append({"id": f"n-{5 + i:03d}", "query": f"decoy {word} item", "expected_top1_any": [],
                     "forbidden_top1": [op["key"]], "origin": f"negative-r{ROUND}", "failure_classes": [], "ambiguous": False, "no_answer": True})
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
    """T (Round 6 spec §5, plan PR-6): candidates --round 6 (seed ∪ regression_positive), R5/R6 classification, carry of the frozen
    lexicon/candidates over themselves (no new lexicon in Round 6), synthetic frozen texts, synthetic archived Round 2 ciphertext,
    the PR-6 counterexample reference (H alias policy) and the round 6 freeze entry. Aliases are not touched at T."""
    from tests.benchmarks import alias_candidates_tool as act, concept_lexicon_check as clc, round_seal as rs
    from tests.benchmarks.evaluator import canonical_sha256
    cache = _fixture_cache()
    _, internal, fp, shas = rs.load_catalogs_from_cache(cache, ROUND)
    ranking = _read(f"{DATA_REL}/search_ranking.json")
    aliases = _read(f"{DATA_REL}/search_aliases.json")
    prior_lexicon = _read(f"{DATA_REL}/concept_lexicon.json"); prior_lexicon_sha = ev.file_sha256(ROOT / DATA_REL / "concept_lexicon.json")
    bench = _read("tests/benchmarks/search_queries.json")
    doc = act.candidates(bench, internal, ranking, aliases, ROUND)              # 1. candidates (fixture-scale)
    old_doc = _read(f"{DATA_REL}/alias_candidates.json"); old_doc_sha = ev.file_sha256(ROOT / DATA_REL / "alias_candidates.json")
    doc["generated_from"] = act.provenance(fp, shas, {"ranking": canonical_sha256(ranking), "aliases": canonical_sha256(aliases),
                                                      "bench": canonical_sha256(bench), "verb_inventory": canonical_sha256(ranking["verb_methods"])})
    lexicon, doc = clc.carry_forward(prior_lexicon, prior_lexicon, doc, old_doc,                     # 2. carry (Round 5 v1.12)
                                     {"concept_lexicon_sha256": prior_lexicon_sha, "alias_candidates_sha256": old_doc_sha})
    act._write(ROOT / DATA_REL / "concept_lexicon.json", lexicon)
    act._write(ROOT / DATA_REL / "alias_candidates.json", doc)
    cls = act.classify(bench, internal, ranking, aliases)                      # 3. R5/R6
    for rec in bench["seed"]:
        rec["failure_classes"] = [c for c in rec["failure_classes"] if c not in ("R5", "R6")] + cls[rec["id"]]
    bench["held_out"], bench["negative"] = [], []                              # the round's pending hidden slots (commit B fills them)
    rs._write_bench(ROOT / "tests" / "benchmarks" / "search_queries.json", bench)
    for name in ("worker-brief", "hidden-generation-prompt", "hidden-reviewer-prompt"):   # 4. synthetic frozen texts
        text = f"# synthetic round{ROUND} {name}\n<generator catalog lines>\n<verb methods json>\n"
        (ROOT / "tests" / "benchmarks" / f"round{ROUND}-{name}.md").write_text(text, encoding="utf-8")
    sim_dir = ROOT / SIM_DIR; sim_dir.mkdir(exist_ok=True)                      # 5. synthetic archived Round 2 ciphertext
    enc_path = sim_dir / "round2-sealed.json.enc"
    enc_path.write_bytes(b"synthetic archived round2 ciphertext (round6_simulation.py phase H)")
    from tests.benchmarks import doc_titles as dt                              # 6. synthetic doc-title bundle + snapshot (Round 4 spec §5)
    bundle = synthetic_doc_bundle(sim_dir / "doc-title-sources")
    snap_path = sim_dir / "doc-titles-snapshot.json"
    snap_path.write_text(json.dumps(dt.snapshot(bundle), sort_keys=True, indent=1) + "\n", encoding="utf-8")
    write_synthetic_reference(aliases, snap_path, fp)                          # 7. PR-6 counterexample reference
    with open(os.devnull, "w") as null:                                        # 8. freeze entry (ev.round_freeze_hashes + Round 4/5/6 keys)
        old, sys.stdout = sys.stdout, null
        try:
            code = rs.main(["freeze", "--round", str(ROUND), "--cache-dir", str(cache), "--reference-enc", str(enc_path),
                            "--doc-title-sources", str(bundle), "--doc-titles", str(snap_path), "--base-commit", "HEAD"])
        finally:
            sys.stdout = old
    assert code == 0
    print(f"{len(doc['candidates'])} candidates; R6 seeds {sum('R6' in v for v in cls.values())}; lexicon carried "
          f"({len(lexicon['lexicon'])} entries); round_freeze round {ROUND} added")


def write_synthetic_reference(policy_h, snap_path, fp):
    """Round 6 plan PR-6 (synthetic): the T-committed counterexample reference binds the H alias policy (aliases-h.json, a $W-side
    file - here a synthetic copy under SIM_DIR) and the registry fingerprint; consistency hashes as in Round 5."""
    from tests.benchmarks import counterexample as cx
    work = ROOT / SIM_DIR
    (work / "aliases-h.json").write_text(json.dumps(policy_h, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    snap = json.loads(pathlib.Path(snap_path).read_text(encoding="utf-8"))
    titles = sorted(({"product": t["product"], "url": t["url"], "title": t["title"]} for t in snap["titles"]), key=lambda t: (t["product"], t["url"]))
    cmap = {json.dumps(list(k)): list(v) for k, v in cx.canonical_policy_map(policy_h).items()}
    doc = {"round": ROUND, "policy": policy_h, "policy_canonical_sha256": ev.canonical_sha256(policy_h), "canonical_policy_map": cmap,
           "canonical_policy_map_sha256": ev.canonical_sha256(cmap), "titles": titles, "titles_sha256": ev.canonical_sha256(titles),
           "inputs": {**INPUT_SHA256, "aliases_h_sha256": ev.file_sha256(work / "aliases-h.json"), "registry_fingerprint": fp}}
    (ROOT / f"tests/benchmarks/round{ROUND}-counterexample-reference.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    probs = counterexample_reference_problems(doc, pathlib.Path(work), fp)
    assert probs == [], probs


def apply_B():
    """B: synthetic Round 5 hidden records (16 held_out + 8 negative), the needle manifest over their queries, and
    round_seal `seal` (binds needle_manifest_sha256)."""
    from tests.benchmarks import round_seal as rs
    cache = _fixture_cache()
    _, internal, _, _ = rs.load_catalogs_from_cache(cache, ROUND)
    vm = _read(f"{DATA_REL}/search_ranking.json")["verb_methods"]
    plain = synthetic_hidden_records(internal, vm)
    sim_dir = ROOT / SIM_DIR; sim_dir.mkdir(exist_ok=True)
    plain_path = sim_dir / f"round{ROUND}-plain.json"
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


def _synthetic_metrics(bench) -> dict:
    """A perfect Round 6 metric vector over the live training sections (synthetic: no snapshot answers the real bench)."""
    n_seed, n_rp, n_rn = (len(bench.get(s) or []) for s in ev.TRAINING_SECTIONS)
    return {"wv": 0, "fr": 0, "sr3": n_seed, "src": n_seed, "srk": n_seed, "rp3": n_rp, "rpk": n_rp, "nab": n_rn,
            "n_seed": n_seed, "n_rp": n_rp, "n_rn": n_rn}


def _round6_line(point, patch, accept, b_aliases, b_ranking, cands_doc, bench, rp, note) -> dict:
    """The log line with exactly tune._finish6's keys (synthetic values)."""
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy
    fp = cands_doc["generated_from"]["registry_fingerprint"]
    fx = {"constants": [], "final": [] if accept else ["s-001"]}
    line = {"run_id": str(uuid.uuid4()), "run_at": "2026-10-11T00:00:00Z", "git_commit": "0" * 40, "round": ROUND,
            "registry_fingerprint": fp, "baseline_sha256": tune.baseline_sha256(b_aliases, b_ranking, fp, cands_doc, bench),
            "events": list(tune.EVENTS), "constants_selected": point, "selection": {"mode": "accept_pool", "accept_points": 1},
            "grid_size": len(tune.grid_points(rp.tuning_grid)), "grid_runtime_s": 0.1, "fixture_fail": fx,
            "passing_combos": 1 if accept else 0, "aliases_proposed": patch, "metrics": _synthetic_metrics(bench),
            "scorer_rule": {"ok": True, "losses": 0, "eligible": 60},
            "fixture_positive": f"{tune.FIXTURE_COUNTS[0] - len(fx['final'])}/{tune.FIXTURE_COUNTS[0]}",
            "fixture_negative_raw": f"{tune.FIXTURE_COUNTS[1]}/{tune.FIXTURE_COUNTS[1]}",
            "tuning_accept": accept, "tuning_failed": not accept, "counterexample": None,
            "result_sha256": tune.result_sha256(point, patch), "dirty": [], "note": note,
            "ranking_structure_sha256": rp.structure_sha256, "baseline": dict(rp.baseline)}
    line["run_log_sha256"] = policy.canonical_sha256(tune.log_core(line))
    return line


def _empty_patch() -> dict:
    return {"aliases": {}, "rules": [], "notes": {}, "resolved_by_prior_change": [], "no_actions": [], "unresolved": [],
            "fixture_fail": [], "trials": 0, "actions_by_seed": {}}


def apply_C():
    """C (branch D only): one fixture-admissible tuning constant + one frozen-candidate alias (Round 6 note origin), written
    directly as an adopted log line with the Round 6 (_finish6) fields."""
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy
    assert tune.ROUND == ROUND and tune.TUNING_ROUND == ROUND
    rp, bench = policy.load_ranking(tune.RANKING_PATH), tune._BENCH
    b_aliases, b_ranking = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    cands_doc = json.loads(tune.CANDIDATES_PATH.read_text(encoding="utf-8"))
    state, fb = tune.fixture_state(), tune.fixture_bench(bench)
    grid, base = rp.tuning_grid, dict(rp.baseline)
    near = sorted((p for p in tune.grid_points(grid) if tune.l1_index_distance(p, base, grid) == 1),
                  key=lambda p: tuple(p[k] for k in tune.CONSTANT_KEYS))
    point = next(p for p in near if not tune.fixture_failures(state, rp, p, fb, tune._alias_policy(b_aliases)))
    queries = {r["id"]: r["query"] for s in ("seed", "regression_positive") for r in bench.get(s) or []}
    classes = tune.classes_r6(bench, cands_doc["candidates"])
    chosen = None
    for word, c in sorted(cands_doc["candidates"].items()):
        for sid in c["seed_ids"]:
            if "R6" not in classes.get(sid, []):
                continue
            for target in c["targets_by_seed"][sid]:
                trial = tune.apply_actions_r6(b_aliases, [(word, target)], sid)
                if not tune.validate_alias_change(b_aliases, trial, cands_doc["candidates"], queries, classes) \
                        and not tune.fixture_failures(state, rp, point, fb, tune._alias_policy(trial)):
                    chosen = (word, sid, target, trial); break
            if chosen: break
        if chosen: break
    assert chosen, f"no fixture-admissible round{ROUND} alias among the frozen candidates"
    word, sid, target, working = chosen
    tune.write_constants(point)
    tune.ALIASES_PATH.write_text(json.dumps(working, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    policy.load_aliases(tune.ALIASES_PATH)
    patch = {**_empty_patch(), **tune.alias_patch(b_aliases, working), "trials": 1, "actions_by_seed": {sid: [[word, target]]}}
    line = _round6_line(point, patch, True, b_aliases, b_ranking, cands_doc, bench, rp, "simulated")
    line["status"], line["adopted"] = "adopted", True
    tune._write_log([line])
    changed = {k: v for k, v in point.items() if v != base[k]}
    print(f"constants {changed}; round{ROUND} alias {word}->{target} ({sid}); adopted log line")


def apply_D():
    """D: diag --round 5 --bench <plain> --json round5-final.json, then --reference append of a synthetic
    round2-origin plaintext."""
    from tests import diag_search_queries as diag
    from tests.benchmarks import round_seal as rs
    cache = _fixture_cache()
    plain_path = ROOT / SIM_DIR / f"round{ROUND}-plain.json"
    out = ROOT / "tests" / "benchmarks" / f"round{ROUND}-final.json"
    with open(os.devnull, "w") as null:
        old, sys.stdout = sys.stdout, null
        try:
            code, _ = diag.run(["--cache-dir", str(cache), "--round", str(ROUND), "--bench", str(plain_path), "--json", str(out)])
        finally:
            sys.stdout = old
    assert code == 0, f"diag run for round{ROUND}-final.json failed"
    _, internal, _, _ = rs.load_catalogs_from_cache(cache, ROUND)
    ref = _reference_plain(internal)
    ref_path = ROOT / SIM_DIR / f"round{ROUND}-reference-r2.json"
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
    """Shared shape for the F/X branches (Round 6 _finish6 log schema), bypassing the full real pipeline: there is no real snapshot
    large enough to answer the production bench, so the fields are written directly rather than computed."""
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy
    assert tune.ROUND == ROUND
    rp = policy.load_ranking(tune.RANKING_PATH)
    b_aliases, b_ranking = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    cands_doc = json.loads(tune.CANDIDATES_PATH.read_text(encoding="utf-8"))
    return _round6_line(dict(rp.baseline), _empty_patch(), status == "adopted", b_aliases, b_ranking, cands_doc, tune._BENCH, rp,
                        f"simulated {status}")


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


# ------------------------------------------------------------------ Round 4: outcomes (spec §9.1)
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
        fh.write(f"\n## Search Quality Round {ROUND} — aborted before B (synthetic)\nhousekeeping_commit: {HK}\nt_commit: {T}\nterminal_branch: X_preB\nhidden_state: {state}\n")
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
        r = subprocess.run([sys.executable, "tests/benchmarks/round6_simulation.py", "--apply", step], cwd=tree, env=_env(), capture_output=True, text=True)
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
    ap.add_argument("--phase", choices=("pre-T", "H", "rehearsal"))
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
    if args.phase == "rehearsal":
        if not args.cache_dir or not args.work:
            print("error: --phase rehearsal needs --cache-dir and --work", file=sys.stderr); return 2
        return run_rehearsal(args.cache_dir, args.work)
    if args.phase == "H":
        return drive(args.keep)
    print("error: --phase pre-T|rehearsal|H required", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main())
