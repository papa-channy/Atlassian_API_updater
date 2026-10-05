"""Manual, offline diagnostic: evaluate the benchmark sets against a cache snapshot (Round 1 spec §9; Round 2 adds
--round, held_out_top3, and the candidates/lexicon data hashes).

    python tests/diag_search_queries.py [--sets seed,regression_negative] [--cache-dir DIR]
                                        [--bench PLAINTEXT] [--bench-file BENCH] [--json OUT] [--round N]

--cache-dir   cache snapshot (default: storage.CACHE_DIR); a temporary copy is used, the snapshot is never written.
--bench       plaintext hidden sets {"held_out": [...], "negative": [...]} for round N; replaces the sealed sections.
              Every record's origin must be "held_out-r{N}" / "negative-r{N}" or the run is refused (exit 2).
--bench-file  benchmark metadata file (default tests/benchmarks/search_queries.json; read-only).
--sets        comma list; default every set that is not sealed.
--round       which round's seal to compare against (default: the current round from round_freeze.json).
On start the loaded registry fingerprint and per-source spec sha256 are compared with `round{N}_seal`: a mismatch
only warns, unless --bench is given or a hidden set (held_out/negative) is requested; then nothing is evaluated and the exit code is 2.
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


def _data_sha(filename):
    """Canonical sha256 of a Round 2 data file under policy.DATA_DIR, or None before it exists."""
    path = policy.DATA_DIR / filename
    if not path.exists():
        return None
    return ev.canonical_sha256(json.loads(path.read_text(encoding="utf-8")))


class _WrongRoundOrigin(Exception):
    pass


def _parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sets", default=None)
    ap.add_argument("--bench", type=pathlib.Path, default=None)
    ap.add_argument("--bench-file", type=pathlib.Path, default=BENCH)
    ap.add_argument("--cache-dir", type=pathlib.Path, default=None)
    ap.add_argument("--json", type=pathlib.Path, default=None)
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--reference", type=pathlib.Path, default=None)
    ap.add_argument("--reference-round", type=int, default=None)
    ap.add_argument("--append-to", type=pathlib.Path, default=None)
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


def _sections(bench, plain, rnd):
    sections = {name: bench[name] for name in ALL_SETS}
    if plain is not None:
        for name in HIDDEN_SETS:
            ev.check_schema(name, plain[name])
            for rec in plain[name]:
                want = f"{name}-r{rnd}"
                if rec.get("origin") != want:
                    raise _WrongRoundOrigin(f"{name}/{rec.get('id')}: origin {rec.get('origin')!r} != {want!r}")
            sections[name] = plain[name]
    return sections


def run(argv=None):
    """Returns (exit_code, report). Writes --json when given; never edits the benchmark file."""
    args = _parse(argv)
    bench = json.loads(args.bench_file.read_text(encoding="utf-8"))
    plain = json.loads(args.bench.expanduser().read_text(encoding="utf-8")) if args.bench else None
    rnd = args.round if args.round is not None else ev.current_round()["round"]
    try:
        sections = _sections(bench, plain, rnd)
    except _WrongRoundOrigin as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2, {"error": "wrong_round_origin", "sets": {}}
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
            state = build_state()
            if args.reference:
                code, report = _append_reference(state, args, bench)
            else:
                code, report = _evaluate(state, bench, sections, sets, plain, rnd)
    if args.json and code == 0 and not args.reference:          # no artifact from a refused run
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return code, report


def _hide_queries(res):
    """Round 3 spec §4 v1.22: hidden/reference failure records never carry a `query` key; they carry `query_sha256`
    instead (diagnostic fields without the text are allowed). Sealed-section stubs pass through unchanged."""
    if res.get("sealed"):
        return res
    out = dict(res)
    out["failed"] = [{**{k: v for k, v in f.items() if k != "query"}, "query_sha256": ev.canonical_sha256(f["query"])}
                     for f in res.get("failed", [])]
    return out


def _append_reference(state, args, bench):
    art_path = args.append_to; art = json.loads(art_path.read_text(encoding="utf-8"))
    key = f"reference_round{args.reference_round}"
    if art.get("git_commit") != _git("rev-parse", "HEAD") or art.get("registry_fingerprint") != state.registry.fingerprint or key in art:
        print(f"error: {art_path} is not the current artifact or already has {key}", file=sys.stderr); return 2, art
    plain = json.loads(args.reference.expanduser().read_text(encoding="utf-8"))
    for name in HIDDEN_SETS:
        ev.check_schema(name, plain[name])
        for rec in plain[name]:
            if rec.get("origin") != f"{name}-r{args.reference_round}":
                print(f"error: {name}/{rec.get('id')}: origin {rec.get('origin')!r} != {name}-r{args.reference_round}", file=sys.stderr); return 2, art
    keys = {op.key for sr in state.registry.sources.values() for op in sr.operations}
    fn = lambda q: (lambda out: ([r["key"] for r in out.get("results", [])], out["actionable"]))(search_operations(state, q, limit=5))
    block, invalid = {}, []
    for name in HIDDEN_SETS:
        valid = []
        for rec in plain[name]:
            bad = [k for k in rec["expected_top1_any"] + rec["forbidden_top1"] if k not in keys]
            (invalid.append({"id": rec["id"], "keys": bad}) if bad else valid.append(rec))
        block[name] = _hide_queries(ev.evaluate(valid, fn, section=name))
    block["invalid_key"] = invalid
    block["plaintext_sha256"] = {n: ev.canonical_sha256(plain[n]) for n in HIDDEN_SETS}
    block["enc_sha256"] = (ev.current_round().get("reference_set") or {}).get("enc_sha256")
    art[key] = block
    art_path.write_text(json.dumps(art, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0, art


def _evaluate(state, bench, sections, sets, plain, rnd):
    seal = bench.get(f"round{rnd}_seal") or {}
    fp = state.registry.fingerprint
    spec_sha = {n: p.active_spec_sha256 for n, p in state.provenance.items()}
    rp, al = policy.ranking(), policy.aliases()
    report = {"run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "git_commit": _git("rev-parse", "HEAD"),
              "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
              "round": rnd,
              "registry_fingerprint": fp,
              "intelligence_fingerprint": policy.intelligence_fingerprint(fp, al.sha256, policy.overrides().sha256),
              "ranking_sha256": rp.sha256, "ranking_structure_sha256": rp.structure_sha256, "alias_sha256": al.sha256,
              "alias_candidates_sha256": _data_sha("alias_candidates.json"),
              "concept_lexicon_sha256": _data_sha("concept_lexicon.json"),
              "evaluation_code_sha256": ev.evaluation_code_sha256(ROOT), "spec_sha256": spec_sha,
              "evaluation_domain": "actionable recommendation queries",
              "policy_version": policy.POLICY_VERSIONS["search"],
              "tuning_grid_sha256": ev.tuning_grid_sha256(json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))),
              "seal_match": fp == seal.get("registry_fingerprint") and spec_sha == seal.get("spec_sha256"),
              "held_out_top3": None, "negative_actionable": None, "negative_abstained": None,
              "sets": {}, "failures": []}
    if not report["seal_match"]:
        print(f"WARNING: snapshot differs from round{rnd}_seal (registry {fp} vs {seal.get('registry_fingerprint')}; "
              f"spec {spec_sha} vs {seal.get('spec_sha256')})", file=sys.stderr)
        if plain is not None or any(n in HIDDEN_SETS for n in sets):
            print(f"error: hidden sets requested on a snapshot that does not match round{rnd}_seal; nothing evaluated",
                  file=sys.stderr)
            return 2, report
    if plain is not None:
        report["sealed_sha256"] = {n: ev.canonical_sha256(sections[n]) for n in HIDDEN_SETS}
        want = {n: seal.get(f"{n}_sha256") for n in HIDDEN_SETS}
        if report["sealed_sha256"] != want:
            print(f"WARNING: plaintext sha256 {report['sealed_sha256']} != round{rnd}_seal {want}", file=sys.stderr)
    ranked = {}

    def fn(q):
        out = search_operations(state, q, limit=5)
        keys = [r["key"] for r in out.get("results", [])]
        ranked[q] = keys
        return keys, out["actionable"]

    for name in sets:
        res = ev.evaluate(sections[name], fn, section=name)
        hidden = name in HIDDEN_SETS
        report["sets"][name] = _hide_queries(res) if hidden else res
        if res.get("sealed"):
            print(f"[{name:19}] sealed ({res['count']} records)")
            continue
        if name in ev.NEGATIVE_SECTIONS:
            print(f"[{name:19}] effective {res['effective_passed']}/{res['total']} (raw {res['raw_passed']}/{res['total']})")
        else:
            print(f"[{name:19}] {res['passed']}/{res['total']}")
        if name == "held_out":
            records = sections[name]
            passed3 = sum(1 for rec in records
                          if any(k in ranked.get(rec["query"], [])[:3] for k in (rec.get("expected_top1_any") or [])))
            report["held_out_top3"] = {"passed": passed3, "total": len(records)}
        if name == "negative":
            report["negative_actionable"], report["negative_abstained"] = res["actionable"], res["abstained"]
        for f in res["failed"]:
            entry = {"set": name, **f, "top5": top5(state, f["query"])}
            if hidden:
                query = entry.pop("query")
                entry["query_sha256"] = ev.canonical_sha256(query)
                for r in entry["top5"]:                        # the verb token echoes a hidden-query word; value/preferred stay
                    mo = (r.get("signals") or {}).get("method_order")
                    if isinstance(mo, dict) and "verb" in mo:
                        mo.pop("verb")
                print(f"    FAIL {f['id']} <hidden>")
            else:
                print(f"    FAIL {f['id']} {f['query']!r}: top1={f['top1']}")
            report["failures"].append(entry)
            for r in entry["top5"]:
                print(f"        {r['score']:8.3f}  {r['key']}  {json.dumps(r['signals'], sort_keys=True)}")
    return 0, report


def main(argv=None) -> int:
    code, report = run(argv)
    print(json.dumps({k: report.get(k) for k in ("run_at", "git_commit", "registry_fingerprint", "seal_match",
                                                 "intelligence_fingerprint", "evaluation_code_sha256")}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
