"""Controller tool (not a unittest module): simulate the Round 2 commits on a throwaway copy of HEAD and run the full
offline suite after each one, so the frozen integrity tests are known to support every branch before H is declared.

    python tests/benchmarks/round2_simulation.py [--keep]

Steps, applied cumulatively to `git archive HEAD` extracted into a temporary directory (this file is copied over the
archived one, so the working version runs):
  T  spec §6 verb inventory verbatim -> search_ranking.json; one synthetic lexicon-r2 alias merged; alias_candidates.json;
     R5/R6 classification; synthetic worker brief / hidden prompts; Round 2 freeze entry (ev.round_freeze_hashes).
  B  round-2 seal metadata + round2_seal over synthetic hidden records (16 held_out + 8 negative).
  C  one tuned constant (fixture-admissible) + one round2 alias from the frozen candidates + an adopted log line.
  D  the synthetic plaintext unsealed into the bench.
After B a dry run of the tuning CLI against the snapshot is reported as an extra smoke check (not part of PASS/FAIL).
The snapshot S is built from the repo's OpenAPI fixtures inside the temp dir. Only synthetic data is used: no real
snapshot, no sealed plaintext, no network; ATLASSIAN_DOCS_* variables are removed from the subprocess environment.
"""
import argparse, copy, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid

STEPS = ("T", "B", "C", "D")
SPEC_REL = "docs/superpowers/specs/2026-10-02-search-quality-round2-design.md"
DATA_REL = "tools/atlassian_docs/intelligence/data"
SIM_DIR = ".round2-sim"                       # inside the temp tree: synthetic snapshot and plaintext
LEXICON_WORD, LEXICON_TARGET = "defect", "issue"
FAILING = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)


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


def drive(keep: bool) -> int:
    repo = pathlib.Path(__file__).resolve().parents[2]
    tree = pathlib.Path(tempfile.mkdtemp(prefix="round2-sim-"))
    try:
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=repo, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
        shutil.copyfile(__file__, tree / "tests" / "benchmarks" / "round2_simulation.py")
        _git(tree, "init", "-q"); _git(tree, "add", "-A"); _git(tree, "commit", "-q", "-m", "H (archive of HEAD)")
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        print(f"simulation tree: {tree} (git archive {head})")
        code, ran, ids, _ = _suite(tree)
        print(f"[H] {'PASS' if code == 0 else 'FAIL'}  Ran {ran} tests" + "".join(f"\n      {i}" for i in ids))
        all_ok = code == 0
        for step in STEPS:
            r = subprocess.run([sys.executable, "tests/benchmarks/round2_simulation.py", "--apply", step], cwd=tree,
                               env=_env(), capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[{step}] APPLY FAILED\n{r.stdout}{r.stderr}"); return 1
            _git(tree, "add", "-A"); _git(tree, "commit", "-q", "-m", f"simulated {step}")
            code, ran, ids, _ = _suite(tree)
            all_ok &= code == 0
            print(f"[{step}] {'PASS' if code == 0 else 'FAIL'}  Ran {ran} tests  ({r.stdout.strip()})"
                  + "".join(f"\n      {i}" for i in ids))
            if step == "B":
                d = subprocess.run([sys.executable, "tests/tune_search_ranking.py", "--cache-dir", str(tree / SIM_DIR / "cache"),
                                    "--dry-run"], cwd=tree, env=_env(), capture_output=True, text=True)
                summary = next((l for l in d.stdout.splitlines() if l.startswith('{"run_id"')), d.stderr.strip()[-300:])
                print(f"    extra: tuning CLI --dry-run on the fixture snapshot exit {d.returncode} "
                      f"(1 = tuning_failed expected: r1 seeds have no fixture answers) {summary}")
        print("ALL STEPS PASS" if all_ok else "SOME STEPS FAILED")
        return 0 if all_ok else 1
    finally:
        if keep:
            print(f"kept {tree}")
        else:
            shutil.rmtree(tree, ignore_errors=True)


# ------------------------------------------------------------------ steps (run inside the temp tree)
ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _write(rel, obj):
    (ROOT / rel).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
                md[s] = {"sha256": storage.sha256_of_spec(spec), "api_version": "v3", "last_checked": "2026-10-02T00:00:00Z",
                         "last_updated": "2026-10-02T00:00:00Z", "resolved_documentation_url": "https://d/"}
            storage.write_metadata(md)
    return cache


def spec_verb_inventory() -> dict:
    text = (ROOT / SPEC_REL).read_text(encoding="utf-8")
    block = re.search(r'```json\n("verb_methods": \{.*?\n\})\n```', text, re.S).group(1)
    return json.loads("{" + block + "}")["verb_methods"]


def apply_T():
    from tests.benchmarks import alias_candidates_tool as act, concept_lexicon_check as clc, round_seal as rs
    from tests.benchmarks.evaluator import canonical_sha256
    cache = _fixture_cache()
    _, internal, fp, shas = rs.load_catalogs_from_cache(cache, 2)
    ranking = _read(f"{DATA_REL}/search_ranking.json")
    ranking["verb_methods"] = spec_verb_inventory()                       # 1. inventory, verbatim
    _write(f"{DATA_REL}/search_ranking.json", ranking)
    aliases = _read(f"{DATA_REL}/search_aliases.json")
    raw, review = {LEXICON_WORD: [LEXICON_TARGET]}, {LEXICON_WORD: True}
    lexicon = {"round": 2, "generated_from": act.provenance(fp, shas, {
                   "verb_inventory": canonical_sha256(ranking["verb_methods"]), "aliases": canonical_sha256(aliases),
                   "raw_generation": canonical_sha256(raw), "semantic_review": canonical_sha256(review)}),
               "raw_sha256": canonical_sha256(raw), "review_output_sha256": canonical_sha256(review),
               "lexicon": {LEXICON_WORD: [LEXICON_TARGET]}, "rejected": {}}
    act._write(ROOT / DATA_REL / "concept_lexicon.json", lexicon)       # 2. synthetic lexicon, merged as lexicon-r2
    merged, skipped = clc.merge(aliases, lexicon["lexicon"], 2)
    assert not skipped
    (ROOT / DATA_REL / "search_aliases.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bench = _read("tests/benchmarks/search_queries.json")
    doc = act.candidates(bench, internal, ranking, merged, 2)           # 3. candidates after the merge
    doc["generated_from"] = act.provenance(fp, shas, {"ranking": canonical_sha256(ranking), "aliases": canonical_sha256(merged),
                                                      "bench": canonical_sha256(bench), "verb_inventory": canonical_sha256(ranking["verb_methods"])})
    act._write(ROOT / DATA_REL / "alias_candidates.json", doc)
    cls = act.classify(bench, internal, ranking, merged)                # 4. R5/R6
    for rec in bench["seed"]:
        rec["failure_classes"] = [c for c in rec["failure_classes"] if c not in ("R5", "R6")] + cls[rec["id"]]
    rs._write_bench(ROOT / "tests" / "benchmarks" / "search_queries.json", bench)
    for name in ("worker-brief", "hidden-generation-prompt", "hidden-reviewer-prompt"):    # 5. synthetic frozen texts
        (ROOT / "tests" / "benchmarks" / f"round2-{name}.md").write_text(f"# synthetic round2 {name}\n", encoding="utf-8")
    with open(os.devnull, "w") as null:                                 # 6. freeze entry (ev.round_freeze_hashes)
        old, sys.stdout = sys.stdout, null
        try:
            code = rs.main(["freeze", "--round", "2", "--cache-dir", str(cache)])
        finally:
            sys.stdout = old
    assert code == 0
    print(f"verb_methods <- spec §6 ({len(ranking['verb_methods'])} verbs, update={ranking['verb_methods']['update']}); "
          f"lexicon-r2 {LEXICON_WORD}->{LEXICON_TARGET}; {len(doc['candidates'])} candidates; "
          f"R6 seeds {sum('R6' in v for v in cls.values())}; round_freeze round 2 added")


def _hidden_records():
    from tests.benchmarks import round_seal as rs
    _, internal, _, _ = rs.load_catalogs_from_cache(_fixture_cache(), 2)
    keys = [op["key"] for op in internal]
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo", "lima",
             "mike", "november", "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey", "xray"]
    held = [{"id": f"h-{i + 1:03d}", "query": f"simulated probe {words[i]} record", "expected_top1_any": [keys[i % len(keys)]],
             "forbidden_top1": [], "origin": "held_out-r2", "failure_classes": [], "ambiguous": False} for i in range(16)]
    neg = [{"id": f"n-{i + 1:03d}", "query": f"simulated decoy {words[16 + i]} record", "expected_top1_any": [],
            "forbidden_top1": [keys[(i * 3) % len(keys)]], "origin": "negative-r2", "failure_classes": [], "ambiguous": False}
           for i in range(8)]
    return {"held_out": held, "negative": neg}


def apply_B():
    from tests.benchmarks import round_seal as rs
    plain = _hidden_records()
    (ROOT / SIM_DIR).mkdir(exist_ok=True)
    (ROOT / SIM_DIR / "round2-plain.json").write_text(json.dumps(plain, indent=2), encoding="utf-8")
    _, _, fp, shas = rs.load_catalogs_from_cache(_fixture_cache(), 2)
    bench = _read("tests/benchmarks/search_queries.json")
    bench["held_out"] = rs.seal_metadata(plain["held_out"], 2, "held_out")
    bench["negative"] = rs.seal_metadata(plain["negative"], 2, "negative")
    bench["round2_seal"] = {"held_out_sha256": bench["held_out"]["sha256"], "negative_sha256": bench["negative"]["sha256"],
                            "held_out_distribution": bench["held_out"]["distribution"],
                            "negative_distribution": bench["negative"]["distribution"],
                            "registry_fingerprint": fp, "spec_sha256": shas, "machine_check": "passed (synthetic)",
                            "origins": rs.section_origin(2)}
    rs._write_bench(ROOT / "tests" / "benchmarks" / "search_queries.json", bench)
    print(f"round2_seal over {len(plain['held_out'])}+{len(plain['negative'])} synthetic records")


def apply_C():
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy
    assert tune.ROUND == 2
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
                trial["aliases"][word] = [target]; trial["notes"][word] = tune.round2_note(word, sid, target, "alias")
                if not tune.validate_alias_change(b_aliases, trial, cands_doc["candidates"], queries, classes) \
                        and not tune.fixture_failures(state, rp, point, fb, tune._alias_policy(trial)):
                    chosen = (word, sid, target, trial); break
            if chosen: break
        if chosen: break
    assert chosen, "no fixture-admissible round2 alias among the frozen candidates"
    word, sid, target, working = chosen
    tune.write_constants(point)
    tune.ALIASES_PATH.write_text(json.dumps(working, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    policy.load_aliases(tune.ALIASES_PATH)
    patch = {**tune.alias_patch(b_aliases, working), "resolved_by_prior_change": [], "not_r6": [], "unresolved": [],
             "fixture_fail": [], "trials": 1}
    fp = cands_doc["generated_from"]["registry_fingerprint"]
    line = {"run_id": str(uuid.uuid4()), "run_at": "2026-10-02T00:00:00Z", "git_commit": "0" * 40, "round": 2,
            "registry_fingerprint": fp, "baseline_sha256": tune.baseline_sha256(b_aliases, b_ranking, fp, cands_doc, bench),
            "events": list(tune.EVENTS), "constants_selected": point, "grid_size": len(tune.grid_points(grid)),
            "fixture_fail": {"constants": [], "final": []}, "passing_combos": 1, "aliases_proposed": patch,
            "seed": f"{tune.SEED_TOTAL}/{tune.SEED_TOTAL}", "regression_negative": f"{tune.REGRESSION_TOTAL}/{tune.REGRESSION_TOTAL}",
            "tuning_failed": False, "result_sha256": tune.result_sha256(point, patch), "dirty": [], "note": "simulated",
            "ranking_structure_sha256": rp.structure_sha256, "baseline": base}
    line["run_log_sha256"] = policy.canonical_sha256(tune.log_core(line))
    line["status"], line["adopted"] = "adopted", True
    tune._write_log([line])
    changed = {k: v for k, v in point.items() if v != base[k]}
    print(f"constants {changed}; round2 alias {word}->{target} ({sid}); adopted log line")


def apply_D():
    from tests.benchmarks import round_seal as rs
    with open(os.devnull, "w") as null:
        old, sys.stdout = sys.stdout, null
        try:
            code = rs.main(["unseal", "--round", "2", "--plain", str(ROOT / SIM_DIR / "round2-plain.json"),
                            "--bench", str(ROOT / "tests" / "benchmarks" / "search_queries.json")])
        finally:
            sys.stdout = old
    assert code == 0
    print("held_out/negative unsealed (synthetic plaintext)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", choices=STEPS)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    if args.apply:
        sys.path.insert(0, str(ROOT))
        {"T": apply_T, "B": apply_B, "C": apply_C, "D": apply_D}[args.apply]()
        return 0
    return drive(args.keep)


if __name__ == "__main__":
    sys.exit(main())
