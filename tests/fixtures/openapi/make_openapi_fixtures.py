"""Deterministically trim the real cached OpenAPI specs into small fixtures.

Manual, run from the repo root after `python -m tools.atlassian_docs`:

    python tests/fixtures/openapi/make_openapi_fixtures.py [--cache DIR]

Round 1 fixtures are regenerated from the frozen snapshot (--cache ~/.atlassian_api_updater/round1-cache).

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
        # Round 1 competitors (spec §10.1): the real top-1 ops observed in §0.1 and their neighbours
        "/rest/api/3/issue/{issueIdOrKey}/properties",
        "/rest/api/3/issuetypescheme/{issueTypeSchemeId}",
        "/rest/api/3/jql/parse",
        "/rest/api/3/projectvalidate/validProjectKey",
        "/rest/api/3/issue/{issueIdOrKey}/assignee",
        "/rest/api/3/issue/{issueIdOrKey}/comment",
        "/rest/api/3/project/{projectIdOrKey}",
        "/rest/api/3/attachment/{id}",
        "/rest/api/3/user",
        "/rest/api/3/users/search",
        "/rest/api/3/users",
    ],
    "jira-software": [
        "/rest/builds/0.1/bulk",                  # path-level parameters
        "/rest/agile/1.0/backlog/issue",
        "/rest/agile/1.0/issue/{issueIdOrKey}",
        "/rest/agile/1.0/board/{boardId}/backlog",
        "/rest/agile/1.0/board/{boardId}/sprint",
        "/rest/agile/1.0/sprint",
        "/rest/agile/1.0/sprint/{sprintId}/issue",
        "/rest/software/1.0/sprint/{sprintId}/issue",
        "/rest/agile/1.0/board",
        "/rest/agile/1.0/backlog/{boardId}/issue",
    ],
    "confluence": [
        "/pages",
        "/pages/{id}",
        "/attachments",                           # cursor pagination
        "/blogposts",                             # $ref requestBody
        "/pages/{page-id}/properties/{property-id}",
        "/pages/{page-id}/properties",
        "/spaces/{id}/pages",
        "/attachments/{id}",
        "/pages/{id}/title",
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


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cache = pathlib.Path(argv[argv.index("--cache") + 1]).expanduser() if "--cache" in argv else CACHE
    for source, paths in SELECTIONS.items():
        src = cache / f"{source}.json"
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
