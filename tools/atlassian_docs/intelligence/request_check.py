"""Structural request check — a fixed, small rule set; never a full validator (spec §16)."""
import hashlib
import importlib.metadata
import importlib.util
import re
from typing import Any, Optional

from . import inspect as insp
from . import oas_schema, policy, provenance, quirks, schemas
from .headers import TRANSPORT_HEADERS, credential_header_names
from .request_template import media_type

MISSING = object()
CHECKED_RULES = ("required", "type", "enum", "body_required", "content_type", "body_root_type",
                 "body_required_properties", "body_property_type", "body_property_enum", "body_unknown_property",
                 "body_not_declared", "quirk_headers")
NOT_CHECKED = ("oneOf/anyOf", "pattern", "format", "minimum/maximum", "minLength/maxLength",
               "nested objects beyond depth 2", "cookie parameters", "conflicting allOf properties")
JSONSCHEMA_CHECKED = ("required", "type", "enum", "body_required", "content_type", "body_not_declared",
                      "quirk_headers", "jsonschema:body")
JSONSCHEMA_NOT_CHECKED = ("format", "cookie parameters")
_MAX_SCHEMA_ERRORS = 50
_INT = re.compile(r"^-?\d+$")


def _type_ok(value: Any, schema: dict, *, from_string: bool) -> Optional[bool]:
    """True/False, or None when the rule does not apply (no type / object / unknown)."""
    typ = schema.get("type")
    if isinstance(typ, list):
        types = [t for t in typ if t != "null"]
        nullable = "null" in typ
        typ = types[0] if len(types) == 1 else None
    else:
        nullable = schema.get("nullable") is True
    if value is None:
        return True if nullable else (None if typ is None else False)
    if typ is None:
        return None
    if typ == "object":
        # query/header strings cannot be checked as objects; body values can.
        return None if from_string and isinstance(value, str) else isinstance(value, dict)
    if from_string and isinstance(value, str):
        if typ == "string":
            return True
        if typ == "integer":
            return bool(_INT.match(value))
        if typ == "number":
            try:
                float(value); return True
            except ValueError:
                return False
        if typ == "boolean":
            return value in ("true", "false")
        if typ == "array":
            return False
        return None
    if typ == "string":
        return isinstance(value, str)
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if typ == "boolean":
        return isinstance(value, bool)
    if typ == "array":
        return isinstance(value, list)
    return None


def _enum_ok(value: Any, schema: dict) -> Optional[bool]:
    enum = schema.get("enum")
    if not isinstance(enum, list) or value is None:
        return None
    return value in enum


def _merge_allof(schema: dict) -> tuple:
    """Return (merged_schema, conflicting_property_names). Only required/properties/additionalProperties merge."""
    if "allOf" not in schema:
        return schema, ()
    required: list = list(schema.get("required", []))
    props: dict = dict(schema.get("properties", {}))
    conflicts: set = set()
    addl = schema.get("additionalProperties")
    for part in schema["allOf"]:
        if not isinstance(part, dict) or "$ref" in part:
            continue
        for r in part.get("required", []):
            if r not in required:
                required.append(r)
        for name, sub in part.get("properties", {}).items():
            if name in props and props[name] != sub:
                conflicts.add(name)
            props.setdefault(name, sub)
        if part.get("additionalProperties") is False:
            addl = False
    merged = {"type": schema.get("type", "object"), "required": required, "properties": props}
    if addl is not None:
        merged["additionalProperties"] = addl
    return merged, tuple(sorted(conflicts))


def _jsonschema_available() -> bool:
    return importlib.util.find_spec("jsonschema") is not None


def validation_engine() -> dict:
    avail = _jsonschema_available()
    version = None
    if avail:
        try:
            version = importlib.metadata.version("jsonschema")
        except importlib.metadata.PackageNotFoundError:
            version = None
    return {"engine": "jsonschema" if avail else "structural", "version": version,
            "oas_transpiler_version": oas_schema.TRANSPILER_VERSION, "oas31_strong_validation": False}


def validation_fingerprint(intelligence_fp: str) -> str:
    e = validation_engine()
    blob = "\n".join([intelligence_fp, e["engine"], e["version"] or "-", str(e["oas_transpiler_version"])])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _path_str(abs_path) -> str:
    out = "body"
    for p in abs_path:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def _jsonschema_body_check(body, body_schema, comps, openapi_version, errors, warnings) -> tuple:
    """Returns ("jsonschema", None) on success or ("structural", reason) when the caller must fall back."""
    if not str(openapi_version).startswith("3.0."):
        return "structural", "oas31_not_supported"
    if not _jsonschema_available():
        return "structural", "jsonschema_not_installed"
    resolved = schemas.resolve(body_schema, comps, max_depth=schemas.MAX_DEPTH_LIMIT, max_nodes=schemas.MAX_NODES_LIMIT)
    if resolved.unresolved or resolved.cycles or resolved.truncated:
        return "structural", "schema_not_fully_resolvable"
    try:
        transpiled = oas_schema.oas30_to_draft7(resolved.schema)
    except ValueError:
        return "structural", "schema_transpile_failed"
    import jsonschema  # guarded optional import (spec §11.1)
    from jsonschema import exceptions as js_exc
    try:
        from referencing import exceptions as ref_exc
        unresolvable = (ref_exc.Unresolvable,)
    except ImportError:  # pragma: no cover
        unresolvable = ()
    try:
        jsonschema.Draft7Validator.check_schema(transpiled.schema)
    except js_exc.SchemaError:
        return "structural", "jsonschema_schema_error"
    try:
        validator = jsonschema.Draft7Validator(transpiled.schema)
        found = list(validator.iter_errors(body))
    except (js_exc.SchemaError, *unresolvable):
        return "structural", "jsonschema_runtime_error"
    for e in found[:_MAX_SCHEMA_ERRORS]:
        errors.append({"location": _path_str(e.absolute_path), "rule": f"schema:{e.validator}", "message": e.message})
    if len(found) > _MAX_SCHEMA_ERRORS:
        warnings.append({"location": "body", "rule": "errors_truncated", "message": f"{len(found)} schema errors; showing {_MAX_SCHEMA_ERRORS}"})
    for loc in oas_schema.find_readonly_values(body, transpiled.readonly_paths):
        warnings.append({"location": loc, "rule": "readonly_property_present", "message": "readOnly property supplied in a request"})
    return "jsonschema", None


def check_request(state, key: str, *, path_params=None, query=None, headers=None,
                  body=MISSING, content_type=None) -> dict:
    op, err = insp.resolve_operation(state, key=key)
    if err:
        return err
    comps = state.registry.sources[op.source]
    cred = credential_header_names(comps)
    path_params, query, headers = path_params or {}, query or {}, headers or {}
    errors, warnings = [], []
    hdr = {}
    for k, v in headers.items():
        if k.lower() in cred:   # never echo the value
            warnings.append({"location": f"header.{k}", "rule": "credential_header_ignored",
                             "message": "credential headers are out of scope and were ignored"})
        else:
            hdr[k.lower()] = v
    if content_type is None and isinstance(hdr.get("content-type"), str):
        content_type = hdr["content-type"]
    declared = {"query": set(), "header": set()}

    for p in op.parameters:
        loc = p.location
        if loc == "cookie":
            warnings.append({"location": f"cookie.{p.name}", "rule": "cookie_not_checked", "message": "cookie parameters are not checked"})
            continue
        source_map = {"path": path_params, "query": query, "header": hdr}[loc]
        lookup = p.name.lower() if loc == "header" else p.name
        declared.get(loc, set()).add(lookup)
        present = lookup in source_map
        if p.required and not present:
            errors.append({"location": f"{loc}.{p.name}", "rule": "required", "message": f"required {loc} parameter is missing"})
            continue
        if not present or not isinstance(p.schema, dict):
            continue
        value = source_map[lookup]
        ok = _type_ok(value, p.schema, from_string=isinstance(value, str))  # path/query/header arrive as strings
        if ok is False:
            errors.append({"location": f"{loc}.{p.name}", "rule": "type", "message": f"expected {p.schema.get('type')}"})
        elif _enum_ok(value, p.schema) is False:
            errors.append({"location": f"{loc}.{p.name}", "rule": "enum", "message": f"must be one of {p.schema['enum']}"})
    q = quirks.for_operation(op)
    for h in q.headers:
        low = h.name.lower()
        declared["header"].add(low)
        present = low in hdr
        matches = None if not present or h.value is None else (str(hdr[low]) == h.value)
        q_err, q_warn = quirks.outcome(h, present, matches)
        loc = f"header.{h.name}"
        if q_err == "required":
            errors.append({"location": loc, "rule": "required", "origin": h.origin, "message": "required header (spec-external quirk) is missing"})
        elif q_err == "quirk_value_mismatch":
            errors.append({"location": loc, "rule": "quirk_value_mismatch", "origin": h.origin, "message": f"expected literal value {h.value!r}"})
        if q_warn == "advisory_header_missing":
            warnings.append({"location": loc, "rule": "advisory_header_missing", "origin": h.origin, "message": "header mentioned in the official description is absent"})
        elif q_warn == "quirk_value_mismatch":
            warnings.append({"location": loc, "rule": "quirk_value_mismatch", "origin": h.origin, "message": f"expected value {h.value!r} (from {h.origin})"})
    for name in query:
        if name not in declared["query"]:
            warnings.append({"location": f"query.{name}", "rule": "unknown_parameter", "message": "not declared in the specification"})
    for name in headers:
        low = name.lower()
        if low not in declared["header"] and low not in TRANSPORT_HEADERS and low not in cred:
            warnings.append({"location": f"header.{name}", "rule": "unknown_parameter", "message": "not declared in the specification"})

    body_schema = None
    if op.request_body:
        types = [m.content_type for m in op.request_body.content]
        if op.request_body.required and body is MISSING:
            errors.append({"location": "body", "rule": "body_required", "message": "request body is required"})
        wanted = media_type(content_type) if isinstance(content_type, str) else content_type
        matching = [t for t in types if media_type(t) == wanted]
        if content_type is not None and not matching:
            errors.append({"location": "content_type", "rule": "content_type", "message": f"not declared; declared: {types}"})
        elif content_type is None and len(types) > 1 and body is not MISSING:
            warnings.append({"location": "content_type", "rule": "content_type_ambiguous",
                             "message": "several content types declared; pass content_type to check the body"})
            warnings.append({"location": "body", "rule": "structure_not_checked", "message": "content type ambiguous"})
        else:
            chosen = matching[0] if content_type is not None else (types[0] if types else None)
            body_schema = next((m.schema for m in op.request_body.content if m.content_type == chosen), None)

    elif body is not MISSING:
        warnings.append({"location": "body", "rule": "body_not_declared", "message": "operation declares no request body"})

    body_check, body_check_reason, run_structural = "structural", "no_body", False
    if body is not MISSING and body_schema is not None:
        body_check, reason = _jsonschema_body_check(body, body_schema, comps, comps.openapi_version, errors, warnings)
        body_check_reason = reason or ("structural_only" if body_check == "structural" else None)
        run_structural = body_check == "structural"
    if run_structural:
        resolved = schemas.resolve(body_schema, comps, max_depth=2, max_nodes=200).schema
        if "oneOf" in resolved or "anyOf" in resolved:
            warnings.append({"location": "body", "rule": "structure_not_checked", "message": "oneOf/anyOf bodies are not checked"})
        elif "$ref" in resolved:
            warnings.append({"location": "body", "rule": "structure_not_checked", "message": "schema could not be resolved within depth 2"})
        else:
            merged, conflicts = _merge_allof(resolved)
            root_ok = _type_ok(body, merged, from_string=False)
            if root_ok is False:
                errors.append({"location": "body", "rule": "body_root_type", "message": f"expected {merged.get('type')}"})
            elif isinstance(body, dict) and (merged.get("type") in (None, "object")):
                props = merged.get("properties", {})
                for name in conflicts:
                    warnings.append({"location": f"body.{name}", "rule": "conflicting_allof_property", "message": "allOf branches disagree; not checked"})
                for req in merged.get("required", []):
                    if req not in body:
                        errors.append({"location": f"body.{req}", "rule": "body_required_properties", "message": "required property is missing"})
                for name, value in body.items():
                    sub = props.get(name)
                    if sub is None:
                        if merged.get("additionalProperties") is False:
                            errors.append({"location": f"body.{name}", "rule": "body_unknown_property", "message": "not allowed by additionalProperties: false"})
                        continue
                    if name in conflicts or not isinstance(sub, dict) or "$ref" in sub:
                        continue
                    if _type_ok(value, sub, from_string=False) is False:
                        errors.append({"location": f"body.{name}", "rule": "body_property_type", "message": f"expected {sub.get('type')}"})
                    elif _enum_ok(value, sub) is False:
                        errors.append({"location": f"body.{name}", "rule": "body_property_enum", "message": f"must be one of {sub['enum']}"})

    if isinstance(body, dict):
        for f in q.request_hints.get("multipart_fields", []):
            if isinstance(f, dict) and f.get("required") and f.get("name") not in body:
                warnings.append({"location": f"body.{f['name']}", "rule": "multipart_field_missing",
                                 "message": "multipart form field expected by request hints is absent"})

    out = {"compatible": not errors, "errors": errors, "warnings": warnings,
           "checked": list(JSONSCHEMA_CHECKED if body_check == "jsonschema" else CHECKED_RULES),
           "not_checked": list(JSONSCHEMA_NOT_CHECKED if body_check == "jsonschema" else NOT_CHECKED),
           "body_check": body_check, "body_check_reason": body_check_reason,
           "quirks": {"applied": [h.to_dict() for h in q.headers], "suppressed": list(q.suppressed),
                      "request_hints": q.request_hints, "notes": list(q.notes)}}
    al_sha, ov_sha = policy.aliases().sha256, policy.overrides().sha256
    out["intelligence_fingerprint"] = policy.intelligence_fingerprint(state.registry.fingerprint, al_sha, ov_sha)
    out["intelligence_policy"] = policy.policy_block(al_sha, ov_sha)
    out["validation_engine"] = validation_engine()
    out["validation_fingerprint"] = validation_fingerprint(out["intelligence_fingerprint"])
    return provenance.with_provenance(out, state, [op.source])
