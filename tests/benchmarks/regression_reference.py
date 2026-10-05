"""AC-R3-02 regression reference (Round 3 spec §3.5).

generate — run with --repo-root pointing at an ISOLATED checkout of the Round 2 reference commit (git worktree add /tmp/r2ref 29dba38):
  that root is put first on sys.path and any imported tools/tests modules are dropped, so the Round 2 scorer, its policy data and
  its fixtures do the scoring. Never generate from the Round 3 working tree.
    python tests/benchmarks/regression_reference.py generate --repo-root /tmp/r2ref \
        --cache-dir ~/.atlassian_api_updater/archive/round2/round2-cache --bench tests/benchmarks/search_queries.json \
        --out tests/benchmarks/round3-regression-reference.json
verify — run in the Round 3 tree: re-score the same queries with the CURRENT scorer under the pinned B policy (B aliases, B inventory,
  B constants + the two Round 3 constants at 0) and compare every ranked key, score and total_matches (limit 50 = search.MAX_LIMIT).
    python tests/benchmarks/regression_reference.py verify [--cache-dir S2] [--reference FILE]
"""
import argparse, hashlib, json, pathlib, shutil, subprocess, sys, tempfile
from unittest import mock

HERE = pathlib.Path(__file__).resolve()
DEFAULT_REF = HERE.parent / "round3-regression-reference.json"
SOURCES = ("jira-platform", "jira-software", "confluence")
LIMIT = 50                      # search.MAX_LIMIT: "the whole ranked list" is everything the API can return (spec §3.5 v1.20)
TOOL_VERSION = "round3.1"
NEW_CONSTANTS = {"method_order_bonus": 0.0, "path_coverage_bonus": 0.0}


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def query_sets(bench) -> tuple:
    """(snapshot queries: seed + regression_negative in file order; fixture queries: their r0 subset)."""
    recs = bench["seed"] + bench["regression_negative"]
    return [r["query"] for r in recs], [r["query"] for r in recs if r["origin"].endswith("-r0")]


def score_all(state, queries, search_operations) -> dict:
    out = {}
    for q in queries:
        res = search_operations(state, q, limit=LIMIT)
        rows = res.get("results", [])
        out[q] = {"keys": [r["key"] for r in rows], "scores": [r["score"] for r in rows], "total_matches": res.get("total_matches", 0)}
    return out


def _state_from_cache(cache_dir):
    """Registry over a temporary copy of the snapshot (the snapshot is never written); returns (state, cleanup)."""
    from tools.atlassian_docs import storage, sync
    from tools.atlassian_docs.intelligence import RegistryManager
    td = tempfile.mkdtemp(prefix="rr-cache-")
    copy = pathlib.Path(td) / "cache"; shutil.copytree(cache_dir, copy)
    patcher = mock.patch.object(storage, "CACHE_DIR", copy); patcher.start()
    mgr = RegistryManager(sync_all=lambda force=False: [sync.SyncResult(s, "ok") for s in SOURCES]); mgr.start()

    def cleanup():
        patcher.stop(); shutil.rmtree(td, ignore_errors=True)
    return mgr.active, cleanup


def _bootstrap(repo_root: pathlib.Path) -> None:
    sys.path.insert(0, str(repo_root))
    for name in [m for m in sys.modules if m.split(".")[0] in ("tools", "tests")]:
        del sys.modules[name]


def generate(repo_root: pathlib.Path, cache_dir: pathlib.Path, bench_path: pathlib.Path) -> dict:
    _bootstrap(repo_root)
    from tools.atlassian_docs.intelligence import search as r2search, policy as r2policy
    from tests.intelligence.helpers import make_state
    bench = json.loads(bench_path.read_text(encoding="utf-8"))
    snap_q, fix_q = query_sets(bench)
    state, cleanup = _state_from_cache(cache_dir)
    try:
        snapshot = score_all(state, snap_q, r2search.search_operations)
        fp, spec_sha = state.registry.fingerprint, {n: p.active_spec_sha256 for n, p in sorted(state.provenance.items())}
    finally:
        cleanup()
    fixture = score_all(make_state(*SOURCES), fix_q, r2search.search_operations)
    data = repo_root / "tools" / "atlassian_docs" / "intelligence" / "data"
    b_ranking = json.loads((data / "search_ranking.json").read_text(encoding="utf-8"))
    b_aliases = json.loads((data / "search_aliases.json").read_text(encoding="utf-8"))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True).stdout.strip()
    return {"tool_version": TOOL_VERSION, "reference_commit": commit, "limit": LIMIT,
            "search_py_sha256": hashlib.sha256((repo_root / "tools/atlassian_docs/intelligence/search.py").read_bytes()).hexdigest(),
            "ranking_sha256": canonical_sha256(b_ranking), "aliases_sha256": canonical_sha256(b_aliases),
            "registry_fingerprint": fp, "spec_sha256": spec_sha, "query_set_sha256": canonical_sha256({"snapshot": snap_q, "fixture": fix_q}),
            "b_ranking": b_ranking, "b_aliases": b_aliases, "snapshot": snapshot, "fixture": fixture}


def _pinned_policies(reference, policy):
    """Round 3 loader + B content: B aliases verbatim; live structure with the B inventory, B constants and the two new constants at 0."""
    live = json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))
    ranking_raw = {**live, "verb_methods": reference["b_ranking"]["verb_methods"],
                   "constants": {**reference["b_ranking"]["constants"], **NEW_CONSTANTS}}
    with tempfile.TemporaryDirectory() as td:
        rp = pathlib.Path(td) / "r.json"; ap = pathlib.Path(td) / "a.json"
        rp.write_text(json.dumps(ranking_raw), encoding="utf-8"); ap.write_text(json.dumps(reference["b_aliases"]), encoding="utf-8")
        return policy.load_ranking(rp), policy.load_aliases(ap)


def _diff(name, want, got) -> list:
    out = []
    for q, row in want.items():
        if got.get(q) != row:
            g = got.get(q) or {}
            first = next((i for i, (a, b) in enumerate(zip(row["keys"], g.get("keys", []))) if a != b), None)
            out.append(f"{name}: {q!r}: first differing rank {first}; scores equal={row['scores'] == g.get('scores')}; total {row['total_matches']} vs {g.get('total_matches')}")
    return out


def verify_reference(reference: dict, cache_dir=None) -> list:
    from tools.atlassian_docs.intelligence import policy, search
    from tests.intelligence.helpers import make_state
    rp, ap = _pinned_policies(reference, policy)
    problems = []
    with mock.patch.object(policy, "ranking", return_value=rp), mock.patch.object(policy, "aliases", return_value=ap):
        problems += _diff("fixture", reference["fixture"], score_all(make_state(*SOURCES), list(reference["fixture"]), search.search_operations))
        if cache_dir is not None:
            state, cleanup = _state_from_cache(pathlib.Path(cache_dir))
            try:
                if state.registry.fingerprint != reference["registry_fingerprint"]:
                    problems.append(f"snapshot fingerprint {state.registry.fingerprint} != reference {reference['registry_fingerprint']}")
                else:
                    problems += _diff("snapshot", reference["snapshot"], score_all(state, list(reference["snapshot"]), search.search_operations))
            finally:
                cleanup()
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--repo-root", required=True, type=pathlib.Path); g.add_argument("--cache-dir", required=True, type=pathlib.Path)
    g.add_argument("--bench", required=True, type=pathlib.Path); g.add_argument("--out", required=True, type=pathlib.Path)
    v = sub.add_parser("verify"); v.add_argument("--cache-dir", type=pathlib.Path, default=None); v.add_argument("--reference", type=pathlib.Path, default=DEFAULT_REF)
    args = ap.parse_args(argv)
    if args.cmd == "generate":
        doc = generate(args.repo_root.resolve(), args.cache_dir.expanduser(), args.bench)
        args.out.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({k: doc[k] for k in ("reference_commit", "registry_fingerprint", "query_set_sha256")})); return 0
    sys.path.insert(0, str(HERE.parents[2]))
    problems = verify_reference(json.loads(args.reference.read_text(encoding="utf-8")), args.cache_dir.expanduser() if args.cache_dir else None)
    print("reference ok" if not problems else "\n".join(f"MISMATCH {p}" for p in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
