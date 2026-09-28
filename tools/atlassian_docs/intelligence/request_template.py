"""HTTP request *template* from an operation — no server URL, no credentials (spec §15)."""
import urllib.parse
from typing import Any, Optional

from . import inspect as insp
from . import provenance

CREDENTIAL_HEADERS = frozenset({"authorization", "cookie"})
_PRIMITIVES = (str, int, float, bool)
OUT_OF_SCOPE_NOTE = "server URL and Authorization are out of scope for Phase 2"


def _param_entry(p, value: Any, given: bool) -> dict:
    entry = {"required": p.required, "schema": p.schema, "deprecated": p.deprecated}
    if given:
        entry["value"] = value
    return entry


def build_request_template(state, key: str, values: Optional[dict] = None) -> dict:
    values = values or {}
    if not isinstance(values, dict):
        return provenance.error_response("invalid_argument", "values must be an object")
    op, err = insp.resolve_operation(state, key=key)
    if err:
        return err
    op_dict = op.to_dict()
    given_path = values.get("path_params") or {}
    given_query = values.get("query") or {}
    given_headers = values.get("headers") or {}
    notes, errors, missing = [OUT_OF_SCOPE_NOTE], [], []
    for v in given_path.values():
        if not isinstance(v, _PRIMITIVES):
            return provenance.error_response("invalid_argument", "path parameter values must be primitives")

    path_params, query, headers, cookies = {}, {}, {}, {}
    header_lookup = {k.lower(): (k, v) for k, v in given_headers.items()}
    for k in list(header_lookup):
        if k in CREDENTIAL_HEADERS:
            notes.append("credential_header_dropped")
            header_lookup.pop(k)
    used_headers = set()
    for p in op.parameters:
        if p.location == "path":
            given = p.name in given_path
            path_params[p.name] = _param_entry(p, given_path.get(p.name), given)
        elif p.location == "query":
            given = p.name in given_query
            query[p.name] = _param_entry(p, given_query.get(p.name), given)
        elif p.location == "header":
            hit = header_lookup.get(p.name.lower())
            if hit:
                used_headers.add(p.name.lower())
            headers[p.name] = _param_entry(p, hit[1] if hit else None, hit is not None)
        else:
            cookies[p.name] = _param_entry(p, None, False)
        if p.required and p.location != "cookie" and "value" not in {**path_params, **query, **headers}.get(p.name, {}):
            missing.append(p.name)
    unknown = {
        "path_params": sorted(k for k in given_path if k not in path_params),
        "query": sorted(k for k in given_query if k not in query),
        "headers": sorted(orig for low, (orig, _) in header_lookup.items() if low not in used_headers),
    }
    path = None
    if all("value" in e for e in path_params.values()):
        path = op.path
        for name, e in path_params.items():
            path = path.replace("{" + name + "}", urllib.parse.quote(str(e["value"]), safe=""))

    content_types = [m.content_type for m in op.request_body.content] if op.request_body else []
    schemas_by_ct = {m["content_type"]: m["schema"] for m in (op_dict["request_body"] or {}).get("content", [])}
    requested = values.get("content_type")
    selected, body_schema = None, None
    if requested is not None:
        if requested in content_types:
            selected = requested
        else:
            errors.append({"location": "content_type", "rule": "invalid_content_type",
                           "message": f"{requested!r} is not declared; declared: {content_types}"})
    elif content_types:
        selected = content_types[0]
        if len(content_types) > 1:
            notes.append("content_type_defaulted")
    if selected:
        body_schema = schemas_by_ct.get(selected)
    body_required = bool(op.request_body and op.request_body.required)
    if body_required and "body" not in values:
        missing.append("body")

    out = {
        "key": op.key, "method": op.method, "path_template": op.path, "path": path,
        "path_params": path_params, "query": query, "headers": headers, "cookies": cookies,
        "unknown_parameters": unknown, "content_types": content_types, "selected_content_type": selected,
        "body_schema": body_schema, "body": values.get("body"), "body_required": body_required,
        "security": op_dict["security"], "oauth2_scopes": op_dict["oauth2_scopes"], "server": None,
        "missing_required": missing, "errors": errors, "notes": notes,
    }
    return provenance.with_provenance(out, state, [op.source])
