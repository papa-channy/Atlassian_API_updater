"""Structural request check — a fixed, small rule set; never a full validator (spec §16)."""
import re
from typing import Any, Optional

from . import inspect as insp
from . import provenance, schemas

MISSING = object()
CHECKED_RULES = ("required", "type", "enum", "body_required", "content_type", "body_root_type",
                 "body_required_properties", "body_property_type", "body_property_enum", "body_unknown_property")
NOT_CHECKED = ("oneOf/anyOf", "pattern", "format", "minimum/maximum", "minLength/maxLength",
               "nested objects beyond depth 2", "cookie parameters", "conflicting allOf properties")
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


def check_request(state, key: str, *, path_params=None, query=None, headers=None,
                  body=MISSING, content_type=None) -> dict:
    op, err = insp.resolve_operation(state, key=key)
    if err:
        return err
    comps = state.registry.sources[op.source]
    path_params, query, headers = path_params or {}, query or {}, headers or {}
    errors, warnings = [], []
    hdr = {k.lower(): v for k, v in headers.items()}
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
    for name in query:
        if name not in declared["query"]:
            warnings.append({"location": f"query.{name}", "rule": "unknown_parameter", "message": "not declared in the specification"})
    for name in headers:
        if name.lower() not in declared["header"]:
            warnings.append({"location": f"header.{name}", "rule": "unknown_parameter", "message": "not declared in the specification"})

    body_schema = None
    if op.request_body:
        types = [m.content_type for m in op.request_body.content]
        if op.request_body.required and body is MISSING:
            errors.append({"location": "body", "rule": "body_required", "message": "request body is required"})
        if content_type is not None and content_type not in types:
            errors.append({"location": "content_type", "rule": "content_type", "message": f"not declared; declared: {types}"})
        elif content_type is None and len(types) > 1 and body is not MISSING:
            warnings.append({"location": "content_type", "rule": "content_type_ambiguous",
                             "message": "several content types declared; pass content_type to check the body"})
            warnings.append({"location": "body", "rule": "structure_not_checked", "message": "content type ambiguous"})
        else:
            chosen = content_type or (types[0] if types else None)
            body_schema = next((m.schema for m in op.request_body.content if m.content_type == chosen), None)

    if body is not MISSING and body_schema is not None:
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

    out = {"compatible": not errors, "errors": errors, "warnings": warnings,
           "checked": list(CHECKED_RULES), "not_checked": list(NOT_CHECKED)}
    return provenance.with_provenance(out, state, [op.source])
