# Search Quality Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repeat the sealed-evaluation procedure with vocabulary-only changes (general verb inventory, general concept lexicon, seed-derived alias candidates), all frozen before a fresh hidden set is generated, tune once through a deterministic one-way pipeline, and measure the sealed set exactly once.

**Architecture:** No scorer change. `policy.py` gains a round-aware alias-notes schema (the only production change). All Round 2 tooling is completed in commit H and frozen by hash at commit T: `tests/benchmarks/round_seal.py` (generalized seal + freeze entry), `tests/benchmarks/alias_candidates_tool.py` (concept tokens, verb report, method-safety, candidates, R5/R6 classification, lexicon gate), `tests/benchmarks/concept_lexicon_check.py` (lexicon normalization/validation/merge), and `tests/tune_search_ranking.py` rewritten as a one-way pipeline (constants once → deterministic alias proposer once → final check) that only ever starts from the B baseline. Controller tasks run the pre-T dependency order, generate the lexicon and the hidden set in stateless contexts, seal, dispatch the frozen worker brief, and evaluate at D (or close at F).

**Tech Stack:** Python ≥ 3.10 stdlib only under `tools/`; `unittest`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-02-search-quality-round2-design.md` v1.10 (external review: 10 rounds, final verdict "구현 계획으로 진행 가능"). The spec is binding; this plan is its argument.

**Plan version:** v3 (after external plan reviews 1 and 2 — see "Plan revision notes" at the end).

## Global Constraints

- Canonical test command: `python -m unittest discover -s tests -t .` (405 OK at `57eb1e5`; omitting `-t .` makes `tests/mcp` shadow the SDK and gives spurious ImportErrors).
- Baseline commit for all "unchanged" checks: `95b8de0` (pre-work merge). Immutable from now to the terminal commit (spec §4, AC-05/AC-09): Round 1 spec §4 list, `tools/atlassian_docs/intelligence/search.py`, `tools/atlassian_docs/intelligence/data/operation_quirks.json`, `tests/benchmarks/round1-final.json`, `tests/benchmarks/search-tuning-round1.jsonl`, the `round1_seal` object inside the bench, and the Round 1 section of `docs/phase3-readiness.md` (from the line `## Search Quality Round 1 — decision record` up to, not including, the line `### Round 2 pre-work`).
- `policy.py` may change only in the housekeeping commit(s) H/H′ (Task 1) and only in `_check_alias_notes`. After the last H′ every file in `TOOLING_FILES` (Task 3) is immutable until the terminal commit (D or F).
- Commit naming: Tasks 1–7 produce development commits H1..H7; **`housekeeping_commit` = H7** (the last of them, or the last H′ if a pre-T defect is fixed). AC-05's immutability window starts there. For AC-01a, `95b8de0..housekeeping_commit` is the *housekeeping range* in which `policy.py` and the tooling may change; the AC verifier treats that range as a single H.
- Commit order (spec §5): H1..H7 (tooling, Tasks 1–7) → S (source snapshot) → pre-T dependency order → T (freeze) → generation (stateless) → B (seal, then user encrypts the plaintext) → tuning (frozen worker brief, one-way pipeline) → C → D, or B → F on tuning failure. Controller-only steps are marked **[controller]**; user-only steps **[user]**.
- Sealed plaintext path `~/.atlassian_api_updater/sealed/round2-sealed.json` is never given to an implementer or a tuning worker. After B only `round2-sealed.json.enc` exists; no agent knows the passphrase.
- Source snapshot S: `~/.atlassian_api_updater/round2-cache/` (`$ATLASSIAN_DOCS_ROUND2_CACHE`), created once after H; every catalog-dependent step reads only S.
- `POLICY_VERSIONS["search"]` stays 3. `search_ranking.json` tables other than `verb_methods` never change; `constants` change only inside the tuning run; `search_aliases.json` changes only at T (lexicon merge) and inside the tuning run (round2 entries).
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Chunked writes: no single tool call larger than ~60 lines.
- After commit B the repository working tree must be clean when the worker starts: every controller record (checkpoints, attempt ledger, shas) accumulates in `~/.atlassian_api_updater/round2-work/controller-events.jsonl` (outside the repo) and is rendered into `docs/phase3-readiness.md` only in the terminal commit (D or F).

## Review Focus

1. A seed query whose verbs conflict (allowed-method intersection empty) must count as "intent 0" in method-safety and R5 in classification, never as a crash (Task 4 `test_method_safety_conflicting_verbs_is_intent_zero`).
2. A lexicon synonym that is a plural of a catalog word (`files`) must be rejected after normalization, not kept because the raw string is absent from the catalog (Task 5 `test_plural_synonym_rejected_after_normalization`).
3. The alias proposer must not adopt an alias that fixes the target seed but breaks a regression_negative record (Task 6 `test_proposer_rejects_change_that_breaks_regression`).
4. Loading `search_aliases.json` with a `round1` note that lacks `candidate_word` must still succeed, while a `round2` note without it must fail (Task 1 `test_round_note_schema_is_round_aware`).
5. `round_seal.py seal --round 2` on a bench that already has `round1_seal` but no `round2_seal` must seal, and must refuse when `round2_seal` exists (Task 2 `test_seal_key_is_per_round`).

---

### Task 1: Round-aware alias-notes schema in `policy.py` (commit H1)

**Files:**
- Modify: `tools/atlassian_docs/intelligence/policy.py:57-74`
- Test: `tests/intelligence/test_policy.py`

**Interfaces:**
- Produces: `policy._check_alias_notes(notes, expected_keys)` accepting origins `phase2.5`, `round{N}` (N ≥ 1), `lexicon-r{N}` (N ≥ 1). `round1` keeps the old rule (`seed_query_id` + `R4`). `round{N≥2}` requires `seed_query_id` (`s-NNN`), non-empty string `candidate_word`, and `R6` in `failure_classes`. `lexicon-r{N}` and `phase2.5` require `seed_query_id: null`; `lexicon-r{N}` additionally `failure_classes == []`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/intelligence/test_policy.py` inside `TestAliases`:

```python
    def test_round_note_schema_is_round_aware(self):
        ph = {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "phase2.5 §6.1"}
        base = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"feedback": ["comment"]},
                "rules": [{"when_all": ["issue", "key"], "add": ["getissue"]}]}
        r1 = {"origin": "round1", "seed_query_id": "s-015", "failure_classes": ["R4"], "evidence": "x"}
        r2 = {"origin": "round2", "seed_query_id": "s-024", "candidate_word": "feedback", "failure_classes": ["R6"], "evidence": "x"}
        lx = {"origin": "lexicon-r2", "seed_query_id": None, "failure_classes": [], "evidence": "concept lexicon r2"}
        for good in (r1, r2, lx):
            policy.load_aliases(self._write({**base, "notes": {"feedback": good, "rule:0": ph}}))
        bads = [{**r2, "candidate_word": None}, {k: v for k, v in r2.items() if k != "candidate_word"},
                {**r2, "failure_classes": ["R4"]}, {**r2, "seed_query_id": None}, {**r2, "origin": "round0"},
                {**r2, "origin": "round02"}, {**r2, "origin": "round9x"}, {**lx, "seed_query_id": "s-001"},
                {**lx, "failure_classes": ["R6"]}, {**lx, "origin": "lexicon-r0"}, {**r1, "candidate_word": 3}]
        for bad in bads:
            with self.assertRaises(ValueError, msg=repr(bad)):
                policy.load_aliases(self._write({**base, "notes": {"feedback": bad, "rule:0": ph}}))

    def test_legacy_alias_subset_unchanged_by_schema_change(self):
        """AC-17: the phase2.5 + round1 subset of search_aliases.json (aliases, rules, notes) is pinned; Round 2 additions
        (lexicon-r2, round2) are stripped before hashing, so the test survives commit T."""
        raw = json.loads((policy.DATA_DIR / "search_aliases.json").read_text(encoding="utf-8"))
        self.assertEqual(policy.canonical_sha256(legacy_alias_subset(raw)), LEGACY_ALIAS_SUBSET_SHA256)
        policy.load_aliases()                                   # the whole file still loads under the new schema


def legacy_alias_subset(raw: dict) -> dict:
    keep = {k for k, n in raw["notes"].items() if n.get("origin") in ("phase2.5", "round1")}
    rules = [r for i, r in enumerate(raw["rules"]) if f"rule:{i}" in keep]
    return {"version": raw["version"], "alias_damping": raw["alias_damping"], "rule_damping": raw["rule_damping"],
            "aliases": {w: v for w, v in raw["aliases"].items() if w in keep}, "rules": rules,
            "notes": {k: n for k, n in raw["notes"].items() if k in keep}}
```

Add near the top of the test module:

```python
LEGACY_ALIAS_SUBSET_SHA256 = "c430e96177612510b94427fa80c1f98c2e6cb1b0e20872a4505964f5df055be3"   # canonical sha of legacy_alias_subset(file at 95b8de0); equals the Round 1 alias_sha256 because the file has no Round 2 entries yet
```

(`{**r1, "candidate_word": 3}` is in `bads` because a non-string `candidate_word` is rejected for every origin.) Put `legacy_alias_subset` and the constant at module level above the class.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.intelligence.test_policy -k round_note -v`
Expected: FAIL (`round2` / `lexicon-r2` origins rejected by the tuple check).

- [ ] **Step 3: Implement**

Replace lines 57–74 of `policy.py` (`_NOTE_ORIGINS` … end of `_check_alias_notes`) with:

```python
_NOTE_ORIGIN = re.compile(r"^(phase2\.5|round([1-9]\d*)|lexicon-r([1-9]\d*))$")
_SEED_ID = re.compile(r"s-\d{3}")               # always fullmatch


def _check_alias_notes(notes, expected_keys: set) -> None:
    """Round 2 spec §8: provenance notes per alias word / rule:<index>, schema branched by origin:
    phase2.5 (legacy), round1 (seed_query_id + R4), round>=2 (seed_query_id + candidate_word + R6),
    lexicon-rN (seed_query_id null, failure_classes empty)."""
    if not isinstance(notes, dict) or set(notes) != expected_keys:
        raise ValueError("alias 'notes' must cover exactly the alias words and rule:<index> keys")
    for key, n in notes.items():
        if not isinstance(n, dict) or not isinstance(n.get("origin"), str) \
                or not isinstance(n.get("failure_classes"), list) or not isinstance(n.get("evidence"), str):
            raise ValueError(f"alias note {key!r} must have origin, failure_classes and evidence")
        m = _NOTE_ORIGIN.fullmatch(n["origin"])
        if m is None:
            raise ValueError(f"alias note {key!r} has unknown origin {n['origin']!r}")
        cw, sid = n.get("candidate_word"), n.get("seed_query_id")
        if cw is not None and (not isinstance(cw, str) or not cw):
            raise ValueError(f"alias note {key!r}: candidate_word must be a non-empty string")
        if m.group(2):                                          # round N
            if not isinstance(sid, str) or not _SEED_ID.fullmatch(sid):
                raise ValueError(f"{n['origin']} alias note {key!r} needs seed_query_id s-NNN")
            if int(m.group(2)) == 1:
                if "R4" not in n["failure_classes"]:
                    raise ValueError(f"round1 alias note {key!r} needs R4 in failure_classes")
            elif "R6" not in n["failure_classes"] or cw is None:
                raise ValueError(f"{n['origin']} alias note {key!r} needs candidate_word and R6 in failure_classes")
        else:                                                   # phase2.5 / lexicon-rN
            if sid is not None:
                raise ValueError(f"{n['origin']} alias note {key!r} must have seed_query_id null")
            if m.group(3) and n["failure_classes"] != []:
                raise ValueError(f"{n['origin']} alias note {key!r} must have empty failure_classes")
```

- [ ] **Step 4: Run the full suite**

Run: `python -m unittest discover -s tests -t .`
Expected: all OK (405 + 2).

- [ ] **Step 5: Commit**

```bash
git add tools/atlassian_docs/intelligence/policy.py tests/intelligence/test_policy.py
git commit -m "policy: round-aware alias-notes schema (round>=2 needs candidate_word+R6; lexicon-rN)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Generalize the seal tool to `round_seal.py --round N` and add the `freeze` command (commit H2)

**Files:**
- Rename: `tests/benchmarks/round1_seal.py` → `tests/benchmarks/round_seal.py` (`git mv`)
- Rename: `tests/benchmarks/test_round1_seal.py` → `tests/benchmarks/test_round_seal.py` (`git mv`)
- Modify: `tests/benchmarks/test_evaluator.py` (two `from tests.benchmarks import round1_seal as rs` → `round_seal`), `tests/intelligence/test_search.py:251` (same import)
- Modify: `README.md` (one paragraph under the Round 1 section: the tool is now `round_seal.py --round N`)

**Interfaces:**
- Produces: module constants become functions of the round: `section_origin(round) -> dict`, `seal_key(round) -> str` (`f"round{round}_seal"`); `machine_check(plain, bench, internal_catalog, round=1)`; `seal_metadata(records, round, section_name)` unchanged; `load_catalogs_from_cache(cache_dir, round=1)` (snapshot label `round{N}-snapshot`); CLI subcommands take `--round N` (default 1); new `cmd_freeze` (Task 3 fills its hash list; here it only writes `round`, `structure_sha256`, `verb_inventory_sha256`, `source_registry_fingerprint`, `source_spec_sha256`).
- Produces: `seal` writes `bench[seal_key]` with the Round 1 fields plus `"machine_check": "passed"` and `"origins": {"held_out": "held_out-rN", "negative": "negative-rN"}` (AC-04 checkpoint record).
- Produces: the Round 2 negative machine rule (spec §5.3): `phrase_tokens(text) -> tuple` (lowercase, split on non-alphanumerics, drop STOPWORDS, `evaluator.singular` each, order kept) and, for `round >= 2`, a violation when a negative query's phrase equals any op's summary phrase or last-literal-path-segment phrase. `evaluator.singular` is a stdlib copy of `search.singular`.
- Produces: `validate_replacement_output(obj, expected_ids) -> list[str]`, `merge_replacements(plain, replacements) -> dict`, `coverage_manifest(plain, review_attempt_by_id) -> dict` (Task 11 uses them); `validate_reviewer_output(obj, ids) -> list[str]` (object with exactly `ids` as keys, each `{"accept": bool, "reason": str}`) and `verify_freeze(round, cache_dir) -> list[str]` + CLI `verify-freeze --round N --cache-dir S` (registry fingerprint and all three source spec shas equal the `round_freeze` entry; exit 1 on mismatch).

- [ ] **Step 1: Rename files and fix imports**

```bash
git mv tests/benchmarks/round1_seal.py tests/benchmarks/round_seal.py
git mv tests/benchmarks/test_round1_seal.py tests/benchmarks/test_round_seal.py
sed -i '' 's/from tests.benchmarks import round1_seal as rs/from tests.benchmarks import round_seal as rs/' tests/benchmarks/test_round_seal.py tests/benchmarks/test_evaluator.py tests/intelligence/test_search.py
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/benchmarks/test_round_seal.py`:

```python
class TestRoundParameter(unittest.TestCase):
    def test_origin_and_seal_key_follow_round(self):
        self.assertEqual(rs.section_origin(2), {"held_out": "held_out-r2", "negative": "negative-r2"})
        self.assertEqual(rs.seal_key(2), "round2_seal")
        plain = valid_plain()
        self.assertEqual(rs.machine_check(plain, BENCH, CAT, round=1), [])
        msgs = rs.machine_check(plain, BENCH, CAT, round=2)
        self.assertTrue(all("origin" in m for m in msgs) and len(msgs) == 24)

    def test_seal_key_is_per_round(self):
        import json, pathlib, tempfile
        from unittest import mock
        plain = valid_plain()
        for r in plain["held_out"] + plain["negative"]:
            r["origin"] = r["origin"].replace("-r1", "-r2")
        bench = {**BENCH, "held_out": [], "negative": [], "round1_seal": {"held_out_sha256": "0" * 64}}
        with tempfile.TemporaryDirectory() as td:
            bp, pp = pathlib.Path(td) / "b.json", pathlib.Path(td) / "p.json"
            bp.write_text(json.dumps(bench)); pp.write_text(json.dumps(plain))
            fake = lambda cache_dir, round=1: (rs.generator_view(CAT), CAT, "f" * 64, {"jira-platform": "a" * 64})
            with mock.patch.object(rs, "load_catalogs_from_cache", fake), mock.patch("builtins.print"):
                self.assertEqual(rs.main(["seal", "--round", "2", "--plain", str(pp), "--bench", str(bp), "--cache-dir", td]), 0)
                out = json.loads(bp.read_text())
                self.assertIn("round2_seal", out); self.assertIn("round1_seal", out)
                self.assertEqual(out["round2_seal"]["machine_check"], "passed")
                self.assertEqual(out["round2_seal"]["origins"], rs.section_origin(2))
                self.assertEqual(out["held_out"]["round"], 2)
                self.assertEqual(rs.main(["seal", "--round", "2", "--plain", str(pp), "--bench", str(bp), "--cache-dir", td]), 1)


class TestRound2NegativePhraseRule(unittest.TestCase):
    def _plain(self):
        plain = valid_plain()
        for r in plain["held_out"] + plain["negative"]:
            r["origin"] = r["origin"].replace("-r1", "-r2")
        return plain

    def test_phrase_tokens(self):
        self.assertEqual(rs.phrase_tokens("Get all the Boards"), ("get", "all", "board"))
        self.assertEqual(rs.phrase_tokens("/rest/agile/1.0/board"), ("rest", "agile", "board"))

    def test_negative_equal_to_summary_phrase_rejected(self):
        plain = self._plain(); plain["negative"][0]["query"] = "get all boards"          # summary of D, 3 words
        msgs = rs.machine_check(plain, BENCH, CAT, round=2)
        self.assertTrue(any(m.startswith("n-001") and "summary phrase" in m for m in msgs), msgs)
        plain1 = valid_plain(); plain1["negative"][0]["query"] = "get all boards"
        self.assertEqual(rs.machine_check(plain1, BENCH, CAT, round=1), [])             # Round 1 rule set unchanged

    def test_negative_equal_to_last_path_segment_rejected(self):
        plain = self._plain(); plain["negative"][1]["query"] = "assignee of this"       # 3 words; of/this are STOPWORDS
        self.assertEqual(rs.phrase_tokens(plain["negative"][1]["query"]), rs.phrase_tokens(rs._last_literal_segment(F)))
        msgs = rs.machine_check(plain, BENCH, CAT, round=2)
        self.assertTrue(any(m.startswith("n-002") and "path phrase" in m for m in msgs), msgs)

    def test_valid_round2_plain_has_no_violations(self):
        self.assertEqual(rs.machine_check(self._plain(), BENCH, CAT, round=2), [])


class TestReviewerOutputValidator(unittest.TestCase):
    def test_exact_keys_and_schema(self):
        ids = ["h-001", "n-001"]
        good = {"h-001": {"accept": True, "reason": "ok"}, "n-001": {"accept": False, "reason": "answerable"}}
        self.assertEqual(rs.validate_reviewer_output(good, ids), [])
        self.assertTrue(rs.validate_reviewer_output({"h-001": good["h-001"]}, ids))                         # missing
        self.assertTrue(rs.validate_reviewer_output({**good, "h-999": good["h-001"]}, ids))                 # extra
        self.assertTrue(rs.validate_reviewer_output({**good, "n-001": {"accept": "no", "reason": "x"}}, ids))  # non-bool
        self.assertTrue(rs.validate_reviewer_output({**good, "n-001": "reject"}, ids))                       # non-object
        self.assertTrue(rs.validate_reviewer_output(["h-001"], ids))


class TestVerifyFreeze(unittest.TestCase):
    def test_verify_freeze_compares_fingerprint_and_spec_shas(self):
        from unittest import mock
        shas = {"jira-platform": "a" * 64, "jira-software": "b" * 64, "confluence": "c" * 64}
        entry = {"round": 2, "source_registry_fingerprint": "f" * 64, "source_spec_sha256": dict(shas)}
        fake = lambda cache_dir, round=1: ([], CAT, "f" * 64, dict(shas))
        with mock.patch.object(rs, "load_catalogs_from_cache", fake), mock.patch.object(rs.ev, "freeze_for", lambda r: entry):
            self.assertEqual(rs.verify_freeze(2, "x"), [])
        bad = lambda cache_dir, round=1: ([], CAT, "f" * 64, {**shas, "confluence": "d" * 64})
        with mock.patch.object(rs, "load_catalogs_from_cache", bad), mock.patch.object(rs.ev, "freeze_for", lambda r: entry):
            self.assertEqual(rs.verify_freeze(2, "x"), ["spec_sha256[confluence] differs from round_freeze"])

class TestReplacementHelpers(unittest.TestCase):
    def test_validate_and_merge_replacements(self):
        plain = valid_plain()
        new = [{**plain["held_out"][2], "query": "wipe out the whole ticket"}]
        self.assertEqual(rs.validate_replacement_output(new, ["h-003"]), [])
        self.assertTrue(rs.validate_replacement_output(new, ["h-003", "h-004"]))                 # missing
        self.assertTrue(rs.validate_replacement_output(new + [plain["held_out"][0]], ["h-003"]))  # unexpected
        self.assertTrue(rs.validate_replacement_output({"h-003": new[0]}, ["h-003"]))            # not a list
        merged = rs.merge_replacements(plain, new)
        self.assertEqual(merged["held_out"][2]["query"], "wipe out the whole ticket")
        self.assertEqual([r["id"] for r in merged["held_out"]], [r["id"] for r in plain["held_out"]])
        self.assertEqual(merged["negative"], plain["negative"])
        manifest = rs.coverage_manifest(merged, {r["id"]: 1 for s in ("held_out", "negative") for r in merged[s]})
        self.assertEqual(len(manifest), 24); self.assertEqual(manifest["h-003"]["record_sha256"], rs.canonical_sha256(new[0]))
```

Run: `python -m unittest tests.benchmarks.test_round_seal -v` → Expected: FAIL (`section_origin`, `phrase_tokens`, `validate_reviewer_output`, `verify_freeze` missing).

- [ ] **Step 3: Implement the round parameter**

In `round_seal.py` replace the module header constants:

```python
def section_origin(round: int) -> dict:
    return {"held_out": f"held_out-r{round}", "negative": f"negative-r{round}"}


def seal_key(round: int) -> str:
    return f"round{round}_seal"


HIDDEN = (("held_out", 16), ("negative", 8))
SECTION_ID_PREFIX = {"held_out": "h-", "negative": "n-"}
```

(delete `ROUND = 1` and `SECTION_ORIGIN`). Update signatures and bodies:

- `load_catalogs_from_cache(cache_dir, round=1)`: `reg = registry.build_registry(srcs, f"round{round}-snapshot")`.
- `machine_check(plain, bench, internal_catalog, round=1)`: compute `origins = section_origin(round)` once and use `origins[sect]` in the origin check.
- `cmd_check`: pass `round=args.round`.
- `cmd_seal`: replace the `round1_seal` refusal with `key = seal_key(args.round); if key in bench: print(f"REFUSED: bench already has a {key} key"); return 1`; call `load_catalogs_from_cache(args.cache_dir, args.round)` and `machine_check(..., args.round)`; `seal_metadata(held, args.round, ...)`; write `bench[key] = {...same fields..., "machine_check": "passed", "origins": section_origin(args.round)}`.
- `cmd_unseal`: `seal = bench.get(seal_key(args.round)) or {}`; the success message names the key.
- `main`: `ap.add_argument("--round", type=int, default=1)` added to every subparser (define a helper `def _round(p): p.add_argument("--round", type=int, default=1)`).

Update the module docstring to show `--round N` on every command.

Add the Round 2 negative rule, the reviewer-output validator and `verify_freeze` (module level, after `_reuse_checks`; `ev` is `from tests.benchmarks import evaluator as ev`):

```python
def phrase_tokens(text) -> tuple:
    return tuple(ev.singular(t) for t in _TOKEN_SPLIT.split((text or "").lower()) if t and t not in STOPWORDS)


def _last_literal_segment(key) -> str:
    for seg in reversed(key.split(":", 2)[2].split("/")):
        if seg and not (seg.startswith("{") and seg.endswith("}")):
            return seg
    return ""


def _negative_phrase_checks(rec, internal_catalog):
    # Round 2 spec 5.3 machine rule: a negative query must not equal an op summary or last-path-segment phrase.
    q, out = phrase_tokens(rec.get("query") or ""), []
    for op in internal_catalog:
        if q == phrase_tokens(op.get("summary")):
            out.append(f"{rec.get('id', '?')}: negative query equals summary phrase of {op['key']}"); break
        if q == phrase_tokens(_last_literal_segment(op["key"])):
            out.append(f"{rec.get('id', '?')}: negative query equals path phrase of {op['key']}"); break
    return out


def validate_reviewer_output(obj, ids) -> list:
    # Hidden semantic reviewer output: exactly the record ids, each {"accept": bool, "reason": str}.
    if not isinstance(obj, dict):
        return ["reviewer output must be a JSON object keyed by record id"]
    wanted = set(ids)
    out = [f"missing id {i}" for i in ids if i not in obj] + [f"extra key {k!r}" for k in obj if k not in wanted]
    for k, v in obj.items():
        if k in wanted and (not isinstance(v, dict) or not isinstance(v.get("accept"), bool) or not isinstance(v.get("reason"), str)):
            out.append(f"{k}: value must be {{accept: bool, reason: str}}")
    return out


def validate_replacement_output(obj, expected_ids) -> list:
    """A replacement response must contain exactly the requested record ids (as a list of records) and nothing else."""
    if not isinstance(obj, list) or not all(isinstance(r, dict) for r in obj):
        return ["replacement output must be a JSON list of records"]
    got = [r.get("id") for r in obj]
    out = [f"missing replacement {i}" for i in expected_ids if i not in got] + [f"unexpected record {i!r}" for i in got if i not in set(expected_ids)]
    if len(set(got)) != len(got):
        out.append("duplicate ids in replacement output")
    return out


def merge_replacements(plain, replacements) -> dict:
    """Deterministic: replace records in place by id (section inferred from the id prefix); other records untouched."""
    by_id = {r["id"]: r for r in replacements}
    out = {sect: [by_id.get(r.get("id"), r) for r in plain.get(sect, [])] for sect, _ in HIDDEN}
    return out


def coverage_manifest(plain, review_attempt_by_id) -> dict:
    """B-time evidence: every final record -> its canonical sha and the review attempt that accepted it."""
    return {r["id"]: {"record_sha256": canonical_sha256(r), "accepted_review_attempt": review_attempt_by_id[r["id"]]}
            for sect, _ in HIDDEN for r in plain[sect]}


def verify_freeze(round: int, cache_dir) -> list:
    # S integrity checkpoint (spec 5.7): the snapshot still matches the round_freeze source fields.
    _, _, fp, shas = load_catalogs_from_cache(cache_dir, round)
    entry, out = ev.freeze_for(round), []
    if fp != entry.get("source_registry_fingerprint"):
        out.append("registry fingerprint differs from round_freeze")
    want = entry.get("source_spec_sha256") or {}
    for name in sorted(set(shas) | set(want)):
        if shas.get(name) != want.get(name):
            out.append(f"spec_sha256[{name}] differs from round_freeze")
    return out


def cmd_verify_freeze(args):
    problems = verify_freeze(args.round, args.cache_dir)
    for m in problems:
        print(f"MISMATCH {m}")
    print("freeze ok" if not problems else f"{len(problems)} mismatch(es)")
    return 1 if problems else 0
```

In `machine_check`, after `out += _record_checks(sect, rec, by_key, opid_sets)` add `if sect == "negative" and round >= 2: out += _negative_phrase_checks(rec, internal_catalog)`. Register `verify-freeze` (`_round(p); p.add_argument("--cache-dir", required=True); p.set_defaults(fn=cmd_verify_freeze)`). `evaluator.py` gets `singular` now (Task 3 keeps it): a stdlib copy of `search.singular` —

```python
IRREGULAR_SINGULAR = {"statuses": "status"}; UNCHANGED_PLURAL = frozenset({"series", "species", "news"})


def singular(t: str) -> str:
    if t in IRREGULAR_SINGULAR: return IRREGULAR_SINGULAR[t]
    if t in UNCHANGED_PLURAL or len(t) <= 3: return t
    if t.endswith("ies"): return t[:-3] + "y"
    if t.endswith(("sses", "shes", "ches", "xes")): return t[:-2]
    if t.endswith(("ss", "us", "is")): return t
    return t[:-1] if t.endswith("s") else t
```

`evaluator.freeze_for` does not exist until Task 3; add it in this task (Task 3 Step 4 shows the final form) so `verify_freeze` imports cleanly.

- [ ] **Step 4: Add the `freeze` command (hash list completed in Task 3)**

```python
ROUND_FREEZE = pathlib.Path(__file__).resolve().parent / "round_freeze.json"
RANKING_PATH = pathlib.Path(__file__).resolve().parents[2] / "tools" / "atlassian_docs" / "intelligence" / "data" / "search_ranking.json"


def freeze_entry(round: int, cache_dir) -> dict:
    """Round 2 spec §4: the per-round freeze record (hashes completed in evaluator.round_freeze_hashes)."""
    from tests.benchmarks import evaluator as ev
    _, _, fp, shas = load_catalogs_from_cache(cache_dir, round)
    raw = _read_json(RANKING_PATH)
    entry = {"round": round, "structure_sha256": canonical_sha256({k: raw[k] for k in ev.STRUCTURE_KEYS}),
             "verb_inventory_sha256": canonical_sha256(raw["verb_methods"]),
             "source_registry_fingerprint": fp, "source_spec_sha256": shas}
    entry.update(ev.round_freeze_hashes(round))
    return entry


def cmd_freeze(args):
    freeze = _read_json(ROUND_FREEZE)
    if any(e.get("round") == args.round for e in freeze):
        print(f"REFUSED: round_freeze.json already has a round {args.round} entry")
        return 1
    entry = freeze_entry(args.round, args.cache_dir)
    _write_json(ROUND_FREEZE, freeze + [entry])
    for k, v in entry.items():
        print(f"{k}: {v}")
    return 0
```

Register: `p = sub.add_parser("freeze"); _round(p); p.add_argument("--cache-dir", required=True); p.set_defaults(fn=cmd_freeze)`. `ev.STRUCTURE_KEYS` and `ev.round_freeze_hashes` come from Task 3; until then add a temporary `STRUCTURE_KEYS` tuple in evaluator (Task 3 replaces it) — do Task 3 immediately after.

- [ ] **Step 5: README paragraph**

In `README.md` after line 279 add one paragraph: 봉인 도구는 `tests/benchmarks/round_seal.py`이며 모든 하위 명령이 `--round N`을 받는다(기본 1); `freeze --round N --cache-dir S`는 `tests/benchmarks/round_freeze.json`에 라운드 동결 항목을 추가한다.

- [ ] **Step 6: Run the suite and commit**

Run: `python -m unittest discover -s tests -t .` → Expected: OK (freeze tests come in Task 3).

```bash
git add -A tests/benchmarks tests/intelligence/test_search.py README.md
git commit -m "benchmarks: round_seal.py --round N (origin/seal key per round), freeze command, AC-04 checkpoint record

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Round-freeze list, tooling hash, R5/R6 schema, Round 1 invariants (commit H3)

**Files:**
- Modify: `tests/benchmarks/round_freeze.json` (object → one-element list)
- Modify: `tests/benchmarks/evaluator.py`
- Modify: `tests/benchmarks/test_evaluator.py`

**Interfaces:**
- Produces in `evaluator.py`: `_CLASSES = {"R1".."R6"}`; `STRUCTURE_KEYS`; `ROUND_FREEZE` path; `load_round_freeze(path=ROUND_FREEZE) -> list`; `current_round(freeze=None) -> dict` (last entry); `freeze_for(round, freeze=None) -> dict`; `files_sha256(root, files) -> str` (path + NUL + bytes + NUL, sorted); `EVALUATION_CODE_FILES` (6 files: evaluator.py, test_evaluator.py, diag_search_queries.py, tune_search_ranking.py, round_seal.py, alias_candidates_tool.py); `TOOLING_FILES` (EVALUATION_CODE_FILES + `tests/benchmarks/concept_lexicon_check.py`, `tests/test_tune_search_ranking.py`, `tests/test_diag_search_queries.py`, `tests/intelligence/test_policy.py`, `tests/benchmarks/test_round_seal.py`); `tooling_code_sha256(root)`; `lexicon_aliases_sha256(raw_aliases, round) -> str`; `round_freeze_hashes(round, root=ROOT) -> dict` with keys `concept_lexicon_sha256`, `lexicon_aliases_sha256`, `alias_candidates_sha256`, `worker_brief_sha256`, `hidden_generation_prompt_sha256`, `hidden_reviewer_prompt_sha256`, `tooling_code_sha256`, `evaluation_code_sha256_at_T` (file hashes of `tools/atlassian_docs/intelligence/data/concept_lexicon.json`, `.../alias_candidates.json`, `tests/benchmarks/round{N}-worker-brief.md`, `round{N}-hidden-generation-prompt.md`, `round{N}-hidden-reviewer-prompt.md`; JSON files hashed canonically, markdown by bytes).
- `round_freeze.json` round 1 entry keeps `commit_T`.

- [ ] **Step 1: Convert the freeze file**

`tests/benchmarks/round_freeze.json` → `[{"round": 1, "commit_T": "26005e4", "structure_sha256": "6b3e79ca4d184b16793fc7fc6c7003733bd2081e35d951af21703c2c407a4de2"}]` (one line, as now).

- [ ] **Step 2: Write the failing tests**

In `test_evaluator.py` replace `RANKING_STRUCTURE_SHA256 = ...` and `STRUCTURE_KEYS = ...` with:

```python
RANKING_STRUCTURE_SHA256 = ev.current_round()["structure_sha256"]
STRUCTURE_KEYS = ev.STRUCTURE_KEYS
ROUND2_HASH_KEYS = {"structure_sha256", "verb_inventory_sha256", "concept_lexicon_sha256", "lexicon_aliases_sha256",
                    "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256",
                    "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T"}
```

Replace `test_round_freeze_file_shape` with:

```python
    def test_round_freeze_file_shape(self):
        f = ev.load_round_freeze()
        self.assertIsInstance(f, list); self.assertEqual([e["round"] for e in f], list(range(1, len(f) + 1)))
        self.assertEqual(set(f[0]), {"round", "commit_T", "structure_sha256"})
        for e in f[1:]:
            self.assertEqual(set(e), ROUND2_HASH_KEYS | {"round", "source_registry_fingerprint", "source_spec_sha256"})
            for k in ROUND2_HASH_KEYS | {"source_registry_fingerprint"}:
                self.assertRegex(e[k], r"^[0-9a-f]{64}$", k)
            self.assertEqual(set(e["source_spec_sha256"]), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(ev.current_round(), f[-1]); self.assertEqual(ev.freeze_for(1), f[0])

    def test_round2_freeze_hashes_match_files(self):
        e = ev.current_round()
        if e["round"] < 2:
            print("round 2 not frozen yet: hash equality checked after commit T"); return
        got = ev.round_freeze_hashes(e["round"])
        for k, v in got.items():
            self.assertEqual(e[k], v, k)
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(e["verb_inventory_sha256"], ev.canonical_sha256(raw["verb_methods"]))
        self.assertEqual(e["structure_sha256"], ranking_structure_sha256(raw))
```

Add a new class:

```python
R1_FINAL_SHA256 = "<paste>"      # python - <<'EOF' ... see Step 3 helper command
R1_TUNING_LOG_SHA256 = "<paste>"
R1_SEAL_SHA256 = "<paste>"
R1_READINESS_SECTION_SHA256 = "<paste>"
READINESS = ROOT / "docs" / "phase3-readiness.md"


def readiness_round1_section(text: str) -> str:
    start = text.index("## Search Quality Round 1 — decision record")
    end = text.index("### Round 2 pre-work", start)
    return text[start:end]


class TestRound1Invariants(unittest.TestCase):
    """AC-09: Round 1 artifacts never change after the pre-work merge 95b8de0."""
    def test_round1_artifacts_unchanged(self):
        self.assertEqual(ev.files_sha256(ROOT, ("tests/benchmarks/round1-final.json",)), R1_FINAL_SHA256)
        self.assertEqual(ev.files_sha256(ROOT, ("tests/benchmarks/search-tuning-round1.jsonl",)), R1_TUNING_LOG_SHA256)
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        self.assertEqual(ev.canonical_sha256(b["round1_seal"]), R1_SEAL_SHA256)
        section = readiness_round1_section(READINESS.read_text(encoding="utf-8"))
        self.assertEqual(ev.canonical_sha256(section), R1_READINESS_SECTION_SHA256)

    def test_schema_accepts_r5_r6(self):
        good = {"id": "s-001", "query": "a b", "expected_top1_any": ["k"], "forbidden_top1": [],
                "origin": "seed-r0", "failure_classes": ["R5", "R6"], "ambiguous": False}
        ev.check_schema("seed", [good])
        with self.assertRaises(ValueError):
            ev.check_schema("seed", [{**good, "failure_classes": ["R7"]}])
```

Update `TestEvaluationCodeSha256`: `EVAL_CODE_FILES` becomes the 6-file tuple; add `self.assertEqual(ev.tooling_code_sha256(ROOT), ev.files_sha256(ROOT, ev.TOOLING_FILES))` and `self.assertTrue(set(ev.EVALUATION_CODE_FILES) <= set(ev.TOOLING_FILES))`. In `test_tuning_log_adopted` keep the Round 1 log checks as they are (they read `search-tuning-round1.jsonl`).

- [ ] **Step 3: Pin the Round 1 constants**

```bash
python - <<'EOF'
import json, hashlib, pathlib
from tests.benchmarks import evaluator as ev
root = pathlib.Path(".")
print("final", ev.files_sha256(root, ("tests/benchmarks/round1-final.json",)))
print("log", ev.files_sha256(root, ("tests/benchmarks/search-tuning-round1.jsonl",)))
b = json.load(open("tests/benchmarks/search_queries.json")); print("seal", ev.canonical_sha256(b["round1_seal"]))
t = pathlib.Path("docs/phase3-readiness.md").read_text(encoding="utf-8")
s = t.index("## Search Quality Round 1 — decision record"); e = t.index("### Round 2 pre-work", s)
print("readiness", ev.canonical_sha256(t[s:e]))
EOF
```

(Run after Step 4 so `files_sha256` exists.) Paste the four values into the constants.

- [ ] **Step 4: Implement in `evaluator.py`**

```python
_CLASSES = {"R1", "R2", "R3", "R4", "R5", "R6"}
STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid", "baseline")
ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUND_FREEZE = pathlib.Path(__file__).resolve().parent / "round_freeze.json"
DATA_REL = "tools/atlassian_docs/intelligence/data"


def load_round_freeze(path=ROUND_FREEZE) -> list:
    freeze = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(freeze, list) or not freeze:
        raise ValueError("round_freeze.json must be a non-empty list of round entries")
    return freeze


def current_round(freeze=None) -> dict:
    return (freeze or load_round_freeze())[-1]


def freeze_for(round: int, freeze=None) -> dict:
    for e in freeze or load_round_freeze():
        if e.get("round") == round:
            return e
    raise KeyError(f"round {round} is not in round_freeze.json")


def files_sha256(root, files) -> str:
    """sha256 over path + NUL + raw bytes + NUL for each file, sorted by relative path."""
    root, h = pathlib.Path(root), hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes() + b"\0")
    return h.hexdigest()


EVALUATION_CODE_FILES = tuple(sorted(("tests/benchmarks/evaluator.py", "tests/benchmarks/test_evaluator.py",
                                      "tests/diag_search_queries.py", "tests/tune_search_ranking.py",
                                      "tests/benchmarks/round_seal.py", "tests/benchmarks/alias_candidates_tool.py")))
TOOLING_FILES = tuple(sorted(EVALUATION_CODE_FILES + ("tests/benchmarks/concept_lexicon_check.py",
                                                      "tests/benchmarks/test_round_seal.py", "tests/test_tune_search_ranking.py",
                                                      "tests/test_diag_search_queries.py", "tests/intelligence/test_policy.py")))


def evaluation_code_sha256(root) -> str:
    return files_sha256(root, EVALUATION_CODE_FILES)


def tooling_code_sha256(root) -> str:
    return files_sha256(root, TOOLING_FILES)


def lexicon_aliases_sha256(raw_aliases: dict, round: int) -> str:
    """Canonical hash of the alias words whose notes.origin == lexicon-r{round} (aliases + notes subsets)."""
    origin = f"lexicon-r{round}"
    notes = raw_aliases.get("notes") or {}
    words = sorted(w for w, n in notes.items() if isinstance(n, dict) and n.get("origin") == origin and w in (raw_aliases.get("aliases") or {}))
    return canonical_sha256({"aliases": {w: raw_aliases["aliases"][w] for w in words}, "notes": {w: notes[w] for w in words}})


def round_freeze_hashes(round: int, root=ROOT) -> dict:
    root = pathlib.Path(root)
    j = lambda rel: canonical_sha256(json.loads((root / rel).read_text(encoding="utf-8")))
    aliases = json.loads((root / DATA_REL / "search_aliases.json").read_text(encoding="utf-8"))
    return {"concept_lexicon_sha256": j(f"{DATA_REL}/concept_lexicon.json"),
            "lexicon_aliases_sha256": lexicon_aliases_sha256(aliases, round),
            "alias_candidates_sha256": j(f"{DATA_REL}/alias_candidates.json"),
            "worker_brief_sha256": files_sha256(root, (f"tests/benchmarks/round{round}-worker-brief.md",)),
            "hidden_generation_prompt_sha256": files_sha256(root, (f"tests/benchmarks/round{round}-hidden-generation-prompt.md",)),
            "hidden_reviewer_prompt_sha256": files_sha256(root, (f"tests/benchmarks/round{round}-hidden-reviewer-prompt.md",)),
            "tooling_code_sha256": tooling_code_sha256(root),
            "evaluation_code_sha256_at_T": evaluation_code_sha256(root)}
```

Remove the old `EVALUATION_CODE_FILES`/`evaluation_code_sha256` definitions. `alias_candidates_tool.py` and `concept_lexicon_check.py` do not exist yet: `tooling_code_sha256` is only called by `freeze` (after Tasks 4–5) and by the Round 2 hash test (guarded by `round < 2`); in Task 3's test, assert `tooling_code_sha256` only when every file in `TOOLING_FILES` exists (`if all((ROOT / p).exists() for p in ev.TOOLING_FILES)`), otherwise print "tooling incomplete".

- [ ] **Step 5: Run the suite, pin constants, commit**

Run: `python -m unittest discover -s tests -t .` → Expected: OK.

```bash
git add tests/benchmarks/round_freeze.json tests/benchmarks/evaluator.py tests/benchmarks/test_evaluator.py
git commit -m "benchmarks: round_freeze as list, tooling/evaluation hashes, R5/R6 schema, Round 1 invariants pinned

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `alias_candidates_tool.py` — concept tokens, verb report, method-safety, candidates, R5/R6, lexicon gate (commit H4)

**Files:**
- Create: `tests/benchmarks/alias_candidates_tool.py`
- Test: `tests/benchmarks/test_alias_candidates_tool.py`

**Interfaces:**
- Consumes: `round_seal.load_catalogs_from_cache(cache_dir, round)`, `round_seal._write_bench`, `evaluator.canonical_sha256/STOPWORDS`, `search.tokenize_unigrams/singular` (read-only import of production code, like `round_seal`).
- Produces (pure, unit-tested; `classify(bench, internal, ranking_raw, aliases_raw)` uses the independent R6 definition): `norm_tokens(text) -> tuple` (unigrams → `singular`, order kept, deduped); `FUNCTION_WORDS`; `op_vocab(op) -> frozenset` (operationId + literal path segments + tags + summary, normalized); `catalog_vocab(internal) -> frozenset`; `catalog_df(internal) -> dict`; `concept_tokens(internal, noise) -> dict token -> {"count", "sources"}`; `verb_report(internal, verb_methods) -> dict verb -> {"methods": {M: n}, "outside": [...], "review": bool}`; `allowed_methods(query, verb_methods) -> None | frozenset`; `method_safety(bench, verb_methods) -> list rows`; `expected_vocab(rec, by_key, verb_methods, noise, hints) -> frozenset`; `candidates(bench, internal, ranking_raw, aliases_raw) -> dict` (`candidates`, `excluded`); `classify(bench, verb_methods, cands) -> dict id -> sorted classes`; `lexicon_gate(lexicon_doc, bench, by_key, ranking_raw) -> (lexicon_doc, rejected_now)`; `provenance(fp, shas, inputs) -> dict`.
- CLI (every command `--cache-dir S`, `--round N` default 2): `concept-tokens --out`, `verb-report [--out]`, `method-safety --out`, `lexicon-gate --lexicon FILE` (rewrites the file), `candidates --out`, `classify` (rewrites the bench seed `failure_classes`).

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_alias_candidates_tool.py`:

```python
import copy, json, unittest
from tests.benchmarks import alias_candidates_tool as act
from tests.benchmarks.test_round_seal import CAT, A, B, C, D, E, F, G, H

WS = {"key": "jira-platform:GET:/rest/api/3/workspace", "source": "jira-platform", "method": "GET", "operation_id": "getLinkedWorkspaces",
      "summary": "Get linked workspaces", "tags": ["Workspaces"], "description": "x"}
CAT2 = CAT + [WS]
VERBS = {"get": ["GET"], "browse": ["GET"], "create": ["POST"], "delete": ["DELETE"], "list": ["GET"], "publish": ["POST"]}
RANK = {"verb_methods": VERBS, "path_noise": ["rest", "api", "agile"], "product_hints": {"jira": ["jira-platform"], "confluence": ["confluence"]}}
ALIASES = {"aliases": {"ticket": ["issue"]}, "rules": [{"when_all": ["issue", "key"], "add": ["getissue"]}], "notes": {}}


def seed(i, q, key, fc=()):
    return {"id": f"s-{i:03d}", "query": q, "expected_top1_any": [key], "forbidden_top1": [], "origin": "seed-r0",
            "failure_classes": list(fc), "ambiguous": False}


BENCH = {"seed": [seed(1, "browse pages inside this workspace", G), seed(2, "get issue by key", A),
                  seed(3, "publish a brand new document", B), seed(4, "create and delete the issue", C)],
         "regression_negative": []}
BY_KEY = {r["key"]: r for r in CAT2}


class TestTokens(unittest.TestCase):
    def test_norm_tokens_singular_and_order(self):
        self.assertEqual(act.norm_tokens("Browse the Pages workspaces files"), ("browse", "page", "workspace", "file"))

    def test_concept_tokens_from_paths_and_tags(self):
        ct = act.concept_tokens(CAT2, frozenset(RANK["path_noise"]))
        self.assertIn("issue", ct); self.assertIn("page", ct); self.assertNotIn("rest", ct)
        self.assertEqual(ct["sprint"]["sources"], ["jira-software"]); self.assertGreaterEqual(ct["issue"]["count"], 3)

    def test_verb_report_flags_methods_outside_inventory(self):
        rep = act.verb_report(CAT2, {"get": ["POST"], "create": ["POST"]})
        self.assertTrue(rep["get"]["review"]); self.assertIn("GET", rep["get"]["outside"])
        self.assertFalse(rep["create"]["review"])


class TestMethodSafety(unittest.TestCase):
    def test_allowed_methods(self):
        self.assertIsNone(act.allowed_methods("show me the ticket", VERBS))
        self.assertEqual(act.allowed_methods("get issue", VERBS), frozenset({"GET"}))
        self.assertEqual(act.allowed_methods("create and delete the issue", VERBS), frozenset())

    def test_method_safety_conflicting_verbs_is_intent_zero(self):
        rows = {r["id"]: r for r in act.method_safety(BENCH, VERBS)}
        self.assertTrue(rows["s-004"]["ok"]); self.assertEqual(rows["s-004"]["allowed"], [])
        self.assertTrue(rows["s-002"]["ok"]); self.assertTrue(rows["s-001"]["ok"])
        bad = act.method_safety({"seed": [seed(9, "get the page", B)]}, VERBS)[0]   # GET verb, POST target
        self.assertFalse(bad["ok"]); self.assertEqual(bad["expected_methods"], ["POST"])


class TestCandidates(unittest.TestCase):
    def test_expected_vocab_excludes_verbs_noise_hints_ids(self):
        v = act.expected_vocab(BENCH["seed"][1], BY_KEY, VERBS, frozenset(RANK["path_noise"]), RANK["product_hints"])
        self.assertIn("issue", v); self.assertNotIn("get", v); self.assertNotIn("rest", v); self.assertNotIn("id", v); self.assertNotIn("key", v)

    def test_candidate_relative_to_expected_vocab_not_global_catalog(self):
        doc = act.candidates(BENCH, CAT2, RANK, ALIASES)
        c = doc["candidates"]
        self.assertIn("workspace", c); self.assertEqual(c["workspace"]["catalog_df"], 1)      # in the catalog, still a candidate
        self.assertEqual(c["workspace"]["seed_ids"], ["s-001"]); self.assertIn("page", c["workspace"]["targets_by_seed"]["s-001"])
        self.assertEqual(c["workspace"]["allowed_targets"], c["workspace"]["targets_by_seed"]["s-001"])
        self.assertIn("document", c); self.assertIn("page", c["document"]["allowed_targets"])
        self.assertNotIn("inside", c); self.assertNotIn("this", c); self.assertNotIn("brand", c)      # function words
        self.assertNotIn("browse", c); self.assertNotIn("issue", c); self.assertNotIn("key", c)      # verb / expected vocab
        self.assertEqual(doc["excluded"]["browse"], "verb"); self.assertEqual(doc["excluded"]["inside"], "function_word")
        self.assertEqual(json.dumps(doc, sort_keys=True), json.dumps(act.candidates(BENCH, CAT2, RANK, ALIASES), sort_keys=True))

    def test_identifier_and_existing_alias_excluded(self):
        b = {"seed": [seed(5, "getissue for my ticket", A)], "regression_negative": []}
        doc = act.candidates(b, CAT2, RANK, ALIASES)
        self.assertEqual(doc["candidates"], {}); self.assertEqual(doc["excluded"]["getissue"], "identifier")
        self.assertEqual(doc["excluded"]["ticket"], "existing_alias")

    def test_classify_r5_r6(self):
        cls = act.classify(BENCH, CAT2, RANK, ALIASES)
        self.assertEqual(cls["s-001"], ["R6"]); self.assertEqual(cls["s-002"], [])      # key is id-like, not R6
        self.assertEqual(cls["s-004"], ["R5"])                      # conflicting verbs -> no expected method covered
        no_verb = {"seed": [seed(7, "ticket details overview", A)], "regression_negative": []}
        self.assertEqual(act.classify(no_verb, CAT2, RANK, ALIASES)["s-007"], ["R5", "R6"])   # ticket is an alias; details/overview are not

class TestLexiconGate(unittest.TestCase):
    def test_gate_keeps_compatible_and_rejects_incompatible(self):
        lex = {"lexicon": {"workspace": ["page"], "document": ["issue"], "note": ["comment"]}, "rejected": {}}
        out, rejected = act.lexicon_gate(copy.deepcopy(lex), BENCH, BY_KEY, RANK)
        self.assertIn("workspace", out["lexicon"]); self.assertNotIn("document", out["lexicon"]); self.assertIn("note", out["lexicon"])
        self.assertEqual(out["rejected"]["document"]["reason"], "seed-incompatible"); self.assertEqual(rejected, ["document"])
```

Run: `python -m unittest tests.benchmarks.test_alias_candidates_tool` → Expected: ImportError / FAIL.

- [ ] **Step 2: Implement the module (part 1: tokens, vocab, report, safety)**

```python
"""Round 2 pre-T tooling (spec §5.1/§5.2/§7.1): concept tokens, verb report, method-safety, alias candidates,
R5/R6 classification, lexicon-seed gate. Every command reads only the source snapshot S (--cache-dir).

  python tests/benchmarks/alias_candidates_tool.py concept-tokens --cache-dir S --out concept_tokens.json
  python tests/benchmarks/alias_candidates_tool.py verb-report    --cache-dir S --out verb_report.json
  python tests/benchmarks/alias_candidates_tool.py method-safety  --cache-dir S --out method_safety.json
  python tests/benchmarks/alias_candidates_tool.py lexicon-gate   --cache-dir S --lexicon tools/.../concept_lexicon.json
  python tests/benchmarks/alias_candidates_tool.py candidates     --cache-dir S --out tools/.../alias_candidates.json
  python tests/benchmarks/alias_candidates_tool.py classify       --cache-dir S
"""
import argparse, collections, json, pathlib, sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.benchmarks import round_seal as rs
from tests.benchmarks.evaluator import STOPWORDS, canonical_sha256
from tools.atlassian_docs.intelligence.search import singular, tokenize_unigrams

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "tools" / "atlassian_docs" / "intelligence" / "data"
BENCH_PATH = ROOT / "tests" / "benchmarks" / "search_queries.json"
TOOL_VERSION = "round2.1"
FUNCTION_WORDS = frozenset("my me this that these those another every which what who now today please into onto brand own "
                           "current some any all one two few several inside up".split())
ID_LIKE = frozenset({"id", "ids", "key", "keys"})


def norm_tokens(text) -> tuple:
    return tuple(dict.fromkeys(singular(t) for t in tokenize_unigrams(text)))


def path_literal_tokens(path) -> tuple:
    out = []
    for seg in (path or "").split("/"):
        if seg and not (seg.startswith("{") and seg.endswith("}")):
            out += [t for t in norm_tokens(seg) if not t.isdigit()]
    return tuple(dict.fromkeys(out))


def op_vocab(op) -> frozenset:
    path = op["key"].split(":", 2)[2]
    toks = set(norm_tokens(op.get("operation_id") or "")) | set(path_literal_tokens(path)) | set(norm_tokens(op.get("summary") or ""))
    for tag in op.get("tags") or []:
        toks |= set(norm_tokens(tag))
    return frozenset(toks)


def catalog_vocab(internal) -> frozenset:
    out = set()
    for op in internal:
        out |= op_vocab(op)
    return frozenset(out)


def catalog_df(internal) -> dict:
    df = collections.Counter()
    for op in internal:
        df.update(op_vocab(op))
    return dict(df)


def concept_tokens(internal, noise) -> dict:
    """Catalog concept tokens: literal path-segment unigrams (minus noise/digits) and tag unigrams, with counts/sources."""
    out = {}
    for op in internal:
        toks = set(path_literal_tokens(op["key"].split(":", 2)[2])) - set(noise)
        for tag in op.get("tags") or []:
            toks |= set(norm_tokens(tag))
        for t in toks:
            e = out.setdefault(t, {"count": 0, "sources": set()})
            e["count"] += 1; e["sources"].add(op["source"])
    return {t: {"count": e["count"], "sources": sorted(e["sources"])} for t, e in sorted(out.items())}


def verb_report(internal, verb_methods) -> dict:
    """Diagnostic only (spec §6): method distribution of ops whose operationId/summary contains the verb token."""
    rep = {}
    for verb, allowed in sorted(verb_methods.items()):
        methods = collections.Counter(op["method"] for op in internal
                                      if verb in norm_tokens(op.get("operation_id") or "") or verb in norm_tokens(op.get("summary") or ""))
        outside = sorted(set(methods) - set(allowed))
        rep[verb] = {"methods": dict(sorted(methods.items())), "outside": outside, "review": bool(outside)}
    return rep


def allowed_methods(query, verb_methods):
    """None when the query has no inventory verb; else the intersection (may be empty = intent 0)."""
    verbs = [t for t in tokenize_unigrams(query) if t in verb_methods]
    if not verbs:
        return None
    allowed = set(verb_methods[verbs[0]])
    for v in verbs[1:]:
        allowed &= set(verb_methods[v])
    return frozenset(allowed)


def expected_methods(rec) -> frozenset:
    return frozenset(k.split(":")[1] for k in rec.get("expected_top1_any") or [])


def method_safety(bench, verb_methods) -> list:
    """spec §5.2.2: (a) no verb or empty intersection, or (b) some expected op method is allowed."""
    rows = []
    for rec in bench["seed"]:
        allowed, exp = allowed_methods(rec["query"], verb_methods), expected_methods(rec)
        ok = allowed is None or not allowed or bool(allowed & exp)
        rows.append({"id": rec["id"], "verbs": [t for t in tokenize_unigrams(rec["query"]) if t in verb_methods],
                     "allowed": sorted(allowed) if allowed is not None else None, "expected_methods": sorted(exp), "ok": ok})
    return rows
```

- [ ] **Step 3: Implement the module (part 2: candidates, classify, gate, provenance)**

```python
def expected_vocab(rec, by_key, verb_methods, noise, hints) -> frozenset:
    """spec §7.1.2: vocabulary of the seed's expected ops minus verbs, function words, noise, id-like and product hints."""
    toks = set()
    for key in rec.get("expected_top1_any") or []:
        op = by_key.get(key)
        if op is not None:
            toks |= op_vocab(op)
    drop = set(verb_methods) | FUNCTION_WORDS | set(noise) | set(hints) | ID_LIKE | STOPWORDS
    return frozenset(t for t in toks if t not in drop and not t.isdigit())


def alias_source_words(aliases_raw) -> frozenset:
    words = set(aliases_raw.get("aliases") or {})
    for rule in aliases_raw.get("rules") or []:
        words |= set(rule.get("when_all") or [])
    return frozenset(words)


def candidates(bench, internal, ranking_raw, aliases_raw, round=2) -> dict:
    """spec §7.1: deterministic seed-derived candidate words with per-seed targets."""
    by_key = {op["key"]: op for op in internal}
    verbs, noise, hints = ranking_raw["verb_methods"], frozenset(ranking_raw["path_noise"]), ranking_raw["product_hints"]
    idents = {(op.get("operation_id") or "").lower() for op in internal}
    alias_words, df = alias_source_words(aliases_raw), catalog_df(internal)
    cands, reasons = {}, {}
    for rec in sorted(bench["seed"], key=lambda r: r["id"]):
        vocab = expected_vocab(rec, by_key, verbs, noise, hints)
        for tok in norm_tokens(rec["query"]):
            reason = ("verb" if tok in verbs else "function_word" if tok in FUNCTION_WORDS else "product_hint" if tok in hints
                      else "existing_alias" if tok in alias_words else "expected_vocab" if tok in vocab
                      else "identifier" if tok in idents else None)
            if reason:
                reasons.setdefault(tok, reason); continue
            c = cands.setdefault(tok, {"seed_ids": [], "targets_by_seed": {}, "allowed_targets": [], "catalog_df": df.get(tok, 0)})
            c["seed_ids"].append(rec["id"]); c["targets_by_seed"][rec["id"]] = sorted(vocab)
    for c in cands.values():
        c["allowed_targets"] = sorted(set().union(*c["targets_by_seed"].values()))
    excluded = {t: r for t, r in sorted(reasons.items()) if t not in cands}
    return {"round": round, "candidates": dict(sorted(cands.items())), "excluded": excluded}


def classify(bench, internal, ranking_raw, aliases_raw) -> dict:
    """spec §0.2 (independent definitions): R5 = no inventory verb, or the allowed methods cover no expected op
    (∃ semantics); R6 = some query token is in none of expected-op vocab / verbs / existing alias words /
    product hints / function words (id-like, noise and digits are ignored)."""
    by_key = {op["key"]: op for op in internal}
    verbs, noise, hints = ranking_raw["verb_methods"], frozenset(ranking_raw["path_noise"]), ranking_raw["product_hints"]
    alias_words, out = alias_source_words(aliases_raw), {}
    for rec in bench["seed"]:
        allowed, classes = allowed_methods(rec["query"], verbs), []
        if allowed is None or not (allowed & expected_methods(rec)):
            classes.append("R5")
        known = expected_vocab(rec, by_key, verbs, noise, hints) | set(verbs) | alias_words | set(hints) | FUNCTION_WORDS | STOPWORDS | ID_LIKE | noise
        if any(t not in known and not t.isdigit() for t in norm_tokens(rec["query"])):
            classes.append("R6")
        out[rec["id"]] = classes
    return out

def lexicon_gate(lexicon_doc, bench, by_key, ranking_raw):
    """spec §5.2.3: a lexicon synonym that occurs in a seed query must target that seed's expected vocabulary."""
    verbs, noise, hints = ranking_raw["verb_methods"], frozenset(ranking_raw["path_noise"]), ranking_raw["product_hints"]
    rejected_now = []
    for syn in sorted(lexicon_doc["lexicon"]):
        seeds = [r for r in bench["seed"] if syn in norm_tokens(r["query"])]
        if not seeds:
            continue
        allowed = set().union(*(expected_vocab(r, by_key, verbs, noise, hints) for r in seeds))
        if not set(lexicon_doc["lexicon"][syn]) & allowed:
            lexicon_doc["rejected"][syn] = {"reason": "seed-incompatible", "targets": lexicon_doc["lexicon"].pop(syn),
                                            "catalog_df": lexicon_doc.get("catalog_df", {}).get(syn, 0)}
            rejected_now.append(syn)
    return lexicon_doc, rejected_now


def provenance(fp, shas, inputs) -> dict:
    return {"registry_fingerprint": fp, "spec_sha256": dict(sorted(shas.items())), "inputs": dict(sorted(inputs.items())),
            "tool_version": TOOL_VERSION}
```

- [ ] **Step 4: Implement the CLI (part 3)**

```python
def _read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _write(path, obj):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _load(args):
    _, internal, fp, shas = rs.load_catalogs_from_cache(args.cache_dir, args.round)
    ranking, aliases, bench = _read(DATA / "search_ranking.json"), _read(DATA / "search_aliases.json"), _read(BENCH_PATH)
    inputs = {"ranking": canonical_sha256(ranking), "aliases": canonical_sha256(aliases), "bench": canonical_sha256(bench),
              "verb_inventory": canonical_sha256(ranking["verb_methods"])}
    return internal, fp, shas, ranking, aliases, bench, inputs


def cmd_concept_tokens(args):
    internal, fp, shas, ranking, _, _, inputs = _load(args)
    _write(args.out, {"round": args.round, "generated_from": provenance(fp, shas, {"ranking": inputs["ranking"]}),
                      "tokens": concept_tokens(internal, ranking["path_noise"])})
    return 0


def cmd_verb_report(args):
    internal, fp, shas, ranking, _, _, inputs = _load(args)
    rep = verb_report(internal, ranking["verb_methods"])
    for verb, row in rep.items():
        if row["review"]:
            print(f"REVIEW {verb}: methods={row['methods']} outside={row['outside']}")
    if args.out:
        _write(args.out, {"round": args.round, "generated_from": provenance(fp, shas, inputs), "report": rep})
    return 0


def cmd_method_safety(args):
    internal, fp, shas, ranking, _, bench, inputs = _load(args)
    rows = method_safety(bench, ranking["verb_methods"])
    bad = [r for r in rows if not r["ok"]]
    for r in bad:
        print(f"VIOLATION {r['id']}: allowed={r['allowed']} expected={r['expected_methods']}")
    _write(args.out, {"round": args.round, "generated_from": provenance(fp, shas, inputs), "rows": rows, "violations": len(bad)})
    return 1 if bad else 0


def cmd_lexicon_gate(args):
    internal, _, _, ranking, _, bench, _ = _load(args)
    doc = _read(args.lexicon)
    doc, rejected = lexicon_gate(doc, bench, {op["key"]: op for op in internal}, ranking)
    doc.setdefault("generated_from", {}).setdefault("inputs", {})["bench"] = canonical_sha256(bench)
    _write(args.lexicon, doc)
    print(f"gate rejected: {rejected}")
    return 0


def cmd_candidates(args):
    internal, fp, shas, ranking, aliases, bench, inputs = _load(args)
    doc = candidates(bench, internal, ranking, aliases, args.round)
    doc["generated_from"] = provenance(fp, shas, inputs)
    _write(args.out, doc)
    print(f"candidates: {len(doc['candidates'])}, excluded: {len(doc['excluded'])}")
    return 0


def cmd_classify(args):
    internal, _, _, ranking, aliases, bench, _ = _load(args)
    cls = classify(bench, internal, ranking, aliases)
    for rec in bench["seed"]:
        keep = [c for c in rec["failure_classes"] if c not in ("R5", "R6")]
        rec["failure_classes"] = keep + cls[rec["id"]]
    rs._write_bench(BENCH_PATH, bench)
    print(json.dumps({k: v for k, v in cls.items() if v}, sort_keys=True))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, extra in (("concept-tokens", cmd_concept_tokens, ("out",)), ("verb-report", cmd_verb_report, ("out?",)),
                            ("method-safety", cmd_method_safety, ("out",)), ("lexicon-gate", cmd_lexicon_gate, ("lexicon",)),
                            ("candidates", cmd_candidates, ("out",)), ("classify", cmd_classify, ())):
        p = sub.add_parser(name); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
        for e in extra:
            p.add_argument(f"--{e.rstrip('?')}", required=not e.endswith("?"))
        p.set_defaults(fn=fn)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and the suite, commit**

Run: `python -m unittest tests.benchmarks.test_alias_candidates_tool -v` → Expected: PASS. Then the full suite → OK.

```bash
git add tests/benchmarks/alias_candidates_tool.py tests/benchmarks/test_alias_candidates_tool.py
git commit -m "benchmarks: alias_candidates_tool (concept tokens, verb report, method-safety, candidates, R5/R6, lexicon gate)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `concept_lexicon_check.py` — normalize, validate, review, cap, merge (commit H5)

**Files:**
- Create: `tests/benchmarks/concept_lexicon_check.py`
- Test: `tests/benchmarks/test_concept_lexicon_check.py`

**Interfaces:**
- Consumes: `alias_candidates_tool.{norm_tokens, catalog_vocab, catalog_df, concept_tokens, alias_source_words, FUNCTION_WORDS, DATA, provenance, _write}`, `round_seal.load_catalogs_from_cache`, `evaluator.{canonical_sha256, STOPWORDS}`.
- Produces (pure): `normalize_raw(raw) -> dict syn -> sorted targets`; `structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys) -> (kept, rejected)` with reasons `shape`, `function_word`, `verb`, `product_hint`, `in_catalog`, `alias_conflict`, `multi_target`, `target_not_concept`; `prepare_review(raw, ...) -> (kept, rejected)` = normalize + structural (NO cap); `validate_review(review, keys) -> list[str]` (object, exactly `keys`, every value bool); `apply_review(lex, review) -> (kept, rejected)` (reason `semantic-reject`; `review` must have passed `validate_review`); `cap_per_concept(lex, limit=5) -> (kept, rejected)` (reason `concept-cap`, lexicographic first 5); `finalize(kept, rejected, review) -> (lexicon, rejected)` = apply_review → cap; `build(raw, review, ...)` = prepare_review → finalize; `merge(aliases_raw, lexicon, round) -> (new_raw, skipped)`.
- CLI: `prepare --cache-dir S --raw RAW.json --out lexicon_structural.json` (writes `{"lexicon": kept, "rejected": ...}` — the reviewer input); `finalize --cache-dir S --raw RAW.json --structural lexicon_structural.json --review REVIEW.json --generation-input FILLED_PROMPT.txt --review-input FILLED_REVIEW.txt --template tests/benchmarks/round2-lexicon-generation-prompt.md --out tools/.../concept_lexicon.json` (refuses when `validate_review` fails); `merge --lexicon FILE --aliases tools/.../search_aliases.json --round 2`.
- `concept_lexicon.json` shape: `{"round", "generated_from", "prompt_template_sha256", "generation_input_sha256", "raw_sha256", "review_input_sha256", "review_output_sha256", "lexicon", "rejected", "catalog_df"}` (the two `*_input_sha256` are hashes of the exact bytes sent to the model).

- [ ] **Step 1: Write the failing tests**

```python
import json, unittest
from tests.benchmarks import concept_lexicon_check as clc

CONCEPTS = {"issue", "comment", "page", "sprint", "attachment", "version", "space"}
CATALOG = CONCEPTS | {"file", "get", "workspace", "linked"}
VERBS, HINTS, ALIAS_KEYS = {"get", "create"}, {"jira", "confluence"}, {"ticket"}
ARGS = (CONCEPTS, CATALOG, VERBS, HINTS, ALIAS_KEYS)


class TestChecks(unittest.TestCase):
    def test_normalize_lowercases_singularizes_and_merges(self):
        raw = {"Tickets": ["issue"], "ticket": ["issues"], "notes": ["comment"]}
        self.assertEqual(clc.normalize_raw(raw), {"note": ["comment"], "ticket": ["issue"]})

    def test_plural_synonym_rejected_after_normalization(self):
        kept, rej = clc.prepare_review({"files": ["attachments"], "File": ["attachment"]}, *ARGS)
        self.assertEqual(kept, {}); self.assertEqual({k: v["reason"] for k, v in rej.items()}, {"file": "in_catalog"})

    def test_structural_reasons(self):
        lex = {"note": ["comment"], "my": ["issue"], "get": ["issue"], "jira": ["issue"], "doc": ["page", "space"],
               "card": ["board"], "ticket": ["issue"], "e-mail": ["comment"]}
        kept, rej = clc.structural_check(lex, *ARGS)
        self.assertEqual(kept, {"note": ["comment"]})
        self.assertEqual({k: v["reason"] for k, v in rej.items()},
                         {"my": "function_word", "get": "verb", "jira": "product_hint", "doc": "multi_target",
                          "card": "target_not_concept", "ticket": "alias_conflict", "e-mail": "shape"})

    def test_prepare_review_does_not_cap(self):
        raw = {f"w{i}": ["issue"] for i in range(8)}
        kept, _ = clc.prepare_review(raw, *ARGS)
        self.assertEqual(len(kept), 8)

    def test_validate_review_exact_keys_and_bools(self):
        keys = ["w0", "w1"]
        self.assertEqual(clc.validate_review({"w0": True, "w1": False}, keys), [])
        self.assertTrue(clc.validate_review({"w0": True}, keys))                       # missing
        self.assertTrue(clc.validate_review({"w0": True, "w1": False, "w9": True}, keys))  # extra
        self.assertTrue(clc.validate_review({"w0": True, "w1": "no"}, keys))           # non-bool
        self.assertTrue(clc.validate_review([True, False], keys))                      # non-object

    def test_review_then_cap_recovers_sixth_synonym(self):
        kept = {f"w{i}": ["issue"] for i in range(7)}
        review = {f"w{i}": i not in (0, 1, 2) for i in range(7)}
        lexicon, rej = clc.finalize(kept, {}, review)
        self.assertEqual(sorted(lexicon), ["w3", "w4", "w5", "w6"])                   # 4 survive the review, all kept (<= 5)
        self.assertEqual(rej["w0"]["reason"], "semantic-reject")
        kept8 = {f"w{i}": ["issue"] for i in range(8)}
        lexicon8, rej8 = clc.finalize(kept8, {}, {k: True for k in kept8})
        self.assertEqual(sorted(lexicon8), ["w0", "w1", "w2", "w3", "w4"]); self.assertEqual(rej8["w7"]["reason"], "concept-cap")
        with self.assertRaises(ValueError):
            clc.finalize(kept, {}, {"w0": True})                                       # invalid review refused

    def test_build_is_deterministic_and_ordered(self):
        raw = {"Notes": ["comment"], "files": ["attachment"], "release": ["version"], "cards": ["board"]}
        review = {"note": True, "release": True}
        a = clc.build(raw, review, *ARGS, df={"file": 3}); b = clc.build(raw, review, *ARGS, df={"file": 3})
        self.assertEqual(a, b); self.assertEqual(a[0], {"note": ["comment"], "release": ["version"]})
        self.assertEqual(a[1]["file"]["catalog_df"], 3); self.assertEqual(a[1]["card"]["reason"], "target_not_concept")

    def test_merge_adds_lexicon_notes_and_skips_conflicts(self):
        aliases = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"ticket": ["issue"]}, "rules": [],
                   "notes": {"ticket": {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "x"}}}
        out, skipped = clc.merge(aliases, {"note": ["comment"], "ticket": ["issue"]}, 2)
        self.assertEqual(out["aliases"], {"ticket": ["issue"], "note": ["comment"]}); self.assertEqual(skipped, ["ticket"])
        self.assertEqual(out["notes"]["note"], {"origin": "lexicon-r2", "seed_query_id": None, "failure_classes": [], "evidence": "concept lexicon r2"})
        self.assertEqual(aliases["aliases"], {"ticket": ["issue"]})      # input untouched
```

Run: `python -m unittest tests.benchmarks.test_concept_lexicon_check` → Expected: ImportError.

- [ ] **Step 2: Implement (pure part)**

```python
"""Round 2 concept lexicon (spec §7.0): normalize a stateless generator's output, validate it against the catalog,
apply the stateless semantic review (validated: exact keys, booleans), cap per concept AFTER the review, and merge
into search_aliases.json as origin lexicon-rN.

  python tests/benchmarks/concept_lexicon_check.py prepare  --cache-dir S --raw RAW.json --out lexicon_structural.json
  python tests/benchmarks/concept_lexicon_check.py finalize --cache-dir S --raw RAW.json --structural lexicon_structural.json
         --review REVIEW.json --generation-input GEN_INPUT.txt --review-input REV_INPUT.txt
         --template tests/benchmarks/round2-lexicon-generation-prompt.md --out tools/.../concept_lexicon.json
  python tests/benchmarks/concept_lexicon_check.py merge --lexicon LEX.json --aliases tools/.../search_aliases.json --round 2
"""
import argparse, copy, hashlib, json, pathlib, re, sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.benchmarks import alias_candidates_tool as act
from tests.benchmarks import round_seal as rs
from tests.benchmarks.evaluator import STOPWORDS, canonical_sha256

MAX_PER_CONCEPT = 5
_SHAPE = re.compile(r"^[a-z]+$")


def _rej(reason, targets, df=0):
    return {"reason": reason, "targets": list(targets), "catalog_df": df}


def normalize_raw(raw) -> dict:
    out = {}
    for syn, targets in (raw or {}).items():
        toks = act.norm_tokens(str(syn))
        key = " ".join(toks) if toks else str(syn).lower()
        vals = [t for target in (targets if isinstance(targets, list) else [targets]) for t in act.norm_tokens(str(target))]
        out.setdefault(key, set()).update(vals)
    return {k: sorted(v) for k, v in sorted(out.items())}


def structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys):
    kept, rej = {}, {}
    for syn, targets in lex.items():
        reason = ("shape" if not _SHAPE.fullmatch(syn) or syn in STOPWORDS else "function_word" if syn in act.FUNCTION_WORDS
                  else "verb" if syn in verbs else "product_hint" if syn in hints else "in_catalog" if syn in catalog_set
                  else "alias_conflict" if syn in alias_keys else "multi_target" if len(targets) != 1
                  else "target_not_concept" if targets[0] not in concept_set else None)
        if reason:
            rej[syn] = _rej(reason, targets)
        else:
            kept[syn] = list(targets)
    return kept, rej


def prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys):
    """Order (spec §7.0): normalize -> structural. No cap here: the semantic review sees every surviving synonym."""
    return structural_check(normalize_raw(raw), concept_set, catalog_set, verbs, hints, alias_keys)


def validate_review(review, keys) -> list:
    if not isinstance(review, dict):
        return ["review must be a JSON object keyed by synonym"]
    wanted = set(keys)
    out = [f"missing key {k!r}" for k in keys if k not in review] + [f"extra key {k!r}" for k in review if k not in wanted]
    out += [f"{k!r}: value must be true/false" for k, v in review.items() if k in wanted and not isinstance(v, bool)]
    return out


def apply_review(lex, review):
    problems = validate_review(review, list(lex))
    if problems:
        raise ValueError("invalid semantic review: " + "; ".join(problems))
    kept, rej = {}, {}
    for syn, targets in lex.items():
        if review[syn]:
            kept[syn] = list(targets)
        else:
            rej[syn] = _rej("semantic-reject", targets)
    return kept, rej


def cap_per_concept(lex, limit=MAX_PER_CONCEPT):
    by_concept, kept, rej = {}, {}, {}
    for syn, targets in sorted(lex.items()):
        by_concept.setdefault(targets[0], []).append(syn)
    for concept, syns in by_concept.items():
        for i, syn in enumerate(sorted(syns)):
            if i < limit:
                kept[syn] = lex[syn]
            else:
                rej[syn] = _rej("concept-cap", lex[syn])
    return dict(sorted(kept.items())), rej


def finalize(kept, rejected, review):
    """review (validated) -> per-concept cap; rejected entries accumulate."""
    rejected = dict(rejected)
    kept, r2 = apply_review(kept, review); rejected.update(r2)
    kept, r3 = cap_per_concept(kept); rejected.update(r3)
    return kept, dict(sorted(rejected.items()))


def build(raw, review, concept_set, catalog_set, verbs, hints, alias_keys, df=None):
    kept, rejected = prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys)
    lexicon, rejected = finalize(kept, rejected, review)
    for syn, e in rejected.items():
        e["catalog_df"] = (df or {}).get(syn, 0)
    return lexicon, rejected


def merge(aliases_raw, lexicon, round):
    out, skipped = copy.deepcopy(aliases_raw), []
    for syn, targets in sorted(lexicon.items()):
        if syn in out["aliases"]:
            skipped.append(syn); continue
        out["aliases"][syn] = list(targets)
        out["notes"][syn] = {"origin": f"lexicon-r{round}", "seed_query_id": None, "failure_classes": [],
                             "evidence": f"concept lexicon r{round}"}
    return out, skipped
```

- [ ] **Step 3: Implement (CLI)**

```python
def _read(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _context(args):
    _, internal, fp, shas = rs.load_catalogs_from_cache(args.cache_dir, args.round)
    ranking, aliases = _read(act.DATA / "search_ranking.json"), _read(act.DATA / "search_aliases.json")
    return internal, fp, shas, ranking, aliases, (set(act.concept_tokens(internal, ranking["path_noise"])), act.catalog_vocab(internal),
                                                  set(ranking["verb_methods"]), set(ranking["product_hints"]), act.alias_source_words(aliases))


def cmd_prepare(args):
    _, _, _, _, _, ctx = _context(args)
    kept, rejected = prepare_review(_read(args.raw), *ctx)
    act._write(args.out, {"round": args.round, "lexicon": kept, "rejected": rejected})
    print(f"structural: {len(kept)} kept, {len(rejected)} rejected")
    return 0


def cmd_finalize(args):
    internal, fp, shas, ranking, aliases, ctx = _context(args)
    raw, structural, review = _read(args.raw), _read(args.structural), _read(args.review)
    kept, rejected = prepare_review(raw, *ctx)
    if kept != structural["lexicon"]:
        print("REFUSED: structural file does not match prepare_review(raw) on the current catalog"); return 1
    problems = validate_review(review, list(kept))
    if problems:
        print("\n".join(f"INVALID REVIEW {m}" for m in problems)); return 1
    lexicon, rejected = finalize(kept, rejected, review)
    df = act.catalog_df(internal)
    for syn, e in rejected.items():
        e["catalog_df"] = df.get(syn, 0)
    doc = {"round": args.round, "prompt_template_sha256": _sha(args.template), "generation_input_sha256": _sha(args.generation_input),
           "raw_sha256": canonical_sha256(raw), "review_input_sha256": _sha(args.review_input), "review_output_sha256": canonical_sha256(review),
           "generated_from": act.provenance(fp, shas, {"verb_inventory": canonical_sha256(ranking["verb_methods"]),
                                                        "aliases": canonical_sha256(aliases), "raw_generation": canonical_sha256(raw),
                                                        "semantic_review": canonical_sha256(review)}),
           "lexicon": lexicon, "rejected": rejected, "catalog_df": {s: df.get(s, 0) for s in lexicon}}
    act._write(args.out, doc)
    print(f"lexicon: {len(lexicon)} kept, {len(rejected)} rejected")
    return 0


def cmd_merge(args):
    aliases, doc = _read(args.aliases), _read(args.lexicon)
    out, skipped = merge(aliases, doc["lexicon"], args.round)
    pathlib.Path(args.aliases).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from tools.atlassian_docs.intelligence import policy
    policy.load_aliases(pathlib.Path(args.aliases))          # must still load
    print(f"merged {len(out['aliases']) - len(aliases['aliases'])} aliases; skipped {skipped}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
    p.add_argument("--raw", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("finalize"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
    for name in ("raw", "structural", "review", "generation-input", "review-input", "template", "out"):
        p.add_argument(f"--{name}", required=True)
    p.set_defaults(fn=cmd_finalize)
    p = sub.add_parser("merge"); p.add_argument("--lexicon", required=True); p.add_argument("--aliases", required=True)
    p.add_argument("--round", type=int, default=2); p.set_defaults(fn=cmd_merge)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and the suite, commit**

```bash
python -m unittest tests.benchmarks.test_concept_lexicon_check -v && python -m unittest discover -s tests -t .
git add tests/benchmarks/concept_lexicon_check.py tests/benchmarks/test_concept_lexicon_check.py
git commit -m "benchmarks: concept_lexicon_check (prepare/finalize: review before cap, validated review, merge)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: One-way tuning pipeline, deterministic alias proposer, replay verifier, two-stage adoption (commit H6)

**Files:**
- Modify (rewrite): `tests/tune_search_ranking.py`
- Modify: `tests/test_tune_search_ranking.py`
- Modify: `tests/benchmarks/test_evaluator.py` (round-2 alias/log integrity tests, guarded by artifact existence)

**Interfaces:**
- Keeps: `grid_points`, `l1_index_distance`, `select_candidate`, `plan_effects`, `dirty_paths`, `ranking_with`, `evaluate_point`, `top5`, `write_constants`, `build_state`, `SEED_TOTAL`, `REGRESSION_TOTAL`, `CONSTANT_KEYS`.
- Produces: `ROUND = ev.current_round()["round"]`; `LOG_PATH = tests/benchmarks/search-tuning-round{ROUND}.jsonl`; `CANDIDATES_PATH`; `baseline_mismatch(aliases_raw, ranking_raw, cands_doc) -> list[str]`; `baseline_sha256(...)`; `result_sha256(final_constants, alias_patch)`; `round2_note(word, sid, target, kind)`; `alias_patch(base_raw, working_raw)`; `strip_round_entries(raw, round) -> raw` (removes `round{N}` aliases/rules/notes = reconstructs the B state); `propose_aliases(eval_fn, bench, base_raw, cands, budget=15) -> (working_raw, patch)`; `validate_alias_change(before_raw, after_raw, cands, queries, budget=15) -> list[str]` (`queries`: id → query; a rule's context token must be a unigram of that seed's query, a target must be in `targets_by_seed[word][seed]`); `verify_replay(eval_fn, bench, base_raw, cands, constants, expected_result_sha256) -> list[str]` (re-runs the proposer, compares `result_sha256`); `EVENTS = ("baseline_checked", "constants_selected", "aliases_proposed", "final_check")`.
- CLI: `python tests/tune_search_ranking.py --cache-dir S [--dry-run] [--note TEXT]` (pipeline; exit 0 = perfect, pending adoption; 1 = tuning_failed; 2 = setup/baseline/replay error); `--adopt RUN_ID` (marks the pending run adopted after the caller ran the full suite; refuses if the policy files no longer reproduce the run's `result_sha256`); `--reject RUN_ID --reason R` (pending → rejected: restores the B policy files via `git checkout --`, verifies the baseline, records `reject_reason`; a rejected run is a **round abort**, not F); `--verify --cache-dir S` (replay check against the adopted run; exit 0/1).
- Log line keys: `run_id`, `run_at`, `git_commit`, `round`, `registry_fingerprint`, `baseline_sha256`, `events`, `constants_selected`, `grid_size`, `passing_combos`, `aliases_proposed` (`aliases`, `rules`, `notes`, `resolved_by_prior_change`, `unresolved`, `trials`), `seed`, `regression_negative`, `tuning_failed`, `status` (`pending` | `adopted` | `failed` | `rejected`; `rejected` lines also carry `reject_reason`), `adopted` (bool), `result_sha256`, `run_log_sha256`, `dirty`, `note`, `ranking_structure_sha256`, `baseline`.

- [ ] **Step 1: Write the failing tests**

Keep `TestSelector` and `TestEffects` (use `tune.LOG_REL` in the porcelain sample). Add `import json` and:

```python
CANDS = {"workspace": {"seed_ids": ["s-001"], "targets_by_seed": {"s-001": ["page", "space"]}, "allowed_targets": ["page", "space"], "catalog_df": 7},
         "feedback": {"seed_ids": ["s-002", "s-003"], "targets_by_seed": {"s-002": ["comment"], "s-003": ["comment", "issue"]},
                      "allowed_targets": ["comment", "issue"], "catalog_df": 0}}
BASE_RAW = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"ticket": ["issue"]}, "rules": [],
            "notes": {"ticket": {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "x"}}}
BENCH2 = {"seed": [{"id": "s-001", "query": "browse pages inside this workspace"}, {"id": "s-002", "query": "leave feedback on this ticket"},
                   {"id": "s-003", "query": "read feedback on the issue"}], "regression_negative": [{"id": "rn-001", "query": "x"}]}
QUERIES = {r["id"]: r["query"] for r in BENCH2["seed"]}


def fake_eval(rules):
    """rules: (word, target) -> seeds fixed; ("rule", sorted when_all, target) -> seeds fixed; ("BREAK", word, target) -> regression breaks."""
    def fn(raw):
        failed, reg = {"s-001", "s-002", "s-003"}, set()
        for word, targets in raw["aliases"].items():
            for sid in rules.get((word, targets[0]), ()):
                failed.discard(sid)
            if ("BREAK", word, targets[0]) in rules:
                reg.add("rn-001")
        for r in raw["rules"]:
            for sid in rules.get(("rule", tuple(sorted(r["when_all"])), r["add"][0]), ()):
                failed.discard(sid)
        return frozenset(failed), frozenset(reg)
    return fn


class TestProposer(unittest.TestCase):
    def test_direct_alias_in_order_and_working_state(self):
        fn = fake_eval({("workspace", "space"): ["s-001"], ("feedback", "comment"): ["s-002", "s-003"]})
        working, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(patch["aliases"], {"workspace": ["space"], "feedback": ["comment"]})   # page tried first, fails; space adopted
        self.assertEqual(patch["resolved_by_prior_change"], ["s-003"]); self.assertEqual(patch["unresolved"], [])
        self.assertEqual(patch["notes"]["workspace"]["candidate_word"], "workspace"); self.assertEqual(patch["notes"]["workspace"]["seed_query_id"], "s-001")
        self.assertEqual(working["aliases"]["ticket"], ["issue"]); self.assertEqual(BASE_RAW["aliases"], {"ticket": ["issue"]})
        self.assertEqual(tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)[1], patch)                 # deterministic

    def test_proposer_rejects_change_that_breaks_regression(self):
        fn = fake_eval({("workspace", "page"): ["s-001"], ("BREAK", "workspace", "page"): True,
                        ("rule", ("browse", "workspace"), "page"): ["s-001"]})
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(patch["aliases"], {}); self.assertEqual(patch["rules"], [{"when_all": ["workspace", "browse"], "add": ["page"]}])
        self.assertIn("rule:0", patch["notes"]); self.assertEqual(patch["unresolved"], ["s-002", "s-003"])

    def test_budget_checked_after_prior_change_reevaluation(self):
        fn = fake_eval({("workspace", "page"): ["s-001"], ("feedback", "comment"): ["s-002", "s-003"]})
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, budget=2)
        self.assertEqual(patch["resolved_by_prior_change"], ["s-003"]); self.assertEqual(patch["unresolved"], [])
        _, patch1 = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, budget=1)
        self.assertEqual(patch1["aliases"], {"workspace": ["page"]}); self.assertEqual(patch1["unresolved"], ["s-002", "s-003"])

    def test_per_seed_one_and_used_word_skips_direct(self):
        fn = fake_eval({("workspace", "page"): ["s-001"], ("feedback", "comment"): ["s-002"], ("feedback", "issue"): ["s-003"]})
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(patch["aliases"], {"workspace": ["page"], "feedback": ["comment"]}); self.assertEqual(patch["unresolved"], ["s-003"])


class TestValidator(unittest.TestCase):
    def after(self, **aliases):
        raw = json.loads(json.dumps(BASE_RAW))
        for w, (t, sid) in aliases.items():
            raw["aliases"][w] = [t]; raw["notes"][w] = tune.round2_note(w, sid, t, "alias")
        return raw

    def v(self, after, **kw):
        return tune.validate_alias_change(BASE_RAW, after, CANDS, QUERIES, **kw)

    def test_accepts_proposer_shape(self):
        self.assertEqual(self.v(self.after(workspace=("page", "s-001"))), [])
        rule = json.loads(json.dumps(BASE_RAW)); rule["rules"] = [{"when_all": ["workspace", "browse"], "add": ["page"]}]
        rule["notes"]["rule:0"] = tune.round2_note("workspace", "s-001", "page", "rule")
        self.assertEqual(self.v(rule), [])

    def test_rejects_bad_shapes(self):
        two = self.after(workspace=("page", "s-001")); two["aliases"]["workspace"] = ["page", "space"]
        self.assertTrue(any("exactly 1" in m for m in self.v(two)))
        self.assertTrue(any("candidate" in m for m in self.v(self.after(release=("version", "s-001")))))
        self.assertTrue(any("target" in m for m in self.v(self.after(workspace=("issue", "s-001")))))
        self.assertTrue(any("target" in m for m in self.v(self.after(feedback=("issue", "s-002")))))      # allowed overall, not for s-002
        self.assertTrue(any("seed" in m for m in self.v(self.after(workspace=("page", "s-002")))))
        twice = self.after(workspace=("page", "s-001")); twice["aliases"]["feedback"] = ["comment"]
        twice["notes"]["feedback"] = tune.round2_note("feedback", "s-001", "comment", "alias")
        self.assertTrue(any("per seed" in m for m in self.v(twice)))
        self.assertTrue(any("budget" in m for m in self.v(self.after(workspace=("page", "s-001")), budget=0)))
        damped = self.after(workspace=("page", "s-001")); damped["alias_damping"] = 0.9
        self.assertTrue(any("alias_damping" in m for m in self.v(damped)))
        removed = self.after(); del removed["aliases"]["ticket"]; del removed["notes"]["ticket"]
        self.assertTrue(any("removed" in m for m in self.v(removed)))
        rule = json.loads(json.dumps(BASE_RAW)); rule["rules"] = [{"when_all": ["workspace", "browse", "page"], "add": ["page"]}]
        rule["notes"]["rule:0"] = tune.round2_note("workspace", "s-001", "page", "rule")
        self.assertTrue(any("context" in m for m in self.v(rule)))
        rule2 = json.loads(json.dumps(BASE_RAW)); rule2["rules"] = [{"when_all": ["workspace", "sprint"], "add": ["page"]}]
        rule2["notes"]["rule:0"] = tune.round2_note("workspace", "s-001", "page", "rule")
        self.assertTrue(any("context" in m for m in self.v(rule2)))                                   # sprint not in the query


class TestReplayAndHashes(unittest.TestCase):
    def test_strip_round_entries_reconstructs_base(self):
        fn = fake_eval({("workspace", "page"): ["s-001"]})
        working, _ = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(tune.strip_round_entries(working, tune.ROUND), BASE_RAW)

    def test_verify_replay_detects_manual_edit(self):
        fn = fake_eval({("workspace", "page"): ["s-001"]})
        working, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        c = {"method_match_bonus": 2.0}
        self.assertEqual(tune.verify_replay(fn, BENCH2, BASE_RAW, CANDS, c, tune.result_sha256(c, patch)), [])
        edited = json.loads(json.dumps(patch)); edited["aliases"]["workspace"] = ["space"]
        self.assertTrue(tune.verify_replay(fn, BENCH2, BASE_RAW, CANDS, c, tune.result_sha256(c, edited)))

    def test_result_sha_and_baseline_mismatch(self):
        c = {"method_match_bonus": 2.0}; p = {"aliases": {"a": ["b"]}, "rules": [], "notes": {}}
        self.assertEqual(tune.result_sha256(c, p), tune.result_sha256(dict(c), json.loads(json.dumps(p))))
        cands = {"generated_from": {"inputs": {"aliases": policy.canonical_sha256(BASE_RAW), "ranking": "r" * 64}}}
        self.assertEqual(tune.baseline_mismatch(BASE_RAW, {"x": 1}, cands), ["ranking"])
        self.assertEqual(tune.baseline_mismatch({**BASE_RAW, "aliases": {}}, {"x": 1}, cands), ["aliases", "ranking"])

    def test_pipeline_calls_selector_once_then_proposer_once(self):
        from unittest import mock
        calls = []
        with mock.patch.object(tune, "select_candidate", side_effect=lambda *a, **k: calls.append("select") or dict(BASE)), \
             mock.patch.object(tune, "propose_aliases", side_effect=lambda *a, **k: calls.append("propose") or (json.loads(json.dumps(BASE_RAW)), {"aliases": {}, "rules": {}, "notes": {}, "resolved_by_prior_change": [], "unresolved": [], "trials": 0})):
            tune.run_pipeline(lambda point, raw: ({"passed": S, "failed": []}, {"passed": R, "failed": []}), tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE)
        self.assertEqual(calls, ["select", "propose"])
```

Run: `python -m unittest tests.test_tune_search_ranking` → Expected: AttributeError.

- [ ] **Step 2: Rewrite the header (constants) of `tests/tune_search_ranking.py`**

Keep the pure helpers verbatim (`grid_points`, `l1_index_distance`, `select_candidate`, `plan_effects`, `dirty_paths`, `ranking_with`, `evaluate_point`, `top5`, `write_constants`, `_git`, `build_state`); delete `head_alias_policy`, `_alias_change`, the `--alias-change` option.

```python
"""One-way, deterministic Round-N tuning (Round 2 spec §5.5/§7.2):

    python tests/tune_search_ranking.py --cache-dir S [--dry-run] [--note TEXT]     # pipeline, exit 0 pending / 1 failed / 2 error
    python tests/tune_search_ranking.py --adopt RUN_ID                               # after the full suite passed
    python tests/tune_search_ranking.py --verify --cache-dir S                       # replay the adopted run

tune_round(b_aliases, b_ranking, snapshot, frozen_candidates, seed, regression) -> (final_constants, alias_patch, log):
  0. baseline_checked: working tree == B baseline (alias/ranking canonical hashes == alias_candidates.generated_from.inputs)
     and verify_freeze(S) ok; otherwise exit 2 - restore B first (git checkout <B> -- <files>).
  1. constants_selected: select_candidate over the whole grid, evaluated with the B aliases (exactly once).
  2. aliases_proposed: propose_aliases at those constants (exactly once; frozen candidates only, 1 target each).
  3. final_check: seed+regression perfect -> policy files written, log status "pending" (adoption needs --adopt after the
     canonical full test suite passed); else status "failed" (tuning_failed), nothing written but the log.
No constant reselection after aliases, no second proposal. --dry-run writes nothing and prints the would-be log line.
"""
import argparse, copy, dataclasses, datetime, itertools, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid
from types import MappingProxyType
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.benchmarks import evaluator as ev  # noqa: E402
from tests.benchmarks import round_seal as rs  # noqa: E402
from tests.benchmarks.evaluator import evaluate  # noqa: E402
from tools.atlassian_docs import storage, sync  # noqa: E402
from tools.atlassian_docs.intelligence import RegistryManager, policy, search_operations  # noqa: E402

ROUND = ev.current_round()["round"]
BENCH_PATH = ROOT / "tests" / "benchmarks" / "search_queries.json"
LOG_REL = f"tests/benchmarks/search-tuning-round{ROUND}.jsonl"
LOG_PATH = ROOT / LOG_REL
RANKING_PATH = policy.DATA_DIR / "search_ranking.json"
ALIASES_PATH = policy.DATA_DIR / "search_aliases.json"
CANDIDATES_PATH = policy.DATA_DIR / "alias_candidates.json"
CONSTANT_KEYS = policy.CONSTANT_KEYS
MAGNITUDE_KEYS = tuple(k for k in CONSTANT_KEYS if k != "path_unmatched_cap")
_BENCH = json.loads(BENCH_PATH.read_text(encoding="utf-8"))
SEED_TOTAL, REGRESSION_TOTAL = len(_BENCH["seed"]), len(_BENCH["regression_negative"])
SOURCES = ("jira-platform", "jira-software", "confluence")
BUDGET = 15
EVENTS = ("baseline_checked", "constants_selected", "aliases_proposed", "final_check")
```

- [ ] **Step 3: Proposer, validator, replay, hashes**

```python
def _norm_tokens(text):
    from tests.benchmarks.alias_candidates_tool import norm_tokens
    return norm_tokens(text)


def round2_note(word, sid, target, kind) -> dict:
    return {"origin": f"round{ROUND}", "seed_query_id": sid, "candidate_word": word, "failure_classes": ["R6"],
            "evidence": f"{kind} {word} -> {target} for {sid} (frozen candidate, deterministic proposer)"}


def alias_patch(base_raw, working_raw) -> dict:
    return {"aliases": {w: v for w, v in working_raw["aliases"].items() if w not in base_raw["aliases"]},
            "rules": working_raw["rules"][len(base_raw["rules"]):],
            "notes": {k: n for k, n in working_raw["notes"].items() if k not in base_raw["notes"]}}


def strip_round_entries(raw, round) -> dict:
    """Reconstruct the B state: drop every alias/rule whose note has origin round{N} (rules are a suffix)."""
    origin, out = f"round{round}", copy.deepcopy(raw)
    for key, n in list(out["notes"].items()):
        if n.get("origin") == origin:
            del out["notes"][key]
            if not key.startswith("rule:"):
                out["aliases"].pop(key, None)
    keep = [i for i in range(len(out["rules"])) if raw["notes"].get(f"rule:{i}", {}).get("origin") != origin]
    out["rules"] = [out["rules"][i] for i in keep]
    return out


def propose_aliases(eval_fn, bench, base_raw, cands, budget=BUDGET):
    """spec §7.2: seeds in id order; each seed is re-evaluated against the working state first (resolved_by_prior_change),
    then the budget is checked; candidate words (sorted) x that seed's targets (sorted); direct alias first, then
    one-context rules; accept the first trial that fixes the seed without breaking any passing record."""
    working = copy.deepcopy(base_raw)
    seed_fail, _ = eval_fn(working)
    patch = {"resolved_by_prior_change": [], "unresolved": [], "trials": 0}
    accepted_n, by_id = 0, {r["id"]: r for r in bench["seed"]}

    def ok(trial, sid, cur_fail, cur_reg):
        patch["trials"] += 1
        f, r = eval_fn(trial)
        return sid not in f and f <= (cur_fail - {sid}) and r <= cur_reg

    for sid in sorted(seed_fail):
        cur_fail, cur_reg = eval_fn(working)
        if sid not in cur_fail:
            patch["resolved_by_prior_change"].append(sid); continue
        if accepted_n >= budget:
            patch["unresolved"].append(sid); continue
        words = sorted(w for w, c in cands.items() if sid in c["seed_ids"])
        qtoks, found = _norm_tokens(by_id[sid]["query"]), None
        for word in words:
            if word in working["aliases"]:
                continue
            for target in sorted(cands[word]["targets_by_seed"][sid]):
                trial = copy.deepcopy(working)
                trial["aliases"][word] = [target]; trial["notes"][word] = round2_note(word, sid, target, "alias")
                if ok(trial, sid, cur_fail, cur_reg):
                    found = trial; break
            if found:
                break
        if found is None:
            for word in words:
                for ctx in sorted(t for t in qtoks if t != word):
                    for target in sorted(cands[word]["targets_by_seed"][sid]):
                        trial = copy.deepcopy(working)
                        trial["rules"].append({"when_all": [word, ctx], "add": [target]})
                        trial["notes"][f"rule:{len(trial['rules']) - 1}"] = round2_note(word, sid, target, "rule")
                        if ok(trial, sid, cur_fail, cur_reg):
                            found = trial; break
                    if found:
                        break
                if found:
                    break
        if found is None:
            patch["unresolved"].append(sid); continue
        working, accepted_n = found, accepted_n + 1
    patch.update(alias_patch(base_raw, working))
    return working, patch


def validate_alias_change(before_raw, after_raw, cands, queries, budget=BUDGET) -> list:
    """Pure shape check (spec §7.2); replay equality is verify_replay."""
    out = [f"top-level {k!r} changed" for k in ("version", "alias_damping", "rule_damping") if before_raw.get(k) != after_raw.get(k)]
    out += [f"unexpected top-level key {k!r}" for k in after_raw if k not in before_raw]
    for w, v in before_raw["aliases"].items():
        if after_raw["aliases"].get(w) != v:
            out.append(f"alias {w!r} removed or changed")
    if after_raw["rules"][:len(before_raw["rules"])] != before_raw["rules"]:
        out.append("existing rules removed or reordered")
    for k, n in before_raw["notes"].items():
        if after_raw["notes"].get(k) != n:
            out.append(f"note {k!r} removed or changed")
    added = alias_patch(before_raw, after_raw)
    per_seed, n_new = {}, len(added["aliases"]) + len(added["rules"])
    if n_new > budget:
        out.append(f"budget exceeded: {n_new} > {budget}")
    for key, note in added["notes"].items():
        cw, sid = note.get("candidate_word"), note.get("seed_query_id")
        if cw not in cands:
            out.append(f"{key}: candidate_word {cw!r} not in frozen candidates"); continue
        if sid not in cands[cw]["seed_ids"]:
            out.append(f"{key}: seed {sid!r} is not a seed of candidate {cw!r}"); continue
        per_seed[sid] = per_seed.get(sid, 0) + 1
        if key.startswith("rule:"):
            rule = after_raw["rules"][int(key[5:])]
            ctx = [t for t in rule["when_all"] if t != cw]
            if cw not in rule["when_all"] or len(rule["when_all"]) > 2:
                out.append(f"{key}: rule must be candidate_word plus at most one context token")
            elif ctx and ctx[0] not in _norm_tokens(queries.get(sid, "")):
                out.append(f"{key}: context token {ctx[0]!r} is not a unigram of seed {sid}")
            targets = rule["add"]
        else:
            if key != cw:
                out.append(f"{key}: alias word must equal candidate_word {cw!r}")
            targets = after_raw["aliases"].get(key, [])
        if len(targets) != 1:
            out.append(f"{key}: exactly 1 target required")
        elif targets[0] not in cands[cw]["targets_by_seed"].get(sid, []):
            out.append(f"{key}: target {targets[0]!r} is not a target of {cw!r} for seed {sid}")
    for w in added["aliases"]:
        if w not in added["notes"]:
            out.append(f"alias {w!r} added without a note")
    for i in range(len(before_raw["rules"]), len(after_raw["rules"])):
        if f"rule:{i}" not in added["notes"]:
            out.append(f"rule:{i} added without a note")
    out += [f"more than one change per seed: {sid}" for sid, n in sorted(per_seed.items()) if n > 1]
    return out


def baseline_mismatch(aliases_raw, ranking_raw, cands_doc) -> list:
    inputs = cands_doc["generated_from"]["inputs"]
    return [name for name, raw in (("aliases", aliases_raw), ("ranking", ranking_raw)) if policy.canonical_sha256(raw) != inputs[name]]


def baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench) -> str:
    return policy.canonical_sha256({"b_aliases_sha256": policy.canonical_sha256(aliases_raw), "b_ranking_sha256": policy.canonical_sha256(ranking_raw),
                                    "snapshot_registry_fingerprint": fp, "alias_candidates_sha256": policy.canonical_sha256(cands_doc),
                                    "seed_benchmark_sha256": policy.canonical_sha256(bench["seed"]),
                                    "regression_benchmark_sha256": policy.canonical_sha256(bench["regression_negative"])})


def result_sha256(final_constants, patch) -> str:
    return policy.canonical_sha256({"final_constants": dict(final_constants),
                                    "alias_patch": {k: patch[k] for k in ("aliases", "rules", "notes")}})


def verify_replay(eval_fn, bench, base_raw, cands, constants, expected_result_sha256) -> list:
    """AC-19: the committed alias additions must equal a fresh proposer run from the B state at the adopted constants."""
    _, patch = propose_aliases(eval_fn, bench, base_raw, cands)
    got = result_sha256(constants, patch)
    return [] if got == expected_result_sha256 else [f"replay result_sha256 {got} != adopted {expected_result_sha256}"]
```

- [ ] **Step 4: Pipeline, adoption, verification CLI**

```python
def _alias_policy(raw):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "a.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        return policy.load_aliases(p)


def run_pipeline(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline):
    """Pure orchestration (tested with a fake evaluate_fn(point, raw_aliases) -> (seed_res, reg_res)):
    constants exactly once with the B aliases, then the proposer exactly once at those constants."""
    results = []
    for point in grid_points(grid):
        s, r = evaluate_fn(point, aliases_raw)
        results.append((point, s["passed"], r["passed"]))
    selected = select_candidate(results, baseline, grid)

    def eval_fn(raw):
        s, r = evaluate_fn(selected, raw)
        return frozenset(f["id"] for f in s["failed"]), frozenset(f["id"] for f in r["failed"])
    working, patch = propose_aliases(eval_fn, bench, aliases_raw, cands_doc["candidates"])
    seed_res, reg_res = evaluate_fn(selected, working)
    return results, selected, working, patch, seed_res, reg_res


def _parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--note", default="")
    ap.add_argument("--adopt", default=None, metavar="RUN_ID")
    ap.add_argument("--reject", default=None, metavar="RUN_ID"); ap.add_argument("--reason", default="full-suite-failed")
    ap.add_argument("--verify", action="store_true")
    return ap.parse_args(argv)


def _read_log():
    return [json.loads(x) for x in LOG_PATH.read_text(encoding="utf-8").splitlines() if x.strip()] if LOG_PATH.exists() else []


def _write_log(lines):
    LOG_PATH.write_text("\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in lines) + "\n", encoding="utf-8")


def _with_state(cache, fn):
    """Build the registry from a temporary copy of the snapshot and call fn(state)."""
    with tempfile.TemporaryDirectory() as td:
        copy_dir = pathlib.Path(td) / "cache"
        shutil.copytree(cache, copy_dir)
        with mock.patch.object(storage, "CACHE_DIR", copy_dir):
            return fn(build_state(copy_dir))


def main(argv=None) -> int:
    args = _parse(argv)
    if args.adopt:
        return _adopt(args.adopt)
    if args.reject:
        return _reject(args.reject, args.reason)
    cache = (args.cache_dir or pathlib.Path("")).expanduser()
    if not all((cache / f"{s}.json").is_file() for s in SOURCES):
        print(f"error: {cache} is not a cache snapshot (missing <source>.json)", file=sys.stderr); return 2
    problems = rs.verify_freeze(ROUND, cache)
    if problems:
        print("error: snapshot S differs from round_freeze: " + "; ".join(problems), file=sys.stderr); return 2
    os.environ.pop("ATLASSIAN_DOCS_SEARCH_LOG", None)
    bench, rp = _BENCH, policy.load_ranking(RANKING_PATH)
    aliases_raw, ranking_raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8")), json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    cands_doc = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    if args.verify:
        return _verify(cache, bench, rp, aliases_raw, ranking_raw, cands_doc)
    bad = baseline_mismatch(aliases_raw, ranking_raw, cands_doc)
    if bad:
        print(f"error: dirty round state: {bad} differ from the B baseline recorded in alias_candidates.json; "
              f"restore the B commit's files first (git checkout <B> -- {ALIASES_PATH.name} {RANKING_PATH.name})", file=sys.stderr); return 2
    seal = bench.get(f"round{ROUND}_seal") or {}

    def body(state):
        fp = state.registry.fingerprint
        if fp != seal.get("registry_fingerprint") or fp != cands_doc["generated_from"]["registry_fingerprint"]:
            raise SystemExit(f"error: registry fingerprint {fp} != round{ROUND}_seal / alias_candidates provenance; wrong snapshot?")
        evaluate_fn = lambda point, raw: evaluate_point(state, rp, point, bench, _alias_policy(raw))
        results, selected, working, patch, seed_res, reg_res = run_pipeline(evaluate_fn, bench, aliases_raw, cands_doc, rp.tuning_grid, dict(rp.baseline))
        violations = validate_alias_change(aliases_raw, working, cands_doc["candidates"], {r["id"]: r["query"] for r in bench["seed"]})
        if violations:
            raise SystemExit("\n".join(f"VIOLATION {v}" for v in violations))
        for f in seed_res["failed"] + reg_res["failed"]:
            print(f"  FAIL {f['id']} {f['query']!r}")
            for key, score, sig in top5(state, rp, selected, f["query"], _alias_policy(working)):
                print(f"      {score:8.3f}  {key}  {json.dumps(sig, sort_keys=True)}")
        return fp, results, selected, working, patch, seed_res, reg_res
    try:
        fp, results, selected, working, patch, seed_res, reg_res = _with_state(cache, body)
    except SystemExit as e:
        print(e, file=sys.stderr); return 2
    return _finish(args, rp, fp, results, selected, patch, working, seed_res, reg_res,
                   baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench))


def _finish(args, rp, fp, results, selected, patch, working, seed_res, reg_res, base_sha) -> int:
    perfect = seed_res["passed"] == SEED_TOTAL and reg_res["passed"] == REGRESSION_TOTAL
    effects = plan_effects(args.dry_run, perfect)
    line = {"run_id": str(uuid.uuid4()), "run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": _git("rev-parse", "HEAD").strip(), "round": ROUND, "registry_fingerprint": fp,
            "baseline_sha256": base_sha, "events": list(EVENTS), "constants_selected": selected, "grid_size": len(results),
            "passing_combos": sum(1 for _, s, r in results if s == SEED_TOTAL and r == REGRESSION_TOTAL),
            "aliases_proposed": patch, "seed": f"{seed_res['passed']}/{SEED_TOTAL}",
            "regression_negative": f"{reg_res['passed']}/{REGRESSION_TOTAL}", "tuning_failed": not perfect,
            "result_sha256": result_sha256(selected, patch),
            "dirty": dirty_paths(_git("status", "--porcelain", "--untracked-files=no")), "note": args.note,
            "ranking_structure_sha256": rp.structure_sha256, "baseline": dict(rp.baseline)}
    line["run_log_sha256"] = policy.canonical_sha256(line)          # hashed before status/adopted (they change on --adopt)
    line["status"], line["adopted"] = ("pending" if perfect else "failed"), False
    if effects["write_constants"]:                                   # candidate policy, adoption pending --adopt
        write_constants(selected)
        ALIASES_PATH.write_text(json.dumps(working, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        policy.load_aliases(ALIASES_PATH)
    if effects["append_log"]:
        _write_log(_read_log() + [line])
    else:
        print("dry run: nothing written; would-be log line:"); print(json.dumps(line, ensure_ascii=False, sort_keys=True))
    print(json.dumps({k: line[k] for k in ("run_id", "constants_selected", "seed", "regression_negative", "passing_combos",
                                           "tuning_failed", "status", "result_sha256")}, ensure_ascii=False))
    print(json.dumps({"aliases": patch["aliases"], "rules": patch["rules"], "unresolved": patch["unresolved"],
                      "resolved_by_prior_change": patch["resolved_by_prior_change"]}, ensure_ascii=False))
    return 0 if perfect else 1


def _current_result_sha256() -> str:
    """result_sha256 recomputed from the policy files on disk (constants + round-N alias additions)."""
    raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    base = strip_round_entries(raw, ROUND)
    return result_sha256(policy.load_ranking(RANKING_PATH).constants, alias_patch(base, raw))


def _adopt(run_id) -> int:
    """Second stage (AC-19/20): called by the frozen worker brief only after the canonical full suite passed."""
    lines = _read_log()
    mine = [l for l in lines if l["run_id"] == run_id]
    if len(mine) != 1 or mine[0]["status"] != "pending":
        print(f"error: run {run_id} is not a pending run", file=sys.stderr); return 2
    if any(l["adopted"] for l in lines):
        print("error: a run is already adopted", file=sys.stderr); return 2
    if _current_result_sha256() != mine[0]["result_sha256"]:
        print("error: policy files no longer reproduce this run's result_sha256", file=sys.stderr); return 2
    mine[0]["status"], mine[0]["adopted"] = "adopted", True
    _write_log(lines)
    print(json.dumps({"run_id": run_id, "adopted": True}))
    return 0


def _reject(run_id, reason) -> int:
    """pending -> rejected (e.g. the canonical full suite failed): restore the B policy files and record why.
    A rejected run is a round abort (the tooling or its tests are wrong), distinct from tuning_failed."""
    lines = _read_log()
    mine = [l for l in lines if l["run_id"] == run_id]
    if len(mine) != 1 or mine[0]["status"] != "pending":
        print(f"error: run {run_id} is not a pending run", file=sys.stderr); return 2
    subprocess.run(["git", "checkout", "--", str(ALIASES_PATH.relative_to(ROOT)), str(RANKING_PATH.relative_to(ROOT))], cwd=ROOT, check=True)
    cands_doc = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    bad = baseline_mismatch(json.loads(ALIASES_PATH.read_text(encoding="utf-8")), json.loads(RANKING_PATH.read_text(encoding="utf-8")), cands_doc)
    if bad:
        print(f"error: B baseline not restored: {bad}", file=sys.stderr); return 2
    mine[0]["status"], mine[0]["reject_reason"] = "rejected", reason
    _write_log(lines)
    print(json.dumps({"run_id": run_id, "status": "rejected", "reason": reason}))
    return 0


def _verify(cache, bench, rp, aliases_raw, ranking_raw, cands_doc) -> int:
    adopted = [l for l in _read_log() if l["adopted"]]
    if len(adopted) != 1:
        print("error: exactly one adopted run required", file=sys.stderr); return 2
    base, consts = strip_round_entries(aliases_raw, ROUND), dict(rp.constants)

    def body(state):
        def eval_fn(raw):
            s, r = evaluate_point(state, rp, consts, bench, _alias_policy(raw))
            return frozenset(f["id"] for f in s["failed"]), frozenset(f["id"] for f in r["failed"])
        return verify_replay(eval_fn, bench, base, cands_doc["candidates"], consts, adopted[0]["result_sha256"])
    problems = _with_state(cache, body)
    if policy.canonical_sha256(base) != cands_doc["generated_from"]["inputs"]["aliases"]:
        problems.append("stripped alias file differs from the B baseline recorded in alias_candidates.json")
    if consts != adopted[0]["constants_selected"]:
        problems.append("constants on disk differ from the adopted run")
    print("replay ok" if not problems else "\n".join(f"MISMATCH {m}" for m in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Round-2 integrity tests in `test_evaluator.py` (guarded)**

```python
CANDIDATES = RANKING.parent / "alias_candidates.json"
TUNING_LOG_R2 = pathlib.Path(__file__).resolve().parent / "search-tuning-round2.jsonl"


class TestRound2AliasesAndLog(unittest.TestCase):
    def test_round2_aliases_within_frozen_candidates(self):
        if not CANDIDATES.exists():
            print("alias_candidates.json absent: checked after commit T"); return
        from tests import tune_search_ranking as tune
        raw = json.loads(ALIASES.read_text(encoding="utf-8")); cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
        b = json.loads(BENCH.read_text(encoding="utf-8")); queries = {r["id"]: r["query"] for r in b["seed"]}
        self.assertEqual(tune.validate_alias_change(tune.strip_round_entries(raw, 2), raw, cands, queries), [])
        seeds = {r["id"]: r for r in b["seed"]}
        for n in raw["notes"].values():
            if n["origin"] == "round2":
                self.assertIn("R6", seeds[n["seed_query_id"]]["failure_classes"])

    def test_round2_tuning_log_one_way(self):
        if not TUNING_LOG_R2.exists():
            print("round 2 tuning log absent: checked after tuning"); return
        from tests import tune_search_ranking as tune
        lines = [json.loads(l) for l in TUNING_LOG_R2.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len({l["run_id"] for l in lines}), len(lines))
        for l in lines:
            self.assertEqual(l["round"], 2); self.assertEqual(l["events"], list(tune.EVENTS))
            self.assertRegex(l["baseline_sha256"], r"^[0-9a-f]{64}$"); self.assertRegex(l["result_sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(l["status"], ("pending", "adopted", "failed", "rejected")); self.assertEqual(l["adopted"], l["status"] == "adopted")
            self.assertEqual(l["run_log_sha256"], ev.canonical_sha256({k: v for k, v in l.items() if k not in ("run_log_sha256", "status", "adopted")}))
        self.assertEqual(len({l["baseline_sha256"] for l in lines}), 1)
        valid = [l for l in lines if not l["tuning_failed"]]
        self.assertLessEqual(len({l["result_sha256"] for l in valid}), 1)
        adopted = [l for l in lines if l["adopted"]]
        self.assertLessEqual(len(adopted), 1)
        if adopted:
            self.assertEqual(adopted[0], valid[0])
            raw = json.loads(RANKING.read_text(encoding="utf-8")); self.assertEqual(adopted[0]["constants_selected"], raw["constants"])
            self.assertEqual(tune._current_result_sha256(), adopted[0]["result_sha256"])     # files reproduce the adopted result
```

(`run_log_sha256` is computed in `_finish` before `status`/`adopted` are added, so `--adopt` does not change it.)

- [ ] **Step 6: Run everything and commit**

```bash
python -m unittest tests.test_tune_search_ranking -v && python -m unittest discover -s tests -t .
git add tests/tune_search_ranking.py tests/test_tune_search_ranking.py tests/benchmarks/test_evaluator.py
git commit -m "tuning: one-way pipeline from the B baseline, deterministic proposer, replay verifier, two-stage adoption

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Round-aware diagnostic with the Round 2 final fields, docs (commit H7 = `housekeeping_commit`)

**Files:**
- Modify: `tests/diag_search_queries.py`
- Modify: `tests/test_diag_search_queries.py`
- Modify: `README.md`, `AGENTS.md` (one paragraph each)

**Interfaces:**
- Produces: `diag.run(argv)` takes `--round N` (default `ev.current_round()["round"]`); the seal key is `round{N}_seal`; plaintext hidden records must carry origin `held_out-r{N}` / `negative-r{N}` (exit 2 otherwise); report gains `"round": N`, `"held_out_top3"` (`{"passed": n, "total": m}` for the `held_out` set: records whose some `expected_top1_any` key is within the top 3 results; `null` when held_out is not evaluated), `"alias_candidates_sha256"` and `"concept_lexicon_sha256"` (canonical sha of the data files, `null` if absent) alongside the existing `alias_sha256`.

- [ ] **Step 1: Tests**

In `tests/test_diag_search_queries.py` change `run_diag` to pass `"--round", "1"` and add:

```python
    def test_round_selects_seal_key_and_reports_round(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--sets", "seed")
        self.assertEqual(rep["round"], 1); self.assertTrue(rep["seal_match"])
        with mock.patch("builtins.print"):
            code2, rep2 = diag.run(["--cache-dir", str(self.cache), "--round", "2", "--bench-file", str(self.good_bench), "--sets", "seed"])
        self.assertEqual(code2, 0); self.assertFalse(rep2["seal_match"])               # no round2_seal in this bench

    def test_plaintext_origin_must_match_round(self):
        plain = {"held_out": [{**self.plain["held_out"][0], "origin": "held_out-r2"}], "negative": []}
        p = self.tmp / "wrong_round.json"; p.write_text(json.dumps(plain), encoding="utf-8")
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(p), "--sets", "held_out")
        self.assertEqual(code, 2); self.assertEqual(rep["sets"], {})

    def test_round2_final_fields(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path))
        self.assertEqual(rep["held_out_top3"], {"passed": 2, "total": 2})
        for k in ("alias_sha256", "alias_candidates_sha256", "concept_lexicon_sha256"):
            self.assertIn(k, rep)
        for k in ("alias_candidates_sha256", "concept_lexicon_sha256"):
            path = diag.policy.DATA_DIR / f"{k[:-7]}.json"
            self.assertEqual(rep[k], ev.canonical_sha256(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None)
        code2, rep2 = self.run_diag("--bench-file", str(self.good_bench), "--sets", "seed")
        self.assertIsNone(rep2["held_out_top3"])
```

- [ ] **Step 2: Implement**

In `diag_search_queries.py`: add `ap.add_argument("--round", type=int, default=None)`; in `run`, `rnd = args.round or ev.current_round()["round"]`; `_sections(bench, plain, rnd)` checks `rec["origin"] == f"{name}-r{rnd}"` for every plaintext record and `run` returns `(2, {"error": "wrong_round_origin", "sets": {}})` when violated; `_evaluate(state, bench, sections, sets, plain, rnd)` uses `seal = bench.get(f"round{rnd}_seal") or {}`, adds `"round": rnd`, `"alias_candidates_sha256": _data_sha("alias_candidates.json")`, `"concept_lexicon_sha256": _data_sha("concept_lexicon.json")` (helper returning `ev.canonical_sha256(json)` or `None`), and `"held_out_top3": None`; `held_out_top3` is derived from the SAME ranked lists the evaluation used (no second search of a hidden query): the search function passed to `ev.evaluate` records each query's top-5 key list in a dict; after evaluating `held_out`, `report["held_out_top3"] = {"passed": count(any(k in ranked[q][:3] for k in expected)), "total": len(records)}`. Update the docstring.

- [ ] **Step 2b: Guarded final-artifact test (in `tests/benchmarks/test_evaluator.py`)**

```python
FINAL_R2 = pathlib.Path(__file__).resolve().parent / "round2-final.json"


class TestRound2FinalArtifact(unittest.TestCase):
    def test_round2_final_artifact(self):
        if not FINAL_R2.exists():
            print("round2-final.json absent: checked after commit D"); return
        art = json.loads(FINAL_R2.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8")); seal = b["round2_seal"]
        e = ev.freeze_for(2)
        self.assertEqual(art["round"], 2); self.assertRegex(art["git_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(art["sealed_sha256"], {"held_out": seal["held_out_sha256"], "negative": seal["negative_sha256"]})
        self.assertEqual(art["registry_fingerprint"], e["source_registry_fingerprint"]); self.assertEqual(art["spec_sha256"], e["source_spec_sha256"])
        self.assertEqual(art["alias_candidates_sha256"], e["alias_candidates_sha256"]); self.assertEqual(art["concept_lexicon_sha256"], e["concept_lexicon_sha256"])
        self.assertEqual(art["alias_sha256"], ev.canonical_sha256(json.loads(ALIASES.read_text(encoding="utf-8"))))
        self.assertEqual(art["evaluation_code_sha256"], e["evaluation_code_sha256_at_T"])
        self.assertEqual(set(art["held_out_top3"]), {"passed", "total"}); self.assertEqual(art["held_out_top3"]["total"], 16)
        for sect, total in (("held_out", 16), ("negative", 8)):
            self.assertEqual(art["sets"][sect]["total"], total)
```

- [ ] **Step 3: Docs**

`README.md` Round section: one paragraph "Round 2" pointing to the spec, the tools (`round_seal.py --round 2` incl. `freeze`/`verify-freeze`, `alias_candidates_tool.py`, `concept_lexicon_check.py prepare/finalize/merge`, the one-way `tune_search_ranking.py` with `--adopt`/`--verify`), the snapshot env var `ATLASSIAN_DOCS_ROUND2_CACHE`, and the terminal states D/F. `AGENTS.md`: one paragraph that the files in `evaluator.TOOLING_FILES` are immutable from `housekeeping_commit` to the terminal commit.

- [ ] **Step 4: Full suite, commit**

```bash
python -m unittest discover -s tests -t .
git add tests/diag_search_queries.py tests/test_diag_search_queries.py README.md AGENTS.md
git commit -m "diag: --round N, plaintext origin check, Round 2 final fields (held_out_top3, candidates/lexicon shas); docs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 5: Whole-branch code review (before S, T and any hidden generation)**

Dispatch the whole-branch code reviewer (most capable model) over `95b8de0..HEAD`: semantics of every tool, the tests that pin them, the spec AC mapping. Fix findings now (they become H′ commits; the last one is `housekeeping_commit`). After this point no semantic review of `TOOLING_FILES` happens again in the round — only hash/provenance checks — because every later reviewer or controller may have seen hidden plaintext.

**`housekeeping_commit` = HEAD after the last H7/H′ commit.** Record its sha in `~/.atlassian_api_updater/round2-work/controller-events.jsonl` (`{"event": "housekeeping_commit", "sha": ...}`). A tool defect found before T is fixed in an H′ commit that replaces `housekeeping_commit`; affected pre-T artifacts are regenerated in dependency order.

---

### Task 8: **[controller]** Source snapshot S and verb inventory finalization (pre-T, dependency order steps 1–5)

**Files:**
- Create (outside repo): `~/.atlassian_api_updater/round2-cache/` (S)
- Modify: `tools/atlassian_docs/intelligence/data/search_ranking.json` (`verb_methods` only)
- Create (scratch, later attached to readiness): `~/.atlassian_api_updater/round2-work/{verb_report,method_safety,concept_tokens}.json`

- [ ] **Step 1: Create S (refuse if it exists) and record its identity**

```bash
test ! -e ~/.atlassian_api_updater/round2-cache || { echo "S exists"; exit 1; }
python -m tools.atlassian_docs            # refresh the live cache once (network), then copy
cp -R ~/.atlassian_api_updater/cache ~/.atlassian_api_updater/round2-cache   # adjust source dir to storage.CACHE_DIR
mkdir -p ~/.atlassian_api_updater/round2-work
python tests/benchmarks/round_seal.py catalog --round 2 --cache-dir ~/.atlassian_api_updater/round2-cache \
  --out ~/.atlassian_api_updater/round2-work/round2-generator-catalog.json \
  --internal-out ~/.atlassian_api_updater/round2-work/round2-internal-catalog.json
```

Ledger `registry_fingerprint` and the three `spec_sha256` lines in `~/.atlassian_api_updater/round2-work/controller-events.jsonl` (Task 15 renders them).

- [ ] **Step 2: Verb report on the current (Round 1) table, then write the §6 inventory**

```bash
python tests/benchmarks/alias_candidates_tool.py verb-report --cache-dir ~/.atlassian_api_updater/round2-cache --out ~/.atlassian_api_updater/round2-work/verb_report_before.json
```

Replace `verb_methods` in `search_ranking.json` with the JSON block of spec §6 verbatim (keep every other key byte-identical; `python -c "from tools.atlassian_docs.intelligence import policy; policy.load_ranking()"` must succeed).

- [ ] **Step 3: Method-safety fixed point**

```bash
W=~/.atlassian_api_updater/round2-work; S=~/.atlassian_api_updater/round2-cache
python tests/benchmarks/alias_candidates_tool.py verb-report   --cache-dir $S --out $W/verb_report.json
python tests/benchmarks/alias_candidates_tool.py method-safety --cache-dir $S --out tests/benchmarks/round2-method-safety.json
```

Rule (fixed point): **whenever `verb_methods` changes for any reason** (a `VIOLATION`, or a `REVIEW` line the controller decides to widen), re-run BOTH commands. Finalize only when a full pass ends with the inventory unchanged AND `violations == 0`. `REVIEW` lines are diagnostic (verb vs noun usage); every widen/no-widen decision is ledgered. `tests/benchmarks/round2-method-safety.json` (the final pass, `violations: 0`, provenance with `inputs.verb_inventory`) is committed at T; the test `test_round2_method_safety_artifact` (Task 10) checks `violations == 0`, `generated_from.registry_fingerprint == freeze.source_registry_fingerprint` and `generated_from.inputs.verb_inventory == freeze.verb_inventory_sha256`. Then `python -m unittest discover -s tests -t .` (the §6 parity test added in Task 10 must see the same inventory in the spec block; update the spec block in the T commit if the inventory was widened).

- [ ] **Step 4: Finalize**

```bash
python -c "import json; from tests.benchmarks.evaluator import canonical_sha256 as c; print(c(json.load(open('tools/atlassian_docs/intelligence/data/search_ranking.json'))['verb_methods']))"
```

Record this `verb_inventory_sha256` in the controller events ledger together with the sha of `tests/benchmarks/round2-method-safety.json`. **From here the inventory does not change.** Leave the change in the working tree: pre-T policy/data changes are committed exactly once, as the single T commit in Task 10 (no intermediate commit; AC-01a).

---

### Task 9: **[controller]** Concept lexicon — generate (stateless), check, review (stateless), gate, merge

**Files:**
- Create: `tests/benchmarks/round2-lexicon-generation-prompt.md`, `tests/benchmarks/round2-lexicon-review-prompt.md` (both committed at T for provenance)
- Create: `tools/atlassian_docs/intelligence/data/concept_lexicon.json`
- Modify: `tools/atlassian_docs/intelligence/data/search_aliases.json` (lexicon merge only)

- [ ] **Step 1: Concept tokens**

```bash
python tests/benchmarks/alias_candidates_tool.py concept-tokens --cache-dir ~/.atlassian_api_updater/round2-cache --out ~/.atlassian_api_updater/round2-work/concept_tokens.json
```

- [ ] **Step 2: Generation prompt (frozen text)**

Write `tests/benchmarks/round2-lexicon-generation-prompt.md`:

```
You are given a list of concept tokens from a REST API catalog (Jira / Confluence). Each line is: token, occurrence count, products.
For each concept token, list up to 5 single English words (lowercase, letters only, one word each, no verbs) that an ordinary
end user might type instead of that token when describing what they want (for example a colloquial or business synonym).
Do not repeat the token itself. Do not invent multi-word phrases. Do not include product names.
Output ONLY one JSON object: {"<synonym>": ["<concept token>"], ...} — one concept per synonym; if a synonym fits several
concepts, choose the single best one. No commentary.

CONCEPT TOKENS:
<one line per token: "<token>\t<count>\t<products>">
```

- [ ] **Step 3: Generate in a stateless context**

Materialize the exact model input: fill the template's `<one line per token ...>` line with `"\t".join([token, str(count), ",".join(sources)])` per token from `concept_tokens.json` and write `~/.atlassian_api_updater/round2-work/lexicon-generation-input.txt`; ledger its sha256 (`generation_input_sha256`) and the template's (`prompt_template_sha256`). Open ChatGPT **Temporary chat**, select **Unpersonalized**, confirm the UI state (screenshot kept in `round2-work/`), paste the input file byte-for-byte, take the first parseable JSON output, save it as `round2-work/lexicon_raw.json`, close the chat without saving; ledger the attempt (`attempts.jsonl`, stage `lexicon-generation`). Not parseable → retry with the identical input; never a semantic re-request.

- [ ] **Step 4: Structural stage (no review, no cap) to produce the review input**

```bash
python tests/benchmarks/concept_lexicon_check.py prepare --cache-dir ~/.atlassian_api_updater/round2-cache \
  --raw ~/.atlassian_api_updater/round2-work/lexicon_raw.json --out ~/.atlassian_api_updater/round2-work/lexicon_structural.json
```

- [ ] **Step 5: Semantic review (stateless, binary reject only)**

`tests/benchmarks/round2-lexicon-review-prompt.md`:

```
Below is a JSON object mapping a candidate synonym (a single English word an end user might type) to one API concept token.
For each entry answer whether an ordinary user of an issue-tracking / wiki product would plausibly use the synonym to mean
that concept. Reply ONLY with a JSON object {"<synonym>": true|false, ...} covering every key. Do not add, rename or
re-target any entry.

ENTRIES:
<the "lexicon" object of lexicon_structural.json>
```

Materialize `round2-work/lexicon-review-input.txt` (template with `<the "lexicon" object of lexicon_structural.json>` replaced by that JSON), ledger its sha256, run it in a new Unpersonalized Temporary chat (same lifecycle rules), save the first parseable output as `round2-work/lexicon_review.json`; `finalize` refuses an invalid review (missing/extra keys, non-bool) → retry the identical input, ledger each attempt. Then:

```bash
python tests/benchmarks/concept_lexicon_check.py finalize --cache-dir ~/.atlassian_api_updater/round2-cache \
  --raw ~/.atlassian_api_updater/round2-work/lexicon_raw.json --structural ~/.atlassian_api_updater/round2-work/lexicon_structural.json \
  --review ~/.atlassian_api_updater/round2-work/lexicon_review.json \
  --generation-input ~/.atlassian_api_updater/round2-work/lexicon-generation-input.txt \
  --review-input ~/.atlassian_api_updater/round2-work/lexicon-review-input.txt \
  --template tests/benchmarks/round2-lexicon-generation-prompt.md --out tools/atlassian_docs/intelligence/data/concept_lexicon.json
python tests/benchmarks/alias_candidates_tool.py lexicon-gate --cache-dir ~/.atlassian_api_updater/round2-cache --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json
python tests/benchmarks/concept_lexicon_check.py merge --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json --aliases tools/atlassian_docs/intelligence/data/search_aliases.json --round 2
python -m unittest discover -s tests -t .
```

Ledger kept/rejected counts, gate rejections, merge skips.

---

### Task 10: **[controller]** Candidates, R5/R6 classification, worker brief, hidden prompts

**Files:**
- Create: `tools/atlassian_docs/intelligence/data/alias_candidates.json`
- Modify: `tests/benchmarks/search_queries.json` (seed `failure_classes` only)
- Create: `tests/benchmarks/round2-worker-brief.md`, `tests/benchmarks/round2-hidden-generation-prompt.md`, `tests/benchmarks/round2-hidden-reviewer-prompt.md`

- [ ] **Step 1: Candidates and classification**

```bash
python tests/benchmarks/alias_candidates_tool.py candidates --cache-dir ~/.atlassian_api_updater/round2-cache --out tools/atlassian_docs/intelligence/data/alias_candidates.json
python tests/benchmarks/alias_candidates_tool.py classify   --cache-dir ~/.atlassian_api_updater/round2-cache
python -m unittest discover -s tests -t .
```

- [ ] **Step 2: Worker brief (frozen text)**

`tests/benchmarks/round2-worker-brief.md`:

```
# Round 2 tuning worker brief (frozen at commit T)

You are the B..C tuning worker. You do not analyse queries, choose constants or choose aliases; the tools do.
Allowed inputs: this file, tests/benchmarks/search_queries.json (seed, regression_negative only), the frozen data files
under tools/atlassian_docs/intelligence/data/, the snapshot at $ATLASSIAN_DOCS_ROUND2_CACHE, and the tuning script.
Forbidden: anything under ~/.atlassian_api_updater/sealed/, any *.enc file, any ChatGPT page, docs/phase3-readiness.md.

Procedure (run from the repo root, exactly once; rerun only after a tool error, never after a valid result):
1. git status --porcelain --untracked-files=no   -> must be empty (otherwise stop and report).
2. python tests/tune_search_ranking.py --cache-dir "$ATLASSIAN_DOCS_ROUND2_CACHE" --note "round2 tuning run"
   (prints a JSON line with run_id and status: "pending" = candidate policy written, "failed" = log only)
3. python -m unittest discover -s tests -t .
4. If step 2 exited 0 and step 3 is OK:
     python tests/tune_search_ranking.py --adopt <run_id>
     git add tools/atlassian_docs/intelligence/data/search_ranking.json tools/atlassian_docs/intelligence/data/search_aliases.json
             tests/benchmarks/search-tuning-round2.jsonl
     git commit -m "round2: tuning run (one-way pipeline, adopted <run_id>)" + the project trailer.
   If step 2 exited 0 but step 3 FAILED:
     python tests/tune_search_ranking.py --reject <run_id> --reason full-suite-failed   (restores the B policy files)
     git add tests/benchmarks/search-tuning-round2.jsonl
     git commit -m "round2: tuning run rejected (full suite failed)" + trailer; report the failing tests verbatim.
   If step 2 exited 1 (tuning_failed): commit ONLY tests/benchmarks/search-tuning-round2.jsonl with message
     "round2: tuning failed (log only)" + trailer; do not touch the data files.
   If step 2 exited 2: do not commit; report the stderr verbatim.
Report: exit codes, the JSON summary lines printed by step 2, the --adopt/--reject output, the commit sha, and nothing else.
```

- [ ] **Step 3: Hidden generation prompt template (frozen text)**

`tests/benchmarks/round2-hidden-generation-prompt.md` — a natural-language transcription of the `round_seal.py` checker contract (the ids in `Rules checked by a program` are the re-request rule ids):

```
You are creating an evaluation set for an API operation search engine over the Atlassian Jira / Confluence REST catalog.
Below is the catalog: one line per operation with key, source, method, summary, tags (tab-separated).
Produce ONLY one JSON object: {"held_out": [16 records], "negative": [8 records]}.
held_out record: {"id": "h-001".."h-016", "query": "...", "expected_top1_any": ["<key>"], "forbidden_top1": [], "origin": "held_out-r2",
  "failure_classes": [], "ambiguous": false}
negative record: {"id": "n-001".."n-008", "query": "...", "expected_top1_any": [], "forbidden_top1": ["<key>"], "origin": "negative-r2",
  "failure_classes": [], "ambiguous": false}
Rules checked by a program (a violation is sent back to you by rule id):
- words: every query has 3 to 7 words of natural end-user phrasing.
- operationId: the set of words in a query (lowercased, split on non-letters, ignoring a/an/the/to/of/for/in/on/at/and/or/with/by/from/is/are/be/this/that)
  must not equal the set of words of any operation's operationId.
- summary/tags: after removing those same small words, a held_out query must not contain two consecutive words that also
  appear consecutively in the expected operation's summary or in one of its tags.
- distribution (held_out): at least 6 jira-platform, 4 jira-software, 5 confluence expected operations; at least 4 GET,
  4 POST, 2 PUT, 2 DELETE; at least 4 queries contain "jira" or "confluence" and at least 9 contain neither.
- negative-phrase: a negative query's words (same normalization, singularized) must not equal, in order, the words of any
  operation summary or of the last literal segment of any operation path.
- schema / catalog: ids and origins exactly as above; every key must exist in the catalog.
- reuse (checker-only, you cannot see the existing benchmark): queries that repeat an existing benchmark query or its word
  set are rejected; if that happens you will be asked for a replacement with rule id "reuse".
negative: the query must have NO correct operation in the catalog; forbidden_top1 is the tempting wrong operation.
No commentary.

CATALOG:
<generator catalog lines>
```

- [ ] **Step 4: Hidden reviewer prompt (frozen text)**

`tests/benchmarks/round2-hidden-reviewer-prompt.md`:

```
You review candidate evaluation records against an API catalog. The catalog is given as JSON lines, one operation per
line, with the fields key, source, method, operation_id, summary, tags, description (full text, not truncated).
For each held_out record decide whether the expected operation is the single best answer to the query
(reject if another operation answers it at least as well, or if the query is unanswerable). For each negative record
decide whether the catalog truly has NO correct operation for the query (reject if one exists) and whether forbidden_top1
is really a wrong answer. Reply ONLY with {"<id>": {"accept": true|false, "reason": "<short>"}, ...} for every record.
Never rewrite queries, never propose replacements.

RECORDS:
<plaintext records>
CATALOG (JSON lines):
<internal catalog lines>
```

- [ ] **Step 5: Commit T (the single freeze commit)**

Add to `tests/intelligence/test_search.py` the §6 parity test (reads the spec file, extracts the JSON block after `## 6.`, compares to `verb_methods`) and `test_round2_method_safety_artifact` (guarded by file existence: `violations == 0`; `generated_from.registry_fingerprint == ev.freeze_for(2)["source_registry_fingerprint"]`; `generated_from.inputs.verb_inventory == ev.freeze_for(2)["verb_inventory_sha256"]`; every row `ok`). Then:

```bash
python tests/benchmarks/round_seal.py freeze --round 2 --cache-dir ~/.atlassian_api_updater/round2-cache
python -m unittest discover -s tests -t .
git add tools/atlassian_docs/intelligence/data tests/benchmarks/round_freeze.json tests/benchmarks/search_queries.json \
  tests/benchmarks/round2-*.md tests/benchmarks/round2-method-safety.json tests/intelligence/test_search.py docs/superpowers/specs/2026-10-02-search-quality-round2-design.md
git commit -m "T: Round 2 freeze (verb inventory, concept lexicon, candidates, R5/R6, worker brief, hidden prompts, tooling hash)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

`git diff --stat 95b8de0 -- tools/atlassian_docs/intelligence/search.py` must be empty; `git diff <H> -- $(python -c "from tests.benchmarks import evaluator as ev; print(' '.join(ev.TOOLING_FILES))")` must be empty (otherwise this is an H′ situation: fix, commit H′, redo Tasks 8–10 from the affected step).

---

### Task 11: **[controller]** Hidden-set generation, machine check, stateless review, commit B, encryption

Evidence for everything in this task goes to `~/.atlassian_api_updater/round2-work/controller-events.jsonl` and the **attempt ledger** `~/.atlassian_api_updater/round2-work/attempts.jsonl`: one line per model call `{"attempt_no", "stage": "generation"|"replacement"|"review", "input_sha256", "output_sha256", "status": "valid"|"parse_error"|"invalid"|"transport_error", "reason_code"}`. Plaintext never enters the ledger — hashes only. The repo working tree stays clean until commit B.

- [ ] **Step 1: Materialize the exact generation input and generate**

```bash
python - <<'EOF2'
import json, pathlib, hashlib
w = pathlib.Path.home() / ".atlassian_api_updater" / "round2-work"
tpl = pathlib.Path("tests/benchmarks/round2-hidden-generation-prompt.md").read_text(encoding="utf-8")
cat = json.load(open(w / "round2-generator-catalog.json"))
lines = "\n".join(f"{r['key']}\t{r['source']}\t{r['method']}\t{r['summary']}\t{','.join(r['tags'] or [])}" for r in cat)
filled = tpl.replace("<generator catalog lines>", lines)
(w / "hidden-generation-input.txt").write_text(filled, encoding="utf-8")
print("generation_input_sha256", hashlib.sha256(filled.encode()).hexdigest())
EOF2
```

Open a new **Unpersonalized Temporary chat** (confirm the toggle, screenshot to `round2-work/`), paste `hidden-generation-input.txt` byte-for-byte, take the first output; store it as `~/.atlassian_api_updater/sealed/round2-sealed.json` (mode 600) only if it parses as JSON with `held_out`/`negative` lists; ledger the attempt (`parse_error` → retry with the identical input; never a semantic re-request before the machine check).

- [ ] **Step 2: Machine check (checker-only constraints included)**

```bash
python tests/benchmarks/round_seal.py check --round 2 --plain ~/.atlassian_api_updater/sealed/round2-sealed.json \
  --bench tests/benchmarks/search_queries.json --internal-catalog ~/.atlassian_api_updater/round2-work/round2-internal-catalog.json
```

On violations: ONE fixed-format re-request in the same chat — lines of the form `record h-00N rejected: <rule id>` (rule ids: `words`, `operationId`, `summary/tags`, `reuse`, `distribution`, `negative-phrase`, `schema`, `catalog`), nothing else — first parseable output replaces only the rejected records (`stage: replacement`); re-check. Count re-requests.

- [ ] **Step 3: Semantic review (stateless, validated output)**

```bash
python - <<'EOF2'
import json, pathlib, hashlib
w = pathlib.Path.home() / ".atlassian_api_updater" / "round2-work"
tpl = pathlib.Path("tests/benchmarks/round2-hidden-reviewer-prompt.md").read_text(encoding="utf-8")
plain = json.load(open(pathlib.Path.home() / ".atlassian_api_updater" / "sealed" / "round2-sealed.json"))
cat = json.load(open(w / "round2-internal-catalog.json"))
lines = "\n".join(json.dumps({k: r.get(k) for k in ("key", "source", "method", "operation_id", "summary", "tags", "description")}, ensure_ascii=False) for r in cat)
filled = tpl.replace("<plaintext records>", json.dumps(plain, ensure_ascii=False, indent=1)).replace("<internal catalog lines>", lines)
(w / "hidden-review-input.txt").write_text(filled, encoding="utf-8")
print("review_input_sha256", hashlib.sha256(filled.encode()).hexdigest())
EOF2
```

New Unpersonalized Temporary chat → paste `hidden-review-input.txt` → first output → `round2-work/hidden-review-output.json` → validate:

```bash
python - <<'EOF2'
import json, pathlib
from tests.benchmarks import round_seal as rs
w = pathlib.Path.home() / ".atlassian_api_updater"
plain = json.load(open(w / "sealed" / "round2-sealed.json")); out = json.load(open(w / "round2-work" / "hidden-review-output.json"))
ids = [r["id"] for r in plain["held_out"] + plain["negative"]]
problems = rs.validate_reviewer_output(out, ids); print(problems or "valid"); print(sorted(k for k, v in out.items() if not v["accept"]))
EOF2
```

Invalid output → `status: invalid`, retry the identical input (transport/parse/invalid only). Rejected ids → one fixed-format replacement request to the generator chat (`record h-00N rejected: reviewer`); the response must pass `validate_replacement_output(obj, rejected_ids)` (exactly those ids), is merged with `merge_replacements`, machine-checked, then reviewed (replacement records only, same frozen prompt). No semantic rerun after a valid output. Before sealing, write `round2-work/coverage-manifest.json` = `coverage_manifest(plain, accepted_attempt_by_id)` (every final record → canonical sha + the review attempt that accepted it; a record without an accepting attempt blocks B). The controller applies results; it never decides accept/reject itself.

- [ ] **Step 4: Seal (commit B)**

```bash
python tests/benchmarks/round_seal.py seal --round 2 --plain ~/.atlassian_api_updater/sealed/round2-sealed.json \
  --bench tests/benchmarks/search_queries.json --cache-dir ~/.atlassian_api_updater/round2-cache
python -m unittest discover -s tests -t .
git add tests/benchmarks/search_queries.json
git commit -m "B: Round 2 seal (held_out 16 / negative 8 sha256 + distributions)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

(Only the bench changes in B; readiness is rendered at the terminal commit from the ledgers.)

- [ ] **Step 5: [user] Encrypt and delete the plaintext**

Ask the user to run in their own terminal (never in this session):

```bash
cd ~/.atlassian_api_updater/sealed && openssl enc -aes-256-cbc -pbkdf2 -in round2-sealed.json -out round2-sealed.json.enc && rm round2-sealed.json
```

Then the controller records the AC-18a-B checkpoint in the ledger:

```bash
test ! -e ~/.atlassian_api_updater/sealed/round2-sealed.json && shasum -a 256 ~/.atlassian_api_updater/sealed/round2-sealed.json.enc
```

---

### Task 12: **[controller]** S checkpoint, then dispatch the frozen worker brief (B..C)

- `python tests/benchmarks/round_seal.py verify-freeze --round 2 --cache-dir ~/.atlassian_api_updater/round2-cache` must print `freeze ok` (ledger it); `git status --porcelain --untracked-files=no` must be empty.
- Dispatch one implementer subagent (standard model) whose prompt is: one line of context + "read `tests/benchmarks/round2-worker-brief.md` first; it is your entire procedure" + the env var value for S + the report file path. Nothing else. Ledger the brief sha (must equal `round_freeze.worker_brief_sha256`), the number of runs, each report's `run_id`/`result_sha256`.
- Only predefined replies are allowed to the worker: "run the brief procedure", "run it again" (after a tool error).
- Review package + task reviewer as usual; the reviewer checks only: the commit matches the brief's rules, `--verify` passes, the log line validates, tests are green.

---

### Task 13: **[controller]** Provenance check, then commit C (success) or F (failure)

- [ ] **Step 1: Hash/provenance check only (both branches)**

No semantic code review after B (Task 7 Step 5 was the last one). Check: `git diff --stat <housekeeping_commit> -- <TOOLING_FILES>` empty; `tooling_code_sha256` unchanged; worker commit touches only the brief's allowed files; the tuning log has exactly one `adopted` run (success) or only `failed` runs (failure). A `rejected` run (full suite failed after a perfect tuning) is a **round abort**: record it in the ledger and readiness, stop, and restart from H′ with a fresh hidden set later; neither C/D nor F is produced.

- [ ] **Step 2a: Success (`status: adopted`, worker commit present)**

```bash
python tests/benchmarks/round_seal.py verify-freeze --round 2 --cache-dir ~/.atlassian_api_updater/round2-cache
python tests/tune_search_ranking.py --verify --cache-dir ~/.atlassian_api_updater/round2-cache
python -c "from tests.benchmarks import evaluator as ev; import pathlib; e=ev.freeze_for(2); assert ev.evaluation_code_sha256(pathlib.Path('.'))==e['evaluation_code_sha256_at_T'], 'evaluator changed since T'; print('ok')"
python -m unittest discover -s tests -t .
git commit --allow-empty -m "C: Round 2 freeze before final evaluation (evaluation_code_sha256 == at_T)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 2b: Failure (`status: failed`, log-only worker commit present)**

Checkpoint AC-18a-F (`.enc` sha unchanged, no plaintext) → ledger; render the full readiness Round 2 section (Task 15, failure branch) → commit `F: Round 2 tuning failed` touching only `docs/phase3-readiness.md`. Skip Task 14; continue with Task 16.

---

### Task 14: **[controller + user]** Commit D — single evaluation (success branch)

- [ ] `python tests/benchmarks/round_seal.py verify-freeze --round 2 --cache-dir ~/.atlassian_api_updater/round2-cache` → `freeze ok`; AC-18a-D checkpoint (`.enc` sha == B value) → ledger.
- [ ] **[user]** decrypt in their terminal: `cd ~/.atlassian_api_updater/sealed && openssl enc -d -aes-256-cbc -pbkdf2 -in round2-sealed.json.enc -out round2-sealed.json`.
- [ ] Plaintext sha must equal the seal, then exactly one evaluation:

```bash
python - <<'EOF2'
import json, pathlib
from tests.benchmarks.evaluator import canonical_sha256
p = json.load(open(pathlib.Path.home()/".atlassian_api_updater/sealed/round2-sealed.json"))
b = json.load(open("tests/benchmarks/search_queries.json"))["round2_seal"]
assert canonical_sha256(p["held_out"]) == b["held_out_sha256"] and canonical_sha256(p["negative"]) == b["negative_sha256"]; print("seal ok")
EOF2
python tests/diag_search_queries.py --round 2 --bench ~/.atlassian_api_updater/sealed/round2-sealed.json \
  --cache-dir ~/.atlassian_api_updater/round2-cache --json tests/benchmarks/round2-final.json
python tests/benchmarks/round_seal.py unseal --round 2 --plain ~/.atlassian_api_updater/sealed/round2-sealed.json --bench tests/benchmarks/search_queries.json
python -m unittest discover -s tests -t .
```

Then render readiness (Task 15, success branch) and commit D:

```bash
git add tests/benchmarks/search_queries.json tests/benchmarks/round2-final.json docs/phase3-readiness.md
git commit -m "D: Round 2 final evaluation (single run), unseal, decision record

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Gate: held_out ≥ 15/16 and negative 0/8.

---

### Task 15: **[controller]** Render the readiness Round 2 section from the ledgers (before the terminal commit)

Append to `docs/phase3-readiness.md` after the Round 2 pre-work subsection (never inside the Round 1 section) a `## Search Quality Round 2 — decision record (<date>)` section rendered from `controller-events.jsonl` + `attempts.jsonl`: `housekeeping_commit`, S fingerprint + spec shas, verb-report decisions, method-safety result, lexicon template/generation-input/raw/review-input/review-output shas + counts (kept/rejected/gate/merge-skipped), candidates count, R5/R6 counts, T/B/C shas (the terminal commit itself is written as `terminal_commit: self` — its sha cannot be known before it exists; it is recorded in the ledger and in Task 16's provenance report), hidden generation input/output shas per attempt with status, re-request count, reviewer input/output shas, `temporary_chat_unpersonalized: true`, `.enc` sha at B/terminal, worker brief sha + run count + `run_id`/`result_sha256` per run, `--verify` result, tuning log summary, result row (success) or failure row, the state model table with `null`/`not_applicable` on the failure branch, and the attestation list of spec §12. This task is a step of Task 13 (failure) or Task 14 (success); it never produces its own commit.

---

### Task 16: **[controller]** Post-terminal provenance review and finishing

- Record the terminal commit sha (D or F) in the ledger. Dispatch a reviewer (most capable model) limited to provenance: AC table of spec §12 row by row against git history, ledgers and artifacts; its report (with the terminal sha) is saved as `~/.atlassian_api_updater/round2-work/provenance-report.md` and summarized in memory; no code changes to `TOOLING_FILES`.
- Update memory: `search-quality-round1-status.md` → Round 2 outcome; MEMORY.md index.
- Use `superpowers:finishing-a-development-branch` (the user chooses merge/push).

## Self-review notes

- Spec coverage: §4 files → Tasks 2–5, 10; §5.1 (H, S, order) → Tasks 1–8; §5.2 → Tasks 8–10; §5.3 → Tasks 2 (negative phrase rule, reviewer validator), 9, 11; §5.4 → Task 11; §5.5/§7.2 → Task 6, 12; §5.6 → Task 12 (predefined replies only); §5.7 → Tasks 12–14 (verify-freeze checkpoints); §6 → Task 8 (+ parity test in Task 10); §7.0 → Tasks 5, 9 (review before cap, validated review, exact-input hashes); §7.1 → Task 4; §8 → Tasks 1–3, 7; §9 → Task 7 (final fields); §10 → each task's tests; §11 → Task 15; §12 AC-01a/b/c (git, Tasks 10–14), AC-02/03 (Task 14), AC-04 (seal checkpoint, Task 2), AC-05 (Task 3 tooling hash + git), AC-06a/b, AC-07, AC-08 (Task 3), AC-09 (Task 3 invariants), AC-10/11 (Tasks 7, 14), AC-12 (Task 6 validator), AC-13 (Tasks 3/4 provenance), AC-14 (Task 2), AC-15a/b, AC-20a/b (Task 6 log test + events + mock-order test), AC-16, AC-17 (Task 1), AC-18a-B/D/F, AC-18b (Tasks 11, 13, 14), AC-19 (Tasks 3, 6 `--verify`, 11 attempt ledger, 12), AC-21 (Task 13).
- Controller ruling: the spec's optional `--from-baseline` restore is not implemented; a dirty round state is refused and restored by `git checkout <B> -- <files>` (spec §5.5.6 allows "거부(기본)").
- The §6 spec-parity test is added at T (Task 10) because the inventory is finalized only after method-safety; `tests/intelligence/test_search.py` is not in `TOOLING_FILES`.

## Plan revision notes

P0 closed: (1) Round 2 negative phrase machine rule + tests (Task 2); (2) R6 defined independently of the candidate artifact (Task 4); (3) lexicon review before the per-concept cap via `prepare`/`finalize` (Task 5); (4) reviewer-output validators for the lexicon review and the hidden review with missing/extra/non-bool/non-object tests (Tasks 2, 5); (5) proposer replay verification `--verify` + `verify_replay`, validator checks `targets_by_seed` and rule context ∈ seed unigrams (Task 6); (6) two-stage adoption `pending` → `--adopt` after the full suite (Task 6, brief); (7) final diag fields `held_out_top3`, candidates/lexicon shas (Task 7); (8) controller evidence kept outside the repo, readiness rendered at the terminal commit on both branches (Tasks 11–15); (9) `verify-freeze` S checkpoints before dispatch and before D, tuning script checks spec shas too (Tasks 2, 12–14); (10) no T0 option (Task 8); (11) exact filled model inputs materialized and hashed, template hash separate (Tasks 5, 9, 11); (12) attempt ledger per model call (Task 11). P1: prompt rules transcribed from the checker (Task 10), budget checked after re-evaluation (Task 6), `events` + mock-order test for AC-20a (Task 6), H1..H7 with `housekeeping_commit` = H7 (constraints), whole-branch review moved before C (Task 13).

v3 (after external plan review 2) — P0: (1) AC-17 pins the legacy subset (phase2.5 + round1) instead of the whole file, so T's lexicon merge does not break it (Task 1); (2) negative path fixture `assignee of this` with a phrase-equality assertion (Task 2); (3) inventory fixed-point loop: any change → verb-report + method-safety rerun, finalize only when unchanged and 0 violations (Task 8); (4) `tests/benchmarks/round2-method-safety.json` committed at T with provenance + guarded test (Tasks 8, 10); (5) `--reject RUN_ID --reason` pending→rejected transition restoring the B policy; rejected = round abort, neither C/D nor F (Tasks 6, 10 brief, 13); (6) reviewer catalog as JSON lines with the fields the prompt names, no truncation (Tasks 10, 11); (7) whole-branch semantic review moved to right after H7, before S; after B only hash/provenance checks (Tasks 7, 13); (8) terminal commit written as `terminal_commit: self`, its sha recorded post-terminal in the ledger and provenance report (Tasks 15, 16). P1: validator checks top-level immutables and `--verify` compares the stripped file with the B baseline (Task 6); guarded `TestRound2FinalArtifact` (Task 7); `validate_replacement_output` / `merge_replacements` / coverage manifest (Tasks 2, 11); `held_out_top3` derived from the same ranked lists (Task 7); `candidates(..., round)` (Task 4); housekeeping range `95b8de0..housekeeping_commit` for AC-01a (constraints).
