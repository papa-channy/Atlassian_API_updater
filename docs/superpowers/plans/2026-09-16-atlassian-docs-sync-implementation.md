# Atlassian Docs Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `python -m tools.atlassian_docs`, a zero-dependency CLI that extracts the OpenAPI spec embedded in Atlassian's official Jira/Confluence REST doc pages and caches it locally at a version-independent path.

**Architecture:** Four pure-ish modules with a strict one-way dependency chain (`__main__ → sync → {extractor, storage}`), built bottom-up: `extractor.py` (HTML → OpenAPI dict, no HTTP) → `sources.py` + `storage.py` (config + atomic file I/O) → `sync.py` (HTTP, TTL, version detection, orchestration) → `__main__.py` (CLI, output formatting, exit codes). Each module is testable in isolation; `sync.py` is the only one that touches the network, and tests mock that boundary so the whole suite runs offline.

**Tech Stack:** Python 3, standard library only (`urllib.request`, `re`, `json`, `hashlib`, `pathlib`, `datetime`, `argparse`, `tempfile`, `os`, `dataclasses`, `unittest`, `unittest.mock`). No `pip install`, no `html.parser`.

**Spec:** `docs/superpowers/specs/2026-09-16-atlassian-docs-sync-design.md` (v1.2) — this plan implements it section by section; executors should read both.

## Global Constraints

- Standard library only. No `pip install` anywhere, including tests (`unittest`, not `pytest`). (Spec §31)
- `.atlassian-docs/` is the cache directory, resolved **relative to the current working directory** the CLI is invoked from (the tool is always run as `python -m tools.atlassian_docs` from the repo root). It must never be imported as an absolute/hardcoded path. (Spec §13, §29)
- Every file write (`*.json` in `.atlassian-docs/`) is atomic: write to a `.tmp` file in the same directory, then `os.replace()`. Within one CLI run, all per-source cache writes happen before the single `metadata.json` write. Never write metadata before the cache file it describes. (Spec §22, AC-28)
- `metadata.sha256` is **always** the SHA-256 of `json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` — the canonical form of the OpenAPI dict. Never hash raw file bytes; recovering from a local cache file means parsing it, validating it, canonicalizing it, and hashing *that*. (Spec §22, AC-24)
- `api_version` is derived **only** from the URL path of `resolved_documentation_url`, via `re.search(r"/rest/(v\d+)(?:/|$)", path)`. Never from `info.version`, `paths` keys, query strings, or HTML content. `null` is a normal, successful outcome. (Spec §15, AC-25)
- Extraction requires exactly one `window.__DATA__` assignment in the HTML and exactly one OpenAPI-shaped candidate inside its parsed JSON. Zero or multiple of either is a failure — never "pick the first one." (Spec §8, AC-26, AC-18)
- A failed sync attempt (HTTP error, extraction error, validation error) never updates `last_checked` and never discards an existing usable cache. (Spec §17, §23, AC-23)
- Test files run fully offline: `python -m unittest discover -s tests -t .` (run from the repo root) must pass with zero network access. `tests/live_smoke.py` is the only exception and is never run by that command.
- No new abstractions beyond what's specified — no classes where a function suffices, no product-specific extractor subclasses, no config beyond the three `discovery_url` entries. (Spec §37: Thin extractor / Minimal state / No infrastructure)

---

### Task 1: Extractor — embedded JSON extraction from HTML

**Files:**
- Create: `tools/__init__.py` (empty)
- Create: `tools/atlassian_docs/__init__.py` (empty)
- Create: `tools/atlassian_docs/extractor.py`
- Create: `tests/fixtures/jira-platform-minimal.html`
- Create: `tests/fixtures/confluence-nested-minimal.html`
- Create: `tests/fixtures/marker-whitespace-variant.html`
- Create: `tests/fixtures/missing-data.html`
- Create: `tests/fixtures/malformed-data.html`
- Create: `tests/fixtures/no-openapi.html`
- Create: `tests/fixtures/multiple-openapi.html`
- Create: `tests/fixtures/multiple-data-markers.html` (addition beyond the spec's literal §13 fixture list — needed to exercise AC-26's "more than one `window.__DATA__` assignment" failure mode, which is distinct from "one assignment containing two OpenAPI-shaped candidates")
- Create: `tests/test_extractor.py`

**Interfaces:**
- Produces (used by `sync.py` in Task 4 and `live_smoke.py` in Task 6):
  - `class ExtractionError(Exception)`
  - `class AmbiguousExtractionError(ExtractionError)`
  - `def extract_embedded_data(html: str) -> object`
  - `def is_openapi_candidate(node: object) -> bool`
  - `def find_openapi_candidates(data: object) -> list[dict]`
  - `def extract_openapi_spec(html: str) -> dict`

- [ ] **Step 1: Create the test fixtures**

`tests/fixtures/jira-platform-minimal.html` — reproduces the observed top-level-ish embed shape:

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>
window.__DATA__ = {"openapi": "3.0.1", "info": {"title": "Jira Cloud Platform REST API", "version": "3"}, "paths": {"/issue/{issueIdOrKey}": {}}};
</script>
</body>
</html>
```

`tests/fixtures/confluence-nested-minimal.html` — reproduces the observed nested-under-`"schema"` shape:

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>
window.__DATA__ = {"nav": {"items": []}, "content": {"schema": {"openapi": "3.0.3", "info": {"title": "Confluence Cloud REST API", "version": "2"}, "paths": {"/pages": {}}}}};
</script>
</body>
</html>
```

`tests/fixtures/marker-whitespace-variant.html` — same shape, extra whitespace around `=` to prove the regex marker (not an exact string) is used:

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>
window.__DATA__   =   {"openapi": "3.0.1", "info": {"title": "Whitespace Variant API", "version": "1"}, "paths": {}};
</script>
</body>
</html>
```

`tests/fixtures/missing-data.html` — no marker at all:

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>console.log("no embedded data on this page");</script>
</body>
</html>
```

`tests/fixtures/malformed-data.html` — marker present, JSON body is syntactically invalid (unquoted key):

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>
window.__DATA__ = {"openapi": "3.0.1", "info": {title: "unquoted key breaks JSON"}, "paths": {}};
</script>
</body>
</html>
```

`tests/fixtures/no-openapi.html` — marker present, valid JSON, zero OpenAPI-shaped candidates:

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>
window.__DATA__ = {"nav": {"items": ["a", "b"]}, "user": {"name": "anonymous"}};
</script>
</body>
</html>
```

`tests/fixtures/multiple-openapi.html` — marker present, valid JSON, two OpenAPI-shaped candidates inside the same assignment:

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>
window.__DATA__ = {"first": {"openapi": "3.0.1", "info": {"title": "First API", "version": "1"}, "paths": {}}, "second": {"openapi": "3.0.1", "info": {"title": "Second API", "version": "1"}, "paths": {}}};
</script>
</body>
</html>
```

`tests/fixtures/multiple-data-markers.html` — two separate `window.__DATA__` assignments on the page:

```html
<!DOCTYPE html>
<html>
<body>
<div id="root"></div>
<script>
window.__DATA__ = {"openapi": "3.0.1", "info": {"title": "First", "version": "1"}, "paths": {}};
</script>
<script>
window.__DATA__ = {"openapi": "3.0.1", "info": {"title": "Second", "version": "1"}, "paths": {}};
</script>
</body>
</html>
```

- [ ] **Step 2: Write the failing test suite**

Create `tests/test_extractor.py`:

```python
import pathlib
import unittest

from tools.atlassian_docs import extractor

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestExtractOpenApiSpec(unittest.TestCase):
    def test_extracts_top_level_spec(self):
        spec = extractor.extract_openapi_spec(_read("jira-platform-minimal.html"))
        self.assertEqual(spec["openapi"], "3.0.1")
        self.assertEqual(spec["info"]["title"], "Jira Cloud Platform REST API")

    def test_extracts_nested_spec(self):
        spec = extractor.extract_openapi_spec(_read("confluence-nested-minimal.html"))
        self.assertEqual(spec["info"]["title"], "Confluence Cloud REST API")

    def test_tolerates_marker_whitespace_variants(self):
        spec = extractor.extract_openapi_spec(_read("marker-whitespace-variant.html"))
        self.assertEqual(spec["info"]["title"], "Whitespace Variant API")

    def test_missing_marker_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("missing-data.html"))

    def test_malformed_json_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("malformed-data.html"))

    def test_zero_candidates_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("no-openapi.html"))

    def test_multiple_candidates_raises_ambiguous_error(self):
        with self.assertRaises(extractor.AmbiguousExtractionError):
            extractor.extract_openapi_spec(_read("multiple-openapi.html"))

    def test_ambiguous_error_is_an_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("multiple-openapi.html"))

    def test_multiple_data_markers_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("multiple-data-markers.html"))


class TestIsOpenApiCandidate(unittest.TestCase):
    def test_accepts_empty_paths(self):
        node = {"openapi": "3.0.1", "info": {}, "paths": {}}
        self.assertTrue(extractor.is_openapi_candidate(node))

    def test_rejects_missing_info(self):
        node = {"openapi": "3.0.1", "paths": {}}
        self.assertFalse(extractor.is_openapi_candidate(node))

    def test_rejects_missing_paths(self):
        node = {"openapi": "3.0.1", "info": {}}
        self.assertFalse(extractor.is_openapi_candidate(node))

    def test_rejects_non_dict(self):
        self.assertFalse(extractor.is_openapi_candidate("not a dict"))
        self.assertFalse(extractor.is_openapi_candidate(["a", "list"]))
        self.assertFalse(extractor.is_openapi_candidate(None))


class TestFindOpenApiCandidates(unittest.TestCase):
    def test_finds_candidate_nested_in_list(self):
        data = {"items": [{"not": "it"}, {"openapi": "3.0.1", "info": {}, "paths": {}}]}
        candidates = extractor.find_openapi_candidates(data)
        self.assertEqual(len(candidates), 1)

    def test_returns_empty_list_when_no_candidates(self):
        self.assertEqual(extractor.find_openapi_candidates({"a": 1, "b": [1, 2, 3]}), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail on import**

Run: `python -m unittest discover -s tests -t . -v`
Expected: `ModuleNotFoundError: No module named 'tools.atlassian_docs.extractor'` (or similar import failure) — `tools/atlassian_docs/extractor.py` doesn't exist yet.

- [ ] **Step 4: Implement `tools/atlassian_docs/extractor.py`**

```python
"""Pure-function extraction of the embedded OpenAPI spec from an Atlassian
REST documentation page's HTML. Knows nothing about HTTP.
"""
import json
import re

_MARKER_PATTERN = re.compile(r"window\.__DATA__\s*=\s*")


class ExtractionError(Exception):
    """Raised when the embedded OpenAPI spec cannot be extracted from HTML."""


class AmbiguousExtractionError(ExtractionError):
    """Raised when more than one OpenAPI-shaped candidate is found."""


def extract_embedded_data(html: str) -> object:
    """Find the single `window.__DATA__ = ...` assignment and JSON-decode
    the value that follows it. Raises ExtractionError if there isn't
    exactly one assignment, or if the JSON after it doesn't parse.
    """
    matches = list(_MARKER_PATTERN.finditer(html))
    if len(matches) != 1:
        raise ExtractionError(
            f"expected exactly 1 window.__DATA__ assignment, found {len(matches)}"
        )
    start = matches[0].end()
    try:
        data, _ = json.JSONDecoder().raw_decode(html, start)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"failed to decode JSON after window.__DATA__: {exc}"
        ) from exc
    return data


def is_openapi_candidate(node: object) -> bool:
    return (
        isinstance(node, dict)
        and isinstance(node.get("openapi"), str)
        and isinstance(node.get("info"), dict)
        and isinstance(node.get("paths"), dict)
    )


def find_openapi_candidates(data: object) -> list:
    """Iterative (stack-based, not recursive) DFS over the parsed tree."""
    stack = [data]
    found = []
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if is_openapi_candidate(node):
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def extract_openapi_spec(html: str) -> dict:
    """Extract the single embedded OpenAPI spec from a documentation
    page's HTML. Raises ExtractionError (or its subclass
    AmbiguousExtractionError) on any failure to find exactly one.
    """
    data = extract_embedded_data(html)
    candidates = find_openapi_candidates(data)
    if len(candidates) == 0:
        raise ExtractionError("no OpenAPI candidate found in embedded data")
    if len(candidates) > 1:
        raise AmbiguousExtractionError(
            f"expected exactly 1 OpenAPI candidate, found {len(candidates)}"
        )
    return candidates[0]
```

Also create the two empty `__init__.py` files:

```bash
mkdir -p tools/atlassian_docs
touch tools/__init__.py tools/atlassian_docs/__init__.py
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: all `TestExtractOpenApiSpec`, `TestIsOpenApiCandidate`, `TestFindOpenApiCandidates` tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/__init__.py tools/atlassian_docs/__init__.py tools/atlassian_docs/extractor.py tests/fixtures tests/test_extractor.py
git commit -m "feat: add embedded-JSON OpenAPI extractor"
```

---

### Task 2: `sources.py` and `storage.py` — config and persistence

**Files:**
- Create: `tools/atlassian_docs/sources.py`
- Create: `tools/atlassian_docs/storage.py`
- Create: `tests/test_sources.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: nothing from Task 1 (this task is independent of `extractor.py`, but both are consumed by `sync.py` in Tasks 3-4).
- Produces (used by `sync.py` in Task 4 and `__main__.py` in Task 5):
  - `sources.SOURCES: dict[str, dict[str, str]]`
  - `storage.CACHE_DIR: pathlib.Path`
  - `storage.canonical_json_bytes(spec: dict) -> bytes`
  - `storage.sha256_of_spec(spec: dict) -> str`
  - `storage.cache_path(source_name: str) -> pathlib.Path`
  - `storage.metadata_path() -> pathlib.Path`
  - `storage.ensure_cache_dir() -> None`
  - `storage.read_metadata() -> dict`
  - `storage.write_metadata(metadata: dict) -> None`
  - `storage.read_cache_spec(source_name: str) -> dict | None`
  - `storage.write_cache_spec(source_name: str, spec: dict) -> None`

- [ ] **Step 1: Write the failing test for `sources.py`**

Create `tests/test_sources.py`:

```python
import unittest

from tools.atlassian_docs import sources


class TestSources(unittest.TestCase):
    def test_has_exactly_the_three_expected_sources(self):
        self.assertEqual(
            set(sources.SOURCES.keys()),
            {"jira-platform", "jira-software", "confluence"},
        )

    def test_each_source_has_only_a_discovery_url(self):
        for name, config in sources.SOURCES.items():
            self.assertEqual(set(config.keys()), {"discovery_url"})
            self.assertTrue(config["discovery_url"].startswith("https://developer.atlassian.com/"))

    def test_no_version_strings_in_configuration(self):
        # AC-02/AC-03: no version or CDN URLs baked into config.
        serialized = str(sources.SOURCES)
        for forbidden in ("v1", "v2", "v3", "v4", "dac-static", "swagger"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
```

Run: `python -m unittest tests.test_sources -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `tools/atlassian_docs/sources.py`**

```python
"""Stable, version-independent discovery URLs. Nothing else lives here —
no version strings, no CDN URLs. See spec §6.
"""

SOURCES = {
    "jira-platform": {
        "discovery_url": "https://developer.atlassian.com/cloud/jira/platform/rest/",
    },
    "jira-software": {
        "discovery_url": "https://developer.atlassian.com/cloud/jira/software/rest/",
    },
    "confluence": {
        "discovery_url": "https://developer.atlassian.com/cloud/confluence/rest/",
    },
}
```

Run: `python -m unittest tests.test_sources -v`
Expected: PASS.

- [ ] **Step 3: Write the failing tests for `storage.py`**

Create `tests/test_storage.py`:

```python
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tools.atlassian_docs import storage


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patcher = mock.patch.object(
            storage, "CACHE_DIR", pathlib.Path(self._tmpdir.name) / ".atlassian-docs"
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()


class TestCanonicalJson(StorageTestCase):
    def test_key_order_does_not_affect_hash(self):
        spec_a = {"openapi": "3.0.1", "info": {"title": "X"}, "paths": {}}
        spec_b = {"paths": {}, "info": {"title": "X"}, "openapi": "3.0.1"}
        self.assertEqual(storage.sha256_of_spec(spec_a), storage.sha256_of_spec(spec_b))

    def test_different_content_produces_different_hash(self):
        spec_a = {"openapi": "3.0.1", "info": {"title": "X"}, "paths": {}}
        spec_b = {"openapi": "3.0.1", "info": {"title": "Y"}, "paths": {}}
        self.assertNotEqual(storage.sha256_of_spec(spec_a), storage.sha256_of_spec(spec_b))


class TestMetadataRoundtrip(StorageTestCase):
    def test_read_missing_metadata_returns_empty_dict(self):
        self.assertEqual(storage.read_metadata(), {})

    def test_write_then_read_roundtrips(self):
        metadata = {"jira-platform": {"api_version": "v3"}}
        storage.write_metadata(metadata)
        self.assertEqual(storage.read_metadata(), metadata)

    def test_write_creates_cache_dir(self):
        self.assertFalse(storage.CACHE_DIR.exists())
        storage.write_metadata({})
        self.assertTrue(storage.CACHE_DIR.is_dir())

    def test_write_leaves_no_tmp_files_behind(self):
        storage.write_metadata({"a": 1})
        leftovers = list(storage.CACHE_DIR.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class TestCacheSpecRoundtrip(StorageTestCase):
    def test_read_missing_cache_returns_none(self):
        self.assertIsNone(storage.read_cache_spec("jira-platform"))

    def test_write_then_read_roundtrips(self):
        spec = {"openapi": "3.0.1", "info": {"title": "X"}, "paths": {}}
        storage.write_cache_spec("jira-platform", spec)
        self.assertEqual(storage.read_cache_spec("jira-platform"), spec)

    def test_read_malformed_cache_file_returns_none(self):
        storage.ensure_cache_dir()
        storage.cache_path("jira-platform").write_text("{not valid json", encoding="utf-8")
        self.assertIsNone(storage.read_cache_spec("jira-platform"))

    def test_cache_filename_has_no_version_in_it(self):
        self.assertEqual(storage.cache_path("jira-platform").name, "jira-platform.json")


if __name__ == "__main__":
    unittest.main()
```

Run: `python -m unittest tests.test_storage -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `tools/atlassian_docs/storage.py`**

```python
"""Local file I/O for the cache and metadata. Knows nothing about Jira,
Confluence, or HTTP — just JSON files under CACHE_DIR, written atomically.
"""
import hashlib
import json
import os
import pathlib
import tempfile
from typing import Optional

CACHE_DIR = pathlib.Path(".atlassian-docs")
METADATA_FILENAME = "metadata.json"


def canonical_json_bytes(spec: dict) -> bytes:
    return json.dumps(
        spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_of_spec(spec: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(spec)).hexdigest()


def cache_path(source_name: str) -> pathlib.Path:
    return CACHE_DIR / f"{source_name}.json"


def metadata_path() -> pathlib.Path:
    return CACHE_DIR / METADATA_FILENAME


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path: pathlib.Path, text: str) -> None:
    ensure_cache_dir()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def read_metadata() -> dict:
    path = metadata_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_metadata(metadata: dict) -> None:
    text = json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False)
    _atomic_write_text(metadata_path(), text)


def read_cache_spec(source_name: str) -> Optional[dict]:
    path = cache_path(source_name)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return None


def write_cache_spec(source_name: str, spec: dict) -> None:
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False)
    _atomic_write_text(cache_path(source_name), text)
```

- [ ] **Step 5: Run the full test suite and confirm everything passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: all tests from Task 1 and Task 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/atlassian_docs/sources.py tools/atlassian_docs/storage.py tests/test_sources.py tests/test_storage.py
git commit -m "feat: add source configuration and atomic cache/metadata storage"
```

---

### Task 3: `sync.py` part 1 — version detection and HTTP fetch

**Files:**
- Create: `tools/atlassian_docs/sync.py`
- Create: `tests/test_sync.py`

**Interfaces:**
- Consumes: nothing yet from Task 1/2 (these two helpers are self-contained; `sync.py` will import `extractor` and `storage` in Task 4).
- Produces (used later in this same file in Task 4, and by `__main__.py` in Task 5):
  - `class FetchError(Exception)`
  - `def detect_api_version(resolved_url: str) -> tuple[str | None, str | None]`
  - `def fetch_documentation_html(discovery_url: str, timeout: float = 10.0) -> tuple[str, str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sync.py`:

```python
import urllib.error
import unittest
from unittest import mock

from tools.atlassian_docs import sync


class TestDetectApiVersion(unittest.TestCase):
    def test_detects_v3_segment(self):
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/jira/platform/rest/v3/"
        )
        self.assertEqual(version, "v3")
        self.assertEqual(source, "documentation_url")

    def test_detects_v2_segment(self):
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/confluence/rest/v2/"
        )
        self.assertEqual(version, "v2")
        self.assertEqual(source, "documentation_url")

    def test_returns_null_when_no_version_segment(self):
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/jira/software/rest/"
        )
        self.assertIsNone(version)
        self.assertIsNone(source)

    def test_does_not_match_non_version_path_segment(self):
        # Jira Software's real shape: /rest/agile/1.0/... must NOT match.
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/jira/software/rest/agile/1.0/"
        )
        self.assertIsNone(version)
        self.assertIsNone(source)

    def test_ignores_version_looking_segments_outside_rest_path(self):
        version, _ = sync.detect_api_version(
            "https://developer.atlassian.com/v3/cloud/jira/software/rest/"
        )
        self.assertIsNone(version)


class TestFetchDocumentationHtml(unittest.TestCase):
    def _fake_response(self, url, body):
        response = mock.MagicMock()
        response.geturl.return_value = url
        response.read.return_value = body.encode("utf-8")
        response.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    def test_returns_resolved_url_and_html_on_success(self):
        fake_response = self._fake_response("https://example.com/final/", "<html>ok</html>")
        with mock.patch(
            "tools.atlassian_docs.sync.urllib.request.urlopen", return_value=fake_response
        ):
            resolved_url, html = sync.fetch_documentation_html("https://example.com/start/")
        self.assertEqual(resolved_url, "https://example.com/final/")
        self.assertEqual(html, "<html>ok</html>")

    def test_wraps_url_error_as_fetch_error(self):
        with mock.patch(
            "tools.atlassian_docs.sync.urllib.request.urlopen",
            side_effect=urllib.error.URLError("boom"),
        ):
            with self.assertRaises(sync.FetchError):
                sync.fetch_documentation_html("https://example.com/start/")

    def test_wraps_timeout_as_fetch_error(self):
        with mock.patch(
            "tools.atlassian_docs.sync.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            with self.assertRaises(sync.FetchError):
                sync.fetch_documentation_html("https://example.com/start/")


if __name__ == "__main__":
    unittest.main()
```

Run: `python -m unittest tests.test_sync -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Implement the first part of `tools/atlassian_docs/sync.py`**

```python
"""Orchestration: HTTP fetch, TTL, version detection, cache/metadata
reconciliation, and per-source failure policy. This is the only module
that knows about HTTP and ties extractor.py + storage.py together.
"""
import re
import urllib.error
import urllib.parse
import urllib.request

_VERSION_SEGMENT_PATTERN = re.compile(r"/rest/(v\d+)(?:/|$)")


class FetchError(Exception):
    """Raised when the discovery URL cannot be fetched successfully."""


def detect_api_version(resolved_url: str):
    """Returns (api_version, api_version_source). Both None if the URL
    path has no explicit /rest/vN/ segment. See spec §15 — this is the
    ONLY source of api_version; info.version and paths are never used.
    """
    path = urllib.parse.urlparse(resolved_url).path
    match = _VERSION_SEGMENT_PATTERN.search(path)
    if match is None:
        return None, None
    return match.group(1), "documentation_url"


def fetch_documentation_html(discovery_url: str, timeout: float = 10.0):
    """GET discovery_url, following redirects (urllib does this by
    default). Returns (resolved_url, html). Raises FetchError on any
    network/HTTP failure.
    """
    request = urllib.request.Request(
        discovery_url, headers={"User-Agent": "atlassian-docs-sync/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            resolved_url = response.geturl()
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"failed to fetch {discovery_url}: {exc}") from exc
    return resolved_url, html
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: `python -m unittest tests.test_sync -v`
Expected: all `TestDetectApiVersion` and `TestFetchDocumentationHtml` tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/atlassian_docs/sync.py tests/test_sync.py
git commit -m "feat: add HTTP fetch and URL-based API version detection"
```

---

### Task 4: `sync.py` part 2 — `sync_source`, `sync_all`, exit code

This is the core of the whole tool: it implements the Update Algorithm from spec §20, including the cache/metadata self-heal rule (§22) and the fail-safe fallback policy (§23).

**Files:**
- Modify: `tools/atlassian_docs/sync.py` (append to the file created in Task 3)
- Modify: `tests/test_sync.py` (append new test classes; keep the ones from Task 3)

**Interfaces:**
- Consumes: `extractor.ExtractionError`, `extractor.extract_openapi_spec`, `extractor.is_openapi_candidate` (Task 1); `storage.read_metadata`, `storage.write_metadata`, `storage.read_cache_spec`, `storage.write_cache_spec`, `storage.sha256_of_spec` (Task 2); `sources.SOURCES` (Task 2); `FetchError`, `fetch_documentation_html`, `detect_api_version` (this file, Task 3).
- Produces (used by `__main__.py` in Task 5 and `live_smoke.py` in Task 6):
  - `@dataclasses.dataclass class SyncResult` with fields `source_name: str`, `status: str`, `api_version: str | None`, `previous_api_version: str | None`, `message: str` — `status` is one of `"ok"`, `"updated"`, `"version_changed"`, `"warn_fallback"`, `"error_unavailable"`.
  - `TTL_SECONDS: int`
  - `def sync_source(source_name: str, discovery_url: str, metadata: dict, force: bool) -> SyncResult` — **mutates `metadata[source_name]` in place** on any successful fetch/extraction (even if the cached file content didn't change), so the caller can persist it.
  - `def sync_all(force: bool = False) -> list[SyncResult]`
  - `def exit_code_for(results: list[SyncResult]) -> int`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sync.py` (add these imports at the top alongside the existing ones, and these new classes at the end of the file):

```python
import datetime
import pathlib
import tempfile

from tools.atlassian_docs import extractor, sources, storage
```

```python
SPEC_V1 = {"openapi": "3.0.1", "info": {"title": "X", "version": "1"}, "paths": {"/a": {}}}
SPEC_V2 = {"openapi": "3.0.1", "info": {"title": "X", "version": "2"}, "paths": {"/a": {}, "/b": {}}}


class SyncSourceTestCase(unittest.TestCase):
    """Shared setup: an isolated cache dir, and a helper to seed it."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patcher = mock.patch.object(
            storage, "CACHE_DIR", pathlib.Path(self._tmpdir.name) / ".atlassian-docs"
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def _seed_consistent_cache(self, source_name, spec, last_checked_iso):
        storage.write_cache_spec(source_name, spec)
        metadata = {
            source_name: {
                "resolved_documentation_url": "https://developer.atlassian.com/cloud/x/rest/v1/",
                "extraction_method": "embedded_window_data",
                "api_version": "v1",
                "api_version_source": "documentation_url",
                "spec_info_version": "1",
                "last_checked": last_checked_iso,
                "last_updated": last_checked_iso,
                "sha256": storage.sha256_of_spec(spec),
            }
        }
        return metadata

    def _fresh_timestamp(self):
        return sync._now_iso()

    def _stale_timestamp(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
        return past.strftime(sync._TIMESTAMP_FORMAT)


class TestSyncSourceCacheHit(SyncSourceTestCase):
    def test_uses_cache_without_fetching_when_ttl_valid_and_consistent(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._fresh_timestamp())
        with mock.patch("tools.atlassian_docs.sync.fetch_documentation_html") as fake_fetch:
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        fake_fetch.assert_not_called()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.api_version, "v1")

    def test_force_ignores_fresh_ttl_and_fetches_anyway(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._fresh_timestamp())
        html = "<script>window.__DATA__ = " + json.dumps(SPEC_V1) + ";</script>"
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v1/", html),
        ) as fake_fetch:
            sync.sync_source("jira-platform", "https://x/", metadata, force=True)
        fake_fetch.assert_called_once()


class TestSyncSourceRefresh(SyncSourceTestCase):
    def _html_for(self, spec):
        return "<script>window.__DATA__ = " + json.dumps(spec) + ";</script>"

    def test_refetches_when_ttl_expired_and_marks_ok_if_unchanged(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v1/", self._html_for(SPEC_V1)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "ok")
        self.assertIsNone(storage.read_cache_spec("jira-platform"))  # unchanged -> not rewritten

    def test_marks_updated_when_spec_content_changes(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v1/", self._html_for(SPEC_V2)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "updated")
        self.assertEqual(storage.read_cache_spec("jira-platform"), SPEC_V2)
        self.assertEqual(metadata["jira-platform"]["sha256"], storage.sha256_of_spec(SPEC_V2))

    def test_marks_version_changed_when_both_versions_are_non_null_and_differ(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v4/", self._html_for(SPEC_V2)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "version_changed")
        self.assertEqual(result.previous_api_version, "v1")
        self.assertEqual(result.api_version, "v4")

    def test_does_not_flag_version_change_when_previous_is_null(self):
        metadata = {}  # first run, no prior metadata for this source
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v3/", self._html_for(SPEC_V1)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "updated")  # not "version_changed"
        self.assertEqual(result.api_version, "v3")


class TestSyncSourceFailurePolicy(SyncSourceTestCase):
    def test_falls_back_on_fetch_error_when_cache_is_valid(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("network down"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "warn_fallback")
        # last_checked must NOT be updated on failure (AC-23):
        self.assertEqual(metadata["jira-platform"]["last_checked"], self._stale_timestamp())

    def test_falls_back_on_extraction_error_when_cache_is_valid(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://x/rest/", "<html>no marker here</html>"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "warn_fallback")

    def test_unavailable_when_fetch_fails_and_no_cache_exists(self):
        metadata = {}
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("network down"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "error_unavailable")

    def test_unavailable_when_fetch_fails_and_local_cache_is_corrupt(self):
        storage.ensure_cache_dir()
        storage.cache_path("jira-platform").write_text("not json", encoding="utf-8")
        metadata = {"jira-platform": {"sha256": "irrelevant", "last_checked": self._stale_timestamp()}}
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("network down"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "error_unavailable")


class TestSyncSourceSelfHeal(SyncSourceTestCase):
    def test_mismatched_but_structurally_valid_cache_is_still_a_usable_fallback(self):
        # Simulate the crash-recovery scenario from spec §22: cache file
        # on disk doesn't match metadata.sha256 (as if metadata write was
        # interrupted), but the cache file itself is valid JSON+OpenAPI.
        storage.write_cache_spec("jira-platform", SPEC_V1)
        metadata = {
            "jira-platform": {
                "sha256": "0" * 64,  # deliberately wrong, forces a mismatch
                "last_checked": self._fresh_timestamp(),  # even though "fresh"...
                "api_version": "v1",
            }
        }
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html"
        ) as fake_fetch:
            fake_fetch.side_effect = sync.FetchError("network down")
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        # mismatch must have skipped the TTL fast-path (fetch was attempted):
        fake_fetch.assert_called_once()
        # and since the cache itself is structurally valid, it's a usable fallback:
        self.assertEqual(result.status, "warn_fallback")


class TestSyncAllAndExitCode(SyncSourceTestCase):
    def test_sync_all_returns_one_result_per_configured_source(self):
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("offline"),
        ):
            results = sync.sync_all(force=False)
        self.assertEqual({r.source_name for r in results}, set(sources.SOURCES.keys()))

    def test_exit_code_all_ok_is_zero(self):
        results = [sync.SyncResult(source_name="a", status="ok")]
        self.assertEqual(sync.exit_code_for(results), 0)

    def test_exit_code_updated_and_version_changed_are_also_zero(self):
        results = [
            sync.SyncResult(source_name="a", status="updated"),
            sync.SyncResult(source_name="b", status="version_changed"),
        ]
        self.assertEqual(sync.exit_code_for(results), 0)

    def test_exit_code_one_warn_fallback_is_one(self):
        results = [
            sync.SyncResult(source_name="a", status="ok"),
            sync.SyncResult(source_name="b", status="warn_fallback"),
        ]
        self.assertEqual(sync.exit_code_for(results), 1)

    def test_exit_code_one_error_unavailable_is_two(self):
        results = [
            sync.SyncResult(source_name="a", status="warn_fallback"),
            sync.SyncResult(source_name="b", status="error_unavailable"),
        ]
        self.assertEqual(sync.exit_code_for(results), 2)
```

Also add `import json` to the top of `tests/test_sync.py` if not already present.

Run: `python -m unittest tests.test_sync -v`
Expected: FAIL — `sync.SyncResult`, `sync.sync_source`, `sync.sync_all`, `sync.exit_code_for`, `sync._now_iso`, `sync._TIMESTAMP_FORMAT` don't exist yet.

- [ ] **Step 2: Append the orchestration logic to `tools/atlassian_docs/sync.py`**

Add these imports to the top of the file (alongside the existing `re`, `urllib.*`):

```python
import dataclasses
import datetime
from typing import Optional

from . import extractor, storage
```

Append to the end of `tools/atlassian_docs/sync.py`:

```python
TTL_SECONDS = 24 * 60 * 60
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(_TIMESTAMP_FORMAT)


def _parse_timestamp(value: Optional[str]):
    if value is None:
        return None
    return datetime.datetime.strptime(value, _TIMESTAMP_FORMAT).replace(
        tzinfo=datetime.timezone.utc
    )


@dataclasses.dataclass
class SyncResult:
    source_name: str
    status: str  # "ok" | "updated" | "version_changed" | "warn_fallback" | "error_unavailable"
    api_version: Optional[str] = None
    previous_api_version: Optional[str] = None
    message: str = ""


def _read_valid_cache_spec(source_name: str):
    """The cached spec if it exists, parses as JSON, and passes OpenAPI
    structural validation — regardless of whether it matches metadata.
    This is what "usable as a fallback" means (spec §22).
    """
    spec = storage.read_cache_spec(source_name)
    if spec is None or not extractor.is_openapi_candidate(spec):
        return None
    return spec


def _cache_matches_metadata(source_name: str, source_meta: dict) -> bool:
    """True only if the on-disk cache is structurally valid AND its
    canonical hash equals metadata.sha256. This gates the TTL fast-path —
    it is stricter than _read_valid_cache_spec, which only gates fallback
    eligibility after a failed refresh.
    """
    valid_spec = _read_valid_cache_spec(source_name)
    if valid_spec is None:
        return False
    expected_sha = source_meta.get("sha256")
    if expected_sha is None:
        return False
    return storage.sha256_of_spec(valid_spec) == expected_sha


def sync_source(
    source_name: str, discovery_url: str, metadata: dict, force: bool
) -> SyncResult:
    """Implements the Update Algorithm from spec §20. Mutates
    metadata[source_name] in place on any successful attempt.
    """
    source_meta = metadata.get(source_name, {})
    has_valid_fallback = _read_valid_cache_spec(source_name) is not None

    if not force and _cache_matches_metadata(source_name, source_meta):
        last_checked = _parse_timestamp(source_meta.get("last_checked"))
        if last_checked is not None:
            age = (datetime.datetime.now(datetime.timezone.utc) - last_checked).total_seconds()
            if age < TTL_SECONDS:
                return SyncResult(
                    source_name=source_name,
                    status="ok",
                    api_version=source_meta.get("api_version"),
                    message=f"cache valid ({source_meta.get('api_version') or 'unknown'})",
                )

    try:
        resolved_url, html = fetch_documentation_html(discovery_url)
        spec = extractor.extract_openapi_spec(html)
    except (FetchError, extractor.ExtractionError) as exc:
        if has_valid_fallback:
            return SyncResult(
                source_name=source_name,
                status="warn_fallback",
                api_version=source_meta.get("api_version"),
                message=str(exc),
            )
        return SyncResult(source_name=source_name, status="error_unavailable", message=str(exc))

    digest = storage.sha256_of_spec(spec)
    api_version, api_version_source = detect_api_version(resolved_url)
    previous_api_version = source_meta.get("api_version")
    now_iso = _now_iso()

    new_meta = dict(source_meta)
    new_meta.update(
        {
            "resolved_documentation_url": resolved_url,
            "extraction_method": "embedded_window_data",
            "api_version": api_version,
            "api_version_source": api_version_source,
            "spec_info_version": spec.get("info", {}).get("version"),
            "last_checked": now_iso,
            "sha256": digest,
        }
    )

    changed = digest != source_meta.get("sha256")
    if changed:
        storage.write_cache_spec(source_name, spec)
        new_meta["last_updated"] = now_iso
    else:
        new_meta["last_updated"] = source_meta.get("last_updated", now_iso)

    metadata[source_name] = new_meta

    version_changed = (
        previous_api_version is not None
        and api_version is not None
        and previous_api_version != api_version
    )

    if version_changed:
        status = "version_changed"
    elif changed:
        status = "updated"
    else:
        status = "ok"

    return SyncResult(
        source_name=source_name,
        status=status,
        api_version=api_version,
        previous_api_version=previous_api_version if version_changed else None,
        message="specification changed" if changed else f"cache valid ({api_version or 'unknown'})",
    )


def sync_all(force: bool = False) -> list:
    from . import sources  # local import: avoids a module-load cycle with __main__

    metadata = storage.read_metadata()
    results = [
        sync_source(name, config["discovery_url"], metadata, force)
        for name, config in sources.SOURCES.items()
    ]
    storage.write_metadata(metadata)  # written once, after every cache file is already on disk
    return results


def exit_code_for(results) -> int:
    if any(r.status == "error_unavailable" for r in results):
        return 2
    if any(r.status == "warn_fallback" for r in results):
        return 1
    return 0
```

Note: `sources` is imported locally inside `sync_all` rather than at module top level. This is deliberate — `sources.py` has no dependency on `sync.py`, but importing it at the top would work fine too; the local import is just to keep the top-level import block focused on what `sync_source` itself needs (`extractor`, `storage`). If you prefer, a top-level `from . import sources` is equally correct — either way, do not import `sync` from `sources.py` (see Global Constraints: `__main__ → sync → {extractor, storage}` is the only allowed direction).

- [ ] **Step 3: Run the tests and confirm they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: every test in `tests/test_sync.py` (Task 3's and Task 4's) PASSes, and Task 1/2 tests still pass.

- [ ] **Step 4: Commit**

```bash
git add tools/atlassian_docs/sync.py tests/test_sync.py
git commit -m "feat: implement sync orchestration with TTL, self-heal, and fail-safe fallback"
```

---

### Task 5: `__main__.py` — CLI

**Files:**
- Create: `tools/atlassian_docs/__main__.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `sync.SyncResult`, `sync.sync_all`, `sync.exit_code_for`, `sync._TIMESTAMP_FORMAT` (Task 3-4); `storage.read_metadata` (Task 2); `sources.SOURCES` (Task 2).
- Produces: `def main(argv: list[str] | None = None) -> int` — the process entry point.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import unittest
from unittest import mock

from tools.atlassian_docs import __main__ as cli
from tools.atlassian_docs import sync


class TestFormatResultLines(unittest.TestCase):
    def test_ok_status(self):
        result = sync.SyncResult(source_name="jira-platform", status="ok", api_version="v3")
        self.assertEqual(
            cli._format_result_lines(result), ["[OK] jira-platform: cache valid (v3)"]
        )

    def test_updated_status(self):
        result = sync.SyncResult(source_name="confluence", status="updated", api_version="v2")
        self.assertEqual(
            cli._format_result_lines(result),
            ["[UPDATED] confluence: specification changed"],
        )

    def test_version_changed_status(self):
        result = sync.SyncResult(
            source_name="jira-platform",
            status="version_changed",
            api_version="v4",
            previous_api_version="v3",
        )
        self.assertEqual(
            cli._format_result_lines(result),
            ["[VERSION] jira-platform: v3 -> v4", "[UPDATED] jira-platform"],
        )

    def test_warn_fallback_status(self):
        result = sync.SyncResult(
            source_name="jira-software",
            status="warn_fallback",
            message="OpenAPI extraction failed (0 candidates)",
        )
        self.assertEqual(
            cli._format_result_lines(result),
            [
                "[WARN] jira-software: OpenAPI extraction failed (0 candidates)",
                "[WARN] jira-software: using existing cache",
            ],
        )

    def test_error_unavailable_status(self):
        result = sync.SyncResult(
            source_name="confluence",
            status="error_unavailable",
            message="unable to extract OpenAPI specification (no existing cache)",
        )
        self.assertEqual(
            cli._format_result_lines(result),
            ["[ERROR] confluence: unable to extract OpenAPI specification (no existing cache)"],
        )


class TestMain(unittest.TestCase):
    def test_returns_exit_code_from_sync_all(self):
        fake_result = sync.SyncResult(source_name="jira-platform", status="ok", api_version="v3")
        with mock.patch(
            "tools.atlassian_docs.__main__.sync.sync_all", return_value=[fake_result]
        ):
            code = cli.main([])
        self.assertEqual(code, 0)

    def test_force_flag_is_passed_through(self):
        fake_result = sync.SyncResult(source_name="jira-platform", status="ok", api_version="v3")
        with mock.patch(
            "tools.atlassian_docs.__main__.sync.sync_all", return_value=[fake_result]
        ) as fake_sync_all:
            cli.main(["--force"])
        fake_sync_all.assert_called_once_with(force=True)

    def test_status_flag_does_not_call_sync_all_and_returns_zero(self):
        with mock.patch("tools.atlassian_docs.__main__.sync.sync_all") as fake_sync_all:
            with mock.patch(
                "tools.atlassian_docs.__main__.storage.read_metadata", return_value={}
            ):
                code = cli.main(["--status"])
        fake_sync_all.assert_not_called()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
```

Run: `python -m unittest tests.test_cli -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.atlassian_docs.__main__'`.

- [ ] **Step 2: Implement `tools/atlassian_docs/__main__.py`**

```python
"""CLI entry point. No sync logic here — parses args, calls sync.py,
formats output per spec §25, and returns the exit code from §26.
"""
import argparse
import sys

from . import sources, storage, sync


def _format_result_lines(result: sync.SyncResult):
    name = result.source_name
    if result.status == "ok":
        return [f"[OK] {name}: cache valid ({result.api_version or 'unknown'})"]
    if result.status == "updated":
        return [f"[UPDATED] {name}: specification changed"]
    if result.status == "version_changed":
        return [
            f"[VERSION] {name}: {result.previous_api_version} -> {result.api_version}",
            f"[UPDATED] {name}",
        ]
    if result.status == "warn_fallback":
        return [
            f"[WARN] {name}: {result.message}",
            f"[WARN] {name}: using existing cache",
        ]
    if result.status == "error_unavailable":
        return [f"[ERROR] {name}: {result.message}"]
    raise ValueError(f"unknown sync result status: {result.status!r}")


def _print_results(results) -> None:
    for result in results:
        for line in _format_result_lines(result):
            print(line)


def _display_timestamp(value):
    if not value:
        return "-"
    import datetime

    dt = datetime.datetime.strptime(value, sync._TIMESTAMP_FORMAT)
    return dt.strftime("%Y-%m-%d %H:%M")


def _show_status() -> int:
    metadata = storage.read_metadata()
    for source_name in sources.SOURCES:
        meta = metadata.get(source_name, {})
        print(source_name)
        print(f"  API version: {meta.get('api_version') or '(unknown)'}")
        print(f"  Cached: {'yes' if meta else 'no'}")
        print(f"  Last checked: {_display_timestamp(meta.get('last_checked'))}")
        print(f"  Last updated: {_display_timestamp(meta.get('last_updated'))}")
        print()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.atlassian_docs")
    parser.add_argument("--force", action="store_true", help="ignore TTL and re-extract")
    parser.add_argument("--status", action="store_true", help="show cache status and exit")
    args = parser.parse_args(argv)

    if args.status:
        return _show_status()

    results = sync.sync_all(force=args.force)
    _print_results(results)
    return sync.exit_code_for(results)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: all tests, across every task so far, PASS.

- [ ] **Step 4: Manually verify the CLI runs end-to-end**

Run from the repo root: `python -m tools.atlassian_docs --status`
Expected: prints all three sources with `Cached: no` (nothing has run against real Atlassian yet), exits 0. This confirms the package is importable as `-m tools.atlassian_docs` (i.e., the `__init__.py` files from Task 1 are correctly in place).

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/__main__.py tests/test_cli.py
git commit -m "feat: add CLI with --force/--status and exit code contract"
```

---

### Task 6: Integration — gitignore, live smoke test, agent instructions, final AC pass

**Files:**
- Create: `.gitignore`
- Create: `tests/live_smoke.py`
- Create: `AGENTS.md`

**Interfaces:**
- Consumes: `sources.SOURCES`, `sync.fetch_documentation_html`, `extractor.extract_openapi_spec`, `extractor.ExtractionError`, `sync.FetchError` (all prior tasks). No new interfaces produced — this task wires up the finished pieces and documents them.

- [ ] **Step 1: Add `.gitignore`**

Create `.gitignore` at the repo root:

```
.atlassian-docs/
__pycache__/
*.pyc
```

- [ ] **Step 2: Write `tests/live_smoke.py`**

```python
"""Manual smoke test against the real Atlassian documentation site.

NOT run by `python -m unittest discover` — it hits the network. Run it
directly when you want to check whether Atlassian's page structure still
matches what extractor.py expects:

    python tests/live_smoke.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.atlassian_docs import extractor, sources, sync


def main() -> int:
    failures = []
    for source_name, config in sources.SOURCES.items():
        try:
            resolved_url, html = sync.fetch_documentation_html(config["discovery_url"])
            spec = extractor.extract_openapi_spec(html)
        except (sync.FetchError, extractor.ExtractionError) as exc:
            failures.append(source_name)
            print(f"[FAIL] {source_name}: {exc}")
            continue
        api_version, _ = sync.detect_api_version(resolved_url)
        print(
            f"[OK] {source_name}: resolved={resolved_url} "
            f"api_version={api_version} openapi={spec.get('openapi')} "
            f"paths={len(spec.get('paths', {}))}"
        )
    if failures:
        print(f"\n{len(failures)} source(s) failed live extraction: {', '.join(failures)}")
        return 1
    print("\nAll sources extracted exactly one OpenAPI candidate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the live smoke test and confirm it passes against the real site**

Run: `python tests/live_smoke.py`
Expected: `[OK]` for `jira-platform`, `jira-software`, and `confluence`, with `jira-platform` showing `api_version=v3`, `confluence` showing `api_version=v2`, and `jira-software` showing `api_version=None`. Exit code 0.

If any source fails here, do not treat it as a plan bug to silently work around — Atlassian's page structure may have changed since the spec was written (2026-09-16). Stop and re-verify the assumption in spec §0 (`curl -L` the discovery URL, inspect the HTML) before changing `extractor.py`.

- [ ] **Step 4: Write `AGENTS.md`**

Create `AGENTS.md` at the repo root (content taken verbatim from spec §28):

```markdown
## Atlassian APIs

Before implementing or modifying Jira or Confluence integrations, run:

    python -m tools.atlassian_docs

Use the OpenAPI specifications under .atlassian-docs/ as the primary
API reference. The cached files always represent the latest
successfully extracted official API specifications.

Do not assume API major versions from memory. Do not rely on
memorized Jira or Confluence endpoints when the local OpenAPI
specification provides the relevant information.

- jira-platform.json  → Jira Platform APIs
- jira-software.json  → Jira Software / Agile APIs
- confluence.json     → Confluence APIs

API versions may change over time without changing these local file
names. jira-software's api_version may legitimately be null/unknown —
this does not mean the cache is invalid.
```

- [ ] **Step 5: Run the full offline suite one more time**

Run: `python -m unittest discover -s tests -t . -v`
Expected: all tests PASS, zero network access.

- [ ] **Step 6: Cross-check against the spec's Acceptance Criteria**

Walk spec §35 (AC-01 through AC-28) and confirm each is covered. This is a review pass, not new code — use this mapping:

| AC | Covered by |
|---|---|
| AC-01 (auto-create `.atlassian-docs/`) | `storage.ensure_cache_dir()`, exercised by `TestMetadataRoundtrip.test_write_creates_cache_dir` |
| AC-02, AC-03 (no version/CDN URL in config) | `tests/test_sources.py::test_no_version_strings_in_configuration` |
| AC-04 | `sources.SOURCES` — all three entries are `discovery_url` only |
| AC-05, AC-06, AC-07 (exactly 1 candidate per source) | `tests/test_extractor.py` + `tests/live_smoke.py` (Step 3 above) |
| AC-08, AC-09 (cache files, no version in filename) | `storage.cache_path()`, `TestCacheSpecRoundtrip.test_cache_filename_has_no_version_in_it` |
| AC-10 (`resolved_documentation_url` + `extraction_method`, no `resolved_openapi_url`) | `sync.sync_source` metadata construction — grep the codebase for `resolved_openapi_url` and confirm zero matches |
| AC-11, AC-12 (`api_version` null is normal) | `TestDetectApiVersion.test_returns_null_when_no_version_segment`, `TestSyncSourceRefresh.test_does_not_flag_version_change_when_previous_is_null` |
| AC-13, AC-14 (TTL / `--force`) | `TestSyncSourceCacheHit` |
| AC-15, AC-16 (hash-gated rewrite) | `TestSyncSourceRefresh.test_refetches_when_ttl_expired_and_marks_ok_if_unchanged` / `test_marks_updated_when_spec_content_changes` |
| AC-17, AC-18, AC-19 (extraction failures keep cache) | `tests/test_extractor.py` failure cases + `TestSyncSourceFailurePolicy` |
| AC-20, AC-21 (major version change output, filename stable) | `TestSyncSourceRefresh.test_marks_version_changed_...`, `TestFormatResultLines.test_version_changed_status` |
| AC-22 (no external packages, no `html.parser`) | grep the codebase for `html.parser` and `import bs4`/`playwright`/`selenium` — confirm zero matches |
| AC-23 (`last_checked` unchanged on failure) | `TestSyncSourceFailurePolicy.test_falls_back_on_fetch_error_when_cache_is_valid` |
| AC-24 (canonical-hash self-heal, not raw bytes) | `TestSyncSourceSelfHeal.test_mismatched_but_structurally_valid_cache_is_still_a_usable_fallback` |
| AC-25 (version regex scoped to URL path) | `TestDetectApiVersion.test_does_not_match_non_version_path_segment`, `test_ignores_version_looking_segments_outside_rest_path` |
| AC-26 (multiple `window.__DATA__` fails closed) | `tests/test_extractor.py::test_multiple_data_markers_raises_extraction_error` |
| AC-27 (exit codes 0/1/2) | `TestSyncAllAndExitCode` |
| AC-28 (cache before metadata write order) | `storage.write_metadata` is called exactly once, after the loop over `sync_source` (which does all cache writes) in `sync.sync_all` — inspect the code, no dedicated test needed since this is an ordering property of `sync_all`'s structure, not a runtime branch |

Run: `grep -rn "resolved_openapi_url\|html.parser\|import bs4\|playwright\|selenium" tools/ tests/`
Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add .gitignore tests/live_smoke.py AGENTS.md
git commit -m "chore: add gitignore, live smoke test, and agent instructions"
```
