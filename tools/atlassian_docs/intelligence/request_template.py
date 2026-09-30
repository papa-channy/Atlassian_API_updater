"""HTTP request *template* from an operation — no server URL, no credentials (spec §15)."""
import copy
import urllib.parse
from typing import Any, Optional

from . import inspect as insp
from . import policy, provenance, quirks
from .headers import REDACTED, credential_header_names, is_transport


def media_type(value: str) -> str:
    """`application/json; charset=utf-8` -> `application/json` (parameters dropped, lower-cased)."""
    return value.split(";")[0].strip().lower()
_PRIMITIVES = (str, int, float, bool)
OUT_OF_SCOPE_NOTE = "server URL and Authorization are out of scope for Phase 2"


def _param_entry(p, value: Any, given: bool) -> dict:
    entry = {"required": p.required, "schema": copy.deepcopy(p.schema), "deprecated": p.deprecated}
    if given:
        entry["value"] = value
    return entry


def _header_entry(p, value: Any, given: bool, quirk=None, redact: bool = False) -> dict:
    declared = bool(p.required) if p is not None else False
    q_required = quirk is not None and quirk.enforcement == "required"
    origins = (["spec"] if p is not None else []) + ([quirk.origin] if quirk else [])
    eff_origins = (["spec"] if declared else []) + ([quirk.origin] if q_required else [])
    entry = {"required": declared, "declared_required": declared, "effective_required": declared or q_required,
             "origins": origins, "effective_required_origins": eff_origins,
             "enforcement": quirk.enforcement if quirk else None, "note": quirk.note if quirk else None,
             "schema": copy.deepcopy(p.schema) if p is not None else None,
             "deprecated": bool(p.deprecated) if p is not None else False}
    if given:
        entry["value"] = value
    elif quirk is not None and quirk.value is not None:
        entry["value"] = REDACTED if redact else quirk.value
    return entry


def build_request_template(state, key: str, values: Optional[dict] = None) -> dict:
    values = values or {}
    if not isinstance(values, dict):
        return provenance.error_response("invalid_argument", "values must be an object")
    op, err = insp.resolve_operation(state, key=key)
    if err:
        return err
    op_dict = op.to_dict()
    cred = credential_header_names(state.registry.sources[op.source])
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
        if k in cred:
            notes.append("credential_header_dropped")
            header_lookup.pop(k)
    used_headers = set()
    q = quirks.for_operation(op)
    qmap = {h.name.lower(): h for h in q.headers}
    advisories = []
    for p in op.parameters:
        if p.location == "path":
            given = p.name in given_path
            path_params[p.name] = _param_entry(p, given_path.get(p.name), given)
        elif p.location == "query":
            given = p.name in given_query
            query[p.name] = _param_entry(p, given_query.get(p.name), given)
        elif p.location == "header":
            low = p.name.lower()
            hit = header_lookup.get(low)
            if hit:
                used_headers.add(low)
            headers[p.name] = _header_entry(p, hit[1] if hit else None, hit is not None, qmap.pop(low, None), low in cred)
            if headers[p.name]["effective_required"] and hit is None:
                missing.append(p.name)
            continue
        else:
            cookies[p.name] = _param_entry(p, None, False)
        bucket = {"path": path_params, "query": query}.get(p.location)
        if p.required and bucket is not None and "value" not in bucket.get(p.name, {}):
            missing.append(p.name)
    for h in qmap.values():
        low = h.name.lower()
        hit = header_lookup.get(low)
        if hit:
            used_headers.add(low)
        elif h.enforcement != "required":
            advisories.append({"name": h.name, "origin": h.origin, "note": h.note})
            continue
        headers[h.name] = _header_entry(None, hit[1] if hit else None, hit is not None, h, low in cred)
        if headers[h.name]["effective_required"] and hit is None:
            missing.append(h.name)
    transport = [{"name": orig, "value": v} for low, (orig, v) in sorted(header_lookup.items())
                 if is_transport(low) and low not in used_headers]
    unknown = {
        "path_params": sorted(k for k in given_path if k not in path_params),
        "query": sorted(k for k in given_query if k not in query),
        "headers": sorted(orig for low, (orig, _) in header_lookup.items() if low not in used_headers and not is_transport(low)),
    }
    path = None
    if all("value" in e for e in path_params.values()):
        path = op.path
        for name, e in path_params.items():
            path = path.replace("{" + name + "}", urllib.parse.quote(str(e["value"]), safe=""))

    content_types = [m.content_type for m in op.request_body.content] if op.request_body else []
    schemas_by_ct = {m["content_type"]: m["schema"] for m in (op_dict["request_body"] or {}).get("content", [])}
    requested = values.get("content_type")
    if requested is None:
        requested = next((t["value"] for t in transport if t["name"].lower() == "content-type"), None)
    selected, body_schema = None, None
    if requested is not None:
        match = [ct for ct in content_types if isinstance(requested, str) and media_type(ct) == media_type(requested)]
        if match:
            selected = match[0]
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
        "unknown_parameters": unknown, "transport_headers": transport, "content_types": content_types, "selected_content_type": selected,
        "body_schema": body_schema, "body": values.get("body"), "body_required": body_required,
        "security": op_dict["security"], "oauth2_scopes": op_dict["oauth2_scopes"], "server": None,
        "missing_required": missing, "errors": errors, "notes": notes,
        "advisories": advisories, "request_hints": q.request_hints,
        "quirks": {"applied": [h.to_dict() for h in q.headers], "advisories": advisories,
                   "suppressed": list(q.suppressed), "request_hints": q.request_hints},
    }
    al_sha, ov_sha = policy.aliases().sha256, policy.overrides().sha256
    out["intelligence_fingerprint"] = policy.intelligence_fingerprint(state.registry.fingerprint, al_sha, ov_sha)
    out["intelligence_policy"] = policy.policy_block(al_sha, ov_sha)
    return provenance.with_provenance(out, state, [op.source])
