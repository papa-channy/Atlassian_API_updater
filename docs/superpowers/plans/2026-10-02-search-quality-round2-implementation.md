# Search Quality Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repeat the sealed-evaluation procedure with vocabulary-only changes (general verb inventory, general concept lexicon, seed-derived alias candidates), all frozen before a fresh hidden set is generated, tune once through a deterministic one-way pipeline, and measure the sealed set exactly once.

**Architecture:** No scorer change. `policy.py` gains a round-aware alias-notes schema (the only production change). All Round 2 tooling is completed in commit H and frozen by hash at commit T: `tests/benchmarks/round_seal.py` (generalized seal + freeze entry), `tests/benchmarks/alias_candidates_tool.py` (concept tokens, verb report, method-safety, candidates, R5/R6 classification, lexicon gate), `tests/benchmarks/concept_lexicon_check.py` (lexicon normalization/validation/merge), and `tests/tune_search_ranking.py` rewritten as a one-way pipeline (constants once → deterministic alias proposer once → final check) that only ever starts from the B baseline. Controller tasks run the pre-T dependency order, generate the lexicon and the hidden set in stateless contexts, seal, dispatch the frozen worker brief, and evaluate at D (or close at F).

**Tech Stack:** Python ≥ 3.10 stdlib only under `tools/`; `unittest`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-02-search-quality-round2-design.md` v1.10 (external review: 10 rounds, final verdict "구현 계획으로 진행 가능"). The spec is binding; this plan is its argument.

## Global Constraints

- Canonical test command: `python -m unittest discover -s tests -t .` (405 OK at `57eb1e5`; omitting `-t .` makes `tests/mcp` shadow the SDK and gives spurious ImportErrors).
- Baseline commit for all "unchanged" checks: `95b8de0` (pre-work merge). Immutable from now to the terminal commit (spec §4, AC-05/AC-09): Round 1 spec §4 list, `tools/atlassian_docs/intelligence/search.py`, `tools/atlassian_docs/intelligence/data/operation_quirks.json`, `tests/benchmarks/round1-final.json`, `tests/benchmarks/search-tuning-round1.jsonl`, the `round1_seal` object inside the bench, and the Round 1 section of `docs/phase3-readiness.md` (from the line `## Search Quality Round 1 — decision record` up to, not including, the line `### Round 2 pre-work`).
- `policy.py` may change only in the housekeeping commit(s) H/H′ (Task 1) and only in `_check_alias_notes`. After the last H′ every file in `TOOLING_FILES` (Task 3) is immutable until the terminal commit (D or F).
- Commit order (spec §5): H (tooling, Tasks 1–7) → S (source snapshot) → pre-T dependency order → T (freeze) → generation (stateless) → B (seal, then user encrypts the plaintext) → tuning (frozen worker brief, one-way pipeline) → C → D, or B → F on tuning failure. Controller-only steps are marked **[controller]**; user-only steps **[user]**.
- Sealed plaintext path `~/.atlassian_api_updater/sealed/round2-sealed.json` is never given to an implementer or a tuning worker. After B only `round2-sealed.json.enc` exists; no agent knows the passphrase.
- Source snapshot S: `~/.atlassian_api_updater/round2-cache/` (`$ATLASSIAN_DOCS_ROUND2_CACHE`), created once after H; every catalog-dependent step reads only S.
- `POLICY_VERSIONS["search"]` stays 3. `search_ranking.json` tables other than `verb_methods` never change; `constants` change only inside the tuning run; `search_aliases.json` changes only at T (lexicon merge) and inside the tuning run (round2 entries).
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Chunked writes: no single tool call larger than ~60 lines.

## Review Focus

1. A seed query whose verbs conflict (allowed-method intersection empty) must count as "intent 0" in method-safety and R5 in classification, never as a crash (Task 4 `test_method_safety_conflicting_verbs_is_intent_zero`).
2. A lexicon synonym that is a plural of a catalog word (`files`) must be rejected after normalization, not kept because the raw string is absent from the catalog (Task 5 `test_plural_synonym_rejected_after_normalization`).
3. The alias proposer must not adopt an alias that fixes the target seed but breaks a regression_negative record (Task 6 `test_proposer_rejects_change_that_breaks_regression`).
4. Loading `search_aliases.json` with a `round1` note that lacks `candidate_word` must still succeed, while a `round2` note without it must fail (Task 1 `test_round_note_schema_is_round_aware`).
5. `round_seal.py seal --round 2` on a bench that already has `round1_seal` but no `round2_seal` must seal, and must refuse when `round2_seal` exists (Task 2 `test_seal_key_is_per_round`).

---

### Task 1: Round-aware alias-notes schema in `policy.py` (commit H)

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

    def test_bundled_aliases_unchanged_by_schema_change(self):
        """AC-17: the file committed at 95b8de0 still loads; its canonical sha is pinned."""
        p = policy.load_aliases()
        self.assertEqual(p.sha256, BUNDLED_ALIAS_SHA256)
```

Add near the top of the test module:

```python
BUNDLED_ALIAS_SHA256 = "<paste>"   # python -c "from tools.atlassian_docs.intelligence import policy; print(policy.load_aliases().sha256)" at 95b8de0
```

Run the print command on the current tree (aliases are unchanged since `95b8de0`) and paste the 64-hex value. (`{**r1, "candidate_word": 3}` is in `bads` because a non-string `candidate_word` is rejected for every origin.)

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

### Task 2: Generalize the seal tool to `round_seal.py --round N` and add the `freeze` command (commit H)

**Files:**
- Rename: `tests/benchmarks/round1_seal.py` → `tests/benchmarks/round_seal.py` (`git mv`)
- Rename: `tests/benchmarks/test_round1_seal.py` → `tests/benchmarks/test_round_seal.py` (`git mv`)
- Modify: `tests/benchmarks/test_evaluator.py` (two `from tests.benchmarks import round1_seal as rs` → `round_seal`), `tests/intelligence/test_search.py:251` (same import)
- Modify: `README.md` (one paragraph under the Round 1 section: the tool is now `round_seal.py --round N`)

**Interfaces:**
- Produces: module constants become functions of the round: `section_origin(round) -> dict`, `seal_key(round) -> str` (`f"round{round}_seal"`); `machine_check(plain, bench, internal_catalog, round=1)`; `seal_metadata(records, round, section_name)` unchanged; `load_catalogs_from_cache(cache_dir, round=1)` (snapshot label `round{N}-snapshot`); CLI subcommands take `--round N` (default 1); new `cmd_freeze` (Task 3 fills its hash list; here it only writes `round`, `structure_sha256`, `verb_inventory_sha256`, `source_registry_fingerprint`, `source_spec_sha256`).
- Produces: `seal` writes `bench[seal_key]` with the Round 1 fields plus `"machine_check": "passed"` and `"origins": {"held_out": "held_out-rN", "negative": "negative-rN"}` (AC-04 checkpoint record).

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
```

Run: `python -m unittest tests.benchmarks.test_round_seal -k RoundParameter -v` → Expected: FAIL (`section_origin` missing).

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

### Task 3: Round-freeze list, tooling hash, R5/R6 schema, Round 1 invariants (commit H)

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

### Task 4: `alias_candidates_tool.py` — concept tokens, verb report, method-safety, candidates, R5/R6, lexicon gate (commit H)

**Files:**
- Create: `tests/benchmarks/alias_candidates_tool.py`
- Test: `tests/benchmarks/test_alias_candidates_tool.py`

**Interfaces:**
- Consumes: `round_seal.load_catalogs_from_cache(cache_dir, round)`, `round_seal._write_bench`, `evaluator.canonical_sha256/STOPWORDS`, `search.tokenize_unigrams/singular` (read-only import of production code, like `round_seal`).
- Produces (pure, unit-tested): `norm_tokens(text) -> tuple` (unigrams → `singular`, order kept, deduped); `FUNCTION_WORDS`; `op_vocab(op) -> frozenset` (operationId + literal path segments + tags + summary, normalized); `catalog_vocab(internal) -> frozenset`; `catalog_df(internal) -> dict`; `concept_tokens(internal, noise) -> dict token -> {"count", "sources"}`; `verb_report(internal, verb_methods) -> dict verb -> {"methods": {M: n}, "outside": [...], "review": bool}`; `allowed_methods(query, verb_methods) -> None | frozenset`; `method_safety(bench, verb_methods) -> list rows`; `expected_vocab(rec, by_key, verb_methods, noise, hints) -> frozenset`; `candidates(bench, internal, ranking_raw, aliases_raw) -> dict` (`candidates`, `excluded`); `classify(bench, verb_methods, cands) -> dict id -> sorted classes`; `lexicon_gate(lexicon_doc, bench, by_key, ranking_raw) -> (lexicon_doc, rejected_now)`; `provenance(fp, shas, inputs) -> dict`.
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
        cands = act.candidates(BENCH, CAT2, RANK, ALIASES)["candidates"]
        cls = act.classify(BENCH, VERBS, cands)
        self.assertEqual(cls["s-001"], ["R6"]); self.assertEqual(cls["s-002"], [])
        self.assertEqual(cls["s-004"], ["R5"])                      # conflicting verbs -> no expected method covered
        no_verb = {"seed": [seed(7, "ticket details overview", A)], "regression_negative": []}
        self.assertEqual(act.classify(no_verb, VERBS, {})["s-007"], ["R5", "R6"])


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


def candidates(bench, internal, ranking_raw, aliases_raw) -> dict:
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
    return {"round": 2, "candidates": dict(sorted(cands.items())), "excluded": excluded}


def classify(bench, verb_methods, cands) -> dict:
    """spec §0.2: R5 = no verb or allowed methods cover no expected op (∃ semantics); R6 = the seed has a candidate word."""
    r6 = {sid for c in cands.values() for sid in c["seed_ids"]}
    out = {}
    for rec in bench["seed"]:
        allowed, classes = allowed_methods(rec["query"], verb_methods), []
        if allowed is None or not (allowed & expected_methods(rec)):
            classes.append("R5")
        if rec["id"] in r6:
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
    doc = candidates(bench, internal, ranking, aliases)
    doc["generated_from"] = provenance(fp, shas, inputs)
    _write(args.out, doc)
    print(f"candidates: {len(doc['candidates'])}, excluded: {len(doc['excluded'])}")
    return 0


def cmd_classify(args):
    internal, _, _, ranking, aliases, bench, _ = _load(args)
    cls = classify(bench, ranking["verb_methods"], candidates(bench, internal, ranking, aliases)["candidates"])
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

### Task 5: `concept_lexicon_check.py` — normalize, validate, cap, merge (commit H)

**Files:**
- Create: `tests/benchmarks/concept_lexicon_check.py`
- Test: `tests/benchmarks/test_concept_lexicon_check.py`

**Interfaces:**
- Consumes: `alias_candidates_tool.{norm_tokens, catalog_vocab, catalog_df, concept_tokens, FUNCTION_WORDS}`, `evaluator.{canonical_sha256, STOPWORDS}`.
- Produces (pure): `normalize_raw(raw) -> dict syn -> sorted targets`; `structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys) -> (kept, rejected)` with reasons `shape`, `function_word`, `verb`, `product_hint`, `in_catalog`, `target_not_concept`, `multi_target`, `alias_conflict`; `apply_review(lex, review) -> (kept, rejected)` (reason `semantic-reject`); `cap_per_concept(lex, limit=5) -> (kept, rejected)` (reason `concept-cap`, lexicographic first 5 kept); `build(raw, review, concept_set, catalog_set, df, verbs, hints, alias_keys) -> (lexicon, rejected)`; `merge(aliases_raw, lexicon, round) -> (new_aliases_raw, skipped)`.
- CLI: `check --cache-dir S --raw RAW.json --prompt PROMPT.md [--review REVIEW.json] --out tools/.../concept_lexicon.json`; `merge --lexicon FILE --aliases tools/.../search_aliases.json --round 2`.
- `concept_lexicon.json` shape: `{"round", "generated_from", "prompt_sha256", "raw_sha256", "review_output_sha256" | null, "lexicon": {syn: [concept]}, "rejected": {syn: {"reason", "targets", "catalog_df"}}, "catalog_df": {syn: n}}`.

- [ ] **Step 1: Write the failing tests**

```python
import json, unittest
from tests.benchmarks import concept_lexicon_check as clc

CONCEPTS = {"issue", "comment", "page", "sprint", "attachment", "version", "space"}
CATALOG = CONCEPTS | {"file", "get", "workspace", "linked"}
VERBS, HINTS, ALIAS_KEYS = {"get", "create"}, {"jira", "confluence"}, {"ticket"}


class TestChecks(unittest.TestCase):
    def test_normalize_lowercases_singularizes_and_merges(self):
        raw = {"Tickets": ["issue"], "ticket": ["issues"], "notes": ["comment"]}
        self.assertEqual(clc.normalize_raw(raw), {"note": ["comment"], "ticket": ["issue"]})

    def test_plural_synonym_rejected_after_normalization(self):
        kept, rej = clc.structural_check({"file": ["attachment"], "files": ["attachment"]}, CONCEPTS, CATALOG, VERBS, HINTS, ALIAS_KEYS)
        self.assertEqual(kept, {}); self.assertEqual({k: v["reason"] for k, v in rej.items()}, {"file": "in_catalog", "files": "in_catalog"})

    def test_structural_reasons(self):
        lex = {"note": ["comment"], "my": ["issue"], "get": ["issue"], "jira": ["issue"], "doc": ["page", "space"],
               "card": ["board"], "ticket": ["issue"], "e-mail": ["comment"]}
        kept, rej = clc.structural_check(lex, CONCEPTS, CATALOG, VERBS, HINTS, ALIAS_KEYS)
        self.assertEqual(kept, {"note": ["comment"]})
        self.assertEqual({k: v["reason"] for k, v in rej.items()},
                         {"my": "function_word", "get": "verb", "jira": "product_hint", "doc": "multi_target",
                          "card": "target_not_concept", "ticket": "alias_conflict", "e-mail": "shape"})

    def test_review_and_cap(self):
        lex = {f"w{i}": ["issue"] for i in range(7)}
        kept, rej = clc.apply_review(lex, {"w0": False, "w1": True})
        self.assertNotIn("w0", kept); self.assertEqual(rej["w0"]["reason"], "semantic-reject"); self.assertEqual(len(kept), 6)
        kept2, rej2 = clc.cap_per_concept(kept, 5)
        self.assertEqual(sorted(kept2), ["w1", "w2", "w3", "w4", "w5"]); self.assertEqual(rej2["w6"]["reason"], "concept-cap")

    def test_build_is_deterministic_and_ordered(self):
        raw = {"Notes": ["comment"], "files": ["attachment"], "release": ["version"], "cards": ["board"]}
        a = clc.build(raw, None, CONCEPTS, CATALOG, {"file": 3}, VERBS, HINTS, ALIAS_KEYS)
        b = clc.build(raw, None, CONCEPTS, CATALOG, {"file": 3}, VERBS, HINTS, ALIAS_KEYS)
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

- [ ] **Step 2: Implement**

```python
"""Round 2 concept lexicon (spec §7.0): normalize a stateless generator's output, validate it against the catalog,
apply the stateless semantic review, cap per concept, and merge into search_aliases.json as origin lexicon-rN.

  python tests/benchmarks/concept_lexicon_check.py check --cache-dir S --raw RAW.json --prompt PROMPT.md
         [--review REVIEW.json] --out tools/atlassian_docs/intelligence/data/concept_lexicon.json
  python tests/benchmarks/concept_lexicon_check.py merge --lexicon LEX.json --aliases tools/.../search_aliases.json --round 2
"""
import argparse, copy, json, pathlib, re, sys

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
        key = " ".join(act.norm_tokens(str(syn))) if act.norm_tokens(str(syn)) else str(syn).lower()
        toks = [t for target in (targets if isinstance(targets, list) else [targets]) for t in act.norm_tokens(str(target))]
        out.setdefault(key, set()).update(toks)
    return {k: sorted(v) for k, v in sorted(out.items())}


def structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys):
    kept, rej = {}, {}
    for syn, targets in lex.items():
        reason = ("shape" if not _SHAPE.fullmatch(syn) or syn in STOPWORDS else "function_word" if syn in act.FUNCTION_WORDS
                  else "verb" if syn in verbs else "product_hint" if syn in hints else "in_catalog" if syn in catalog_set
                  else "alias_conflict" if syn in alias_keys else "multi_target" if len(targets) != 1
                  else "target_not_concept" if targets[0] not in concept_set else None)
        (rej.__setitem__(syn, _rej(reason, targets)) if reason else kept.__setitem__(syn, list(targets)))
    return kept, rej


def apply_review(lex, review):
    kept, rej = {}, {}
    for syn, targets in lex.items():
        (rej.__setitem__(syn, _rej("semantic-reject", targets)) if review and review.get(syn) is False else kept.__setitem__(syn, list(targets)))
    return kept, rej


def cap_per_concept(lex, limit=MAX_PER_CONCEPT):
    by_concept = {}
    for syn, targets in sorted(lex.items()):
        by_concept.setdefault(targets[0], []).append(syn)
    kept, rej = {}, {}
    for concept, syns in by_concept.items():
        for i, syn in enumerate(sorted(syns)):
            (kept if i < limit else rej).__setitem__(syn, lex[syn] if i < limit else _rej("concept-cap", lex[syn]))
    return dict(sorted(kept.items())), rej


def build(raw, review, concept_set, catalog_set, df, verbs, hints, alias_keys):
    """Order (spec §7.0): normalize -> structural -> semantic reject -> per-concept cap. The seed gate runs later."""
    lex = normalize_raw(raw)
    kept, rejected = structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys)
    kept, r2 = apply_review(kept, review); rejected.update(r2)
    kept, r3 = cap_per_concept(kept); rejected.update(r3)
    for syn, e in rejected.items():
        e["catalog_df"] = df.get(syn, 0)
    return kept, dict(sorted(rejected.items()))


def merge(aliases_raw, lexicon, round):
    out, skipped = copy.deepcopy(aliases_raw), []
    for syn, targets in sorted(lexicon.items()):
        if syn in out["aliases"]:
            skipped.append(syn); continue
        out["aliases"][syn] = list(targets)
        out["notes"][syn] = {"origin": f"lexicon-r{round}", "seed_query_id": None, "failure_classes": [],
                             "evidence": f"concept lexicon r{round}"}
    return out, skipped


def _read(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def cmd_check(args):
    _, internal, fp, shas = rs.load_catalogs_from_cache(args.cache_dir, args.round)
    ranking, aliases = _read(act.DATA / "search_ranking.json"), _read(act.DATA / "search_aliases.json")
    raw, prompt = _read(args.raw), pathlib.Path(args.prompt).read_bytes()
    review = _read(args.review) if args.review else None
    concept_set = set(act.concept_tokens(internal, ranking["path_noise"]))
    df = act.catalog_df(internal)
    lexicon, rejected = build(raw, review, concept_set, act.catalog_vocab(internal), df, set(ranking["verb_methods"]),
                              set(ranking["product_hints"]), act.alias_source_words(aliases))
    doc = {"round": args.round, "prompt_sha256": __import__("hashlib").sha256(prompt).hexdigest(), "raw_sha256": canonical_sha256(raw),
           "review_output_sha256": canonical_sha256(review) if review is not None else None,
           "generated_from": act.provenance(fp, shas, {"verb_inventory": canonical_sha256(ranking["verb_methods"]),
                                                        "aliases": canonical_sha256(aliases), "raw_generation": canonical_sha256(raw),
                                                        "semantic_review": canonical_sha256(review) if review is not None else "none"}),
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
    p = sub.add_parser("check"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
    p.add_argument("--raw", required=True); p.add_argument("--prompt", required=True); p.add_argument("--review")
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("merge"); p.add_argument("--lexicon", required=True); p.add_argument("--aliases", required=True)
    p.add_argument("--round", type=int, default=2); p.set_defaults(fn=cmd_merge)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the tests and the suite, commit**

```bash
python -m unittest tests.benchmarks.test_concept_lexicon_check -v && python -m unittest discover -s tests -t .
git add tests/benchmarks/concept_lexicon_check.py tests/benchmarks/test_concept_lexicon_check.py
git commit -m "benchmarks: concept_lexicon_check (normalize, structural rules, semantic reject, per-concept cap, merge)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: One-way tuning pipeline with the deterministic alias proposer (commit H)

**Files:**
- Modify (rewrite): `tests/tune_search_ranking.py`
- Modify: `tests/test_tune_search_ranking.py`
- Modify: `tests/benchmarks/test_evaluator.py` (round-2 alias/log integrity tests, guarded by artifact existence)

**Interfaces:**
- Keeps: `grid_points`, `l1_index_distance`, `select_candidate`, `plan_effects`, `dirty_paths`, `ranking_with`, `evaluate_point`, `top5`, `write_constants`, `build_state`, `SEED_TOTAL`, `REGRESSION_TOTAL`, `CONSTANT_KEYS`.
- Produces: `ROUND = ev.current_round()["round"]`; `LOG_PATH = tests/benchmarks/search-tuning-round{ROUND}.jsonl`; `CANDIDATES_PATH`; `baseline_mismatch(aliases_raw, ranking_raw, cands_doc) -> list[str]`; `baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench) -> str`; `result_sha256(final_constants, alias_patch) -> str`; `round2_note(word, sid, target, kind)`; `propose_aliases(eval_fn, bench, base_raw, cands, budget=15) -> (working_raw, patch)` where `eval_fn(raw_aliases) -> (failed_seed_ids: frozenset, failed_regression_ids: frozenset)`; `alias_patch(base_raw, working_raw) -> dict` (`aliases`, `rules`, `notes` added); `validate_alias_change(before_raw, after_raw, cands, budget=15) -> list[str]`; `main(argv)` running the one-way pipeline; exit 0 success, 1 tuning_failed, 2 setup/baseline errors.
- Log line keys: `run_id`, `run_at`, `git_commit`, `round`, `registry_fingerprint`, `baseline_sha256`, `constants_selected`, `grid_size`, `passing_combos`, `aliases_proposed` (`aliases`, `rules`, `notes`, `resolved_by_prior_change`, `unresolved`, `trials`), `seed`, `regression_negative`, `tuning_failed`, `adopted`, `result_sha256`, `run_log_sha256`, `dirty`, `note`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_tune_search_ranking.py` `TestEffects` additions and add a proposer class (keep `TestSelector` and `test_plan_effects`/`test_dirty_paths` as they are; `dirty_paths` now excludes the round-N log — update the porcelain sample to `search-tuning-round2.jsonl` when `tune.ROUND == 2`, else keep round1; simplest: use `tune.LOG_REL` in the sample string):

```python
CANDS = {"workspace": {"seed_ids": ["s-001"], "targets_by_seed": {"s-001": ["page", "space"]}, "allowed_targets": ["page", "space"], "catalog_df": 7},
         "feedback": {"seed_ids": ["s-002", "s-003"], "targets_by_seed": {"s-002": ["comment"], "s-003": ["comment", "issue"]},
                      "allowed_targets": ["comment", "issue"], "catalog_df": 0}}
BASE_RAW = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"ticket": ["issue"]}, "rules": [],
            "notes": {"ticket": {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "x"}}}
BENCH2 = {"seed": [{"id": "s-001", "query": "browse pages inside this workspace"}, {"id": "s-002", "query": "leave feedback on this ticket"},
                   {"id": "s-003", "query": "read feedback on the issue"}], "regression_negative": [{"id": "rn-001", "query": "x"}]}


def fake_eval(rules):
    """rules: dict alias-word -> target that makes the listed seeds pass; 'BREAK:<word>' marks a regression break."""
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

    def test_budget_and_per_seed_one(self):
        fn = fake_eval({("workspace", "page"): ["s-001"], ("feedback", "comment"): ["s-002"], ("feedback", "issue"): ["s-003"]})
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, budget=1)
        self.assertEqual(patch["aliases"], {"workspace": ["page"]}); self.assertEqual(patch["unresolved"], ["s-002", "s-003"])
        _, patch2 = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(patch2["aliases"], {"workspace": ["page"], "feedback": ["comment"]})      # s-003: word already used, no rule fits
        self.assertEqual(patch2["unresolved"], ["s-003"])


class TestValidator(unittest.TestCase):
    def after(self, **aliases):
        raw = json.loads(json.dumps(BASE_RAW))
        for w, (t, sid) in aliases.items():
            raw["aliases"][w] = [t]; raw["notes"][w] = tune.round2_note(w, sid, t, "alias")
        return raw

    def test_accepts_proposer_shape(self):
        self.assertEqual(tune.validate_alias_change(BASE_RAW, self.after(workspace=("page", "s-001")), CANDS), [])

    def test_rejects_bad_shapes(self):
        two = self.after(workspace=("page", "s-001")); two["aliases"]["workspace"] = ["page", "space"]
        self.assertTrue(any("exactly 1" in v for v in tune.validate_alias_change(BASE_RAW, two, CANDS)))
        self.assertTrue(any("candidate" in v for v in tune.validate_alias_change(BASE_RAW, self.after(release=("version", "s-001")), CANDS)))
        self.assertTrue(any("target" in v for v in tune.validate_alias_change(BASE_RAW, self.after(workspace=("issue", "s-001")), CANDS)))
        bad_seed = self.after(workspace=("page", "s-002"))
        self.assertTrue(any("seed" in v for v in tune.validate_alias_change(BASE_RAW, bad_seed, CANDS)))
        twice = self.after(workspace=("page", "s-001")); twice["aliases"]["feedback"] = ["comment"]
        twice["notes"]["feedback"] = tune.round2_note("feedback", "s-001", "comment", "alias")
        self.assertTrue(any("per seed" in v for v in tune.validate_alias_change(BASE_RAW, twice, CANDS)))
        self.assertTrue(any("budget" in v for v in tune.validate_alias_change(BASE_RAW, self.after(workspace=("page", "s-001")), CANDS, budget=0)))
        removed = self.after(); del removed["aliases"]["ticket"]; del removed["notes"]["ticket"]
        self.assertTrue(any("removed" in v for v in tune.validate_alias_change(BASE_RAW, removed, CANDS)))
        rule = json.loads(json.dumps(BASE_RAW)); rule["rules"] = [{"when_all": ["workspace", "browse", "page"], "add": ["page"]}]
        rule["notes"]["rule:0"] = tune.round2_note("workspace", "s-001", "page", "rule")
        self.assertTrue(any("context" in v for v in tune.validate_alias_change(BASE_RAW, rule, CANDS)))


class TestHashes(unittest.TestCase):
    def test_result_sha_ignores_run_metadata_and_baseline_mismatch_detects_dirty(self):
        c = {"method_match_bonus": 2.0}; p = {"aliases": {"a": ["b"]}, "rules": [], "notes": {}}
        self.assertEqual(tune.result_sha256(c, p), tune.result_sha256(dict(c), json.loads(json.dumps(p))))
        cands = {"generated_from": {"inputs": {"aliases": policy.canonical_sha256(BASE_RAW), "ranking": "r" * 64}}}
        self.assertEqual(tune.baseline_mismatch(BASE_RAW, {"x": 1}, cands), ["ranking"])
        self.assertEqual(tune.baseline_mismatch({**BASE_RAW, "aliases": {}}, {"x": 1}, cands), ["aliases", "ranking"])
```

Add `import json` at the top of the test module. Run: `python -m unittest tests.test_tune_search_ranking` → Expected: AttributeError (`propose_aliases` missing).

- [ ] **Step 2: Rewrite `tests/tune_search_ranking.py` (header + pure helpers)**

Keep the existing pure helpers verbatim (`grid_points`, `l1_index_distance`, `select_candidate`, `plan_effects`, `dirty_paths`, `ranking_with`, `evaluate_point`, `top5`, `write_constants`, `_git`, `build_state`). Replace the docstring, constants and remove `head_alias_policy`, `_alias_change`, `--alias-change`:

```python
"""One-way, deterministic Round-N tuning (Round 2 spec §5.5/§7.2):

    python tests/tune_search_ranking.py --cache-dir S [--dry-run] [--note TEXT]

tune_round(b_aliases, b_ranking, snapshot, frozen_candidates, seed, regression) -> (final_constants, alias_patch, log):
  1. the working tree must be at the B baseline (search_aliases.json / search_ranking.json canonical hashes equal
     alias_candidates.json.generated_from.inputs); otherwise exit 2 ("dirty round state") - restore B first.
  2. constants := select_candidate over the whole grid, evaluated with the B aliases (exactly once).
  3. alias_patch := propose_aliases at those constants (exactly once; frozen candidates only, 1 target each).
  4. final check seed+regression; perfect -> write constants + aliases + log (adopted); else tuning_failed, log only.
No constant reselection after aliases, no second proposal. --dry-run writes nothing and prints the would-be log line.
"""
import argparse, copy, dataclasses, datetime, itertools, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid
from types import MappingProxyType
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.benchmarks import evaluator as ev  # noqa: E402
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
```

- [ ] **Step 3: Add the proposer, validator and hashes**

```python
def _norm_tokens(text):
    from tests.benchmarks.alias_candidates_tool import norm_tokens
    return norm_tokens(text)


def round2_note(word, sid, target, kind) -> dict:
    return {"origin": f"round{ROUND}", "seed_query_id": sid, "candidate_word": word, "failure_classes": ["R6"],
            "evidence": f"{kind} {word} -> {target} for {sid} (frozen candidate, deterministic proposer)"}


def alias_patch(base_raw, working_raw) -> dict:
    new_rules = working_raw["rules"][len(base_raw["rules"]):]
    return {"aliases": {w: v for w, v in working_raw["aliases"].items() if w not in base_raw["aliases"]},
            "rules": new_rules, "notes": {k: n for k, n in working_raw["notes"].items() if k not in base_raw["notes"]}}


def propose_aliases(eval_fn, bench, base_raw, cands, budget=BUDGET):
    """spec §7.2: seeds in id order; per seed, candidate words (sorted) x that seed's targets (sorted); direct alias
    first, then one-context rules; accept the first trial that fixes the seed without breaking any passing record.
    Every accepted change is applied immediately; later seeds are re-evaluated against the working state."""
    working = copy.deepcopy(base_raw)
    seed_fail, reg_fail = eval_fn(working)
    patch = {"resolved_by_prior_change": [], "unresolved": [], "trials": 0}
    accepted_n, by_id = 0, {r["id"]: r for r in bench["seed"]}

    def ok(trial, sid, cur_fail, cur_reg):
        patch["trials"] += 1
        f, r = eval_fn(trial)
        return sid not in f and f <= (cur_fail - {sid}) and r <= cur_reg

    for sid in sorted(seed_fail):
        if accepted_n >= budget:
            patch["unresolved"].append(sid); continue
        cur_fail, cur_reg = eval_fn(working)
        if sid not in cur_fail:
            patch["resolved_by_prior_change"].append(sid); continue
        words = sorted(w for w, c in cands.items() if sid in c["seed_ids"])
        qtoks = _norm_tokens(by_id[sid]["query"])
        found = None
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


def validate_alias_change(before_raw, after_raw, cands, budget=BUDGET) -> list:
    """Pure (spec §7.2): only additions, each a frozen candidate word -> exactly one allowed target, notes round{N}
    with candidate_word, one change per seed, within budget; existing entries untouched."""
    out = []
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
            out.append(f"{key}: seed {sid!r} is not a seed of candidate {cw!r}")
        per_seed[sid] = per_seed.get(sid, 0) + 1
        if key.startswith("rule:"):
            rule = after_raw["rules"][int(key[5:])]
            if cw not in rule["when_all"] or len(rule["when_all"]) > 2:
                out.append(f"{key}: rule must be candidate_word plus at most one context token")
            targets = rule["add"]
        else:
            if key != cw:
                out.append(f"{key}: alias word must equal candidate_word {cw!r}")
            targets = after_raw["aliases"].get(key, [])
        if len(targets) != 1:
            out.append(f"{key}: exactly 1 target required")
        elif targets[0] not in cands[cw]["allowed_targets"]:
            out.append(f"{key}: target {targets[0]!r} not an allowed target of {cw!r}")
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
```

- [ ] **Step 4: Rewrite `main` as the one-way pipeline**

```python
def _alias_policy(raw):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "a.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        return policy.load_aliases(p)


def _parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", required=True, type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--note", default="")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    cache = args.cache_dir.expanduser()
    if not all((cache / f"{s}.json").is_file() for s in SOURCES):
        print(f"error: {cache} is not a cache snapshot (missing <source>.json)", file=sys.stderr); return 2
    os.environ.pop("ATLASSIAN_DOCS_SEARCH_LOG", None)
    bench, rp = _BENCH, policy.load_ranking(RANKING_PATH)
    aliases_raw, ranking_raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8")), json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    cands_doc = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    bad = baseline_mismatch(aliases_raw, ranking_raw, cands_doc)
    if bad:
        print(f"error: dirty round state: {bad} differ from the B baseline recorded in alias_candidates.json; "
              f"restore the B commit's files first (git checkout <B> -- {ALIASES_PATH.name} {RANKING_PATH.name})", file=sys.stderr); return 2
    seal = bench.get(f"round{ROUND}_seal") or {}
    grid, baseline, base_policy = rp.tuning_grid, dict(rp.baseline), _alias_policy(aliases_raw)
    with tempfile.TemporaryDirectory() as td:
        copy_dir = pathlib.Path(td) / "cache"
        shutil.copytree(cache, copy_dir)
        with mock.patch.object(storage, "CACHE_DIR", copy_dir):
            state = build_state(copy_dir)
            fp = state.registry.fingerprint
            if fp != seal.get("registry_fingerprint") or fp != cands_doc["generated_from"]["registry_fingerprint"]:
                print(f"error: registry fingerprint {fp} != round{ROUND}_seal / alias_candidates provenance; wrong snapshot?", file=sys.stderr); return 2
            results = []
            for point in grid_points(grid):                                   # step 2: constants, exactly once, B aliases
                s, r = evaluate_point(state, rp, point, bench, base_policy)
                results.append((point, s["passed"], r["passed"]))
            selected = select_candidate(results, baseline, grid)

            def eval_fn(raw):                                                 # step 3: proposer at the frozen constants
                s, r = evaluate_point(state, rp, selected, bench, _alias_policy(raw))
                return frozenset(f["id"] for f in s["failed"]), frozenset(f["id"] for f in r["failed"])
            working, patch = propose_aliases(eval_fn, bench, aliases_raw, cands_doc["candidates"])
            violations = validate_alias_change(aliases_raw, working, cands_doc["candidates"])
            if violations:
                print("\n".join(f"VIOLATION {v}" for v in violations), file=sys.stderr); return 2
            seed_res, reg_res = evaluate_point(state, rp, selected, bench, _alias_policy(working))   # step 4: final check
            for f in seed_res["failed"] + reg_res["failed"]:
                print(f"  FAIL {f['id']} {f['query']!r}")
                for key, score, sig in top5(state, rp, selected, f["query"], _alias_policy(working)):
                    print(f"      {score:8.3f}  {key}  {json.dumps(sig, sort_keys=True)}")
    return _finish(args, rp, fp, results, selected, patch, working, seed_res, reg_res,
                   baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench))


def _append_log(line: dict) -> None:
    old = [json.loads(x) for x in LOG_PATH.read_text(encoding="utf-8").splitlines() if x.strip()] if LOG_PATH.exists() else []
    out = [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in old + [line]]
    LOG_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def _prior_adopted() -> bool:
    if not LOG_PATH.exists():
        return False
    return any(json.loads(x).get("adopted") for x in LOG_PATH.read_text(encoding="utf-8").splitlines() if x.strip())


def _finish(args, rp, fp, results, selected, patch, working, seed_res, reg_res, base_sha) -> int:
    perfect = seed_res["passed"] == SEED_TOTAL and reg_res["passed"] == REGRESSION_TOTAL
    effects = plan_effects(args.dry_run, perfect)
    line = {"run_id": str(uuid.uuid4()), "run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": _git("rev-parse", "HEAD").strip(), "round": ROUND, "registry_fingerprint": fp,
            "baseline_sha256": base_sha, "constants_selected": selected, "grid_size": len(results),
            "passing_combos": sum(1 for _, s, r in results if s == SEED_TOTAL and r == REGRESSION_TOTAL),
            "aliases_proposed": patch, "seed": f"{seed_res['passed']}/{SEED_TOTAL}",
            "regression_negative": f"{reg_res['passed']}/{REGRESSION_TOTAL}", "tuning_failed": not perfect,
            "adopted": effects["write_constants"] and not _prior_adopted(), "result_sha256": result_sha256(selected, patch),
            "dirty": dirty_paths(_git("status", "--porcelain", "--untracked-files=no")), "note": args.note,
            "ranking_structure_sha256": rp.structure_sha256, "baseline": dict(rp.baseline)}
    line["run_log_sha256"] = policy.canonical_sha256(line)
    if line["adopted"]:
        write_constants(selected)
        ALIASES_PATH.write_text(json.dumps(working, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        policy.load_aliases(ALIASES_PATH)
    if effects["append_log"]:
        _append_log(line)
    else:
        print("dry run: nothing written; would-be log line:"); print(json.dumps(line, ensure_ascii=False, sort_keys=True))
    print(json.dumps({k: line[k] for k in ("constants_selected", "seed", "regression_negative", "passing_combos", "tuning_failed",
                                           "adopted", "result_sha256")}, ensure_ascii=False))
    print(json.dumps({"aliases": patch["aliases"], "rules": patch["rules"], "unresolved": patch["unresolved"],
                      "resolved_by_prior_change": patch["resolved_by_prior_change"]}, ensure_ascii=False))
    return 0 if perfect else 1
```

`dirty_paths` keeps its signature but compares with `LOG_REL` (now round-based).

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
        before = json.loads(json.dumps(raw))
        for key, n in list(raw["notes"].items()):
            if n["origin"] == "round2":
                if key.startswith("rule:"):
                    before["rules"] = before["rules"][:int(key[5:])] if len(before["rules"]) > int(key[5:]) else before["rules"]
                else:
                    before["aliases"].pop(key, None)
                before["notes"].pop(key, None)
        self.assertEqual(tune.validate_alias_change(before, raw, cands), [])
        b = json.loads(BENCH.read_text(encoding="utf-8")); seeds = {r["id"]: r for r in b["seed"]}
        for n in raw["notes"].values():
            if n["origin"] == "round2":
                self.assertIn("R6", seeds[n["seed_query_id"]]["failure_classes"])

    def test_round2_tuning_log_one_way(self):
        if not TUNING_LOG_R2.exists():
            print("round 2 tuning log absent: checked after tuning"); return
        lines = [json.loads(l) for l in TUNING_LOG_R2.read_text(encoding="utf-8").splitlines() if l.strip()]
        runs = {l["run_id"] for l in lines}
        self.assertEqual(len(runs), len(lines))                                   # one record per run
        for l in lines:
            self.assertEqual(l["round"], 2); self.assertIn("constants_selected", l); self.assertIn("aliases_proposed", l)
            self.assertRegex(l["baseline_sha256"], r"^[0-9a-f]{64}$"); self.assertRegex(l["result_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(l["run_log_sha256"], ev.canonical_sha256({k: v for k, v in l.items() if k != "run_log_sha256"}))
        self.assertEqual(len({l["baseline_sha256"] for l in lines}), 1)
        valid = [l for l in lines if not l["tuning_failed"]]
        self.assertLessEqual(len({l["result_sha256"] for l in valid}), 1)
        adopted = [l for l in lines if l["adopted"]]
        if valid:
            self.assertEqual(adopted, [valid[0]])
            raw = json.loads(RANKING.read_text(encoding="utf-8"))
            self.assertEqual(adopted[0]["constants_selected"], raw["constants"])
        else:
            self.assertEqual(adopted, [])
```

- [ ] **Step 6: Run everything and commit**

```bash
python -m unittest tests.test_tune_search_ranking -v && python -m unittest discover -s tests -t .
git add tests/tune_search_ranking.py tests/test_tune_search_ranking.py tests/benchmarks/test_evaluator.py
git commit -m "tuning: one-way pipeline from the B baseline, deterministic alias proposer, validator, result/run-log hashes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Round-aware diagnostic, docs, and the Round 1 regression guard (commit H)

**Files:**
- Modify: `tests/diag_search_queries.py`
- Modify: `tests/test_diag_search_queries.py`
- Modify: `README.md`, `AGENTS.md` (one paragraph each)

**Interfaces:**
- Produces: `diag.run(argv)` takes `--round N` (default `ev.current_round()["round"]`); the seal key is `round{N}_seal`; report gains `"round": N`; plaintext hidden records must carry origin `held_out-r{N}` / `negative-r{N}` (checked via `check_schema` + explicit origin assertion, exit 2 otherwise).

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
```

- [ ] **Step 2: Implement**

In `diag_search_queries.py`: add `ap.add_argument("--round", type=int, default=None)`; in `run`, `rnd = args.round or ev.current_round()["round"]`; `_sections(bench, plain, rnd)` asserts `rec["origin"] == f"{name}-r{rnd}"` for every plaintext record, returning an error tuple `(2, {"error": "wrong_round_origin", "sets": {}})` from `run` when violated; `_evaluate(state, bench, sections, sets, plain, rnd)` uses `seal = bench.get(f"round{rnd}_seal") or {}` and adds `"round": rnd` to the report; messages say `round{rnd}_seal`. Update the module docstring.

- [ ] **Step 3: Docs**

`README.md` Round section: one paragraph "Round 2" pointing to the spec, the tools (`round_seal.py --round 2`, `alias_candidates_tool.py`, `concept_lexicon_check.py`, one-way `tune_search_ranking.py`), the snapshot env var `ATLASSIAN_DOCS_ROUND2_CACHE`, and the terminal states D/F. `AGENTS.md`: one paragraph that the Round 2 tooling files listed in `evaluator.TOOLING_FILES` are immutable from the housekeeping commit to the terminal commit.

- [ ] **Step 4: Full suite, commit**

```bash
python -m unittest discover -s tests -t .
git add tests/diag_search_queries.py tests/test_diag_search_queries.py README.md AGENTS.md
git commit -m "diag: --round N (seal key, plaintext origin check, report.round); Round 2 docs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

This is the last tooling commit: **H = HEAD after Task 7** (record its sha as `housekeeping_commit`). Any later tool defect found before T is fixed in an H′ commit and `housekeeping_commit` is updated.

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

Record `registry_fingerprint` and the three `spec_sha256` lines in `docs/phase3-readiness.md` (Round 2 section draft, Task 17 finalizes it).

- [ ] **Step 2: Verb report on the current (Round 1) table, then write the §6 inventory**

```bash
python tests/benchmarks/alias_candidates_tool.py verb-report --cache-dir ~/.atlassian_api_updater/round2-cache --out ~/.atlassian_api_updater/round2-work/verb_report_before.json
```

Replace `verb_methods` in `search_ranking.json` with the JSON block of spec §6 verbatim (keep every other key byte-identical; `python -c "from tools.atlassian_docs.intelligence import policy; policy.load_ranking()"` must succeed).

- [ ] **Step 3: Method-safety; widen only on violations; re-run until 0 violations**

```bash
python tests/benchmarks/alias_candidates_tool.py method-safety --cache-dir ~/.atlassian_api_updater/round2-cache --out ~/.atlassian_api_updater/round2-work/method_safety.json
python tests/benchmarks/alias_candidates_tool.py verb-report   --cache-dir ~/.atlassian_api_updater/round2-cache --out ~/.atlassian_api_updater/round2-work/verb_report.json
```

For each `VIOLATION` widen that verb to the superset that covers the expected method, re-run. `REVIEW` lines are diagnostic: decide per verb (verb usage vs noun usage) and record the decision in readiness; do not widen automatically. Then run `python -m unittest discover -s tests -t .` (the spec-§6 parity test in `tests/intelligence/test_search.py` is added here: it parses the JSON block under `## 6.` of the Round 2 spec and asserts equality with `verb_methods`; if the inventory was widened, update the spec §6 block in the same commit so both stay equal).

- [ ] **Step 4: Finalize**

```bash
python -c "import json; from tests.benchmarks.evaluator import canonical_sha256 as c; print(c(json.load(open('tools/atlassian_docs/intelligence/data/search_ranking.json'))['verb_methods']))"
```

Record this `verb_inventory_sha256` in readiness. **From here the inventory does not change.** Commit (not T yet — T is one commit, Task 11; keep this as a staged working-tree change or commit as `T0: verb inventory` if the user prefers smaller commits; the plan's default is a single T commit, so leave it uncommitted and continue).

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

Open ChatGPT **Temporary chat**, select **Unpersonalized**, confirm the UI state (screenshot kept in `round2-work/`), paste the prompt with the token lines filled from `concept_tokens.json` (`"\t".join([token, str(count), ",".join(sources)])`), take the first parseable JSON output, save it as `~/.atlassian_api_updater/round2-work/lexicon_raw.json`, close the chat without saving. Record `sha256` of the filled prompt and of the raw output. If the output is not parseable JSON: transport/parse retry with the identical prompt; never a semantic re-request.

- [ ] **Step 4: Structural check (no review yet) to produce the review input**

```bash
python tests/benchmarks/concept_lexicon_check.py check --cache-dir ~/.atlassian_api_updater/round2-cache \
  --raw ~/.atlassian_api_updater/round2-work/lexicon_raw.json --prompt tests/benchmarks/round2-lexicon-generation-prompt.md \
  --out ~/.atlassian_api_updater/round2-work/lexicon_structural.json
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

Run it in a new Unpersonalized Temporary chat (same lifecycle rules), save the first parseable output as `round2-work/lexicon_review.json`, record its sha256, then:

```bash
python tests/benchmarks/concept_lexicon_check.py check --cache-dir ~/.atlassian_api_updater/round2-cache \
  --raw ~/.atlassian_api_updater/round2-work/lexicon_raw.json --prompt tests/benchmarks/round2-lexicon-generation-prompt.md \
  --review ~/.atlassian_api_updater/round2-work/lexicon_review.json --out tools/atlassian_docs/intelligence/data/concept_lexicon.json
python tests/benchmarks/alias_candidates_tool.py lexicon-gate --cache-dir ~/.atlassian_api_updater/round2-cache --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json
python tests/benchmarks/concept_lexicon_check.py merge --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json --aliases tools/atlassian_docs/intelligence/data/search_aliases.json --round 2
python -m unittest discover -s tests -t .
```

Record kept/rejected counts, gate rejections, merge skips in readiness.

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
3. python -m unittest discover -s tests -t .
4. If step 2 exited 0 and step 3 is OK: git add tools/atlassian_docs/intelligence/data/search_ranking.json
   tools/atlassian_docs/intelligence/data/search_aliases.json tests/benchmarks/search-tuning-round2.jsonl
   and commit with message "round2: tuning run (one-way pipeline)" + the project trailer.
   If step 2 exited 1 (tuning_failed): commit ONLY tests/benchmarks/search-tuning-round2.jsonl with message
   "round2: tuning failed (log only)" + trailer; do not touch the data files.
   If step 2 exited 2: do not commit; report the stderr verbatim.
Report: exit codes, the two JSON summary lines printed by step 2, the commit sha, and nothing else.
```

- [ ] **Step 3: Hidden generation prompt template (frozen text)**

`tests/benchmarks/round2-hidden-generation-prompt.md` — the Round 1 generation prompt structure with the Round 2 rules:

```
You are creating an evaluation set for an API operation search engine over the Atlassian Jira / Confluence REST catalog.
Attached/below is the catalog: one line per operation with key, source, method, summary, tags.
Produce ONLY one JSON object: {"held_out": [16 records], "negative": [8 records]}.
held_out record: {"id": "h-001".., "query": "...", "expected_top1_any": ["<key>"], "forbidden_top1": [], "origin": "held_out-r2",
  "failure_classes": [], "ambiguous": false}
negative record: {"id": "n-001".., "query": "...", "expected_top1_any": [], "forbidden_top1": ["<key>"], "origin": "negative-r2",
  "failure_classes": [], "ambiguous": false}
Rules for every query: 3 to 7 words; natural end-user phrasing; never copy two consecutive words from the expected
operation's summary or tags; never equal the operationId's words; never reuse a query from the catalog text.
held_out: at least 6 jira-platform, 4 jira-software, 5 confluence targets; at least 4 GET, 4 POST, 2 PUT, 2 DELETE;
at most 7 queries name a product ("jira"/"confluence"), at least 9 do not.
negative: the query must have NO correct operation in the catalog; forbidden_top1 is the tempting wrong operation;
a query whose normalized words equal an operation summary or the last path segment is NOT allowed.
No commentary.

CATALOG:
<generator catalog lines>
```

- [ ] **Step 4: Hidden reviewer prompt (frozen text)**

`tests/benchmarks/round2-hidden-reviewer-prompt.md`:

```
You review candidate evaluation records against an API catalog (attached: key, source, method, operationId, summary, tags,
description). For each held_out record decide whether the expected operation is the single best answer to the query
(reject if another operation answers it at least as well, or if the query is unanswerable). For each negative record
decide whether the catalog truly has NO correct operation for the query (reject if one exists) and whether forbidden_top1
is really a wrong answer. Reply ONLY with {"<id>": {"accept": true|false, "reason": "<short>"}, ...} for every record.
Never rewrite queries, never propose replacements.

RECORDS:
<plaintext records>
CATALOG:
<internal catalog lines>
```

- [ ] **Step 5: Commit T (the single freeze commit)**

Add to `tests/intelligence/test_search.py` the §6 parity test (reads the spec file, extracts the JSON block after `## 6.`, compares to `verb_methods`). Then:

```bash
python tests/benchmarks/round_seal.py freeze --round 2 --cache-dir ~/.atlassian_api_updater/round2-cache
python -m unittest discover -s tests -t .
git add tools/atlassian_docs/intelligence/data tests/benchmarks/round_freeze.json tests/benchmarks/search_queries.json \
  tests/benchmarks/round2-*.md tests/intelligence/test_search.py docs/superpowers/specs/2026-10-02-search-quality-round2-design.md
git commit -m "T: Round 2 freeze (verb inventory, concept lexicon, candidates, R5/R6, worker brief, hidden prompts, tooling hash)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

`git diff --stat 95b8de0 -- tools/atlassian_docs/intelligence/search.py` must be empty; `git diff <H> -- $(python -c "from tests.benchmarks import evaluator as ev; print(' '.join(ev.TOOLING_FILES))")` must be empty (otherwise this is an H′ situation: fix, commit H′, redo Tasks 8–10 from the affected step).

---

### Task 11: **[controller]** Hidden-set generation, machine check, stateless review, commit B, encryption

- [ ] **Step 1: Generate** in a new **Unpersonalized Temporary chat** with the frozen template filled with `round2-generator-catalog.json` lines. First parseable output → `~/.atlassian_api_updater/sealed/round2-sealed.json` (mode 600). Record prompt/result sha256.

- [ ] **Step 2: Machine check**

```bash
python tests/benchmarks/round_seal.py check --round 2 --plain ~/.atlassian_api_updater/sealed/round2-sealed.json \
  --bench tests/benchmarks/search_queries.json --internal-catalog ~/.atlassian_api_updater/round2-work/round2-internal-catalog.json
```

On violations: re-request in the SAME temporary chat with the fixed format only (`레코드 h-00N 거부: <rule id>`), first parseable output again, re-check. Count re-requests.

- [ ] **Step 3: Semantic review** — new Unpersonalized Temporary chat with the frozen reviewer prompt + plaintext + internal catalog; first parseable output; record sha. Rejected records → one fixed-format re-request to the generator chat for replacements → machine check → review again for the replacements only. The controller applies results; it never decides accept/reject itself.

- [ ] **Step 4: Seal (commit B)**

```bash
python tests/benchmarks/round_seal.py seal --round 2 --plain ~/.atlassian_api_updater/sealed/round2-sealed.json \
  --bench tests/benchmarks/search_queries.json --cache-dir ~/.atlassian_api_updater/round2-cache
python -m unittest discover -s tests -t .
git add tests/benchmarks/search_queries.json docs/phase3-readiness.md
git commit -m "B: Round 2 seal (held_out 16 / negative 8 sha256 + distributions)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 5: [user] Encrypt and delete the plaintext**

Ask the user to run in their own terminal (never in this session):

```bash
cd ~/.atlassian_api_updater/sealed && openssl enc -aes-256-cbc -pbkdf2 -in round2-sealed.json -out round2-sealed.json.enc && rm round2-sealed.json
```

Then the controller verifies the AC-18a-B checkpoint and records it:

```bash
test ! -e ~/.atlassian_api_updater/sealed/round2-sealed.json && shasum -a 256 ~/.atlassian_api_updater/sealed/round2-sealed.json.enc
```

---

### Task 12: **[controller]** Dispatch the frozen worker brief (B..C)

- Dispatch one implementer subagent (standard model) whose prompt is: one line of context + "read `tests/benchmarks/round2-worker-brief.md` first; it is your entire procedure" + the env var value for S + the report file path. Nothing else. Record the brief sha (must equal `round_freeze.worker_brief_sha256`), the number of runs, and each report's result sha.
- Only predefined replies are allowed to the worker: "run the brief procedure", "run it again" (after a tool error).
- Review package + task reviewer as usual, but the reviewer checks only: the commit matches the brief's rules, the log line validates, tests are green.

---

### Task 13: **[controller]** Commit C (success branch) or F (failure branch)

- Success (`tuning_failed: false`, adopted run committed):

```bash
python -c "from tests.benchmarks import evaluator as ev, round_seal as rs; import pathlib; e=ev.freeze_for(2); assert ev.evaluation_code_sha256(pathlib.Path('.'))==e['evaluation_code_sha256_at_T'], 'evaluator changed since T'; print('ok')"
python -m unittest discover -s tests -t .
git commit --allow-empty -m "C: Round 2 freeze before final evaluation (evaluation_code_sha256 == at_T)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- Failure (`tuning_failed: true`): the worker already committed the log-only commit; add readiness status "Round 2 tuning failed" (AC-21), verify `.enc` sha unchanged and no plaintext (AC-18a-F), commit `F: Round 2 tuning failed` touching only readiness. Skip Tasks 14–15; go to Task 16.

---

### Task 14: **[controller + user]** Commit D — single evaluation

- [ ] **[user]** decrypt in their terminal: `cd ~/.atlassian_api_updater/sealed && openssl enc -d -aes-256-cbc -pbkdf2 -in round2-sealed.json.enc -out round2-sealed.json`.
- [ ] Controller checkpoint AC-18a-D (`.enc` sha unchanged), then plaintext sha must equal the seal:

```bash
python - <<'EOF'
import json, pathlib
from tests.benchmarks.evaluator import canonical_sha256
p = json.load(open(pathlib.Path.home()/".atlassian_api_updater/sealed/round2-sealed.json"))
b = json.load(open("tests/benchmarks/search_queries.json"))["round2_seal"]
assert canonical_sha256(p["held_out"]) == b["held_out_sha256"] and canonical_sha256(p["negative"]) == b["negative_sha256"]; print("seal ok")
EOF
python tests/diag_search_queries.py --round 2 --bench ~/.atlassian_api_updater/sealed/round2-sealed.json \
  --cache-dir ~/.atlassian_api_updater/round2-cache --json tests/benchmarks/round2-final.json
python tests/benchmarks/round_seal.py unseal --round 2 --plain ~/.atlassian_api_updater/sealed/round2-sealed.json --bench tests/benchmarks/search_queries.json
python -m unittest discover -s tests -t .
git add tests/benchmarks/search_queries.json tests/benchmarks/round2-final.json docs/phase3-readiness.md
git commit -m "D: Round 2 final evaluation (single run) and unseal

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Exactly one `diag` run with `--bench`. Gate: held_out ≥ 15/16 and negative 0/8.

---

### Task 15: **[controller]** Readiness Round 2 section and attestation

Append to `docs/phase3-readiness.md` (after the Round 2 pre-work subsection, never inside the Round 1 section) a `## Search Quality Round 2 — decision record (2026-10-0X)` section with: `housekeeping_commit`, S fingerprint + spec shas, verb-report decisions, method-safety result, lexicon prompt/raw/review shas + counts, candidates count, R5/R6 counts, T/B/(C/D | F) shas, generation prompt/result shas + re-request count + reviewer shas + `temporary_chat_unpersonalized: true`, `.enc` sha at B/at terminal, worker brief sha + run count + output shas, tuning log summary, result row (or failure row), the state model table with `null`/`not_applicable` on the failure branch, and the attestation list of spec §12. Commit as part of D (or F).

---

### Task 16: **[controller]** Final review and finishing

- Dispatch the whole-branch code reviewer (most capable model) over `95b8de0..HEAD`; one fix dispatch max (post-terminal fixes may touch only test code outside `TOOLING_FILES`, docs, and memory notes — anything else means the round's provenance is broken and must be reported, not patched).
- Update memory: `search-quality-round1-status.md` → add the Round 2 outcome; MEMORY.md index.
- Use `superpowers:finishing-a-development-branch` (the user chooses merge/push).

## Self-review notes

- Spec coverage: §4 files → Tasks 2–5, 10; §5.1 (H, S, order) → Tasks 1–8; §5.2 → Tasks 8–10; §5.3 → Tasks 9, 11; §5.4 → Task 11; §5.5/§7.2 → Task 6, 12; §5.6 → Task 12 (predefined replies only); §5.7 → Tasks 13–14; §6 → Task 8 (+ parity test in Task 10); §7.0 → Tasks 5, 9; §7.1 → Task 4; §8 → Tasks 1–3, 7; §10 → each task's tests; §11 → Task 15; §12 AC-01a/b/c (git, Tasks 10–14), AC-02/03 (Task 14), AC-04 (seal checkpoint, Task 2), AC-05 (Task 3 tooling hash + git), AC-06a/b (existing seed test + log), AC-07, AC-08 (Task 3), AC-09 (Task 3 invariants), AC-10/11 (Task 14), AC-12 (Task 6 validator test), AC-13 (Task 3/4 provenance), AC-14 (Task 2), AC-15a/b, AC-20a/b (Task 6 log test), AC-16, AC-17 (Task 1), AC-18a/b (Tasks 11, 13, 14), AC-19 (Tasks 3, 6, 12), AC-21 (Task 13).
- Known simplification (controller ruling): the spec's optional `--from-baseline` restore is not implemented; a dirty round state is refused and restored by `git checkout <B> -- <files>` manually (spec §5.5.6 allows "거부(기본)").
- The §6 spec-parity test is added at T (Task 10) rather than in H because the inventory is finalized only after method-safety; test code under `tests/intelligence/test_search.py` is not in `TOOLING_FILES`, so this is allowed.
