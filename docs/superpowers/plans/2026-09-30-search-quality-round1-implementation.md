# Search Quality Round 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-baseline the search benchmarks, seal a fresh evaluation set by hash, add three policy-driven structural ranking signals (method intent, path specificity, product hint) to the lexical scorer, tune only within a frozen grid, and measure the sealed set exactly once at a frozen commit.

**Architecture:** `search.py` gets an explicit token contract (`tokenize_unigrams` / `token_forms` / `expand_token_forms` / `joined_query_forms`) and a single scoring algorithm that adds structural signals read from a new `RankingPolicy` (`intelligence/data/search_ranking.json`, loaded by `policy.py`, two canonical hashes). The benchmark file gains ids/origins/`failure_classes`, a `regression_negative` set, and sealed metadata (`round1_seal`) that a frozen evaluator later checks against plaintext. Test tooling (`tests/benchmarks/round1_seal.py`, `tests/tune_search_ranking.py`, extended `tests/diag_search_queries.py`) drives the A→T→B→C→D commit procedure; the controller performs the sealing, freezing and final-evaluation commits.

**Tech Stack:** Python ≥ 3.10 stdlib only under `tools/atlassian_docs/intelligence/`; `unittest`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-search-quality-round1-design.md` (v1.3 + fingerprint/snapshot amendment `6aeb032`). The spec is binding; this plan is its argument.

## Global Constraints

- Canonical test command: `python -m unittest discover -s tests -t .` (currently 328 OK; omitting `-t .` makes `tests/mcp` shadow the SDK and gives spurious ImportErrors). `python -S` variant skips jsonschema/MCP tests.
- Immutable files (baseline `d63a2ca`, spec §4, AC-09): `tools/atlassian_docs/{__main__,sources,extractor,sync,storage}.py`; `tools/atlassian_docs/intelligence/{models,normalizer,registry,schemas,gate,lastgood,provenance,quirks,request_template,request_check,oas_schema,headers,search_log,manager}.py`; `tools/atlassian_docs/intelligence/data/operation_quirks.json`; `tools/atlassian_docs/mcp/`.
- Mutable-by-interval files (AC-01): `tools/atlassian_docs/intelligence/search.py`, `tools/atlassian_docs/intelligence/policy.py`, `tools/atlassian_docs/intelligence/data/search_aliases.json`, and the `constants` object of `tools/atlassian_docs/intelligence/data/search_ranking.json` may change **only between commit B and commit C**. The table part of `search_ranking.json` never changes after commit T.
- Commit order (spec §5): A (benchmark demotion) → T (table freeze + snapshot) → B (hash seal) → implementation/tuning → C (freeze) → D (unseal + final evaluation). Controller-only steps are marked **[controller]**.
- The sealed plaintext path (`$ATLASSIAN_DOCS_SEALED_BENCH`, default `~/.atlassian_api_updater/sealed/round1-sealed.json`) is never given to an implementer or copied into the worktree. The cache snapshot (`$ATLASSIAN_DOCS_ROUND1_CACHE`, default `~/.atlassian_api_updater/round1-cache/`) is not secret and may be passed to implementers.
- All measurements during implementation use the snapshot (`--cache-dir`), never the live cache, and never a sealed set.
- `POLICY_VERSIONS["search"]` becomes 3. `intelligence_fingerprint` / `policy_block` keep their signatures and fold `ranking().sha256` in internally (spec §6.7).
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Chunked writes: no single tool call larger than ~60 lines (harness workaround).

## Review Focus

1. A query whose only verb is in `verb_methods` but whose target op uses an unlisted method (e.g. `PATCH`) must get the mismatch penalty, never a crash or a bonus (Task 6 test `test_method_intent_unlisted_op_method`).
2. A path with a segment that tokenizes to nothing after noise/digit removal (e.g. `/rest/api/3`) must yield an empty `path_tokens` and zero penalty (Task 6 test `test_path_tokens_empty_after_noise`).
3. A query containing only a product hint token (`jira`) that matches no field lexically must still return `empty_query`/no candidates rather than every jira op with a +3 bonus — structural signals never create candidates (Task 6 test `test_hint_only_query_has_no_candidates`).
4. `limit=1` with two exact-pinned operationIds must return exactly one result and `exact_match: true` (Task 6 test `test_limit_truncates_pinned_and_keeps_exact_flag`).
5. Loading `search_ranking.json` whose `constants` value lies outside its grid must fail loudly at `ranking()` time, not silently at tuning time (Task 5 test `test_constants_outside_grid_rejected`).

---

### Task 1: Commit A — benchmark demotion, record schema, evaluator semantics

**Files:**
- Modify: `tests/benchmarks/search_queries.json`
- Modify: `tests/benchmarks/evaluator.py`
- Modify: `tests/benchmarks/test_evaluator.py`
- Modify: `tests/intelligence/test_search.py` (`TestSeedBenchmark.test_seed_passes_on_fixtures` → evaluates `seed` and `regression_negative`; expected to FAIL on fixtures until Task 7 — mark with `@unittest.expectedFailure` in this task, removed in Task 7)
- Modify: `tests/diag_search_queries.py` (iterate over the sets that exist and are not sealed; minimal change)

**Interfaces:**
- Produces: benchmark file shape `{"version": 2, "record_schema": {...}, "seed": [...], "regression_negative": [...], "held_out": [], "negative": []}`; record fields `id`, `query`, `expected_top1_any`, `forbidden_top1`, `origin`, `failure_classes`, `ambiguous`, optional `note`.
- Produces: `evaluator.evaluate(records, search_fn)` unchanged signature; new `evaluator.check_schema(section_name, records)` raising `ValueError`; new `evaluator.is_sealed(section)` → bool; new `evaluator.canonical_sha256(obj)` (same algorithm as `policy.canonical_sha256`, duplicated on purpose so evaluator has no dependency on production code); new `evaluator.unigram_set(query)` (stdlib re-implementation of `tokenize_unigrams`: camelCase split, lowercase, `[^a-z0-9]+` split, len ≥ 2, STOPWORDS).

- [ ] **Step 1: Rewrite the benchmark file**

Write `tests/benchmarks/search_queries.json` with `version: 2`. Assign ids in file order: existing seed 9 → `s-001..s-009` (`origin: "seed-r0"`), promoted held_out 12 → `s-010..s-021` (`origin: "held_out-r0"`), `update issue summary` → `s-022` (`origin: "negative-r0"`, `expected_top1_any: ["jira-platform:PUT:/rest/api/3/issue/{issueIdOrKey}"]`, `forbidden_top1: []`). Remaining 7 negatives → `rn-001..rn-007` (`origin: "negative-r0"`, `expected_top1_any: []`, keep `forbidden_top1`). `held_out: []`, `negative: []`.

`failure_classes` (spec §0.2), all other records `[]`:

| id | query | failure_classes |
|---|---|---|
| s-005 | update page content | ["R1"] |
| s-006 | get issue by key | ["R1"] |
| s-011 | change issue assignee | ["R1","R4"] |
| s-013 | create a new confluence page in a space | ["R2","R3"] |
| s-015 | run jql query | ["R4"] |
| s-016 | add issue to sprint | ["R2"] |
| s-018 | delete an attachment | ["R2","R3"] |
| s-019 | get project by key | ["R1"] |
| s-022 | update issue summary | ["R1"] |

(Verify the ids against the actual order of the current `held_out` list; the mapping above assumes the current file order: attach…, change…, post…, create a new…, fetch page…, run jql…, add issue…, list boards, delete an attachment, get project…, update page title, move issue…)

`s-018` (`delete an attachment`): `ambiguous: true`, `expected_top1_any: ["jira-platform:DELETE:/rest/api/3/attachment/{id}", "confluence:DELETE:/attachments/{id}"]`.

`record_schema`: `{"id": "str (s-|rn-|h-|n- + 3 digits)", "query": "str", "expected_top1_any": "[key]", "forbidden_top1": "[key]", "origin": "<set>-r<n>", "failure_classes": "[R1..R4]", "ambiguous": "bool", "note": "str?"}`.

- [ ] **Step 2: Write failing evaluator tests** (append to `tests/benchmarks/test_evaluator.py`)

```python
from tests.benchmarks import evaluator as ev

class TestSchemaAndSemantics(unittest.TestCase):
    def test_regression_negative_passes_when_top1_not_forbidden_or_empty(self):
        recs = [{"id": "rn-001", "query": "x", "expected_top1_any": [], "forbidden_top1": ["k1"],
                 "origin": "negative-r0", "failure_classes": [], "ambiguous": False}]
        self.assertEqual(ev.evaluate(recs, lambda q: ["k2"])["failed"], [])
        self.assertEqual(ev.evaluate(recs, lambda q: [])["failed"], [])
        self.assertEqual(len(ev.evaluate(recs, lambda q: ["k1"])["failed"]), 1)

    def test_schema_invariants(self):
        good = {"id": "s-001", "query": "a b", "expected_top1_any": ["k"], "forbidden_top1": [],
                "origin": "seed-r0", "failure_classes": ["R1"], "ambiguous": False}
        ev.check_schema("seed", [good])
        for bad in ({**good, "expected_top1_any": []}, {**good, "id": "x-1"}, {**good, "origin": "seed"},
                    {**good, "failure_classes": ["R9"]}, {**good, "ambiguous": "no"}):
            with self.assertRaises(ValueError):
                ev.check_schema("seed", [bad])
        neg = {**good, "id": "rn-001", "expected_top1_any": [], "forbidden_top1": ["k"], "origin": "negative-r0"}
        ev.check_schema("regression_negative", [neg])
        with self.assertRaises(ValueError):
            ev.check_schema("regression_negative", [{**neg, "expected_top1_any": ["k"]}])
        with self.assertRaises(ValueError):
            ev.check_schema("seed", [good, {**good}])   # duplicate id

    def test_bundled_file_schema_and_counts(self):
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        self.assertEqual(b["version"], 2)
        for sect in ("seed", "regression_negative", "held_out", "negative"):
            if not ev.is_sealed(b[sect]):
                ev.check_schema(sect, b[sect])
        self.assertEqual(len(b["seed"]), 22); self.assertEqual(len(b["regression_negative"]), 7)

    def test_no_query_reuse_across_sets(self):
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        seen_q, seen_t = set(), set()
        for sect in ("seed", "regression_negative", "held_out", "negative"):
            if ev.is_sealed(b[sect]):
                continue
            for r in b[sect]:
                self.assertNotIn(r["query"], seen_q); self.assertNotIn(ev.unigram_set(r["query"]), seen_t)
                seen_q.add(r["query"]); seen_t.add(ev.unigram_set(r["query"]))

    def test_canonical_sha256_and_unigrams(self):
        self.assertEqual(ev.canonical_sha256({"b": 1, "a": [1, 2]}), ev.canonical_sha256({"a": [1, 2], "b": 1}))
        self.assertEqual(ev.unigram_set("Get the issueIdOrKey"), frozenset({"get", "issue", "id", "key"}))

    def test_sealed_section_is_reported_not_evaluated(self):
        sealed = {"sealed": True, "round": 1, "count": 16, "sha256": "0" * 64, "distribution": {}}
        self.assertTrue(ev.is_sealed(sealed)); self.assertFalse(ev.is_sealed([]))
        self.assertEqual(ev.evaluate(sealed, lambda q: []), {"sealed": True, "count": 16})
```

Replace the old `test_frozen_file_has_no_degenerate_records` body so it iterates `("seed", "regression_negative")` and skips sealed sections.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m unittest tests.benchmarks.test_evaluator -v`  
Expected: FAIL (`check_schema`, `is_sealed`, `canonical_sha256`, `unigram_set` undefined; counts wrong).

- [ ] **Step 4: Implement evaluator.py**

```python
"""Shared benchmark evaluator (Round 1 spec §5.1): one record schema, sealed-section awareness.
Deliberately stdlib-only and independent of tools/ so its hash (evaluation_code_sha256) is meaningful."""
import hashlib, json, re

STOPWORDS = frozenset("a an the to of for in on at and or with by from is are be this that".split())
_CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])"); _CAMEL_2 = re.compile(r"([A-Z]{2,})([A-Z][a-z])"); _SPLIT = re.compile(r"[^a-z0-9]+")
_ID = re.compile(r"^(s|rn|h|n)-\d{3}$"); _ORIGIN = re.compile(r"^(seed|held_out|negative)-r\d+$")
_CLASSES = {"R1", "R2", "R3", "R4"}
NEGATIVE_SECTIONS = ("regression_negative", "negative")


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def unigram_set(query: str) -> frozenset:
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", query or "")).lower()
    return frozenset(t for t in _SPLIT.split(text) if len(t) >= 2 and t not in STOPWORDS)


def is_sealed(section) -> bool:
    return isinstance(section, dict) and section.get("sealed") is True


def check_schema(section_name: str, records) -> None:
    if not isinstance(records, list):
        raise ValueError(f"{section_name}: records must be a list")
    seen = set()
    for rec in records:
        if not isinstance(rec, dict):
            raise ValueError(f"{section_name}: record must be an object")
        rid = rec.get("id")
        if not isinstance(rid, str) or not _ID.match(rid) or rid in seen:
            raise ValueError(f"{section_name}: bad or duplicate id {rid!r}")
        seen.add(rid)
        if not isinstance(rec.get("query"), str) or not rec["query"].strip():
            raise ValueError(f"{section_name}/{rid}: query must be a non-empty string")
        exp, forb = rec.get("expected_top1_any"), rec.get("forbidden_top1")
        if not isinstance(exp, list) or not isinstance(forb, list) or not all(isinstance(k, str) for k in exp + forb):
            raise ValueError(f"{section_name}/{rid}: expected_top1_any/forbidden_top1 must be lists of keys")
        if section_name in NEGATIVE_SECTIONS:
            if exp or not forb:
                raise ValueError(f"{section_name}/{rid}: negative records need empty expected and non-empty forbidden")
        elif not exp:
            raise ValueError(f"{section_name}/{rid}: expected_top1_any must not be empty")
        if not isinstance(rec.get("origin"), str) or not _ORIGIN.match(rec["origin"]):
            raise ValueError(f"{section_name}/{rid}: bad origin {rec.get('origin')!r}")
        fc = rec.get("failure_classes")
        if not isinstance(fc, list) or not set(fc) <= _CLASSES or len(set(fc)) != len(fc):
            raise ValueError(f"{section_name}/{rid}: bad failure_classes {fc!r}")
        if not isinstance(rec.get("ambiguous"), bool):
            raise ValueError(f"{section_name}/{rid}: ambiguous must be a bool")


def evaluate(records, search_fn):
    if is_sealed(records):
        return {"sealed": True, "count": records.get("count")}
    failed = []
    for rec in records:
        expected = rec.get("expected_top1_any") or []
        forbidden = rec.get("forbidden_top1") or []
        if not expected and not forbidden:
            raise ValueError(f"benchmark record {rec.get('query')!r} must set expected_top1_any or forbidden_top1")
        ranked = search_fn(rec["query"])
        top1 = ranked[0] if ranked else None
        ok = (not expected or top1 in expected) and (top1 not in forbidden)
        if not ok:
            failed.append({"id": rec.get("id"), "query": rec["query"], "top1": top1,
                           "expected_top1_any": expected, "forbidden_top1": forbidden})
    return {"passed": len(records) - len(failed), "failed": failed, "total": len(records)}
```

- [ ] **Step 5: Update `TestSeedBenchmark` and the diag script**

In `tests/intelligence/test_search.py::TestSeedBenchmark.test_seed_passes_on_fixtures`, evaluate `BENCH["seed"]` and `BENCH["regression_negative"]`; decorate with `@unittest.expectedFailure` and a comment `# Round 1 Task 7 removes this decorator once fixtures + scorer land`.

In `tests/diag_search_queries.py`, change the loop to `for name in ("seed", "regression_negative", "held_out", "negative"):` and, when `evaluate` returns `{"sealed": True, ...}`, print `[name] sealed (n records)` and continue. Nothing else changes in this task.

- [ ] **Step 6: Run the full suite**

Run: `python -m unittest discover -s tests -t .`  
Expected: OK with 1 expected failure (seed benchmark), 328 + 6 new tests.

- [ ] **Step 7: Commit A**

```bash
git add tests/benchmarks tests/intelligence/test_search.py tests/diag_search_queries.py
git commit -m "bench: demote observed held_out/negative to seed/regression_negative (Round 1 commit A)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Commit T — ranking tables + structure hash freeze (data + tests only)

**Files:**
- Create: `tools/atlassian_docs/intelligence/data/search_ranking.json`
- Modify: `tests/benchmarks/test_evaluator.py` (add `TestRankingTablesFrozen`)

**Interfaces:**
- Produces: the JSON exactly as spec §6.2 (keys `version`, `verb_methods`, `path_noise`, `product_hints`, `tuning_grid`, `constants`).
- Produces: `RANKING_STRUCTURE_SHA256` constant in `tests/benchmarks/test_evaluator.py` (computed in this task from the file; Task 5's loader must reproduce it).
- No production Python changes in this task (AC-01: `policy.py` may not change before commit B).

- [ ] **Step 1: Write the data file**

Copy the JSON block from spec §6.2 verbatim into `tools/atlassian_docs/intelligence/data/search_ranking.json` (2-space indent, trailing newline).

- [ ] **Step 2: Write the failing test** (append)

```python
RANKING = pathlib.Path(__file__).resolve().parents[2] / "tools" / "atlassian_docs" / "intelligence" / "data" / "search_ranking.json"
RANKING_STRUCTURE_SHA256 = "<fill in Step 3>"
STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid")


def ranking_structure_sha256(raw: dict) -> str:
    return ev.canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS})


class TestRankingTablesFrozen(unittest.TestCase):
    def test_structure_hash_matches_commit_t(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(ranking_structure_sha256(raw), RANKING_STRUCTURE_SHA256)

    def test_constants_inside_grid(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(set(raw["constants"]), set(raw["tuning_grid"]))
        for k, v in raw["constants"].items():
            self.assertIn(v, raw["tuning_grid"][k], k)
```

- [ ] **Step 3: Compute the constant, fill it in, run**

Run: `python -c "import json,pathlib; from tests.benchmarks import evaluator as ev; raw=json.load(open('tools/atlassian_docs/intelligence/data/search_ranking.json')); print(ev.canonical_sha256({k: raw[k] for k in ('verb_methods','path_noise','product_hints','tuning_grid')}))"`  
Paste the value into `RANKING_STRUCTURE_SHA256`. Run `python -m unittest tests.benchmarks.test_evaluator -v` → PASS.

- [ ] **Step 4: Commit T**

```bash
git add tools/atlassian_docs/intelligence/data/search_ranking.json tests/benchmarks/test_evaluator.py
git commit -m "policy: freeze Round 1 ranking tables and tuning grid (commit T)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 5 [controller]: Snapshot the cache**

```bash
export ATLASSIAN_DOCS_ROUND1_CACHE=~/.atlassian_api_updater/round1-cache
mkdir -p "$ATLASSIAN_DOCS_ROUND1_CACHE" && cp -R .atlassian-docs/. "$ATLASSIAN_DOCS_ROUND1_CACHE"/
```
Record the snapshot's registry fingerprint and spec sha256 values (Task 3's `round1_seal.py catalog` prints them).

---

### Task 3: Seal tooling (`tests/benchmarks/round1_seal.py`) — before commit B

**Files:**
- Create: `tests/benchmarks/round1_seal.py`
- Create: `tests/benchmarks/test_round1_seal.py`

**Interfaces:**
- CLI: `python tests/benchmarks/round1_seal.py catalog --cache-dir DIR --out catalog.json` (writes `[{"key","source","method","summary","tags"}]` sorted by key, prints `registry_fingerprint` and per-source `spec_sha256`); `check --plain round1-sealed.json --bench tests/benchmarks/search_queries.json --catalog catalog.json` (machine rules of spec §5.4, exit 1 on any violation, prints each violation); `seal --plain ... --bench ... --cache-dir DIR` (writes sealed metadata + `round1_seal` into the bench file); `unseal --plain ... --bench ...` (replaces `held_out`/`negative` with the plaintext lists; refuses if hashes differ).
- Library functions (used by tests and by Task 8): `load_catalog_from_cache(cache_dir) -> (records, registry_fingerprint, spec_sha256_by_source)`, `machine_check(plain, bench, catalog) -> list[str]` (violation messages), `seal_metadata(plain_section, round) -> dict`, `distribution(records) -> dict`.
- Uses `tools.atlassian_docs.intelligence.registry`/`normalizer`/`storage` read-only to build the catalog from a cache dir (patch `storage.CACHE_DIR` for the call, restore after).

- [ ] **Step 1: Write failing tests**

`tests/benchmarks/test_round1_seal.py`:

```python
import json, unittest
from tests.benchmarks import round1_seal as rs

CAT = [{"key": "jira-platform:GET:/rest/api/3/issue/{issueIdOrKey}", "source": "jira-platform", "method": "GET",
        "summary": "Get issue", "tags": ["Issues"]},
       {"key": "confluence:POST:/pages", "source": "confluence", "method": "POST", "summary": "Create page", "tags": ["Page"]}]
BENCH = {"seed": [{"id": "s-001", "query": "get issue by key", "expected_top1_any": [CAT[0]["key"]], "forbidden_top1": [],
                   "origin": "seed-r0", "failure_classes": [], "ambiguous": False}], "regression_negative": []}


def rec(i, q, key, **kw):
    return {"id": f"h-{i:03d}", "query": q, "expected_top1_any": [key], "forbidden_top1": [], "origin": "held_out-r1",
            "failure_classes": [], "ambiguous": False, **kw}


class TestMachineCheck(unittest.TestCase):
    def test_reuse_and_summary_copy_and_missing_key(self):
        plain = {"held_out": [rec(1, "get issue by key", CAT[0]["key"]),            # exact reuse of a seed query
                              rec(2, "make a create page now", CAT[1]["key"]),      # copies 2 consecutive summary tokens
                              rec(3, "open a ticket", "jira-platform:POST:/nope")], # key not in catalog
                 "negative": []}
        msgs = rs.machine_check(plain, BENCH, CAT)
        self.assertTrue(any("h-001" in m and "reuse" in m for m in msgs))
        self.assertTrue(any("h-002" in m and "summary" in m for m in msgs))
        self.assertTrue(any("h-003" in m and "catalog" in m for m in msgs))

    def test_distribution_uses_first_expected_key(self):
        d = rs.distribution([rec(1, "show me the ticket", CAT[0]["key"]), rec(2, "start new page", CAT[1]["key"], ambiguous=True)])
        self.assertEqual(d["source"], {"jira-platform": 1, "confluence": 1}); self.assertEqual(d["method"], {"GET": 1, "POST": 1})
        self.assertEqual(d["product_named"], 0)

    def test_seal_metadata_and_roundtrip(self):
        recs = [rec(1, "show me the ticket", CAT[0]["key"])]
        meta = rs.seal_metadata(recs, 1)
        self.assertEqual(meta["count"], 1); self.assertEqual(meta["sha256"], rs.canonical_sha256(recs)); self.assertTrue(meta["sealed"])
```

- [ ] **Step 2: Run to verify failure** — `python -m unittest tests.benchmarks.test_round1_seal -v` → ImportError.

- [ ] **Step 3: Implement `round1_seal.py`**

Rules to encode in `machine_check` (spec §5.4, machine-checkable only): (1) 3–7 words; unigram set ≠ any catalog operationId unigram set (derive operationId tokens from the last path segment? No — the catalog carries `key` only; add `operation_id` to catalog records and compare `unigram_set(operation_id)`); no 2 consecutive content tokens copied from the expected op's `summary` or any tag (compare consecutive token pairs of the query, STOPWORDS removed, against consecutive pairs of `unigram list` of summary/tags); (2) held_out count 16 and distributions per §5.4.2 (use `distribution()`); (3) negative count 8, `expected_top1_any == []`, `forbidden_top1` ≥ 1, all keys in catalog; (4) no query string / unigram-set reuse against `bench["seed"] + bench["regression_negative"]` and within the plaintext; (5) every expected/forbidden key ∈ catalog. `product_named` counts records whose unigram set contains `jira` or `confluence`. `seal_metadata` returns `{"sealed": True, "round": r, "count": n, "sha256": canonical_sha256(records), "distribution": distribution(records)}`. `seal` command also writes top-level `round1_seal = {"held_out_sha256", "negative_sha256", "registry_fingerprint", "spec_sha256"}` and leaves `seed`/`regression_negative` untouched; it refuses if any `machine_check` violation exists. `unseal` verifies hashes then replaces the two lists. Import `canonical_sha256`, `unigram_set`, `STOPWORDS` from `evaluator`. Keep the file under ~200 lines; write in chunks.

- [ ] **Step 4: Run** — `python -m unittest tests.benchmarks.test_round1_seal -v` → PASS; full suite OK.

- [ ] **Step 5: Commit**

```bash
git add tests/benchmarks/round1_seal.py tests/benchmarks/test_round1_seal.py
git commit -m "bench: Round 1 seal tooling (catalog, machine checks, seal/unseal)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6 [controller]: Generate, review, seal → commit B**

1. `python tests/benchmarks/round1_seal.py catalog --cache-dir "$ATLASSIAN_DOCS_ROUND1_CACHE" --out /tmp/round1-catalog.json`.
2. Clean-context generation: open a **new** ChatGPT conversation (or a fresh subagent with an empty context) and provide only the catalog file and the spec §5.4 rules (copy the machine-checkable and reviewer-check rules; do not mention failures, signals, aliases or this repo). Ask for `held_out` (16) and `negative` (8) records in the §5.1 schema with ids `h-001..h-016`, `n-001..n-008`, `origin` `held_out-r1`/`negative-r1`, `failure_classes: []`. Save the prompt text and its sha256; save the output as `$ATLASSIAN_DOCS_SEALED_BENCH`.
3. `round1_seal.py check ...` — on violations, re-request with only "item N rejected; generate a replacement satisfying the original rules". Count re-requests.
4. Reviewer check (controller or a fresh reviewer subagent given only the plaintext + catalog summaries/descriptions; it must not call `search_operations`): semantic query↔op correspondence, `ambiguous` validity, negative decoy validity.
5. `round1_seal.py seal --plain "$ATLASSIAN_DOCS_SEALED_BENCH" --bench tests/benchmarks/search_queries.json --cache-dir "$ATLASSIAN_DOCS_ROUND1_CACHE"`; run the full suite; commit:
   ```bash
   git add tests/benchmarks/search_queries.json
   git commit -m "bench: seal Round 1 held_out/negative by hash with cache snapshot fingerprint (commit B)

   Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
   ```
6. Write the decision record entries (prompt sha256, output sha256, re-request count, snapshot fingerprint, commit A/T/B shas) into `docs/phase3-readiness.md` (this doc is not a mutable-interval file; commit it right after B).

---

### Task 4: Token contract in `search.py` (after commit B)

**Files:**
- Modify: `tools/atlassian_docs/intelligence/search.py`
- Modify: `tests/intelligence/test_search.py` (`TestTokenize`)
- Modify: `tools/atlassian_docs/intelligence/policy.py` (`_token_ok` uses the new singular rule; no other change yet)

**Interfaces:**
- Produces: `tokenize_unigrams(text) -> tuple[str, ...]`, `singular(t) -> str`, `token_forms(t) -> frozenset`, `expand_token_forms(tokens) -> frozenset`, `joined_query_forms(query) -> frozenset`; `tokenize(text)` kept as `expand_token_forms(tokenize_unigrams(text))` for existing callers; `_variants` removed (use `expand_token_forms`); `_query_tokens(query)` kept as `tokenize(query) | joined_query_forms(query)`.
- Consumes: nothing new.

- [ ] **Step 1: Failing tests** — replace `TestTokenize.test_plural_variants` and add:

```python
    def test_plural_variants(self):
        self.assertEqual(search.tokenize("statuses"), frozenset({"statuses", "status"}))
        self.assertEqual(search.tokenize("status"), frozenset({"status"}))
        self.assertEqual(search.tokenize("process"), frozenset({"process"}))
        self.assertEqual(search.tokenize("analysis"), frozenset({"analysis"}))
        self.assertEqual(search.tokenize("issues"), frozenset({"issues", "issue"}))

    def test_singular_contract(self):
        cases = {"properties": "property", "queries": "query", "statuses": "status", "status": "status", "access": "access",
                 "issues": "issue", "databases": "database", "schemes": "scheme", "boards": "board", "classes": "class",
                 "series": "series", "news": "news", "jsis": "jsis", "id": "id"}
        for word, want in cases.items():
            self.assertEqual(search.singular(word), want, word)

    def test_unigrams_forms_and_joined(self):
        self.assertEqual(search.tokenize_unigrams("Get the issueIdOrKey properties"), ("get", "issue", "id", "key", "properties"))
        self.assertEqual(search.token_forms("properties"), frozenset({"properties", "property"}))
        self.assertEqual(search.expand_token_forms(("issues", "get")), frozenset({"issues", "issue", "get"}))
        self.assertEqual(search.joined_query_forms("IssueCreateMetadata get"), frozenset({"issuecreatemetadata"}))
        self.assertEqual(search.joined_query_forms("issue attachment"), frozenset())
        self.assertEqual(search._query_tokens("IssueCreateMetadata"), search.tokenize("IssueCreateMetadata") | {"issuecreatemetadata"})
```

- [ ] **Step 2: Run** — expected FAIL (`singular` etc. undefined; `statuse`).

- [ ] **Step 3: Implement**

```python
IRREGULAR_SINGULAR = {"statuses": "status"}          # observed in the real cache vocabulary only (spec §6.1)
UNCHANGED_PLURAL = frozenset({"series", "species", "news"})


def tokenize_unigrams(text: Optional[str]) -> tuple:
    if not text:
        return ()
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", text)).lower()
    out, seen = [], set()
    for tok in _SPLIT.split(text):
        if len(tok) < 2 or tok in STOPWORDS or tok in seen:
            continue
        seen.add(tok); out.append(tok)
    return tuple(out)


def singular(t: str) -> str:
    if t in IRREGULAR_SINGULAR:
        return IRREGULAR_SINGULAR[t]
    if t in UNCHANGED_PLURAL or len(t) <= 3:
        return t
    if t.endswith("ies"):
        return t[:-3] + "y"
    if t.endswith(("sses", "shes", "ches", "xes")):
        return t[:-2]
    if t.endswith(("ss", "us", "is")):
        return t
    if t.endswith("s"):
        return t[:-1]
    return t


def token_forms(t: str) -> frozenset:
    return frozenset({t, singular(t)})


def expand_token_forms(tokens) -> frozenset:
    out = set()
    for t in tokens:
        out |= token_forms(t)
    return frozenset(out)


def tokenize(text: Optional[str]) -> frozenset:
    return expand_token_forms(tokenize_unigrams(text))


def joined_query_forms(query: str) -> frozenset:
    """Each whitespace word that splits into 2+ unigrams contributes its joined lowercase form (Phase 2.5 §5)."""
    out = set()
    for word in (query or "").split():
        joined = _JOIN.sub("", word.lower())
        if len(tokenize_unigrams(word)) >= 2 and len(joined) > 3 and joined not in STOPWORDS:
            out.add(joined)
    return frozenset(out)


def _query_tokens(query: str) -> frozenset:
    return tokenize(query) | joined_query_forms(query)
```

Replace `_variants(x)` uses in `expand_query` with `expand_token_forms(x)`. In `policy._token_ok`, replace the manual plural check with `toks == frozenset({tok, search.singular(tok)})`.

- [ ] **Step 4: Run full suite** — `python -m unittest discover -s tests -t .` → OK (1 expected failure remains). If any Phase 2 ranking test changes order because `statuse` no longer exists, inspect: it should not.

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py tests/intelligence/test_search.py
git commit -m "search: explicit token contract (unigrams, conservative singular, forms, joined)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `RankingPolicy` loader, two hashes, fingerprint fold-in, `POLICY_VERSIONS["search"] = 3`

**Files:**
- Modify: `tools/atlassian_docs/intelligence/policy.py`
- Modify: `tests/intelligence/test_policy.py`
- Modify: `tests/intelligence/test_search.py` (`test_fields_and_fingerprint` expects version 3)

**Interfaces:**
- Produces: `RankingPolicy(version, verb_methods: Mapping[str, frozenset], path_noise: frozenset, product_hints: Mapping[str, frozenset], tuning_grid: Mapping[str, tuple], constants: Mapping[str, float|int], sha256, structure_sha256)`; `load_ranking(path=None) -> RankingPolicy`; `ranking()` lru_cache; `STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid")`; `CONSTANT_KEYS = ("method_match_bonus", "method_mismatch_penalty", "path_unmatched_penalty", "path_unmatched_cap", "product_hint_bonus")`.
- Changes: `intelligence_fingerprint(registry_fp, aliases_sha256, overrides_sha256)` blob becomes `[registry_fp, aliases_sha256, overrides_sha256 or "-", ranking().sha256, POLICY_VERSIONS json]`; `policy_block(...)` adds `ranking_sha256`, `ranking_structure_sha256`; `POLICY_VERSIONS = {"search": 3, "quirks": 1, "oas_transpiler": 1}`.
- Consumed by Task 6 (`search._structural_signals`) and Task 7 (tuning script writes `constants`).

- [ ] **Step 1: Failing tests** (append to `tests/intelligence/test_policy.py`)

```python
class TestRankingPolicy(unittest.TestCase):
    def _raw(self):
        return json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))

    def test_bundled_loads_and_hashes(self):
        rp = policy.load_ranking()
        self.assertEqual(rp.verb_methods["move"], frozenset({"PUT", "POST"})); self.assertIn("rest", rp.path_noise)
        self.assertEqual(rp.product_hints["jira"], frozenset({"jira-platform", "jira-software"}))
        self.assertEqual(set(rp.constants), set(policy.CONSTANT_KEYS)); self.assertEqual(len(rp.sha256), 64)
        from tests.benchmarks.test_evaluator import RANKING_STRUCTURE_SHA256
        self.assertEqual(rp.structure_sha256, RANKING_STRUCTURE_SHA256)
        self.assertIs(policy.ranking(), policy.ranking())

    def test_constants_change_only_full_hash(self):
        raw = self._raw(); a = policy.load_ranking()
        raw["constants"]["method_match_bonus"] = 3.0
        b = self._from(raw)
        self.assertNotEqual(a.sha256, b.sha256); self.assertEqual(a.structure_sha256, b.structure_sha256)

    def _from(self, raw):
        import tempfile, pathlib
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(raw, fh); path = pathlib.Path(fh.name)
        return policy.load_ranking(path)

    def test_constants_outside_grid_rejected(self):
        raw = self._raw(); raw["constants"]["path_unmatched_cap"] = 99
        with self.assertRaises(ValueError):
            self._from(raw)

    def test_loader_contract_violations(self):
        base = self._raw()
        bad = [dict(base, version=0), dict(base, verb_methods={**base["verb_methods"], "Get": ["GET"]}),
               dict(base, verb_methods={**base["verb_methods"], "get": ["GET", "GET"]}),
               dict(base, verb_methods={**base["verb_methods"], "get": ["FETCH"]}),
               dict(base, path_noise=base["path_noise"] + ["rest"]),
               dict(base, product_hints={**base["product_hints"], "jira": ["nowhere"]}),
               dict(base, product_hints={**base["product_hints"], "jira": []}),
               dict(base, tuning_grid={k: v for k, v in base["tuning_grid"].items() if k != "product_hint_bonus"}),
               dict(base, constants={**base["constants"], "path_unmatched_cap": True}),
               dict(base, constants={**base["constants"], "method_match_bonus": -1.0}),
               dict(base, extra=1)]
        for raw in bad:
            with self.assertRaises(ValueError):
                self._from(raw)

    def test_returned_structures_are_immutable(self):
        rp = policy.ranking()
        with self.assertRaises(TypeError):
            rp.verb_methods["x"] = frozenset()
        with self.assertRaises(TypeError):
            rp.constants["method_match_bonus"] = 9


class TestFingerprintIncludesRanking(unittest.TestCase):
    def test_versions_and_block(self):
        self.assertEqual(policy.POLICY_VERSIONS["search"], 3)
        blk = policy.policy_block("A", "B")
        self.assertEqual(blk["ranking_sha256"], policy.ranking().sha256)
        self.assertEqual(blk["ranking_structure_sha256"], policy.ranking().structure_sha256)

    def test_fingerprint_sensitive_to_ranking(self):
        from unittest import mock
        a = policy.intelligence_fingerprint("reg", "A", "B")
        fake = policy.RankingPolicy(**{**policy.ranking().__dict__, "sha256": "f" * 64})
        with mock.patch.object(policy, "ranking", return_value=fake):
            self.assertNotEqual(a, policy.intelligence_fingerprint("reg", "A", "B"))
```

Update `tests/intelligence/test_search.py::test_fields_and_fingerprint` to assert `versions["search"] == 3`.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement in `policy.py`**

Add after `QuirkOverrides`:

```python
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid")
CONSTANT_KEYS = ("method_match_bonus", "method_mismatch_penalty", "path_unmatched_penalty", "path_unmatched_cap", "product_hint_bonus")
_WORD = re.compile(r"^[a-z]+$"); _NOISE = re.compile(r"^[a-z0-9]+$")


@dataclass(frozen=True)
class RankingPolicy:
    version: int
    verb_methods: Mapping[str, frozenset]
    path_noise: frozenset
    product_hints: Mapping[str, frozenset]
    tuning_grid: Mapping[str, tuple]
    constants: Mapping[str, float]
    sha256: str
    structure_sha256: str


def _num(v, name, integer=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")) or v < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    if integer and not isinstance(v, int):
        raise ValueError(f"{name} must be an int")
    return int(v) if integer else float(v)


def load_ranking(path: Optional[pathlib.Path] = None) -> RankingPolicy:
    from .. import sources
    raw = _read(path or DATA_DIR / "search_ranking.json")
    if not isinstance(raw, dict) or set(raw) != {"version", *STRUCTURE_KEYS, "constants"}:
        raise ValueError("ranking policy must have exactly version, verb_methods, path_noise, product_hints, tuning_grid, constants")
    if not isinstance(raw["version"], int) or isinstance(raw["version"], bool) or raw["version"] < 1:
        raise ValueError("version must be an int >= 1")
    verbs = {}
    for k, v in (raw["verb_methods"] or {}).items() if isinstance(raw["verb_methods"], dict) else [(None, None)]:
        if k is None or not _WORD.match(k) or not isinstance(v, list) or not v or len(set(v)) != len(v) or not set(v) <= _METHODS:
            raise ValueError(f"invalid verb_methods entry {k!r}")
        verbs[k] = frozenset(v)
    noise = raw["path_noise"]
    if not isinstance(noise, list) or len(set(noise)) != len(noise) or not all(isinstance(t, str) and _NOISE.match(t) for t in noise):
        raise ValueError("invalid path_noise")
    hints = {}
    for k, v in (raw["product_hints"] or {}).items() if isinstance(raw["product_hints"], dict) else [(None, None)]:
        if k is None or not _WORD.match(k) or not isinstance(v, list) or not v or len(set(v)) != len(v) or not set(v) <= set(sources.SOURCES):
            raise ValueError(f"invalid product_hints entry {k!r}")
        hints[k] = frozenset(v)
    grid, consts = raw["tuning_grid"], raw["constants"]
    if not isinstance(grid, dict) or not isinstance(consts, dict) or set(grid) != set(CONSTANT_KEYS) or set(consts) != set(CONSTANT_KEYS):
        raise ValueError("tuning_grid and constants must both have exactly the five constant keys")
    out_grid, out_consts = {}, {}
    for k in CONSTANT_KEYS:
        integer = k == "path_unmatched_cap"
        vals = grid[k]
        if not isinstance(vals, list) or not vals or len(set(vals)) != len(vals):
            raise ValueError(f"tuning_grid[{k}] must be a non-empty list without duplicates")
        out_grid[k] = tuple(_num(v, f"tuning_grid[{k}]", integer) for v in vals)
        c = _num(consts[k], f"constants[{k}]", integer)
        if c not in out_grid[k]:
            raise ValueError(f"constants[{k}]={c} is outside its tuning grid")
        out_consts[k] = c
    return RankingPolicy(raw["version"], MappingProxyType(verbs), frozenset(noise), MappingProxyType(hints),
                         MappingProxyType(out_grid), MappingProxyType(out_consts), canonical_sha256(raw),
                         canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS}))


@functools.lru_cache(maxsize=1)
def ranking() -> RankingPolicy:
    return load_ranking()
```

Change `POLICY_VERSIONS["search"]` to 3; in `intelligence_fingerprint` insert `ranking().sha256` before the versions JSON; in `policy_block` add `"ranking_sha256": ranking().sha256, "ranking_structure_sha256": ranking().structure_sha256`.

- [ ] **Step 4: Run full suite** → OK (expected failure remains). Also check `tests/test_layering.py` still passes (`from .. import sources` inside the function is fine).

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/policy.py tests/intelligence/test_policy.py tests/intelligence/test_search.py
git commit -m "policy: RankingPolicy loader with structure/full hashes; search policy version 3

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Structural signals and the single scoring algorithm

**Files:**
- Modify: `tools/atlassian_docs/intelligence/search.py`
- Modify: `tests/intelligence/test_search.py`
- Modify: `tests/test_layering.py` (AST test for AC-05)

**Interfaces:**
- Produces: `PathToken(origin: str, forms: frozenset)`; `IndexEntry` gains `path_tokens: tuple` and `source: str`, `method: str`; `path_tokens_for(path, noise) -> tuple[PathToken]`; `_structural_signals(entry, query_unigrams: tuple, exp_all: frozenset, rp) -> (float, dict)`; `_score(entry, exp, lexical_base, bonus_tokens, deprecated, pol)` returns lexical only; `search_operations` implements spec §6.6 verbatim; result items gain `signals`; `intelligence_policy` carries ranking hashes (from Task 5).
- Consumes: `policy.ranking()`; `tokenize_unigrams`, `token_forms`, `expand_token_forms`, `joined_query_forms` (Task 4).
- `build_index(operations, noise)`: `registry.py` is frozen and calls `build_index(operations)` positionally — keep the one-argument signature and read `policy.ranking().path_noise` lazily inside `build_index` via a local import (`from . import policy`), same pattern as `search_operations`.

- [ ] **Step 1: Failing tests** — add `TestStructuralSignals` and `TestScoringAlgorithm` to `tests/intelligence/test_search.py`

```python
class TestStructuralSignals(unittest.TestCase):
    def setUp(self):
        self.rp = policy.ranking()

    def test_path_tokens_model(self):
        toks = search.path_tokens_for("/rest/api/3/issue/{issueIdOrKey}/properties", self.rp.path_noise)
        self.assertEqual([t.origin for t in toks], ["issue", "properties"])
        self.assertEqual(toks[1].forms, frozenset({"properties", "property"}))
        self.assertEqual(search.path_tokens_for("/rest/api/3", self.rp.path_noise), ())          # review focus 2
        dup = search.path_tokens_for("/issue/{id}/issue", self.rp.path_noise)
        self.assertEqual([t.origin for t in dup], ["issue"])                                       # duplicate segment once
        camel = search.path_tokens_for("/issueTypeScheme", self.rp.path_noise)
        self.assertEqual([t.origin for t in camel], ["issue", "type", "scheme"])                  # unigrams, no joined form

    def _entry(self, path, method="GET", source="jira-platform"):
        return search.IndexEntry(f"{source}:{method}:{path}", {f: frozenset() for f in search.FIELD_WEIGHTS},
                                 search.path_tokens_for(path, self.rp.path_noise), source, method)

    def test_path_penalty_origin_once_and_cap(self):
        e = self._entry("/rest/api/3/issue/{k}/properties")
        val, sig = search._structural_signals(e, ("get", "issue"), frozenset({"get", "issue"}), self.rp)
        self.assertEqual(sig["path_unmatched"], {"value": -1.0, "tokens": ["properties"]})
        val2, sig2 = search._structural_signals(e, ("get", "property"), frozenset({"get", "property"}), self.rp)
        self.assertEqual(sig2["path_unmatched"]["value"], 0.0)                                    # plural matched via forms
        deep = self._entry("/a/b/c/d/e")
        _, sig3 = search._structural_signals(deep, ("zzz",), frozenset({"zzz"}), self.rp)
        self.assertEqual(sig3["path_unmatched"]["value"], -self.rp.constants["path_unmatched_cap"] * self.rp.constants["path_unmatched_penalty"])

    def test_method_intent(self):
        e = self._entry("/x", method="POST")
        self.assertEqual(search._structural_signals(e, ("add", "x"), frozenset({"add", "x"}), self.rp)[1]["method_intent"], {"value": 2.0, "allowed": ["POST"]})
        self.assertEqual(search._structural_signals(e, ("get", "x"), frozenset({"get", "x"}), self.rp)[1]["method_intent"], {"value": -2.0, "allowed": ["GET"]})
        self.assertEqual(search._structural_signals(e, ("x",), frozenset({"x"}), self.rp)[1]["method_intent"], {"value": 0.0, "allowed": []})
        self.assertEqual(search._structural_signals(e, ("get", "delete", "x"), frozenset(), self.rp)[1]["method_intent"]["value"], 0.0)   # conflict
        self.assertEqual(search._structural_signals(e, ("move", "x"), frozenset(), self.rp)[1]["method_intent"]["allowed"], ["POST", "PUT"])
        patch = self._entry("/x", method="PATCH")
        self.assertEqual(search._structural_signals(patch, ("update", "x"), frozenset(), self.rp)[1]["method_intent"]["value"], -2.0)  # review focus 1

    def test_product_hint(self):
        j = self._entry("/x", source="jira-software"); c = self._entry("/x", source="confluence")
        self.assertEqual(search._structural_signals(j, ("jira", "x"), frozenset(), self.rp)[1]["product_hint"], {"value": 3.0, "sources": ["jira-platform", "jira-software"]})
        self.assertEqual(search._structural_signals(c, ("jira", "x"), frozenset(), self.rp)[1]["product_hint"]["value"], 0.0)
        self.assertEqual(search._structural_signals(c, ("x",), frozenset(), self.rp)[1]["product_hint"], {"value": 0.0, "sources": []})


class TestScoringAlgorithm(unittest.TestCase):
    """End-to-end numbers on a synthetic state (spec §6.6, AC-07)."""
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})   # small, deterministic

    def test_hint_only_query_has_no_candidates(self):                                            # review focus 3
        out = search.search_operations(self.state, "jira")
        self.assertTrue(out.get("error") == "empty_query" or out["results"] == [])

    def test_limit_truncates_pinned_and_keeps_exact_flag(self):                                    # review focus 4
        state = make_state("jira-platform", "jira-software")
        out = search.search_operations(state, "getIssue", limit=1)
        self.assertEqual(len(out["results"]), 1); self.assertTrue(out["exact_match"]); self.assertIn("match", out["results"][0])

    def test_signals_shape_and_exact_zero(self):
        state = make_state("jira-platform")
        out = search.search_operations(state, "createIssue")
        pinned = out["results"][0]
        self.assertEqual(pinned["signals"], {"method_intent": {"value": 0.0, "allowed": []}, "path_unmatched": {"value": 0.0, "tokens": []}, "product_hint": {"value": 0.0, "sources": []}})
        other = out["results"][1]
        self.assertEqual(set(other["signals"]), {"method_intent", "path_unmatched", "product_hint"})
        self.assertEqual(set(out["intelligence_policy"]) >= {"ranking_sha256", "ranking_structure_sha256"}, True)
```

Add a numeric end-to-end test using a hand-built state (two synthetic operations via `models.Operation` from a tiny inline OpenAPI dict normalized with `normalizer.normalize_openapi`): op A `GET /widgets` summary "List widgets", op B `GET /widgets/{id}/history` summary "Widget history", op C deprecated `GET /widgets/legacy`. Query `"list widgets"`: assert A.score == (5·0 + 4·2 [summary: list, widgets] + 3·1 [path: widgets] + method 0 + ALL_MATCH 2) + method_intent(+2, GET) − path 0 = exactly the computed number; B gets path penalty −1 (`history` unmatched); C gets `× 0.7`; then a query whose structural penalty exceeds lexical (`"get zzz"` against a 5-deep path with `zzz` only in description) yields no result (clamp → 0 → excluded). Write the expected numbers in the test after computing them once by hand; the numbers must not be derived by calling the scorer.

Also add to `tests/test_layering.py`:

```python
    def test_ranking_constants_not_in_search_py(self):
        path = PKG / "intelligence" / "search.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        floats = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)}
        self.assertTrue(floats <= {0.0, 1.0, 0.7}, floats)      # DEPRECATED_FACTOR and the +1.0 pin are the only float literals
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for forbidden in ("METHOD_INTENT", "PRODUCT_HINTS", "PATH_NOISE", "VERB_METHODS"):
            self.assertNotIn(forbidden, names)
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

`IndexEntry` → `IndexEntry(key, fields, path_tokens, source, method)`; `PathToken` frozen dataclass; `path_tokens_for(path, noise)`; `build_index` fills them (local import of `policy` for `ranking().path_noise`). `_structural_signals`:

```python
def _structural_signals(entry, query_unigrams, exp_all, rp):
    c = rp.constants
    verbs = [t for t in query_unigrams if t in rp.verb_methods]
    allowed = None
    for v in verbs:
        allowed = rp.verb_methods[v] if allowed is None else (allowed & rp.verb_methods[v])
    if not allowed:
        mi = {"value": 0.0, "allowed": []}
    elif entry.method in allowed:
        mi = {"value": c["method_match_bonus"], "allowed": sorted(allowed)}
    else:
        mi = {"value": -c["method_mismatch_penalty"], "allowed": sorted(allowed)}
    unmatched = sorted(pt.origin for pt in entry.path_tokens if not (pt.forms & exp_all))
    pu = {"value": -min(len(unmatched), c["path_unmatched_cap"]) * c["path_unmatched_penalty"], "tokens": unmatched}
    hinted = set()
    for t in query_unigrams:
        hinted |= rp.product_hints.get(t, frozenset())
    ph = {"value": c["product_hint_bonus"] if entry.source in hinted else 0.0, "sources": sorted(hinted)}
    return mi["value"] + pu["value"] + ph["value"], {"method_intent": mi, "path_unmatched": pu, "product_hint": ph}
```

`search_operations` per spec §6.6: `unigrams = tokenize_unigrams(query)`; `base = expand_token_forms(unigrams)`; `lexical_base = base | joined_query_forms(query)`; `exp = expand_query(query, pol)` (its `.base` stays `_query_tokens(query)` for alias/rule triggering; pass `lexical_base` explicitly to `_score`); all-match: `all(token_forms(q) & matched_base for q in unigrams)` where `matched_base` is the union of `lexical_base ∩ field` over fields; candidates only if `lexical > 0`; `final = max(lexical + structural, 0) × factor`; drop `final == 0`; sort `(-final, deprecated, key)`; `pinned_score = (max non-pinned final or 0.0) + 1.0`; `results = pinned + candidates`, then `[:limit]`; `exact_match = bool(pinned)`; `total_matches = len(pinned) + len(candidates)`. `_item(op, s, signals, match=None)`. Keep `query_tokens`/`alias_tokens`/`expanded_tokens` fields as today (from `exp`).

- [ ] **Step 4: Run full suite** — `python -m unittest discover -s tests -t .`. Phase 2 tests that legitimately change: `test_all_match_bonus_ignores_joined_forms` (adapt to the new `_score` signature: pass `lexical_base` and `unigrams`; the assertion intent — joined form absent from entry does not cancel the bonus — is unchanged); any ordering test whose new order the spec makes more correct must be updated and the reason recorded in the report (ledger). Expected failure on the seed benchmark may now pass or fail; leave the decorator until Task 7.

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/search.py tests/intelligence/test_search.py tests/test_layering.py
git commit -m "search: method-intent, path-specificity and product-hint signals; single scoring algorithm with signals

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Fixtures with competitors, grid tuning script, seed 22/22, R4 aliases

**Files:**
- Modify: `tests/fixtures/openapi/make_openapi_fixtures.py` (+ `--cache DIR` option; new paths) and regenerate the three fixture JSONs **from the snapshot**
- Create: `tests/tune_search_ranking.py`
- Create: `tests/benchmarks/search-tuning-round1.jsonl`
- Modify: `tools/atlassian_docs/intelligence/data/search_ranking.json` (`constants` only, written by the script)
- Modify: `tools/atlassian_docs/intelligence/data/search_aliases.json` (`notes` for all entries; R4 additions only if needed)
- Modify: `tools/atlassian_docs/intelligence/policy.py` (`load_aliases` validates `notes`)
- Modify: `tests/intelligence/test_search.py` (remove `@expectedFailure`), `tests/benchmarks/test_evaluator.py` (`alias_notes_r4_only`, `tuning_log_adopted`), `tests/intelligence/test_policy.py` (notes validation)

**Interfaces:**
- `make_openapi_fixtures.py --cache DIR` (default `ROOT/.atlassian-docs`); SELECTIONS gain: jira-platform `/rest/api/3/issue/{issueIdOrKey}/properties`, `/rest/api/3/issuetypescheme/{issueTypeSchemeId}`, `/rest/api/3/jql/parse`, `/rest/api/3/projectvalidate/validProjectKey`, `/rest/api/3/issue/{issueIdOrKey}/assignee`, `/rest/api/3/issue/{issueIdOrKey}/comment`, `/rest/api/3/project/{projectIdOrKey}`, `/rest/api/3/attachment/{id}`, `/rest/api/3/user`, `/rest/api/3/users/search`, `/rest/api/3/users`; jira-software `/rest/software/1.0/sprint/{sprintId}/issue`, `/rest/agile/1.0/board`, `/rest/agile/1.0/backlog/{boardId}/issue`; confluence `/pages/{page-id}/properties/{property-id}`, `/pages/{page-id}/properties`, `/spaces/{id}/pages`, `/attachments/{id}`, `/pages/{id}/title`. (All verified present in the cache on 2026-09-30.)
- `tests/tune_search_ranking.py --cache-dir DIR [--dry-run] [--note TEXT]`: loads bench `seed` + `regression_negative`, builds state from the cache dir (same fake `sync_all` as diag), evaluates **every** grid combination (constants injected by constructing a `RankingPolicy` copy with new `constants`/`sha256` and patching `policy.ranking` for the run; index is built once — `path_noise` is frozen so the index does not depend on constants), applies spec §8.2 selection, writes `constants` into `search_ranking.json` (unless `--dry-run`), appends one line to `tests/benchmarks/search-tuning-round1.jsonl` per spec §8.3, prints the selected tuple and pass counts, exit 0 if 22/22 and 7/7 else 1.
- `search_aliases.json` gains top-level `notes` per spec §7 (`origin`, `seed_query_id`, `failure_classes`, `evidence`) for every alias word and `rule:<index>`; `load_aliases` requires `notes` to cover exactly the alias words and rule indices and validates the shape (`origin ∈ {"phase2.5","round1"}`; round1 entries need `seed_query_id` matching `^s-\d{3}$` and `"R4" ∈ failure_classes`).

- [ ] **Step 1: Failing tests**

`tests/benchmarks/test_evaluator.py`:
```python
ALIASES = RANKING.parent / "search_aliases.json"
TUNING_LOG = pathlib.Path(__file__).resolve().parent / "search-tuning-round1.jsonl"


class TestAliasNotesAndTuningLog(unittest.TestCase):
    def test_alias_notes_r4_only(self):
        raw = json.loads(ALIASES.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8"))
        seed_ids = {r["id"]: r for r in b["seed"]}
        expected_keys = set(raw["aliases"]) | {f"rule:{i}" for i in range(len(raw["rules"]))}
        self.assertEqual(set(raw["notes"]), expected_keys)
        per_seed = {}
        for k, n in raw["notes"].items():
            self.assertIn(n["origin"], ("phase2.5", "round1"))
            if n["origin"] == "round1":
                self.assertIn(n["seed_query_id"], seed_ids); self.assertIn("R4", n["failure_classes"])
                self.assertIn("R4", seed_ids[n["seed_query_id"]]["failure_classes"])
                per_seed[n["seed_query_id"]] = per_seed.get(n["seed_query_id"], 0) + 1
        self.assertTrue(all(c <= 1 for c in per_seed.values()), per_seed)

    def test_tuning_log_adopted(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8"))
        lines = [json.loads(l) for l in TUNING_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        adopted = [l for l in lines if l.get("adopted")]
        self.assertEqual(len(adopted), 1); self.assertEqual(adopted[0]["selected"], raw["constants"])
        for l in lines:
            for k, v in l["selected"].items():
                self.assertIn(v, raw["tuning_grid"][k])
            self.assertEqual(l["registry_fingerprint"], b["round1_seal"]["registry_fingerprint"])
```

`tests/intelligence/test_policy.py`: `test_alias_notes_required_and_validated` — loading a temp file without `notes`, with an unknown key in `notes`, or with `origin: "round1"` lacking `seed_query_id` raises `ValueError`; the bundled file loads.

`tests/intelligence/test_search.py`: remove `@unittest.expectedFailure`.

- [ ] **Step 2: Fixtures** — add `--cache` to the generator; run `python tests/fixtures/openapi/make_openapi_fixtures.py --cache "$ATLASSIAN_DOCS_ROUND1_CACHE"`; run twice and confirm identical output; run the full suite and fix tests that depended on fixture op counts (report each).

- [ ] **Step 3: Alias notes + loader validation** — add `notes` for the 8 existing aliases and 3 rules (`origin: "phase2.5"`, `seed_query_id: null`, `failure_classes: []`, `evidence: "phase2.5 §6.1"`); implement validation in `load_aliases` (notes are excluded from nothing — `sha256` still hashes the whole raw file).

- [ ] **Step 4: Tuning script** — write `tests/tune_search_ranking.py` (chunked); run `python tests/tune_search_ranking.py --cache-dir "$ATLASSIAN_DOCS_ROUND1_CACHE" --note "initial grid sweep"`. If the result is not 22/22 + 7/7, inspect the failing seed records: for those with `"R4" ∈ failure_classes` and still failing, add **one** alias or rule (spec §7 candidates: `jql → search` / `{jql} → searchandreconsileissuesusingjql, search`; `{issue, assignee} → assignissue`) with `origin: "round1"` notes, then re-run the script with `--note "alias:<word> for s-0xx (before: fail, after: ?)"`. Do not touch tables, grid, or any R1–R3 record via aliases. If 22/22 is still not reachable, stop and report `DONE_WITH_CONCERNS` with the failing top-5s; the controller rules.

- [ ] **Step 5: Run the full suite** → OK, no expected failures, seed 22/22 and regression 7/7 on fixtures.

- [ ] **Step 6: Commit** (one commit for fixtures + tests, one for the tuning script + adopted constants + aliases; both between B and C)

```bash
git add tests/fixtures tests/intelligence tests/benchmarks/test_evaluator.py tests/intelligence/test_policy.py tools/atlassian_docs/intelligence/policy.py tools/atlassian_docs/intelligence/data/search_aliases.json
git commit -m "test: competitor fixtures from snapshot, alias notes schema, seed 22/22 on fixtures

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git add tests/tune_search_ranking.py tests/benchmarks/search-tuning-round1.jsonl tools/atlassian_docs/intelligence/data/search_ranking.json
git commit -m "search: grid-exhaustive deterministic tuning (Round 1 constants adopted)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Diagnostic script, evaluation-code hash, docs

**Files:**
- Modify: `tests/diag_search_queries.py`
- Modify: `tests/benchmarks/round1_seal.py` (add `evaluation_code_sha256()` helper per spec §5.7 — or place it in `evaluator.py`; choose `evaluator.py` so the hash covers itself)
- Modify: `tests/benchmarks/test_evaluator.py` (`test_final_artifact` — skips with a printed reason when `tests/benchmarks/round1-final.json` is absent; when present, checks spec §5.8 (b),(c))
- Modify: `README.md`, `AGENTS.md`, `docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md` (§6 one line: "search policy version 3 is specified in the Round 1 spec"; §11.2 rule 5: `oneOf` → `anyOf`), `docs/phase3-readiness.md` (Round 1 section skeleton: decision record fields, state model per spec §11)

**Interfaces:**
- `diag_search_queries.py` options and output per spec §9: `--sets`, `--bench PATH`, `--cache-dir DIR`, `--json OUT`; seal check on start (exit 2 when `--bench` given and the loaded registry fingerprint/spec shas differ from `round1_seal`); JSON fields: sets, failures with top-5 `{key, score, signals}`, `git_commit`, `registry_fingerprint`, `intelligence_fingerprint`, `ranking_sha256`, `ranking_structure_sha256`, `alias_sha256`, `evaluation_code_sha256`, `sealed_sha256` (`{"held_out", "negative"}` when `--bench`), `spec_sha256`, `run_at`.
- `evaluator.evaluation_code_sha256(root) -> str` over the four files sorted by path: `sha256(concat(path.encode() + b"\0" + raw_bytes + b"\0"))`.

- [ ] **Step 1: Failing tests** — `test_evaluation_code_sha256_is_stable_and_path_sensitive` (hash of the repo files is 64 hex and equals a recomputation; renaming the root argument changes nothing because paths are relative to root); `test_diag_cli_sets_and_cache_dir` (run the script via `subprocess` with `--sets seed --cache-dir <a temp copy of the fixtures? no — use the fixture-based state>`: simplest is to give the script a `--fixtures` mode? Not in spec. Instead unit-test the internal functions: refactor `main()` into `run(args) -> dict` and test `run(["--sets", "seed", "--cache-dir", str(snapshot_or_skip)])` skipping when no cache dir is available; test the seal-mismatch branch by passing a fake `round1_seal`).
- [ ] **Step 2: Implement** the script (chunked), keeping exit 0 for normal runs and exit 2 for seal mismatch.
- [ ] **Step 3: Docs** — README Phase 2.5 section: add "검색 품질 라운드 1" paragraph (signals, product hints, version 3, tuning script, sealed benchmark procedure, `--cache-dir`); AGENTS.md: one line — "`signals` explains why a result ranked; add a product word (`jira`/`confluence`) to disambiguate"; Phase 2.5 spec §6/§11.2 lines; readiness skeleton with the decision-record fields from commit B (controller fills values).
- [ ] **Step 4: Run full suite; commit**

```bash
git add tests/diag_search_queries.py tests/benchmarks README.md AGENTS.md docs
git commit -m "diag: sealed-set evaluation with snapshot check and provenance; Round 1 docs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9 [controller]: Commit C — freeze

- [ ] Run the full suite; run `python tests/diag_search_queries.py --sets seed,regression_negative --cache-dir "$ATLASSIAN_DOCS_ROUND1_CACHE"` → 22/22, 7/7 (this is the last non-gating run).
- [ ] Compute `evaluation_code_sha256` (`python -c "from tests.benchmarks import evaluator as ev, pathlib; print(ev.evaluation_code_sha256(pathlib.Path('.')))"`), append "Round 1 frozen at <HEAD>" + the hash to `docs/phase3-readiness.md`, commit:
  ```bash
  git add docs/phase3-readiness.md
  git commit -m "Round 1 freeze (commit C): scorer, policy data and evaluator frozen

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
  ```
- [ ] Verify AC-01 interval rule: `git log --name-only T..B` and `C..HEAD` touch none of the mutable files.

### Task 10 [controller]: Commit D — unseal, final evaluation, readiness

- [ ] From the commit-C checkout: `python tests/diag_search_queries.py --bench "$ATLASSIAN_DOCS_SEALED_BENCH" --cache-dir "$ATLASSIAN_DOCS_ROUND1_CACHE" --json tests/benchmarks/round1-final.json` — exactly once. Exit 2 means snapshot drift: stop and investigate; do not re-run against another cache.
- [ ] `python tests/benchmarks/round1_seal.py unseal --plain "$ATLASSIAN_DOCS_SEALED_BENCH" --bench tests/benchmarks/search_queries.json`.
- [ ] Run the full suite (now `test_final_artifact`, `sealed_or_plain`, `hidden_set_rules` run for real) → OK.
- [ ] Fill the readiness 2nd-evaluation row and attestation fields; commit only `tests/benchmarks/search_queries.json`, `tests/benchmarks/round1-final.json`, `docs/phase3-readiness.md`:
  ```bash
  git commit -m "Round 1 final evaluation (commit D): unseal held_out/negative, record gate result

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
  ```
- [ ] AC pass: walk AC-01..AC-16 with the cited commands; record in the readiness doc. Gate result is recorded as `passed`/`failed`; no retuning either way.

---

## Spec coverage map

| Spec § | Task |
|---|---|
| 5.1, 5.2 (schema, commit A) | 1 |
| 5.3 (commit T, snapshot) | 2 |
| 5.4, 5.5 (generation rules, seal, commit B) | 3 |
| 5.6 (implementation window) | 4–7 |
| 5.7 (commit C), 5.8 (commit D), 5.9 (gate) | 9, 10, 8 (tests) |
| 6.1 token contract | 4 |
| 6.2 policy data, loader, hashes | 2, 5 |
| 6.3–6.7 signals, algorithm, response | 6 |
| 7 alias R4 rules, notes | 7 |
| 8 tuning (grid, selection, log) | 7 |
| 9 diagnostic script | 8 |
| 10.1 unit tests | 4, 5, 6, 7 |
| 10.2 benchmark integrity tests | 1, 2, 7, 8 |
| 11 state model / readiness | 8, 10 |
| 12 AC | 10 (walk), tests throughout |

## Self-review notes

- Placeholder scan: the only intentionally deferred literal is `RANKING_STRUCTURE_SHA256 = "<fill in Step 3>"` in Task 2, filled inside the same task before commit.
- Type consistency: `IndexEntry(key, fields, path_tokens, source, method)` is introduced in Task 6 and used by the Task 6 tests; `registry.build_source_registry` (frozen) calls `search.build_index(ns.operations)` — signature kept. `_score` signature changes in Task 6; the only external caller is `test_all_match_bonus_ignores_joined_forms`, updated there.
- Frozen-file check: Tasks 4–7 touch only `search.py`, `policy.py`, the two data files and tests; no frozen module is edited. `registry.py` needs no change because `build_index` keeps its signature and `IndexEntry` gains fields with values computed inside `build_index`.
- Interval rule: Task 4 must start only after commit B exists (controller gate). Task 2 deliberately contains no `policy.py` change.
