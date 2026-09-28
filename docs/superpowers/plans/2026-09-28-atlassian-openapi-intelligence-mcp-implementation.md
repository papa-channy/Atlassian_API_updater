# Atlassian OpenAPI Intelligence MCP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/atlassian_docs/intelligence/` (stdlib-only registry, search, schema resolution, request template/check, self-updating manager) and `tools/atlassian_docs/mcp/` (7 fixed MCP tools over the official `mcp` SDK) on top of the untouched Phase 1 sync core.

**Architecture:** Bottom-up in four milestones. 2A: fixtures → domain model → normalizer → `$ref` resolver → tokenizer/index → registry → gate. 2B: provenance → search → inspect → request template → request check (all pure functions over an immutable `ActiveState`). 2C: last-known-good persistence → `RegistryManager` (cache-first startup, `needs_refresh`, failure-only monotonic backoff, atomic `ActiveState` swap). 2D: SDK-free tool handlers → FastMCP binding → docs/smoke. Every intelligence function takes `state: ActiveState` first, returns a JSON-serialisable dict, and never leaks registry-internal dicts.

**Tech Stack:** Python ≥ 3.10 (dev 3.11), stdlib only for everything under `intelligence/` and Phase 1 (`dataclasses`, `copy`, `re`, `json`, `hashlib`, `threading`, `time`, `datetime`, `pathlib`, `tempfile`, `os`, `ast`, `unittest`). `mcp>=2.2,<3` only for `tools/atlassian_docs/mcp/` and `tests/mcp/test_server.py`.

**Spec:** `docs/superpowers/specs/2026-09-28-atlassian-openapi-intelligence-mcp-design.md` (v2.1). Section numbers below (§N) refer to it. Executors read both.

## Global Constraints

- Phase 1 files are never modified: `git diff ffbdd42 -- tools/atlassian_docs/{__main__,sources,extractor,sync,storage}.py` must stay empty (AC-02). Import them; never edit them.
- `intelligence/**` and all `tests/intelligence/**` import only the standard library plus `tools.atlassian_docs.{sync,storage,extractor,sources}` and sibling `intelligence` modules. `mcp/**` may additionally import the `mcp` package. Neither may import `urllib.request`, `http.client`, or `socket` (§4, AC-03, AC-35). Enforced by `tests/test_layering.py` (Task 1).
- Tests use `unittest` (not pytest) and run with `python -m unittest discover -s tests -t .` from the repo root, fully offline. Network happens only inside Phase 1 `sync.sync_all`, which tests replace with fakes (AC-34). `tests/live_mcp_smoke.py` is manual only.
- Canonical operation key is exactly `f"{source}:{method.upper()}:{path}"` (§9.1).
- `spec_sha256` is always `storage.sha256_of_spec(spec)` (canonical JSON hash, same definition as Phase 1 metadata) (§9.2).
- Logical immutability: after `build_source_registry`, no code mutates registry contents; every public return value is a deep copy or freshly assembled (§9.5, AC-24).
- Compact-by-default output: description 500 chars, `max_depth` 2 (max 8), `max_nodes` 200 (max 2000), search `limit` 10 (max 50), tool payload ≤ 200 × 1024 UTF-8 bytes (§14, §17.5).
- No `valid` key anywhere; the request checker's verdict is `compatible` (§16). `server` is always `null` and no Authorization/Cookie value is ever produced (§15).
- Backoff (`MIN_RETRY_INTERVAL = 900` s) applies only after a failed refresh, measured with an injectable monotonic clock (§11.4).
- `x-atlassian-oauth2-scopes` is a list of `{"scheme","scopes","state"}` objects in the real specs; `x-experimental` counts only when it is the bool `True` (§7.5).
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

Inputs the spec implies but that are easy to get wrong; each has a pinned test in the owning task.

1. **A parameter whose `schema` is itself a `$ref`** (e.g. `{"$ref": "#/components/parameters/X"}` at the parameter level *and* `schema: {"$ref": ...}` inside). Normalizer must resolve the parameter-level ref and keep the schema-level ref raw. → Task 3 `test_parameter_ref_resolved_schema_ref_kept`.
2. **`security: [{}]`** (an empty alternative, meaning "no auth is one option") — real Jira specs contain it. Must become `SecurityAlternative(requirements=())`, not be dropped. → Task 3 `test_empty_security_alternative_preserved`.
3. **Query value given as a Python `bool`** for an `integer` parameter (`True` is an `int` subclass). Must be a `type` error. → Task 12 `test_bool_is_not_integer`.
4. **Refresh where Phase 1 rewrote the cache but metadata.json write failed** (`MetadataPersistenceError`). Manager must treat it as a failed refresh, still read the new cache, and keep serving. → Task 14 `test_metadata_persistence_error_counts_as_failed_refresh`.
5. **Search query consisting only of stopwords/one-char tokens** (`"a to"`) → `empty_query` error, not an empty list. → Task 9 `test_stopword_only_query_is_empty_query_error`.

---

### Task 1: Fixtures, fixture generator, and layering test

**Files:**
- Create: `tests/fixtures/openapi/make_openapi_fixtures.py`
- Create: `tests/fixtures/openapi/jira-platform-openapi.json` (generated)
- Create: `tests/fixtures/openapi/jira-software-openapi.json` (generated)
- Create: `tests/fixtures/openapi/confluence-openapi.json` (generated)
- Create: `tests/fixtures/openapi/edge-cases-openapi.json` (hand-written)
- Create: `tests/fixtures/openapi/unsupported-dialect-openapi.json` (hand-written)
- Create: `tests/intelligence/__init__.py` (empty)
- Create: `tests/intelligence/helpers.py`
- Create: `tests/test_layering.py`
- Create: `tools/atlassian_docs/intelligence/__init__.py` (empty for now)

**Interfaces:**
- Produces: `tests/intelligence/helpers.py::load_fixture(name: str) -> dict` (deep-loads `tests/fixtures/openapi/{name}-openapi.json`), `FIXTURE_DIR: pathlib.Path`.
- Produces: layering test that later tasks must keep green.

- [ ] **Step 1: Run Phase 1 sync so the real specs are on disk**

Run: `python -m tools.atlassian_docs` (from repo root). Expected: three `[OK]`/`[UPDATED]` lines, exit 0, files under `.atlassian-docs/`.

- [ ] **Step 2: Write the generator**

`tests/fixtures/openapi/make_openapi_fixtures.py`:

```python
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
        "/rest/api/3/issue/createmeta",
        "/rest/api/3/search/jql",
        "/rest/api/3/expression/eval",            # deprecated operation
        "/rest/api/3/field/{fieldId}/context/defaultValue",  # deprecated + allOf-ish
    ],
    "jira-software": [
        "/rest/builds/0.1/bulk",                  # path-level parameters
        "/rest/agile/1.0/backlog/issue",
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
```

- [ ] **Step 3: Generate and inspect**

Run: `python tests/fixtures/openapi/make_openapi_fixtures.py`
Expected: three `[OK]` lines. Confirm with `python -c "import json;d=json.load(open('tests/fixtures/openapi/jira-platform-openapi.json'));print('IssueCreateMetadata' in d['components']['schemas'], 'MultipartFile' in d['components']['schemas'])"` → `True True`. Each file should be well under 1 MB; if jira-platform exceeds ~1.5 MB, remove `/rest/api/3/search/jql` from the selection and regenerate.

- [ ] **Step 4: Hand-write the edge-case fixture**

`tests/fixtures/openapi/edge-cases-openapi.json`:

```json
{
  "openapi": "3.1.0",
  "info": {"title": "Edge Cases", "version": "0"},
  "security": [{"basicAuth": []}],
  "paths": {
    "/things/{thingId}": {
      "parameters": [
        {"name": "thingId", "in": "path", "required": true, "schema": {"type": "string"}},
        {"name": "expand", "in": "query", "schema": {"type": "string", "enum": ["a", "b"]}}
      ],
      "get": {
        "summary": "Get thing",
        "tags": ["Things"],
        "parameters": [
          {"name": "expand", "in": "query", "schema": {"type": "string", "enum": ["x", "y"]}},
          {"$ref": "#/components/parameters/PageSize"},
          {"name": "session", "in": "cookie", "schema": {"type": "string"}}
        ],
        "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}}}
      },
      "post": {
        "operationId": "dupId",
        "summary": "Create thing",
        "tags": ["Things"],
        "security": [{}, {"OAuth2": ["write:thing"], "basicAuth": []}],
        "x-experimental": "true",
        "x-atlassian-oauth2-scopes": [{"scheme": "OAuth2", "scopes": ["write:thing", "read:thing"], "state": "Current"}, {"scheme": "OAuth2", "scopes": ["write:thing"], "state": "Beta"}],
        "requestBody": {"required": true, "content": {
          "application/json": {"schema": {"$ref": "#/components/schemas/Strict"}, "example": {"name": "drop me"}},
          "multipart/form-data": {"schema": {"type": "object"}}
        }},
        "responses": {"201": {"description": "created"}}
      },
      "delete": {
        "operationId": "dupId",
        "summary": "Delete thing",
        "tags": ["Things"],
        "x-experimental": true,
        "responses": {"204": {"description": "gone"}}
      }
    },
    "/merge": {
      "post": {
        "operationId": "mergeThing",
        "summary": "Merge with allOf conflict",
        "requestBody": {"required": true, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Merged"}}}},
        "responses": {"200": {"description": "ok"}}
      }
    },
    "/choice": {
      "post": {
        "operationId": "chooseThing",
        "summary": "oneOf body",
        "requestBody": {"required": false, "content": {"application/json": {"schema": {"oneOf": [{"$ref": "#/components/schemas/Strict"}, {"type": "string"}]}}}},
        "responses": {"200": {"description": "ok"}}
      }
    },
    "/external": {
      "get": {
        "operationId": "externalRef",
        "summary": "external and missing refs",
        "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"type": "object", "properties": {
          "ext": {"$ref": "https://example.com/other.json#/components/schemas/X"},
          "gone": {"$ref": "#/components/schemas/DoesNotExist"}
        }}}}}}
      }
    }
  },
  "components": {
    "parameters": {"PageSize": {"name": "limit", "in": "query", "required": true, "schema": {"type": "integer"}}},
    "schemas": {
      "Node": {"type": "object", "properties": {"id": {"type": "string"}, "children": {"type": "array", "items": {"$ref": "#/components/schemas/Node"}}, "parent": {"$ref": "#/components/schemas/Node"}}},
      "Strict": {"type": "object", "additionalProperties": false, "required": ["name"],
                 "properties": {"name": {"type": "string"}, "count": {"type": "integer"}, "kind": {"type": "string", "enum": ["a", "b"]}, "note": {"type": "string", "nullable": true}}},
      "Base": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}, "shared": {"type": "string"}}},
      "Merged": {"allOf": [{"$ref": "#/components/schemas/Base"}, {"type": "object", "required": ["extra"], "properties": {"extra": {"type": "integer"}, "shared": {"type": "integer"}}}]}
    },
    "securitySchemes": {"basicAuth": {"type": "http", "scheme": "basic"}, "OAuth2": {"type": "oauth2", "flows": {}}}
  }
}
```

`tests/fixtures/openapi/unsupported-dialect-openapi.json`:

```json
{"openapi": "4.0.0", "info": {"title": "Future", "version": "0"}, "paths": {"/x": {"get": {"operationId": "x", "responses": {"200": {"description": "ok"}}}}}}
```

- [ ] **Step 5: Write the helper and the layering test**

`tests/intelligence/helpers.py`:

```python
import json
import pathlib

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openapi"


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / f"{name}-openapi.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)
```

`tests/test_layering.py`:

```python
"""Spec §4 / §21.4: import direction and no-direct-HTTP rules, checked with ast."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "tools" / "atlassian_docs"
PHASE1 = ["__main__.py", "sources.py", "extractor.py", "sync.py", "storage.py"]
HTTP_MODULES = {"urllib.request", "http.client", "socket"}


def _imports(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            yield base
            for alias in node.names:
                yield f"{base}.{alias.name}" if base else alias.name


def _py_files(directory: pathlib.Path):
    return sorted(directory.rglob("*.py")) if directory.exists() else []


class TestLayering(unittest.TestCase):
    def test_phase1_does_not_import_phase2(self):
        for name in PHASE1:
            for imp in _imports(PKG / name):
                self.assertNotIn("intelligence", imp, f"{name} imports {imp}")
                self.assertNotIn("mcp", imp.split(".")[0], f"{name} imports {imp}")

    def test_intelligence_does_not_import_mcp_or_http(self):
        for path in _py_files(PKG / "intelligence"):
            for imp in _imports(path):
                self.assertFalse(imp == "mcp" or imp.startswith("mcp.") or ".mcp" in imp,
                                 f"{path.name} imports {imp}")
                self.assertNotIn(imp, HTTP_MODULES, f"{path.name} imports {imp}")

    def test_mcp_layer_does_not_import_http(self):
        for path in _py_files(PKG / "mcp"):
            for imp in _imports(path):
                self.assertNotIn(imp, HTTP_MODULES, f"{path.name} imports {imp}")

    def test_intelligence_is_stdlib_plus_phase1_only(self):
        import sys
        allowed_prefixes = ("tools.atlassian_docs", ".")
        for path in _py_files(PKG / "intelligence"):
            for imp in _imports(path):
                top = imp.split(".")[0]
                if imp.startswith(allowed_prefixes) or top in sys.stdlib_module_names:
                    continue
                self.fail(f"{path.name} imports non-stdlib module {imp}")
```

- [ ] **Step 6: Run the suite**

Run: `python -m unittest discover -s tests -t .`
Expected: 67 Phase 1 tests + 4 layering tests pass (the intelligence directory exists but is empty, so the loops are vacuous).

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/openapi tests/intelligence tests/test_layering.py tools/atlassian_docs/intelligence/__init__.py
git commit -m "test: add OpenAPI fixtures, generator, and layering test for Phase 2

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 2: Domain model (`models.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/models.py`
- Create: `tests/intelligence/test_models.py`

**Interfaces:**
- Produces (used by every later task):
  - `Parameter(name, location, required, description, schema, deprecated)`
  - `MediaType(content_type, schema)`
  - `RequestBody(required, description, content: tuple[MediaType, ...])`
  - `Response(status, description, content: tuple[MediaType, ...])`
  - `SecurityRequirement(scheme, scopes: tuple[str, ...])`
  - `SecurityAlternative(requirements: tuple[SecurityRequirement, ...])`
  - `Operation(source, key, operation_id, method, path, summary, description, tags, parameters, request_body, responses, security, deprecated, experimental, oauth2_scopes)`
  - `SourceProvenance(...)` — fields exactly as spec §12
  - `RefreshStatus(ttl_seconds, min_retry_interval_seconds, backoff_active, last_refresh_attempt_at, last_refresh_result, in_progress)`
  - every class has `to_dict() -> dict` returning deep-copied, JSON-serialisable data (tuples → lists).

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_models.py`:

```python
import copy
import json
import unittest

from tools.atlassian_docs.intelligence import models


def _op(**overrides):
    base = dict(
        source="jira-platform",
        key="jira-platform:POST:/rest/api/3/issue",
        operation_id="createIssue",
        method="POST",
        path="/rest/api/3/issue",
        summary="Create issue",
        description="desc",
        tags=("Issues",),
        parameters=(models.Parameter("x", "query", False, None, {"type": "string"}, False),),
        request_body=models.RequestBody(True, None, (models.MediaType("application/json", {"$ref": "#/components/schemas/A"}),)),
        responses=(models.Response("201", "created", ()),),
        security=(models.SecurityAlternative((models.SecurityRequirement("OAuth2", ("write:jira-work",)),)),),
        deprecated=False,
        experimental=False,
        oauth2_scopes=("write:jira-work",),
    )
    base.update(overrides)
    return models.Operation(**base)


class TestOperation(unittest.TestCase):
    def test_is_frozen(self):
        op = _op()
        with self.assertRaises(Exception):
            op.summary = "changed"  # type: ignore[misc]

    def test_to_dict_is_json_serialisable_and_uses_lists(self):
        d = _op().to_dict()
        json.dumps(d)
        self.assertEqual(d["tags"], ["Issues"])
        self.assertEqual(d["security"], [[{"scheme": "OAuth2", "scopes": ["write:jira-work"]}]])
        self.assertEqual(d["parameters"][0]["in"], "query")
        self.assertEqual(d["request_body"]["content"][0]["content_type"], "application/json")

    def test_to_dict_returns_copies_of_raw_schema(self):
        op = _op()
        d = op.to_dict()
        d["request_body"]["content"][0]["schema"]["$ref"] = "mutated"
        self.assertEqual(op.request_body.content[0].schema["$ref"], "#/components/schemas/A")

    def test_empty_security_alternative_serialises_to_empty_list(self):
        d = _op(security=(models.SecurityAlternative(()),)).to_dict()
        self.assertEqual(d["security"], [[]])


class TestProvenanceAndRefresh(unittest.TestCase):
    def test_provenance_to_dict_round_trip(self):
        p = models.SourceProvenance(
            source="confluence", status="fresh", reason=None,
            active_spec_sha256="abc", active_openapi_version="3.0.3", active_api_version="v2",
            operation_count=3, schema_count=2,
            observed_cache_sha256="abc", metadata_sha256="abc",
            resolved_documentation_url="https://developer.atlassian.com/cloud/confluence/rest/v2/",
            last_checked="2026-09-28T00:00:00Z", last_updated="2026-09-28T00:00:00Z",
            candidate=None, warnings=({"kind": "x"},),
        )
        d = p.to_dict()
        self.assertEqual(d["status"], "fresh")
        self.assertEqual(d["warnings"], [{"kind": "x"}])
        d["warnings"][0]["kind"] = "mutated"
        self.assertEqual(p.warnings[0]["kind"], "x")

    def test_refresh_status_to_dict(self):
        r = models.RefreshStatus(86400, 900, False, None, None, False)
        self.assertEqual(r.to_dict()["ttl_seconds"], 86400)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.intelligence.test_models -v`
Expected: ImportError / AttributeError on `models`.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/models.py`:

```python
"""Frozen domain model for normalised OpenAPI operations (spec §6, §12).

Raw JSON-schema fragments are kept as plain dicts owned by the registry;
``to_dict`` always deep-copies them so callers can never mutate registry
state through a returned value (spec §9.5).
"""
import copy
import dataclasses
from dataclasses import dataclass
from typing import Any, Mapping, Optional


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


@dataclass(frozen=True)
class Parameter:
    name: str
    location: str  # "path" | "query" | "header" | "cookie"
    required: bool
    description: Optional[str]
    schema: Optional[dict]
    deprecated: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name, "in": self.location, "required": self.required,
            "description": self.description, "schema": _copy(self.schema),
            "deprecated": self.deprecated,
        }


@dataclass(frozen=True)
class MediaType:
    content_type: str
    schema: Optional[dict]

    def to_dict(self) -> dict:
        return {"content_type": self.content_type, "schema": _copy(self.schema)}


@dataclass(frozen=True)
class RequestBody:
    required: bool
    description: Optional[str]
    content: tuple  # tuple[MediaType, ...]

    def to_dict(self) -> dict:
        return {"required": self.required, "description": self.description,
                "content": [m.to_dict() for m in self.content]}


@dataclass(frozen=True)
class Response:
    status: str
    description: Optional[str]
    content: tuple  # tuple[MediaType, ...]

    def to_dict(self) -> dict:
        return {"status": self.status, "description": self.description,
                "content": [m.to_dict() for m in self.content]}


@dataclass(frozen=True)
class SecurityRequirement:
    scheme: str
    scopes: tuple  # tuple[str, ...]

    def to_dict(self) -> dict:
        return {"scheme": self.scheme, "scopes": list(self.scopes)}


@dataclass(frozen=True)
class SecurityAlternative:
    requirements: tuple  # tuple[SecurityRequirement, ...]  (AND)

    def to_dict(self) -> list:
        return [r.to_dict() for r in self.requirements]


@dataclass(frozen=True)
class Operation:
    source: str
    key: str
    operation_id: Optional[str]
    method: str
    path: str
    summary: Optional[str]
    description: Optional[str]
    tags: tuple
    parameters: tuple
    request_body: Optional[RequestBody]
    responses: tuple
    security: tuple  # tuple[SecurityAlternative, ...]  (OR)
    deprecated: bool
    experimental: bool
    oauth2_scopes: tuple

    def to_dict(self) -> dict:
        return {
            "source": self.source, "key": self.key, "operation_id": self.operation_id,
            "method": self.method, "path": self.path, "summary": self.summary,
            "description": self.description, "tags": list(self.tags),
            "parameters": [p.to_dict() for p in self.parameters],
            "request_body": self.request_body.to_dict() if self.request_body else None,
            "responses": [r.to_dict() for r in self.responses],
            "security": [alt.to_dict() for alt in self.security],
            "deprecated": self.deprecated, "experimental": self.experimental,
            "oauth2_scopes": list(self.oauth2_scopes),
        }


@dataclass(frozen=True)
class SourceProvenance:
    source: str
    status: str  # "fresh" | "stale" | "unavailable"
    reason: Optional[str]
    active_spec_sha256: Optional[str]
    active_openapi_version: Optional[str]
    active_api_version: Optional[str]
    operation_count: int
    schema_count: int
    observed_cache_sha256: Optional[str]
    metadata_sha256: Optional[str]
    resolved_documentation_url: Optional[str]
    last_checked: Optional[str]
    last_updated: Optional[str]
    candidate: Optional[dict]
    warnings: tuple

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["warnings"] = [_copy(w) for w in self.warnings]
        d["candidate"] = _copy(self.candidate)
        return d


@dataclass(frozen=True)
class RefreshStatus:
    ttl_seconds: int
    min_retry_interval_seconds: int
    backoff_active: bool
    last_refresh_attempt_at: Optional[str]
    last_refresh_result: Optional[dict]
    in_progress: bool

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["last_refresh_result"] = _copy(self.last_refresh_result)
        return d
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.intelligence.test_models -v` → all PASS. Then `python -m unittest discover -s tests -t .` → layering still green.

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/models.py tests/intelligence/test_models.py
git commit -m "feat(intelligence): add frozen domain model with copying to_dict

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Normalizer (`normalizer.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/normalizer.py`
- Create: `tests/intelligence/test_normalizer.py`

**Interfaces:**
- Consumes: Task 2 models; `tests/intelligence/helpers.load_fixture`.
- Produces:
  - `HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")`
  - `class NormalizationError(Exception)`
  - `@dataclass(frozen=True) class NormalizedSpec: source, openapi_version, title, operations: tuple[Operation, ...], schemas, parameters, request_bodies, responses, security_schemes: dict, tags: tuple[str, ...], warnings: tuple[dict, ...], normalization_partial: bool`
  - `strip_examples(node) -> node` (deep copy without `example`/`examples` keys)
  - `normalize_openapi(source_name: str, spec: dict) -> NormalizedSpec`

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_normalizer.py`:

```python
import unittest

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs.intelligence import normalizer


def _find(ns, method, path):
    for op in ns.operations:
        if op.method == method and op.path == path:
            return op
    raise AssertionError(f"{method} {path} not found")


class TestRealFixtures(unittest.TestCase):
    def test_all_three_fixtures_normalize(self):
        for name in ("jira-platform", "jira-software", "confluence"):
            ns = normalizer.normalize_openapi(name, load_fixture(name))
            self.assertGreater(len(ns.operations), 0, name)
            self.assertEqual(ns.source, name)
            self.assertFalse(ns.normalization_partial, ns.warnings)

    def test_canonical_key_and_upper_method(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        op = _find(ns, "POST", "/rest/api/3/issue/{issueIdOrKey}/attachments")
        self.assertEqual(op.key, "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")
        self.assertEqual(op.operation_id, "addAttachment")
        self.assertTrue(op.parameters[0].required)          # path param forced required
        self.assertEqual(op.request_body.content[0].content_type, "multipart/form-data")

    def test_oauth2_scopes_flattened_from_object_array(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        op = _find(ns, "POST", "/rest/api/3/issue")
        self.assertIn("write:jira-work", op.oauth2_scopes)
        self.assertEqual(len(op.oauth2_scopes), len(set(op.oauth2_scopes)))

    def test_path_level_parameters_merged_for_jira_software(self):
        ns = normalizer.normalize_openapi("jira-software", load_fixture("jira-software"))
        op = _find(ns, "POST", "/rest/builds/0.1/bulk")
        self.assertTrue(any(p.location == "header" for p in op.parameters))

    def test_confluence_requestbody_ref_resolved(self):
        ns = normalizer.normalize_openapi("confluence", load_fixture("confluence"))
        op = _find(ns, "POST", "/blogposts")
        self.assertIsNotNone(op.request_body)
        self.assertTrue(op.request_body.content)

    def test_examples_are_stripped_everywhere(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        import json
        blob = json.dumps([op.to_dict() for op in ns.operations]) + json.dumps(ns.schemas)
        self.assertNotIn('"example"', blob)
        self.assertNotIn('"examples"', blob)

    def test_deterministic(self):
        spec = load_fixture("confluence")
        a = normalizer.normalize_openapi("confluence", spec)
        b = normalizer.normalize_openapi("confluence", spec)
        self.assertEqual([o.key for o in a.operations], [o.key for o in b.operations])
        self.assertEqual(a.tags, b.tags)


class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))

    def test_operation_without_operation_id(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        self.assertIsNone(op.operation_id)

    def test_operation_level_overrides_path_level_by_name_and_location(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        expands = [p for p in op.parameters if p.name == "expand"]
        self.assertEqual(len(expands), 1)
        self.assertEqual(expands[0].schema["enum"], ["x", "y"])
        self.assertEqual([p.name for p in op.parameters][:2], ["thingId", "expand"])  # path-level order first

    def test_parameter_ref_resolved_schema_ref_kept(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        limit = [p for p in op.parameters if p.name == "limit"][0]
        self.assertTrue(limit.required)
        node = _find(self.ns, "GET", "/things/{thingId}").responses[0].content[0].schema
        self.assertEqual(node, {"$ref": "#/components/schemas/Node"})  # schema-level ref stays raw

    def test_cookie_parameter_preserved(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        self.assertTrue(any(p.location == "cookie" for p in op.parameters))

    def test_empty_security_alternative_preserved(self):
        op = _find(self.ns, "POST", "/things/{thingId}")
        self.assertEqual(len(op.security), 2)
        self.assertEqual(op.security[0].requirements, ())
        and_part = op.security[1].requirements
        self.assertEqual([r.scheme for r in and_part], ["OAuth2", "basicAuth"])
        self.assertEqual(and_part[0].scopes, ("write:thing",))

    def test_top_level_security_inherited(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        self.assertEqual(op.security[0].requirements[0].scheme, "basicAuth")

    def test_experimental_only_when_bool_true(self):
        self.assertFalse(_find(self.ns, "POST", "/things/{thingId}").experimental)
        self.assertTrue(_find(self.ns, "DELETE", "/things/{thingId}").experimental)
        self.assertTrue(any(w["kind"] == "experimental_value_ignored" for w in self.ns.warnings))

    def test_oauth2_scopes_deduped_in_order(self):
        op = _find(self.ns, "POST", "/things/{thingId}")
        self.assertEqual(op.oauth2_scopes, ("write:thing", "read:thing"))

    def test_example_inside_media_type_dropped(self):
        op = _find(self.ns, "POST", "/things/{thingId}")
        self.assertEqual(op.request_body.content[0].schema, {"$ref": "#/components/schemas/Strict"})

    def test_duplicate_operation_ids_both_kept(self):
        self.assertEqual(sum(1 for o in self.ns.operations if o.operation_id == "dupId"), 2)


class TestFailures(unittest.TestCase):
    def test_paths_not_dict_raises(self):
        with self.assertRaises(normalizer.NormalizationError):
            normalizer.normalize_openapi("x", {"openapi": "3.0.0", "info": {}, "paths": []})

    def test_broken_operation_is_skipped_and_flagged(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {
            "/ok": {"get": {"responses": {}}},
            "/bad": {"get": {"parameters": "not-a-list", "responses": {}}},
        }}
        ns = normalizer.normalize_openapi("x", spec)
        self.assertEqual([o.path for o in ns.operations], ["/ok"])
        self.assertTrue(ns.normalization_partial)
        self.assertEqual(ns.warnings[0]["kind"], "operation_skipped")

    def test_path_item_ref_is_skipped_with_warning(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {"/r": {"$ref": "#/x"}}}
        ns = normalizer.normalize_openapi("x", spec)
        self.assertEqual(ns.operations, ())
        self.assertEqual(ns.warnings[0]["kind"], "path_item_ref_unsupported")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.intelligence.test_normalizer` → ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/normalizer.py`:

```python
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


def strip_examples(node: Any) -> Any:
    """Deep copy of node with every `example`/`examples` key removed."""
    if isinstance(node, dict):
        return {k: strip_examples(v) for k, v in node.items() if k not in _EXAMPLE_KEYS}
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
        schemas=strip_examples(components["schemas"]),
        parameters=strip_examples(components["parameters"]),
        request_bodies=strip_examples(components["requestBodies"]),
        responses=strip_examples(components["responses"]),
        security_schemes=copy.deepcopy(components["securitySchemes"]),
        tags=tuple(tags),
        warnings=tuple(warnings),
        normalization_partial=partial,
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.intelligence.test_normalizer -v` → all PASS. If `test_path_level_parameters_merged_for_jira_software` fails because the fixture's `/rest/builds/0.1/bulk` has no header param, inspect `tests/fixtures/openapi/jira-software-openapi.json` and assert on whichever `in` value its path-level parameters actually use (they exist — the generator selected that path for this reason).

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/normalizer.py tests/intelligence/test_normalizer.py
git commit -m "feat(intelligence): normalize OpenAPI into frozen operations

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 4: `$ref` resolver (`schemas.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/schemas.py`
- Create: `tests/intelligence/test_schemas.py`

**Interfaces:**
- Consumes: `NormalizedSpec` (Task 3) — the resolver only needs an object with `.schemas/.parameters/.request_bodies/.responses` dicts; `SourceRegistry` (Task 6) exposes the same attribute names, so this works for both.
- Produces:
  - `parse_local_ref(ref: str) -> tuple[str, str] | None` → `("schemas", "Node")` for `#/components/schemas/Node`; `None` for unsupported forms.
  - `lookup_ref(components, ref: str) -> tuple[dict | None, str]` → `(node, "ok")`, `(None, "missing")`, `(None, "external")`.
  - `@dataclass(frozen=True) class ResolvedSchema: schema: dict, truncated: bool, unresolved: tuple[str, ...], cycles: tuple[str, ...], node_count: int`
  - `resolve(node, components, *, max_depth=2, max_nodes=200) -> ResolvedSchema`
  - `collect_local_ref_names(node, *, max_depth=6) -> tuple[str, ...]` (sorted unique last segments; used by the search index)
  - `MAX_DEPTH_LIMIT = 8`, `MAX_NODES_LIMIT = 2000`

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_schemas.py`:

```python
import unittest

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs.intelligence import normalizer, schemas


class TestParseAndLookup(unittest.TestCase):
    def setUp(self):
        self.ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))

    def test_parse_local_ref(self):
        self.assertEqual(schemas.parse_local_ref("#/components/schemas/Node"), ("schemas", "Node"))
        self.assertEqual(schemas.parse_local_ref("#/components/requestBodies/X"), ("requestBodies", "X"))
        self.assertIsNone(schemas.parse_local_ref("https://x/y.json#/components/schemas/A"))
        self.assertIsNone(schemas.parse_local_ref("#/paths/~1x"))

    def test_lookup(self):
        node, status = schemas.lookup_ref(self.ns, "#/components/schemas/Node")
        self.assertEqual(status, "ok"); self.assertEqual(node["type"], "object")
        self.assertEqual(schemas.lookup_ref(self.ns, "#/components/schemas/Nope"), (None, "missing"))
        self.assertEqual(schemas.lookup_ref(self.ns, "file://a.json#/x"), (None, "external"))


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))

    def test_single_ref_inlined(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Strict"}, self.ns, max_depth=1)
        self.assertEqual(r.schema["required"], ["name"])
        self.assertFalse(r.truncated); self.assertEqual(r.unresolved, ())

    def test_cycle_marked_not_infinite(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Node"}, self.ns, max_depth=8)
        parent = r.schema["properties"]["parent"]
        self.assertEqual(parent, {"$ref": "#/components/schemas/Node", "_cycle": True})
        self.assertIn("#/components/schemas/Node", r.cycles)

    def test_depth_truncation(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Merged"}, self.ns, max_depth=1)
        base = r.schema["allOf"][0]
        self.assertEqual(base["_truncated"], "depth"); self.assertTrue(r.truncated)

    def test_missing_and_external_markers(self):
        node = {"type": "object", "properties": {
            "ext": {"$ref": "https://example.com/other.json#/components/schemas/X"},
            "gone": {"$ref": "#/components/schemas/DoesNotExist"}}}
        r = schemas.resolve(node, self.ns)
        self.assertEqual(r.schema["properties"]["ext"]["_unresolved"], "external")
        self.assertEqual(r.schema["properties"]["gone"]["_unresolved"], "missing")
        self.assertEqual(len(r.unresolved), 2)

    def test_node_budget(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Node"}, self.ns, max_depth=8, max_nodes=1)
        self.assertTrue(r.truncated)
        self.assertLessEqual(r.node_count, 2)

    def test_input_not_mutated_and_output_independent(self):
        node = {"$ref": "#/components/schemas/Strict"}
        r = schemas.resolve(node, self.ns, max_depth=1)
        self.assertEqual(node, {"$ref": "#/components/schemas/Strict"})
        r.schema["required"].append("mutated")
        self.assertEqual(self.ns.schemas["Strict"]["required"], ["name"])

    def test_limits_enforced(self):
        with self.assertRaises(ValueError):
            schemas.resolve({}, self.ns, max_depth=9)
        with self.assertRaises(ValueError):
            schemas.resolve({}, self.ns, max_nodes=2001)


class TestCollectRefNames(unittest.TestCase):
    def test_collects_nested_refs_without_resolving(self):
        node = {"type": "array", "items": {"$ref": "#/components/schemas/MultipartFile"},
                "allOf": [{"properties": {"a": {"$ref": "#/components/schemas/Inner"}}}],
                "x": {"$ref": "https://ext/#/components/schemas/Ext"}}
        self.assertEqual(schemas.collect_local_ref_names(node), ("Inner", "MultipartFile"))

    def test_none_and_scalars(self):
        self.assertEqual(schemas.collect_local_ref_names(None), ())
```

- [ ] **Step 2: Run to verify failure** — `python -m unittest tests.intelligence.test_schemas` → ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/schemas.py`:

```python
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
        if key in _RECURSE_KEYS or key == "properties":
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
                    walk(n[key], depth + 1)
    walk(node, 0)
    return tuple(sorted(found))
```

- [ ] **Step 4: Run tests** — `python -m unittest tests.intelligence.test_schemas -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/schemas.py tests/intelligence/test_schemas.py
git commit -m "feat(intelligence): bounded local \$ref resolution with cycle and budget markers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Tokenizer and search index (`search.py`, part 1)

**Files:**
- Create: `tools/atlassian_docs/intelligence/search.py`
- Create: `tests/intelligence/test_search.py` (tokenizer/index tests; scoring tests added in Task 9)

**Interfaces:**
- Consumes: `Operation` (Task 2), `schemas.collect_local_ref_names` (Task 4).
- Produces:
  - `STOPWORDS: frozenset[str]`
  - `tokenize(text: str | None) -> frozenset[str]`
  - `FIELD_WEIGHTS = {"operation_id": 5, "summary": 4, "tags": 3, "path": 3, "schema_names": 2, "method": 1, "description": 1}`
  - `@dataclass(frozen=True) class IndexEntry: key: str, fields: Mapping[str, frozenset]`
  - `@dataclass(frozen=True) class SearchIndex: entries: tuple[IndexEntry, ...]`
  - `build_index(operations: tuple[Operation, ...]) -> SearchIndex`

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_search.py`:

```python
import unittest

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs.intelligence import normalizer, search


class TestTokenize(unittest.TestCase):
    def test_camel_case_and_path(self):
        self.assertEqual(search.tokenize("issueIdOrKey"), frozenset({"issue", "id", "key"}))  # "or" is a stopword
        self.assertTrue({"rest", "api", "issue", "id", "key", "attachments", "attachment"}
                        <= search.tokenize("/rest/api/3/issue/{issueIdOrKey}/attachments"))

    def test_acronyms_and_digits(self):
        self.assertEqual(search.tokenize("OAuth2"), frozenset({"oauth2"}))
        self.assertEqual(search.tokenize("JQLQuery"), frozenset({"jql", "query"}))
        self.assertEqual(search.tokenize("IssueCreateMetadata"), frozenset({"issue", "create", "metadata"}))

    def test_plural_variants(self):
        self.assertEqual(search.tokenize("statuses"), frozenset({"statuses", "statuse"}))
        self.assertEqual(search.tokenize("status"), frozenset({"status"}))
        self.assertEqual(search.tokenize("process"), frozenset({"process"}))
        self.assertEqual(search.tokenize("analysis"), frozenset({"analysis"}))
        self.assertEqual(search.tokenize("issues"), frozenset({"issues", "issue"}))

    def test_stopwords_short_tokens_and_dedupe(self):
        self.assertEqual(search.tokenize("a to the x issue issue"), frozenset({"issue"}))
        self.assertEqual(search.tokenize(""), frozenset())
        self.assertEqual(search.tokenize(None), frozenset())

    def test_snake_and_kebab(self):
        self.assertEqual(search.tokenize("create_issue"), frozenset({"create", "issue"}))
        self.assertEqual(search.tokenize("jira-platform"), frozenset({"jira", "platform"}))


class TestBuildIndex(unittest.TestCase):
    def test_index_fields_for_attachment_operation(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        index = search.build_index(ns.operations)
        entry = next(e for e in index.entries if e.key.endswith("/attachments"))
        self.assertIn("attachment", entry.fields["operation_id"])
        self.assertIn("multipartfile", entry.fields["schema_names"])
        self.assertEqual(entry.fields["method"], frozenset({"post"}))
        self.assertIn("issue", entry.fields["path"])

    def test_nested_schema_names_indexed(self):
        ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))
        index = search.build_index(ns.operations)
        entry = next(e for e in index.entries if e.key == "edge:POST:/things/{thingId}")
        self.assertIn("strict", entry.fields["schema_names"])
        merge = next(e for e in index.entries if e.key == "edge:POST:/merge")
        self.assertIn("merged", merge.fields["schema_names"])  # body is a bare $ref; no resolution (spec §13.2)
```

- [ ] **Step 2: Run to verify failure** — `python -m unittest tests.intelligence.test_search` → ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/search.py` (part 1 — Task 9 appends `search_operations`):

```python
"""Weighted lexical operation search: tokenizer + prebuilt index (spec §13)."""
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from . import schemas

STOPWORDS = frozenset("a an the to of for in on at and or with by from is are be this that".split())
FIELD_WEIGHTS = {"operation_id": 5, "summary": 4, "tags": 3, "path": 3,
                 "schema_names": 2, "method": 1, "description": 1}
DESCRIPTION_INDEX_CHARS = 1000
_CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])")        # fooBar -> foo Bar
_CAMEL_2 = re.compile(r"([A-Z]{2,})([A-Z][a-z])")  # JQLQuery -> JQL Query (2+ so OAuth2 stays whole)
_SPLIT = re.compile(r"[^a-z0-9]+")


def tokenize(text: Optional[str]) -> frozenset:
    if not text:
        return frozenset()
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", text)).lower()
    out = set()
    for tok in _SPLIT.split(text):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        out.add(tok)
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
            out.add(tok[:-1])
    return frozenset(out)


@dataclass(frozen=True)
class IndexEntry:
    key: str
    fields: Mapping[str, frozenset]


@dataclass(frozen=True)
class SearchIndex:
    entries: tuple


def _schema_names(op: Any) -> frozenset:
    names: set = set()
    if op.request_body:
        for media in op.request_body.content:
            names.update(schemas.collect_local_ref_names(media.schema))
    for resp in op.responses:
        for media in resp.content:
            names.update(schemas.collect_local_ref_names(media.schema))
    for p in op.parameters:
        names.update(schemas.collect_local_ref_names(p.schema))
    toks: set = set()
    for n in names:
        toks.add(n.lower())          # exact type name, e.g. "issuecreatemetadata"
        toks |= tokenize(n)          # split parts, e.g. "issue", "create", "metadata"
    return frozenset(toks)


def build_index(operations: tuple) -> SearchIndex:
    entries = []
    for op in operations:
        fields = {
            "operation_id": tokenize(op.operation_id),
            "summary": tokenize(op.summary),
            "tags": frozenset().union(*(tokenize(t) for t in op.tags)) if op.tags else frozenset(),
            "path": tokenize(op.path),
            "schema_names": _schema_names(op),
            "method": frozenset({op.method.lower()}),
            "description": tokenize((op.description or "")[:DESCRIPTION_INDEX_CHARS]),
        }
        entries.append(IndexEntry(op.key, fields))
    return SearchIndex(tuple(entries))
```

- [ ] **Step 4: Run tests** — `python -m unittest tests.intelligence.test_search -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/search.py tests/intelligence/test_search.py
git commit -m "feat(intelligence): lexical tokenizer and per-field search index

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Registry and ActiveState (`registry.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/registry.py`
- Create: `tests/intelligence/test_registry.py`
- Modify: `tests/intelligence/helpers.py` (add `build_source_registry_from_fixture`)

**Interfaces:**
- Consumes: `NormalizedSpec` (Task 3), `search.build_index` (Task 5), `models.SourceProvenance`, `models.RefreshStatus`, `storage.sha256_of_spec`, `sources.SOURCES`.
- Produces:
  - `@dataclass(frozen=True) class SourceRegistry`: fields per spec §9.2 (`source, openapi_version, title, operations, operations_by_key, keys_by_operation_id, schemas, parameters, request_bodies, responses, security_schemes, tags, spec_sha256, warnings, normalization_partial, search_index`).
  - `build_source_registry(normalized: NormalizedSpec, spec_sha256: str) -> SourceRegistry`
  - `compute_fingerprint(shas: Mapping[str, str | None]) -> str` (over `sorted(sources.SOURCES)`, missing → `"-"`)
  - `@dataclass(frozen=True) class Registry: sources: Mapping[str, SourceRegistry], fingerprint: str, built_at: str` with methods `get_operation(key) -> Operation | None`, `find_by_operation_id(source: str | None, operation_id: str) -> tuple[str, ...]`, `list_operations(source=None, method=None, tag=None, include_deprecated=True) -> tuple[Operation, ...]`, `list_sources() -> tuple[str, ...]`, `list_tags(source) -> tuple[str, ...]`, `get_schema(source, name) -> dict | None` (deep copy), `components(source) -> SourceRegistry | None`.
  - `build_registry(sources: Mapping[str, SourceRegistry], built_at: str) -> Registry`
  - `@dataclass(frozen=True) class ActiveState: registry: Registry, provenance: Mapping[str, SourceProvenance], refresh: RefreshStatus`
  - `class RegistryUnavailableError(Exception)`

- [ ] **Step 1: Add the helper**

Append to `tests/intelligence/helpers.py`:

```python
def build_source_registry_from_fixture(name: str, source: str | None = None):
    """normalize + build for one fixture; returns SourceRegistry."""
    from tools.atlassian_docs import storage
    from tools.atlassian_docs.intelligence import normalizer, registry
    spec = load_fixture(name)
    ns = normalizer.normalize_openapi(source or name, spec)
    return registry.build_source_registry(ns, storage.sha256_of_spec(spec))
```

- [ ] **Step 2: Write the failing tests**

`tests/intelligence/test_registry.py`:

```python
import unittest

from tests.intelligence.helpers import build_source_registry_from_fixture
from tools.atlassian_docs.intelligence import registry


def _reg(*names):
    srcs = {n: build_source_registry_from_fixture(n) for n in names}
    return registry.build_registry(srcs, "2026-09-28T00:00:00Z")


class TestSourceRegistry(unittest.TestCase):
    def test_lookup_maps_and_index(self):
        sr = build_source_registry_from_fixture("jira-platform")
        key = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"
        self.assertEqual(sr.operations_by_key[key].operation_id, "addAttachment")
        self.assertEqual(sr.keys_by_operation_id["addAttachment"], (key,))
        self.assertEqual(len(sr.search_index.entries), len(sr.operations))
        self.assertEqual(len(sr.spec_sha256), 64)

    def test_duplicate_operation_ids_listed(self):
        sr = build_source_registry_from_fixture("edge-cases", source="edge")
        self.assertEqual(len(sr.keys_by_operation_id["dupId"]), 2)


class TestRegistry(unittest.TestCase):
    def test_fingerprint_covers_all_configured_sources(self):
        a = registry.compute_fingerprint({"jira-platform": "x", "jira-software": None, "confluence": "y"})
        b = registry.compute_fingerprint({"jira-platform": "x", "confluence": "y"})
        c = registry.compute_fingerprint({"jira-platform": "x", "confluence": "z"})
        self.assertEqual(a, b); self.assertNotEqual(a, c); self.assertEqual(len(a), 64)

    def test_find_by_operation_id_across_sources(self):
        reg = _reg("jira-platform", "confluence")
        self.assertEqual(len(reg.find_by_operation_id(None, "addAttachment")), 1)
        self.assertEqual(reg.find_by_operation_id("confluence", "addAttachment"), ())
        self.assertEqual(reg.list_sources(), ("confluence", "jira-platform"))

    def test_list_operations_filters(self):
        reg = _reg("jira-platform")
        posts = reg.list_operations(method="post")
        self.assertTrue(posts and all(o.method == "POST" for o in posts))
        self.assertTrue(all(not o.deprecated for o in reg.list_operations(include_deprecated=False)))
        self.assertIn("Issues", reg.list_tags("jira-platform"))

    def test_get_schema_returns_copy(self):
        reg = _reg("jira-platform")
        s = reg.get_schema("jira-platform", "MultipartFile")
        s["mutated"] = True
        self.assertNotIn("mutated", reg.get_schema("jira-platform", "MultipartFile"))
        self.assertIsNone(reg.get_schema("jira-platform", "Nope"))
        self.assertIsNone(reg.get_schema("nope", "MultipartFile"))

    def test_registry_with_missing_source_still_builds(self):
        reg = _reg("confluence")
        self.assertIsNone(reg.get_operation("jira-platform:POST:/rest/api/3/issue"))
        self.assertEqual(reg.fingerprint, registry.compute_fingerprint({"confluence": reg.sources["confluence"].spec_sha256}))
```

- [ ] **Step 3: Run to verify failure** — ImportError.

- [ ] **Step 4: Implement**

`tools/atlassian_docs/intelligence/registry.py`:

```python
"""Immutable per-source and composite registries plus the ActiveState snapshot (spec §9, §11.1)."""
import copy
import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from .. import sources
from . import search
from .models import Operation, RefreshStatus, SourceProvenance
from .normalizer import NormalizedSpec


class RegistryUnavailableError(Exception):
    """No source could be loaded at startup (spec §11.2)."""


@dataclass(frozen=True)
class SourceRegistry:
    source: str
    openapi_version: str
    title: Optional[str]
    operations: tuple
    operations_by_key: Mapping[str, Operation]
    keys_by_operation_id: Mapping[str, tuple]
    schemas: Mapping[str, dict]
    parameters: Mapping[str, dict]
    request_bodies: Mapping[str, dict]
    responses: Mapping[str, dict]
    security_schemes: Mapping[str, dict]
    tags: tuple
    spec_sha256: str
    warnings: tuple
    normalization_partial: bool
    search_index: search.SearchIndex


def build_source_registry(normalized: NormalizedSpec, spec_sha256: str) -> SourceRegistry:
    by_key = {}
    by_op_id: dict = {}
    for op in normalized.operations:
        by_key[op.key] = op
        if op.operation_id:
            by_op_id.setdefault(op.operation_id, []).append(op.key)
    return SourceRegistry(
        source=normalized.source, openapi_version=normalized.openapi_version, title=normalized.title,
        operations=normalized.operations,
        operations_by_key=MappingProxyType(by_key),
        keys_by_operation_id=MappingProxyType({k: tuple(v) for k, v in by_op_id.items()}),
        schemas=MappingProxyType(normalized.schemas), parameters=MappingProxyType(normalized.parameters),
        request_bodies=MappingProxyType(normalized.request_bodies), responses=MappingProxyType(normalized.responses),
        security_schemes=MappingProxyType(normalized.security_schemes),
        tags=normalized.tags, spec_sha256=spec_sha256, warnings=normalized.warnings,
        normalization_partial=normalized.normalization_partial,
        search_index=search.build_index(normalized.operations),
    )


def compute_fingerprint(shas: Mapping[str, Optional[str]]) -> str:
    lines = [f"{name}:{shas.get(name) or '-'}" for name in sorted(sources.SOURCES)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Registry:
    sources: Mapping[str, SourceRegistry]
    fingerprint: str
    built_at: str

    def components(self, source: str) -> Optional[SourceRegistry]:
        return self.sources.get(source)

    def get_operation(self, key: str) -> Optional[Operation]:
        source = key.split(":", 1)[0]
        sr = self.sources.get(source)
        return sr.operations_by_key.get(key) if sr else None

    def find_by_operation_id(self, source: Optional[str], operation_id: str) -> tuple:
        names = [source] if source else sorted(self.sources)
        keys: list = []
        for name in names:
            sr = self.sources.get(name)
            if sr:
                keys.extend(sr.keys_by_operation_id.get(operation_id, ()))
        return tuple(keys)

    def list_operations(self, source=None, method=None, tag=None, include_deprecated=True) -> tuple:
        out = []
        for name in sorted(self.sources):
            if source and name != source:
                continue
            for op in self.sources[name].operations:
                if method and op.method != method.upper():
                    continue
                if tag and tag not in op.tags:
                    continue
                if not include_deprecated and op.deprecated:
                    continue
                out.append(op)
        return tuple(out)

    def list_sources(self) -> tuple:
        return tuple(sorted(self.sources))

    def list_tags(self, source: str) -> tuple:
        sr = self.sources.get(source)
        return sr.tags if sr else ()

    def get_schema(self, source: str, name: str) -> Optional[dict]:
        sr = self.sources.get(source)
        node = sr.schemas.get(name) if sr else None
        return copy.deepcopy(node) if isinstance(node, dict) else None


def build_registry(source_registries: Mapping[str, SourceRegistry], built_at: str) -> Registry:
    frozen = MappingProxyType(dict(source_registries))
    return Registry(sources=frozen,
                    fingerprint=compute_fingerprint({n: sr.spec_sha256 for n, sr in frozen.items()}),
                    built_at=built_at)


@dataclass(frozen=True)
class ActiveState:
    registry: Registry
    provenance: Mapping[str, SourceProvenance]
    refresh: RefreshStatus
```

- [ ] **Step 5: Run tests** — `python -m unittest tests.intelligence.test_registry -v` → PASS; full suite green.

- [ ] **Step 6: Commit**

```bash
git add tools/atlassian_docs/intelligence/registry.py tests/intelligence/test_registry.py tests/intelligence/helpers.py
git commit -m "feat(intelligence): source/composite registry, fingerprint, ActiveState

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 7: Compatibility gate and integrity check (`gate.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/gate.py`
- Create: `tests/intelligence/test_gate.py`

**Interfaces:**
- Consumes: `extractor.is_openapi_candidate`, `normalizer.normalize_openapi/NormalizationError/HTTP_METHODS`, `registry.build_source_registry`, `storage.sha256_of_spec`.
- Produces:
  - `@dataclass(frozen=True) class GateResult: ok: bool, code: str | None, message: str`
  - `check_compatibility(spec) -> GateResult` — codes `incompatible_dialect`, `invalid_structure`, `no_operations`
  - `check_integrity(source_registry) -> GateResult` — codes `empty_registry`, `duplicate_keys`
  - `build_candidate(source_name: str, spec) -> tuple[SourceRegistry | None, GateResult]` — gate → `invalid_components` check on the raw spec → normalize (catching `NormalizationError` → `normalization_failed`) → build → integrity.

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_gate.py`:

```python
import unittest

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs.intelligence import gate


class TestCompatibility(unittest.TestCase):
    def test_supported_dialects(self):
        for name in ("jira-platform", "confluence", "edge-cases"):
            self.assertTrue(gate.check_compatibility(load_fixture(name)).ok, name)

    def test_unsupported_dialect(self):
        r = gate.check_compatibility(load_fixture("unsupported-dialect"))
        self.assertFalse(r.ok); self.assertEqual(r.code, "incompatible_dialect")

    def test_invalid_structure(self):
        r = gate.check_compatibility({"openapi": "3.0.0", "paths": {}})   # no info
        self.assertEqual(r.code, "invalid_structure")

    def test_no_operations(self):
        r = gate.check_compatibility({"openapi": "3.0.0", "info": {}, "paths": {"/x": {"parameters": []}}})
        self.assertEqual(r.code, "no_operations")


class TestBuildCandidate(unittest.TestCase):
    def test_success(self):
        sr, result = gate.build_candidate("confluence", load_fixture("confluence"))
        self.assertTrue(result.ok); self.assertGreater(len(sr.operations), 0)

    def test_gate_failure_returns_none(self):
        sr, result = gate.build_candidate("x", load_fixture("unsupported-dialect"))
        self.assertIsNone(sr); self.assertEqual(result.code, "incompatible_dialect")

    def test_normalization_failure_maps_to_code(self):
        sr, result = gate.build_candidate("x", {"openapi": "3.0.0", "info": {}, "paths": {"/a": {"get": {}}}})
        self.assertTrue(result.ok)  # sanity: minimal op is fine
        # force NormalizationError via non-dict paths is blocked by compatibility; simulate by patching
        from unittest import mock
        with mock.patch("tools.atlassian_docs.intelligence.gate.normalizer.normalize_openapi",
                        side_effect=gate.normalizer.NormalizationError("boom")):
            sr, result = gate.build_candidate("x", load_fixture("confluence"))
        self.assertIsNone(sr); self.assertEqual(result.code, "normalization_failed")

    def test_invalid_components(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {"/a": {"get": {"responses": {}}}}, "components": {"schemas": []}}
        sr, result = gate.build_candidate("x", spec)
        self.assertIsNone(sr); self.assertEqual(result.code, "invalid_components")
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/gate.py`:

```python
"""Compatibility gate (before normalize) and integrity check (after) — spec §10."""
from dataclasses import dataclass
from typing import Any, Optional

from .. import extractor, storage
from . import normalizer, registry

SUPPORTED_DIALECT_PREFIXES = ("3.0.", "3.1.")


@dataclass(frozen=True)
class GateResult:
    ok: bool
    code: Optional[str]
    message: str


_OK = GateResult(True, None, "ok")


def check_compatibility(spec: Any) -> GateResult:
    if not extractor.is_openapi_candidate(spec):
        return GateResult(False, "invalid_structure", "not an OpenAPI document (openapi/info/paths)")
    if not spec["openapi"].startswith(SUPPORTED_DIALECT_PREFIXES):
        return GateResult(False, "incompatible_dialect", f"unsupported OpenAPI dialect {spec['openapi']!r}")
    has_op = any(isinstance(item, dict) and any(m in item for m in normalizer.HTTP_METHODS)
                 for item in spec["paths"].values())
    if not has_op:
        return GateResult(False, "no_operations", "spec declares no operations")
    return _OK


def check_integrity(sr: registry.SourceRegistry) -> GateResult:
    if not sr.operations:
        return GateResult(False, "empty_registry", "normalized registry has no operations")
    keys = [op.key for op in sr.operations]
    if len(keys) != len(set(keys)):
        return GateResult(False, "duplicate_keys", "duplicate canonical keys")
    return _OK


def build_candidate(source_name: str, spec: Any) -> tuple:
    result = check_compatibility(spec)
    if not result.ok:
        return None, result
    comps = spec.get("components")
    if comps is not None and (not isinstance(comps, dict) or
                              ("schemas" in comps and not isinstance(comps["schemas"], dict))):
        return None, GateResult(False, "invalid_components", "components.schemas is not an object")
    try:
        normalized = normalizer.normalize_openapi(source_name, spec)
    except normalizer.NormalizationError as exc:
        return None, GateResult(False, "normalization_failed", str(exc))
    sr = registry.build_source_registry(normalized, storage.sha256_of_spec(spec))
    result = check_integrity(sr)
    return (sr, result) if result.ok else (None, result)
```

- [ ] **Step 4: Run tests** — PASS. - [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/gate.py tests/intelligence/test_gate.py
git commit -m "feat(intelligence): compatibility gate and integrity check before swap

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Provenance and response helpers (`provenance.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/provenance.py`
- Create: `tests/intelligence/test_provenance.py`
- Modify: `tests/intelligence/helpers.py` (add `make_state`)

**Interfaces:**
- Consumes: `models.SourceProvenance`, `models.RefreshStatus`, `registry.ActiveState/Registry/SourceRegistry`, `sync.TTL_SECONDS`, `sync.TIMESTAMP_FORMAT`, `sources.SOURCES`.
- Produces:
  - `@dataclass(frozen=True) class SourceObservation: source, metadata: dict, observed_cache_sha256: str | None, served_from_last_good: bool, rejected: dict | None (`{"sha256", "rejected_reason"}`), refresh_failed: bool, extra_warnings: tuple`
  - `build_source_provenance(active: SourceRegistry | None, obs: SourceObservation, *, now: datetime, ttl_seconds=sync.TTL_SECONDS) -> SourceProvenance`
  - `build_provenance(reg: Registry, observations: Mapping[str, SourceObservation], *, now, ttl_seconds) -> Mapping[str, SourceProvenance]` (one entry per `sources.SOURCES`)
  - `error_response(code: str, message: str, **extra) -> dict`
  - `with_provenance(payload: dict, state: ActiveState, source_names) -> dict` (adds `provenance` for the named sources and `registry_fingerprint`; unknown names get an `unavailable` stub)

- [ ] **Step 1: Add `make_state` helper**

Append to `tests/intelligence/helpers.py`:

```python
def make_state(*fixture_names, source_map=None):
    """ActiveState over fixtures with 'fresh' provenance; for testing intelligence functions."""
    import datetime
    from tools.atlassian_docs import sync
    from tools.atlassian_docs.intelligence import models, provenance, registry
    source_map = source_map or {}
    srcs = {source_map.get(n, n): build_source_registry_from_fixture(n, source_map.get(n)) for n in fixture_names}
    reg = registry.build_registry(srcs, "2026-09-28T00:00:00Z")
    now = datetime.datetime(2026, 9, 28, 1, 0, tzinfo=datetime.timezone.utc)
    obs = {}
    for name, sr in srcs.items():
        obs[name] = provenance.SourceObservation(
            source=name, observed_cache_sha256=sr.spec_sha256, served_from_last_good=False,
            rejected=None, refresh_failed=False, extra_warnings=(),
            metadata={"sha256": sr.spec_sha256, "api_version": "v3", "last_checked": now.strftime(sync.TIMESTAMP_FORMAT),
                      "last_updated": now.strftime(sync.TIMESTAMP_FORMAT), "resolved_documentation_url": "https://x/"})
    prov = provenance.build_provenance(reg, obs, now=now, ttl_seconds=sync.TTL_SECONDS)
    return registry.ActiveState(reg, prov, models.RefreshStatus(sync.TTL_SECONDS, 900, False, None, None, False))
```

- [ ] **Step 2: Write the failing tests**

`tests/intelligence/test_provenance.py`:

```python
import datetime
import unittest

from tests.intelligence.helpers import build_source_registry_from_fixture, make_state
from tools.atlassian_docs import sync
from tools.atlassian_docs.intelligence import provenance, registry

NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=datetime.timezone.utc)


def _obs(sr, **over):
    base = dict(source=sr.source, observed_cache_sha256=sr.spec_sha256, served_from_last_good=False,
                rejected=None, refresh_failed=False, extra_warnings=(),
                metadata={"sha256": sr.spec_sha256, "api_version": "v3",
                          "last_checked": (NOW - datetime.timedelta(hours=1)).strftime(sync.TIMESTAMP_FORMAT),
                          "last_updated": "2026-09-27T00:00:00Z", "resolved_documentation_url": "https://d/"})
    base.update(over)
    return provenance.SourceObservation(**base)


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.sr = build_source_registry_from_fixture("confluence")

    def test_fresh(self):
        p = provenance.build_source_provenance(self.sr, _obs(self.sr), now=NOW)
        self.assertEqual((p.status, p.reason), ("fresh", None))
        self.assertEqual(p.active_spec_sha256, self.sr.spec_sha256)
        self.assertEqual(p.active_api_version, "v3")
        self.assertEqual(p.operation_count, len(self.sr.operations))

    def test_ttl_expired(self):
        old = {"last_checked": (NOW - datetime.timedelta(hours=25)).strftime(sync.TIMESTAMP_FORMAT)}
        obs = _obs(self.sr); obs = provenance.SourceObservation(**{**obs.__dict__, "metadata": {**obs.metadata, **old}})
        p = provenance.build_source_provenance(self.sr, obs, now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "ttl_expired"))

    def test_refresh_failed(self):
        p = provenance.build_source_provenance(self.sr, _obs(self.sr, refresh_failed=True), now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "refresh_failed"))

    def test_metadata_mismatch_hides_api_version(self):
        obs = _obs(self.sr); obs = provenance.SourceObservation(**{**obs.__dict__, "metadata": {**obs.metadata, "sha256": "other"}})
        p = provenance.build_source_provenance(self.sr, obs, now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "metadata_mismatch"))
        self.assertIsNone(p.active_api_version)

    def test_rejected_candidate_is_diagnostic_only(self):
        obs = _obs(self.sr, observed_cache_sha256="newsha", rejected={"sha256": "newsha", "rejected_reason": "incompatible_dialect"})
        p = provenance.build_source_provenance(self.sr, obs, now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "incompatible_dialect"))
        self.assertEqual(p.active_spec_sha256, self.sr.spec_sha256)
        self.assertEqual(p.observed_cache_sha256, "newsha")
        self.assertEqual(p.candidate["rejected_reason"], "incompatible_dialect")

    def test_served_from_last_good(self):
        p = provenance.build_source_provenance(self.sr, _obs(self.sr, served_from_last_good=True), now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "served_from_last_good"))

    def test_unavailable(self):
        p = provenance.build_source_provenance(None, _obs(self.sr, observed_cache_sha256=None, metadata={}), now=NOW)
        self.assertEqual((p.status, p.reason), ("unavailable", "no_cache"))
        self.assertEqual(p.operation_count, 0)

    def test_partial_normalization_warning(self):
        sr = build_source_registry_from_fixture("edge-cases", source="edge")
        p = provenance.build_source_provenance(sr, _obs(sr), now=NOW)
        self.assertFalse(any(w["kind"] == "normalization_partial" for w in p.warnings))  # fixture is complete


class TestBuildProvenanceAndHelpers(unittest.TestCase):
    def test_all_configured_sources_present(self):
        state = make_state("confluence")
        self.assertEqual(set(state.provenance), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(state.provenance["jira-platform"].status, "unavailable")

    def test_with_provenance_and_error(self):
        state = make_state("confluence")
        out = provenance.with_provenance({"x": 1}, state, ["confluence", "jira-platform"])
        self.assertEqual(set(out["provenance"]), {"confluence", "jira-platform"})
        self.assertEqual(out["registry_fingerprint"], state.registry.fingerprint)
        err = provenance.error_response("operation_not_found", "nope", candidates=["a"])
        self.assertEqual(err["error"]["code"], "operation_not_found"); self.assertEqual(err["error"]["candidates"], ["a"])
```

- [ ] **Step 3: Run to verify failure** — ImportError.

- [ ] **Step 4: Implement**

`tools/atlassian_docs/intelligence/provenance.py`:

```python
"""Per-source provenance computed from the ACTIVE registry (spec §12) + response helpers (§14.1)."""
import datetime
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .. import sources, sync
from .models import SourceProvenance


@dataclass(frozen=True)
class SourceObservation:
    source: str
    metadata: dict
    observed_cache_sha256: Optional[str]
    served_from_last_good: bool
    rejected: Optional[dict]
    refresh_failed: bool
    extra_warnings: tuple


def _parse_ts(value: Any) -> Optional[datetime.datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value, sync.TIMESTAMP_FORMAT).replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def build_source_provenance(active, obs: SourceObservation, *, now: datetime.datetime,
                            ttl_seconds: int = sync.TTL_SECONDS) -> SourceProvenance:
    md = obs.metadata if isinstance(obs.metadata, dict) else {}
    warnings = list(obs.extra_warnings)
    common = dict(
        source=obs.source, observed_cache_sha256=obs.observed_cache_sha256,
        metadata_sha256=md.get("sha256"), resolved_documentation_url=md.get("resolved_documentation_url"),
        last_checked=md.get("last_checked"), last_updated=md.get("last_updated"),
        candidate=dict(obs.rejected) if obs.rejected else None,
    )
    if active is None:
        reason = obs.rejected["rejected_reason"] if obs.rejected else "no_cache"
        return SourceProvenance(status="unavailable", reason=reason, active_spec_sha256=None,
                                active_openapi_version=None, active_api_version=None,
                                operation_count=0, schema_count=0, warnings=tuple(warnings), **common)
    if active.normalization_partial:
        warnings.append({"kind": "normalization_partial",
                         "skipped": sum(1 for w in active.warnings if w.get("kind") == "operation_skipped")})
    matches_metadata = md.get("sha256") == active.spec_sha256
    checked = _parse_ts(md.get("last_checked"))
    ttl_ok = checked is not None and (now - checked).total_seconds() < ttl_seconds
    if obs.served_from_last_good:          # wins over `rejected`: the candidate stays in `candidate` as diagnostic
        reason = "served_from_last_good"
    elif obs.rejected:
        reason = obs.rejected["rejected_reason"]
    elif obs.refresh_failed:
        reason = "refresh_failed"
    elif not matches_metadata:
        reason = "metadata_mismatch"
    elif not ttl_ok:
        reason = "ttl_expired"
    else:
        reason = None
    return SourceProvenance(
        status="fresh" if reason is None else "stale", reason=reason,
        active_spec_sha256=active.spec_sha256, active_openapi_version=active.openapi_version,
        active_api_version=md.get("api_version") if matches_metadata else None,
        operation_count=len(active.operations), schema_count=len(active.schemas),
        warnings=tuple(warnings), **common)


def build_provenance(reg, observations: Mapping[str, SourceObservation], *, now: datetime.datetime,
                     ttl_seconds: int = sync.TTL_SECONDS) -> Mapping[str, SourceProvenance]:
    out = {}
    for name in sources.SOURCES:
        obs = observations.get(name) or SourceObservation(name, {}, None, False, None, False, ())
        out[name] = build_source_provenance(reg.sources.get(name), obs, now=now, ttl_seconds=ttl_seconds)
    return out


def error_response(code: str, message: str, **extra) -> dict:
    err = {"code": code, "message": message}
    err.update(extra)
    return {"error": err}


def with_provenance(payload: dict, state, source_names) -> dict:
    prov = {}
    for name in source_names:
        p = state.provenance.get(name)
        prov[name] = p.to_dict() if p else {"source": name, "status": "unavailable", "reason": "unknown_source"}
    payload["provenance"] = prov
    payload["registry_fingerprint"] = state.registry.fingerprint
    return payload
```

- [ ] **Step 5: Run tests** — PASS. - [ ] **Step 6: Commit**

```bash
git add tools/atlassian_docs/intelligence/provenance.py tests/intelligence/test_provenance.py tests/intelligence/helpers.py
git commit -m "feat(intelligence): active-registry provenance and response helpers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Operation search (`search.py`, part 2)

**Files:**
- Modify: `tools/atlassian_docs/intelligence/search.py` (append `search_operations`, `MAX_LIMIT`)
- Modify: `tests/intelligence/test_search.py` (append scoring tests)

**Interfaces:**
- Consumes: `ActiveState`, `provenance.with_provenance/error_response`, `sources.SOURCES`.
- Produces: `MAX_LIMIT = 50`; `search_operations(state, query, *, source=None, method=None, tag=None, include_deprecated=True, limit=10) -> dict` with `{"query", "results": [...], "total_matches", "provenance", "registry_fingerprint"}` or an error dict.

- [ ] **Step 1: Append failing tests to `tests/intelligence/test_search.py`**

```python
from tests.intelligence.helpers import make_state  # add at top


class TestSearchOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "jira-software", "confluence")

    def _keys(self, **kw):
        return [r["key"] for r in search.search_operations(self.state, **kw)["results"]]

    def test_attachment_query_top1(self):
        self.assertEqual(self._keys(query="upload attachment to issue")[0],
                         "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")

    def test_plural_and_singular_agree(self):
        self.assertEqual(self._keys(query="issue attachments")[0], self._keys(query="issue attachment")[0])

    def test_sprint_query_prefers_jira_software(self):
        top3 = self._keys(query="sprint board backlog")[:3]
        self.assertEqual(len(top3), 3)
        self.assertTrue(all(k.startswith("jira-software:") for k in top3), top3)

    def test_create_confluence_page(self):
        self.assertEqual(self._keys(query="create confluence page")[0], "confluence:POST:/pages")

    def test_exact_schema_name(self):
        self.assertEqual(self._keys(query="IssueCreateMetadata")[0], "jira-platform:GET:/rest/api/3/issue/createmeta")

    def test_source_filter(self):
        self.assertTrue(all(k.startswith("confluence:") for k in self._keys(query="issue page", source="confluence")))

    def test_method_tag_and_deprecated_filters(self):
        self.assertTrue(all(":GET:" in k for k in self._keys(query="issue", method="get")))
        out = search.search_operations(self.state, "issue", include_deprecated=False)
        self.assertTrue(all(not r["deprecated"] for r in out["results"]))
        tag = self.state.registry.sources["jira-platform"].operations[0].tags[0]
        self.assertTrue(all(tag in r["tags"] for r in search.search_operations(self.state, "issue", tag=tag)["results"]))

    def test_deterministic_order(self):
        self.assertEqual(self._keys(query="issue"), self._keys(query="issue"))

    def test_limit_bounds_and_provenance_scope(self):
        out = search.search_operations(self.state, "issue", limit=2)
        self.assertEqual(len(out["results"]), 2)
        self.assertEqual(set(out["provenance"]), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(set(search.search_operations(self.state, "issue", source="confluence")["provenance"]), {"confluence"})
        self.assertEqual(search.search_operations(self.state, "issue", limit=51)["error"]["code"], "invalid_argument")
        self.assertEqual(search.search_operations(self.state, "issue", source="github")["error"]["code"], "invalid_argument")

    def test_stopword_only_query_is_empty_query_error(self):
        self.assertEqual(search.search_operations(self.state, "a to")["error"]["code"], "empty_query")
        self.assertEqual(search.search_operations(self.state, "")["error"]["code"], "empty_query")

    def test_unavailable_source_filter_returns_empty_not_error(self):
        state = make_state("confluence")
        out = search.search_operations(state, "issue", source="jira-platform")
        self.assertEqual(out["results"], [])
        self.assertEqual(out["provenance"]["jira-platform"]["status"], "unavailable")
```

- [ ] **Step 2: Run to verify failure** — AttributeError `search_operations`.

- [ ] **Step 3: Append implementation to `search.py`**

```python
from .. import sources  # add to imports at top
from . import provenance  # add to imports at top

MAX_LIMIT = 50
ALL_MATCH_BONUS = 2
DEPRECATED_FACTOR = 0.7


def _score(entry: IndexEntry, query_tokens: frozenset, deprecated: bool) -> float:
    score = 0.0
    matched_any_token = set()
    for field, weight in FIELD_WEIGHTS.items():
        hits = query_tokens & entry.fields[field]
        score += weight * len(hits)
        matched_any_token |= hits
    if score and matched_any_token == query_tokens:
        score += ALL_MATCH_BONUS
    return score * DEPRECATED_FACTOR if deprecated else score


def search_operations(state, query: str, *, source=None, method=None, tag=None,
                      include_deprecated: bool = True, limit: int = 10) -> dict:
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return provenance.error_response("invalid_argument", f"limit must be 1..{MAX_LIMIT}")
    if source is not None and source not in sources.SOURCES:
        return provenance.error_response("invalid_argument", f"unknown source {source!r}")
    query_tokens = tokenize(query)
    if not query_tokens:
        return provenance.error_response("empty_query", "query has no searchable tokens")
    scope = [source] if source else sorted(sources.SOURCES)
    scored = []
    for name in scope:
        sr = state.registry.sources.get(name)
        if sr is None:
            continue
        for entry in sr.search_index.entries:
            op = sr.operations_by_key[entry.key]
            if method and op.method != method.upper():
                continue
            if tag and tag not in op.tags:
                continue
            if not include_deprecated and op.deprecated:
                continue
            s = _score(entry, query_tokens, op.deprecated)
            if s > 0:
                scored.append((s, op))
    scored.sort(key=lambda item: (-item[0], item[1].deprecated, item[1].source, item[1].key))
    results = [{"key": op.key, "source": op.source, "operation_id": op.operation_id, "method": op.method,
                "path": op.path, "summary": op.summary, "tags": list(op.tags), "deprecated": op.deprecated,
                "experimental": op.experimental, "score": round(s, 3)}
               for s, op in scored[:limit]]
    payload = {"query": query, "results": results, "total_matches": len(scored)}
    return provenance.with_provenance(payload, state, scope)
```

- [ ] **Step 4: Run tests** — `python -m unittest tests.intelligence.test_search -v` → PASS. If `test_sprint_query_prefers_jira_software` fails because a jira-platform operation with "board" in its description sneaks into the top 3, do **not** change weights: check the jira-platform fixture selection — `/rest/api/3/search/jql` descriptions can mention sprints; drop that path from `SELECTIONS` in Task 1's generator, regenerate, and re-run.

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/search.py tests/intelligence/test_search.py
git commit -m "feat(intelligence): weighted lexical search_operations with filters and provenance

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 10: Operation and schema inspection (`inspect.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/inspect.py`
- Create: `tests/intelligence/test_inspect.py`

**Interfaces:**
- Consumes: `ActiveState`, `schemas.resolve`, `provenance.with_provenance/error_response`.
- Produces:
  - `DESCRIPTION_COMPACT_CHARS = 500`
  - `resolve_operation(state, key=None, source=None, operation_id=None) -> tuple[Operation | None, dict | None]` — returns `(op, None)` or `(None, error_dict)` with codes `invalid_argument`, `operation_not_found`, `ambiguous_operation_id` (with `candidates`), `source_unavailable`. Shared by Tasks 11–12.
  - `get_operation(state, key=None, source=None, operation_id=None, *, include_full_description=False, include_response_schemas=False, resolve_schema_depth=0) -> dict`
  - `get_schema(state, source, name, *, max_depth=2, max_nodes=200) -> dict`

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_inspect.py`:

```python
import json
import unittest

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import inspect as insp

ATT = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"


class TestResolveOperation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "edge-cases", source_map={"edge-cases": "edge"})

    def test_by_key_and_by_operation_id(self):
        self.assertEqual(insp.resolve_operation(self.state, key=ATT)[0].operation_id, "addAttachment")
        self.assertEqual(insp.resolve_operation(self.state, operation_id="addAttachment")[0].key, ATT)

    def test_errors(self):
        self.assertEqual(insp.resolve_operation(self.state)[1]["error"]["code"], "invalid_argument")
        self.assertEqual(insp.resolve_operation(self.state, key="jira-platform:GET:/nope")[1]["error"]["code"], "operation_not_found")
        self.assertEqual(insp.resolve_operation(self.state, key="confluence:GET:/pages")[1]["error"]["code"], "source_unavailable")
        err = insp.resolve_operation(self.state, operation_id="dupId")[1]["error"]
        self.assertEqual(err["code"], "ambiguous_operation_id"); self.assertEqual(len(err["candidates"]), 2)


class TestGetOperation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform")

    def test_compact_default(self):
        out = insp.get_operation(self.state, key=ATT)
        json.dumps(out)
        self.assertLessEqual(len(out["description"]), 500)
        self.assertTrue(out["description_truncated"])
        self.assertEqual(out["responses"][0]["status"], "200")
        self.assertNotIn("schema", json.dumps(out["responses"]))
        self.assertNotIn('"example"', json.dumps(out))
        self.assertEqual(out["request_body"]["content"][0]["schema"]["items"], {"$ref": "#/components/schemas/MultipartFile"})
        self.assertEqual(set(out["provenance"]), {"jira-platform"})
        self.assertIsInstance(out["security"][0], list)

    def test_full_description_and_response_schemas(self):
        out = insp.get_operation(self.state, key=ATT, include_full_description=True, include_response_schemas=True)
        self.assertFalse(out["description_truncated"])
        self.assertIn("content", out["responses"][0])

    def test_resolve_schema_depth_inlines(self):
        out = insp.get_operation(self.state, key=ATT, resolve_schema_depth=1)
        items = out["request_body"]["content"][0]["schema"]["items"]
        self.assertNotIn("$ref", items); self.assertIn("type", items)
        self.assertEqual(insp.get_operation(self.state, key=ATT, resolve_schema_depth=9)["error"]["code"], "invalid_argument")

    def test_output_is_independent_copy(self):
        out = insp.get_operation(self.state, key=ATT)
        out["request_body"]["content"][0]["schema"]["items"]["$ref"] = "x"
        self.assertEqual(insp.get_operation(self.state, key=ATT)["request_body"]["content"][0]["schema"]["items"]["$ref"],
                         "#/components/schemas/MultipartFile")


class TestGetSchema(unittest.TestCase):
    def test_get_schema_and_limits(self):
        state = make_state("edge-cases", source_map={"edge-cases": "edge"})
        out = insp.get_schema(state, "edge", "Node", max_depth=3)
        self.assertEqual(out["source"], "edge"); self.assertTrue(out["cycles"])
        self.assertEqual(insp.get_schema(state, "edge", "Nope")["error"]["code"], "schema_not_found")
        self.assertEqual(insp.get_schema(state, "confluence", "X")["error"]["code"], "source_unavailable")
        self.assertEqual(insp.get_schema(state, "edge", "Node", max_depth=99)["error"]["code"], "invalid_argument")
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/inspect.py`:

```python
"""get_operation / get_schema with compact-by-default output (spec §14)."""
from typing import Any, Optional

from .. import sources
from . import provenance, schemas

DESCRIPTION_COMPACT_CHARS = 500


def resolve_operation(state, key: Optional[str] = None, source: Optional[str] = None,
                      operation_id: Optional[str] = None) -> tuple:
    reg = state.registry
    if key:
        src = key.split(":", 1)[0]
        if src not in sources.SOURCES:
            return None, provenance.error_response("invalid_argument", f"unknown source in key {key!r}")
        if src not in reg.sources:
            return None, provenance.error_response("source_unavailable", f"source {src!r} is unavailable")
        op = reg.get_operation(key)
        return (op, None) if op else (None, provenance.error_response("operation_not_found", f"no operation {key!r}"))
    if not operation_id:
        return None, provenance.error_response("invalid_argument", "provide key, or operation_id (optionally with source)")
    if source is not None:
        if source not in sources.SOURCES:
            return None, provenance.error_response("invalid_argument", f"unknown source {source!r}")
        if source not in reg.sources:
            return None, provenance.error_response("source_unavailable", f"source {source!r} is unavailable")
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
    if source not in sources.SOURCES:
        return provenance.error_response("invalid_argument", f"unknown source {source!r}")
    comps = state.registry.sources.get(source)
    if comps is None:
        return provenance.error_response("source_unavailable", f"source {source!r} is unavailable")
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
```

- [ ] **Step 4: Run tests** — PASS. - [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/inspect.py tests/intelligence/test_inspect.py
git commit -m "feat(intelligence): get_operation and get_schema with compact output policy

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Request template builder (`request_template.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/request_template.py`
- Create: `tests/intelligence/test_request_template.py`

**Interfaces:**
- Consumes: `inspect.resolve_operation`, `provenance.*`.
- Produces: `CREDENTIAL_HEADERS = frozenset({"authorization", "cookie"})`; `build_request_template(state, key: str, values: dict | None = None) -> dict` shaped as spec §15 (keys: `key, method, path_template, path, path_params, query, headers, cookies, unknown_parameters, content_types, selected_content_type, body_schema, body, body_required, security, oauth2_scopes, server, missing_required, errors, notes, provenance, registry_fingerprint`).

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_request_template.py`:

```python
import unittest

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import request_template as rt

ATT = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"
THING = "edge:GET:/things/{thingId}"
CREATE = "edge:POST:/things/{thingId}"


class TestTemplate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "edge-cases", source_map={"edge-cases": "edge"})

    def test_no_values(self):
        out = rt.build_request_template(self.state, ATT)
        self.assertEqual(out["method"], "POST"); self.assertIsNone(out["path"]); self.assertIsNone(out["server"])
        self.assertEqual(out["path_params"]["issueIdOrKey"]["required"], True)
        self.assertEqual(out["selected_content_type"], "multipart/form-data")
        self.assertTrue(out["body_required"]); self.assertIn("body", out["missing_required"]); self.assertIn("issueIdOrKey", out["missing_required"])
        self.assertIn("server URL and Authorization are out of scope for Phase 2", out["notes"])

    def test_path_substitution_encodes(self):
        out = rt.build_request_template(self.state, ATT, {"path_params": {"issueIdOrKey": "AB C/1"}, "body": [{"file": "x"}]})
        self.assertEqual(out["path"], "/rest/api/3/issue/AB%20C%2F1/attachments")
        self.assertEqual(out["missing_required"], []); self.assertEqual(out["body"], [{"file": "x"}])

    def test_non_primitive_path_value_is_invalid(self):
        self.assertEqual(rt.build_request_template(self.state, ATT, {"path_params": {"issueIdOrKey": {"a": 1}}})["error"]["code"], "invalid_argument")

    def test_query_headers_unknown_and_case_insensitive(self):
        out = rt.build_request_template(self.state, THING, {"path_params": {"thingId": "1"}, "query": {"limit": 5, "foo": 1},
                                                              "headers": {"X-Custom": "v"}})
        self.assertEqual(out["query"]["limit"]["value"], 5)
        self.assertEqual(out["unknown_parameters"]["query"], ["foo"])
        self.assertEqual(out["unknown_parameters"]["headers"], ["X-Custom"])
        self.assertIn("session", out["cookies"])

    def test_invalid_content_type_not_silently_replaced(self):
        out = rt.build_request_template(self.state, CREATE, {"content_type": "text/plain"})
        self.assertIsNone(out["selected_content_type"]); self.assertIsNone(out["body_schema"])
        self.assertEqual(out["errors"][0]["rule"], "invalid_content_type")

    def test_content_type_defaulted_note_when_ambiguous(self):
        out = rt.build_request_template(self.state, CREATE)
        self.assertEqual(out["selected_content_type"], "application/json"); self.assertIn("content_type_defaulted", out["notes"])
        out = rt.build_request_template(self.state, CREATE, {"content_type": "multipart/form-data"})
        self.assertEqual(out["selected_content_type"], "multipart/form-data"); self.assertEqual(out["body_schema"], {"type": "object"})

    def test_credential_headers_dropped(self):
        out = rt.build_request_template(self.state, THING, {"headers": {"Authorization": "Basic xxx", "Cookie": "a=b"}})
        self.assertNotIn("Basic xxx", str(out)); self.assertIn("credential_header_dropped", out["notes"])
        self.assertEqual(out["unknown_parameters"]["headers"], [])

    def test_security_and_scopes_and_error(self):
        out = rt.build_request_template(self.state, CREATE)
        self.assertEqual(out["security"][0], []); self.assertEqual(out["oauth2_scopes"], ["write:thing", "read:thing"])
        self.assertEqual(rt.build_request_template(self.state, "edge:GET:/nope")["error"]["code"], "operation_not_found")
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/request_template.py`:

```python
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
```

- [ ] **Step 4: Run tests** — PASS. - [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/request_template.py tests/intelligence/test_request_template.py
git commit -m "feat(intelligence): build_request_template without server or credentials

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Structural request check (`request_check.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/request_check.py`
- Create: `tests/intelligence/test_request_check.py`

**Interfaces:**
- Consumes: `inspect.resolve_operation`, `schemas.resolve`, `provenance.*`.
- Produces: `MISSING = object()` sentinel; `CHECKED_RULES`, `NOT_CHECKED` tuples; `check_request(state, key, *, path_params=None, query=None, headers=None, body=MISSING, content_type=None) -> dict` shaped as spec §16 (`compatible, errors, warnings, checked, not_checked, provenance, registry_fingerprint`).

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_request_check.py`:

```python
import unittest

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import request_check as rc

THING = "edge:GET:/things/{thingId}"
CREATE = "edge:POST:/things/{thingId}"
MERGE = "edge:POST:/merge"
CHOICE = "edge:POST:/choice"


def _rules(out, kind="errors"):
    return sorted((e["location"], e["rule"]) for e in out[kind])


class TestParameters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})

    def test_required_missing(self):
        out = rc.check_request(self.state, THING)
        self.assertFalse(out["compatible"]); self.assertNotIn("valid", out)
        self.assertIn(("path.thingId", "required"), _rules(out)); self.assertIn(("query.limit", "required"), _rules(out))
        self.assertIn(("cookie.session", "cookie_not_checked"), _rules(out, "warnings"))

    def test_coercion_rules(self):
        ok = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": "5", "expand": "x"})
        self.assertTrue(ok["compatible"], ok)
        bad = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": "5.5", "expand": "zzz"})
        self.assertIn(("query.limit", "type"), _rules(bad)); self.assertIn(("query.expand", "enum"), _rules(bad))

    def test_bool_is_not_integer(self):
        out = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": True})
        self.assertIn(("query.limit", "type"), _rules(out))

    def test_unknown_parameter_warning_and_header_case(self):
        out = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": 1, "foo": 1}, headers={"x-y": "1"})
        self.assertTrue(out["compatible"])
        self.assertIn(("query.foo", "unknown_parameter"), _rules(out, "warnings"))
        self.assertIn(("header.x-y", "unknown_parameter"), _rules(out, "warnings"))


class TestBody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})

    def test_body_required_vs_explicit_null(self):
        self.assertIn(("body", "body_required"), _rules(rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json")))
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body=None, content_type="application/json")
        self.assertNotIn(("body", "body_required"), _rules(out)); self.assertIn(("body", "body_root_type"), _rules(out))

    def test_content_type_rules(self):
        bad = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={"name": "n"}, content_type="text/plain")
        self.assertIn(("content_type", "content_type"), _rules(bad))
        amb = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={})
        self.assertIn(("content_type", "content_type_ambiguous"), _rules(amb, "warnings"))
        self.assertTrue(amb["compatible"])  # body schema check skipped, nothing else wrong

    def test_body_rules_on_strict_schema(self):
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json",
                               body={"count": "x", "kind": "z", "extra": 1, "note": None})
        r = _rules(out)
        self.assertIn(("body.name", "body_required_properties"), r)
        self.assertIn(("body.count", "body_property_type"), r)
        self.assertIn(("body.kind", "body_property_enum"), r)
        self.assertIn(("body.extra", "body_unknown_property"), r)     # additionalProperties:false -> error
        self.assertNotIn(("body.note", "body_property_type"), r)      # nullable
        good = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json", body={"name": "n"})
        self.assertTrue(good["compatible"])

    def test_allof_merge_and_conflict(self):
        out = rc.check_request(self.state, MERGE, body={"id": "1"})
        self.assertIn(("body.extra", "body_required_properties"), _rules(out))
        self.assertIn(("body.shared", "conflicting_allof_property"), _rules(out, "warnings"))
        out = rc.check_request(self.state, MERGE, body={"id": "1", "extra": 2, "shared": "anything"})
        self.assertTrue(out["compatible"])

    def test_oneof_not_checked(self):
        out = rc.check_request(self.state, CHOICE, body={"whatever": 1})
        self.assertIn(("body", "structure_not_checked"), _rules(out, "warnings")); self.assertTrue(out["compatible"])

    def test_checked_lists_present(self):
        out = rc.check_request(self.state, CHOICE)
        self.assertIn("required", out["checked"]); self.assertIn("oneOf/anyOf", out["not_checked"])
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/request_check.py`:

```python
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
    if typ in (None, "object"):
        return None
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
```

- [ ] **Step 4: Run tests** — PASS. Then full suite.

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/request_check.py tests/intelligence/test_request_check.py
git commit -m "feat(intelligence): structural check_request with fixed rule set

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 13: Last-known-good persistence (`lastgood.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/lastgood.py`
- Create: `tests/intelligence/test_lastgood.py`

**Interfaces:**
- Consumes: `storage.CACHE_DIR` (read at call time so tests can patch it), `storage.sha256_of_spec`.
- Produces: `last_good_dir() -> pathlib.Path` (`storage.CACHE_DIR / "intelligence"`), `last_good_path(source) -> Path`, `read_last_good(source) -> dict | None` (None on missing/invalid JSON), `write_last_good(source, spec) -> None` (atomic; raises `OSError`), `last_good_sha(source) -> str | None`.

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_lastgood.py`:

```python
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tools.atlassian_docs import storage
from tools.atlassian_docs.intelligence import lastgood


class TestLastGood(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(storage, "CACHE_DIR", pathlib.Path(self.tmp.name) / ".atlassian-docs")
        patcher.start(); self.addCleanup(patcher.stop)

    def test_round_trip_and_sha(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {"/a": {"get": {}}}}
        self.assertIsNone(lastgood.read_last_good("confluence")); self.assertIsNone(lastgood.last_good_sha("confluence"))
        lastgood.write_last_good("confluence", spec)
        self.assertEqual(lastgood.read_last_good("confluence"), spec)
        self.assertEqual(lastgood.last_good_sha("confluence"), storage.sha256_of_spec(spec))
        self.assertTrue(lastgood.last_good_path("confluence").name.endswith(".last-good.json"))
        self.assertEqual(lastgood.last_good_path("confluence").parent, storage.CACHE_DIR / "intelligence")

    def test_invalid_json_reads_as_none(self):
        lastgood.last_good_dir().mkdir(parents=True)
        lastgood.last_good_path("jira-platform").write_text("{not json", encoding="utf-8")
        self.assertIsNone(lastgood.read_last_good("jira-platform"))

    def test_write_is_atomic_no_tmp_left(self):
        lastgood.write_last_good("x", {"a": 1})
        self.assertEqual([p.name for p in lastgood.last_good_dir().iterdir()], ["x.last-good.json"])
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/lastgood.py`:

```python
"""Durable last-known-good raw spec per source (spec §11.3). Phase 1 owns .atlassian-docs/;
Phase 2 owns only the intelligence/ subdirectory. Atomic write mirrors storage.py without importing its private helper."""
import json
import os
import pathlib
import tempfile
from typing import Optional

from .. import storage


def last_good_dir() -> pathlib.Path:
    return storage.CACHE_DIR / "intelligence"


def last_good_path(source: str) -> pathlib.Path:
    return last_good_dir() / f"{source}.last-good.json"


def read_last_good(source: str) -> Optional[dict]:
    path = last_good_path(source)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_last_good(source: str, spec: dict) -> None:
    path = last_good_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def last_good_sha(source: str) -> Optional[str]:
    spec = read_last_good(source)
    return storage.sha256_of_spec(spec) if spec is not None else None
```

- [ ] **Step 4: Run tests** — PASS. - [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/lastgood.py tests/intelligence/test_lastgood.py
git commit -m "feat(intelligence): durable last-known-good spec snapshots

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: RegistryManager — startup, lazy refresh, atomic swap (`manager.py`)

**Files:**
- Create: `tools/atlassian_docs/intelligence/manager.py`
- Create: `tests/intelligence/test_manager.py`
- Modify: `tools/atlassian_docs/intelligence/__init__.py` (public re-exports)

**Interfaces:**
- Consumes: `sync.sync_all`, `sync.SyncResult`, `sync.MetadataPersistenceError`, `sync.TTL_SECONDS`, `storage.read_cache_spec/read_metadata/sha256_of_spec`, `sources.SOURCES`, `gate.build_candidate`, `lastgood.*`, `provenance.*`, `registry.*`, `models.RefreshStatus`.
- Produces:
  ```python
  MIN_RETRY_INTERVAL = 900
  class RegistryManager:
      def __init__(self, *, sync_all=sync.sync_all, read_cache_spec=storage.read_cache_spec,
                   read_metadata=storage.read_metadata, read_last_good=lastgood.read_last_good,
                   write_last_good=lastgood.write_last_good, clock=time.monotonic,
                   now=<utc now>, ttl_seconds=sync.TTL_SECONDS, min_retry_interval=MIN_RETRY_INTERVAL)
      def start(self) -> None                     # raises RegistryUnavailableError
      @property
      def active(self) -> ActiveState
      def needs_refresh(self, source: str) -> bool
      @property
      def backoff_active(self) -> bool
      def ensure_fresh(self) -> None
      def refresh(self) -> dict                   # {"status": "completed"|"refresh_in_progress", ...}
  ```
  Everything is synchronous (spec §11.8).

- [ ] **Step 1: Write the failing tests**

`tests/intelligence/test_manager.py`:

```python
import datetime
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs import storage, sync
from tools.atlassian_docs.intelligence import lastgood, manager, registry, search

NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=datetime.timezone.utc)
FMT = sync.TIMESTAMP_FORMAT


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


class Harness(unittest.TestCase):
    """Real storage under a temp CACHE_DIR; sync replaced by a controllable fake."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(storage, "CACHE_DIR", pathlib.Path(self.tmp.name) / ".atlassian-docs"); p.start(); self.addCleanup(p.stop)
        self.clock = FakeClock()
        self.sync_calls = 0
        self.sync_behaviour = "ok"  # "ok" | "fail" | "raise" | "metadata_error"

    def write_cache(self, source, spec, checked=NOW):
        storage.write_cache_spec(source, spec)
        md = storage.read_metadata()
        md[source] = {"sha256": storage.sha256_of_spec(spec), "api_version": "v3", "last_checked": checked.strftime(FMT),
                      "last_updated": checked.strftime(FMT), "resolved_documentation_url": "https://d/"}
        storage.write_metadata(md)

    def fake_sync(self, force=False):
        self.sync_calls += 1
        if self.sync_behaviour == "raise":
            raise OSError("network down")
        results = [sync.SyncResult(s, "ok") for s in ("jira-platform", "jira-software", "confluence")]
        if self.sync_behaviour == "fail":
            results[0] = sync.SyncResult("jira-platform", "warn_fallback", message="boom")
        if self.sync_behaviour == "metadata_error":
            raise sync.MetadataPersistenceError("disk", results)
        return results

    def make(self):
        m = manager.RegistryManager(sync_all=self.fake_sync, clock=self.clock, now=lambda: NOW)
        m.start()
        return m


class TestStartup(Harness):
    def test_cache_first_no_network(self):
        self.write_cache("confluence", load_fixture("confluence"))
        m = self.make()
        self.assertEqual(self.sync_calls, 0)
        self.assertEqual(m.active.provenance["confluence"].status, "fresh")
        self.assertEqual(m.active.provenance["jira-platform"].status, "unavailable")
        self.assertTrue(lastgood.last_good_path("confluence").exists())

    def test_ttl_expired_still_no_network_at_startup(self):
        self.write_cache("confluence", load_fixture("confluence"), checked=NOW - datetime.timedelta(hours=30))
        m = self.make()
        self.assertEqual(self.sync_calls, 0)
        self.assertEqual(m.active.provenance["confluence"].reason, "ttl_expired")

    def test_no_cache_triggers_single_sync_then_unavailable_error(self):
        with self.assertRaises(registry.RegistryUnavailableError):
            self.make()
        self.assertEqual(self.sync_calls, 1)

    def test_no_cache_sync_populates(self):
        def sync_and_write(force=False):
            self.write_cache("confluence", load_fixture("confluence")); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        self.assertIn("confluence", m.active.registry.sources)

    def test_incompatible_cache_falls_back_to_last_good(self):
        self.write_cache("confluence", load_fixture("confluence"))
        self.make()  # writes last-good
        self.write_cache("confluence", load_fixture("unsupported-dialect"))
        m = self.make()
        p = m.active.provenance["confluence"]
        self.assertEqual((p.status, p.reason), ("stale", "served_from_last_good"))
        self.assertEqual(p.candidate["rejected_reason"], "incompatible_dialect")
        self.assertGreater(p.operation_count, 0)


class TestRefresh(Harness):
    def setUp(self):
        super().setUp()
        self.write_cache("confluence", load_fixture("confluence"), checked=NOW - datetime.timedelta(hours=30))

    def test_ensure_fresh_syncs_and_rebuilds_on_sha_change(self):
        m = self.make(); before = m.active.registry.fingerprint
        new = load_fixture("confluence"); new["paths"]["/zzz-new"] = {"get": {"operationId": "zzzNew", "summary": "brand new op", "responses": {}}}
        def sync_and_write(force=False):
            self.write_cache("confluence", new); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        m.ensure_fresh()
        self.assertEqual(self.sync_calls, 1)
        self.assertNotEqual(m.active.registry.fingerprint, before)
        self.assertIsNotNone(m.active.registry.get_operation("confluence:GET:/zzz-new"))
        self.assertEqual(lastgood.last_good_sha("confluence"), storage.sha256_of_spec(new))
        self.assertEqual(m.active.provenance["confluence"].status, "fresh")

    def test_unchanged_sha_reuses_source_registry(self):
        m = self.make(); sr = m.active.registry.sources["confluence"]
        self.write_cache("confluence", load_fixture("confluence"))  # same content, fresh metadata
        m.refresh()
        self.assertIs(m.active.registry.sources["confluence"], sr)

    def test_failed_refresh_backoff_only_after_failure(self):
        self.sync_behaviour = "raise"
        m = self.make()
        m.ensure_fresh(); m.ensure_fresh()
        self.assertEqual(self.sync_calls, 1)
        self.assertTrue(m.backoff_active)
        self.assertEqual(m.active.provenance["confluence"].reason, "refresh_failed")
        self.clock.t += 901
        m.ensure_fresh()
        self.assertEqual(self.sync_calls, 2)
        self.sync_behaviour = "ok"; self.clock.t += 901
        self.write_cache("confluence", load_fixture("confluence"))
        m.refresh()   # ensure_fresh would short-circuit: the rewritten metadata is already fresh
        self.assertFalse(m.backoff_active)
        self.assertEqual(m.active.provenance["confluence"].status, "fresh")

    def test_warn_fallback_counts_as_failed(self):
        self.sync_behaviour = "fail"
        m = self.make(); m.ensure_fresh()
        self.assertTrue(m.backoff_active)

    def test_metadata_persistence_error_counts_as_failed_refresh(self):
        self.sync_behaviour = "metadata_error"
        m = self.make(); m.ensure_fresh()
        self.assertTrue(m.backoff_active)
        self.assertIn("confluence", m.active.registry.sources)

    def test_gate_failure_keeps_previous_and_does_not_recheck_same_sha(self):
        m = self.make(); before = m.active.registry.sources["confluence"]
        bad = load_fixture("unsupported-dialect")
        def sync_and_write(force=False):
            self.write_cache("confluence", bad); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        m.ensure_fresh()
        p = m.active.provenance["confluence"]
        self.assertEqual((p.status, p.reason), ("stale", "incompatible_dialect"))
        self.assertEqual(p.active_spec_sha256, before.spec_sha256)
        self.assertEqual(p.observed_cache_sha256, storage.sha256_of_spec(bad))
        with mock.patch("tools.atlassian_docs.intelligence.manager.gate.build_candidate", wraps=manager.gate.build_candidate) as bc:
            m.refresh()
            self.assertEqual(bc.call_count, 0)  # same rejected sha skipped

    def test_unavailable_source_recovers_at_runtime(self):
        m = self.make()
        self.assertEqual(m.active.provenance["jira-platform"].status, "unavailable")
        def sync_and_write(force=False):
            self.write_cache("jira-platform", load_fixture("jira-platform")); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        self.assertTrue(m.needs_refresh("jira-platform"))
        m.ensure_fresh()
        self.assertEqual(m.active.provenance["jira-platform"].status, "fresh")

    def test_refresh_tool_semantics(self):
        m = self.make()
        out = m.refresh()
        self.assertEqual(out["status"], "completed"); self.assertIn("registry_rebuilt", out)
        m._lock.acquire()
        try:
            self.assertEqual(m.refresh(), {"status": "refresh_in_progress"})
            m.ensure_fresh()  # lock busy -> silently keep current
        finally:
            m._lock.release()

    def test_state_snapshot_is_consistent(self):
        m = self.make()
        state = m.active
        new = load_fixture("confluence"); new["info"]["title"] = "changed"
        def sync_and_write(force=False):
            self.write_cache("confluence", new); return self.fake_sync(force)
        m2 = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m2.start(); m2.ensure_fresh()
        self.assertEqual(state.registry.fingerprint, state.registry.fingerprint)  # captured snapshot untouched
        self.assertEqual(m2.active.provenance["confluence"].active_spec_sha256, m2.active.registry.sources["confluence"].spec_sha256)

    def test_last_good_write_failure_does_not_block_swap(self):
        def boom(source, spec): raise OSError("disk full")
        m = manager.RegistryManager(sync_all=self.fake_sync, write_last_good=boom, clock=self.clock, now=lambda: NOW); m.start()
        self.assertIn("confluence", m.active.registry.sources)
        self.assertTrue(any(w["kind"] == "last_good_write_failed" for w in m.active.provenance["confluence"].warnings))
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

`tools/atlassian_docs/intelligence/manager.py`:

```python
"""RegistryManager: cache-first startup, lazy TTL refresh with failure-only backoff,
gate-before-swap, durable last-known-good, single ActiveState snapshot (spec §11)."""
import datetime
import threading
import time
from typing import Callable, Optional

from .. import sources, storage, sync
from . import gate, lastgood, provenance, registry
from .models import RefreshStatus

MIN_RETRY_INTERVAL = 900
_FAILED_STATUSES = ("warn_fallback", "error_unavailable")


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class RegistryManager:
    def __init__(self, *, sync_all: Callable = sync.sync_all,
                 read_cache_spec: Callable = storage.read_cache_spec,
                 read_metadata: Callable = storage.read_metadata,
                 read_last_good: Callable = lastgood.read_last_good,
                 write_last_good: Callable = lastgood.write_last_good,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime.datetime] = _utc_now,
                 ttl_seconds: int = sync.TTL_SECONDS,
                 min_retry_interval: int = MIN_RETRY_INTERVAL):
        self._sync_all, self._read_cache_spec, self._read_metadata = sync_all, read_cache_spec, read_metadata
        self._read_last_good, self._write_last_good = read_last_good, write_last_good
        self._clock, self._now = clock, now
        self._ttl, self._min_retry = ttl_seconds, min_retry_interval
        self._lock = threading.Lock()
        self._active: Optional[registry.ActiveState] = None
        self._last_failed_mono: Optional[float] = None
        self._last_attempt_at: Optional[str] = None
        self._last_result: Optional[dict] = None
        self._last_rejected_sha: dict = {}
        self._served_from_last_good: set = set()
        self._rejected: dict = {}
        self._extra_warnings: dict = {}

    # ---- public -----------------------------------------------------------------
    @property
    def active(self) -> registry.ActiveState:
        if self._active is None:
            raise registry.RegistryUnavailableError("manager not started")
        return self._active

    @property
    def backoff_active(self) -> bool:
        return self._last_failed_mono is not None and (self._clock() - self._last_failed_mono) < self._min_retry

    def start(self) -> None:
        self._rebuild(previous=None, refresh_failed=False)
        if not self._active.registry.sources:
            self._run_sync()
            self._rebuild(previous=None, refresh_failed=self._last_failed_mono is not None)
            if not self._active.registry.sources:
                raise registry.RegistryUnavailableError("no usable OpenAPI cache for any source")

    def needs_refresh(self, source: str) -> bool:
        if source not in self._active.registry.sources:
            return True
        md = self._read_metadata().get(source, {})
        prov = self._active.provenance[source]
        if prov.observed_cache_sha256 != md.get("sha256"):
            return True
        checked = provenance._parse_ts(md.get("last_checked"))
        return checked is None or (self._now() - checked).total_seconds() >= self._ttl

    def ensure_fresh(self) -> None:
        if not any(self.needs_refresh(s) for s in sources.SOURCES):
            return
        if self.backoff_active:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._refresh_locked()
        finally:
            self._lock.release()

    def refresh(self) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"status": "refresh_in_progress"}
        try:
            before = self._active.registry.fingerprint
            self._refresh_locked()
            after = self._active.registry.fingerprint
            return {"status": "completed", "registry_rebuilt": before != after,
                    "fingerprint_before": before, "fingerprint_after": after,
                    "sources": dict(self._last_result or {})}
        finally:
            self._lock.release()

    # ---- internals ---------------------------------------------------------------
    def _run_sync(self) -> None:
        self._last_attempt_at = self._now().strftime(sync.TIMESTAMP_FORMAT)
        failed, results = False, []
        try:
            results = self._sync_all(force=False)
        except sync.MetadataPersistenceError as exc:
            failed, results = True, exc.results
        except Exception as exc:  # noqa: BLE001 - any sync failure is a failed refresh
            failed, results = True, []
            self._last_result = {"error": str(exc)}
        if any(r.status in _FAILED_STATUSES for r in results):
            failed = True
        if results:
            self._last_result = {r.source_name: r.status for r in results}
        if failed:
            self._last_failed_mono = self._clock()
        else:
            self._last_failed_mono = None

    def _refresh_locked(self) -> None:
        previous = self._active
        self._run_sync()
        self._rebuild(previous=previous, refresh_failed=self._last_failed_mono is not None)

    def _candidate_from(self, source: str, spec: dict, previous_sr):
        sha = storage.sha256_of_spec(spec)
        if previous_sr is not None and sha == previous_sr.spec_sha256:
            return previous_sr, sha, None
        if sha == self._last_rejected_sha.get(source):
            return None, sha, self._rejected.get(source)
        sr, result = gate.build_candidate(source, spec)
        if sr is None:
            self._last_rejected_sha[source] = sha
            return None, sha, {"sha256": sha, "rejected_reason": result.code, "message": result.message}
        return sr, sha, None

    def _rebuild(self, *, previous: Optional[registry.ActiveState], refresh_failed: bool) -> None:
        metadata = self._read_metadata()
        new_sources, observations = {}, {}
        for source in sources.SOURCES:
            prev_sr = previous.registry.sources.get(source) if previous else None
            warnings: list = []
            rejected = None
            served_last_good = False
            spec = self._read_cache_spec(source)
            observed_sha = storage.sha256_of_spec(spec) if spec is not None else None
            chosen = None
            if spec is not None:
                chosen, _, rejected = self._candidate_from(source, spec, prev_sr)
                if chosen is not None and chosen is not prev_sr:
                    if lastgood.last_good_sha(source) != observed_sha:
                        try:
                            self._write_last_good(source, spec)
                        except OSError as exc:
                            warnings.append({"kind": "last_good_write_failed", "message": str(exc)})
            if chosen is None and prev_sr is not None:
                chosen = prev_sr
                served_last_good = source in self._served_from_last_good
            if chosen is None:
                lg = self._read_last_good(source)
                if lg is not None:
                    sr, result = gate.build_candidate(source, lg)
                    if sr is not None:
                        chosen, served_last_good = sr, True
            if served_last_good:
                self._served_from_last_good.add(source)
            else:
                self._served_from_last_good.discard(source)
            if rejected:
                self._rejected[source] = rejected
            elif chosen is not None and not served_last_good:
                self._rejected.pop(source, None)
            if chosen is not None:
                new_sources[source] = chosen
            observations[source] = provenance.SourceObservation(
                source=source, metadata=metadata.get(source, {}), observed_cache_sha256=observed_sha,
                served_from_last_good=served_last_good, rejected=self._rejected.get(source),
                refresh_failed=refresh_failed, extra_warnings=tuple(warnings))
        now = self._now()
        reg = registry.build_registry(new_sources, now.strftime(sync.TIMESTAMP_FORMAT))
        prov = provenance.build_provenance(reg, observations, now=now, ttl_seconds=self._ttl)
        status = RefreshStatus(self._ttl, self._min_retry, self.backoff_active, self._last_attempt_at,
                               self._last_result, False)
        self._active = registry.ActiveState(reg, prov, status)   # single assignment = atomic swap
```

- [ ] **Step 4: Run tests and iterate**

Run: `python -m unittest tests.intelligence.test_manager -v`. Expected: all PASS. Known subtle points if something fails:
- `test_incompatible_cache_falls_back_to_last_good` relies on Task 8's precedence: `served_from_last_good` is reported as the reason while the rejected current cache stays in `candidate`. Do not reorder that precedence.
- `test_unchanged_sha_reuses_source_registry` needs `write_cache` with identical content: `storage.sha256_of_spec` is content-based, so `chosen is prev_sr`.
- `test_gate_failure_keeps_previous_and_does_not_recheck_same_sha` patches `manager.gate.build_candidate`; `_candidate_from` must consult `_last_rejected_sha` **before** calling the gate.

- [ ] **Step 5: Public re-exports**

`tools/atlassian_docs/intelligence/__init__.py`:

```python
"""Atlassian OpenAPI Intelligence — stdlib-only registry, search, and request intelligence."""
from .inspect import get_operation, get_schema  # noqa: F401
from .manager import MIN_RETRY_INTERVAL, RegistryManager  # noqa: F401
from .registry import ActiveState, Registry, RegistryUnavailableError, SourceRegistry  # noqa: F401
from .request_check import MISSING, check_request  # noqa: F401
from .request_template import build_request_template  # noqa: F401
from .search import search_operations  # noqa: F401
```

- [ ] **Step 6: Full suite and commit**

Run: `python -m unittest discover -s tests -t .` → all green (layering included).

```bash
git add tools/atlassian_docs/intelligence/manager.py tools/atlassian_docs/intelligence/__init__.py tools/atlassian_docs/intelligence/provenance.py tests/intelligence/test_manager.py
git commit -m "feat(intelligence): RegistryManager with cache-first startup, backoff, gate-before-swap

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 15: MCP layer — SDK-free tool handlers, FastMCP server, entry point

**Files:**
- Create: `requirements-mcp.txt`
- Create: `tools/atlassian_docs/mcp/__init__.py` (empty)
- Create: `tools/atlassian_docs/mcp/tools.py`
- Create: `tools/atlassian_docs/mcp/server.py`
- Create: `tools/atlassian_docs/mcp/__main__.py`
- Create: `tests/mcp/__init__.py` (empty)
- Create: `tests/mcp/test_tools.py`
- Create: `tests/mcp/test_server.py`

**Interfaces:**
- Consumes: `RegistryManager`, every intelligence function, `request_check.MISSING`.
- Produces:
  - `tools.py`: `MAX_RESULT_BYTES = 200 * 1024`; `TOOL_NAMES = ("search_operations", "get_operation", "get_schema", "build_request_template", "check_request", "get_api_status", "refresh_api_docs")`; `payload_size(payload) -> int`; `guard_size(payload) -> dict`; `run_tool(manager, name: str, arguments: dict) -> dict` (synchronous; calls `manager.ensure_fresh()` for the five intelligence tools, captures `state = manager.active` once, maps `"body"` absent → `MISSING`, wraps unexpected exceptions into `internal_error`, applies `guard_size`); `get_api_status(manager) -> dict`.
  - `server.py`: `create_server(manager) -> FastMCP`; `main(argv=None) -> int`.
  - `__main__.py`: `sys.exit(server.main())`, with the missing-SDK guard (exit 3).

- [ ] **Step 1: Write `requirements-mcp.txt` and install it locally**

```text
mcp>=2.2,<3
```

Run: `pip install -r requirements-mcp.txt`. Then verify the import path the installed version exposes:

```bash
python -c "from mcp.server.fastmcp import FastMCP; print('fastmcp ok')" || python -c "from mcp.server import FastMCP; print('fastmcp at mcp.server')"
python -c "from mcp.shared.memory import create_connected_server_and_client_session; print('memory client ok')"
```

Use whichever import succeeds in `server.py` / `test_server.py` (the code below tries `mcp.server.fastmcp` first and falls back).

- [ ] **Step 2: Write the failing SDK-free handler tests**

`tests/mcp/test_tools.py`:

```python
import datetime
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs import storage, sync
from tools.atlassian_docs.intelligence import manager
from tools.atlassian_docs.mcp import tools

NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=datetime.timezone.utc)
ATT = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"


def make_manager(tmpdir, *fixtures):
    cache = pathlib.Path(tmpdir) / ".atlassian-docs"
    patcher = mock.patch.object(storage, "CACHE_DIR", cache); patcher.start()
    md = {}
    for name in fixtures:
        spec = load_fixture(name); storage.write_cache_spec(name, spec)
        md[name] = {"sha256": storage.sha256_of_spec(spec), "api_version": "v3", "last_checked": NOW.strftime(sync.TIMESTAMP_FORMAT),
                    "last_updated": NOW.strftime(sync.TIMESTAMP_FORMAT), "resolved_documentation_url": "https://d/"}
    storage.write_metadata(md)
    calls = []
    def fake_sync(force=False):
        calls.append(force); return [sync.SyncResult(s, "ok") for s in ("jira-platform", "jira-software", "confluence")]
    m = manager.RegistryManager(sync_all=fake_sync, clock=lambda: 0.0, now=lambda: NOW); m.start()
    m._test_sync_calls = calls  # type: ignore[attr-defined]
    return m, patcher


class TestRunTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.m, patcher = make_manager(self.tmp.name, "jira-platform", "confluence"); self.addCleanup(patcher.stop)

    def test_all_seven_tools_return_dicts(self):
        cases = {
            "search_operations": {"query": "upload attachment to issue"},
            "get_operation": {"key": ATT},
            "get_schema": {"source": "jira-platform", "name": "MultipartFile"},
            "build_request_template": {"key": ATT},
            "check_request": {"key": ATT, "path_params": {"issueIdOrKey": "A-1"}, "body": [{}], "content_type": "multipart/form-data"},
            "get_api_status": {},
            "refresh_api_docs": {},
        }
        for name in tools.TOOL_NAMES:
            out = tools.run_tool(self.m, name, cases[name])
            self.assertIsInstance(out, dict, name); self.assertNotIn("error", out, (name, out))
            json.dumps(out)

    def test_status_shape_and_no_ensure_fresh(self):
        out = tools.run_tool(self.m, "get_api_status", {})
        self.assertEqual(set(out["sources"]), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(out["execution"], "disabled"); self.assertIn("backoff_active", out["refresh"])
        self.assertEqual(self.m._test_sync_calls, [])

    def test_body_absent_vs_null(self):
        absent = tools.run_tool(self.m, "check_request", {"key": ATT, "path_params": {"issueIdOrKey": "A"}, "content_type": "multipart/form-data"})
        self.assertTrue(any(e["rule"] == "body_required" for e in absent["errors"]))
        null = tools.run_tool(self.m, "check_request", {"key": ATT, "path_params": {"issueIdOrKey": "A"}, "body": None, "content_type": "multipart/form-data"})
        self.assertFalse(any(e["rule"] == "body_required" for e in null["errors"]))

    def test_unknown_tool_and_internal_error(self):
        self.assertEqual(tools.run_tool(self.m, "nope", {})["error"]["code"], "invalid_argument")
        with mock.patch("tools.atlassian_docs.mcp.tools.search.search_operations", side_effect=RuntimeError("kaboom")):
            out = tools.run_tool(self.m, "search_operations", {"query": "x"})
        self.assertEqual(out["error"]["code"], "internal_error")

    def test_size_guard(self):
        big = {"blob": "x" * (tools.MAX_RESULT_BYTES + 1)}
        self.assertEqual(tools.guard_size(big)["error"]["code"], "result_too_large")
        self.assertEqual(tools.guard_size({"a": 1}), {"a": 1})
        self.assertEqual(tools.payload_size({"é": 1}), len(json.dumps({"é": 1}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
```

- [ ] **Step 3: Run to verify failure** — ImportError on `tools.atlassian_docs.mcp`.

- [ ] **Step 4: Implement `tools.py`**

`tools/atlassian_docs/mcp/tools.py`:

```python
"""SDK-independent tool handlers. server.py binds these to FastMCP (spec §17)."""
import json
from typing import Any

from ..intelligence import inspect as insp
from ..intelligence import provenance, request_check, request_template, search

MAX_RESULT_BYTES = 200 * 1024
TOOL_NAMES = ("search_operations", "get_operation", "get_schema", "build_request_template",
              "check_request", "get_api_status", "refresh_api_docs")
_FRESHNESS_TOOLS = TOOL_NAMES[:5]


def payload_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def guard_size(payload: dict) -> dict:
    if payload_size(payload) > MAX_RESULT_BYTES:
        return provenance.error_response("result_too_large",
                                         "result exceeds 200 KiB; reduce limit / max_depth / max_nodes / resolve_schema_depth")
    return payload


def get_api_status(manager) -> dict:
    state = manager.active
    return {
        "registry_fingerprint": state.registry.fingerprint, "built_at": state.registry.built_at,
        "sources": {name: p.to_dict() for name, p in state.provenance.items()},
        "refresh": {**state.refresh.to_dict(), "backoff_active": manager.backoff_active},
        "execution": "disabled",
    }


def _dispatch(manager, name: str, args: dict) -> dict:
    if name == "get_api_status":
        return get_api_status(manager)
    if name == "refresh_api_docs":
        return manager.refresh()
    manager.ensure_fresh()
    state = manager.active
    if name == "search_operations":
        return search.search_operations(state, args.get("query", ""), source=args.get("source"), method=args.get("method"),
                                        tag=args.get("tag"), include_deprecated=args.get("include_deprecated", True),
                                        limit=args.get("limit", 10))
    if name == "get_operation":
        return insp.get_operation(state, key=args.get("key"), source=args.get("source"), operation_id=args.get("operation_id"),
                                  include_full_description=args.get("include_full_description", False),
                                  include_response_schemas=args.get("include_response_schemas", False),
                                  resolve_schema_depth=args.get("resolve_schema_depth", 0))
    if name == "get_schema":
        return insp.get_schema(state, args.get("source", ""), args.get("name", ""),
                               max_depth=args.get("max_depth", 2), max_nodes=args.get("max_nodes", 200))
    if name == "build_request_template":
        return request_template.build_request_template(state, args.get("key", ""), args.get("values"))
    if name == "check_request":
        body = args["body"] if "body" in args else request_check.MISSING
        return request_check.check_request(state, args.get("key", ""), path_params=args.get("path_params"),
                                           query=args.get("query"), headers=args.get("headers"), body=body,
                                           content_type=args.get("content_type"))
    return provenance.error_response("invalid_argument", f"unknown tool {name!r}")


def run_tool(manager, name: str, arguments: dict) -> dict:
    try:
        return guard_size(_dispatch(manager, name, arguments or {}))
    except Exception as exc:  # noqa: BLE001 - the server process must never die on a tool error
        return provenance.error_response("internal_error", f"{type(exc).__name__}: {exc}")
```

- [ ] **Step 5: Run handler tests** — `python -m unittest tests.mcp.test_tools -v` → PASS.

- [ ] **Step 6: Write the SDK integration test (skips without SDK)**

`tests/mcp/test_server.py`:

```python
import asyncio
import importlib.util
import json
import tempfile
import unittest

from tests.mcp.test_tools import make_manager

HAS_MCP = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(HAS_MCP, "mcp SDK not installed (pip install -r requirements-mcp.txt)")
class TestServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.m, patcher = make_manager(self.tmp.name, "jira-platform", "confluence"); self.addCleanup(patcher.stop)

    def _call(self, coro):
        return asyncio.run(coro)

    async def _session(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        from tools.atlassian_docs.mcp import server
        srv = server.create_server(self.m)
        return create_connected_server_and_client_session(srv._mcp_server if hasattr(srv, "_mcp_server") else srv)

    def test_tools_list_has_exactly_seven(self):
        async def go():
            async with await self._session() as client:
                result = await client.list_tools()
                return sorted(t.name for t in result.tools)
        from tools.atlassian_docs.mcp import tools
        self.assertEqual(self._call(go()), sorted(tools.TOOL_NAMES))

    def test_each_tool_call_succeeds(self):
        cases = {
            "search_operations": {"query": "upload attachment to issue"},
            "get_operation": {"key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"},
            "get_schema": {"source": "jira-platform", "name": "MultipartFile"},
            "build_request_template": {"key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"},
            "check_request": {"key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments", "path_params": {"issueIdOrKey": "A-1"}},
            "get_api_status": {},
            "refresh_api_docs": {},
        }
        async def go():
            async with await self._session() as client:
                out = {}
                for name, args in cases.items():
                    res = await client.call_tool(name, args)
                    out[name] = (res.isError, json.loads(res.content[0].text))
                return out
        results = self._call(go())
        for name, (is_error, payload) in results.items():
            self.assertFalse(is_error, name); self.assertNotIn("error", payload, name)

    def test_error_marks_is_error(self):
        async def go():
            async with await self._session() as client:
                res = await client.call_tool("get_operation", {"key": "jira-platform:GET:/nope"})
                return res.isError, json.loads(res.content[0].text)
        is_error, payload = self._call(go())
        self.assertTrue(is_error); self.assertEqual(payload["error"]["code"], "operation_not_found")
```

- [ ] **Step 7: Implement `server.py` and `__main__.py`**

`tools/atlassian_docs/mcp/server.py`:

```python
"""FastMCP binding for the seven fixed tools (spec §17). All handlers run the synchronous
intelligence code in a worker thread so the event loop never blocks on Phase 1 sync."""
import asyncio
import json
import sys
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # SDK 2.x layout fallback
    from mcp.server import FastMCP  # type: ignore[no-redef]

from ..intelligence import manager as manager_mod
from ..intelligence import registry
from . import tools

PROVENANCE_NOTE = ("Every result carries `provenance` per source: status fresh|stale|unavailable; when stale, the "
                   "result reflects the last good spec and `active_*` fields describe the spec actually used. "
                   "This server never calls Atlassian APIs; it only reads the official OpenAPI specs.")


def _text(payload: dict):
    return json.dumps(payload, ensure_ascii=False)


def create_server(manager) -> "FastMCP":
    mcp = FastMCP("atlassian-openapi-intelligence")

    @mcp.tool(name="search_operations", description="Weighted English lexical search over official Jira/Confluence OpenAPI operations "
              "(operationId, summary, tags, path, schema names, description). Filters: source, method, tag, include_deprecated, limit (<=50). " + PROVENANCE_NOTE)
    async def search_operations(query: str, source: Optional[str] = None, method: Optional[str] = None, tag: Optional[str] = None,
                                include_deprecated: bool = True, limit: int = 10) -> str:
        return await _run("search_operations", locals())

    @mcp.tool(name="get_operation", description="Compact detail for one operation by canonical key or (source, operation_id). "
              "Options: include_full_description, include_response_schemas, resolve_schema_depth (0-8). " + PROVENANCE_NOTE)
    async def get_operation(key: Optional[str] = None, source: Optional[str] = None, operation_id: Optional[str] = None,
                            include_full_description: bool = False, include_response_schemas: bool = False,
                            resolve_schema_depth: int = 0) -> str:
        return await _run("get_operation", locals())

    @mcp.tool(name="get_schema", description="Resolve a components.schemas entry with bounded depth/nodes; cycles and unresolved refs are marked. " + PROVENANCE_NOTE)
    async def get_schema(source: str, name: str, max_depth: int = 2, max_nodes: int = 200) -> str:
        return await _run("get_schema", locals())

    @mcp.tool(name="build_request_template", description="HTTP request template (method, path, params, content type, body schema, security). "
              "No server URL and no Authorization/Cookie values are ever produced. " + PROVENANCE_NOTE)
    async def build_request_template(key: str, values: Optional[dict] = None) -> str:
        return await _run("build_request_template", locals())

    @mcp.tool(name="check_request", description="Structural check of a planned request against the spec. `compatible` means no error "
              "was found by the fixed rule set listed in `checked`; it does NOT mean the request satisfies every OpenAPI rule (see `not_checked`). "
              "Omit `body` to mean 'no body'; pass null for an explicit JSON null. " + PROVENANCE_NOTE)
    async def check_request(key: str, path_params: Optional[dict] = None, query: Optional[dict] = None, headers: Optional[dict] = None,
                            body: Optional[object] = None, content_type: Optional[str] = None) -> str:
        args = {"key": key, "path_params": path_params, "query": query, "headers": headers, "content_type": content_type}
        if body is not None:      # FastMCP maps both "omitted" and JSON null to None; only a non-null body reaches run_tool
            args["body"] = body
        return await _run("check_request", args)

    @mcp.tool(name="get_api_status", description="Registry fingerprint, per-source provenance and refresh/backoff state. Never triggers a refresh.")
    async def get_api_status() -> str:
        return await _run("get_api_status", {})

    @mcp.tool(name="refresh_api_docs", description="Run the Phase 1 sync (24h TTL respected; no force) and rebuild the registry if the spec changed. "
              "Returns refresh_in_progress if another refresh is running.")
    async def refresh_api_docs() -> str:
        return await _run("refresh_api_docs", {})

    async def _run(name: str, args: dict) -> str:
        payload = await asyncio.to_thread(tools.run_tool, manager, name, args)
        if "error" in payload:
            raise RuntimeError(_text(payload))   # FastMCP converts exceptions into isError=true results
        return _text(payload)

    return mcp


def main(argv=None) -> int:
    mgr = manager_mod.RegistryManager()
    try:
        mgr.start()
    except registry.RegistryUnavailableError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    create_server(mgr).run(transport="stdio")
    return 0
```

Note on `check_request`'s `body`: FastMCP maps JSON `null` to `None` and cannot tell it from omission; the JSON-level distinction is preserved in `tools.run_tool` (Task 15 tests) and documented in the tool description. If the installed SDK exposes raw arguments (e.g. via a `Context`/`**kwargs` mode), prefer that and pass the raw dict through so `null` reaches `run_tool` — check `FastMCP.tool` signature after Step 1 and adapt.

Error surfacing: verify with the installed SDK that raising inside a tool yields `isError=True` with the message as text (Step 6's `test_error_marks_is_error`). If the SDK wraps the message (e.g. `"Error executing tool get_operation: {...}"`), parse the JSON substring in the test with `text[text.index('{'):]`.

`tools/atlassian_docs/mcp/__main__.py`:

```python
import sys

try:
    from . import server
except ImportError as exc:  # mcp SDK missing
    if "mcp" in str(exc):
        print("The MCP layer needs the official SDK: pip install -r requirements-mcp.txt", file=sys.stderr)
        sys.exit(3)
    raise

sys.exit(server.main())
```

- [ ] **Step 8: Run the MCP tests and the whole suite**

Run: `python -m unittest tests.mcp.test_server -v` → PASS (with SDK). Then `pip uninstall -y mcp && python -m unittest discover -s tests -t .` → `test_server` reported as skipped, everything else passes (AC-33); reinstall with `pip install -r requirements-mcp.txt`.

- [ ] **Step 9: Manual stdio smoke**

Run from repo root: `python -m tools.atlassian_docs.mcp` — it must print nothing to stdout before the client handshake and wait on stdin; Ctrl-C to exit. Then add the server to Claude Code (`claude mcp add atlassian-openapi -- python -m tools.atlassian_docs.mcp` from the repo root, or the JSON in spec §17.1) and call `get_api_status` and `search_operations` once from a Claude Code session.

- [ ] **Step 10: Commit**

```bash
git add requirements-mcp.txt tools/atlassian_docs/mcp tests/mcp
git commit -m "feat(mcp): expose seven fixed intelligence tools over the official MCP SDK

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 16: Docs, live smoke, and final acceptance pass

**Files:**
- Create: `tests/live_mcp_smoke.py`
- Modify: `AGENTS.md` (append MCP section)
- Modify: `README.md` (Phase 2 section)
- Modify: `.gitignore` (no change needed — `.atlassian-docs/` already covers `intelligence/`; verify)

- [ ] **Step 1: Live smoke script**

`tests/live_mcp_smoke.py`:

```python
"""Manual, network-required, diagnostic smoke: real sync -> RegistryManager -> search -> inspect -> template.
Never run by unittest discover. Never calls Atlassian product APIs.

    python tests/live_mcp_smoke.py
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.atlassian_docs.intelligence import (RegistryManager, build_request_template,  # noqa: E402
                                               get_operation, search_operations)


def main() -> int:
    t0 = time.perf_counter()
    mgr = RegistryManager()
    mgr.start()
    mgr.refresh()
    state = mgr.active
    print(f"registry build+index: {time.perf_counter() - t0:.2f}s (benchmark target < 1s, not a gate)")
    failed = False
    for name, p in state.provenance.items():
        print(f"[{p.status.upper():11}] {name}: ops={p.operation_count} schemas={p.schema_count} "
              f"openapi={p.active_openapi_version} api={p.active_api_version} reason={p.reason}")
        if p.status == "unavailable":
            failed = True
    res = search_operations(state, "upload attachment to issue", limit=5)
    for r in res.get("results", []):
        print(f"  {r['score']:6.1f} {r['key']}")
    if res.get("results"):
        top = res["results"][0]["key"]
        op = get_operation(state, key=top)
        print(f"top: {op.get('operation_id')} content_types={[m['content_type'] for m in (op.get('request_body') or {}).get('content', [])]}")
        tpl = build_request_template(state, top)
        print(f"template server={tpl.get('server')} missing_required={tpl.get('missing_required')}")
    print("\nFAIL: some source unavailable" if failed else "\nOK: all sources normalized")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

Run it once: `python tests/live_mcp_smoke.py`. Record the build time and the top-5 in the PR description (diagnostic).

- [ ] **Step 2: AGENTS.md — append**

```markdown
## Atlassian OpenAPI Intelligence MCP (Phase 2)

Prefer the MCP server over reading `.atlassian-docs/*.json` directly. Start it from the
repository root: `python -m tools.atlassian_docs.mcp` (needs `pip install -r requirements-mcp.txt`).

Tools: `search_operations` → `get_operation` → `get_schema` → `build_request_template` → `check_request`;
`get_api_status` and `refresh_api_docs` for freshness. Every result carries `provenance`: if a source
is `stale`, the answer comes from the last good spec (`active_*` fields say which). `check_request.compatible`
only means the fixed rule set found no error. The server never calls Jira/Confluence APIs and never
produces server URLs or credentials. Without the MCP SDK, fall back to the Phase 1 CLI and the cached files.
```

- [ ] **Step 3: README.md — add a "Phase 2" section** describing: what the MCP does (one paragraph), install/run commands, the seven tools in a table, the self-update flow (sync → SHA → gate → integrity → last-good → swap), degraded behaviour, offline test command, and links to the v2.1 spec and this plan. Keep the Phase 1 sections intact.

- [ ] **Step 4: Final acceptance pass**

Run and record:

```bash
git diff ffbdd42 -- tools/atlassian_docs/__main__.py tools/atlassian_docs/sources.py tools/atlassian_docs/extractor.py tools/atlassian_docs/sync.py tools/atlassian_docs/storage.py   # must be empty (AC-02)
python -m unittest discover -s tests -t .                                        # all pass (AC-01, AC-34)
grep -rn "valid\"" tools/atlassian_docs/intelligence/request_check.py            # no `valid` key (AC-18)
grep -rn "atlassian.net\|/rest/api/3\|/wiki/api" tools/atlassian_docs/intelligence tools/atlassian_docs/mcp  # only in comments/docstrings if at all (AC-36)
```

Walk spec §23 AC-01…AC-39 and tick each with the test name that covers it; anything without a test gets one before the branch is finished.

- [ ] **Step 5: Commit**

```bash
git add tests/live_mcp_smoke.py AGENTS.md README.md
git commit -m "docs: Phase 2 MCP usage, agent instructions, and live smoke

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## AC → task map

| AC | Task / test |
|---|---|
| 01, 34 | every task's full-suite run; sync is always a fake |
| 02 | Task 16 step 4 |
| 03, 35 | Task 1 `test_layering` |
| 04 | Task 7 `TestCompatibility` |
| 05 | Task 3 `test_canonical_key_and_upper_method`, Task 7 `duplicate_keys` |
| 06, 07 | Task 3 `test_operation_without_operation_id`, Task 10 `test_errors` (ambiguous) |
| 08 | Task 3 `test_operation_level_overrides_path_level_by_name_and_location` |
| 09 | Task 4 `TestResolve` |
| 10, 11, 12 | Task 9 `TestSearchOperations` |
| 13 | Task 10 `test_compact_default` |
| 14 | Task 10 `test_get_schema_and_limits`, Task 4 `test_node_budget` |
| 15, 16 | Task 11 |
| 17, 18 | Task 12 |
| 19, 23 (search scope) | Task 9 `test_limit_bounds_and_provenance_scope`, Task 8 |
| 20, 21 | Task 14 `test_gate_failure_keeps_previous_and_does_not_recheck_same_sha` |
| 22 | Task 14 `test_ensure_fresh_syncs_and_rebuilds_on_sha_change` |
| 23 (last-good restart) | Task 14 `test_incompatible_cache_falls_back_to_last_good` |
| 24 | Task 6 `test_get_schema_returns_copy`, Task 10 `test_output_is_independent_copy` |
| 25 | Task 14 `test_failed_refresh_backoff_only_after_failure` |
| 26, 27 | Task 14 `TestStartup` |
| 28 | Task 14 `test_unavailable_source_recovers_at_runtime` |
| 29 | Task 14 `test_state_snapshot_is_consistent` |
| 30, 31 | Task 15 `test_server` |
| 32 | Task 15 `test_size_guard` |
| 33 | Task 15 step 8 (uninstall run) |
| 36 | Task 16 step 4 grep + review |
| 37 | Task 14 `test_refresh_tool_semantics` |
| 38 | Task 3 `test_experimental_only_when_bool_true` |
| 39 | Task 16 live smoke |
