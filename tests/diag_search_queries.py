"""Manual, offline diagnostic: evaluate the benchmark sets against a cache snapshot (Round 1 spec §9).

    python tests/diag_search_queries.py [--sets seed,regression_negative] [--cache-dir DIR]
                                        [--bench PLAINTEXT] [--bench-file BENCH] [--json OUT]

--cache-dir   cache snapshot (default: storage.CACHE_DIR); a temporary copy is used, the snapshot is never written.
--bench       plaintext hidden sets {"held_out": [...], "negative": [...]} (commit D); replaces the sealed sections.
--bench-file  benchmark metadata file (default tests/benchmarks/search_queries.json; read-only).
--sets        comma list; default every set that is not sealed.
On start the loaded registry fingerprint and per-source spec sha256 are compared with `round1_seal`: a mismatch
only warns, unless a hidden set (held_out/negative) is requested, then nothing is evaluated and the exit code is 2.
Exit 0 otherwise (the numbers are for docs/phase3-readiness.md). The benchmark file is never edited.
"""
import argparse
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.benchmarks import evaluator as ev  # noqa: E402
from tools.atlassian_docs import storage, sync  # noqa: E402
from tools.atlassian_docs.intelligence import RegistryManager, policy, search_operations  # noqa: E402

BENCH = ROOT / "tests" / "benchmarks" / "search_queries.json"
SOURCES = ("jira-platform", "jira-software", "confluence")
ALL_SETS = ("seed", "regression_negative", "held_out", "negative")
HIDDEN_SETS = ("held_out", "negative")


def _parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sets", default=None)
    ap.add_argument("--bench", type=pathlib.Path, default=None)
    ap.add_argument("--bench-file", type=pathlib.Path, default=BENCH)
    ap.add_argument("--cache-dir", type=pathlib.Path, default=None)
    ap.add_argument("--json", type=pathlib.Path, default=None)
    return ap.parse_args(argv)


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_state():
    """Registry from storage.CACHE_DIR (the caller patches it); sync is a no-op, the network is never used."""
    mgr = RegistryManager(sync_all=lambda force=False: [sync.SyncResult(s, "ok") for s in SOURCES])
    mgr.start()
    return mgr.active


def top5(state, query):
    return [{"key": r["key"], "score": r["score"], "signals": r.get("signals")}
            for r in search_operations(state, query, limit=5).get("results", [])]


def _sections(bench, plain):
    sections = {name: bench[name] for name in ALL_SETS}
    if plain is not None:
        for name in HIDDEN_SETS:
            ev.check_schema(name, plain[name])
            sections[name] = plain[name]
    return sections


def run(argv=None):
    """Returns (exit_code, report). Writes --json when given; never edits the benchmark file."""
    args = _parse(argv)
    bench = json.loads(args.bench_file.read_text(encoding="utf-8"))
    plain = json.loads(args.bench.expanduser().read_text(encoding="utf-8")) if args.bench else None
    sections = _sections(bench, plain)
    sets = args.sets.split(",") if args.sets else [n for n in ALL_SETS if not ev.is_sealed(sections[n])]
    unknown = [n for n in sets if n not in ALL_SETS]
    if unknown:
        print(f"error: unknown set(s) {unknown}; choose from {list(ALL_SETS)}", file=sys.stderr)
        return 2, {"error": "unknown_sets", "sets": {}}
    cache = (args.cache_dir or storage.CACHE_DIR).expanduser()
    if not all((cache / f"{s}.json").is_file() for s in SOURCES):
        print(f"error: {cache} is not a cache snapshot (missing <source>.json)", file=sys.stderr)
        return 2, {"error": "no_cache", "sets": {}}
    with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ):
        os.environ.pop("ATLASSIAN_DOCS_SEARCH_LOG", None)      # diagnostic queries are not user queries
        copy = pathlib.Path(td) / "cache"
        shutil.copytree(cache, copy)                            # the snapshot itself is never written
        with mock.patch.object(storage, "CACHE_DIR", copy):
            code, report = _evaluate(build_state(), bench, sections, sets, plain)
    if args.json and code == 0:                                # no artifact from a refused run
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return code, report


def _evaluate(state, bench, sections, sets, plain):
    seal = bench.get("round1_seal") or {}
    fp = state.registry.fingerprint
    spec_sha = {n: p.active_spec_sha256 for n, p in state.provenance.items()}
    rp, al = policy.ranking(), policy.aliases()
    report = {"run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "git_commit": _git("rev-parse", "HEAD"),
              "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
              "registry_fingerprint": fp,
              "intelligence_fingerprint": policy.intelligence_fingerprint(fp, al.sha256, policy.overrides().sha256),
              "ranking_sha256": rp.sha256, "ranking_structure_sha256": rp.structure_sha256, "alias_sha256": al.sha256,
              "evaluation_code_sha256": ev.evaluation_code_sha256(ROOT), "spec_sha256": spec_sha,
              "seal_match": fp == seal.get("registry_fingerprint") and spec_sha == seal.get("spec_sha256"),
              "sets": {}, "failures": []}
    if not report["seal_match"]:
        print(f"WARNING: snapshot differs from round1_seal (registry {fp} vs {seal.get('registry_fingerprint')}; "
              f"spec {spec_sha} vs {seal.get('spec_sha256')})", file=sys.stderr)
        if any(n in HIDDEN_SETS for n in sets):
            print("error: hidden sets requested on a snapshot that does not match round1_seal; nothing evaluated",
                  file=sys.stderr)
            return 2, report
    if plain is not None:
        report["sealed_sha256"] = {n: ev.canonical_sha256(sections[n]) for n in HIDDEN_SETS}
        want = {n: seal.get(f"{n}_sha256") for n in HIDDEN_SETS}
        if report["sealed_sha256"] != want:
            print(f"WARNING: plaintext sha256 {report['sealed_sha256']} != round1_seal {want}", file=sys.stderr)
    fn = lambda q: [r["key"] for r in search_operations(state, q, limit=5).get("results", [])]
    for name in sets:
        res = ev.evaluate(sections[name], fn)
        report["sets"][name] = res
        if res.get("sealed"):
            print(f"[{name:19}] sealed ({res['count']} records)")
            continue
        print(f"[{name:19}] {res['passed']}/{res['total']}")
        for f in res["failed"]:
            report["failures"].append({"set": name, **f, "top5": top5(state, f["query"])})
            print(f"    FAIL {f['id']} {f['query']!r}: top1={f['top1']}")
            for r in report["failures"][-1]["top5"]:
                print(f"        {r['score']:8.3f}  {r['key']}  {json.dumps(r['signals'], sort_keys=True)}")
    return 0, report


def main(argv=None) -> int:
    code, report = run(argv)
    print(json.dumps({k: report.get(k) for k in ("run_at", "git_commit", "registry_fingerprint", "seal_match",
                                                 "intelligence_fingerprint", "evaluation_code_sha256")}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
