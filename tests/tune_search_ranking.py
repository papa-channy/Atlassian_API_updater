"""Grid-exhaustive, deterministic tuning of the five search ranking constants (Round 1 spec §8.2/§8.3).

    python tests/tune_search_ranking.py --cache-dir DIR [--dry-run] [--note TEXT] [--alias-change JSON]

Builds the registry once from a copy of the frozen snapshot DIR, evaluates every tuning_grid point on the
`seed` and `regression_negative` sets (constants injected by patching policy.ranking with a RankingPolicy copy),
selects one point with select_candidate (baseline = the frozen `baseline`, never the current constants),
writes ONLY `constants` into search_ranking.json and appends one line to the tuning log (neither with --dry-run).
A fallback (non-perfect) selection is logged with adopted:false and never written (controller ruling).
--dry-run has no side effects: nothing is written; the would-be log line is printed.
Exit 0 when the selected point passes every seed and regression_negative record, 1 otherwise, 2 on setup errors.
"""
import argparse
import dataclasses
import datetime
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from types import MappingProxyType
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.benchmarks.evaluator import evaluate  # noqa: E402
from tools.atlassian_docs import storage, sync  # noqa: E402
from tools.atlassian_docs.intelligence import RegistryManager, policy, search_operations  # noqa: E402

BENCH_PATH = ROOT / "tests" / "benchmarks" / "search_queries.json"
LOG_PATH = ROOT / "tests" / "benchmarks" / "search-tuning-round1.jsonl"
RANKING_PATH = policy.DATA_DIR / "search_ranking.json"
ALIASES_PATH = policy.DATA_DIR / "search_aliases.json"
ALIASES_REL = "tools/atlassian_docs/intelligence/data/search_aliases.json"
CONSTANT_KEYS = policy.CONSTANT_KEYS
MAGNITUDE_KEYS = tuple(k for k in CONSTANT_KEYS if k != "path_unmatched_cap")   # every bonus/penalty (spec §8.2 (3))
_BENCH = json.loads(BENCH_PATH.read_text(encoding="utf-8"))
SEED_TOTAL, REGRESSION_TOTAL = len(_BENCH["seed"]), len(_BENCH["regression_negative"])
SOURCES = ("jira-platform", "jira-software", "confluence")


# ---- pure helpers (unit-tested in tests/test_tune_search_ranking.py) ----

def grid_points(grid) -> list:
    """Cartesian product of the grid in CONSTANT_KEYS order; ascending values -> lexicographic order."""
    axes = [sorted(grid[k]) for k in CONSTANT_KEYS]
    return [dict(zip(CONSTANT_KEYS, combo)) for combo in itertools.product(*axes)]


def l1_index_distance(point, baseline, grid) -> int:
    return sum(abs(list(grid[k]).index(point[k]) - list(grid[k]).index(baseline[k])) for k in CONSTANT_KEYS)


def select_candidate(results, baseline, grid, seed_total=SEED_TOTAL, regression_total=REGRESSION_TOTAL) -> dict:
    """spec §8.2: (1) perfect points only, else max seed then max regression; (2) min L1 grid-index distance to
    baseline; (3) min magnitude sum; (4) lexicographic 6-tuple."""
    if not results:
        raise ValueError("no results to select from")
    pool = [p for p, s, r in results if s == seed_total and r == regression_total]
    if not pool:
        best = max((s, r) for _, s, r in results)
        pool = [p for p, s, r in results if (s, r) == best]
    return dict(min(pool, key=lambda p: (l1_index_distance(p, baseline, grid), sum(p[k] for k in MAGNITUDE_KEYS),
                                          tuple(p[k] for k in CONSTANT_KEYS))))


def plan_effects(dry_run: bool, perfect: bool) -> dict:
    """--dry-run has no side effects; a normal run always logs, but writes constants only for a perfect pick."""
    return {"write_constants": perfect and not dry_run, "append_log": not dry_run}


LOG_REL = "tests/benchmarks/search-tuning-round1.jsonl"


def dirty_paths(porcelain: str) -> list:
    """Tracked paths with uncommitted changes (git status --porcelain), excluding untracked files and the log."""
    out = set()
    for row in porcelain.splitlines():
        if len(row) < 4 or row.startswith("??"):
            continue
        path = row[3:].split(" -> ")[-1].strip().strip('"')
        if path != LOG_REL:
            out.add(path)
    return sorted(out)


# ---- evaluation against the snapshot ----

def _search_fn(state):
    return lambda q: [r["key"] for r in search_operations(state, q, limit=5).get("results", [])]


def ranking_with(rp, point):
    return dataclasses.replace(rp, constants=MappingProxyType(dict(point)),
                               sha256=policy.canonical_sha256({"tuning_point": dict(point)}))


def evaluate_point(state, rp, point, bench, alias_policy):
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), \
            mock.patch.object(policy, "aliases", return_value=alias_policy):
        fn = _search_fn(state)
        return evaluate(bench["seed"], fn), evaluate(bench["regression_negative"], fn)


def top5(state, rp, point, query, alias_policy):
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), \
            mock.patch.object(policy, "aliases", return_value=alias_policy):
        return [(r["key"], r["score"], r.get("signals")) for r in search_operations(state, query, limit=5).get("results", [])]


def write_constants(point, path=RANKING_PATH) -> None:
    """Rewrite ONLY the `constants` object; verify the frozen structure hash is unchanged, else restore."""
    original = path.read_text(encoding="utf-8")
    before = policy.load_ranking(path)
    rows = (CONSTANT_KEYS[:2], CONSTANT_KEYS[2:5], CONSTANT_KEYS[5:])          # the frozen file's layout
    body = ",\n    ".join(", ".join(f'"{k}": {json.dumps(point[k])}' for k in row) for row in rows if row)
    text, n = re.subn(r'"constants": \{[^}]*\}', lambda _m: '"constants": {\n    ' + body + "\n  }", original)
    if n != 1:
        raise SystemExit("could not locate a single 'constants' object in search_ranking.json")
    path.write_text(text, encoding="utf-8")
    after = policy.load_ranking(path)
    if after.structure_sha256 != before.structure_sha256 or dict(after.constants) != dict(point):
        path.write_text(original, encoding="utf-8")
        raise SystemExit("constants rewrite changed the frozen structure; restored the original file")


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def head_alias_policy():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "search_aliases.json"
        p.write_text(_git("show", f"HEAD:{ALIASES_REL}"), encoding="utf-8")
        return policy.load_aliases(p)


def build_state(cache_copy: pathlib.Path):
    """Same construction as tests/diag_search_queries.py; caller patches storage.CACHE_DIR to cache_copy."""
    mgr = RegistryManager(sync_all=lambda force=False: [sync.SyncResult(s, "ok") for s in SOURCES])
    mgr.start()
    return mgr.active


def _parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", required=True, type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--note", default="")
    ap.add_argument("--alias-change", type=json.loads, default=None,
                    help='{"seed_query_id": "s-015", "policy_key": "jql"}')
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    cache = args.cache_dir.expanduser()
    if not all((cache / f"{s}.json").is_file() for s in SOURCES):
        print(f"error: {cache} is not a cache snapshot (missing <source>.json)", file=sys.stderr)
        return 2
    os.environ.pop("ATLASSIAN_DOCS_SEARCH_LOG", None)          # never log thousands of tuning queries
    bench, rp, aliases = _BENCH, policy.load_ranking(RANKING_PATH), policy.load_aliases(ALIASES_PATH)
    grid, baseline = rp.tuning_grid, dict(rp.baseline)
    with tempfile.TemporaryDirectory() as td:
        copy = pathlib.Path(td) / "cache"
        shutil.copytree(cache, copy)                             # the snapshot itself is never written
        with mock.patch.object(storage, "CACHE_DIR", copy):
            state = build_state(copy)
            fp = state.registry.fingerprint
            if fp != bench["round1_seal"]["registry_fingerprint"]:
                print(f"error: registry fingerprint {fp} != round1_seal.registry_fingerprint "
                      f"{bench['round1_seal']['registry_fingerprint']}; wrong snapshot?", file=sys.stderr)
                return 2
            results = []
            for point in grid_points(grid):
                seed_res, reg_res = evaluate_point(state, rp, point, bench, aliases)
                results.append((point, seed_res["passed"], reg_res["passed"]))
            selected = select_candidate(results, baseline, grid)
            seed_res, reg_res = evaluate_point(state, rp, selected, bench, aliases)
            change = _alias_change(args.alias_change, state, rp, selected, bench, aliases)
            for f in seed_res["failed"] + reg_res["failed"]:
                print(f"  FAIL {f['id']} {f['query']!r}")
                for key, score, sig in top5(state, rp, selected, f["query"], aliases):
                    print(f"      {score:8.3f}  {key}  {json.dumps(sig, sort_keys=True)}")
    return _finish(args, rp, aliases, fp, results, selected, seed_res, reg_res, change)


def _alias_change(spec, state, rp, selected, bench, aliases):
    """before_pass: alias file as committed at HEAD; after_pass: working tree; both at the selected constants."""
    if spec is None:
        return None
    if set(spec) != {"seed_query_id", "policy_key"}:
        raise SystemExit("--alias-change needs exactly seed_query_id and policy_key")
    recs = [r for r in bench["seed"] if r["id"] == spec["seed_query_id"]]
    if len(recs) != 1:
        raise SystemExit(f"unknown seed query {spec['seed_query_id']!r}")
    one = {"seed": recs, "regression_negative": []}
    before = evaluate_point(state, rp, selected, one, head_alias_policy())[0]["passed"] == 1
    after = evaluate_point(state, rp, selected, one, aliases)[0]["passed"] == 1
    return {"seed_query_id": spec["seed_query_id"], "policy_key": spec["policy_key"],
            "before_pass": before, "after_pass": after}


def _append_log(line: dict) -> None:
    """Append one line; an adopting run supersedes the previous adopted line (exactly one adopted, spec §8.3)."""
    old = [json.loads(x) for x in LOG_PATH.read_text(encoding="utf-8").splitlines() if x.strip()] if LOG_PATH.exists() else []
    if line["adopted"]:
        for prev in old:
            if prev.get("adopted"):
                prev["adopted"], prev["superseded_by"] = False, line["run_at"]
    out = [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in old + [line]]
    LOG_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def _finish(args, rp, aliases, fp, results, selected, seed_res, reg_res, change) -> int:
    perfect = seed_res["passed"] == SEED_TOTAL and reg_res["passed"] == REGRESSION_TOTAL
    note = args.note
    if change:
        fmt = lambda ok: "pass" if ok else "fail"
        note = (note + "; " if note else "") + (f"alias:{change['policy_key']} for {change['seed_query_id']} "
                                                f"(before: {fmt(change['before_pass'])}, after: {fmt(change['after_pass'])})")
    line = {"run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": _git("rev-parse", "HEAD").strip(), "registry_fingerprint": fp,
            "alias_sha256": aliases.sha256, "ranking_structure_sha256": rp.structure_sha256,
            "grid_size": len(results), "baseline": dict(rp.baseline), "selected": selected,
            "passing_combos": sum(1 for _, s, r in results if s == SEED_TOTAL and r == REGRESSION_TOTAL),
            "seed": f"{seed_res['passed']}/{SEED_TOTAL}", "regression_negative": f"{reg_res['passed']}/{REGRESSION_TOTAL}",
            "seed_shortfall": not perfect, "note": note,
            "bench_sha256": policy.canonical_sha256(_BENCH),
            "dirty": dirty_paths(_git("status", "--porcelain", "--untracked-files=no"))}
    if change:
        line["alias_change"] = change
    effects = plan_effects(args.dry_run, perfect)
    line["adopted"] = effects["write_constants"]   # a non-perfect (fallback) selection is never adopted
    if effects["write_constants"]:
        write_constants(selected)
    if effects["append_log"]:
        _append_log(line)
    else:
        print("dry run: nothing written; would-be log line:")
        print(json.dumps(line, ensure_ascii=False, sort_keys=True))
    print(json.dumps({k: line[k] for k in ("selected", "seed", "regression_negative", "passing_combos", "grid_size",
                                           "adopted", "note")}, ensure_ascii=False))
    return 0 if perfect else 1


if __name__ == "__main__":
    sys.exit(main())
