"""MCP SDK binding for the seven fixed tools (spec §17). All handlers run the synchronous
intelligence code in a worker thread so the event loop never blocks on Phase 1 sync.

Targets mcp 2.x (requirements-mcp.txt), where FastMCP was renamed to MCPServer
(`mcp.server.mcpserver`). Handlers return an explicit CallToolResult so an intelligence
error payload is delivered verbatim as JSON text with is_error=True."""
import asyncio
import json
import sys
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from ..intelligence import manager as manager_mod
from ..intelligence import registry
from . import tools

PROVENANCE_NOTE = ("Every result carries `provenance` per source: status fresh|stale|unavailable; when stale, the "
                   "result reflects the last good spec and `active_*` fields describe the spec actually used. "
                   "This server never calls Atlassian APIs; it only reads the official OpenAPI specs.")


def _text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))  # same bytes tools.payload_size measures


def create_server(manager) -> MCPServer:
    mcp = MCPServer("atlassian-openapi-intelligence")

    async def _run(name: str, args: dict) -> CallToolResult:
        payload = await asyncio.to_thread(tools.run_tool, manager, name, args)
        return CallToolResult(content=[TextContent(type="text", text=_text(payload))], is_error="error" in payload)

    @mcp.tool(name="search_operations", description="Weighted English ASCII lexical search over official Jira/Confluence OpenAPI operations "
              "(operationId, summary, tags, path, schema names, description). An exact canonical key or operationId (case-insensitive fallback) "
              "pins that operation to the top (`exact_match`); curated aliases expand the query (`alias_tokens`). "
              "Filters: source, method, tag, include_deprecated, limit (<=50). "
              "Round 3 abstention contract: the response carries method_intent_consistent, intent_methods, actionable and "
              "recommended_operation; when actionable is false the results are candidates only - do not treat results[0] as "
              "a recommendation. " + PROVENANCE_NOTE)
    async def search_operations(query: str, source: Optional[str] = None, method: Optional[str] = None, tag: Optional[str] = None,
                                include_deprecated: bool = True, limit: int = 10) -> CallToolResult:
        return await _run("search_operations", {"query": query, "source": source, "method": method, "tag": tag,
                                                "include_deprecated": include_deprecated, "limit": limit})

    @mcp.tool(name="get_operation", description="Compact detail for one operation by canonical key or (source, operation_id). "
              "Options: include_full_description, include_response_schemas, resolve_schema_depth (0-8). " + PROVENANCE_NOTE)
    async def get_operation(key: Optional[str] = None, source: Optional[str] = None, operation_id: Optional[str] = None,
                            include_full_description: bool = False, include_response_schemas: bool = False,
                            resolve_schema_depth: int = 0) -> CallToolResult:
        return await _run("get_operation", {"key": key, "source": source, "operation_id": operation_id,
                                            "include_full_description": include_full_description,
                                            "include_response_schemas": include_response_schemas,
                                            "resolve_schema_depth": resolve_schema_depth})

    @mcp.tool(name="get_schema", description="Resolve a components.schemas entry with bounded depth/nodes; cycles and unresolved refs are marked. " + PROVENANCE_NOTE)
    async def get_schema(source: str, name: str, max_depth: int = 2, max_nodes: int = 200) -> CallToolResult:
        return await _run("get_schema", {"source": source, "name": name, "max_depth": max_depth, "max_nodes": max_nodes})

    @mcp.tool(name="build_request_template", description="HTTP request template (method, path, params, content type, body schema, security). "
              "Known quirk headers are added with `origins` and `effective_required`; `quirks` reports applied/suppressed quirks "
              "and `request_hints` carries non-header guidance (e.g. multipart part names). "
              "No server URL and no Authorization/Cookie values are ever produced. " + PROVENANCE_NOTE)
    async def build_request_template(key: str, values: Optional[dict] = None) -> CallToolResult:
        return await _run("build_request_template", {"key": key, "values": values})

    @mcp.tool(name="check_request", description="Structural check of a planned request against the spec. `compatible` means no error "
              "was found by the fixed rule set listed in `checked`; it does NOT mean the request satisfies every OpenAPI rule (see `not_checked`). "
              "Omit `body` (or pass null) to mean 'no body'. Set body_present=false to mean 'no body' even if body is given "
              "(a `body_ignored` warning is added), body_present=true with body=null for an explicit JSON null. " + PROVENANCE_NOTE)
    async def check_request(key: str, path_params: Optional[dict] = None, query: Optional[dict] = None, headers: Optional[dict] = None,
                            body: Optional[object] = None, content_type: Optional[str] = None,
                            body_present: Optional[bool] = None) -> CallToolResult:
        args = {"key": key, "path_params": path_params, "query": query, "headers": headers, "content_type": content_type}
        if body_present is not None:  # disambiguates omitted vs JSON null, which the SDK collapses to None (spec §12)
            args["body_present"] = body_present
        if body is not None:  # the SDK maps both "omitted" and JSON null to None; only a non-null body reaches run_tool
            args["body"] = body
        return await _run("check_request", args)

    @mcp.tool(name="get_api_status", description="Registry and intelligence fingerprints, policy versions, per-source provenance, refresh/backoff state, "
              "validation capabilities and diagnostics (orphaned override keys, header candidates). Never triggers a refresh.")
    async def get_api_status() -> CallToolResult:
        return await _run("get_api_status", {})

    @mcp.tool(name="refresh_api_docs", description="Run the Phase 1 sync (24h TTL respected; no force) and rebuild the registry if the spec changed. "
              "Downloads only the official OpenAPI docs pages via the Phase 1 sync; never calls Jira/Confluence APIs. "
              "Returns refresh_in_progress if another refresh is running.")
    async def refresh_api_docs() -> CallToolResult:
        return await _run("refresh_api_docs", {})

    return mcp


def main(argv=None) -> int:
    mgr = manager_mod.RegistryManager()
    try:
        mgr.start()
    except registry.RegistryUnavailableError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    create_server(mgr).run(transport="stdio")
    return 0
