"""Manual, offline diagnostic: evaluate the frozen benchmark sets against the REAL cache (spec §7).

    python tests/diag_search_queries.py [--json out.json]

Never edits the benchmark file. Exit code is always 0; the numbers are for docs/phase3-readiness.md.
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tests.benchmarks.evaluator import evaluate  # noqa: E402
from tools.atlassian_docs import sync  # noqa: E402
from tools.atlassian_docs.intelligence import RegistryManager, search_operations  # noqa: E402
from tools.atlassian_docs.intelligence import policy  # noqa: E402

BENCH = pathlib.Path(__file__).resolve().parent / "benchmarks" / "search_queries.json"


def main() -> int:
    mgr = RegistryManager(sync_all=lambda force=False: [sync.SyncResult(s, "ok") for s in ("jira-platform", "jira-software", "confluence")])
    mgr.start(); state = mgr.active
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    fn = lambda q: [r["key"] for r in search_operations(state, q, limit=5).get("results", [])]
    report = {"run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "registry_fingerprint": state.registry.fingerprint,
              "intelligence_fingerprint": policy.intelligence_fingerprint(state.registry.fingerprint, policy.aliases().sha256, policy.overrides().sha256),
              "spec_sha256": {n: p.active_spec_sha256 for n, p in state.provenance.items()}, "sets": {}}
    for name in ("seed", "regression_negative", "held_out", "negative"):
        res = evaluate(bench[name], fn)
        report["sets"][name] = res
        if res.get("sealed"):
            print(f"[{name:9}] sealed ({res['count']} records)")
            continue
        print(f"[{name:9}] {res['passed']}/{res['total']}")
        for f in res["failed"]:
            print(f"    FAIL {f['query']!r}: top1={f['top1']} expected={f['expected_top1_any']} forbidden={f['forbidden_top1']}")
    if "--json" in sys.argv:
        pathlib.Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("run_at", "registry_fingerprint", "intelligence_fingerprint")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
