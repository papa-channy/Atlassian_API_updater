"""get_operation / get_schema with compact-by-default output (spec §14)."""
from typing import Optional

from .. import sources
from . import provenance, schemas

DESCRIPTION_COMPACT_CHARS = 500


def _check_source(reg, name: str) -> Optional[dict]:
    """None if `name` is loaded; otherwise the error dict to return.
    Registry membership is checked first so fixture-aliased sources work; SOURCES only
    decides between 'unknown' and 'configured but unavailable'."""
    if name in reg.sources:
        return None
    if name in sources.SOURCES:
        return provenance.error_response("source_unavailable", f"source {name!r} is unavailable")
    return provenance.error_response("invalid_argument", f"unknown source {name!r}")


def resolve_operation(state, key: Optional[str] = None, source: Optional[str] = None,
                      operation_id: Optional[str] = None) -> tuple:
    reg = state.registry
    if key:
        src = key.split(":", 1)[0]
        err = _check_source(reg, src)
        if err:
            return None, err
        op = reg.get_operation(key)
        return (op, None) if op else (None, provenance.error_response("operation_not_found", f"no operation {key!r}"))
    if not operation_id:
        return None, provenance.error_response("invalid_argument", "provide key, or operation_id (optionally with source)")
    if source is not None:
        err = _check_source(reg, source)
        if err:
            return None, err
    keys = reg.find_by_operation_id(source, operation_id)
    if not keys:
        return None, provenance.error_response("operation_not_found", f"no operation with operationId {operation_id!r}")
    if len(keys) > 1:
        return None, provenance.error_response("ambiguous_operation_id", "operationId maps to several operations; use key",
                                               candidates=list(keys))
    return reg.get_operation(keys[0]), None


def _maybe_resolve(node: Optional[dict], comps, depth: int) -> Optional[dict]:
    if node is None or depth <= 0:
        return node
    return schemas.resolve(node, comps, max_depth=depth, max_nodes=schemas.MAX_NODES_LIMIT).schema


def get_operation(state, key=None, source=None, operation_id=None, *, include_full_description=False,
                  include_response_schemas=False, resolve_schema_depth=0) -> dict:
    if not isinstance(resolve_schema_depth, int) or not 0 <= resolve_schema_depth <= schemas.MAX_DEPTH_LIMIT:
        return provenance.error_response("invalid_argument", f"resolve_schema_depth must be 0..{schemas.MAX_DEPTH_LIMIT}")
    op, err = resolve_operation(state, key, source, operation_id)
    if err:
        return err
    comps = state.registry.sources[op.source]
    out = op.to_dict()  # deep-copied raw fragments
    desc = op.description or ""
    truncated = (not include_full_description) and len(desc) > DESCRIPTION_COMPACT_CHARS
    out["description"] = desc[:DESCRIPTION_COMPACT_CHARS] if truncated else desc
    out["description_truncated"] = truncated
    for p in out["parameters"]:
        p["schema"] = _maybe_resolve(p["schema"], comps, resolve_schema_depth)
    if out["request_body"]:
        for m in out["request_body"]["content"]:
            m["schema"] = _maybe_resolve(m["schema"], comps, resolve_schema_depth)
    responses = []
    for r in out["responses"]:
        item: dict = {"status": r["status"], "content_types": [m["content_type"] for m in r["content"]]}
        if include_response_schemas:
            item["description"] = r["description"]
            item["content"] = [{"content_type": m["content_type"],
                                "schema": _maybe_resolve(m["schema"], comps, resolve_schema_depth)} for m in r["content"]]
        responses.append(item)
    out["responses"] = responses
    return provenance.with_provenance(out, state, [op.source])


def get_schema(state, source: str, name: str, *, max_depth: int = 2, max_nodes: int = 200) -> dict:
    err = _check_source(state.registry, source)
    if err:
        return err
    comps = state.registry.sources[source]
    if name not in comps.schemas:
        return provenance.error_response("schema_not_found", f"no schema {name!r} in {source}")
    if not isinstance(max_depth, int) or not 0 <= max_depth <= schemas.MAX_DEPTH_LIMIT:
        return provenance.error_response("invalid_argument", f"max_depth must be 0..{schemas.MAX_DEPTH_LIMIT}")
    try:
        # the synthetic top-level $ref costs one level, so "depth 2" means two levels below the named schema
        resolved = schemas.resolve({"$ref": f"#/components/schemas/{name}"}, comps,
                                   max_depth=min(max_depth + 1, schemas.MAX_DEPTH_LIMIT), max_nodes=max_nodes)
    except ValueError as exc:
        return provenance.error_response("invalid_argument", str(exc))
    out = {"source": source, "name": name, "schema": resolved.schema, "truncated": resolved.truncated,
           "unresolved": list(resolved.unresolved), "cycles": list(resolved.cycles), "node_count": resolved.node_count}
    return provenance.with_provenance(out, state, [source])
