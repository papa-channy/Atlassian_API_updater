"""SDK-independent tool handlers. server.py binds these to the MCP SDK (spec §17)."""
import json
import sys
from typing import Any

from ..intelligence import inspect as insp
from ..intelligence import policy, provenance, quirks, request_check, request_template, search, search_log

MAX_RESULT_BYTES = 200 * 1024
TOOL_NAMES = ("search_operations", "get_operation", "get_schema", "build_request_template",
              "check_request", "get_api_status", "refresh_api_docs")
_FRESHNESS_TOOLS = TOOL_NAMES[:5]


def payload_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def guard_size(payload: dict) -> dict:
    if payload_size(payload) > MAX_RESULT_BYTES:
        return provenance.error_response("result_too_large",
                                         "result exceeds 200 KiB; reduce limit / max_depth / max_nodes / resolve_schema_depth")
    return payload


def get_api_status(manager) -> dict:
    state = manager.active
    al_sha, ov_sha = policy.aliases().sha256, policy.overrides().sha256
    return {
        "registry_fingerprint": state.registry.fingerprint, "built_at": state.registry.built_at,
        "intelligence_fingerprint": policy.intelligence_fingerprint(state.registry.fingerprint, al_sha, ov_sha),
        "intelligence_policy": policy.policy_block(al_sha, ov_sha),
        "sources": {name: p.to_dict() for name, p in state.provenance.items()},
        "refresh": {**state.refresh.to_dict(), "backoff_active": manager.backoff_active,
                    "in_progress": manager.refresh_in_progress, "search_log_enabled": search_log.enabled()},
        "capabilities": {"validation": request_check.validation_engine()},
        "diagnostics": {"orphaned_override_keys": list(quirks.orphaned_override_keys(state.registry)),
                        "header_candidates": list(quirks.header_candidates(state.registry))},
        "execution": "disabled",
    }


def _dispatch(manager, name: str, args: dict) -> dict:
    if name == "get_api_status":
        return get_api_status(manager)
    if name == "refresh_api_docs":
        return manager.refresh()
    if name not in _FRESHNESS_TOOLS:
        return provenance.error_response("invalid_argument", f"unknown tool {name!r}")
    manager.ensure_fresh()
    state = manager.active
    if name == "search_operations":
        return search.search_operations(state, args.get("query", ""), source=args.get("source"), method=args.get("method"),
                                        tag=args.get("tag"), include_deprecated=args.get("include_deprecated", True),
                                        limit=args.get("limit", 10))
    if name == "get_operation":
        return insp.get_operation(state, key=args.get("key"), source=args.get("source"), operation_id=args.get("operation_id"),
                                  include_full_description=args.get("include_full_description", False),
                                  include_response_schemas=args.get("include_response_schemas", False),
                                  resolve_schema_depth=args.get("resolve_schema_depth", 0))
    if name == "get_schema":
        return insp.get_schema(state, args.get("source", ""), args.get("name", ""),
                               max_depth=args.get("max_depth", 2), max_nodes=args.get("max_nodes", 200))
    if name == "build_request_template":
        return request_template.build_request_template(state, args.get("key", ""), args.get("values"))
    # check_request
    bp = args.get("body_present")  # spec §12: False -> no body; True -> body (None = JSON null); None -> key presence
    if bp is False:
        body, ignored = request_check.MISSING, args.get("body") is not None
    elif bp is True:
        body, ignored = args.get("body"), False
    else:
        body, ignored = (args["body"] if "body" in args else request_check.MISSING), False
    out = request_check.check_request(state, args.get("key", ""), path_params=args.get("path_params"),
                                      query=args.get("query"), headers=args.get("headers"), body=body,
                                      content_type=args.get("content_type"))
    if ignored and "warnings" in out:
        out["warnings"].append({"location": "body", "rule": "body_ignored",
                                "message": "body_present=false: supplied body was ignored"})
    return out


def run_tool(manager, name: str, arguments: dict) -> dict:
    try:
        return guard_size(_dispatch(manager, name, arguments or {}))
    except Exception as exc:  # noqa: BLE001 - the server process must never die on a tool error
        print(f"[internal_error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return provenance.error_response("internal_error", type(exc).__name__)
