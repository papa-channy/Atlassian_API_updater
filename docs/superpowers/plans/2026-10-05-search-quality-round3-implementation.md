# Search Quality Round 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the four structural causes of the Round 2 tuning failure with two baseline-0 grid constants, a relaxed alias-target rule and a budget-2 atomic-action proposer; make the product abstain on verb-less queries and the evaluator require that symmetry; then repeat the sealed procedure against a **new** hidden set and measure the Discovery gate exactly once.

**Architecture:** The scorer (`search.py`) gains two constants (`method_order_bonus`, `path_coverage_bonus`, both baseline 0 so the Round 2 ranking is reproduced bit-for-bit, AC-R3-02) and an abstention contract in the response (`method_intent_consistent`, `intent_methods`, `actionable`, `recommended_operation`). `policy.py` changes only in four declared ways. All Round 3 tooling (`evaluator.py` symmetric judgement + raw/effective, `round_seal.py` actionability rules + section-replacement state machine + Round 3 freeze keys, `alias_candidates_tool.py` resource-vocabulary target rule, `tune_search_ranking.py` memoized grid evaluator + atomic-action proposer + `tuning_accept`, `regression_reference.py`, `round3_simulation.py`, diag) is completed in the housekeeping commits H1..H8 and frozen by hash at T. Controller tasks then run S → inventory (prefix-invariant suffix only) → lexicon re-gate from the Round 2 archive → candidates → **binding pre-T checkpoint** → T → stateless hidden generation/review → B → frozen worker brief → C/D | F | X, with the Round 2 sealed set decrypted at D only after the gate-result checkpoint, as a reference observation.

**Tech Stack:** Python ≥ 3.10 stdlib only under `tools/`; `unittest`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-05-search-quality-round3-design.md` **v1.16** (v1.12 passed 12 external reviews with "구현 계획으로 진행 가능"; v1.13 = the plan-stage corrections listed in its §14, made while writing this plan — grid count 23,328 and measured runtime, memoized grid evaluator, ranking structure committed at H, `verb_method_order`, seed = raw top-1, AC-R3-02 "full" = `MAX_LIMIT`, direct-alias proposer, pre-freeze structure-hash window; v1.14–v1.16 = plan review 1–3 corrections). The spec v1.16 is binding; this plan is its argument. Round 2 spec v1.14 is inherited where the Round 3 spec v1.16 is silent.

**Plan version:** v4 (2026-10-05; after external plan reviews 1–3, see Plan revision notes).

## Global Constraints

- Canonical test command: `python -m unittest discover -s tests -t .` (**476 OK** at `93bf458`, Python 3.11.15; omitting `-t .` makes `tests/mcp` shadow the SDK and gives spurious ImportErrors). `canonical_full_suite_pass := exit code 0 of exactly this command`; the controller ledgers the command string and the sha256 of its output at every checkpoint; a timeout or infrastructure error is recorded as `not pass` (never as pass).
- `round3_start_commit := e16c073` (main after the Round 2 merge). Spec/plan docs commits after it (`9683dc8..93bf458`) touch only `docs/`. AC-01a: `e16c073 < housekeeping_commit < T < B`.
- **Byte-invariant from now to the terminal commit** (spec §2 "불변", AC-09): Round 1·2 logs (`tests/benchmarks/search-tuning-round1.jsonl`, `search-tuning-round2.jsonl`), the round 1 and round 2 entries of `tests/benchmarks/round_freeze.json`, `tests/benchmarks/round1-final.json`, every `tests/benchmarks/round2-*` file (`round2-worker-brief.md`, `round2-hidden-generation-prompt.md`, `round2-hidden-reviewer-prompt.md`, `round2-lexicon-generation-prompt.md`, `round2-lexicon-review-prompt.md`, `round2-method-safety.json`), the `round1_seal`/`round2_seal` objects and the 29 r0 fixture records inside `tests/benchmarks/search_queries.json`, the Round 1 and Round 2 sections of `docs/phase3-readiness.md` (from `## Search Quality Round 1 — decision record` to the end of the file as of `93bf458`), `tests/fixtures/**`, every Phase 1 file, and every Phase 2 core module except `tools/atlassian_docs/intelligence/search.py`, `tools/atlassian_docs/intelligence/policy.py`, `tools/atlassian_docs/intelligence/data/search_ranking.json`, `search_aliases.json`, `alias_candidates.json`, `concept_lexicon.json`, `tools/atlassian_docs/mcp/server.py` (tool description text only).
- **Constrained changes** (spec §2): `verb_methods` row set identical to Round 2 and each Round 2 list an exact prefix of the Round 3 list (AC-R3-12); suffixes only at T, sorted. Between H1 and T the structure check is two invariants (spec §8 v1.14): non-verb structure sha == `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[3]` and the prefix invariant on `verb_methods`. `search_ranking.json` structure (8 constant keys with the two new baselines 0, the final grid, `method_mismatch_penalty` grid `[0,1,2,3,4,5]`, `version: 2`) is committed at **H1** and frozen at T; after T the structure never changes; B..C changes only the selected constant values and `origin=round3` aliases. `policy.py` changes only in H and only in the four declared kinds (CONSTANT_KEYS +2, origins — already general, `POLICY_VERSIONS["search"]` 3→4, `RankingPolicy.verb_method_order`).
- `TOOLING_FILES` (Task 3) are immutable from `housekeeping_commit` to the terminal commit (D, F or X). A pre-T tooling defect is fixed as H′ and the affected pre-T artifacts are regenerated in dependency order.
- Commit naming: Tasks 1–8 produce development commits H1..H8 on branch `round3` in `.worktrees/round3`; **`housekeeping_commit` = H8** (or the last H′). Commit order: H1..H8 → S → inventory → lexicon → candidates → pre-T checkpoint → T → generation/review (stateless) → seal metadata → **user encrypts + plaintext deleted + scan `[]`** → B → tuning (frozen brief) → (C → D | F | X). **terminal commit := D | F | X**.
- **Session separation (AC-R3-08):** the session that wrote the Round 3 spec and this plan (`5edca2ca…`, 2026-10-02..05) saw the Round 2 hidden plaintext. It may implement Tasks 1–8 (tooling) but **must not** act as Round 3 generator, reviewer, tuning worker or D controller. Tasks 9–17 are run by a fresh controller session; the tuning worker is a fresh subagent; the D gate controller is a fresh actor that did not touch tuning; the Round 2 reference set is opened only by the D controller after the gate checkpoint, and that actor is then `reference-aware`. Every actor's ids are ledgered: `actor_id` := the immutable chat/agent identifier (Temporary chat URL id; subagent agent id), `session_id` := the orchestration session identifier (the Claude Code session uuid for controller/worker steps; the canonical sentinel `not_available` where none exists — never an invented string). Three machine-checked separation events (spec §5 v1.15): `actor_separation_check_B` (`generator_actor_id != reviewer_actor_id`, before B), `actor_separation_check_worker` (`worker_actor_id ∉ {generator, reviewer}`, after the worker's Phase 0 handshake and before `run the brief procedure`, Task 13), `actor_separation_check_D` (`D_controller_actor_id ∉ {controller, generator, reviewer, worker}`, before the D evaluation, Task 15). Plaintext scans never retain the queries: the controller writes a hashed n-gram **needle manifest** before encryption and every later scan (`round_seal.py scan`) compares normalized word n-grams against it with an explicit allow list; the verdict is `unexpected_hits == []` (spec §5 v1.16).
- Sealed plaintext path `~/.atlassian_api_updater/sealed/round3-sealed.json` is never given to an implementer or a tuning worker. The plaintext is encrypted and deleted **before** commit B, so at B and after only `round3-sealed.json.enc` exists; no agent knows the passphrase. **AC-18b(R3):** any review input that embeds the hidden records (`hidden-review-input.txt`, replacement outputs, replacement-review messages) is written under `~/.atlassian_api_updater/round3-work/plain/` and that directory is deleted before commit B; only sha256 values survive in the ledgers. The B-time scan of `~/.atlassian_api_updater/` for record plaintext is ledgered.
- Source snapshot S: `~/.atlassian_api_updater/round3-cache/` (`$ATLASSIAN_DOCS_ROUND3_CACHE`), created once after H (Task 9): a copy of the archived Round 2 S iff its registry fingerprint `f3c2e9d48aa85c96ca62cdd84ff700cc2714c888cf4148b3a91c604c45b47b62` **and** all three spec shas (`confluence b3d010b6…`, `jira-platform 3d0edfb0…`, `jira-software cb7e24b3…`) equal a fresh live fetch; otherwise the fresh fetch. Every catalog-dependent step reads only S.
- Round 2 archive (read-only inputs): `~/.atlassian_api_updater/archive/round2/round2-cache/` (S2), `round2-work/lexicon_raw.json` (sha `acc5cebeafc5c48236a9de5d685b888fb2a83532340405556d77b801468a6872`), `round2-work/lexicon_review.json` (`c5ba256f8acd082febe06724d6646bff631e136dc437f4fa1528286117bd62f4`), `round2-work/lexicon-generation-input.txt`, `round2-work/lexicon-review-input.txt`, `sealed/round2-sealed.json.enc` (`c1a3794b0ac7563bee0ccdcc61e0ecb43026d0f778ec4773ef2695459cca369b`; held_out `0f990f2fc134cd41eca2061931c65cfdd4bc21819051f9ae8538c0258aaf3540`, negative `7750a2020923bcf8ddfa22e79f2c071001db9942194c3215cc03c60f363dde76`). Round 2 reference commit for AC-R3-02: `29dba38` (T; the B/F policy files equal T's).
- `POLICY_VERSIONS["search"]` becomes 4 in H1 and never changes again this round. `search_aliases.json` changes only at T (lexicon-r3 merge) and inside the tuning run (round3 entries). `constants` change only inside the tuning run.
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Chunked writes: no single tool call larger than ~60 lines. Never call real Jira/Confluence APIs; never print credential header values.
- After commit B the working tree must be clean when the worker starts. Controller evidence accumulates in `~/.atlassian_api_updater/round3-work/controller-events.jsonl` and `attempts.jsonl` (outside the repo) and is rendered into `docs/phase3-readiness.md` only in the terminal commit.
- Branch-aware test ACs: the suite must be green at T and B (AC-23), on the success and tuning-failure branches after tuning (AC-07/14/16); the abort branch preserves the failing test names/output as AC-22 evidence.
- **Measured grid runtime (spec §11):** Apple M3 Pro, Python 3.11.15, archived S2 (943 ops), B aliases: production path 0.2007 s/point (40 random points) → 23,328 points ≈ 78 min; memoized grid evaluator 0.0454 s/point (20 points, 0 ranking mismatches) → ≈ 17.6 min. **Final grid: both new bonuses `[0, 0.5, 1.0]`, no reduction**; the worker brief states the expected wall-clock.

## Review Focus

1. A held_out record whose verbs have a non-empty method intersection but whose expected operation's method lies outside it must be rejected by the `actionable` rule, not accepted (Task 6 `test_actionable_rule_three_branches`).
2. A query whose first verb's preferred method is outside the multi-verb intersection must receive `method_order` value 0 even though `method_intent` matches (Task 2 `test_method_order_first_verb_preferred_outside_intersection_is_zero`).
3. The memoized grid evaluator must rank every bench query identically to `search_operations` at random grid points, including deprecated operations and the zero-clamp (Task 7 `test_grid_evaluator_matches_search_operations`).
4. A `search_fn` returning a bare list must evaluate exactly as in Round 1 (`actionable=True`), so Round 1 artifacts and tests stay byte-invariant (Task 3 `test_legacy_search_fn_is_actionable_true`).
5. A `verb_methods` row that is reordered or truncated versus Round 2 must fail the prefix invariant even when the set of methods is equal (Task 5 `test_verb_prefix_invariant_rejects_reorder_and_truncation`).

---

### Task 1: `policy.py` four declared changes + `search_ranking.json` v2 structure + structure-hash window (commit H1)

**Files:**
- Modify: `tools/atlassian_docs/intelligence/policy.py:14` (`POLICY_VERSIONS`), `:165-167` (`CONSTANT_KEYS`), `:177-186` (`RankingPolicy`), `load_ranking` return
- Modify: `tools/atlassian_docs/intelligence/data/search_ranking.json` (`version`, `tuning_grid`, `baseline`, `constants` only; `verb_methods`, `path_noise`, `product_hints` byte-identical)
- Modify: `tests/benchmarks/evaluator.py` (add `PRE_FREEZE_NONVERB_STRUCTURE_SHA256`, `NONVERB_STRUCTURE_KEYS`, `nonverb_structure_sha256`, `pending_round`, `round2_verb_inventory`, `verb_prefix_violations`, `structure_check_problems`, `tuning_grid_sha256`)
- Test: `tests/intelligence/test_policy.py`, `tests/benchmarks/test_evaluator.py:125-157`, `tests/intelligence/test_search.py:264-269` (`versions.search == 3` → 4), `tests/test_tune_search_ranking.py:27-30` (grid cardinality)

**Interfaces:**
- Produces: `policy.CONSTANT_KEYS == ("method_match_bonus", "method_mismatch_penalty", "path_unmatched_penalty", "path_unmatched_cap", "product_hint_bonus", "resource_match_bonus", "method_order_bonus", "path_coverage_bonus")`; `policy.POLICY_VERSIONS["search"] == 4`; `RankingPolicy.verb_method_order: Mapping[str, tuple]` (file order, same keys as `verb_methods`); `ev.tuning_grid_sha256(raw) -> str` (= `canonical_sha256(raw["tuning_grid"])`); `ev.pending_round() -> int | None`; `ev.nonverb_structure_sha256(raw)`; `ev.round2_verb_inventory() -> dict` (the Round 2 spec §6 block; stdlib parse); `ev.verb_prefix_violations(base, live) -> list[str]`; `ev.structure_check_problems(raw) -> list[str]` (spec §8 v1.14: while Round 3 is pending, non-verb structure == H1 constant AND verb prefix invariant; after T, full `structure_sha256` == the Round 3 freeze).

- [ ] **Step 1: Write the failing tests**

In `tests/intelligence/test_policy.py`, replace the two assertions in `TestRankingPolicy.test_bundled_loads_and_hashes` that read `self.assertEqual(len(policy.CONSTANT_KEYS), 6); self.assertEqual(policy.CONSTANT_KEYS[-1], "resource_match_bonus")` and `self.assertEqual(rp.structure_sha256, ev.current_round()["structure_sha256"])` with:

```python
        self.assertEqual(policy.CONSTANT_KEYS, ("method_match_bonus", "method_mismatch_penalty", "path_unmatched_penalty", "path_unmatched_cap",
                                                "product_hint_bonus", "resource_match_bonus", "method_order_bonus", "path_coverage_bonus"))
        self.assertEqual(ev.structure_check_problems(self._raw()), [])                                  # Round 3: H1 non-verb structure + verb prefix until T refreezes
        self.assertEqual(rp.verb_method_order["change"], ("PUT", "POST")); self.assertEqual(rp.verb_method_order["leave"], ("POST", "DELETE"))
        self.assertEqual(set(rp.verb_method_order), set(rp.verb_methods))
        for v, order in rp.verb_method_order.items():
            self.assertEqual(frozenset(order), rp.verb_methods[v], v)
        self.assertEqual(rp.constants["method_order_bonus"], 0.0); self.assertEqual(rp.baseline["path_coverage_bonus"], 0.0)
        self.assertEqual(rp.tuning_grid["method_mismatch_penalty"], (0.0, 1.0, 2.0, 3.0, 4.0, 5.0))
        self.assertEqual(rp.tuning_grid["method_order_bonus"], (0.0, 0.5, 1.0)); self.assertEqual(rp.tuning_grid["path_coverage_bonus"], (0.0, 0.5, 1.0))
        self.assertEqual(rp.version, 2)
```

In `TestFingerprintIncludesRanking.test_versions_and_block` change `3` to `4`. Add to `TestRankingPolicy`:

```python
    def test_verb_method_order_preserves_file_order_and_is_immutable(self):
        raw = self._raw()
        raw["verb_methods"]["zzverb"] = ["DELETE", "GET", "POST"]
        rp = self._from(raw)
        self.assertEqual(rp.verb_method_order["zzverb"], ("DELETE", "GET", "POST"))
        with self.assertRaises(TypeError):
            rp.verb_method_order["zzverb"] = ()

    def test_round3_policy_diff_is_limited_to_declared_kinds(self):
        """AC-R3-13a: policy.py at HEAD differs from e16c073 only in POLICY_VERSIONS, CONSTANT_KEYS, the verb_method_order
        field and its construction (the origin regex was already general)."""
        import subprocess, pathlib
        root = pathlib.Path(__file__).resolve().parents[2]
        diff = subprocess.run(["git", "diff", "e16c073", "--", "tools/atlassian_docs/intelligence/policy.py"], cwd=root, capture_output=True, text=True).stdout
        changed = [l[1:] for l in diff.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        allowed = ("POLICY_VERSIONS", "CONSTANT_KEYS", "verb_method_order", "resource_match_bonus", "order = {}", "order[k]", "MappingProxyType(order)",
                   "method_order_bonus", "path_coverage_bonus")
        for l in changed:
            self.assertTrue(any(tok in l for tok in allowed) or not l.strip(), f"undeclared policy.py change: {l!r}")
```

In `tests/intelligence/test_search.py:268` change `["versions"]["search"], 3` to `4`. In `tests/test_tune_search_ranking.py:27-30` change both `1728` to `23328` and extend `GRID`/`BASE` at the top of the file with `"method_order_bonus": [0.0, 0.5, 1.0], "path_coverage_bonus": [0.0, 0.5, 1.0]` and `"method_order_bonus": 0.0, "path_coverage_bonus": 0.0` (the `GRID` for the selector tests keeps `method_mismatch_penalty: [0.0, 1.0, 2.0, 3.0]`; cardinality there becomes 1728 × 9 = 15552 — update `test_grid_cardinality_and_order` to `self.assertEqual(len(pts), 15552)` for `GRID` and `23328` for the loaded grid).

In `tests/benchmarks/test_evaluator.py` replace `RANKING_STRUCTURE_SHA256 = ev.current_round()["structure_sha256"]` (line 114) and `test_structure_hash_matches_commit_t` with:

```python
    def test_structure_hash_matches_commit_t_or_pre_freeze_window(self):
        """Round 3 (spec §8 v1.14): between H1 and T the NON-VERB structure equals the H1 constant and verb_methods satisfies the
        Round 2 prefix invariant (suffixes may be added before T); from T the full structure equals the Round 3 freeze."""
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(ev.structure_check_problems(raw), [])
        if ev.current_round()["round"] >= 3:
            self.assertIsNone(ev.pending_round()); self.assertEqual(ranking_structure_sha256(raw), ev.freeze_for(3)["structure_sha256"])
        else:
            self.assertEqual(ev.pending_round(), 3); self.assertEqual(raw["version"], 2)
            self.assertEqual(ev.nonverb_structure_sha256(raw), ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256[3])
            suffixed = json.loads(json.dumps(raw)); suffixed["verb_methods"]["get"] = ["GET", "POST"]            # a T-style suffix is allowed before T
            self.assertEqual(ev.structure_check_problems(suffixed), [])
            reordered = json.loads(json.dumps(raw)); reordered["verb_methods"]["change"] = ["POST", "PUT"]
            self.assertTrue(ev.structure_check_problems(reordered))
            moved = json.loads(json.dumps(raw)); moved["path_noise"] = moved["path_noise"] + ["zz"]
            self.assertTrue(ev.structure_check_problems(moved))

    def test_tuning_grid_sha256_helper(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(ev.tuning_grid_sha256(raw), ev.canonical_sha256(raw["tuning_grid"]))
        other = json.loads(json.dumps(raw)); other["constants"]["method_match_bonus"] = 1.0
        self.assertEqual(ev.tuning_grid_sha256(other), ev.tuning_grid_sha256(raw))        # constants do not change the grid hash
```

and in `test_constants_inside_grid` nothing changes.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.intelligence.test_policy tests.benchmarks.test_evaluator -v 2>&1 | tail -20`
Expected: FAIL (`CONSTANT_KEYS` tuple mismatch, `verb_method_order` AttributeError, `structure_check_problems` AttributeError).

- [ ] **Step 3: Implement `policy.py`**

Line 14: `POLICY_VERSIONS = {"search": 4, "quirks": 1, "oas_transpiler": 1}`.

Lines 165–167:

```python
CONSTANT_KEYS = ("method_match_bonus", "method_mismatch_penalty", "path_unmatched_penalty", "path_unmatched_cap", "product_hint_bonus",
                 "resource_match_bonus", "method_order_bonus", "path_coverage_bonus")
```

`RankingPolicy` gains a last field `verb_method_order: Mapping[str, tuple] = MappingProxyType({})`. In `load_ranking`, next to `verbs = {}` add `order = {}`; inside the loop after `verbs[k] = frozenset(v)` add `order[k] = tuple(v)`; and the return becomes:

```python
    return RankingPolicy(raw["version"], MappingProxyType(verbs), frozenset(noise), MappingProxyType(hints),
                         MappingProxyType(out_grid), MappingProxyType(out_base), MappingProxyType(out_consts),
                         canonical_sha256(raw), canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS}), MappingProxyType(order))
```

Nothing else in `policy.py` changes (AC-R3-13a).

- [ ] **Step 4: Rewrite the three tables of `search_ranking.json` (keep `verb_methods`, `path_noise`, `product_hints` byte-identical)**

```json
  "tuning_grid": {
    "method_match_bonus": [1.0, 2.0, 3.0], "method_mismatch_penalty": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
    "path_unmatched_penalty": [0.5, 1.0, 1.5, 2.0], "path_unmatched_cap": [2, 3, 4],
    "product_hint_bonus": [2.0, 3.0, 4.0],
    "resource_match_bonus": [6.0, 8.0, 10.0, 12.0],
    "method_order_bonus": [0.0, 0.5, 1.0], "path_coverage_bonus": [0.0, 0.5, 1.0]
  },
  "baseline": {
    "method_match_bonus": 2.0, "method_mismatch_penalty": 2.0,
    "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0,
    "resource_match_bonus": 10.0,
    "method_order_bonus": 0.0, "path_coverage_bonus": 0.0
  },
  "constants": {
    "method_match_bonus": 2.0, "method_mismatch_penalty": 2.0,
    "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0,
    "resource_match_bonus": 10.0,
    "method_order_bonus": 0.0, "path_coverage_bonus": 0.0
  }
```

and `"version": 2` on line 2. The `constants` object layout (four lines) is what `tune.write_constants` rewrites in Task 7 (rows `K[:2]`, `K[2:5]`, `K[5:6]`, `K[6:]`).

- [ ] **Step 5: Evaluator helpers (append to `tests/benchmarks/evaluator.py` after `freeze_for`)**

```python
PRE_FREEZE_NONVERB_STRUCTURE_SHA256 = {3: "<canonical sha of {k: raw[k] for k in NONVERB_STRUCTURE_KEYS} after Step 4 — computed by the command below>"}
NONVERB_STRUCTURE_KEYS = tuple(k for k in STRUCTURE_KEYS if k != "verb_methods")
ROUND2_SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-10-02-search-quality-round2-design.md"


def tuning_grid_sha256(raw: dict) -> str:
    """spec AC-R3-13b: sha256(canonical_json(search_ranking.json["tuning_grid"])); freeze, tests and readiness share it."""
    return canonical_sha256(raw["tuning_grid"])


def nonverb_structure_sha256(raw: dict) -> str:
    return canonical_sha256({k: raw[k] for k in NONVERB_STRUCTURE_KEYS})


def pending_round(freeze=None):
    """The round whose H structure/tooling is committed but whose freeze entry (commit T) does not exist yet, or None.
    While a round is pending, the previous round's freeze entry is history: its file hashes are no longer compared with the
    live tree (the tooling and the ranking structure legitimately changed at H)."""
    cur = current_round(freeze)["round"]
    return next((r for r in sorted(PRE_FREEZE_NONVERB_STRUCTURE_SHA256) if r > cur), None)


def round2_verb_inventory() -> dict:
    """The frozen Round 2 inventory: the JSON block under '## 6.' of the Round 2 spec (verb_inventory_sha256 d66317db…)."""
    lines = ROUND2_SPEC.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("## 6."))
    fence = next(i for i in range(start, len(lines)) if lines[i].startswith("```json"))
    end = next(i for i in range(fence + 1, len(lines)) if lines[i].startswith("```"))
    return json.loads("{" + "\n".join(lines[fence + 1:end]) + "}")["verb_methods"]


def verb_prefix_violations(base: dict, live: dict) -> list:
    """AC-R3-12: same row set; each base list is an exact prefix of the live list; the appended suffix is sorted, no duplicates."""
    out = [f"verb {v!r} removed" for v in base if v not in live] + [f"verb {v!r} added" for v in live if v not in base]
    for v, methods in base.items():
        cur = list(live.get(v) or [])
        if not cur:
            continue
        if cur[:len(methods)] != list(methods):
            out.append(f"verb {v!r}: Round 2 list {list(methods)} is not an exact prefix of {cur}")
            continue
        suffix = cur[len(methods):]
        if suffix != sorted(suffix):
            out.append(f"verb {v!r}: suffix {suffix} is not sorted")
        if len(set(cur)) != len(cur):
            out.append(f"verb {v!r}: duplicate methods in {cur}")
    return out


def structure_check_problems(raw: dict, freeze=None) -> list:
    """spec §8 (v1.14). Pending round N (H committed, no T yet): the non-verb structure must equal PRE_FREEZE_NONVERB_STRUCTURE_SHA256[N]
    and verb_methods must satisfy the Round 2 prefix invariant (T may append sorted suffixes). Otherwise the full structure hash
    must equal the current round's freeze."""
    p = pending_round(freeze)
    if p is None:
        want, got = current_round(freeze)["structure_sha256"], canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS})
        return [] if got == want else [f"structure_sha256 {got} != current freeze {want}"]
    out = [] if nonverb_structure_sha256(raw) == PRE_FREEZE_NONVERB_STRUCTURE_SHA256[p] else ["non-verb ranking structure differs from the H1 constant"]
    return out + verb_prefix_violations(round2_verb_inventory(), raw["verb_methods"])
```

Fill the constant: `python -c "import json; from tests.benchmarks.evaluator import canonical_sha256 as c, STRUCTURE_KEYS as K; r=json.load(open('tools/atlassian_docs/intelligence/data/search_ranking.json')); print(c({k: r[k] for k in K if k != 'verb_methods'}))"`. (`round2_verb_inventory` lives in the stdlib-only evaluator so that the structure check needs no `tools/` import; Task 5 re-exports it.)

Guard the historical freeze comparison in `tests/benchmarks/test_evaluator.py::test_round2_freeze_hashes_match_files` (rename to `test_current_round_freeze_hashes_match_files`): after the existing `if e["round"] < 2:` guard add

```python
        if ev.pending_round() is not None:
            print(f"round {ev.pending_round()} structure/tooling committed at H; freeze hashes checked after its commit T"); return
```

(at H1 `evaluator.py` itself changes, so `tooling_code_sha256`/`evaluation_code_sha256_at_T` of the round 2 entry can no longer equal the live tree; the round 2 entry is history, AC-08). Add the same two-line guard at the top of `tests/intelligence/test_search.py::TestRound2SpecParity.test_verb_inventory_matches_spec_section_6` is **not** needed (the inventory does not change at H), but Task 5 replaces that test with the prefix invariant.

- [ ] **Step 6: Run the full suite**

Run: `python -m unittest discover -s tests -t .`
Expected: OK. (`test_round2_freeze_hashes_match_files` still passes: the round 2 entry is compared only to the live files it names — brief/prompts/lexicon/candidates/aliases/tooling — none of which this task touches; `structure_sha256` of round 2 is not compared to the live file there.) If `tests/intelligence/test_search.py::TestScoringNumbers` fails because `raw["constants"]` in its `setUpClass` lacks the two new keys, add `"method_order_bonus": 0.0, "path_coverage_bonus": 0.0` to that dict (Task 2 rewrites the expectations anyway).

- [ ] **Step 7: Commit**

```bash
git add tools/atlassian_docs/intelligence/policy.py tools/atlassian_docs/intelligence/data/search_ranking.json tests/benchmarks/evaluator.py \
  tests/intelligence/test_policy.py tests/intelligence/test_search.py tests/benchmarks/test_evaluator.py tests/test_tune_search_ranking.py
git commit -m "H1: Round 3 ranking structure v2 (two baseline-0 constants, mismatch grid 0..5), POLICY_VERSIONS 4, verb_method_order, pre-freeze non-verb structure window + verb prefix invariant

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Scorer — `method_intent` helper, `method_order_bonus`, `path_coverage_bonus`, abstention payload, MCP/README text (commit H2)

**Files:**
- Modify: `tools/atlassian_docs/intelligence/search.py:214-238` (`_structural_signals`), `:269-274` (`_zero_signals`), `:286-333` (`search_operations`)
- Modify: `tools/atlassian_docs/mcp/server.py:35-38` (description string only)
- Modify: `README.md:181-188` (search section)
- Test: `tests/intelligence/test_search.py`, `tests/mcp/test_tools.py`

**Interfaces:**
- Produces: `search.method_intent(query_unigrams: tuple, verb_methods: Mapping[str, Collection[str]]) -> (verbs: list, allowed: frozenset | None)` — `verbs` = inventory tokens in query order; `allowed` = intersection of their methods (`None` when no verb; may be empty). `search._structural_signals(entry, query_unigrams, exp_all, rp, intent=None)` returns `(value, signals)` with signals keys `method_intent, path_unmatched, product_hint, resource_match, method_order, path_coverage`. `search_operations` payload gains `method_intent_consistent: bool`, `intent_methods: list[str]` (sorted, `[]` when None/empty), `actionable: bool` (== `method_intent_consistent`), `recommended_operation: str | None`.
- Consumes: `policy.RankingPolicy.verb_method_order` (Task 1).

- [ ] **Step 1: Write the failing tests**

In `tests/intelligence/test_search.py::TestScoringAlgorithm.test_signals_shape_and_exact_zero` extend the pinned-signals dict with `"method_order": {"value": 0.0, "verb": None, "preferred": None}, "path_coverage": {"value": 0.0, "matched": []}` and the key set with `"method_order", "path_coverage"`. In `TestScoringNumbers.setUpClass` add `"method_order_bonus": 0.0, "path_coverage_bonus": 0.0` to `raw["constants"]`; in `test_list_widget_numbers` extend the expected `b` dict with `"method_order": {"value": 0.0, "verb": "list", "preferred": "GET"}, "path_coverage": {"value": 0.0, "matched": ["widget"]}` (scores unchanged: both constants are 0). Then add:

```python
class TestRound3Signals(unittest.TestCase):
    """spec §3.1-§3.3: method_order_bonus (first verb's preferred method, only inside the intersection), path_coverage_bonus
    (unique matched literal path origins), abstention payload."""
    def setUp(self):
        import tempfile, os
        raw = json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))
        raw["constants"].update({"method_order_bonus": 1.0, "path_coverage_bonus": 1.0})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(raw, fh)
        try:
            self.rp = policy.load_ranking(pathlib.Path(fh.name))
        finally:
            os.unlink(fh.name)

    def _entry(self, path, method="GET", source="jira-platform"):
        return search.IndexEntry(f"{source}:{method}:{path}", {f: frozenset() for f in search.FIELD_WEIGHTS},
                                 search.path_tokens_for(path, self.rp.path_noise), source, method, search.terminal_tokens_for(path))

    def _sig(self, entry, q):
        return search._structural_signals(entry, q, frozenset(q), self.rp)[1]

    def test_method_intent_helper(self):
        vm = self.rp.verb_methods
        self.assertEqual(search.method_intent(("issue", "status"), vm), ([], None))
        self.assertEqual(search.method_intent(("get", "issue"), vm), (["get"], frozenset({"GET"})))
        self.assertEqual(search.method_intent(("change", "add", "x"), vm), (["change", "add"], frozenset({"POST"})))
        self.assertEqual(search.method_intent(("get", "delete", "x"), vm), (["get", "delete"], frozenset()))
        self.assertEqual(search.method_intent(("get",), {"get": ["GET"]}), (["get"], frozenset({"GET"})))     # raw lists work too

    def test_method_order_first_verb_preferred_only(self):
        post = self._entry("/x", method="POST"); put = self._entry("/x", method="PUT")
        self.assertEqual(self._sig(post, ("add", "x"))["method_order"], {"value": 1.0, "verb": "add", "preferred": "POST"})
        self.assertEqual(self._sig(put, ("add", "x"))["method_order"]["value"], 0.0)                     # entry.method != preferred
        self.assertEqual(self._sig(put, ("change", "x"))["method_order"], {"value": 1.0, "verb": "change", "preferred": "PUT"})
        self.assertEqual(self._sig(post, ("change", "x"))["method_order"]["value"], 0.0)                  # POST allowed but not preferred
        self.assertEqual(self._sig(post, ("x",))["method_order"], {"value": 0.0, "verb": None, "preferred": None})

    def test_method_order_first_verb_preferred_outside_intersection_is_zero(self):                        # review focus 2
        post = self._entry("/x", method="POST")
        sig = self._sig(post, ("change", "add", "x"))                        # change -> (PUT, POST), add -> (POST): intersection {POST}
        self.assertEqual(sig["method_intent"]["value"], self.rp.constants["method_match_bonus"])            # intent matches POST
        self.assertEqual(sig["method_order"], {"value": 0.0, "verb": "change", "preferred": "PUT"})      # preferred PUT is outside
        self.assertEqual(self._sig(post, ("add", "change", "x"))["method_order"]["value"], 1.0)           # order matters
        self.assertEqual(self._sig(post, ("get", "delete", "x"))["method_order"]["value"], 0.0)           # empty intersection

    def test_path_coverage_counts_unique_matched_origins(self):
        e = self._entry("/rest/api/3/issue/{k}/properties")
        self.assertEqual(self._sig(e, ("get", "issue", "property"))["path_coverage"], {"value": 2.0, "matched": ["issue", "properties"]})
        self.assertEqual(self._sig(e, ("get", "issue"))["path_coverage"], {"value": 1.0, "matched": ["issue"]})
        self.assertEqual(self._sig(e, ("get", "rest", "api"))["path_coverage"], {"value": 0.0, "matched": []})   # noise never counts
        dup = self._entry("/issue/{id}/issue")
        self.assertEqual(self._sig(dup, ("issue",))["path_coverage"]["value"], 1.0)                              # origin once
        total, _ = search._structural_signals(e, ("get", "issue", "property"), frozenset({"get", "issue", "property"}), self.rp)
        self.assertEqual(total, self.rp.constants["method_match_bonus"] + 2.0)                                   # mi + coverage, nothing unmatched

    def test_abstention_payload_four_quadrants(self):
        state = make_state("jira-platform", "jira-software", "confluence")
        out = search.search_operations(state, "get issue by key")
        self.assertEqual((out["method_intent_consistent"], out["intent_methods"], out["actionable"]), (True, ["GET"], True))
        self.assertEqual(out["recommended_operation"], out["results"][0]["key"])
        out = search.search_operations(state, "issue status field values")                                  # no verb
        self.assertEqual((out["method_intent_consistent"], out["intent_methods"], out["actionable"]), (False, [], False))
        self.assertIsNone(out["recommended_operation"]); self.assertTrue(out["results"])                      # candidates only
        out = search.search_operations(state, "create and delete issue")                                    # conflicting verbs
        self.assertEqual((out["intent_methods"], out["actionable"], out["recommended_operation"]), ([], False, None))
        out = search.search_operations(state, "delete zzzqqq", method="POST")                               # actionable, no candidates
        self.assertEqual((out["actionable"], out["results"], out["recommended_operation"]), (True, [], None))

    def test_actionable_does_not_change_scores_or_order(self):                                             # AC-R3-03
        state = make_state("jira-platform", "jira-software", "confluence")
        for q in ("issue status field values", "get issue by key", "create and delete issue"):
            out = search.search_operations(state, q)
            rows = [(r["key"], r["score"], r["deprecated"]) for r in out["results"]]
            self.assertEqual(rows, sorted(rows, key=lambda t: (-t[1], t[2], t[0])), q)
            self.assertEqual(out["recommended_operation"], out["results"][0]["key"] if out["actionable"] and out["results"] else None)
```

In `tests/mcp/test_tools.py::TestRunTool` add:

```python
    def test_search_response_carries_abstention_contract(self):
        out = tools.run_tool(self.m, "search_operations", {"query": "upload attachment to issue"})
        self.assertTrue(out["actionable"]); self.assertEqual(out["recommended_operation"], out["results"][0]["key"])
        out = tools.run_tool(self.m, "search_operations", {"query": "issue status field values"})
        self.assertFalse(out["actionable"]); self.assertIsNone(out["recommended_operation"]); self.assertEqual(out["intent_methods"], [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.intelligence.test_search tests.mcp.test_tools 2>&1 | tail -5`
Expected: FAIL (`method_intent` missing, KeyError `method_order`, KeyError `actionable`).

- [ ] **Step 3: Implement `search.py`**

Insert before `_structural_signals`:

```python
def method_intent(query_unigrams, verb_methods):
    """spec §3.3 (shared with the hidden-set machine check): inventory verbs in query order and the intersection of their
    allowed methods — None when the query has no inventory verb, possibly empty (conflicting verbs)."""
    verbs = [t for t in query_unigrams if t in verb_methods]
    allowed = None
    for v in verbs:
        methods = frozenset(verb_methods[v])
        allowed = methods if allowed is None else (allowed & methods)
    return verbs, allowed
```

Replace `_structural_signals` with:

```python
def _structural_signals(entry, query_unigrams: tuple, exp_all: frozenset, rp, intent=None):
    """method intent + path specificity + product hint + terminal resource match (spec §6.3-§6.5b) + Round 3 method order and
    path coverage (Round 3 spec §3.1/§3.2); every number comes from rp. intent = method_intent(...) computed once per query."""
    c = rp.constants
    verbs, allowed = intent if intent is not None else method_intent(query_unigrams, rp.verb_methods)
    if not allowed:
        mi = {"value": 0.0, "allowed": []}
    elif entry.method in allowed:
        mi = {"value": c["method_match_bonus"], "allowed": sorted(allowed)}
    else:
        mi = {"value": 0.0 - c["method_mismatch_penalty"], "allowed": sorted(allowed)}   # 0.0 - x: never -0.0
    unmatched = sorted(pt.origin for pt in entry.path_tokens if not (pt.forms & exp_all))
    pu = {"value": 0.0 - min(len(unmatched), c["path_unmatched_cap"]) * c["path_unmatched_penalty"], "tokens": unmatched}
    hinted = set()
    for t in query_unigrams:
        hinted |= rp.product_hints.get(t, frozenset())
    ph = {"value": c["product_hint_bonus"] if entry.source in hinted else 0.0, "sources": sorted(hinted)}
    term = entry.terminal_tokens
    matched = bool(term) and all(token_forms(t) & exp_all for t in term)
    rm = {"value": c["resource_match_bonus"] if matched else 0.0, "tokens": list(term)}
    preferred = rp.verb_method_order[verbs[0]][0] if verbs else None                        # Round 2 prefix invariant: == Round 2's first
    order_hit = bool(allowed) and preferred in allowed and entry.method == preferred
    mo = {"value": c["method_order_bonus"] if order_hit else 0.0, "verb": verbs[0] if verbs else None, "preferred": preferred}
    covered = sorted({pt.origin for pt in entry.path_tokens if pt.forms & exp_all})
    pc = {"value": c["path_coverage_bonus"] * len(covered), "matched": covered}
    return mi["value"] + pu["value"] + ph["value"] + rm["value"] + mo["value"] + pc["value"], \
        {"method_intent": mi, "path_unmatched": pu, "product_hint": ph, "resource_match": rm, "method_order": mo, "path_coverage": pc}
```

`_zero_signals` gains `"method_order": {"value": 0.0, "verb": None, "preferred": None}, "path_coverage": {"value": 0.0, "matched": []}`.

In `search_operations`: after `unigrams = tokenize_unigrams(query)` add `intent = method_intent(unigrams, rp.verb_methods)`; pass `intent` to `_structural_signals(entry, unigrams, exp.all, rp, intent)`; after the `payload = {...}` literal add:

```python
    verbs, allowed = intent
    shown = payload["results"]
    payload["method_intent_consistent"] = bool(allowed)
    payload["intent_methods"] = sorted(allowed) if allowed else []
    payload["actionable"] = payload["method_intent_consistent"]              # spec §3.3: the product abstains without a clear intent
    payload["recommended_operation"] = shown[0]["key"] if payload["actionable"] and shown else None
```

(With both new constants at 0 every score is unchanged: `0.0 * len(covered)` and `0.0` add nothing; the sort key is untouched — AC-R3-02/AC-R3-03.)

- [ ] **Step 4: MCP description and README**

In `tools/atlassian_docs/mcp/server.py` append to the `search_operations` description, before `+ PROVENANCE_NOTE`: `"Round 3 abstention contract: the response carries method_intent_consistent, intent_methods, actionable and recommended_operation; when actionable is false the results are candidates only — do not treat results[0] as a recommendation. "`. In `README.md` after the `query_tokens`/`alias_tokens` bullet add:

```
- 응답은 **abstention 계약**(Round 3)을 담는다: `intent_methods`(질의 동사들의 허용 HTTP 메서드 교집합), `method_intent_consistent`,
  `actionable`(동사 의도가 명확할 때만 `true`), `recommended_operation`(`actionable`이고 결과가 있으면 `results[0].key`, 아니면 `null`).
  `actionable: false`이면 `results`는 후보 목록이며 소비자는 `results[0]`을 추천으로 해석해서는 안 된다. 점수·순서는 영향받지 않는다.
```

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests -t .`
Expected: OK (`test_seed_passes_on_fixtures` 23/23 · 6/6 unchanged since both constants are 0).

- [ ] **Step 6: Commit**

```bash
git add tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/mcp/server.py README.md tests/intelligence/test_search.py tests/mcp/test_tools.py
git commit -m "H2: scorer method_order/path_coverage signals (baseline 0), shared method_intent helper, abstention payload, MCP/README contract

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Evaluator — symmetric judgement with sections, legacy adapter, raw/effective, Round 3 freeze key set (commit H3)

**Files:**
- Modify: `tests/benchmarks/evaluator.py:9` (`NEGATIVE_SECTIONS`), `:55-70` (`evaluate`), `:85` (`STRUCTURE_KEYS` unchanged), `:146-160` (`round_freeze_hashes`), add `freeze_key_set`, `ROUND3_EXTRA_KEYS`, `ranked_and_actionable`
- Test: `tests/benchmarks/test_evaluator.py:116-140` (`ROUND2_HASH_KEYS`, `test_round_freeze_file_shape`), new `TestRound3SymmetricJudgement`, `TestRound3FreezeKeys`

**Interfaces:**
- Produces: `ev.ranked_and_actionable(search_fn, query) -> (list[str], bool)`; `ev.evaluate(records, search_fn, section=None)` — `section ∈ {None, "seed", "regression_negative", "held_out", "negative"}`; result keys `passed, failed, total` always; for `held_out`/`regression_negative`/`negative` also `raw_passed`, `effective_passed` (== `passed`), `actionable: {"total", "raw_passed"}`, `abstained: {"total", "effective_passed"}`; failure records gain `actionable`, `raw_ok` only when `section` is given. `ev.freeze_key_set(round) -> set`; `ev.ROUND3_EXTRA_KEYS = ("regression_reference_sha256", "reference_set", "hidden_generation_rules", "tuning_grid_sha256", "hidden_set_origin")`; `ev.round_freeze_hashes(round)` adds `regression_reference_sha256` (canonical sha of `tests/benchmarks/round{N}-regression-reference.json`) and `tuning_grid_sha256` for `round >= 3`.
- Consumes: `ev.tuning_grid_sha256`, `ev.pending_round` (Task 1).

- [ ] **Step 1: Write the failing tests**

In `tests/benchmarks/test_evaluator.py` replace `ROUND2_HASH_KEYS` and `test_round_freeze_file_shape` with:

```python
ROUND2_HASH_KEYS = {"structure_sha256", "verb_inventory_sha256", "concept_lexicon_sha256", "lexicon_aliases_sha256",
                    "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256",
                    "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T"}
SHA_KEYS_R3 = ROUND2_HASH_KEYS | {"regression_reference_sha256", "tuning_grid_sha256"}

    def test_round_freeze_file_shape(self):
        f = ev.load_round_freeze()
        self.assertIsInstance(f, list); self.assertEqual([e["round"] for e in f], list(range(1, len(f) + 1)))
        self.assertEqual(set(f[0]), {"round", "commit_T", "structure_sha256"})
        for e in f[1:]:
            self.assertEqual(set(e), ev.freeze_key_set(e["round"]), e["round"])
            self.assertNotIn("commit_T", e)                                                     # spec §9: T sha is not inside the T file
            for k in (SHA_KEYS_R3 if e["round"] >= 3 else ROUND2_HASH_KEYS) | {"source_registry_fingerprint"}:
                self.assertRegex(e[k], r"^[0-9a-f]{64}$", k)
            self.assertEqual(set(e["source_spec_sha256"]), {"jira-platform", "jira-software", "confluence"})
            if e["round"] >= 3:
                self.assertEqual(set(e["reference_set"]), {"origin", "enc_sha256", "held_out_sha256", "negative_sha256"})
                self.assertEqual(e["reference_set"]["origin"], "round2"); self.assertEqual(e["hidden_set_origin"], f"round{e['round']}")
                self.assertIsInstance(e["hidden_generation_rules"], list)
        self.assertEqual(ev.current_round(), f[-1]); self.assertEqual(ev.freeze_for(1), f[0])
```

Append:

```python
class TestRound3SymmetricJudgement(unittest.TestCase):
    """Round 3 spec §4 / §13: held_out requires actionable; negatives pass when abstained; seed is raw top-1; a legacy
    search_fn (ranked keys only) is read as actionable=True so Round 1/2 judgements never change."""
    def rec(self, i, q, exp, forb, origin):
        return {"id": i, "query": q, "expected_top1_any": exp, "forbidden_top1": forb, "origin": origin, "failure_classes": [], "ambiguous": False}

    def setUp(self):
        self.H = [self.rec("h-001", "get the ticket", ["A"], [], "held_out-r3"), self.rec("h-002", "ticket details", ["A"], [], "held_out-r3")]
        self.N = [self.rec("n-001", "ticket owner list", [], ["F"], "negative-r3"), self.rec("n-002", "get the owner", [], ["F"], "negative-r3")]
        self.table = {"get the ticket": (["A"], True), "ticket details": (["A"], False), "ticket owner list": (["F"], False), "get the owner": (["F"], True)}
        self.fn = lambda q: self.table[q]
        self.legacy = lambda q: self.table[q][0]

    def test_held_out_requires_actionable(self):
        res = ev.evaluate(self.H, self.fn, section="held_out")
        self.assertEqual((res["passed"], res["raw_passed"], res["effective_passed"]), (1, 2, 1))
        self.assertEqual([f["id"] for f in res["failed"]], ["h-002"]); self.assertEqual((res["failed"][0]["actionable"], res["failed"][0]["raw_ok"]), (False, True))
        self.assertEqual(res["actionable"], {"total": 1, "raw_passed": 1}); self.assertEqual(res["abstained"], {"total": 1, "effective_passed": 0})

    def test_negative_passes_when_abstained_fails_when_actionable(self):
        res = ev.evaluate(self.N, self.fn, section="negative")
        self.assertEqual((res["passed"], res["raw_passed"], res["effective_passed"]), (1, 0, 1))
        self.assertEqual([f["id"] for f in res["failed"]], ["n-002"])
        self.assertEqual(res["actionable"], {"total": 1, "raw_passed": 0}); self.assertEqual(res["abstained"], {"total": 1, "effective_passed": 1})
        same = ev.evaluate(self.N, self.fn, section="regression_negative")
        self.assertEqual((same["passed"], same["raw_passed"]), (1, 0))

    def test_seed_section_is_raw_top1(self):
        res = ev.evaluate(self.H, self.fn, section="seed")
        self.assertEqual((res["passed"], res["failed"]), (2, [])); self.assertNotIn("raw_passed", res)

    def test_legacy_search_fn_is_actionable_true(self):                                                 # review focus 4
        self.assertEqual(ev.ranked_and_actionable(self.legacy, "ticket details"), (["A"], True))
        self.assertEqual(ev.ranked_and_actionable(self.fn, "ticket details"), (["A"], False))
        self.assertEqual(ev.evaluate(self.H, self.legacy, section="held_out")["passed"], 2)
        self.assertEqual(ev.evaluate(self.N, self.legacy, section="negative")["passed"], 0)
        res = ev.evaluate(self.N, self.legacy)                                                           # Round 1 call form, no section
        self.assertEqual(res["passed"], 0); self.assertNotIn("raw_passed", res)
        self.assertEqual(set(res["failed"][0]), {"id", "query", "top1", "expected_top1_any", "forbidden_top1"})   # Round 1 failure shape


class TestRound3FreezeKeys(unittest.TestCase):
    def test_freeze_key_set_per_round(self):
        self.assertEqual(ev.freeze_key_set(1), {"round", "commit_T", "structure_sha256"})
        self.assertEqual(ev.freeze_key_set(2), ROUND2_HASH_KEYS | {"round", "source_registry_fingerprint", "source_spec_sha256"})
        self.assertEqual(ev.freeze_key_set(3), ev.freeze_key_set(2) | set(ev.ROUND3_EXTRA_KEYS))
        self.assertNotIn("commit_T", ev.freeze_key_set(3))
        self.assertEqual(ev.freeze_key_set(2), set(ev.freeze_for(2)))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.benchmarks.test_evaluator 2>&1 | tail -5`
Expected: FAIL (`freeze_key_set` missing; `evaluate()` rejects `section`; tuple-returning fn breaks `top1 in expected`).

- [ ] **Step 3: Implement**

Replace lines 9 and 55–70 of `evaluator.py`:

```python
NEGATIVE_SECTIONS = ("regression_negative", "negative")
ACTIONABLE_SECTIONS = ("held_out",)          # Round 3 spec §4 v1.13: only held_out requires actionable; seed/fixture positive are raw top-1


def ranked_and_actionable(search_fn, query):
    """Round 3 spec §4: search_fn returns (ranked_keys, actionable) or - the Round 1/2 call form - ranked_keys only, which the
    adapter reads as actionable=True (historical judgements never turn into abstentions)."""
    out = search_fn(query)
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], bool):
        return list(out[0]), out[1]
    return list(out), True


def evaluate(records, search_fn, section=None):
    """Symmetric judgement (Round 3 spec §4). held_out: top1 ∈ expected AND actionable. negatives: top1 ∉ forbidden OR abstained.
    Everything else (seed, fixtures, Round 1 callers with section=None): raw top-1 only."""
    if is_sealed(records):
        return {"sealed": True, "count": records.get("count")}
    failed, raw_passed, act_total, act_raw = [], 0, 0, 0
    for rec in records:
        expected = rec.get("expected_top1_any") or []
        forbidden = rec.get("forbidden_top1") or []
        if not expected and not forbidden:
            raise ValueError(f"benchmark record {rec.get('query')!r} must set expected_top1_any or forbidden_top1")
        ranked, actionable = ranked_and_actionable(search_fn, rec["query"])
        top1 = ranked[0] if ranked else None
        raw_ok = (not expected or top1 in expected) and (top1 not in forbidden)
        raw_passed += raw_ok
        if actionable:
            act_total += 1; act_raw += raw_ok
        if section in ACTIONABLE_SECTIONS:
            ok = raw_ok and actionable
        elif section in NEGATIVE_SECTIONS:
            ok = raw_ok or not actionable
        else:
            ok = raw_ok
        if not ok:
            f = {"id": rec.get("id"), "query": rec["query"], "top1": top1, "expected_top1_any": expected, "forbidden_top1": forbidden}
            if section is not None:
                f.update(actionable=actionable, raw_ok=raw_ok)
            failed.append(f)
    out = {"passed": len(records) - len(failed), "failed": failed, "total": len(records)}
    if section in ACTIONABLE_SECTIONS or section in NEGATIVE_SECTIONS:
        abstained = len(records) - act_total
        out.update(raw_passed=raw_passed, effective_passed=out["passed"], actionable={"total": act_total, "raw_passed": act_raw},
                   abstained={"total": abstained, "effective_passed": abstained if section in NEGATIVE_SECTIONS else 0})
    return out
```

After `freeze_for` add:

```python
ROUND3_EXTRA_KEYS = ("regression_reference_sha256", "reference_set", "hidden_generation_rules", "tuning_grid_sha256", "hidden_set_origin")
_ROUND2_KEYS = frozenset({"round", "structure_sha256", "verb_inventory_sha256", "source_registry_fingerprint", "source_spec_sha256",
                          "concept_lexicon_sha256", "lexicon_aliases_sha256", "alias_candidates_sha256", "worker_brief_sha256",
                          "hidden_generation_prompt_sha256", "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T"})


def freeze_key_set(round: int) -> set:
    """Canonical key set of a round_freeze.json entry (Round 3 spec §9): round 1 legacy; round 2 as frozen; round >= 3 adds
    ROUND3_EXTRA_KEYS. No entry after round 1 carries commit_T (self-reference)."""
    if round == 1:
        return {"round", "commit_T", "structure_sha256"}
    return set(_ROUND2_KEYS) | (set(ROUND3_EXTRA_KEYS) if round >= 3 else set())
```

In `round_freeze_hashes` add before the `return`:

```python
    if round >= 3:
        out = {...the existing dict...}
```

concretely: build the dict into a variable `out`, then `if round >= 3: out["regression_reference_sha256"] = j(f"tests/benchmarks/round{round}-regression-reference.json"); out["tuning_grid_sha256"] = tuning_grid_sha256(json.loads((root / DATA_REL / "search_ranking.json").read_text(encoding="utf-8")))`, then `return out`.

- [ ] **Step 4: Run the full suite**

Run: `python -m unittest discover -s tests -t .`
Expected: OK (every existing `evaluate(records, fn)` call keeps `section=None` semantics).

- [ ] **Step 5: Commit**

```bash
git add tests/benchmarks/evaluator.py tests/benchmarks/test_evaluator.py
git commit -m "H3: evaluator symmetric judgement per section, legacy actionable adapter, raw/effective counts, Round 3 freeze key set

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: AC-R3-02 regression reference — generator (isolated Round 2 checkout), verifier, pinned file (commit H4)

**Files:**
- Create: `tests/benchmarks/regression_reference.py`
- Create: `tests/benchmarks/round3-regression-reference.json` (generated inside the `29dba38` worktree against the archived S2)
- Create: `tests/benchmarks/test_regression_reference.py`
- Modify: `tests/benchmarks/evaluator.py:117-122` (`EVALUATION_CODE_FILES` += `tests/benchmarks/regression_reference.py`; `TOOLING_FILES` += `tests/benchmarks/test_regression_reference.py`), `tests/benchmarks/test_evaluator.py` (`EVAL_CODE_FILES` constant)

**Interfaces:**
- Produces: `regression_reference.verify_reference(reference: dict, cache_dir=None) -> list[str]` (empty = identical); CLI `generate --repo-root DIR --cache-dir S2 --bench FILE --out FILE`, `verify [--cache-dir S2] [--reference FILE]`. Reference document keys: `tool_version, reference_commit, search_py_sha256, ranking_sha256, aliases_sha256, registry_fingerprint, spec_sha256, query_set_sha256, limit, b_ranking, b_aliases, snapshot{query: {keys, scores, total_matches}}, fixture{...}`.
- Consumes: `search.search_operations`, `policy.load_ranking/load_aliases`, `tests.intelligence.helpers.make_state` (both trees).

- [ ] **Step 1: Write the failing test**

`tests/benchmarks/test_regression_reference.py`:

```python
"""AC-R3-02: the Round 3 scorer with the two new constants at 0, the B aliases and the B inventory reproduces the Round 2
scorer's whole ranked list (keys, scores, total_matches) on the pinned reference (snapshot S2 + fixture registry)."""
import json, os, pathlib, unittest
from tests.benchmarks import evaluator as ev
from tests.benchmarks import regression_reference as rr

REF = pathlib.Path(__file__).resolve().parent / "round3-regression-reference.json"
BENCH = pathlib.Path(__file__).resolve().parent / "search_queries.json"


class TestRegressionReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = json.loads(REF.read_text(encoding="utf-8"))

    def test_reference_provenance_is_the_round2_b_policy(self):
        r, e2 = self.ref, ev.freeze_for(2)
        self.assertEqual(r["reference_commit"], "29dba38"); self.assertEqual(r["tool_version"], rr.TOOL_VERSION); self.assertEqual(r["limit"], 50)
        self.assertEqual(r["aliases_sha256"], ev.canonical_sha256(r["b_aliases"])); self.assertEqual(r["ranking_sha256"], ev.canonical_sha256(r["b_ranking"]))
        self.assertEqual(ev.canonical_sha256(r["b_ranking"]["verb_methods"]), e2["verb_inventory_sha256"])
        self.assertEqual(r["registry_fingerprint"], e2["source_registry_fingerprint"]); self.assertEqual(r["spec_sha256"], e2["source_spec_sha256"])
        self.assertRegex(r["search_py_sha256"], r"^[0-9a-f]{64}$")
        bench = json.loads(BENCH.read_text(encoding="utf-8")); snap_q, fix_q = rr.query_sets(bench)
        self.assertEqual(r["query_set_sha256"], ev.canonical_sha256({"snapshot": snap_q, "fixture": fix_q}))
        self.assertEqual((len(r["snapshot"]), len(r["fixture"])), (53, 29))
        for block in (r["snapshot"], r["fixture"]):
            for q, row in block.items():
                self.assertEqual(set(row), {"keys", "scores", "total_matches"}); self.assertEqual(len(row["keys"]), len(row["scores"]))
                self.assertGreaterEqual(row["total_matches"], len(row["keys"]))

    def test_fixture_part_matches_current_scorer(self):
        self.assertEqual(rr.verify_reference(self.ref, cache_dir=None), [])

    def test_snapshot_part_matches_current_scorer_when_archive_present(self):
        cache = os.environ.get("ATLASSIAN_DOCS_ROUND2_CACHE") or str(pathlib.Path.home() / ".atlassian_api_updater" / "archive" / "round2" / "round2-cache")
        if not pathlib.Path(cache).is_dir():
            print("archived Round 2 snapshot not available: snapshot part of AC-R3-02 checked by the controller (ledger)"); return
        self.assertEqual(rr.verify_reference(self.ref, cache_dir=pathlib.Path(cache)), [])

    def test_round3_freeze_pins_the_reference(self):
        if ev.current_round()["round"] < 3:
            print("round 3 not frozen yet: regression_reference_sha256 checked after commit T"); return
        self.assertEqual(ev.freeze_for(3)["regression_reference_sha256"], ev.canonical_sha256(self.ref))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.benchmarks.test_regression_reference 2>&1 | tail -3`
Expected: FAIL/ERROR (module and reference file missing).

- [ ] **Step 3: Write `tests/benchmarks/regression_reference.py`**

```python
"""AC-R3-02 regression reference (Round 3 spec §3.5).

generate — run with --repo-root pointing at an ISOLATED checkout of the Round 2 reference commit (git worktree add /tmp/r2ref 29dba38):
  that root is put first on sys.path and any imported tools/tests modules are dropped, so the Round 2 scorer, its policy data and
  its fixtures do the scoring. Never generate from the Round 3 working tree.
    python tests/benchmarks/regression_reference.py generate --repo-root /tmp/r2ref \
        --cache-dir ~/.atlassian_api_updater/archive/round2/round2-cache --bench tests/benchmarks/search_queries.json \
        --out tests/benchmarks/round3-regression-reference.json
verify — run in the Round 3 tree: re-score the same queries with the CURRENT scorer under the pinned B policy (B aliases, B inventory,
  B constants + the two Round 3 constants at 0) and compare every ranked key, score and total_matches (limit 50 = search.MAX_LIMIT).
    python tests/benchmarks/regression_reference.py verify [--cache-dir S2] [--reference FILE]
"""
import argparse, hashlib, json, pathlib, shutil, subprocess, sys, tempfile
from unittest import mock

HERE = pathlib.Path(__file__).resolve()
DEFAULT_REF = HERE.parent / "round3-regression-reference.json"
SOURCES = ("jira-platform", "jira-software", "confluence")
LIMIT = 50                      # search.MAX_LIMIT: "the whole ranked list" is everything the API can return (spec §3.5 v1.13)
TOOL_VERSION = "round3.1"
NEW_CONSTANTS = {"method_order_bonus": 0.0, "path_coverage_bonus": 0.0}


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def query_sets(bench) -> tuple:
    """(snapshot queries: seed + regression_negative in file order; fixture queries: their r0 subset)."""
    recs = bench["seed"] + bench["regression_negative"]
    return [r["query"] for r in recs], [r["query"] for r in recs if r["origin"].endswith("-r0")]


def score_all(state, queries, search_operations) -> dict:
    out = {}
    for q in queries:
        res = search_operations(state, q, limit=LIMIT)
        rows = res.get("results", [])
        out[q] = {"keys": [r["key"] for r in rows], "scores": [r["score"] for r in rows], "total_matches": res.get("total_matches", 0)}
    return out


def _state_from_cache(cache_dir):
    """Registry over a temporary copy of the snapshot (the snapshot is never written); returns (state, cleanup)."""
    from tools.atlassian_docs import storage, sync
    from tools.atlassian_docs.intelligence import RegistryManager
    td = tempfile.mkdtemp(prefix="rr-cache-")
    copy = pathlib.Path(td) / "cache"; shutil.copytree(cache_dir, copy)
    patcher = mock.patch.object(storage, "CACHE_DIR", copy); patcher.start()
    mgr = RegistryManager(sync_all=lambda force=False: [sync.SyncResult(s, "ok") for s in SOURCES]); mgr.start()

    def cleanup():
        patcher.stop(); shutil.rmtree(td, ignore_errors=True)
    return mgr.active, cleanup


def _bootstrap(repo_root: pathlib.Path) -> None:
    sys.path.insert(0, str(repo_root))
    for name in [m for m in sys.modules if m.split(".")[0] in ("tools", "tests")]:
        del sys.modules[name]


def generate(repo_root: pathlib.Path, cache_dir: pathlib.Path, bench_path: pathlib.Path) -> dict:
    _bootstrap(repo_root)
    from tools.atlassian_docs.intelligence import search as r2search, policy as r2policy
    from tests.intelligence.helpers import make_state
    bench = json.loads(bench_path.read_text(encoding="utf-8"))
    snap_q, fix_q = query_sets(bench)
    state, cleanup = _state_from_cache(cache_dir)
    try:
        snapshot = score_all(state, snap_q, r2search.search_operations)
        fp, spec_sha = state.registry.fingerprint, {n: p.active_spec_sha256 for n, p in sorted(state.provenance.items())}
    finally:
        cleanup()
    fixture = score_all(make_state(*SOURCES), fix_q, r2search.search_operations)
    data = repo_root / "tools" / "atlassian_docs" / "intelligence" / "data"
    b_ranking = json.loads((data / "search_ranking.json").read_text(encoding="utf-8"))
    b_aliases = json.loads((data / "search_aliases.json").read_text(encoding="utf-8"))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True).stdout.strip()
    return {"tool_version": TOOL_VERSION, "reference_commit": commit, "limit": LIMIT,
            "search_py_sha256": hashlib.sha256((repo_root / "tools/atlassian_docs/intelligence/search.py").read_bytes()).hexdigest(),
            "ranking_sha256": canonical_sha256(b_ranking), "aliases_sha256": canonical_sha256(b_aliases),
            "registry_fingerprint": fp, "spec_sha256": spec_sha, "query_set_sha256": canonical_sha256({"snapshot": snap_q, "fixture": fix_q}),
            "b_ranking": b_ranking, "b_aliases": b_aliases, "snapshot": snapshot, "fixture": fixture}


def _pinned_policies(reference, policy):
    """Round 3 loader + B content: B aliases verbatim; live structure with the B inventory, B constants and the two new constants at 0."""
    live = json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))
    ranking_raw = {**live, "verb_methods": reference["b_ranking"]["verb_methods"],
                   "constants": {**reference["b_ranking"]["constants"], **NEW_CONSTANTS}}
    with tempfile.TemporaryDirectory() as td:
        rp = pathlib.Path(td) / "r.json"; ap = pathlib.Path(td) / "a.json"
        rp.write_text(json.dumps(ranking_raw), encoding="utf-8"); ap.write_text(json.dumps(reference["b_aliases"]), encoding="utf-8")
        return policy.load_ranking(rp), policy.load_aliases(ap)


def _diff(name, want, got) -> list:
    out = []
    for q, row in want.items():
        if got.get(q) != row:
            g = got.get(q) or {}
            first = next((i for i, (a, b) in enumerate(zip(row["keys"], g.get("keys", []))) if a != b), None)
            out.append(f"{name}: {q!r}: first differing rank {first}; scores equal={row['scores'] == g.get('scores')}; total {row['total_matches']} vs {g.get('total_matches')}")
    return out


def verify_reference(reference: dict, cache_dir=None) -> list:
    from tools.atlassian_docs.intelligence import policy, search
    from tests.intelligence.helpers import make_state
    rp, ap = _pinned_policies(reference, policy)
    problems = []
    with mock.patch.object(policy, "ranking", return_value=rp), mock.patch.object(policy, "aliases", return_value=ap):
        problems += _diff("fixture", reference["fixture"], score_all(make_state(*SOURCES), list(reference["fixture"]), search.search_operations))
        if cache_dir is not None:
            state, cleanup = _state_from_cache(pathlib.Path(cache_dir))
            try:
                if state.registry.fingerprint != reference["registry_fingerprint"]:
                    problems.append(f"snapshot fingerprint {state.registry.fingerprint} != reference {reference['registry_fingerprint']}")
                else:
                    problems += _diff("snapshot", reference["snapshot"], score_all(state, list(reference["snapshot"]), search.search_operations))
            finally:
                cleanup()
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--repo-root", required=True, type=pathlib.Path); g.add_argument("--cache-dir", required=True, type=pathlib.Path)
    g.add_argument("--bench", required=True, type=pathlib.Path); g.add_argument("--out", required=True, type=pathlib.Path)
    v = sub.add_parser("verify"); v.add_argument("--cache-dir", type=pathlib.Path, default=None); v.add_argument("--reference", type=pathlib.Path, default=DEFAULT_REF)
    args = ap.parse_args(argv)
    if args.cmd == "generate":
        doc = generate(args.repo_root.resolve(), args.cache_dir.expanduser(), args.bench)
        args.out.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({k: doc[k] for k in ("reference_commit", "registry_fingerprint", "query_set_sha256")})); return 0
    sys.path.insert(0, str(HERE.parents[2]))
    problems = verify_reference(json.loads(args.reference.read_text(encoding="utf-8")), args.cache_dir.expanduser() if args.cache_dir else None)
    print("reference ok" if not problems else "\n".join(f"MISMATCH {p}" for p in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Generate the reference in an isolated Round 2 checkout (this machine only — the archive is local)**

```bash
git worktree add /tmp/r2ref 29dba38
python tests/benchmarks/regression_reference.py generate --repo-root /tmp/r2ref \
  --cache-dir ~/.atlassian_api_updater/archive/round2/round2-cache --bench tests/benchmarks/search_queries.json \
  --out tests/benchmarks/round3-regression-reference.json
git worktree remove /tmp/r2ref
python tests/benchmarks/regression_reference.py verify --cache-dir ~/.atlassian_api_updater/archive/round2/round2-cache   # -> "reference ok"
```

The printed `registry_fingerprint` must be `f3c2e9d48aa85c96ca62cdd84ff700cc2714c888cf4148b3a91c604c45b47b62`. Record the verify output and the file's canonical sha in the implementer report.

- [ ] **Step 5: Register the new files in the hash lists**

`evaluator.py`: `EVALUATION_CODE_FILES` gains `"tests/benchmarks/regression_reference.py"`; `TOOLING_FILES` gains `"tests/benchmarks/test_regression_reference.py"`. `test_evaluator.py`: add `"tests/benchmarks/regression_reference.py"` to `EVAL_CODE_FILES`.

- [ ] **Step 6: Run the full suite, commit**

Run: `python -m unittest discover -s tests -t .` → OK (the snapshot test prints its archive note or runs it; the fixture part always runs).

```bash
git add tests/benchmarks/regression_reference.py tests/benchmarks/round3-regression-reference.json tests/benchmarks/test_regression_reference.py \
  tests/benchmarks/evaluator.py tests/benchmarks/test_evaluator.py
git commit -m "H4: AC-R3-02 regression reference generated in an isolated 29dba38 checkout (S2 + fixtures), verifier and test

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `alias_candidates_tool.py` — resource-vocabulary target rule, shared intent helper, verb prefix invariant (commit H5)

**Files:**
- Modify: `tests/benchmarks/alias_candidates_tool.py:16-26` (imports, `TOOL_VERSION`), `:87-95` (`allowed_methods`), `:113-121` (`expected_vocab`), callers in `candidates`/`classify`/`lexicon_gate`, new `resource_vocab`, `round2_verb_inventory`, `verb_prefix_violations`, CLI `verb-prefix-check`
- Test: `tests/benchmarks/test_alias_candidates_tool.py`, `tests/intelligence/test_search.py:426-437` (replace `TestRound2SpecParity`)

**Interfaces:**
- Produces: `act.resource_vocab(op) -> frozenset` (normalized literal path segments incl. terminal + tag tokens; summary/operationId excluded); `act.expected_vocab(rec, by_key, noise) -> frozenset` (**new signature**: resource vocabulary minus `FUNCTION_WORDS ∪ noise ∪ ID_LIKE ∪ STOPWORDS ∪ digits`; verbs/hints no longer excluded); `act.allowed_methods(query, verb_methods)` delegates to `search.method_intent`; `act.round2_verb_inventory` / `act.verb_prefix_violations` (re-exports of the Task 1 evaluator helpers); `TOOL_VERSION = "round3.1"`.
- Consumes: `search.method_intent` (Task 2).

- [ ] **Step 1: Write the failing tests**

In `tests/benchmarks/test_alias_candidates_tool.py` replace `test_expected_vocab_excludes_verbs_noise_hints_ids` with:

```python
    def test_expected_vocab_is_resource_evidence_minus_function_noise_id(self):
        """Round 3 spec §6: targets must appear in the expected op's path/terminal/tag tokens; verbs and hint keys are allowed."""
        op = {"key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment", "source": "jira-platform", "method": "POST",
              "operation_id": "addComment", "summary": "Add comment", "tags": ["Issue comments"]}
        rec = {"expected_top1_any": [op["key"]]}
        self.assertEqual(act.resource_vocab(op), frozenset({"rest", "api", "issue", "comment"}))
        vocab = act.expected_vocab(rec, {op["key"]: op}, ["rest", "api"])
        self.assertEqual(vocab, frozenset({"issue", "comment"}))                       # comment is a verb-inventory key and still a target
        self.assertNotIn("add", vocab)                                                   # summary/operationId words are not resource evidence
        sprint = {"key": "jira-software:POST:/rest/agile/1.0/sprint", "source": "jira-software", "method": "POST", "operation_id": "createSprint",
                  "summary": "Create sprint", "tags": ["Sprint"]}
        self.assertEqual(act.expected_vocab({"expected_top1_any": [sprint["key"]]}, {sprint["key"]: sprint}, ["rest", "agile"]), frozenset({"sprint"}))   # hint key allowed; "1.0" dropped (digits), "create" absent

    def test_resource_vocab_targets_on_real_fixtures(self):
        from tests.benchmarks import round_seal as rs
        from tests.intelligence.helpers import make_state
        state = make_state("jira-platform", "jira-software", "confluence")
        internal = {op.key: rs._catalog_record(op) for sr in state.registry.sources.values() for op in sr.operations}
        noise = ["rest", "api", "agile", "software", "wiki"]
        ev_ = lambda key: act.expected_vocab({"expected_top1_any": [key]}, internal, noise)
        self.assertIn("comment", ev_("jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment"))     # feedback -> comment (s-024 shape)
        self.assertIn("sprint", ev_("jira-software:POST:/rest/agile/1.0/sprint"))                         # iteration -> sprint (s-032 shape)
        self.assertIn("post", ev_("confluence:POST:/blogposts"))                                           # blog entry -> post via tag "Blog Post"
        for key in ("jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment", "confluence:POST:/blogposts"):
            self.assertFalse({"get", "create", "add", "rest", "api", "id"} & ev_(key), key)                 # pure action tokens / noise / id-like never qualify

    def test_allowed_methods_is_the_production_helper(self):
        from tools.atlassian_docs.intelligence import search
        vm = {"get": ["GET"], "delete": ["DELETE"], "change": ["PUT", "POST"], "add": ["POST"]}
        for q in ("get the issue", "issue status", "get and delete issue", "change add x"):
            self.assertEqual(act.allowed_methods(q, vm), search.method_intent(search.tokenize_unigrams(q), vm)[1], q)
        self.assertIsNone(act.allowed_methods("issue status", vm)); self.assertEqual(act.allowed_methods("get and delete issue", vm), frozenset())


class TestVerbPrefixInvariant(unittest.TestCase):
    """AC-R3-12: the live inventory keeps Round 2's rows and each Round 2 list as an exact prefix; suffixes sorted."""
    def test_live_inventory_satisfies_prefix_invariant(self):
        base = act.round2_verb_inventory()
        self.assertEqual(canonical_sha256(base), "d66317db7a6a3d047f30197791eefdb93448747b913544da7545136f91dbffc0")   # Round 2 verb_inventory_sha256
        live = json.loads((act.DATA / "search_ranking.json").read_text(encoding="utf-8"))["verb_methods"]
        self.assertEqual(act.verb_prefix_violations(base, live), [])

    def test_verb_prefix_invariant_rejects_reorder_and_truncation(self):                                   # review focus 5
        base = {"change": ["PUT", "POST"], "get": ["GET"], "leave": ["POST", "DELETE"]}
        self.assertEqual(act.verb_prefix_violations(base, {"change": ["PUT", "POST", "DELETE"], "get": ["GET"], "leave": ["POST", "DELETE"]}), [])
        self.assertTrue(act.verb_prefix_violations(base, {"change": ["POST", "PUT"], "get": ["GET"], "leave": ["POST", "DELETE"]}))       # same set, reordered
        self.assertTrue(act.verb_prefix_violations(base, {"change": ["PUT"], "get": ["GET"], "leave": ["POST", "DELETE"]}))              # truncated
        self.assertTrue(act.verb_prefix_violations(base, {"change": ["PUT", "POST"], "get": ["GET"]}))                                   # row removed
        self.assertTrue(act.verb_prefix_violations(base, {**base, "zz": ["GET"]}))                                                       # row added
        self.assertTrue(act.verb_prefix_violations(base, {**base, "get": ["GET", "POST", "DELETE"]}))                                    # suffix not sorted
        self.assertEqual(act.verb_prefix_violations(base, {**base, "get": ["GET", "DELETE", "POST"]}), [])
```

Keep `test_candidates_exclude_what_classify_treats_as_known` (candidates ⇔ R6) and `test_classify_r5_r6` as they are (both call `candidates`/`classify`, whose signatures do not change); adjust any direct `expected_vocab(rec, by_key, verbs, noise, hints)` call in the test module to `expected_vocab(rec, by_key, noise)`.

Replace `tests/intelligence/test_search.py::TestRound2SpecParity` with:

```python
class TestVerbInventoryPrefixInvariant(unittest.TestCase):
    """AC-R3-12 (replaces the Round 2 §6 parity test): the live inventory extends the Round 2 §6 block by sorted suffixes only."""
    def test_verb_inventory_is_round2_block_plus_sorted_suffixes(self):
        from tests.benchmarks import alias_candidates_tool as act
        base, rp = act.round2_verb_inventory(), policy.load_ranking()
        self.assertEqual(act.verb_prefix_violations(base, {v: list(o) for v, o in rp.verb_method_order.items()}), [])
        for v, methods in base.items():
            self.assertEqual(rp.verb_method_order[v][0], methods[0], v)                                    # §3.1: first method never changes
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.benchmarks.test_alias_candidates_tool tests.intelligence.test_search 2>&1 | tail -5`
Expected: FAIL (`resource_vocab`/`round2_verb_inventory` missing; old `expected_vocab` arity).

- [ ] **Step 3: Implement**

Imports: `from tools.atlassian_docs.intelligence.search import method_intent, singular, tokenize_unigrams` and `from tests.benchmarks import evaluator as ev`; `TOOL_VERSION = "round3.1"`; add `TARGET_EXCLUDE = FUNCTION_WORDS | ID_LIKE | STOPWORDS`.

```python
def allowed_methods(query, verb_methods):
    """None when the query has no inventory verb; else the intersection (may be empty = intent 0). The production helper
    (search.method_intent) so the machine check, the evaluator's inputs and the scorer agree (Round 3 spec §4)."""
    return method_intent(tokenize_unigrams(query), verb_methods)[1]


def resource_vocab(op) -> frozenset:
    """Round 3 spec §6: resource evidence of an operation = normalized tokens of its literal path segments (terminal segment
    included) and of its tags. summary / operationId words are NOT resource evidence."""
    toks = set(path_literal_tokens(op["key"].split(":", 2)[2]))
    for tag in op.get("tags") or []:
        toks |= set(norm_tokens(tag))
    return frozenset(toks)


def expected_vocab(rec, by_key, noise) -> frozenset:
    """Round 3 spec §6 target eligibility: tokens of the seed's expected ops' resource vocabulary minus function words, path
    noise, id-like tokens, stopwords and digits. Verb-inventory and product_hints membership are not exclusion reasons."""
    toks = set()
    for key in rec.get("expected_top1_any") or []:
        op = by_key.get(key)
        if op is not None:
            toks |= resource_vocab(op)
    drop = TARGET_EXCLUDE | set(noise)
    return frozenset(t for t in toks if t not in drop and not t.isdigit())


round2_verb_inventory, verb_prefix_violations = ev.round2_verb_inventory, ev.verb_prefix_violations      # defined in the stdlib-only evaluator (Task 1)
```

Callers: in `candidates` → `vocab = expected_vocab(rec, by_key, noise)`; in `classify` → `expected_vocab(rec, by_key, noise)`; in `lexicon_gate` → `expected_vocab(r, by_key, noise)` (the `verbs`/`hints` locals stay for the other reasons). CLI: add

```python
def cmd_verb_prefix_check(args):
    live = _read(DATA / "search_ranking.json")["verb_methods"]
    problems = verb_prefix_violations(round2_verb_inventory(), live)
    for m in problems:
        print(f"VIOLATION {m}")
    print("prefix ok" if not problems else f"{len(problems)} violation(s)")
    return 1 if problems else 0
```

registered as `p = sub.add_parser("verb-prefix-check"); p.set_defaults(fn=cmd_verb_prefix_check)` (no `--cache-dir`).

- [ ] **Step 4: Run the full suite, commit**

Run: `python -m unittest discover -s tests -t .` → OK.

```bash
git add tests/benchmarks/alias_candidates_tool.py tests/benchmarks/test_alias_candidates_tool.py tests/intelligence/test_search.py
git commit -m "H5: alias target eligibility by resource vocabulary (verbs/hints allowed), production intent helper, verb prefix invariant (AC-R3-12)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `round_seal.py` — Round 3 actionability rules, rule ids, replacement state machine, rendered generation input, Round 3 freeze entry (commit H6)

**Files:**
- Modify: `tests/benchmarks/round_seal.py:16-18` (imports), `:105-140` (`_record_checks`), `:266-288` (`freeze_entry`, `cmd_freeze`), `:307-340` (`machine_check`), `:400-444` (`cmd_check`, `cmd_seal`), `:474-489` (CLI), new helpers
- Test: `tests/benchmarks/test_round_seal.py`

**Interfaces:**
- Produces: `rs.HIDDEN_RULES_R3` (frozen ordered tuple), `rs.RECORD_RULES`, `rs.SECTION_RULES`, `rs.NEGATIVE_SPLIT == (4, 4)`; `rs.intent_of(query, verb_methods)`; `rs.record_actionable(rec, verb_methods) -> bool`; `rs.negative_distribution(records, verb_methods) -> (actionable, abstained)`; `rs.machine_check(plain, bench, internal, round=1, verb_methods=None)` (round ≥ 3 requires `verb_methods`, else `ValueError`); `rs.rule_id(message) -> str`; `rs.record_rejections(violations) -> list[str]`; `rs.section_rejections(violations) -> list[str]`; `rs.section_request(section, plain) -> str`; `rs.next_request(violations, plain, state) -> tuple`; `rs.render_generation_input(template, generator_records, verb_methods) -> str`; `rs.annotate_for_review(plain, verb_methods) -> dict` (same records plus `machine: {matched_verbs, intent_methods, machine_actionable}` per record); `rs.needle_manifest(queries) -> list[{"words", "sha256"}]` (normalized n-gram hashes, no plaintext); `rs.scan_for_needles(roots, manifest, allow=()) -> list[str]` (files whose normalized word stream contains any manifest n-gram, minus allowed paths); CLI `scan --manifest M --root R [--root R2…] [--allow PATH…]` (prints `{"unexpected_hits": [...]}`, exit 0 iff empty); `rs.verify_reference_ciphertext(enc_path, round=3) -> list[str]` (`[]` iff `file_sha256(enc) == freeze_for(round)["reference_set"]["enc_sha256"]`); CLI `reference-check --round 3 --reference-enc PATH` (prints `reference ciphertext ok` / `MISMATCH …`, exit 0/1); `rs.freeze_entry(round, cache_dir, reference_enc=None)`; CLI `freeze --round 3 --cache-dir S --reference-enc PATH`, `check/seal --round 3` read `verb_methods` from `search_ranking.json`.
- Consumes: `search.method_intent`, `search.tokenize_unigrams` (Task 2); `ev.freeze_key_set`, `ev.round_freeze_hashes` (Task 3).

- [ ] **Step 1: Write the failing tests**

Add to `tests/benchmarks/test_round_seal.py` (module level, after `valid_plain`):

```python
VERBS = {"get": ["GET"], "show": ["GET"], "list": ["GET"], "create": ["POST"], "publish": ["POST"], "start": ["POST"],
         "delete": ["DELETE"], "erase": ["DELETE"], "remove": ["DELETE"], "update": ["PUT"], "rename": ["PUT", "POST"], "assign": ["PUT", "POST"]}


def rec3(i, q, key):
    return {**rec(i, q, key), "origin": "held_out-r3"}


def neg3(i, q, key):
    return {**neg(i, q, key), "origin": "negative-r3"}


def valid_plain_r3():
    """Round 3 shape of valid_plain(): same expected keys/distribution; every held_out query carries a verb whose method matches
    its expected op; negatives: n1-n4 actionable with the forbidden op's method inside the intent, n5-n8 verb-less."""
    held = [rec3(1, "show me the ticket details", A), rec3(2, "publish a brand new document", B), rec3(3, "erase the whole ticket", C),
            rec3(4, "list every jira board", D), rec3(5, "rename the current jira sprint", E), rec3(6, "assign the ticket to someone", F),
            rec3(7, "show the confluence document", G), rec3(8, "start a fresh sprint", H), rec3(9, "get my ticket now", A),
            rec3(10, "publish a fresh wiki entry", B), rec3(11, "remove the ticket record", C), rec3(12, "list which agile boards exist", D),
            rec3(13, "create a document today", B), rec3(14, "start another sprint now", H), rec3(15, "show one wiki document", G),
            rec3(16, "get a jira ticket", A)]
    negs = [neg3(1, "delete the ticket status field", C), neg3(2, "update the issue type scheme", E), neg3(3, "show the document space overview", G),
            neg3(4, "assign jira ticket owner", F), neg3(5, "confluence document tree", B), neg3(6, "sprint board settings", D),
            neg3(7, "ticket record archive", C), neg3(8, "page tree layout", G)]
    return {"held_out": held, "negative": negs}


class TestRound3ActionabilityRules(unittest.TestCase):
    def check(self, plain):
        return rs.machine_check(plain, BENCH, CAT, round=3, verb_methods=VERBS)

    def test_valid_round3_plain_has_no_violations(self):
        self.assertEqual(self.check(valid_plain_r3()), [])
        self.assertEqual(rs.negative_distribution(valid_plain_r3()["negative"], VERBS), (4, 4))
        with self.assertRaises(ValueError):
            rs.machine_check(valid_plain_r3(), BENCH, CAT, round=3)                                  # round >= 3 needs the inventory
        self.assertEqual(rs.machine_check(valid_plain(), BENCH, CAT), [])                            # round 1 unchanged

    def test_actionable_rule_three_branches(self):                                                     # review focus 1
        p = valid_plain_r3(); p["held_out"][0]["expected_top1_any"] = [C]                              # show (GET) vs DELETE op: intent non-empty, expected outside
        msgs = self.check(p); self.assertEqual([rs.rule_id(m) for m in msgs], ["actionable"]); self.assertTrue(msgs[0].startswith("h-001: actionable:"))
        p = valid_plain_r3(); p["held_out"][0]["query"] = "create and delete the ticket"              # empty intersection
        self.assertEqual([rs.rule_id(m) for m in self.check(p)], ["actionable"])
        p = valid_plain_r3(); p["held_out"][0]["query"] = "the ticket details please"                 # no verb
        self.assertEqual([rs.rule_id(m) for m in self.check(p)], ["actionable"])
        self.assertEqual(self.check(valid_plain_r3()), [])                                           # non-empty + expected inside -> pass

    def test_negative_method_rule_applies_to_actionable_negatives_only(self):
        p = valid_plain_r3(); p["negative"][0]["forbidden_top1"] = [A]                                  # delete (DELETE) vs GET op
        msgs = self.check(p); self.assertEqual([rs.rule_id(m) for m in msgs], ["negative-method"]); self.assertTrue(msgs[0].startswith("n-001: negative-method:"))
        p = valid_plain_r3(); p["negative"][4]["forbidden_top1"] = [A]                                  # abstained n-005: rule does not apply
        self.assertEqual(self.check(p), [])

    def test_negative_distribution_must_be_exactly_four_four(self):
        p = valid_plain_r3(); p["negative"][4]["query"] = "show the document tree"                     # 5 actionable / 3 abstained
        msgs = self.check(p); self.assertEqual([rs.rule_id(m) for m in msgs], ["negative-distribution"])
        self.assertIn("5 actionable / 3 abstained", msgs[0])
        p = valid_plain_r3(); p["negative"][0]["query"] = "ticket status field values"                # 3 / 5
        self.assertEqual([rs.rule_id(m) for m in self.check(p)], ["negative-distribution"])

    def test_rule_id_covers_every_checker_message(self):
        mutations = [lambda p: p["held_out"][0].update(query="two words"), lambda p: p["held_out"][0].update(expected_top1_any=["nope:GET:/x"]),
                     lambda p: p["held_out"][0].update(query="get issue"), lambda p: p["held_out"][1].update(query="publish a create page now"),
                     lambda p: p["negative"][6].update(query="delete issue"), lambda p: p["held_out"][1].update(query="get issue by key"),
                     lambda p: p["held_out"][0].update(origin="held_out-r2"), lambda p: p["negative"][0].update(expected_top1_any=[A]),
                     lambda p: p["held_out"].__setitem__(3, rec3(4, "get my ticket now", A)), lambda p: p["negative"][4].update(query="show the document tree")]
        for mutate in mutations:
            p = valid_plain_r3(); mutate(p)
            msgs = self.check(p); self.assertTrue(msgs)
            for m in msgs:
                self.assertIn(rs.rule_id(m), rs.HIDDEN_RULES_R3, m)
        self.assertEqual(rs.HIDDEN_RULES_R3, ("schema", "catalog", "words", "actionable", "negative-method", "operationId", "summary/tags",
                                              "negative-phrase", "reuse", "distribution", "negative-distribution"))


class TestReplacementStateMachine(unittest.TestCase):
    def test_record_lines_by_priority_then_sections_in_frozen_order(self):
        p = valid_plain_r3()
        v = ["h-002: query has 2 words (must be 3-7)", "h-002: copies consecutive tokens 'create page' from expected op summary (summary/tags rule)",
             "held_out: method DELETE=1 (need >= 2)", "negative: negative-distribution: 5 actionable / 3 abstained (need 4/4)", "n-003: negative-method: forbidden methods ['GET'] outside intent ['POST']"]
        self.assertEqual(rs.record_rejections(v), ["record h-002 rejected: words", "record n-003 rejected: negative-method"])     # words beats summary/tags
        self.assertEqual(rs.section_rejections(v), ["distribution", "negative-distribution"])
        self.assertEqual(rs.next_request(v, p, {})[0], "records")
        only_sections = v[2:4]
        kind, section, text = rs.next_request(only_sections, p, {})
        self.assertEqual((kind, section), ("section", "held_out")); self.assertEqual(text.split("\n"), ["distribution rejected"] + [r["id"] for r in p["held_out"]])
        kind, section, text = rs.next_request(only_sections[1:], p, {"negative_section_replacements": 0})
        self.assertEqual((kind, section), ("section", "negative")); self.assertEqual(text.split("\n"), ["negative distribution rejected"] + [r["id"] for r in p["negative"]])
        self.assertEqual(rs.next_request(only_sections[1:], p, {"negative_section_replacements": 1})[0], "invalid")           # second section replacement forbidden
        self.assertEqual(rs.next_request([], p, {}), ("ok", None))

    def test_render_generation_input_is_deterministic_and_pins_the_inventory(self):
        tpl = "RULES\nVERB_METHODS:\n<verb methods json>\nCATALOG:\n<generator catalog lines>\n"
        gen = rs.generator_view(CAT)
        a, b = rs.render_generation_input(tpl, gen, VERBS), rs.render_generation_input(tpl, gen, VERBS)
        self.assertEqual(a, b)
        block = a.split("VERB_METHODS:\n")[1].split("\nCATALOG:")[0]
        self.assertEqual(json.loads(block), VERBS); self.assertEqual(rs.canonical_sha256(json.loads(block)), rs.canonical_sha256(VERBS))
        self.assertIn(f"{CAT[0]['key']}\t{CAT[0]['source']}\t{CAT[0]['method']}\t{CAT[0]['summary']}\tIssues", a)
        with self.assertRaises(ValueError):
            rs.render_generation_input("no placeholders", gen, VERBS)

    def test_annotate_for_review_adds_machine_fields(self):
        ann = rs.annotate_for_review(valid_plain_r3(), VERBS)
        h1, n5 = ann["held_out"][0], ann["negative"][4]
        self.assertEqual(h1["machine"], {"matched_verbs": ["show"], "intent_methods": ["GET"], "machine_actionable": True})
        self.assertEqual(n5["machine"], {"matched_verbs": [], "intent_methods": [], "machine_actionable": False})
        self.assertEqual({k: v for k, v in h1.items() if k != "machine"}, valid_plain_r3()["held_out"][0])          # records untouched
        self.assertEqual(sum(r["machine"]["machine_actionable"] for r in ann["negative"]), 4)

    def test_needle_manifest_and_scan(self):
        import tempfile, pathlib, json
        queries = ["show me the ticket details", "Delete the ticket status field"]
        m = rs.needle_manifest(queries)
        self.assertEqual([e["words"] for e in m], [5, 5]); self.assertTrue(all(len(e["sha256"]) == 64 for e in m))
        self.assertNotIn("ticket", json.dumps(m))                                                           # no plaintext in the manifest
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); (root / "a.txt").write_text("notes: Show   me the\nticket details!", encoding="utf-8")     # whitespace / case variant
            (root / "b.json").write_text(json.dumps({"q": "delete the ticket status field"}), encoding="utf-8")
            (root / "c.md").write_text("ticket details are shown here", encoding="utf-8")                   # partial: no hit
            (root / "allowed.json").write_text(json.dumps({"q": "show me the ticket details"}), encoding="utf-8")
            hits = rs.scan_for_needles([root], m)
            self.assertEqual(sorted(pathlib.Path(h).name for h in hits), ["a.txt", "allowed.json", "b.json"])
            self.assertEqual(sorted(pathlib.Path(h).name for h in rs.scan_for_needles([root], m, allow=[root / "allowed.json"])), ["a.txt", "b.json"])
            self.assertEqual(rs.scan_for_needles([root], rs.needle_manifest(["totally absent phrase here"])), [])

    def test_verify_reference_ciphertext(self):
        import tempfile, pathlib
        from unittest import mock
        from tests.benchmarks import evaluator as ev
        with tempfile.TemporaryDirectory() as td:
            enc = pathlib.Path(td) / "round2-sealed.json.enc"; enc.write_bytes(b"ciphertext")
            entry = {"round": 3, "reference_set": {"enc_sha256": ev.file_sha256(enc)}}
            with mock.patch.object(rs.ev, "freeze_for", lambda r: entry):
                self.assertEqual(rs.verify_reference_ciphertext(enc, 3), [])
                enc.write_bytes(b"tampered")
                self.assertEqual(len(rs.verify_reference_ciphertext(enc, 3)), 1)


class TestRound3FreezeEntry(unittest.TestCase):
    def test_round3_entry_has_the_canonical_key_set(self):
        import tempfile, pathlib
        from unittest import mock
        from tests.benchmarks import evaluator as ev
        shas = {"jira-platform": "a" * 64, "jira-software": "b" * 64, "confluence": "c" * 64}
        hashes = {k: "0" * 64 for k in ("concept_lexicon_sha256", "lexicon_aliases_sha256", "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256",
                                         "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T", "regression_reference_sha256", "tuning_grid_sha256")}
        with tempfile.TemporaryDirectory() as td:
            enc = pathlib.Path(td) / "round2-sealed.json.enc"; enc.write_bytes(b"ciphertext")
            with mock.patch.object(rs, "load_catalogs_from_cache", lambda cache_dir, round=1: ([], CAT, "f" * 64, dict(shas))), \
                 mock.patch.object(rs.ev, "round_freeze_hashes", lambda r: dict(hashes)):
                e = rs.freeze_entry(3, "x", reference_enc=enc)
        self.assertEqual(set(e), ev.freeze_key_set(3)); self.assertNotIn("commit_T", e)
        self.assertEqual(e["reference_set"]["origin"], "round2"); self.assertEqual(e["reference_set"]["enc_sha256"], ev.file_sha256(enc))
        b = json.loads(rs.BENCH_PATH.read_text(encoding="utf-8"))["round2_seal"]
        self.assertEqual((e["reference_set"]["held_out_sha256"], e["reference_set"]["negative_sha256"]), (b["held_out_sha256"], b["negative_sha256"]))
        self.assertEqual(e["hidden_generation_rules"], list(rs.HIDDEN_RULES_R3)); self.assertEqual(e["hidden_set_origin"], "round3")
        with self.assertRaises(SystemExit):
            with mock.patch.object(rs, "load_catalogs_from_cache", lambda cache_dir, round=1: ([], CAT, "f" * 64, dict(shas))), \
                 mock.patch.object(rs.ev, "round_freeze_hashes", lambda r: dict(hashes)):
                rs.freeze_entry(3, "x")                                                               # round >= 3 needs --reference-enc
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.benchmarks.test_round_seal 2>&1 | tail -5`
Expected: FAIL (`machine_check()` unexpected `verb_methods`; helpers missing).

- [ ] **Step 3: Implement**

Imports: `from tools.atlassian_docs.intelligence.search import method_intent, tokenize_unigrams` (read-only use of the production intent helper). Constants after `PRODUCT_WORDS`:

```python
HIDDEN_RULES_R3 = ("schema", "catalog", "words", "actionable", "negative-method", "operationId", "summary/tags", "negative-phrase", "reuse",
                   "distribution", "negative-distribution")            # Round 3 spec §4: frozen order; record-level priority = first 9
RECORD_RULES, SECTION_RULES = HIDDEN_RULES_R3[:9], HIDDEN_RULES_R3[9:]
NEGATIVE_SPLIT = (4, 4)
BENCH_PATH = pathlib.Path(__file__).resolve().parent / "search_queries.json"


def intent_of(query, verb_methods):
    return method_intent(tokenize_unigrams(query or ""), verb_methods)[1]       # None (no verb) | frozenset (maybe empty)


def record_actionable(rec, verb_methods) -> bool:
    return bool(intent_of(rec.get("query"), verb_methods))


def _methods(keys) -> set:
    return {k.split(":", 2)[1] for k in keys or [] if k.count(":") >= 2}


def _actionable_checks(rec, verb_methods) -> list:
    """Round 3 spec §4 rule `actionable` (held_out): a verb, a non-empty allowed-method intersection, an expected method inside it."""
    rid, allowed = rec.get("id", "?"), intent_of(rec.get("query"), verb_methods)
    if allowed is None:
        return [f"{rid}: actionable: no inventory verb in the query"]
    if not allowed:
        return [f"{rid}: actionable: recognized verbs have an empty allowed-method intersection"]
    exp = _methods(rec.get("expected_top1_any"))
    if not exp & allowed:
        return [f"{rid}: actionable: expected methods {sorted(exp)} outside intent {sorted(allowed)}"]
    return []


def _negative_method_checks(rec, verb_methods) -> list:
    """Round 3 spec §4 rule `negative-method` (actionable negatives only): methods(forbidden) ∩ intent ≠ ∅."""
    rid, allowed = rec.get("id", "?"), intent_of(rec.get("query"), verb_methods)
    if not allowed:
        return []
    forb = _methods(rec.get("forbidden_top1"))
    return [] if forb & allowed else [f"{rid}: negative-method: forbidden methods {sorted(forb)} outside intent {sorted(allowed)}"]


def negative_distribution(records, verb_methods) -> tuple:
    a = sum(record_actionable(r, verb_methods) for r in records if isinstance(r, dict))
    return a, len(records) - a


def _negative_distribution_checks(records, verb_methods) -> list:
    a, n = negative_distribution(records, verb_methods)
    return [] if (a, n) == NEGATIVE_SPLIT else [f"negative: negative-distribution: {a} actionable / {n} abstained (need {NEGATIVE_SPLIT[0]}/{NEGATIVE_SPLIT[1]})"]
```

In `machine_check(plain, bench, internal_catalog, round=1, verb_methods=None)`: at the top `if round >= 3 and verb_methods is None: raise ValueError("round >= 3 machine check needs the frozen verb_methods")`; inside the record loop after `_record_checks`: `if round >= 3 and sect == "held_out": out += _actionable_checks(rec, verb_methods)` and `if round >= 3 and sect == "negative": out += _negative_method_checks(rec, verb_methods)`; after the section loop: `if round >= 3 and isinstance(plain.get("negative"), list): out += _negative_distribution_checks(plain["negative"], verb_methods)`.

Rule ids and the replacement state machine:

```python
_RULE_PATTERNS = ((": actionable:", "actionable"), (": negative-method:", "negative-method"), ("negative-distribution:", "negative-distribution"),
                  ("held_out: source ", "distribution"), ("held_out: method ", "distribution"), ("held_out: product", "distribution"),
                  ("not in catalog", "catalog"), ("query has ", "words"), ("equals operationId", "operationId"),
                  ("copies consecutive tokens", "summary/tags"), ("negative query equals", "negative-phrase"), ("reuse of", "reuse"))


def rule_id(message: str) -> str:
    """Map a machine_check message to its frozen rule id; everything structural (schema, origin, id prefix, counts, list shape) is `schema`."""
    for needle, rule in _RULE_PATTERNS:
        if needle in message:
            return rule
    return "schema"


def record_rejections(violations) -> list:
    """Fixed-format lines, one per violating record, the rule chosen by RECORD_RULES priority (the controller never chooses)."""
    by_id = {}
    for m in violations:
        rule = rule_id(m)
        if rule in SECTION_RULES:
            continue
        rid = m.split(":", 1)[0]
        if rid not in by_id or RECORD_RULES.index(rule) < RECORD_RULES.index(by_id[rid]):
            by_id[rid] = rule
    return [f"record {rid} rejected: {rule}" for rid, rule in sorted(by_id.items())]


def section_rejections(violations) -> list:
    present = {rule_id(m) for m in violations}
    return [r for r in SECTION_RULES if r in present]


def section_request(section, plain) -> str:
    head = "distribution rejected" if section == "held_out" else "negative distribution rejected"
    return "\n".join([head] + [r["id"] for r in plain[section]])


def next_request(violations, plain, state) -> tuple:
    """Deterministic controller step (Round 3 spec §4): record-level lines first; then section rules in frozen order (held_out
    `distribution`, then `negative-distribution`, each followed by a full re-check). The negative section may be replaced exactly
    once; needing a second replacement makes the whole generation attempt invalid. state: {"negative_section_replacements": int}."""
    if not violations:
        return ("ok", None)
    lines = record_rejections(violations)
    if lines:
        return ("records", lines)
    for rule in section_rejections(violations):
        if rule == "distribution":
            return ("section", "held_out", section_request("held_out", plain))
        if state.get("negative_section_replacements", 0) >= 1:
            return ("invalid", "negative-distribution broken again after the single section replacement (spec §4): attempt invalid")
        return ("section", "negative", section_request("negative", plain))
    return ("ok", None)


def annotate_for_review(plain, verb_methods) -> dict:
    """Reviewer input (spec §4 v1.14): each record plus the machine's verdict so the reviewer judges verb USE, not the mapping."""
    out = {}
    for sect, _ in HIDDEN:
        rows = []
        for rec in plain.get(sect, []):
            verbs, allowed = method_intent(tokenize_unigrams(rec.get("query") or ""), verb_methods)
            rows.append({**rec, "machine": {"matched_verbs": list(verbs), "intent_methods": sorted(allowed) if allowed else [], "machine_actionable": bool(allowed)}})
        out[sect] = rows
    return out


_WORD = re.compile(r"[^a-z0-9]+")
SCAN_SUFFIXES = (".txt", ".json", ".jsonl", ".md", ".log", ".py", ".yaml", ".yml", ".csv")


def _words(text: str) -> list:
    return [w for w in _WORD.split(text.lower()) if w]


def needle_manifest(queries) -> list:
    """AC-18b scanner input (spec §5 v1.16): per query the word count and sha256 of the normalized n-gram — never the text."""
    return [{"words": len(_words(q)), "sha256": canonical_sha256(" ".join(_words(q)))} for q in queries]


def scan_for_needles(roots, manifest, allow=()) -> list:
    """Files under `roots` (text suffixes only) whose normalized word stream contains any manifest n-gram, minus `allow`."""
    by_n, allowed = {}, {pathlib.Path(p).resolve() for p in allow}
    for e in manifest:
        by_n.setdefault(e["words"], set()).add(e["sha256"])
    hits = []
    for root in roots:
        for p in sorted(pathlib.Path(root).rglob("*")):
            if not p.is_file() or p.suffix not in SCAN_SUFFIXES or p.resolve() in allowed or ".git" in p.parts:
                continue
            words = _words(p.read_text(encoding="utf-8", errors="ignore"))
            if any(canonical_sha256(" ".join(words[i:i + n])) in shas for n, shas in by_n.items() for i in range(len(words) - n + 1)):
                hits.append(str(p))
    return hits


def cmd_scan(args):
    hits = scan_for_needles(args.root, _read_json(args.manifest), allow=args.allow or [])
    print(json.dumps({"unexpected_hits": hits}))
    return 1 if hits else 0


def verify_reference_ciphertext(enc_path, round=3) -> list:
    """AC-R3-06 checkpoint helper (B, before the D decryption, terminal D/F/X): archive ciphertext sha == freeze reference_set.enc_sha256."""
    want, got = ev.freeze_for(round)["reference_set"]["enc_sha256"], ev.file_sha256(enc_path)
    return [] if got == want else [f"reference ciphertext sha {got} != freeze reference_set.enc_sha256 {want}"]


def cmd_reference_check(args):
    problems = verify_reference_ciphertext(args.reference_enc, args.round)
    for m in problems:
        print(f"MISMATCH {m}")
    print("reference ciphertext ok" if not problems else f"{len(problems)} mismatch(es)")
    return 1 if problems else 0


def render_generation_input(template: str, generator_records, verb_methods) -> str:
    """The exact generator input: catalog TSV lines and the canonical VERB_METHODS JSON (sha == verb_inventory_sha256)."""
    if "<generator catalog lines>" not in template or "<verb methods json>" not in template:
        raise ValueError("generation template must contain <generator catalog lines> and <verb methods json>")
    lines = "\n".join(f"{r['key']}\t{r['source']}\t{r['method']}\t{r['summary']}\t{','.join(r['tags'] or [])}" for r in generator_records)
    block = json.dumps(verb_methods, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return template.replace("<generator catalog lines>", lines).replace("<verb methods json>", block)
```

`freeze_entry(round, cache_dir, reference_enc=None)`: after `entry.update(ev.round_freeze_hashes(round))` add

```python
    if round >= 3:
        if reference_enc is None:
            raise SystemExit("round >= 3 freeze needs --reference-enc (the archived Round 2 ciphertext)")
        r2 = _read_json(BENCH_PATH)["round2_seal"]
        entry["reference_set"] = {"origin": "round2", "enc_sha256": ev.file_sha256(reference_enc),
                                  "held_out_sha256": r2["held_out_sha256"], "negative_sha256": r2["negative_sha256"]}
        entry["hidden_generation_rules"] = list(HIDDEN_RULES_R3)
        entry["hidden_set_origin"] = f"round{round}"
```

`cmd_freeze` passes `reference_enc=getattr(args, "reference_enc", None)`; the `freeze` parser gains `p.add_argument("--reference-enc", default=None)`; new parsers `p = sub.add_parser("scan"); p.add_argument("--manifest", required=True); p.add_argument("--root", action="append", required=True); p.add_argument("--allow", action="append"); p.set_defaults(fn=cmd_scan)` and `p = sub.add_parser("reference-check"); _round(p); p.add_argument("--reference-enc", required=True); p.set_defaults(fn=cmd_reference_check)`. `cmd_check`/`cmd_seal`: `vm = _read_json(RANKING_PATH)["verb_methods"] if args.round >= 3 else None` and pass `verb_methods=vm` to `machine_check`.

- [ ] **Step 4: Run the full suite, commit**

Run: `python -m unittest discover -s tests -t .` → OK.

```bash
git add tests/benchmarks/round_seal.py tests/benchmarks/test_round_seal.py
git commit -m "H6: round_seal Round 3 rules, rule ids and replacement state machine, rendered generation input, reviewer annotations, reference ciphertext check, Round 3 freeze entry

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `tune_search_ranking.py` — 8 constants, conservative selector, memoized grid evaluator, atomic-action proposer (budget 2), `tuning_accept`, failure-branch `--verify` (commit H7)

**Files:**
- Modify: `tests/tune_search_ranking.py` (selector, evaluation, proposer, validator, baseline hash, `_finish`, `_verify`, `write_constants`)
- Test: `tests/test_tune_search_ranking.py`

**Interfaces:**
- Produces: `tune.BONUS_KEYS = ("path_coverage_bonus", "method_order_bonus")`, `tune.PER_SEED = 2`; `tune.select_candidate(results, baseline, grid)` with `results = [(point, seed_passed, regression_effective_passed)]` and key `(bonus tuple, L1, magnitude, lexicographic)`; `tune.GridEvaluator(state, queries, alias_policy)` with `.ranked(query, rp, limit=5) -> (keys, actionable)`; `tune.evaluate_point(state, rp, point, bench, alias_policy) -> (seed_res, reg_res)` (production path, sections `seed`/`regression_negative`); `tune.evaluate_point_fast(ge, rp, point, bench)`; `tune.fixture_failures(...)`/`fixture_failures_fast(...)` (raw judgement); `tune.round_note(word, sid, target)`; `tune.atomic_actions(cands, sid, working)`, `tune.trial_order(actions)`, `tune.apply_actions(working, actions, sid)`, `tune.propose_aliases(eval_fn, bench, base_raw, cands, budget=15, per_seed=2, fixture_fn=None)` (patch gains `actions_by_seed`); `tune.validate_alias_change(...)` rejects rules and >2 actions per seed; `tune.tuning_accept(seed_res, reg_res, fixture_final) -> bool`; `tune.fixture_negative_diagnostic(state, rp, point, bench_r0, alias_policy) -> dict` (the fixture negatives judged with `section="regression_negative"`, diagnostic only — AC-R3-11a `fixture_negative.effective_diagnostic`); `tune.baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench, root=ROOT)`; log line fields `tuning_accept, regression_raw, fixture_positive, fixture_negative_raw, fixture_negative_effective_diagnostic, grid_runtime_s, grid_size`; `_verify` handles `failed` runs.
- Consumes: `policy.CONSTANT_KEYS` (8, Task 1), `search.method_intent/_score/_structural_signals` (Task 2), `ev.evaluate(section=)`, `ev.tuning_grid_sha256`, `ev.evaluation_code_sha256` (Tasks 1, 3).

- [ ] **Step 1: Write the failing tests**

In `tests/test_tune_search_ranking.py` (GRID/BASE already have the two new keys from Task 1):

```python
class TestConservativeSelector(unittest.TestCase):
    def test_smaller_bonus_pair_beats_l1_distance(self):
        near, far = pt(method_order_bonus=0.5), pt(method_match_bonus=1.0, path_unmatched_cap=4)          # bonuses (0,0.5) L1 1 vs (0,0) L1 2
        self.assertEqual(tune.select_candidate([(near, S, R), (far, S, R)], BASE, GRID), far)             # bonus tuple first
        o, c = pt(method_order_bonus=0.5), pt(path_coverage_bonus=0.5)                                     # (0,0.5) < (0.5,0)
        self.assertEqual(tune.select_candidate([(c, S, R), (o, S, R)], BASE, GRID), o)
        self.assertEqual(tune.select_candidate([(o, S, R), (BASE, S, R)], BASE, GRID), BASE)
        self.assertEqual(tune.select_candidate([(o, S, R), (BASE, S - 1, R)], BASE, GRID), o)             # perfect still beats non-perfect
        self.assertEqual(tune.BONUS_KEYS, ("path_coverage_bonus", "method_order_bonus"))


def fake_eval(rules):
    """rules: (word, target) -> seeds fixed; ("PAIR", (w1, t1), (w2, t2)) -> seeds fixed only when both aliases present;
    ("BREAK", word, target) -> regression breaks. Returns (failed seed ids, failed regression ids) like eval_fn."""
    def fn(raw):
        failed, reg = {"s-001", "s-002", "s-003", "s-004"}, set()
        have = {(w, v[0]) for w, v in raw["aliases"].items()}
        for key, seeds in rules.items():
            if key[0] == "PAIR" and key[1] in have and key[2] in have:
                failed -= set(seeds)
            elif key[0] == "BREAK":
                if (key[1], key[2]) in have: reg.add("rn-001")
            elif key in have:
                failed -= set(seeds)
        return frozenset(failed), frozenset(reg)
    return fn


CANDS = {"workspace": {"seed_ids": ["s-001"], "targets_by_seed": {"s-001": ["page", "space"]}, "allowed_targets": ["page", "space"], "catalog_df": 7},
         "feedback": {"seed_ids": ["s-002", "s-003"], "targets_by_seed": {"s-002": ["comment"], "s-003": ["comment", "issue"]}, "allowed_targets": ["comment", "issue"], "catalog_df": 0},
         "starred": {"seed_ids": ["s-004"], "targets_by_seed": {"s-004": ["favourite"]}, "allowed_targets": ["favourite"], "catalog_df": 1},
         "searches": {"seed_ids": ["s-004"], "targets_by_seed": {"s-004": ["filter"]}, "allowed_targets": ["filter"], "catalog_df": 2}}
BENCH2 = {"seed": [{"id": "s-001", "query": "browse pages inside this workspace", "failure_classes": ["R6"]},
                   {"id": "s-002", "query": "leave feedback on this ticket", "failure_classes": ["R5", "R6"]},
                   {"id": "s-003", "query": "read feedback on the issue", "failure_classes": ["R6"]},
                   {"id": "s-004", "query": "list my starred searches", "failure_classes": ["R6"]}], "regression_negative": [{"id": "rn-001", "query": "x"}]}
```

(replace the module's existing `fake_eval`, `CANDS`, `BENCH2`; keep `BASE_RAW`, `QUERIES`, `CLASSES` derived from the new `BENCH2`). Rewrite `TestProposer`:

```python
class TestProposer(unittest.TestCase):
    """spec §6: atomic actions (candidate_word, target), size-1 in tuple order then size-2 with distinct words, rollback per trial,
    <= 2 per seed, <= budget total, direct aliases only."""
    def test_trial_order_singles_then_distinct_word_pairs(self):
        acts = [("a", "x"), ("a", "y"), ("b", "x")]
        self.assertEqual(tune.trial_order(acts), [(("a", "x"),), (("a", "y"),), (("b", "x"),), (("a", "x"), ("b", "x")), (("a", "y"), ("b", "x"))])
        self.assertEqual(tune.atomic_actions(CANDS, "s-004", BASE_RAW), [("searches", "filter"), ("starred", "favourite")])
        self.assertEqual(tune.atomic_actions(CANDS, "s-004", {**BASE_RAW, "aliases": {"starred": ["favourite"]}}), [("searches", "filter")])

    def test_single_actions_in_order_and_rollback(self):
        fn = fake_eval({("workspace", "space"): ["s-001"], ("feedback", "comment"): ["s-002", "s-003"]})
        working, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(patch["aliases"], {"workspace": ["space"], "feedback": ["comment"]})           # page tried first, failed, rolled back
        self.assertEqual(patch["rules"], []); self.assertEqual(patch["resolved_by_prior_change"], ["s-003"]); self.assertEqual(patch["unresolved"], ["s-004"])
        self.assertEqual(patch["actions_by_seed"], {"s-001": [["workspace", "space"]], "s-002": [["feedback", "comment"]]})
        self.assertEqual(patch["notes"]["workspace"], tune.round_note("workspace", "s-001", "space"))
        self.assertEqual(working["aliases"]["ticket"], ["issue"]); self.assertEqual(BASE_RAW["aliases"], {"ticket": ["issue"]})
        self.assertEqual(tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)[1], patch)                    # deterministic

    def test_pair_adopted_when_no_single_fixes_the_seed(self):
        fn = fake_eval({("PAIR", ("searches", "filter"), ("starred", "favourite")): ["s-004"]})
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(patch["aliases"], {"searches": ["filter"], "starred": ["favourite"]}); self.assertEqual(patch["actions_by_seed"]["s-004"], [["searches", "filter"], ["starred", "favourite"]])
        self.assertEqual(patch["unresolved"], ["s-001", "s-002", "s-003"])
        _, capped = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, per_seed=1)
        self.assertEqual(capped["aliases"], {}); self.assertIn("s-004", capped["unresolved"])          # pair never tried at per_seed=1
        _, budget = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, budget=1)
        self.assertEqual(budget["aliases"], {})                                                           # a pair does not fit a budget of 1

    def test_proposer_rejects_change_that_breaks_regression(self):
        fn = fake_eval({("workspace", "page"): ["s-001"], ("BREAK", "workspace", "page"): True, ("workspace", "space"): ["s-001"]})
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(patch["aliases"]["workspace"], ["space"])

    def test_seed_without_r6_is_skipped_and_used_word_not_retried(self):
        bench = json.loads(json.dumps(BENCH2)); bench["seed"][0]["failure_classes"] = ["R5"]
        fn = fake_eval({("workspace", "page"): ["s-001"], ("feedback", "comment"): ["s-002"], ("feedback", "issue"): ["s-003"]})
        _, patch = tune.propose_aliases(fn, bench, BASE_RAW, CANDS)
        self.assertEqual(patch["not_r6"], ["s-001"]); self.assertEqual(patch["aliases"], {"feedback": ["comment"]}); self.assertIn("s-003", patch["unresolved"])

    def test_fixture_constraint_skips_breaking_action(self):
        fn = fake_eval({("workspace", "page"): ["s-001"], ("workspace", "space"): ["s-001"]})
        breaks = lambda raw: ["s-022"] if raw["aliases"].get("workspace") == ["page"] else []
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, fixture_fn=breaks)
        self.assertEqual(patch["aliases"]["workspace"], ["space"])
        self.assertEqual(patch["fixture_fail"], [{"kind": "alias", "actions": [["workspace", "page"]], "seed_query_id": "s-001", "failing": ["s-022"]}])
```

Add to `TestValidator`:

```python
    def test_rejects_rules_and_more_than_two_actions_per_seed(self):
        after = json.loads(json.dumps(BASE_RAW)); after["rules"].append({"when_all": ["workspace", "browse"], "add": ["page"]})
        after["notes"]["rule:0"] = tune.round_note("workspace", "s-001", "page")
        self.assertTrue(any("not proposed in Round 3" in v for v in tune.validate_alias_change(BASE_RAW, after, CANDS, QUERIES, CLASSES)))
        three = json.loads(json.dumps(BASE_RAW))
        for w, t in (("workspace", "page"), ("feedback", "comment"), ("starred", "favourite")):
            three["aliases"][w] = [t]; three["notes"][w] = tune.round_note(w, "s-001", t)
        self.assertTrue(any("more than two atomic actions" in v for v in tune.validate_alias_change(BASE_RAW, three, CANDS, QUERIES, CLASSES)))
        two = json.loads(json.dumps(BASE_RAW))
        for w, t in (("searches", "filter"), ("starred", "favourite")):
            two["aliases"][w] = [t]; two["notes"][w] = tune.round_note(w, "s-004", t)
        self.assertEqual(tune.validate_alias_change(BASE_RAW, two, CANDS, QUERIES, CLASSES), [])
```

New classes:

```python
class TestGridEvaluator(unittest.TestCase):
    """spec §3.4 v1.13: the memoized grid path must rank exactly like search_operations (review focus 3)."""
    @classmethod
    def setUpClass(cls):
        cls.state = tune.fixture_state(); cls.rp = policy.load_ranking(); cls.bench = tune.fixture_bench(tune._BENCH)
        cls.queries = [r["query"] for r in cls.bench["seed"] + cls.bench["regression_negative"]] + ["issue status field values", "create and delete issue", "list page versions"]
        cls.ap = tune._alias_policy(json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")))
        cls.ge = tune.GridEvaluator(cls.state, cls.queries, cls.ap)

    def test_grid_evaluator_matches_search_operations(self):
        import random
        from unittest import mock
        from tools.atlassian_docs.intelligence import search
        pts = tune.grid_points(self.rp.tuning_grid); rnd = random.Random(7)
        sample = rnd.sample(pts, 20) + [{**dict(self.rp.constants), "method_order_bonus": 1.0, "path_coverage_bonus": 1.0, "method_mismatch_penalty": 5.0}]
        for p in sample:
            rpp = tune.ranking_with(self.rp, p)
            with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=self.ap):
                for q in self.queries:
                    out = search.search_operations(self.state, q, limit=5)
                    self.assertEqual(self.ge.ranked(q, rpp), ([r["key"] for r in out["results"]], out["actionable"]), (p, q))

    def test_fast_and_slow_point_evaluation_agree(self):
        for p in (dict(self.rp.constants), {**dict(self.rp.constants), "path_coverage_bonus": 0.5}):
            fast = tune.evaluate_point_fast(self.ge, self.rp, p, self.bench)
            slow = tune.evaluate_point(self.state, self.rp, p, self.bench, self.ap)
            self.assertEqual([(r["passed"], r.get("raw_passed"), r.get("effective_passed")) for r in fast], [(r["passed"], r.get("raw_passed"), r.get("effective_passed")) for r in slow])
            self.assertEqual(tune.fixture_failures_fast(self.ge, self.rp, p, self.bench), tune.fixture_failures(self.state, self.rp, p, self.bench, self.ap))


class TestTuningAccept(unittest.TestCase):
    def res(self, passed, raw=None, eff=None):
        out = {"passed": passed, "failed": [], "total": R}
        if raw is not None: out.update(raw_passed=raw, effective_passed=eff)
        return out

    def test_predicate_uses_effective_regression_and_fixture_raw(self):
        seed_ok, seed_bad = {"passed": S, "failed": [], "total": S}, {"passed": S - 1, "failed": [], "total": S}
        self.assertTrue(tune.tuning_accept(seed_ok, self.res(R, raw=10, eff=R), []))                      # raw 10/14 is fine
        self.assertFalse(tune.tuning_accept(seed_ok, self.res(R - 1, raw=R - 1, eff=R - 1), []))
        self.assertFalse(tune.tuning_accept(seed_bad, self.res(R, raw=R, eff=R), []))
        self.assertFalse(tune.tuning_accept(seed_ok, self.res(R, raw=R, eff=R), ["rn-003"]))               # fixture negative raw is a hard constraint

    def test_finish_marks_failed_or_pending(self):
        import argparse
        from unittest import mock
        rp = policy.load_ranking(); patch = {"aliases": {}, "rules": [], "notes": {}, "resolved_by_prior_change": [], "not_r6": [], "unresolved": [], "fixture_fail": [], "trials": 0, "actions_by_seed": {}}
        args = argparse.Namespace(dry_run=True, note="t")
        with mock.patch.object(tune, "_git", return_value=""), mock.patch("builtins.print") as pr:
            code = tune._finish(args, rp, "f" * 64, [], dict(rp.constants), patch, {}, {"passed": S, "failed": [], "total": S}, self.res(R, raw=10, eff=R), "b" * 64, {"constants": [], "final": []}, 1.5, {"raw_passed": 6, "effective_passed": 6, "total": 6})
            self.assertEqual(code, 0)
            line = json.loads(pr.call_args_list[1].args[0]); self.assertEqual((line["status"], line["tuning_accept"], line["regression_raw"], line["regression_negative"]), ("pending", True, f"10/{R}", f"{R}/{R}"))
            self.assertEqual((line["fixture_negative_raw"], line["fixture_negative_effective_diagnostic"]), ("6/6", "6/6"))
        with mock.patch.object(tune, "_git", return_value=""), mock.patch("builtins.print") as pr:
            code = tune._finish(args, rp, "f" * 64, [], dict(rp.constants), patch, {}, {"passed": S - 1, "failed": [], "total": S}, self.res(R, raw=R, eff=R), "b" * 64, {"constants": [], "final": []}, 1.5, {"raw_passed": 6, "effective_passed": 6, "total": 6})
            self.assertEqual(code, 1); line = json.loads(pr.call_args_list[1].args[0]); self.assertEqual((line["status"], line["tuning_accept"], line["tuning_failed"]), ("failed", False, True))

    def test_verify_failure_branch_replays_the_failed_run(self):
        from unittest import mock
        failed = {"run_id": "f1", "status": "failed", "adopted": False, "tuning_failed": True, "constants_selected": dict(BASE), "result_sha256": "a" * 64}
        with mock.patch.object(tune, "_read_log", return_value=[failed, {**failed, "run_id": "f2"}]), mock.patch.object(tune, "_with_state", return_value=[]), \
             mock.patch.object(tune, "baseline_mismatch", return_value=[]), mock.patch("builtins.print") as pr:
            self.assertEqual(tune._verify("cache", tune._BENCH, policy.load_ranking(), BASE_RAW, {}, {"generated_from": {"inputs": {"aliases": policy.canonical_sha256(BASE_RAW)}}, "candidates": {}}), 0)
        with mock.patch.object(tune, "_read_log", return_value=[failed, {**failed, "run_id": "f2", "result_sha256": "b" * 64}]), mock.patch("sys.stderr"), mock.patch("builtins.print"):
            self.assertEqual(tune._verify("cache", tune._BENCH, policy.load_ranking(), BASE_RAW, {}, {"generated_from": {"inputs": {}}, "candidates": {}}), 2)   # failed runs disagree


class TestBaselineAndConstantsFile(unittest.TestCase):
    def test_baseline_sha_includes_fixture_evaluator_and_grid(self):
        import tempfile, pathlib, shutil
        bench = tune._BENCH; rk = json.loads(tune.RANKING_PATH.read_text(encoding="utf-8")); al = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8"))
        cands = {"candidates": {}, "generated_from": {}}
        a = tune.baseline_sha256(al, rk, "f" * 64, cands, bench)
        other = json.loads(json.dumps(rk)); other["tuning_grid"]["method_order_bonus"] = [0.0, 0.5]
        self.assertNotEqual(a, tune.baseline_sha256(al, other, "f" * 64, cands, bench))                # grid is an input
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            for rel in tune.ev.EVALUATION_CODE_FILES:
                (root / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(tune.ROOT / rel, root / rel)
            self.assertEqual(tune.baseline_sha256(al, rk, "f" * 64, cands, bench, root=root), a)
            (root / tune.ev.EVALUATION_CODE_FILES[0]).write_bytes(b"x")
            self.assertNotEqual(tune.baseline_sha256(al, rk, "f" * 64, cands, bench, root=root), a)        # evaluation code is an input

    def test_write_constants_eight_keys_keeps_structure(self):
        import tempfile, pathlib, shutil
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "search_ranking.json"; shutil.copyfile(tune.RANKING_PATH, p)
            before = policy.load_ranking(p); point = {**dict(before.constants), "method_order_bonus": 0.5, "method_mismatch_penalty": 5.0}
            tune.write_constants(point, path=p)
            after = policy.load_ranking(p)
            self.assertEqual(dict(after.constants), point); self.assertEqual(after.structure_sha256, before.structure_sha256)
            self.assertEqual(p.read_text(encoding="utf-8").count('"constants"'), 1)
```

Update existing tests that referenced `tune.round2_note(w, sid, t, "alias")` to `tune.round_note(w, sid, t)` and `test_pipeline_calls_selector_once_then_proposer_once`'s fake proposer patch to include `"actions_by_seed": {}` and `"fixture_fail": []`; `test_grid_cardinality_and_order` already updated in Task 1.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_tune_search_ranking 2>&1 | tail -5` → FAIL (`GridEvaluator`, `trial_order`, `tuning_accept` missing; selector order).

- [ ] **Step 3: Implement — constants, selector, evaluation paths**

```python
BUDGET, PER_SEED = 15, 2
BONUS_KEYS = ("path_coverage_bonus", "method_order_bonus")      # spec §3.4: conservative tie-break, in this order
EVENTS = ("baseline_checked", "constants_selected", "aliases_proposed", "final_check")


def select_candidate(results, baseline, grid, seed_total=SEED_TOTAL, regression_total=REGRESSION_TOTAL) -> dict:
    """spec §3.4: results = (point, seed_passed, regression_EFFECTIVE_passed). (1) perfect points only, else max seed then max
    regression; (2) smaller (path_coverage_bonus, method_order_bonus); (3) min L1 grid-index distance to the baseline; (4) min
    magnitude sum; (5) lexicographic 8-tuple."""
    if not results:
        raise ValueError("no results to select from")
    pool = [p for p, s, r in results if s == seed_total and r == regression_total]
    if not pool:
        best = max((s, r) for _, s, r in results)
        pool = [p for p, s, r in results if (s, r) == best]
    return dict(min(pool, key=lambda p: (tuple(p[k] for k in BONUS_KEYS), l1_index_distance(p, baseline, grid),
                                          sum(p[k] for k in MAGNITUDE_KEYS), tuple(p[k] for k in CONSTANT_KEYS))))


def _search_fn(state):
    """(top-5 keys, actionable) — the Round 3 evaluator contract."""
    def fn(q):
        out = search_operations(state, q, limit=5)
        return [r["key"] for r in out.get("results", [])], bool(out.get("actionable", True))
    return fn


def evaluate_point(state, rp, point, bench, alias_policy):
    """Production path: seed raw top-1, regression_negative raw + effective (spec §4)."""
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), mock.patch.object(policy, "aliases", return_value=alias_policy):
        fn = _search_fn(state)
        return evaluate(bench["seed"], fn, section="seed"), evaluate(bench["regression_negative"], fn, section="regression_negative")


def fixture_negative_diagnostic(state, rp, point, bench_r0, alias_policy) -> dict:
    """AC-R3-11a `fixture_negative.effective_diagnostic`: the 6 r0 negatives judged like regression_negative (raw + effective) — recorded
    on the log line only; acceptance uses fixture_failures (raw)."""
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), mock.patch.object(policy, "aliases", return_value=alias_policy):
        return evaluate(bench_r0["regression_negative"], _search_fn(state), section="regression_negative")


def fixture_failures(state, rp, point, bench_r0, alias_policy) -> list:
    """Sorted ids of r0 fixture records failing at `point` — RAW judgement for both sets (spec §3.4 fixture hard constraint)."""
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), mock.patch.object(policy, "aliases", return_value=alias_policy):
        fn = _search_fn(state)
        s, r = evaluate(bench_r0["seed"], fn), evaluate(bench_r0["regression_negative"], fn)
    return sorted(f["id"] for f in s["failed"] + r["failed"])


class GridEvaluator:
    """Memoized grid-stage evaluation (spec §3.4 v1.13). Per query the lexical rows (entry, op, lexical) are computed ONCE per alias
    state with the production `_score`; every grid point re-runs only the production `_structural_signals` and reproduces
    search_operations' ordering: key (-final, deprecated, key), DEPRECATED_FACTOR, zero clamp, limit. Bench queries contain
    whitespace so exact-key pinning never applies; a whitespace-free query falls back to search_operations."""
    def __init__(self, state, queries, alias_policy):
        from tools.atlassian_docs.intelligence import search as S
        self.S, self.state, self.ap, self.rows, self.meta = S, state, alias_policy, {}, {}
        for q in dict.fromkeys(queries):
            unigrams, exp = S.tokenize_unigrams(q), S.expand_query(q, alias_policy)
            lexical_base, rows = exp.base | S.joined_query_forms(q), []
            for name in sorted(state.registry.sources):
                sr = state.registry.sources[name]
                for entry in sr.search_index.entries:
                    lexical, _ = S._score(entry, lexical_base, exp.direct, exp.cond, unigrams, alias_policy)
                    if lexical > 0:
                        rows.append((entry, sr.operations_by_key[entry.key], lexical))
            self.rows[q], self.meta[q] = rows, (unigrams, exp.all)

    def ranked(self, query, rp, limit=5):
        if query not in self.rows or not any(ch.isspace() for ch in query.strip()):
            with mock.patch.object(policy, "ranking", return_value=rp), mock.patch.object(policy, "aliases", return_value=self.ap):
                return _search_fn(self.state)(query)
        unigrams, exp_all = self.meta[query]
        intent = self.S.method_intent(unigrams, rp.verb_methods)
        cands = []
        for entry, op, lexical in self.rows[query]:
            structural, _ = self.S._structural_signals(entry, unigrams, exp_all, rp, intent)
            final = max(lexical + structural, 0.0) * (self.S.DEPRECATED_FACTOR if op.deprecated else 1.0)
            if final == 0.0:
                continue
            cands.append((final, op.deprecated, op.key))
        cands.sort(key=lambda c: (-c[0], c[1], c[2]))
        return [c[2] for c in cands[:limit]], bool(intent[1])


def evaluate_point_fast(ge, rp, point, bench):
    rpp = ranking_with(rp, point); fn = lambda q: ge.ranked(q, rpp)
    return evaluate(bench["seed"], fn, section="seed"), evaluate(bench["regression_negative"], fn, section="regression_negative")


def fixture_failures_fast(ge, rp, point, bench_r0) -> list:
    rpp = ranking_with(rp, point); fn = lambda q: ge.ranked(q, rpp)
    s, r = evaluate(bench_r0["seed"], fn), evaluate(bench_r0["regression_negative"], fn)
    return sorted(f["id"] for f in s["failed"] + r["failed"])
```

`write_constants`: `rows = (CONSTANT_KEYS[:2], CONSTANT_KEYS[2:5], CONSTANT_KEYS[5:6], CONSTANT_KEYS[6:])` (the H1 layout). `ranking_with` unchanged.

- [ ] **Step 4: Implement — proposer, validator, hashes**

```python
def round_note(word, sid, target) -> dict:
    return {"origin": f"round{ROUND}", "seed_query_id": sid, "candidate_word": word, "failure_classes": ["R6"],
            "evidence": f"alias {word} -> {target} for {sid} (frozen candidate, deterministic atomic-action proposer)"}


def atomic_actions(cands, sid, working) -> list:
    """spec §6: this seed's (candidate_word, target) pairs in tuple order; words already aliased in the working state excluded."""
    return sorted((w, t) for w, c in cands.items() if sid in c["seed_ids"] and w not in working["aliases"] for t in c["targets_by_seed"][sid])


def trial_order(actions) -> list:
    """size-1 actions in tuple order, then size-2 combinations with DISTINCT candidate words in tuple order."""
    return [(a,) for a in actions] + [(a, b) for a, b in itertools.combinations(actions, 2) if a[0] != b[0]]


def apply_actions(working, actions, sid):
    trial = copy.deepcopy(working)
    for word, target in actions:
        trial["aliases"][word] = [target]; trial["notes"][word] = round_note(word, sid, target)
    return trial


def propose_aliases(eval_fn, bench, base_raw, cands, budget=BUDGET, per_seed=PER_SEED, fixture_fn=None):
    """spec §6 atomic-action contract: seeds in id order; each seed re-evaluated against the working state first
    (resolved_by_prior_change); seeds without R6 skipped; trials in trial_order(); every trial starts from the current working
    snapshot (failed trials are not accumulated); the first trial that fixes the seed without breaking a passing seed, a
    regression record (effective) or the fixture suite is committed. <= per_seed actions per seed, <= budget in total. Direct
    aliases only (no rules, spec §2)."""
    working = copy.deepcopy(base_raw)
    seed_fail, _ = eval_fn(working)
    patch = {"resolved_by_prior_change": [], "not_r6": [], "unresolved": [], "fixture_fail": [], "trials": 0, "actions_by_seed": {}}
    accepted_n, by_id = 0, {r["id"]: r for r in bench["seed"]}

    def ok(trial, sid, cur_fail, cur_reg, desc):
        patch["trials"] += 1
        f, r = eval_fn(trial)
        if not (sid not in f and f <= (cur_fail - {sid}) and r <= cur_reg):
            return False
        bad = list(fixture_fn(trial)) if fixture_fn is not None else []
        if bad:
            patch["fixture_fail"].append({**desc, "seed_query_id": sid, "failing": bad})
        return not bad

    for sid in sorted(seed_fail):
        cur_fail, cur_reg = eval_fn(working)
        if sid not in cur_fail:
            patch["resolved_by_prior_change"].append(sid); continue
        if "R6" not in (by_id[sid].get("failure_classes") or ()):
            patch["not_r6"].append(sid); continue
        found = None
        for combo in trial_order(atomic_actions(cands, sid, working)):
            if len(combo) > per_seed or accepted_n + len(combo) > budget:
                continue
            trial = apply_actions(working, combo, sid)
            if ok(trial, sid, cur_fail, cur_reg, {"kind": "alias", "actions": [list(a) for a in combo]}):
                found = (trial, combo); break
        if found is None:
            patch["unresolved"].append(sid); continue
        working, accepted_n = found[0], accepted_n + len(found[1])
        patch["actions_by_seed"][sid] = [list(a) for a in found[1]]
    patch.update(alias_patch(base_raw, working))
    return working, patch
```

`validate_alias_change(before_raw, after_raw, cands, queries, classes, budget=BUDGET, per_seed=PER_SEED)`: keep the Round 2 checks; add right after `added = alias_patch(...)`: `if added["rules"]: out.append("rules are not proposed in Round 3 (direct aliases only)")`; the final per-seed line becomes `out += [f"more than two atomic actions for seed {sid}: {n}" for sid, n in sorted(per_seed_counts.items()) if n > per_seed]`.

```python
def baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench, root=ROOT) -> str:
    """spec §5.5 v1.13: the whole input of tune_round3 — B aliases/ranking, S, frozen candidates, seed/regression benches, the r0
    fixture bench, the evaluation code and the final grid."""
    fx = fixture_bench(bench)
    return policy.canonical_sha256({"b_aliases_sha256": policy.canonical_sha256(aliases_raw), "b_ranking_sha256": policy.canonical_sha256(ranking_raw),
                                    "snapshot_registry_fingerprint": fp, "alias_candidates_sha256": policy.canonical_sha256(cands_doc),
                                    "seed_benchmark_sha256": policy.canonical_sha256(bench["seed"]),
                                    "regression_benchmark_sha256": policy.canonical_sha256(bench["regression_negative"]),
                                    "fixture_benchmark_sha256": policy.canonical_sha256(fx),
                                    "evaluation_code_sha256": ev.evaluation_code_sha256(root), "tuning_grid_sha256": ev.tuning_grid_sha256(ranking_raw)})


def tuning_accept(seed_res, reg_res, fixture_final) -> bool:
    """spec §5.5 v1.13: seed 39/39 ∧ regression_effective 14/14 ∧ fixture positive 23/23 ∧ fixture negative raw 6/6."""
    return seed_res["passed"] == SEED_TOTAL and reg_res["effective_passed"] == REGRESSION_TOTAL and not fixture_final
```

- [ ] **Step 5: Implement — pipeline wiring, log line, `--verify`**

In `main()`'s `body(state)`:

```python
        b_sha = policy.canonical_sha256(aliases_raw)
        queries = [r["query"] for r in bench["seed"] + bench["regression_negative"]]
        fx_state, fx_bench = fixture_state(), fixture_bench(bench)
        ge, ge_fx = GridEvaluator(state, queries, _alias_policy(aliases_raw)), GridEvaluator(fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]], _alias_policy(aliases_raw))
        def evaluate_fn(point, raw):                    # grid stage (B aliases): memoized; proposer trials / final: production path
            return evaluate_point_fast(ge, rp, point, bench) if policy.canonical_sha256(raw) == b_sha else evaluate_point(state, rp, point, bench, _alias_policy(raw))
        def fixture_fn(point, raw):
            return fixture_failures_fast(ge_fx, rp, point, fx_bench) if policy.canonical_sha256(raw) == b_sha else fixture_failures(fx_state, rp, point, fx_bench, _alias_policy(raw))
        t0 = time.perf_counter()
        results, selected, working, patch, seed_res, reg_res, fixture_fail = run_pipeline(evaluate_fn, bench, aliases_raw, cands_doc, rp.tuning_grid, dict(rp.baseline), fixture_fn)
        grid_runtime = time.perf_counter() - t0
        fixture_diag = fixture_negative_diagnostic(fx_state, rp, selected, fx_bench, _alias_policy(working))   # AC-R3-11a diagnostic, final config
        slow_s, slow_r = evaluate_point(state, rp, selected, bench, _alias_policy(aliases_raw))         # cross-check the memoized path once
        fast_s, fast_r = evaluate_point_fast(ge, rp, selected, bench)
        if (slow_s["passed"], slow_r["passed"], slow_r["raw_passed"]) != (fast_s["passed"], fast_r["passed"], fast_r["raw_passed"]):
            raise SystemExit("error: memoized grid evaluator disagrees with search_operations at the selected point")
```

(`import time`; `run_pipeline` itself is unchanged except that `results` rows carry the effective regression count, which `evaluate` now returns as `passed` for the `regression_negative` section; its final `seed_res, reg_res = evaluate_fn(selected, working)` now runs the production path because `working != B`.) `_finish(args, rp, fp, results, selected, patch, working, seed_res, reg_res, base_sha, fixture_fail, grid_runtime, fixture_diag)`:

```python
    accept = tuning_accept(seed_res, reg_res, fixture_fail["final"])
    effects = plan_effects(args.dry_run, accept)
    pos_fail = [i for i in fixture_fail["final"] if i.startswith("s-")]; neg_fail = [i for i in fixture_fail["final"] if i.startswith("rn-")]
    line = {..., "constants_selected": selected, "grid_size": len(results) + len(fixture_fail["constants"]), "grid_runtime_s": round(grid_runtime, 1),
            "fixture_fail": fixture_fail, "passing_combos": sum(1 for _, s, r in results if s == SEED_TOTAL and r == REGRESSION_TOTAL),
            "aliases_proposed": patch, "seed": f"{seed_res['passed']}/{SEED_TOTAL}",
            "regression_negative": f"{reg_res['effective_passed']}/{REGRESSION_TOTAL}", "regression_raw": f"{reg_res['raw_passed']}/{REGRESSION_TOTAL}",
            "fixture_positive": f"{FIXTURE_COUNTS[0] - len(pos_fail)}/{FIXTURE_COUNTS[0]}", "fixture_negative_raw": f"{FIXTURE_COUNTS[1] - len(neg_fail)}/{FIXTURE_COUNTS[1]}",
            "fixture_negative_effective_diagnostic": f"{fixture_diag['effective_passed']}/{FIXTURE_COUNTS[1]}",
            "tuning_accept": accept, "tuning_failed": not accept, ...}
    line["status"], line["adopted"] = ("pending" if accept else "failed"), False
    ... return 0 if accept else 1
```

(`tuning_valid := tuning_accept`; AC-valid is decided by `--adopt` after the canonical suite, `--reject` after a red suite — unchanged two-stage adoption.) `_verify`: after computing `adopted, rejected`, add `failed = [l for l in log if l["status"] == "failed"]`; the branch selection becomes: exactly one adopted → success; exactly one rejected → abort; no adopted/rejected and `failed` → failure branch with `target = failed[0]`, requiring `len({l["result_sha256"] for l in failed}) == 1` (else `print(error); return 2`), `consts = dict(target["constants_selected"])`, policy files at B (`baseline_mismatch == []` and no round3 delta, as on the abort branch); otherwise error exit 2. The replay comparison is unchanged (`verify_replay` at `consts` against `target["result_sha256"]`).

`require_round(min_round=3)` default (the Round 3 log/paths exist only after the Round 3 freeze entry).

- [ ] **Step 6: Run the full suite, commit**

Run: `python -m unittest discover -s tests -t .` → OK (`TestGridEvaluator` takes ~20 s on the fixture registry).

```bash
git add tests/tune_search_ranking.py tests/test_tune_search_ranking.py
git commit -m "H7: tuning pipeline — 8 constants, conservative selector, memoized grid evaluator, budget-2 atomic-action proposer, tuning_accept, failure-branch verify

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Diagnostic raw/effective + reference block, `round3_simulation.py` (synthetic lifecycle, binding pre-T checkpoint), whole-branch review (commit H8 = `housekeeping_commit`)

**Files:**
- Modify: `tests/diag_search_queries.py` (`fn`, `_evaluate`, `--reference/--reference-round/--append-to`)
- Create: `tests/benchmarks/round3_simulation.py`, `tests/benchmarks/test_round3_simulation.py`
- Modify: `tests/benchmarks/evaluator.py` (`TOOLING_FILES` += the two new files), `tests/benchmarks/test_evaluator.py` (guarded `TestRound3FinalArtifact`)
- Test: `tests/test_diag_search_queries.py`

**Interfaces:**
- Produces: diag report fields `evaluation_domain: "actionable recommendation queries"`, `policy_version`, `tuning_grid_sha256`, per-set evaluator dicts (`raw_passed`/`effective_passed` on negative sets, `actionable`/`abstained` sub-dicts), `negative_actionable`, `negative_abstained`, failures with `actionable`; CLI mode `--reference PLAIN --reference-round N --append-to ARTIFACT [--cache-dir S]` that appends `reference_round{N}` (`held_out`/`negative` evaluator dicts over valid-key records, `invalid_key: [{id, keys}]`, `plaintext_sha256`, `enc_sha256` from the current freeze's `reference_set`) to an existing artifact whose `git_commit` is HEAD, without evaluating the current round's sets. `round3_simulation.py --phase pre-T --cache-dir S --work DIR` (binding AC-R3-01; appends `pre_t_checkpoint` to `DIR/controller-events.jsonl`; exit 0 iff seed ≥ 36/39, fixture failing == [], regression raw ≥ 10/14, effective == 14/14 **and** the memoized-evaluator preflight passes: `random.Random(20261005).sample(grid_points, 20)` plus the baseline point, every seed/regression query on S and every fixture query on the fixture registry, `GridEvaluator.ranked == search_operations` keys and `actionable` exactly — `equivalence_mismatches: []` in the event); `--phase H` (synthetic T→B then C→D / F / X on throwaway copies, full suite after each; `ALL STEPS PASS`); `round3_simulation.pre_t_verdict(seed_passed, reg_raw, reg_eff, fixture_failing) -> bool`; `round3_simulation.synthetic_hidden_records(internal, verb_methods) -> plain`.
- Consumes: Tasks 1–7.

- [ ] **Step 1: Write the failing tests**

`tests/test_diag_search_queries.py` — in `setUpClass` give the plaintext held_out fixtures verb-bearing queries (e.g. `"get the issue attachment"` → the attachment op) so `section="held_out"` passes; then add:

```python
    def test_round3_report_fields_raw_effective_and_actionable_failures(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path))
        self.assertEqual(rep["evaluation_domain"], "actionable recommendation queries"); self.assertEqual(rep["policy_version"], 4)
        self.assertEqual(rep["tuning_grid_sha256"], ev.tuning_grid_sha256(json.loads((diag.policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))))
        for name in ("regression_negative", "negative"):
            self.assertEqual(set(rep["sets"][name]) >= {"passed", "raw_passed", "effective_passed", "actionable", "abstained"}, True, name)
        self.assertEqual(rep["negative_actionable"], rep["sets"]["negative"]["actionable"]); self.assertEqual(rep["negative_abstained"], rep["sets"]["negative"]["abstained"])
        plain = {"held_out": [{**self.plain["held_out"][0], "query": "issue attachment details"}], "negative": []}      # verb-less held_out fails as abstained
        p = self.tmp / "abstained.json"; p.write_text(json.dumps(plain), encoding="utf-8")
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(p), "--sets", "held_out")
        self.assertEqual(rep["sets"]["held_out"]["passed"], 0); self.assertEqual(rep["failures"][0]["actionable"], False); self.assertTrue(rep["failures"][0]["raw_ok"])
        self.assertEqual(set(rep["failures"][0]["top5"][0]["signals"]) >= {"method_order", "path_coverage"}, True)

    def test_reference_block_is_appended_once_and_only_to_the_current_artifact(self):
        out = self.tmp / "final.json"
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path), "--json", str(out))
        ref = {"held_out": [self.plain["held_out"][0], {**self.plain["held_out"][0], "id": "h-099", "expected_top1_any": ["nope:GET:/x"]}], "negative": list(self.plain["negative"])}
        rp = self.tmp / "ref.json"; rp.write_text(json.dumps(ref), encoding="utf-8")
        code, _ = self.run_diag("--bench-file", str(self.good_bench), "--reference", str(rp), "--reference-round", "1", "--append-to", str(out))
        self.assertEqual(code, 0)
        art = json.loads(out.read_text(encoding="utf-8")); blk = art["reference_round1"]
        self.assertEqual(blk["invalid_key"], [{"id": "h-099", "keys": ["nope:GET:/x"]}]); self.assertEqual(blk["held_out"]["total"], 1)
        self.assertEqual(set(blk["negative"]) >= {"raw_passed", "effective_passed"}, True); self.assertEqual(set(blk["plaintext_sha256"]), {"held_out", "negative"})
        self.assertEqual(art["sets"], rep["sets"])                                                                  # current-round results untouched
        code2, _ = self.run_diag("--bench-file", str(self.good_bench), "--reference", str(rp), "--reference-round", "1", "--append-to", str(out))
        self.assertEqual(code2, 2)                                                                                  # second append refused
```

`tests/benchmarks/test_round3_simulation.py`:

```python
import json, pathlib, tempfile, unittest
from tests.benchmarks import round3_simulation as sim, round_seal as rs
from tests.test_diag_search_queries import build_fixture_cache


class TestPreTVerdict(unittest.TestCase):
    def test_thresholds(self):
        self.assertTrue(sim.pre_t_verdict(36, 10, 14, [])); self.assertTrue(sim.pre_t_verdict(39, 14, 14, []))
        self.assertFalse(sim.pre_t_verdict(35, 10, 14, [])); self.assertFalse(sim.pre_t_verdict(36, 9, 14, []))
        self.assertFalse(sim.pre_t_verdict(36, 10, 13, [])); self.assertFalse(sim.pre_t_verdict(36, 10, 14, ["rn-003"]))

    def test_event_shape(self):
        e = sim.pre_t_event({"passed": 36}, {"raw_passed": 10, "effective_passed": 14}, [], {"ranking_sha256": "a"}, at="2026-10-06T00:00:00Z")
        self.assertEqual(e["event"], "pre_t_checkpoint"); self.assertTrue(e["pass"])
        self.assertEqual(set(e) >= {"seed", "regression_raw", "regression_effective", "fixture_failing", "inputs", "at"}, True)


class TestSyntheticHidden(unittest.TestCase):
    def test_synthetic_records_pass_round3_machine_check_on_fixture_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            cache = pathlib.Path(td) / "cache"; build_fixture_cache(cache)
            _, internal, _, _ = rs.load_catalogs_from_cache(cache, 3)
        vm = json.loads((sim.ROOT / "tools/atlassian_docs/intelligence/data/search_ranking.json").read_text(encoding="utf-8"))["verb_methods"]
        plain = sim.synthetic_hidden_records(internal, vm)
        bench = json.loads((sim.ROOT / "tests/benchmarks/search_queries.json").read_text(encoding="utf-8"))
        self.assertEqual(rs.machine_check(plain, bench, internal, round=3, verb_methods=vm), [])
        self.assertEqual(rs.negative_distribution(plain["negative"], vm), (4, 4))
```

Guarded `TestRound3FinalArtifact` in `test_evaluator.py` (mirrors `TestRound2FinalArtifact`, file `round3-final.json`): `round == 3`, sealed shas == `round3_seal`, `evaluation_code_sha256 == freeze_for(3)["evaluation_code_sha256_at_T"]`, `tuning_grid_sha256 == freeze_for(3)["tuning_grid_sha256"]`, `sets.negative` has `raw_passed`/`effective_passed`, `negative_actionable.total == 4 == negative_abstained.total`, `reference_round2` present with `invalid_key` list and `enc_sha256 == freeze_for(3)["reference_set"]["enc_sha256"]`, `evaluation_domain` set.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_diag_search_queries tests.benchmarks.test_round3_simulation 2>&1 | tail -5` → FAIL/ERROR.

- [ ] **Step 3: Implement the diagnostic**

In `diag_search_queries.py`: `fn(q)` returns `(keys, out["actionable"])` (keep `ranked[q] = keys`); `_evaluate` uses `ev.evaluate(sections[name], fn, section=name)`; the report gains `"evaluation_domain": "actionable recommendation queries"`, `"policy_version": policy.POLICY_VERSIONS["search"]`, `"tuning_grid_sha256": ev.tuning_grid_sha256(json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8")))`; after evaluating `negative`: `report["negative_actionable"], report["negative_abstained"] = res["actionable"], res["abstained"]` (both `None` in the initial report); the per-set print shows `effective x/n (raw y/n)` for negative sets. New arguments `--reference PATH`, `--reference-round N`, `--append-to PATH`; when `--reference` is given `run()` branches to:

```python
def _append_reference(state, args, bench):
    art_path = args.append_to; art = json.loads(art_path.read_text(encoding="utf-8"))
    key = f"reference_round{args.reference_round}"
    if art.get("git_commit") != _git("rev-parse", "HEAD") or art.get("registry_fingerprint") != state.registry.fingerprint or key in art:
        print(f"error: {art_path} is not the current artifact or already has {key}", file=sys.stderr); return 2, art
    plain = json.loads(args.reference.expanduser().read_text(encoding="utf-8"))
    for name in HIDDEN_SETS:
        ev.check_schema(name, plain[name])
        for rec in plain[name]:
            if rec.get("origin") != f"{name}-r{args.reference_round}":
                print(f"error: {name}/{rec.get('id')}: origin {rec.get('origin')!r} != {name}-r{args.reference_round}", file=sys.stderr); return 2, art
    keys = {op.key for sr in state.registry.sources.values() for op in sr.operations}
    fn = lambda q: (lambda out: ([r["key"] for r in out.get("results", [])], out["actionable"]))(search_operations(state, q, limit=5))
    block, invalid = {}, []
    for name in HIDDEN_SETS:
        valid = []
        for rec in plain[name]:
            bad = [k for k in rec["expected_top1_any"] + rec["forbidden_top1"] if k not in keys]
            (invalid.append({"id": rec["id"], "keys": bad}) if bad else valid.append(rec))
        block[name] = ev.evaluate(valid, fn, section=name)
    block["invalid_key"] = invalid
    block["plaintext_sha256"] = {n: ev.canonical_sha256(plain[n]) for n in HIDDEN_SETS}
    block["enc_sha256"] = (ev.current_round().get("reference_set") or {}).get("enc_sha256")
    art[key] = block
    art_path.write_text(json.dumps(art, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0, art
```

(wired inside the same `with tempfile.TemporaryDirectory()`/`storage.CACHE_DIR` block as `_evaluate`, replacing the normal evaluation entirely when `--reference` is given; the current round's hidden sets are never touched.)

- [ ] **Step 4: Implement `tests/benchmarks/round3_simulation.py`**

Generalize `round2_simulation.py` (module constants `ROUND = 3`, `SIM_DIR = ".round3-sim"`, synthetic alias word `zzsynthetic -> issue` as `lexicon-r3`), with:

```python
def pre_t_verdict(seed_passed, reg_raw, reg_eff, fixture_failing) -> bool:
    """AC-R3-01: seed >= 36/39, fixture 23/23 · 6/6 (raw), regression raw >= 10/14, effective == 14/14."""
    return seed_passed >= 36 and reg_raw >= 10 and reg_eff == 14 and not fixture_failing


def pre_t_event(seed_res, reg_res, fixture_failing, inputs, at=None) -> dict:
    return {"event": "pre_t_checkpoint", "seed": seed_res["passed"], "regression_raw": reg_res["raw_passed"], "regression_effective": reg_res["effective_passed"],
            "fixture_failing": list(fixture_failing), "inputs": inputs, "pass": pre_t_verdict(seed_res["passed"], reg_res["raw_passed"], reg_res["effective_passed"], fixture_failing),
            "at": at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def equivalence_mismatches(state, rp, bench, ap, n=20, seed=20261005) -> list:
    """spec §5 v1.14 preflight: the memoized grid evaluator must rank exactly like search_operations on the ACTUAL S and fixture
    registry for a deterministic sample of grid points (plus the baseline) and every seed/regression/fixture query."""
    import random
    from unittest import mock
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy, search
    pts = random.Random(seed).sample(tune.grid_points(rp.tuning_grid), n) + [dict(rp.baseline)]
    fx_state, fx_bench = tune.fixture_state(), tune.fixture_bench(bench)
    pairs = [(state, [r["query"] for r in bench["seed"] + bench["regression_negative"]]), (fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]])]
    out = []
    for st, queries in pairs:
        ge = tune.GridEvaluator(st, queries, ap)
        for p in pts:
            rpp = tune.ranking_with(rp, p)
            with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=ap):
                for q in queries:
                    o = search.search_operations(st, q, limit=5)
                    if ge.ranked(q, rpp) != ([r["key"] for r in o["results"]], o["actionable"]):
                        out.append({"point": p, "query": q})
    return out


def run_pre_t(cache: pathlib.Path, work: pathlib.Path) -> int:
    """Binding checkpoint on the EXACT working-tree policy (ranking, aliases, inventory) against S; appends the event to the ledger."""
    from tests import tune_search_ranking as tune
    from tests.benchmarks import evaluator as ev, round_seal as rs
    from tools.atlassian_docs.intelligence import policy
    rp, bench = policy.load_ranking(tune.RANKING_PATH), tune._BENCH
    aliases_raw, ranking_raw = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    ap = tune._alias_policy(aliases_raw)
    def body(state):
        s, r = tune.evaluate_point(state, rp, dict(rp.constants), bench, ap)
        return s, r, state.registry.fingerprint, {n: p.active_spec_sha256 for n, p in state.provenance.items()}
    seed_res, reg_res, fp, spec = tune._with_state(cache, body)
    failing = tune.fixture_failures(tune.fixture_state(), rp, dict(rp.constants), tune.fixture_bench(bench), ap)
    inputs = {"ranking_sha256": policy.canonical_sha256(ranking_raw), "aliases_sha256": policy.canonical_sha256(aliases_raw),
              "verb_inventory_sha256": policy.canonical_sha256(ranking_raw["verb_methods"]), "registry_fingerprint": fp, "spec_sha256": spec,
              "fixture_benchmark_sha256": policy.canonical_sha256(tune.fixture_bench(bench)), "evaluation_code_sha256": ev.evaluation_code_sha256(ROOT),
              "tuning_grid_sha256": ev.tuning_grid_sha256(ranking_raw)}
    e = pre_t_event(seed_res, reg_res, failing, inputs)
    e["equivalence_mismatches"] = tune._with_state(cache, lambda state: equivalence_mismatches(state, rp, bench, ap))
    e["pass"] = e["pass"] and not e["equivalence_mismatches"]
    work.mkdir(parents=True, exist_ok=True)
    with open(work / "controller-events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(e) + "\n")
    print(json.dumps(e, indent=1)); return 0 if e["pass"] else 1
```

`synthetic_hidden_records(internal, verb_methods)`: deterministic over the fixture catalog — pick 16 operations satisfying `MIN_SOURCE`/`MIN_METHOD`, build queries `"<verb> probe <word> record"` with `verb = {"GET": "show", "POST": "create", "PUT": "update", "DELETE": "delete"}[method]` (all in the live inventory with that single method), four of them prefixed by `jira`/`confluence` to satisfy `product_named`, the rest unnamed; negatives: 4 actionable `"<verb> decoy <word> record"` whose `forbidden_top1` op has that verb's method, 4 verb-less `"decoy <word> record"`; the NATO word list of `round2_simulation.py` keeps every query distinct. The function asserts `rs.machine_check(..., round=3, verb_methods=...) == []` before returning. `--phase H`: `apply_T` (synthetic lexicon-r3 merge, `candidates --round 3`, classify, synthetic `round3-worker-brief.md`/prompts containing the two placeholders, synthetic `round2-sealed.json.enc` bytes in `SIM_DIR`, `rs.main(["freeze", "--round", "3", "--cache-dir", cache, "--reference-enc", enc])`), `apply_B` (seal metadata over the synthetic records, `round3_seal`), then the tree is copied three times: `apply_C` + `apply_D` (adopted line with the Round 3 fields, `diag --round 3 --bench plain --json tests/benchmarks/round3-final.json`, then `--reference` append with a synthetic r2 plain), `apply_F` (one `failed` line, `tuning_accept: false`), `apply_X` (one `rejected` line with `reject_evidence`, policy at B). The canonical suite runs after every step; the driver prints `ALL STEPS PASS` only when every run is green. `TOOLING_FILES` += `tests/benchmarks/round3_simulation.py`, `tests/benchmarks/test_round3_simulation.py`.

- [ ] **Step 5: Run the full suite and the H sanity simulation**

```bash
python -m unittest discover -s tests -t .                 # OK
python tests/benchmarks/round3_simulation.py --phase H    # ALL STEPS PASS (T, B, C, D, F, X)
```

- [ ] **Step 6: Commit H8, then the whole-branch review**

```bash
git add tests/diag_search_queries.py tests/test_diag_search_queries.py tests/benchmarks/round3_simulation.py tests/benchmarks/test_round3_simulation.py tests/benchmarks/evaluator.py tests/benchmarks/test_evaluator.py
git commit -m "H8: diag raw/effective + reference block, round3_simulation (binding pre-T checkpoint, synthetic D/F/X lifecycle)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Dispatch the whole-branch code reviewer (most capable model) over `e16c073..HEAD` with the spec v1.15 and this plan (v3); fix findings as H′ commits; re-run the suite and `--phase H`. The last green commit is **`housekeeping_commit`**. Record its sha, the suite count and the `ALL STEPS PASS` output in the SDD ledger; the controller later pins it as `$W/housekeeping_commit` (Task 9 Step 1). Measure once more on this machine: `python - <<'EOF'` timing 40 random grid points through `GridEvaluator` on the archived S2 (the probe used while writing this plan gave 0.0454 s/point) and ledger `grid_runtime_probe` (machine, Python, s/point, projected minutes for 23,328 points). From here `TOOLING_FILES` are immutable until the terminal commit.

---

### Task 9: **[controller — fresh session]** Source snapshot S and verb inventory finalization (prefix-invariant suffixes only)

**Files:**
- Create (outside repo): `~/.atlassian_api_updater/round3-cache/` (S), `~/.atlassian_api_updater/round3-work/{controller-events,attempts}.jsonl`
- Modify: `tools/atlassian_docs/intelligence/data/search_ranking.json` (`verb_methods` suffixes only — left uncommitted until T)
- Create: `tests/benchmarks/round3-method-safety.json` (committed at T)

The controller session for Tasks 9–17 must be a new session (Global Constraints, AC-R3-08); ledger its session id as `controller_actor_id` in the first event.

- [ ] **Step 1: Create S (reuse the archived S2 only if identical to a fresh fetch)**

```bash
test ! -e ~/.atlassian_api_updater/round3-cache || { echo "S exists"; exit 1; }
mkdir -p ~/.atlassian_api_updater/round3-work
test -z "$(git status --porcelain --untracked-files=no)" || { echo "dirty tree"; exit 1; }
git rev-parse HEAD > ~/.atlassian_api_updater/round3-work/housekeeping_commit      # HEAD == the reviewed last H/H′ commit (branch round3)
python -m tools.atlassian_docs                                                    # refresh the live cache once (network)
python tests/benchmarks/round_seal.py catalog --round 3 --cache-dir "$(python -c 'from tools.atlassian_docs import storage; print(storage.CACHE_DIR)')" \
  --out /tmp/live-gen.json --internal-out /tmp/live-internal.json                 # prints registry_fingerprint + 3 spec shas of the live cache
```

If the printed fingerprint is `f3c2e9d48aa85c96ca62cdd84ff700cc2714c888cf4148b3a91c604c45b47b62` **and** the three spec shas equal the archived round 2 freeze values (`confluence b3d010b6438677d864495ce15828f57080ff72afe190efdf7f86f0f5140b700d`, `jira-platform 3d0edfb02ff91873f99421de579182b6d66f07b804063e9ae458a30d6901a2db`, `jira-software cb7e24b331ad9b31944fa9a588f70d4ea60d74d1dfb52d39a59770230b79207a`): `cp -R ~/.atlassian_api_updater/archive/round2/round2-cache ~/.atlassian_api_updater/round3-cache` and ledger `{"event": "s_created", "s_reused_from_round2": true, ...}`; otherwise copy the live cache and ledger `s_reused_from_round2: false`. Then:

```bash
S=~/.atlassian_api_updater/round3-cache; W=~/.atlassian_api_updater/round3-work
python tests/benchmarks/round_seal.py catalog --round 3 --cache-dir $S --out $W/round3-generator-catalog.json --internal-out $W/round3-internal-catalog.json
```

Ledger `registry_fingerprint`, the three `spec_sha256`, operation count. `export ATLASSIAN_DOCS_ROUND3_CACHE=$S` for the rest of the procedure.

- [ ] **Step 2: Verb report and method-safety — suffix-only fixed point**

```bash
python tests/benchmarks/alias_candidates_tool.py verb-report    --cache-dir $S --out $W/verb_report.json
python tests/benchmarks/alias_candidates_tool.py method-safety  --cache-dir $S --out tests/benchmarks/round3-method-safety.json
python tests/benchmarks/alias_candidates_tool.py verb-prefix-check
```

Rule (fixed point): a `VIOLATION` (allowed set excludes the expected method) is fixed by **appending** the missing method to that verb's list (never removing or reordering; several additions sorted by method name), then both commands and `verb-prefix-check` are re-run; finalize only when a full pass ends with the inventory unchanged, `violations == 0` and `prefix ok`. `REVIEW` lines are diagnostic; every widen/no-widen decision is ledgered. If a widening would require removing a method (impossible under the prefix invariant) STOP and ask the user (spec §5).

- [ ] **Step 3: Fixture-compatibility check (narrow-only, Round 2 rule)**

`python -m unittest tests.intelligence.test_search tests.test_diag_search_queries`. If a suffix breaks an r0 fixture, the suffix is removed (that is the only "narrowing" the prefix invariant allows); if method-safety needs that same suffix, STOP and ask the user. Ledger every decision with the failing fixture id.

- [ ] **Step 4: Finalize**

```bash
python -c "import json; from tests.benchmarks.evaluator import canonical_sha256 as c; print(c(json.load(open('tools/atlassian_docs/intelligence/data/search_ranking.json'))['verb_methods']))"
```

Ledger `verb_inventory_sha256` and the sha of `tests/benchmarks/round3-method-safety.json`. **From here the inventory does not change.** Leave the change uncommitted: pre-T data changes are committed once, as T (AC-01a). (If no suffix was needed, `verb_inventory_sha256` equals Round 2's `d66317db…`; ledger that explicitly.)

---

### Task 10: **[controller]** Concept lexicon — re-gate the archived Round 2 generation/review (no ChatGPT call)

**Files:**
- Modify: `tools/atlassian_docs/intelligence/data/concept_lexicon.json` (Round 3 document), `search_aliases.json` (lexicon-r3 merge only)

- [ ] **Step 1: Verify the archived inputs**

```bash
A=~/.atlassian_api_updater/archive/round2/round2-work
shasum -a 256 $A/lexicon_raw.json $A/lexicon_review.json $A/lexicon-generation-input.txt $A/lexicon-review-input.txt
```

Expected: `lexicon_raw.json acc5cebeafc5c48236a9de5d685b888fb2a83532340405556d77b801468a6872`, `lexicon_review.json c5ba256f8acd082febe06724d6646bff631e136dc437f4fa1528286117bd62f4`, `lexicon-generation-input.txt 9125fa8444453762076cdb5c6791f166f46a15579fd016bfcbb8cd4412bd857e`, `lexicon-review-input.txt 17efa0b87647cf89357fffe3c2aaf2f0effb24539ce1c44b399a0a574eb3a484`. Any mismatch → stop (spec §5: the inputs must equal the Round 2 ledger).

- [ ] **Step 2: Re-gate with the Round 3 target rule**

```bash
cp tools/atlassian_docs/intelligence/data/search_aliases.json $W/aliases-premerge.json
cp tests/benchmarks/search_queries.json $W/bench-preclassify.json
python tests/benchmarks/concept_lexicon_check.py prepare --cache-dir $S --round 3 --raw $A/lexicon_raw.json --out $W/lexicon_structural.json
python tests/benchmarks/concept_lexicon_check.py finalize --cache-dir $S --round 3 --raw $A/lexicon_raw.json --structural $W/lexicon_structural.json \
  --review $A/lexicon_review.json --generation-input $A/lexicon-generation-input.txt --review-input $A/lexicon-review-input.txt \
  --template tests/benchmarks/round2-lexicon-generation-prompt.md --out tools/atlassian_docs/intelligence/data/concept_lexicon.json
python tests/benchmarks/alias_candidates_tool.py lexicon-gate --cache-dir $S --round 3 --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json
python tests/benchmarks/concept_lexicon_check.py merge --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json --aliases tools/atlassian_docs/intelligence/data/search_aliases.json --round 3
python -m unittest discover -s tests -t .
```

`prepare`'s structural stage rejects synonyms already in the alias file (`alias_conflict`) — the 462 `lexicon-r2` words are therefore excluded from the Round 3 document and `merge` adds only words that were seed-gate-rejected in Round 2 and now pass (expected at least `feedback`, `iteration`; `release`, `summary`, `fresh`, `new` stay rejected unless their targets appear in a seed's resource vocabulary). Ledger: structural kept/rejected by reason, semantic rejected, gate rejected (expected to no longer contain `feedback`/`iteration`), merged count and the words, `lexicon_aliases_sha256(aliases, 3)`.

---

### Task 11: **[controller]** Candidates, R5/R6, AC-13 replay, **binding pre-T checkpoint**, frozen texts, freeze, commit T

**Files:**
- Create: `tools/atlassian_docs/intelligence/data/alias_candidates.json` (round 3)
- Modify: `tests/benchmarks/search_queries.json` (seed `failure_classes` only)
- Create: `tests/benchmarks/round3-worker-brief.md`, `tests/benchmarks/round3-hidden-generation-prompt.md`, `tests/benchmarks/round3-hidden-reviewer-prompt.md`
- Modify: `tests/benchmarks/round_freeze.json` (append the round 3 entry)

- [ ] **Step 1: Candidates and classification**

```bash
python tests/benchmarks/alias_candidates_tool.py candidates --cache-dir $S --round 3 --bench $W/bench-preclassify.json --out tools/atlassian_docs/intelligence/data/alias_candidates.json
python tests/benchmarks/alias_candidates_tool.py classify   --cache-dir $S --round 3
python -m unittest discover -s tests -t .
```

Ledger the candidate count, `preclassify_bench_sha256`, R5/R6 counts; confirm in the ledger that `comment` ∈ `targets_by_seed["s-024"]` of `feedback` and `sprint` ∈ the s-032 targets (the Round 2 blockers, spec §0).

- [ ] **Step 2: AC-13 deterministic replay (archive inputs, `--round 3`)**

```bash
W=~/.atlassian_api_updater/round3-work; S=~/.atlassian_api_updater/round3-cache; A=~/.atlassian_api_updater/archive/round2/round2-work
python - "$W" "$S" "$A" <<'EOF2'
import json, pathlib, shutil, subprocess, sys, tempfile
from tests.benchmarks import evaluator as ev, alias_candidates_tool as act, round_seal as rs
W, S, A = (pathlib.Path(p).expanduser() for p in sys.argv[1:4]); D = pathlib.Path("tools/atlassian_docs/intelligence/data"); B = pathlib.Path("tests/benchmarks/search_queries.json")
tmp = pathlib.Path(tempfile.mkdtemp(prefix="ac13-"))
run = lambda *a: subprocess.run([sys.executable, *a], check=True, capture_output=True, text=True)
j = lambda p: json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
shutil.copy(D / "search_aliases.json", tmp / "aliases-current.json"); shutil.copy(B, tmp / "bench-current.json")
shutil.copy(W / "aliases-premerge.json", D / "search_aliases.json"); shutil.copy(W / "bench-preclassify.json", B)      # lexicon stage inputs
try:
    run("tests/benchmarks/concept_lexicon_check.py", "prepare", "--cache-dir", str(S), "--round", "3", "--raw", str(A / "lexicon_raw.json"), "--out", str(tmp / "structural.json"))
    run("tests/benchmarks/concept_lexicon_check.py", "finalize", "--cache-dir", str(S), "--round", "3", "--raw", str(A / "lexicon_raw.json"), "--structural", str(tmp / "structural.json"),
        "--review", str(A / "lexicon_review.json"), "--generation-input", str(A / "lexicon-generation-input.txt"), "--review-input", str(A / "lexicon-review-input.txt"),
        "--template", "tests/benchmarks/round2-lexicon-generation-prompt.md", "--out", str(tmp / "lexicon.json"))
    run("tests/benchmarks/alias_candidates_tool.py", "lexicon-gate", "--cache-dir", str(S), "--round", "3", "--lexicon", str(tmp / "lexicon.json"))
    shutil.copy(W / "aliases-premerge.json", tmp / "aliases.json")
    run("tests/benchmarks/concept_lexicon_check.py", "merge", "--lexicon", str(tmp / "lexicon.json"), "--aliases", str(tmp / "aliases.json"), "--round", "3")
finally:
    shutil.copy(tmp / "aliases-current.json", D / "search_aliases.json"); shutil.copy(tmp / "bench-current.json", B)
assert ev.canonical_sha256(j(tmp / "lexicon.json")) == ev.canonical_sha256(j(D / "concept_lexicon.json")), "lexicon replay differs"
assert ev.lexicon_aliases_sha256(j(tmp / "aliases.json"), 3) == ev.lexicon_aliases_sha256(j(D / "search_aliases.json"), 3), "merge replay differs"
run("tests/benchmarks/alias_candidates_tool.py", "candidates", "--cache-dir", str(S), "--round", "3", "--bench", str(W / "bench-preclassify.json"), "--out", str(tmp / "cands.json"))
assert ev.canonical_sha256(j(tmp / "cands.json")) == ev.canonical_sha256(j(D / "alias_candidates.json")), "candidates replay differs"
_, internal, _, _ = rs.load_catalogs_from_cache(S, 3)
bench, ranking, aliases = j(B), j(D / "search_ranking.json"), j(D / "search_aliases.json")
cls = act.classify(bench, internal, ranking, aliases)
for rec in bench["seed"]:
    assert [c for c in rec["failure_classes"] if c in ("R5", "R6")] == cls[rec["id"]], rec["id"]
with open(W / "controller-events.jsonl", "a") as fh:
    fh.write(json.dumps({"event": "ac13_replay", "status": "ok", "lexicon_sha256": ev.canonical_sha256(j(D / "concept_lexicon.json")), "candidates_sha256": ev.canonical_sha256(j(D / "alias_candidates.json"))}) + "\n")
print("AC-13 replay ok")
EOF2
```

A mismatch is a tool defect → H′ → redo Tasks 9–11 from the affected step.

- [ ] **Step 3: Binding pre-T checkpoint (AC-R3-01)**

```bash
python tests/benchmarks/round3_simulation.py --phase pre-T --cache-dir $S --work $W
```

Exit 0 is required to continue: seed ≥ 36/39, fixture failing `[]`, regression raw ≥ 10/14, effective 14/14, and `equivalence_mismatches: []` (memoized grid evaluator == `search_operations` on the actual S, 20 sampled points + baseline, every query); the event carries the input shas (ranking, aliases, verb inventory, S, fixture bench, evaluation code, tuning grid). An equivalence mismatch is a tooling defect → H′. Exit 1 on the thresholds → do not freeze; the structural change is insufficient on the real catalog → report to the user (the spec's expectation came from the archived-S simulation, 36/39).

- [ ] **Step 4: Worker brief (frozen text) — `tests/benchmarks/round3-worker-brief.md`**

```
# Round 3 tuning worker brief (frozen at commit T)

You are the B..C tuning worker. You do not analyse queries, choose constants or choose aliases; the tools do.
Allowed inputs: this file, tests/benchmarks/search_queries.json (seed, regression_negative only), the frozen data files
under tools/atlassian_docs/intelligence/data/, the snapshot at $ATLASSIAN_DOCS_ROUND3_CACHE, and the tuning script.
Forbidden: anything under ~/.atlassian_api_updater/sealed/ or ~/.atlassian_api_updater/archive/, any *.enc file, any ChatGPT page,
docs/phase3-readiness.md.
Acceptance (spec §5.5 v1.15, byte-for-byte): tuning_accept := seed == 39/39 ∧ regression_effective == 14/14 ∧ fixture_positive == 23/23 ∧ fixture_negative_raw == 6/6
regression_raw is recorded only. tuning_accept false -> status "failed" (F). tuning_accept true -> status "pending"; the candidate is
AC-valid (adoptable) only if the canonical full suite then passes (C); a red suite rejects it (X).
Expected wall-clock of step 2: about 18 minutes for the 23,328-point grid (memoized evaluator) plus the proposer trials; do not interrupt it.

Phase 0 (handshake): if your dispatch message is exactly "handshake", write {"worker_actor_id": <your agent id>, "session_id": <your session id or "not_available">}
to ~/.atlassian_api_updater/round3-work/worker-handshake.json, read NO other file, run NO other command, and report the single word
HANDSHAKE. Do not start the procedure below until you receive the message "run the brief procedure".

Procedure (run from the repo root, exactly once; rerun only after a tool error, never after a valid result):
1. git status --porcelain --untracked-files=no   -> must be empty (otherwise stop and report).
2. python tests/tune_search_ranking.py --cache-dir "$ATLASSIAN_DOCS_ROUND3_CACHE" --note "round3 tuning run"
   (prints a JSON line with run_id, status and tuning_accept: "pending" = candidate policy written, "failed" = log only)
3. python -m unittest discover -s tests -t . > ~/.atlassian_api_updater/round3-work/suite-<run_id>.txt 2>&1; echo "exit_code: $?" >> ~/.atlassian_api_updater/round3-work/suite-<run_id>.txt
4. If step 2 exited 0 and the suite exit code is 0:
     python tests/tune_search_ranking.py --adopt <run_id>
     git add tools/atlassian_docs/intelligence/data/search_ranking.json tools/atlassian_docs/intelligence/data/search_aliases.json
             tests/benchmarks/search-tuning-round3.jsonl
     git commit -m "round3: tuning run (one-way pipeline, adopted <run_id>)" + the project trailer.
   If step 2 exited 0 but the suite exit code is not 0:
     python tests/tune_search_ranking.py --reject <run_id> --reason full-suite-failed --evidence ~/.atlassian_api_updater/round3-work/suite-<run_id>.txt
       (stores the failure signature on the log line, then restores the B policy files)
     git add tests/benchmarks/search-tuning-round3.jsonl
     git commit -m "round3: tuning run rejected (full suite failed)" + trailer.
   If step 2 exited 1 (tuning_accept false): commit ONLY tests/benchmarks/search-tuning-round3.jsonl with message
     "round3: tuning failed (log only)" + trailer; do not touch the data files.
   If step 2 exited 2: do not commit; report the stderr verbatim.
Report: exit codes, the JSON summary lines printed by step 2, the --adopt/--reject output, the commit sha, the suite file path and — when
rejected — the failing test ids verbatim. Nothing else.
```

- [ ] **Step 5: Hidden generation prompt template (frozen text) — `tests/benchmarks/round3-hidden-generation-prompt.md`**

```
You are creating an evaluation set for an API operation search engine over the Atlassian Jira / Confluence REST catalog.
Below are VERB_METHODS — a JSON object mapping every action verb the engine recognizes to the HTTP methods it may express — and the
catalog: one line per operation with key, source, method, summary, tags (tab-separated).
Produce ONLY one JSON object: {"held_out": [16 records], "negative": [8 records]}.
held_out record: {"id": "h-001".."h-016", "query": "...", "expected_top1_any": ["<key>"], "forbidden_top1": [], "origin": "held_out-r3",
  "failure_classes": [], "ambiguous": false}
negative record: {"id": "n-001".."n-008", "query": "...", "expected_top1_any": [], "forbidden_top1": ["<key>"], "origin": "negative-r3",
  "failure_classes": [], "ambiguous": false}
Rules checked by a program (a violation is sent back to you by rule id):
- words: every query has 3 to 7 words of natural end-user phrasing.
- actionable (held_out): Every held_out query must express a single actionable API intent using at least one action verb whose HTTP
  method matches the expected operation; if several recognized verbs occur, their allowed-method intersection must be non-empty.
  Precisely: the query contains at least one VERB_METHODS key (matched as a lowercase word); the intersection of the method lists of
  all contained keys is non-empty; and the expected operation's method is inside that intersection.
- negative-distribution: Exactly 4 negative queries must be actionable under the frozen verb-method inventory (a recognized action
  verb is present and the allowed-method intersection is non-empty) and exactly 4 must be non-actionable; prefer no recognized verb
  for the non-actionable half — do not manufacture conflicting multi-verb phrasings merely to force abstention.
- negative-method (actionable negatives only): the method of the forbidden_top1 operation must be inside the query's allowed-method
  intersection — a wrong operation that merely has the wrong HTTP method is too easy.
- operationId: the set of words in a query (lowercased, split on non-letters, words shorter than 2 letters dropped, ignoring
  a/an/the/to/of/for/in/on/at/and/or/with/by/from/is/are/be/this/that) must not equal the set of words of any operation's
  operationId (camelCase split into words the same way).
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
Replacement contract: if a later message consists only of lines "record <id> rejected: <rule-id>" (one rule id per record, chosen by the
fixed priority schema > catalog > words > actionable > negative-method > operationId > summary/tags > negative-phrase > reuse), respond
ONLY with a JSON array containing exactly one replacement record for each listed id, in the same record schema and with the same id.
A later message may also contain lines "record <id> rejected: reviewer": "reviewer" is a valid semantic-review replacement request (a
human-language review found the expected answer not the single best one, the verb used as a noun, or a negative that has a correct
answer); it is not a machine rule id and takes no part in the priority above; respond with the same JSON array of replacement records.
Do not repeat or modify any other record. If a later message starts with "distribution rejected" and lists all 16 held_out ids, return a
JSON array of 16 replacement held_out records (same ids) that satisfy the distribution rule. If a later message starts with
"negative distribution rejected" and lists all eight negative ids, reply ONLY with a JSON array of exactly eight replacement negative
records, one per listed id, preserving those ids; together they must satisfy exactly 4 actionable / 4 non-actionable. Do not return
held_out records or the outer object.
No commentary.

VERB_METHODS:
<verb methods json>

CATALOG:
<generator catalog lines>
```

- [ ] **Step 6: Hidden reviewer prompt (frozen text) — `tests/benchmarks/round3-hidden-reviewer-prompt.md`**

```
You review candidate evaluation records against an API catalog. The catalog is the ATTACHED file round3-internal-catalog.jsonl:
JSON lines, one operation per line, with the fields key, source, method, operation_id, summary, tags, description (full text, not
truncated). Read the attachment as the catalog; nothing in this message replaces it.
Each record below carries a "machine" object computed by a program: matched_verbs (the recognized action verbs found in the query),
intent_methods (the HTTP methods those verbs allow) and machine_actionable. Do not re-judge that mapping.
For every record whose matched_verbs is non-empty (held_out records and the actionable negative records alike), verify that each
listed verb is used in the query as a request for an action, not as a noun or modifier ("comment history", "post details" are noun
uses): reject the record if any listed verb is a noun use.
For each held_out record also decide whether the expected operation is the single best answer to the query (reject if another
operation answers it at least as well, or if the query is unanswerable).
For each negative record also decide whether the catalog truly has NO correct operation for the query (reject if one exists) and
whether forbidden_top1 is really a wrong answer.
Reply ONLY with {"<id>": {"accept": true|false, "reason": "<short>"}, ...} for every record.
Never rewrite queries, never propose replacements.

RECORDS:
<plaintext records>
CATALOG: attached file round3-internal-catalog.jsonl
```

- [ ] **Step 7: Freeze and commit T**

```bash
python tests/benchmarks/round_seal.py freeze --round 3 --cache-dir $S --reference-enc ~/.atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc
python -m unittest discover -s tests -t .
HK=$(cat $W/housekeeping_commit); TF=$(python -c "from tests.benchmarks import evaluator as ev; print(' '.join(ev.TOOLING_FILES))")
git diff --exit-code "$HK" -- $TF tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py   # exit 0 required (AC-05)
git add tools/atlassian_docs/intelligence/data tests/benchmarks/round_freeze.json tests/benchmarks/search_queries.json tests/benchmarks/round3-*.md tests/benchmarks/round3-method-safety.json
git commit -m "T: Round 3 freeze (verb suffixes, lexicon-r3, candidates, R5/R6, worker brief, hidden prompts, reference set, regression reference, grid)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

The freeze printout must show `reference_set.enc_sha256 == c1a3794b…`, `hidden_generation_rules` == the 11 rule ids, `tuning_grid_sha256`, `regression_reference_sha256`; `git diff "$HK" HEAD -- tools/atlassian_docs/intelligence/data/search_ranking.json` must touch `verb_methods` lines only (AC-01a/AC-R3-13b). Then the AC-23 evidence step of the Round 2 plan (suite on the clean committed HEAD, event `ac23_test_checkpoint` with `checkpoint: "T"`, command, exit code, output sha) — the paths read `round3-work`.

---

### Task 12: **[controller]** Hidden-set generation, machine check (Round 3 rules), stateless review with attached catalog, AC-18b hygiene, commit B, encryption

Evidence goes to `$W/controller-events.jsonl` and `$W/attempts.jsonl` — one line per model call: `{"attempt_no", "stage": "generation"|"replacement"|"section-replacement"|"review", "actor_id", "session_id", "input_sha256", "output_sha256", "transport_status": "ok"|"error", "parse_status": "ok"|"parse_error", "valid_status": "valid"|"invalid", "reason_code"}`, plus for generation `rendered_generation_prompt_sha256`, for review `catalog_attachment_sha256`, `reviewed_record_shas`, `accepted_ids`. `actor_id` of a Temporary chat = the chat's URL id at the time of the call; generation and review use different chats. Retry lifecycle for every stage (inherited §5.3): transport error / parse error / invalid shape → retry the identical input in the same chat; never a semantic re-run after a valid output. **Every file that embeds the records** (`hidden-review-input.txt`, replacement outputs, replacement-review messages, screenshots that show records) is written under `$W/plain/` and that directory is deleted before the seal (AC-18b(R3)); only hashes survive.

- [ ] **Step 1: Render the exact generation input and generate**

```bash
python - <<'EOF2'
import json, pathlib, hashlib
from tests.benchmarks import round_seal as rs, evaluator as ev
w = pathlib.Path.home() / ".atlassian_api_updater" / "round3-work"
tpl = pathlib.Path("tests/benchmarks/round3-hidden-generation-prompt.md").read_text(encoding="utf-8")
cat = json.load(open(w / "round3-generator-catalog.json"))
vm = json.load(open("tools/atlassian_docs/intelligence/data/search_ranking.json"))["verb_methods"]
assert ev.canonical_sha256(vm) == ev.freeze_for(3)["verb_inventory_sha256"]
text = rs.render_generation_input(tpl, cat, vm)
(w / "hidden-generation-input.txt").write_text(text, encoding="utf-8")
print("rendered_generation_prompt_sha256", hashlib.sha256(text.encode()).hexdigest())
EOF2
```

Open a new **Unpersonalized Temporary chat** (confirm the toggle; screenshot of the toggle only, no records), paste the file byte-for-byte, take the first output; store it as `~/.atlassian_api_updater/sealed/round3-sealed.json` (mode 600) only if it parses as JSON with `held_out`/`negative` lists; ledger the attempt. Re-rendering the template must reproduce the same sha (ledger `rendered_prompt_reproduced: true`).

- [ ] **Step 2: Machine check with the frozen rule order (one state machine for machine and semantic rejections)**

```bash
python tests/benchmarks/round_seal.py check --round 3 --plain ~/.atlassian_api_updater/sealed/round3-sealed.json --bench tests/benchmarks/search_queries.json --internal-catalog $W/round3-internal-catalog.json
```

The controller keeps one state `state = {"negative_section_replacements": 0}` for the whole attempt. On violations the next message is computed, never composed: `rs.next_request(violations, plain, state)` → `("records", lines)` sent verbatim; `("section", "held_out", text)` / `("section", "negative", text)` likewise (after a negative section replacement `state["negative_section_replacements"] = 1`); `("invalid", reason)` ends the attempt: ledger it and start a **new** Unpersonalized Temporary chat with the identical rendered input (Round 2 attempt cap). Responses pass `validate_replacement_output(obj, requested_ids)`, are merged with `merge_replacements`, and the whole set is re-checked after every merge (the 4/4 distribution included). Semantic rejections from Step 3 re-enter this same loop with the same `state`.

- [ ] **Step 3: Semantic review (stateless, attached catalog, machine annotations, hygiene)**

```bash
mkdir -p $W/plain && chmod 700 $W/plain
python - <<'EOF2'
import json, pathlib, hashlib
from tests.benchmarks import round_seal as rs
w = pathlib.Path.home() / ".atlassian_api_updater" / "round3-work"
tpl = pathlib.Path("tests/benchmarks/round3-hidden-reviewer-prompt.md").read_text(encoding="utf-8")
plain = json.load(open(pathlib.Path.home() / ".atlassian_api_updater" / "sealed" / "round3-sealed.json"))
vm = json.load(open("tools/atlassian_docs/intelligence/data/search_ranking.json"))["verb_methods"]
cat = json.load(open(w / "round3-internal-catalog.json"))
lines = "\n".join(json.dumps({k: r.get(k) for k in ("key", "source", "method", "operation_id", "summary", "tags", "description")}, ensure_ascii=False) for r in cat)
(w / "round3-internal-catalog.jsonl").write_text(lines, encoding="utf-8")
msg = tpl.replace("<plaintext records>", json.dumps(rs.annotate_for_review(plain, vm), ensure_ascii=False, indent=1))
(w / "plain" / "hidden-review-input.txt").write_text(msg, encoding="utf-8")
print("review_message_sha256", hashlib.sha256(msg.encode()).hexdigest()); print("catalog_attachment_sha256", hashlib.sha256(lines.encode()).hexdigest())
EOF2
```

New Unpersonalized Temporary chat (a different chat from the generator's; its id is the `reviewer_actor_id`) → attach `round3-internal-catalog.jsonl` → paste the message → first output → `$W/plain/hidden-review-output.json` → validate with `rs.validate_reviewer_output(out, ids)` (invalid/parse/transport → retry the identical input, each attempt ledgered); ledger `reviewed_record_shas`/`accepted_ids`. Rejected ids → one request to the generator chat with lines `record <id> rejected: reviewer` (the frozen prompt's semantic replacement contract); the response is validated (`validate_replacement_output`), merged, and the **whole set re-enters Step 2** (full machine check with the same `state`; a broken 4/4 may trigger the single negative section replacement, whose 8 new records are machine-checked and then reviewed in full; a second need is `invalid`). Replacement records are reviewed with the same frozen prompt (annotated the same way), in a new review attempt. The controller never decides accept/reject. Build `$W/coverage-manifest.json = coverage_manifest(plain, accepted_attempt_by_id)`; `verify_coverage(manifest, plain, attempts) == []` or the seal is blocked (hashes only). Then the actor check: `generator_actor_id != reviewer_actor_id` (ledger the event `actor_separation_check_B` with both ids).

- [ ] **Step 4: Seal metadata, hygiene, [user] encryption, scan — then commit B**

```bash
rm -rf $W/plain
python tests/benchmarks/round_seal.py seal --round 3 --plain ~/.atlassian_api_updater/sealed/round3-sealed.json --bench tests/benchmarks/search_queries.json --cache-dir $S
```

(The seal command only rewrites the bench's hidden sections and `round3_seal`; nothing is committed yet.) Ask the user to run in their own terminal:

```bash
cd ~/.atlassian_api_updater/sealed && openssl enc -aes-256-cbc -pbkdf2 -in round3-sealed.json -out round3-sealed.json.enc && rm round3-sealed.json
```

**Before** asking for encryption: write the needle manifest (hashes only) and run the first scan (spec §5 v1.16):

```bash
python - <<'EOF2'
import json, pathlib
from tests.benchmarks import round_seal as rs
root = pathlib.Path.home() / ".atlassian_api_updater"; sealed = root / "sealed" / "round3-sealed.json"
plain = json.load(open(sealed))
(root / "round3-work" / "needle-manifest.json").write_text(json.dumps(rs.needle_manifest([r["query"] for r in plain["held_out"] + plain["negative"]]), indent=1), encoding="utf-8")
EOF2
python tests/benchmarks/round_seal.py scan --manifest $W/needle-manifest.json --root ~/.atlassian_api_updater --root . --allow ~/.atlassian_api_updater/sealed/round3-sealed.json
```

The scan must print `{"unexpected_hits": []}` (ledger as `ac18b_scan_before_encryption`). Only then the user encrypts (command above). Controller, after the user confirms:

```bash
test ! -e ~/.atlassian_api_updater/sealed/round3-sealed.json && shasum -a 256 ~/.atlassian_api_updater/sealed/round3-sealed.json.enc   # AC-18a-B value
python tests/benchmarks/round_seal.py reference-check --round 3 --reference-enc ~/.atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc   # AC-R3-06 checkpoint B
```

Ledger both. Then:

```bash
python -m unittest discover -s tests -t .
git add tests/benchmarks/search_queries.json
git commit -m "B: Round 3 seal (held_out 16 / negative 8 sha256 + distributions, 4/4 actionable split)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

AC-23 evidence (checkpoint `B`) as in Task 11 on the clean committed HEAD; ledger `negative_distribution` (4/4) from the seal output as the AC-R3-09a B check. The post-B scan (`ac18b_scan_after_B`) is `python tests/benchmarks/round_seal.py scan --manifest $W/needle-manifest.json --root ~/.atlassian_api_updater --root .` with no allow list (the plaintext is gone) and must print `{"unexpected_hits": []}`.

---

### Task 13: **[controller]** S checkpoint, then dispatch the frozen worker brief (B..C)

- `python tests/benchmarks/round_seal.py verify-freeze --round 3 --cache-dir $S` → `freeze ok` (ledger); `git status --porcelain --untracked-files=no` empty; `shasum -a 256 tests/benchmarks/round3-worker-brief.md` == `freeze_for(3)["worker_brief_sha256"]`.
- **Two-phase handshake (spec §5 v1.16).** Phase 0: dispatch one **fresh** implementer subagent (standard model) whose prompt is: one line of context + "read `tests/benchmarks/round3-worker-brief.md` first; it is your entire procedure; this message is: handshake" + `ATLASSIAN_DOCS_ROUND3_CACHE=$S` + the report file path. The frozen brief makes the worker write `$W/worker-handshake.json` and stop with `HANDSHAKE` (no other file read, no other command). The controller then checks `worker_actor_id ∉ {generator_actor_id, reviewer_actor_id}` and ledgers `actor_separation_check_worker` (a collision ends the dispatch; a new worker is allocated). Phase 1: only after that event exists, send the same agent (SendMessage, context intact) exactly `run the brief procedure`. Ledger `worker_actor_id`, run count, each report's `run_id`/`status`/`tuning_accept`/`result_sha256`/`grid_runtime_s`/`fixture_negative_effective_diagnostic`.
- Only predefined replies: "run the brief procedure", "run it again" (after a tool error).
- Branch-aware task review (Round 2 Task 12 checklist with `round3` names): `adopted` → suite green, `--verify` passes, `constants_selected`/`result_sha256` match the files, commit touches only the three files; `failed` → suite green, policy == B, the `failed` line validates (`tuning_accept: false`, `regression_raw`/`regression_negative` present), commit touches only the log, `python tests/tune_search_ranking.py --verify --cache-dir $S` prints `replay ok` (failure-branch replay, AC-R3-10); `rejected` → policy == B on HEAD, `reject_evidence` matches the evidence file, `--materialize` reproduction of the failing-test signature in a temporary worktree.

---

### Task 14: **[controller]** Provenance check, then commit C (success), F (tuning failure) or X (abort)

- [ ] **Step 1: Hash/provenance check (all branches)** — `HK=$(cat $W/housekeeping_commit); TF=$(python -c "from tests.benchmarks import evaluator as ev; print(' '.join(ev.TOOLING_FILES))"); git diff --exit-code "$HK" -- $TF tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py` exits 0; `tooling_code_sha256` unchanged; the worker commit touches only the brief's allowed files; the log matches exactly one branch (one `adopted` | `failed ≥ 1` and no adopted/rejected | one `rejected`). `python tests/tune_search_ranking.py --verify --cache-dir $S` → `replay ok` on every branch.
- [ ] **Step 2a: Success** — `verify-freeze`, the `evaluation_code_sha256 == freeze_for(3)["evaluation_code_sha256_at_T"]` assertion, suite, empty commit `C: Round 3 freeze before final evaluation (evaluation_code_sha256 == at_T)`; continue with Task 15.
- [ ] **Step 2b: Tuning failure** — AC-18a-F checkpoint (`.enc` sha unchanged, no plaintext, no decryption), the `pre_terminal_plaintext_scan` (`python tests/benchmarks/round_seal.py scan --manifest $W/needle-manifest.json --root ~/.atlassian_api_updater --root .` with no allow list; must print `{"unexpected_hits": []}`), and the AC-R3-06 pre-terminal check `python tests/benchmarks/round_seal.py reference-check --round 3 --reference-enc ~/.atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc` (hash only, never opened), render readiness (Task 16, failure branch: `D_controller_actor_id: not_applicable`, hidden `not_evaluated`, `reference_round2: not_applicable`), commit `F: Round 3 tuning failed` touching only `docs/phase3-readiness.md`. Skip Task 15; continue with Task 17.
- [ ] **Step 2c: Abort** — ledger `rejected_suite_evidence`, AC-18a-X checkpoint, `pre_terminal_plaintext_scan` (as in 2b), AC-R3-06 pre-terminal `reference-check` (hash only), render readiness (abort branch, B-vs-X policy shas), commit `X: Round 3 aborted (rejected tuning run)` touching only `docs/phase3-readiness.md`. Skip Task 15; continue with Task 17.

---

### Task 15: **[D controller (fresh actor) + user]** Commit D — single gate evaluation, gate checkpoint, then the Round 2 reference observation

The D controller is a fresh actor (new session or subagent that did not run Tasks 9–14's tuning dispatch); ledger `D_controller_actor_id` and the event `actor_separation_check_D` (`D_controller_actor_id ∉ {controller_actor_id, generator_actor_id, reviewer_actor_id, worker_actor_id}`) before anything else.

- [ ] `python tests/benchmarks/round_seal.py verify-freeze --round 3 --cache-dir $S` → `freeze ok`; AC-18a-D checkpoint (`.enc` sha == B value, no plaintext) → ledger.
- [ ] **[user]** decrypt: `cd ~/.atlassian_api_updater/sealed && openssl enc -d -aes-256-cbc -pbkdf2 -in round3-sealed.json.enc -out round3-sealed.json`.
- [ ] Seal check, then exactly one evaluation of the Round 3 sets:

```bash
python - <<'EOF2'
import json, pathlib
from tests.benchmarks.evaluator import canonical_sha256
p = json.load(open(pathlib.Path.home()/".atlassian_api_updater/sealed/round3-sealed.json")); b = json.load(open("tests/benchmarks/search_queries.json"))["round3_seal"]
assert canonical_sha256(p["held_out"]) == b["held_out_sha256"] and canonical_sha256(p["negative"]) == b["negative_sha256"]; print("seal ok")
EOF2
python tests/diag_search_queries.py --round 3 --bench ~/.atlassian_api_updater/sealed/round3-sealed.json --cache-dir $S --json tests/benchmarks/round3-final.json
```

Gate (AC-R3-09b): `sets.held_out.passed ≥ 15/16`, `negative_actionable.raw_passed == 4/4`, `negative_abstained.effective_passed == 4/4`, `sets.negative.effective_passed == 8/8`.

- [ ] **Gate checkpoint event (before anything Round 2 is opened)**:

```bash
python - <<'EOF2'
import json, pathlib, subprocess, datetime
from tests.benchmarks.evaluator import canonical_sha256
art = json.load(open("tests/benchmarks/round3-final.json")); root = pathlib.Path.home() / ".atlassian_api_updater"
gate = {"held_out": art["sets"]["held_out"], "negative": art["sets"]["negative"], "negative_actionable": art["negative_actionable"], "negative_abstained": art["negative_abstained"],
        "pass": art["sets"]["held_out"]["passed"] >= 15 and art["negative_actionable"]["raw_passed"] == 4 and art["negative_abstained"]["effective_passed"] == 4 and art["sets"]["negative"]["effective_passed"] == 8}
e = {"event": "round3_gate_checkpoint", "round3_gate_result_sha256": canonical_sha256(gate), "gate": gate, "commit_C": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
     "round3_seal_sha256": {"held_out": art["sealed_sha256"]["held_out"], "negative": art["sealed_sha256"]["negative"]}, "evaluation_code_sha256": art["evaluation_code_sha256"],
     "ranking_sha256": art["ranking_sha256"], "aliases_sha256": art["alias_sha256"], "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
open(root / "round3-work" / "controller-events.jsonl", "a").write(json.dumps(e) + "\n"); print(json.dumps(e, indent=1))
EOF2
```

- [ ] **Round 2 reference observation (AC-R3-07)** — only after the event above exists in the ledger. First the AC-R3-06 pre-decrypt checkpoint: `python tests/benchmarks/round_seal.py reference-check --round 3 --reference-enc ~/.atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc` → `reference ciphertext ok` (ledger). Then **[user]** decrypts the archive copy to a temporary path: `openssl enc -d -aes-256-cbc -pbkdf2 -in ~/.atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc -out ~/.atlassian_api_updater/round3-work/reference-round2-plain.json` (the ciphertext file itself is never modified). Controller: assert its canonical shas equal the freeze's `reference_set` values, ledger `decrypt_at` + `plaintext_sha256`, then:

```bash
python tests/diag_search_queries.py --round 3 --cache-dir $S --reference ~/.atlassian_api_updater/round3-work/reference-round2-plain.json --reference-round 2 --append-to tests/benchmarks/round3-final.json
rm ~/.atlassian_api_updater/round3-work/reference-round2-plain.json
```

Ledger `deleted_at` and mark this actor `reference-aware`; it performs no further Round 3 evaluation. The Round 3 gate is never re-run or re-interpreted after this point (the checkpoint event is the evidence). Run the AC-R3-06 `reference-check` once more (hash unchanged after the user's decryption step) and the `pre_terminal_plaintext_scan`: `python tests/benchmarks/round_seal.py scan --manifest $W/needle-manifest.json --root ~/.atlassian_api_updater --root . --allow ~/.atlassian_api_updater/sealed/round3-sealed.json` → `{"unexpected_hits": []}` (the decrypted sealed plaintext is the only allowed copy; the reference plaintext must already be deleted; the unseal has not happened yet).

- [ ] Unseal, suite, **render readiness (Task 16, success branch)**, commit D:

```bash
python tests/benchmarks/round_seal.py unseal --round 3 --plain ~/.atlassian_api_updater/sealed/round3-sealed.json --bench tests/benchmarks/search_queries.json
python -m unittest discover -s tests -t .
git add tests/benchmarks/search_queries.json tests/benchmarks/round3-final.json docs/phase3-readiness.md
git commit -m "D: Round 3 final evaluation (single run), gate checkpoint, Round 2 reference observation, unseal, decision record

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

The `post_terminal_plaintext_scan` after commit D is Task 17's first step (ledger and provenance report only; the only plaintext allowed to remain is `sealed/round3-sealed.json`, which the user may now re-encrypt or delete).

---

### Task 16: **[controller]** Subroutine — render the readiness Round 3 section from the ledgers (called by Task 14 Step 2b/2c before F/X and by Task 15 before commit D; never its own commit)

Append `## Search Quality Round 3 — decision record (<date>)` after the Round 2 section of `docs/phase3-readiness.md` (never inside it), rendered from `controller-events.jsonl` + `attempts.jsonl`: `round3_start_commit e16c073`, `housekeeping_commit`, spec v1.15 / plan v3, `evaluation_domain: actionable recommendation queries`, S (`s_reused_from_round2`, fingerprint, spec shas, op count) as `round3_operational_snapshot`, the AC-R3-02 reference provenance as `round2_regression_snapshot` (29dba38, fingerprint, reference sha), verb inventory decisions (suffixes, prefix check), method-safety, lexicon re-gate counts and the newly merged `lexicon-r3` words, candidates/R5/R6, AC-13 replay, **pre-T checkpoint** numbers and input shas, T/B/C shas (terminal commit `self`), `structure/tooling/evaluation/tuning_grid/regression_reference` shas at T, `reference_set` (enc sha), hidden generation attempts (`rendered_generation_prompt_sha256`, outputs, `next_request` kinds sent, section replacements used), review attempts (`catalog_attachment_sha256`), coverage manifest sha, `temporary_chat_unpersonalized: true`, AC-18b scans (`ac18b_scan_before_encryption`, `ac18b_scan_after_B`, `pre_terminal_plaintext_scan` — the `post_terminal_plaintext_scan` is ledger/provenance-only because it runs after the terminal commit), the three `actor_separation_check_*` events, `.enc` sha at B and pre-terminal, worker brief sha + `worker_actor_id` + runs (`run_id`, `status`, `tuning_accept`, `seed`, `regression_negative` effective, `regression_raw`, `fixture_positive`, `fixture_negative_raw`, `fixture_negative_effective_diagnostic`, `grid_runtime_s`, `result_sha256`), `--verify` result, actor table (`controller_actor_id`, generator/reviewer chat attestation, `worker_actor_id`, `D_controller_actor_id` or `not_applicable`, `reference-aware` actor), the result rows in the spec §13 schema — `seed.top1_correct`, `regression_negative.{raw, effective}`, `fixture_positive.top1_correct`, `fixture_negative.{raw, effective_diagnostic}` (from the log line's `fixture_negative_raw` / `fixture_negative_effective_diagnostic`), `hidden.held_out_pass`, `hidden.negative.{raw, effective}` (+ `negative_actionable`/`negative_abstained`) or `not_evaluated` on F/X, `round3_gate_result_sha256`, `reference_round2` (raw/effective, `invalid_key`, `plaintext_sha256`, `decrypt_at`, `deleted_at`) or `not_applicable`, the state model table (branch D/F/X; `adopted_runs`, `failed_runs`, `rejected_runs`, `hidden_evaluated`, `ciphertext_retained`), and the attestation list over spec v1.15 §10 (AC-01a/b, 02–05, 06b, 07, 08 with the two provenance domains, 09, 10, 12, 13, 15a/15b split, 19c, 21/22, 23, AC-R3-01..13b, AC-18b(R3)). This task never produces its own commit.

---

### Task 17: **[controller]** Post-terminal provenance review and finishing

- Record the terminal commit sha (D, F or X) in the ledger in one event together with the post-terminal AC-R3-06 check: `{"event": "terminal_commit", "terminal_commit_sha", "reference_ciphertext_sha256" (== freeze reference_set.enc_sha256 via reference-check), "checked_at"}`; then the `post_terminal_plaintext_scan`: `python tests/benchmarks/round_seal.py scan --manifest $W/needle-manifest.json --root ~/.atlassian_api_updater --root .` — on F/X with no allow list; on D with the intentionally published terminal artifacts allowed (`--allow tests/benchmarks/search_queries.json --allow tests/benchmarks/round3-final.json --allow docs/phase3-readiness.md --allow ~/.atlassian_api_updater/sealed/round3-sealed.json`) — must print `{"unexpected_hits": []}`, ledgered and copied into the provenance report (not into readiness). Dispatch a reviewer (most capable model) limited to provenance: spec v1.15 §10.1/§10.2 row by row against git history, ledgers and artifacts, including the AC-18b scans and the ledger ORDER (gate checkpoint before `decrypt_at`); report saved as `$W/provenance-report.md`; no changes to `TOOLING_FILES`.
- Update memory (`search-quality-round3-design-status.md` → outcome; MEMORY.md index); archive `round3-cache`, `round3-work` and `sealed/round3-sealed.json.enc` under `~/.atlassian_api_updater/archive/round3/` after the user confirms.
- Use `superpowers:finishing-a-development-branch` (the user chooses merge/push; push only on instruction).

## AC coverage map (spec v1.15)

| AC | Where |
|---|---|
| AC-01a/b, 01c/d | Global Constraints (H1 structure, T suffix/data, B..C values), Tasks 11/13/14 git checks |
| AC-02, 03, 10, 11 | Task 15 (D whitelist, seal check, artifact), Task 8 `TestRound3FinalArtifact` |
| AC-04 | Task 6 origins `-r3` + seal, Task 12 B check |
| AC-05, AC-R3-13a | Task 1 `test_round3_policy_diff_is_limited_to_declared_kinds`, Task 11/14 `git diff` on `TOOLING_FILES`/`search.py`/`policy.py` |
| AC-06a/06b | Task 7 fixture raw constraint, `tuning_accept` (effective 14/14, raw recorded) |
| AC-07, 14, 16, 23 | canonical suite at every commit, AC-23 events at T and B (Tasks 11, 12) |
| AC-08, AC-13 | Task 3 freeze keys + `pending_round` guard, Task 11 freeze/replay, Task 16 two provenance domains |
| AC-09 | Global Constraints byte-invariant list, Task 5 prefix invariant, Task 1 structure window |
| AC-12, AC-R3-05 | Task 7 validator (≤ 2 per seed, ≤ 15, direct aliases only, `candidate_word`, targets), Task 5 target eligibility |
| AC-15a/b, 19a/b/c/d, 20a/b, 21, 22 | Task 7 log fields + `_verify` (adopted / failed / rejected), Task 13 branch-aware review, Task 14 |
| AC-R3-01 | Task 8 `--phase pre-T`, Task 11 Step 3 (binding) |
| AC-R3-02 | Task 4 (isolated generation, verifier, test), Task 11 freeze `regression_reference_sha256` |
| AC-R3-03 | Task 2 `test_actionable_does_not_change_scores_or_order`, Task 4 regression reference |
| AC-R3-04 | Task 5 tests (resource vocabulary, real fixtures, candidates ⇔ R6) |
| AC-R3-06, AC-R3-07 | Task 6 `reference_set` + `reference-check`; checkpoints at B (Task 12), before the D decryption (Task 15), post-terminal D/F/X with the terminal sha (Task 17); Task 15 gate checkpoint → decrypt → observe → delete (ledger order) |
| AC-R3-08 | Global Constraints session separation; three `actor_separation_check_*` events (Tasks 12, 13, 15) |
| AC-R3-09a/b | Task 6 rules + Task 3 evaluator (T), Task 12 seal distribution (B), Task 15 single evaluation (D) |
| AC-R3-10 | Task 7 `--verify` on success/failure/abort |
| AC-R3-11a/b | Task 7 log fields incl. `fixture_negative_effective_diagnostic`, Task 8 diag raw/effective, Task 16 §13 rows, `TestRound3FinalArtifact` |
| AC-R3-12 | Task 5 prefix invariant test + CLI, Task 9 fixed point |
| AC-R3-13b | Task 1 grid committed at H1, Task 3 `tuning_grid_sha256` in freeze, Task 11 diff check |
| AC-18a-B/D/F/X, AC-18b(R3) | Tasks 12, 14, 15 checkpoints and scans |

## Self-review notes

- Spec coverage: §2 → Tasks 1–8 (constrained changes), Global Constraints (invariants); §3.1–3.3 → Task 2; §3.4 → Tasks 1, 7; §3.5 → Task 4; §4 → Tasks 3, 6, 12, 15; §5 → Tasks 8 (pre-T), 9–15; §6 → Tasks 5, 7; §7 table → Tasks 1–8; §8 → each task's tests + Task 8 `--phase H`; §9 → Tasks 3, 6, 16; §10 → coverage map; §11 → Global Constraints (measured grid), Task 8 probe; §13 → Task 7 (`tuning_accept` field, AC-15a/b split in Task 16, `canonical_full_suite_pass` command and `exit_code` line in the brief), Task 8 raw/effective schema (positive sets carry no negative fields; `negative_actionable`/`negative_abstained` on the negative set), Global Constraints (final grid value); §14 corrections are all reflected.
- Rulings: (1) the Round 2 simulation tool `tests/benchmarks/round2_simulation.py` is left untouched (history, not executed by the suite; it references the renamed `round2_note`/`ROUND == 2` and would need the Round 2 tree to run). (2) `evaluate()` keeps the Round 1 failure-record shape when `section is None`, so Round 1 tests and artifacts stay byte-invariant. (3) The memoized grid evaluator is used only while the alias state equals B (the constants grid); every proposer trial and the final/verify evaluations run the production path, plus a cross-check at the selected point. (4) AC-R3-02 "whole list" = up to `MAX_LIMIT=50` results plus `total_matches` (spec v1.13 §3.5).
- Type consistency checked: `evaluate(section=)` keys used by Tasks 7/8 (`raw_passed`, `effective_passed`, `actionable`, `abstained`) are produced by Task 3; `GridEvaluator.ranked` returns `(keys, actionable)` consumed by `evaluate_point_fast`; `rs.next_request` state key `negative_section_replacements` used in Task 12; `ev.freeze_key_set(3)` equals `rs.freeze_entry(3, …)` keys (Task 6 test); `tune.round_note(word, sid, target)` replaces `round2_note(word, sid, target, kind)` everywhere.

## Plan revision notes

v1 (2026-10-05): initial plan written against spec v1.13.

v2 (after external plan review 1 — P0 5 / P1 7; spec v1.14): P0: (1) pre-freeze structure check split into non-verb structure sha + verb prefix invariant (`ev.structure_check_problems`; helpers moved into the stdlib evaluator, Task 1/5); (2) seal → user encryption + deletion + scan → commit B (Global Constraints, Task 12); (3) `record <id> rejected: reviewer` added to the frozen generation prompt as the semantic replacement contract, semantic rejections re-enter the single `next_request` state machine (Tasks 11, 12); (4) reviewer prompt checks verb USE for held_out and actionable negatives with machine annotations `rs.annotate_for_review` (Tasks 6, 11, 12); (5) AC-R3-06 `reference-check` at B, before the D decryption, and at every terminal commit (Tasks 6, 12, 14, 15). P1: AC-09/§7 spec wording; memoized-evaluator equivalence preflight on the actual S inside `--phase pre-T` (Tasks 8, 11); AC-13 replay as an executable script (Task 11); `$W/housekeeping_commit` pinned in Task 9 and used instead of placeholders (Tasks 11, 14); Task 16 declared a subroutine called before D/F/X; readiness result rows in the §13 schema; attempts ledger carries actor/session ids and transport/parse/valid status with the actor-separation check (Task 12).

v3 (after external plan review 2 — P0 3 / P1 5; spec v1.15): P0: (1) actor separation split into three chronologically possible checks (before B, worker allocation, before D) with `session_id` sourced from the orchestration session or `not_available`; (2) AC-R3-11a/b rewritten to the §13 schema and `tune.fixture_negative_diagnostic` produces `fixture_negative_effective_diagnostic` on the log line (acceptance still raw); (3) plaintext scans split into `pre_terminal_plaintext_scan` (before Task 16, in readiness) and `post_terminal_plaintext_scan` (Task 17, ledger/provenance only). P1: every binding reference now says spec v1.15; the before-encryption scan uses the 24 query needles with only the sealed plaintext excluded; §5 distinguishes the top-5 pre-T equivalence from the MAX_LIMIT AC-R3-02 equivalence; the terminal AC-R3-06 check is tied to the terminal commit sha in Task 17; `actor_id`/`session_id` sources defined.

v4 (after external plan review 3 — P0 3 / P1 5; spec v1.16): P0: (1) two-phase worker handshake in the frozen brief (Phase 0 `handshake` → `worker-handshake.json` + `HANDSHAKE`; controller checks and ledgers `actor_separation_check_worker`; then `run the brief procedure` via SendMessage) — Tasks 11, 13; (2) plaintext scans use a hashed normalized n-gram needle manifest written before encryption (`rs.needle_manifest`, `rs.scan_for_needles`, CLI `scan --manifest --root --allow`), verdict `unexpected_hits == []` with explicit allow lists (pre-encryption: sealed plaintext; after B and F/X: none; pre-terminal D: decrypted sealed plaintext; post-terminal D: the published terminal artifacts) — Tasks 6, 12, 14, 15, 17; (3) spec §9 state model now cites the §13 schema. P1: Task 12 event named `actor_separation_check_B`; D check includes `controller_actor_id`; header inheritance sentence; AC-R3-06 coverage row; Task 16 run schema carries `fixture_negative_effective_diagnostic`.
