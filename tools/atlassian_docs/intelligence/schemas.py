"""Local `$ref` lookup and bounded recursive resolution (spec §8)."""
import copy
import re
from dataclasses import dataclass
from typing import Any, Optional

MAX_DEPTH_LIMIT = 8
MAX_NODES_LIMIT = 2000
_SECTIONS = {"schemas": "schemas", "parameters": "parameters",
             "requestBodies": "request_bodies", "responses": "responses"}
_LOCAL = re.compile(r"^#/components/(schemas|parameters|requestBodies|responses)/(.+)$")
_RECURSE_KEYS = ("allOf", "oneOf", "anyOf", "items", "properties", "additionalProperties", "not")


def parse_local_ref(ref: str) -> Optional[tuple]:
    m = _LOCAL.match(ref) if isinstance(ref, str) else None
    return (m.group(1), m.group(2)) if m else None


def lookup_ref(components: Any, ref: str) -> tuple:
    parsed = parse_local_ref(ref)
    if parsed is None:
        return None, "external"
    section, name = parsed
    node = getattr(components, _SECTIONS[section], {}).get(name)
    if isinstance(node, dict):
        return node, "ok"
    return None, "missing"


@dataclass(frozen=True)
class ResolvedSchema:
    schema: dict
    truncated: bool
    unresolved: tuple
    cycles: tuple
    node_count: int


class _Budget:
    def __init__(self, max_nodes: int):
        self.max_nodes = max_nodes
        self.count = 0
        self.truncated = False
        self.unresolved: list = []
        self.cycles: list = []


def _walk(node: Any, components: Any, depth: int, max_depth: int, stack: tuple, budget: _Budget) -> Any:
    if isinstance(node, list):
        return [_walk(v, components, depth, max_depth, stack, budget) for v in node]
    if not isinstance(node, dict):
        return copy.deepcopy(node)
    ref = node.get("$ref")
    if isinstance(ref, str):
        if ref in stack:
            budget.cycles.append(ref)
            return {"$ref": ref, "_cycle": True}
        if depth >= max_depth:
            budget.truncated = True
            return {"$ref": ref, "_truncated": "depth"}
        if budget.count >= budget.max_nodes:
            budget.truncated = True
            return {"$ref": ref, "_truncated": "nodes"}
        target, status = lookup_ref(components, ref)
        if target is None:
            budget.unresolved.append(ref)
            return {"$ref": ref, "_unresolved": status}
        budget.count += 1
        return _walk(target, components, depth + 1, max_depth, stack + (ref,), budget)
    out = {}
    for key, value in node.items():
        if key in _RECURSE_KEYS:
            if key == "properties" and isinstance(value, dict):
                out[key] = {k: _walk(v, components, depth, max_depth, stack, budget) for k, v in value.items()}
            else:
                out[key] = _walk(value, components, depth, max_depth, stack, budget)
        else:
            out[key] = copy.deepcopy(value)
    return out


def resolve(node: Any, components: Any, *, max_depth: int = 2, max_nodes: int = 200) -> ResolvedSchema:
    if not 0 <= max_depth <= MAX_DEPTH_LIMIT:
        raise ValueError(f"max_depth must be 0..{MAX_DEPTH_LIMIT}")
    if not 1 <= max_nodes <= MAX_NODES_LIMIT:
        raise ValueError(f"max_nodes must be 1..{MAX_NODES_LIMIT}")
    budget = _Budget(max_nodes)
    schema = _walk(node, components, 0, max_depth, (), budget)
    return ResolvedSchema(schema=schema, truncated=budget.truncated,
                          unresolved=tuple(budget.unresolved), cycles=tuple(budget.cycles),
                          node_count=budget.count)


def collect_local_ref_names(node: Any, *, max_depth: int = 6) -> tuple:
    found: set = set()

    def walk(n: Any, depth: int) -> None:
        if depth > max_depth:
            return
        if isinstance(n, list):
            for v in n:
                walk(v, depth + 1)
        elif isinstance(n, dict):
            parsed = parse_local_ref(n.get("$ref")) if isinstance(n.get("$ref"), str) else None
            if parsed:
                found.add(parsed[1])
            for key in _RECURSE_KEYS:
                if key in n:
                    if key == "properties" and isinstance(n[key], dict):
                        for v in n[key].values():
                            walk(v, depth + 1)
                    else:
                        walk(n[key], depth + 1)
    walk(node, 0)
    return tuple(sorted(found))
