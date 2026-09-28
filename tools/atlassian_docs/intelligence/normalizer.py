"""Raw OpenAPI dict -> NormalizedSpec (spec §7). Pure; never mutates input."""
import copy
from dataclasses import dataclass
from typing import Any, Optional

from .models import (MediaType, Operation, Parameter, RequestBody, Response,
                     SecurityAlternative, SecurityRequirement)

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")
_EXAMPLE_KEYS = ("example", "examples")


class NormalizationError(Exception):
    """The spec as a whole cannot be normalised (e.g. paths is not a dict)."""


@dataclass(frozen=True)
class NormalizedSpec:
    source: str
    openapi_version: str
    title: Optional[str]
    operations: tuple
    schemas: dict
    parameters: dict
    request_bodies: dict
    responses: dict
    security_schemes: dict
    tags: tuple
    warnings: tuple
    normalization_partial: bool


_NAME_MAP_KEYS = frozenset({"properties", "patternProperties", "definitions", "$defs"})


def strip_examples(node: Any, *, in_name_map: bool = False) -> Any:
    """Deep copy of node with `example`/`examples` schema keywords removed.

    Entries of a name map (`properties`, `patternProperties`, `definitions`, `$defs`, or a
    components section when called with in_name_map=True) are user-chosen names, so a property
    literally called `example` is kept; the entry values are schemas again.
    """
    if isinstance(node, dict):
        if in_name_map:
            return {k: strip_examples(v) for k, v in node.items()}
        return {k: strip_examples(v, in_name_map=k in _NAME_MAP_KEYS)
                for k, v in node.items() if k not in _EXAMPLE_KEYS}
    if isinstance(node, list):
        return [strip_examples(v) for v in node]
    return copy.deepcopy(node)


def _components(spec: dict, section: str) -> dict:
    comps = spec.get("components")
    if not isinstance(comps, dict):
        return {}
    value = comps.get(section)
    return value if isinstance(value, dict) else {}


def _deref(node: Any, components: dict, section: str) -> Any:
    """Resolve a top-level `$ref` into components[section]; other refs are left alone."""
    if isinstance(node, dict) and isinstance(node.get("$ref"), str):
        prefix = f"#/components/{section}/"
        if node["$ref"].startswith(prefix):
            target = components.get(section, {}).get(node["$ref"][len(prefix):])
            if isinstance(target, dict):
                return target
    return node


def _parameter(raw: dict) -> Parameter:
    location = raw.get("in")
    name = raw.get("name")
    if not isinstance(name, str) or location not in ("path", "query", "header", "cookie"):
        raise ValueError(f"invalid parameter: {raw!r}")
    schema = raw.get("schema")
    return Parameter(
        name=name, location=location,
        required=True if location == "path" else bool(raw.get("required", False)),
        description=raw.get("description") if isinstance(raw.get("description"), str) else None,
        schema=strip_examples(schema) if isinstance(schema, dict) else None,
        deprecated=raw.get("deprecated") is True,
    )


def _merge_parameters(path_level: list, op_level: list, components: dict) -> tuple:
    merged: dict = {}
    for raw in path_level:
        p = _parameter(_deref(raw, components, "parameters"))
        merged[(p.name, p.location)] = p
    for raw in op_level:
        p = _parameter(_deref(raw, components, "parameters"))
        merged[(p.name, p.location)] = p  # override keeps original insertion position
    return tuple(merged.values())


def _media_types(content: Any) -> tuple:
    if not isinstance(content, dict):
        return ()
    out = []
    for ctype, media in content.items():
        schema = media.get("schema") if isinstance(media, dict) else None
        out.append(MediaType(ctype, strip_examples(schema) if isinstance(schema, dict) else None))
    return tuple(out)


def _request_body(raw: Any, components: dict) -> Optional[RequestBody]:
    raw = _deref(raw, components, "requestBodies")
    if not isinstance(raw, dict):
        return None
    return RequestBody(
        required=raw.get("required") is True,
        description=raw.get("description") if isinstance(raw.get("description"), str) else None,
        content=_media_types(raw.get("content")),
    )


def _responses(raw: Any, components: dict) -> tuple:
    if not isinstance(raw, dict):
        return ()
    out = []
    for status, resp in raw.items():
        resp = _deref(resp, components, "responses")
        if not isinstance(resp, dict):
            continue
        out.append(Response(str(status),
                            resp.get("description") if isinstance(resp.get("description"), str) else None,
                            _media_types(resp.get("content"))))
    return tuple(out)


def _security(raw: Any) -> tuple:
    if not isinstance(raw, list):
        return ()
    alts = []
    for alt in raw:
        if not isinstance(alt, dict):
            continue
        reqs = tuple(SecurityRequirement(str(scheme), tuple(str(s) for s in scopes) if isinstance(scopes, list) else ())
                     for scheme, scopes in alt.items())
        alts.append(SecurityAlternative(reqs))
    return tuple(alts)


def _oauth2_scopes(raw: Any, warnings: list, where: str) -> tuple:
    if not isinstance(raw, list):
        if raw is not None:
            warnings.append({"kind": "oauth2_scopes_shape_ignored", "operation": where})
        return ()
    seen, out = set(), []
    for item in raw:
        scopes = item.get("scopes") if isinstance(item, dict) else item
        if isinstance(scopes, str):
            scopes = [scopes]
        if not isinstance(scopes, list):
            warnings.append({"kind": "oauth2_scopes_shape_ignored", "operation": where})
            continue
        for s in scopes:
            if isinstance(s, str) and s not in seen:
                seen.add(s)
                out.append(s)
    return tuple(out)


def _operation(source: str, path: str, method: str, raw: dict, path_params: list,
               top_security: Any, components: dict, warnings: list) -> Operation:
    where = f"{method.upper()} {path}"
    op_params = raw.get("parameters", [])
    if not isinstance(op_params, list):
        raise ValueError("parameters is not a list")
    security_raw = raw["security"] if "security" in raw else top_security
    experimental_raw = raw.get("x-experimental")
    if experimental_raw is not None and experimental_raw is not True and experimental_raw is not False:
        warnings.append({"kind": "experimental_value_ignored", "operation": where, "value": experimental_raw})
    tags = raw.get("tags", [])
    return Operation(
        source=source,
        key=f"{source}:{method.upper()}:{path}",
        operation_id=raw.get("operationId") if isinstance(raw.get("operationId"), str) else None,
        method=method.upper(), path=path,
        summary=raw.get("summary") if isinstance(raw.get("summary"), str) else None,
        description=raw.get("description") if isinstance(raw.get("description"), str) else None,
        tags=tuple(str(t) for t in tags) if isinstance(tags, list) else (),
        parameters=_merge_parameters(path_params, op_params, components),
        request_body=_request_body(raw.get("requestBody"), components),
        responses=_responses(raw.get("responses"), components),
        security=_security(security_raw),
        deprecated=raw.get("deprecated") is True,
        experimental=experimental_raw is True,
        oauth2_scopes=_oauth2_scopes(raw.get("x-atlassian-oauth2-scopes"), warnings, where),
    )


def normalize_openapi(source_name: str, spec: dict) -> NormalizedSpec:
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise NormalizationError("spec.paths is not an object")
    components = {s: _components(spec, s) for s in ("schemas", "parameters", "requestBodies", "responses", "securitySchemes")}
    warnings: list = []
    operations: list = []
    top_security = spec.get("security")
    for path, item in spec["paths"].items():
        if not isinstance(item, dict):
            warnings.append({"kind": "path_item_invalid", "path": path})
            continue
        if "$ref" in item:
            warnings.append({"kind": "path_item_ref_unsupported", "path": path})
            continue
        path_params = item.get("parameters", [])
        if not isinstance(path_params, list):
            path_params = []
        for method in HTTP_METHODS:
            raw = item.get(method)
            if not isinstance(raw, dict):
                continue
            try:
                operations.append(_operation(source_name, path, method, raw, path_params,
                                             top_security, components, warnings))
            except Exception as exc:  # noqa: BLE001 - one bad operation must not sink the source
                warnings.append({"kind": "operation_skipped", "path": path, "method": method.upper(), "reason": str(exc)})
    partial = any(w["kind"] == "operation_skipped" for w in warnings)
    tags = sorted({str(t.get("name")) for t in spec.get("tags", []) if isinstance(t, dict) and t.get("name")}
                  | {t for op in operations for t in op.tags})
    info = spec.get("info") if isinstance(spec.get("info"), dict) else {}
    return NormalizedSpec(
        source=source_name,
        openapi_version=str(spec.get("openapi")),
        title=info.get("title") if isinstance(info.get("title"), str) else None,
        operations=tuple(operations),
        schemas=strip_examples(components["schemas"], in_name_map=True),
        parameters=strip_examples(components["parameters"], in_name_map=True),
        request_bodies=strip_examples(components["requestBodies"], in_name_map=True),
        responses=strip_examples(components["responses"], in_name_map=True),
        security_schemes=copy.deepcopy(components["securitySchemes"]),
        tags=tuple(tags),
        warnings=tuple(warnings),
        normalization_partial=partial,
    )
