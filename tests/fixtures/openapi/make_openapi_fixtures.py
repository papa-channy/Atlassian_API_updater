"""Deterministically trim the real cached OpenAPI specs into small fixtures.

Manual, run from the repo root after `python -m tools.atlassian_docs`:

    python tests/fixtures/openapi/make_openapi_fixtures.py

Keeps only the listed paths plus the transitive closure of every local
$ref they use. Output is sorted JSON so re-running yields identical files
when the upstream spec has not changed.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
CACHE = ROOT / ".atlassian-docs"
OUT = pathlib.Path(__file__).resolve().parent

SELECTIONS = {
    "jira-platform": [
        "/rest/api/3/issue",
        "/rest/api/3/issue/{issueIdOrKey}",
        "/rest/api/3/issue/{issueIdOrKey}/attachments",
        "/rest/api/3/issue/{issueIdOrKey}/transitions",
        "/rest/api/3/issue/createmeta",
        "/rest/api/3/search/jql",
        "/rest/api/3/expression/eval",            # deprecated operation
        "/rest/api/3/field/{fieldId}/context/defaultValue",  # deprecated + allOf-ish
    ],
    "jira-software": [
        "/rest/builds/0.1/bulk",                  # path-level parameters
        "/rest/agile/1.0/backlog/issue",
        "/rest/agile/1.0/issue/{issueIdOrKey}",
        "/rest/agile/1.0/board/{boardId}/backlog",
        "/rest/agile/1.0/board/{boardId}/sprint",
        "/rest/agile/1.0/sprint",
        "/rest/agile/1.0/sprint/{sprintId}/issue",
    ],
    "confluence": [
        "/pages",
        "/pages/{id}",
        "/attachments",                           # cursor pagination
        "/blogposts",                             # $ref requestBody
    ],
}

_REF = re.compile(r"^#/components/([^/]+)/(.+)$")


def _walk_refs(node, found):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            m = _REF.match(ref)
            if m:
                found.add((m.group(1), m.group(2)))
        for v in node.values():
            _walk_refs(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk_refs(v, found)


def trim(spec: dict, paths: list) -> dict:
    kept_paths = {p: spec["paths"][p] for p in paths if p in spec["paths"]}
    missing = [p for p in paths if p not in spec["paths"]]
    if missing:
        print(f"  warning: paths not found upstream: {missing}", file=sys.stderr)
    components = spec.get("components", {})
    needed, frontier = set(), set()
    _walk_refs(kept_paths, frontier)
    while frontier:
        needed |= frontier
        nxt = set()
        for section, name in frontier:
            _walk_refs(components.get(section, {}).get(name), nxt)
        frontier = nxt - needed
    out_components = {}
    for section, name in sorted(needed):
        value = components.get(section, {}).get(name)
        if value is not None:
            out_components.setdefault(section, {})[name] = value
    if "securitySchemes" in components:
        out_components["securitySchemes"] = components["securitySchemes"]
    used_tags = {t for item in kept_paths.values() for op in item.values()
                 if isinstance(op, dict) for t in op.get("tags", [])}
    out = {
        "openapi": spec["openapi"],
        "info": {"title": spec.get("info", {}).get("title"), "version": spec.get("info", {}).get("version")},
        "servers": spec.get("servers", []),
        "tags": [t for t in spec.get("tags", []) if t.get("name") in used_tags],
        "paths": kept_paths,
        "components": out_components,
    }
    if "security" in spec:
        out["security"] = spec["security"]
    return out


def main() -> int:
    for source, paths in SELECTIONS.items():
        src = CACHE / f"{source}.json"
        if not src.exists():
            print(f"[SKIP] {source}: {src} missing (run python -m tools.atlassian_docs)")
            continue
        spec = json.loads(src.read_text(encoding="utf-8"))
        trimmed = trim(spec, paths)
        dst = OUT / f"{source}-openapi.json"
        dst.write_text(json.dumps(trimmed, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        ops = sum(1 for item in trimmed["paths"].values() for m in item if m in ("get", "post", "put", "patch", "delete"))
        print(f"[OK] {source}: {len(trimmed['paths'])} paths, {ops} ops, "
              f"{len(trimmed['components'].get('schemas', {}))} schemas -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
