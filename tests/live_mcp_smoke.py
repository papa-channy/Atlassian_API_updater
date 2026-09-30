"""Manual, network-required, diagnostic smoke: real sync -> RegistryManager -> search -> inspect -> template.
Never run by unittest discover. Never calls Atlassian product APIs.

    python tests/live_mcp_smoke.py
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.atlassian_docs.intelligence import (RegistryManager, build_request_template,  # noqa: E402
                                               get_operation, search_operations)
from tools.atlassian_docs.intelligence.request_check import validation_engine  # noqa: E402


def main() -> int:
    t0 = time.perf_counter()
    mgr = RegistryManager()
    mgr.start()
    mgr.refresh()
    state = mgr.active
    print(f"registry build+index: {time.perf_counter() - t0:.2f}s (benchmark target < 1s, not a gate)")
    failed = False
    for name, p in state.provenance.items():
        print(f"[{p.status.upper():11}] {name}: ops={p.operation_count} schemas={p.schema_count} "
              f"openapi={p.active_openapi_version} api={p.active_api_version} reason={p.reason}")
        if p.status == "unavailable":
            failed = True
    res = search_operations(state, "upload attachment to issue", limit=5)
    print(f"intelligence_fingerprint: {res.get('intelligence_fingerprint')}")
    print(f"validation_engine: {json.dumps(validation_engine())}")
    for r in res.get("results", []):
        print(f"  {r['score']:6.1f} {r['key']}")
    if res.get("results"):
        top = res["results"][0]["key"]
        op = get_operation(state, key=top)
        print(f"top: {op.get('operation_id')} content_types={[m['content_type'] for m in (op.get('request_body') or {}).get('content', [])]}")
        tpl = build_request_template(state, top)
        print(f"template server={tpl.get('server')} missing_required={tpl.get('missing_required')}")
    print("\nFAIL: some source unavailable" if failed else "\nOK: all sources normalized")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
