"""OpenAPI 3.0 Schema Object -> JSON Schema draft-07, request direction (spec §11.2). Stdlib only, pure."""
import copy
from dataclasses import dataclass
from typing import Any, List

TRANSPILER_VERSION = 1
_DROP = ("discriminator", "xml", "externalDocs", "deprecated", "example", "examples")
_SCHEMA_KEYS = ("items", "additionalProperties", "not")
_LIST_KEYS = ("allOf", "oneOf", "anyOf")


@dataclass(frozen=True)
class TranspiledSchema:
    schema: dict
    readonly_paths: tuple


def oas30_to_draft7(schema: Any) -> TranspiledSchema:
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object")
    paths: list = []
    out = _walk(copy.deepcopy(schema), (), paths)
    return TranspiledSchema(out, tuple(paths))


def _walk(node: dict, path: tuple, paths: list) -> dict:
    out = {}
    for key, value in node.items():
        if key in _DROP or key.startswith("x-"):
            continue
        out[key] = value
    # nullable
    if out.pop("nullable", None) is True and isinstance(out.get("type"), str):
        out["type"] = [out["type"], "null"]
    # exclusive bounds (OAS 3.0 booleans)
    for excl, bound in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        if isinstance(out.get(excl), bool):
            flag = out.pop(excl)
            if flag and bound in out:
                out[excl] = out.pop(bound)
    # readOnly / writeOnly on this node (recorded by the parent via properties)
    out.pop("writeOnly", None)
    # recurse
    props = out.get("properties")
    if props is not None:
        if not isinstance(props, dict):
            raise ValueError("properties must be an object")
        new_props, readonly_names = {}, []
        for name, sub in props.items():
            if isinstance(sub, dict) and sub.get("readOnly") is True:
                readonly_names.append(name)
                paths.append(path + (name,))
            new_props[name] = _walk({k: v for k, v in sub.items() if k != "readOnly"}, path + (name,), paths) if isinstance(sub, dict) else sub
        out["properties"] = new_props
        if readonly_names and isinstance(out.get("required"), list):
            out["required"] = [r for r in out["required"] if r not in readonly_names]
    out.pop("readOnly", None)
    for key in _SCHEMA_KEYS:
        if isinstance(out.get(key), dict):
            out[key] = _walk(out[key], path + ((key,) if key == "items" else ()), paths)
    for key in _LIST_KEYS:
        if isinstance(out.get(key), list):
            out[key] = [_walk(p, path, paths) if isinstance(p, dict) else p for p in out[key]]
    # rule 5: Atlassian unions overlap (non-exclusive); an advisory check prefers false negatives -> oneOf becomes anyOf
    if "oneOf" in out:
        branches = out.pop("oneOf")
        if "anyOf" in out:
            out["allOf"] = list(out.get("allOf") or []) + [{"anyOf": branches}]
        else:
            out["anyOf"] = branches
    return out


def find_readonly_values(body: Any, readonly_paths) -> List[str]:
    found: list = []

    def visit(value: Any, segs: tuple, loc: str) -> None:
        if not segs:
            found.append(loc)
            return
        head, rest = segs[0], segs[1:]
        if head == "items" and isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, rest, f"{loc}[{i}]")
        elif isinstance(value, dict) and head in value:
            visit(value[head], rest, f"{loc}.{head}")

    for p in readonly_paths:
        visit(body, tuple(p), "body")
    return found
