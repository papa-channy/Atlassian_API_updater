# Search Quality Round 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the lexicon generator a seed-independent vocabulary source (the current titles of every official Jira/Confluence Cloud support page, frozen as an immutable raw bundle), gate T on an exact dry-run of the production tuning pipeline, model the Round 3 → Round 4 gap and the between-T-and-B abort without fake freeze entries, and then repeat the sealed Discovery procedure once against a **new** hidden set.

**Architecture:** Scorer, constants, grid and the Round 3 ordering rules are untouched (AC-R4-04). Three tooling commits (H13 state model, H14 corpus + renderer + prompts, H15 pipeline dry-run + Round 4 simulation + X_preB) extend `tests/benchmarks/` only; `tools/atlassian_docs/intelligence/data/*` changes only at T (lexicon-r4, candidates, verb suffixes) and in tuning. The controller procedure is the Round 3 plan v16 procedure (Tasks 9–17, 21) with the Round 4 deltas written out in Tasks 4–12 below; every decision point is taken to the ChatGPT review thread, never to the user (the user is stopped only for the four hard stops and the completion report).

**Tech Stack:** Python 3.11 stdlib only (`urllib`, `gzip`, `html.parser`, `xml.etree`, `hashlib`, `json`, `subprocess`); `unittest`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-09-search-quality-round4-design.md` **v1.11** (v1.10 passed external review 11 with P0 0 / P1 4 "구현 계획으로 진행 가능"; v1.11 applied the four P1 items). The spec inherits Round 3 v1.25.1 (`docs/superpowers/specs/2026-10-05-search-quality-round3-design.md`) by delta; where this plan says "as Round 3 plan v16 Task N Step M" it means `docs/superpowers/plans/2026-10-05-search-quality-round3-implementation.md` with the substitution table of §"Name substitutions" applied verbatim.

**Plan version:** v3 (2026-10-09; v2 → plan review 2 P0 2 / P1 5: `append_outcome` with the real freeze + `--apply-outcome` CLI and four tests, the sealed plaintext registered in the attempt ledger (states 3–5 simulated), independent blockers, attestation evidence checks, child-sitemap kind, sha helper; v1 → plan review 1 P0 4 / P1 5: strict compound state, Git-bound recovery verifier, TOOLING_FILES timing, cleanup deletion/terminal machine checks, fetch errors, not_applicable branch, sha helpers, full post-T allowlist check, no runtime placeholders).

## Global Constraints

- Canonical test command: `python -m unittest discover -s tests -t .` (**555 OK** at `53b79c2`, Python 3.11.15). `canonical_full_suite_pass := exit code 0 of exactly this command`; the controller ledgers the command and the sha256 of its output at every checkpoint. Simulation is always run as `python -m tests.benchmarks.round4_simulation …` (the `_html_mng.pth` shadowing trap).
- `round4_start_commit := 237d2c9` (spec §9.2). Spec/plan commits after it touch only `docs/`. Branch-aware ancestry: `237d2c9 < initial_housekeeping_commit ≤ housekeeping_commit < T` (common prefix, AC-R4-07); `T < B < terminal` on D/F/X (inherited); `T < X_preB`, B absent (AC-R4-09).
- **Byte-invariant** (spec §2): everything the Round 3 plan v16 lists plus `tests/benchmarks/round3-*` (frozen texts, method-safety, regression reference), the Round 3 section of `docs/phase3-readiness.md` (the Round 4 section is appended after it), `search.py`, `policy.py`, the **structure** of `search_ranking.json` (`ordering_rules`, 8 constants, grid; `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[4] == PRE_FREEZE_NONVERB_STRUCTURE_SHA256[3]`). AC-R4-04: at every H/H′ `git diff --stat <prev>..HEAD -- tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py tools/atlassian_docs/intelligence/data/search_ranking.json` is empty and is ledgered.
- **T commit allowlist (spec §9.6, exact):** `tools/atlassian_docs/intelligence/data/{search_ranking.json (verb_methods suffix only), search_aliases.json (lexicon-r4 merge only), concept_lexicon.json, alias_candidates.json}`, `tests/benchmarks/round_freeze.json` (round 4 entry appended), `tests/benchmarks/search_queries.json` (seed `failure_classes`; hidden sections `[]`), `tests/benchmarks/round4-worker-brief.md`, `round4-hidden-generation-prompt.md`, `round4-hidden-reviewer-prompt.md`, `round4-lexicon-generation-prompt.md`, `round4-lexicon-review-prompt.md`, `tests/benchmarks/round4-method-safety.json`. `freeze[4].t_policy_files` = the subset of the four data files that actually changed; re-verified right after commit T.
- `TOOLING_FILES` gains `tests/benchmarks/doc_titles.py`, `tests/benchmarks/test_doc_titles.py`, `tests/benchmarks/round4_simulation.py`, `tests/benchmarks/test_round4_simulation.py` (Task 2) and is immutable from `housekeeping_commit` to the terminal commit. Post-S H′ comes in two kinds (spec §9.3): **bundle-preserving** (reuse the raw bundle, same S) and **acquisition-invalidating** (new corpus epoch, same catalog S, only before T). Both: fix → suite → `--phase H` → fresh reviewer findings 0 → `housekeeping_commit` move + `housekeeping_commit_moved` ledger → regenerate downstream artifacts.
- Round state (spec §9.1): `tests/benchmarks/round_outcomes.json` records Round 3 as `pre-T not reached`; `round_freeze.json` gets no round 3 entry ever; `pending_round() == 4`; `freeze --round N` requires `N == pending_round(freeze, outcomes)` and every lower round in exactly one of {frozen, closed, aborted-pre-B}. `tests/benchmarks/round_recoveries.json` is created empty in H13 and only ever appended by a recovery attestation commit A (spec §9.5).
- **Pre-T gate (spec §4.1, AC-R4-06):** T is allowed iff AC-R3-01 passes ∧ `pre_t_blockers == []` where the blockers come from an exact, write-free dry-run of `tune_search_ranking.run_pipeline_result` (grid → `select_candidate` once → `propose_aliases` once with `BUDGET = 15`, `PER_SEED = 2` → `tuning_accept`). Any blocker → `STOP_FOR_AMENDMENT` (non-terminal; the controller takes the blocker to the ChatGPT review thread for the amendment decision). `TERMINAL_PRE_T_NOT_REACHED` is a user decision only.
- **Corpus (spec §5.1):** `doc_titles.DOC_SOURCES` = the three literal `(product, sitemap_url, allowed_loc_prefix)` rows; acquisition runs once per epoch (≈2,435 pages, ≥0.25 s apart, HTML kept gzip-compressed under `$W/doc-title-sources/pages/`), failure rate > 5 % aborts; the snapshot and every render read only the bundle. No function in `doc_titles.py` or the renderer path takes the bench as input (AC-R4-05).
- Session separation (AC-R3-08 inherited): this planning session (`42e25099…`) never saw any hidden plaintext and may act as Round 4 controller; the lexicon generator/reviewer and hidden generator/reviewer are stateless ChatGPT Temporary chats (personalization off); the tuning worker is a fresh subagent; the D controller is a fresh actor. Hidden plaintext path `~/.atlassian_api_updater/sealed/round4-sealed.json` is never given to subagents. Every hidden-attempt artifact is needle-ledgered before deletion (spec §9.4).
- Decision protocol: every judgement call (approach, amendment, blocker handling, record questions) is written up and decided on the ChatGPT review thread `https://chatgpt.com/c/6aa781b6-36b0-83ee-810f-aa82f8b54610`; the ruling is ledgered with the review output sha. The user is interrupted only by the four hard stops (destructive/irreversible action, security-sensitive action, push/merge/publish, broken plan) and the completion report. Push and merge only on the user's instruction.
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Chunked writes: no single tool call larger than ~60 lines. Never call real Jira/Confluence APIs; the only network steps are `python -m tools.atlassian_docs` (catalog refresh) and `doc_titles.py acquire`.

## Name substitutions (applied to every Round 3 plan v16 step this plan imports)

| Round 3 token | Round 4 token |
|---|---|
| `round3` / `Round 3` / `ROUND = 3` / `--round 3` | `round4` / `Round 4` / `ROUND = 4` / `--round 4` |
| `~/.atlassian_api_updater/round3-cache` (`$S`), `round3-work` (`$W`) | `round4-cache`, `round4-work` |
| `ATLASSIAN_DOCS_ROUND3_CACHE` | `ATLASSIAN_DOCS_ROUND4_CACHE` |
| `lexicon-r3`, `-r3` origins, `seed-r3`/`held_out-r3`/`negative-r3` | `lexicon-r4`, `-r4`, `held_out-r4`/`negative-r4` |
| `round3_seal`, `round3-sealed.json(.enc)`, `round3-final.json`, `search-tuning-round3.jsonl` | `round4_seal`, `round4-sealed.json(.enc)`, `round4-final.json`, `search-tuning-round4.jsonl` |
| `round3-*.md` frozen texts, `round3-method-safety.json`, `round3-regression-reference.json` | `round4-*.md`, `round4-method-safety.json`, **`round3-regression-reference.json` stays** (AC-R3-02 reference is the Round 2 isolated scorer; `round_freeze_hashes(4)` reads the round 3 file, Task 1) |
| `HIDDEN_RULES_R3` | `HIDDEN_RULES_R4` (same ids, same order) |
| `ROUND3-WORKER-HANDSHAKE` | `ROUND4-WORKER-HANDSHAKE` |
| `python -m tests.benchmarks.round3_simulation` | `python -m tests.benchmarks.round4_simulation` |
| `round3_start_commit e16c073` | `round4_start_commit 237d2c9` |
| Round 2 archive inputs (`$A`, S2, `round2-sealed.json.enc`) | unchanged (the Round 2 set is again the `reference_set`) |

## Review Focus

1. A sitemap `<loc>` whose host is `support.atlassian.com` but whose path is under a different product prefix must be discarded and counted, never fetched under the wrong `product` label (Task 2 `test_preflight_discards_foreign_prefix_and_counts`).
2. A page GET that redirects outside `allowed_loc_prefix` must be recorded as `page_failed` with `fail_reason: "redirect-outside-prefix"` and must not store HTML (Task 2 `test_acquire_redirect_outside_prefix_is_failed`).
3. A grid point at which a failing seed becomes correct but which `select_candidate` would never pick must not open T: the dry-run gate, not `reachable_by_grid`, decides (Task 3 `test_pre_t_gate_uses_dry_run_not_grid_reachability`).
4. A parse-invalid generator output whose hidden query is split across two lines must still produce the 3–7-word needles that find a one-line copy of that query elsewhere (Task 3 `test_cleanup_needles_span_line_breaks`).
5. A `freeze --round 5` after an `aborted-pre-B` round 4 with `invalidates_policy: true` must be refused unless a recovery attestation whose R/A commits satisfy the exact diff contract exists (Task 1 `test_freeze_guard_requires_recovery_attestation`).

---

### Task 1: Round state model — `round_outcomes.json`, `round_recoveries.json`, pending-round gap, compound terminal state, Round 4 freeze keys, freeze guard, recovery attestation verifier, `validate-terminal` (commit H13)

**Files:**
- Create: `tests/benchmarks/round_outcomes.json`, `tests/benchmarks/round_recoveries.json`
- Modify: `tests/benchmarks/evaluator.py` (`load_round_outcomes`, `closed_rounds`, `round_states`, `pending_round`, `current_round`, `freeze_key_set`, `ROUND4_EXTRA_KEYS`, `round_freeze_hashes`, `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[4]`, `TOOLING_FILES`), `tests/benchmarks/round_seal.py` (`freeze_entry` round-4 keys, `cmd_freeze` guard, `verify_recovery`, `cmd_validate_terminal`, `HIDDEN_RULES_R4`)
- Test: `tests/benchmarks/test_evaluator.py`, `tests/benchmarks/test_round_seal.py`

**Interfaces:**
- Consumes: `ev.load_round_freeze()`, `ev.freeze_for()`, `rs.freeze_entry()`, `rs.cmd_freeze()`.
- Produces: `ev.load_round_outcomes(path=OUTCOMES) -> list`; `ev.closed_rounds(outcomes) -> set`; `ev.round_states(freeze, outcomes) -> dict[int, str]` (`"frozen" | "closed" | "aborted-pre-B"`, raises `ValueError` on any other combination); `ev.pending_round(freeze=None, outcomes=None) -> int|None`; `ev.current_round(freeze=None)` = max-round entry; `ev.ROUND4_EXTRA_KEYS = ("doc_titles_source_bundle_sha256", "doc_titles_snapshot_sha256", "round_outcomes_sha256", "round_recoveries_sha256", "t_policy_files")`; `ev.freeze_key_set(4) == freeze_key_set(3) | set(ROUND4_EXTRA_KEYS)`; `ev.t_policy_files(root, base_commit) -> list[str]`; `rs.verify_recovery(round, repo) -> list[str]` (empty = valid); `rs.freeze_guard_problems(round, freeze, outcomes, repo) -> list[str]`; CLI `round_seal.py validate-terminal --round 4 --state X_preB --work DIR`.

- [ ] **Step 1: Write the two state files and the failing state tests**

`tests/benchmarks/round_outcomes.json`:

```json
[
  {"round": 3, "outcome": "pre-T not reached", "decided": "2026-10-07",
   "decision_record": "docs/phase3-readiness.md#search-quality-round-3--decision-record-2026-10-07",
   "final_housekeeping_commit": "9bf823d", "last_checkpoint": {"seed": "35/39", "threshold": 36}}
]
```

`tests/benchmarks/round_recoveries.json`: `[]`.

Append to `tests/benchmarks/test_evaluator.py`:

```python
class TestRoundStateModel(unittest.TestCase):
    F12 = [{"round": 1}, {"round": 2}]
    def test_pending_round_skips_closed_round(self):
        with mock.patch.dict(ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256, {3: "a", 4: "b"}, clear=True):
            self.assertEqual(ev.pending_round(self.F12, [{"round": 3, "outcome": "pre-T not reached"}]), 4)
            self.assertEqual(ev.pending_round(self.F12, []), 3)                       # Round 3 history without outcomes
    def test_round_states_three_kinds_and_rejections(self):
        f = self.F12 + [{"round": 4}]
        o = [{"round": 3, "outcome": "pre-T not reached"}, {"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": False}]
        self.assertEqual(ev.round_states(f, o), {1: "frozen", 2: "frozen", 3: "closed", 4: "aborted-pre-B"})
        with self.assertRaises(ValueError):
            ev.round_states(f, [{"round": 4, "outcome": "pre-T not reached"}])        # freeze + ordinary outcome
        with self.assertRaises(ValueError):
            ev.round_states(self.F12, [{"round": 3, "outcome": "aborted-pre-B", "invalidated_by": "X_preB"}])   # orphan abort (no freeze)
        with self.assertRaises(ValueError):
            ev.round_states(f, [{"round": 4, "outcome": "aborted-pre-B"}])            # abort without invalidated_by
    def test_current_round_is_max_not_last(self):
        self.assertEqual(ev.current_round([{"round": 4}, {"round": 2}])["round"], 4)
    def test_freeze_key_set_round4(self):
        self.assertEqual(ev.freeze_key_set(4), ev.freeze_key_set(3) | set(ev.ROUND4_EXTRA_KEYS))
        self.assertNotIn("commit_T", ev.freeze_key_set(4))
    def test_committed_outcomes_file_shape(self):
        o = ev.load_round_outcomes()
        self.assertEqual([e["round"] for e in o], [3]); self.assertEqual(o[0]["outcome"], "pre-T not reached")
        self.assertEqual(ev.load_round_recoveries(), [])
```

Run: `python -m unittest tests.benchmarks.test_evaluator.TestRoundStateModel -v` → FAIL (`AttributeError: pending_round() takes …`, `load_round_outcomes` missing).

- [ ] **Step 2: Implement the state model in `evaluator.py`**

Replace `current_round` and `pending_round`, add after `freeze_for`:

```python
OUTCOMES = pathlib.Path(__file__).resolve().parent / "round_outcomes.json"
RECOVERIES = pathlib.Path(__file__).resolve().parent / "round_recoveries.json"
ROUND4_EXTRA_KEYS = ("doc_titles_source_bundle_sha256", "doc_titles_snapshot_sha256", "round_outcomes_sha256", "round_recoveries_sha256", "t_policy_files")
TERMINAL_OUTCOMES = ("pre-T not reached", "aborted-pre-B")

def load_round_outcomes(path=OUTCOMES) -> list:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8")) if pathlib.Path(path).exists() else []

def load_round_recoveries(path=RECOVERIES) -> list:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8")) if pathlib.Path(path).exists() else []

def current_round(freeze=None) -> dict:
    return max(freeze if freeze is not None else load_round_freeze(), key=lambda e: e["round"])

def round_states(freeze, outcomes) -> dict:
    """spec §9.1: every round is exactly one of frozen | closed | aborted-pre-B (freeze entry + aborted-pre-B outcome)."""
    fr = {e["round"] for e in freeze}; by = {}
    for o in outcomes:
        if o["round"] in by or o.get("outcome") not in TERMINAL_OUTCOMES:
            raise ValueError(f"round_outcomes.json: bad or duplicate record for round {o['round']}")
        by[o["round"]] = o
    out = {}
    for r in sorted(fr | set(by)):
        o = by.get(r)
        if r in fr and o is not None:
            if o["outcome"] != "aborted-pre-B" or o.get("invalidated_by") != "X_preB" or not isinstance(o.get("invalidates_policy"), bool):
                raise ValueError(f"round {r}: freeze entry + outcome is only valid as aborted-pre-B/X_preB with invalidates_policy")
            out[r] = "aborted-pre-B"
        elif o is not None:
            if o["outcome"] != "pre-T not reached":
                raise ValueError(f"round {r}: outcome {o['outcome']!r} without a freeze entry (orphan abort)")
            out[r] = "closed"
        else:
            out[r] = "frozen"
    return out

def closed_rounds(outcomes) -> set:
    return {o["round"] for o in outcomes}

def pending_round(freeze=None, outcomes=None):
    """The round whose H is committed but whose T does not exist yet: the smallest PRE_FREEZE key above the current
    freeze round that is not a decided (closed / aborted) round (spec §9.1)."""
    freeze = freeze if freeze is not None else load_round_freeze()
    outcomes = outcomes if outcomes is not None else load_round_outcomes()
    cur = current_round(freeze)["round"]; decided = set(round_states(freeze, outcomes))
    return next((r for r in sorted(PRE_FREEZE_NONVERB_STRUCTURE_SHA256) if r > cur and r not in decided), None)
```

`freeze_key_set`: `return set(_ROUND2_KEYS) | (set(ROUND3_EXTRA_KEYS) if round >= 3 else set()) | (set(ROUND4_EXTRA_KEYS) if round >= 4 else set())`. `PRE_FREEZE_NONVERB_STRUCTURE_SHA256 = {3: "1e99c67e…", 4: "1e99c67e…"}` (same value; the structure is unchanged — spec §3). `round_freeze_hashes(round)`: the `regression_reference_sha256` line becomes `j("tests/benchmarks/round3-regression-reference.json")` for every `round >= 3` (ruling: the AC-R3-02 reference is the Round 2 isolated scorer and is byte-invariant; ledger it); for `round >= 4` add `out["round_outcomes_sha256"] = file_sha256(root / "tests/benchmarks/round_outcomes.json")`, `out["round_recoveries_sha256"] = file_sha256(root / "tests/benchmarks/round_recoveries.json")`. The two doc-title shas and `t_policy_files` are supplied by `freeze_entry` (Task 2 / Step 4 below), not computed from the tree. Add `tests/benchmarks/round_outcomes.json` and `round_recoveries.json` to the byte-invariant lists of the simulation (Task 3) but not to `TOOLING_FILES` (they are state, hashed separately). `pending_round` callers in `structure_check_problems` pass no outcomes (they load the file).

Run the class → PASS; run `tests.benchmarks.test_evaluator` whole → the existing `test_freeze_key_set_per_round`, `test_round_freeze_file_shape` still PASS (rounds 1–2 unchanged).

- [ ] **Step 3: Failing tests for the freeze guard and the recovery verifier**

Append to `tests/benchmarks/test_round_seal.py`:

```python
class TestFreezeGuardAndRecovery(unittest.TestCase):
    F = [{"round": 1}, {"round": 2}]; O3 = [{"round": 3, "outcome": "pre-T not reached"}]
    def test_freeze_guard_round4_needs_closed_round3(self):
        with mock.patch.dict(ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256, {3: "a", 4: "b"}, clear=True):
            self.assertEqual(rs.freeze_guard_problems(4, self.F, self.O3, repo=None), [])
            self.assertIn("pending_round", rs.freeze_guard_problems(4, self.F, [], repo=None)[0])
            self.assertIn("pending_round", rs.freeze_guard_problems(5, self.F, self.O3, repo=None)[0])
    def test_freeze_guard_requires_recovery_attestation(self):
        f = self.F + [{"round": 4, "t_policy_files": ["tools/atlassian_docs/intelligence/data/search_aliases.json"]}]
        ab = lambda inv: self.O3 + [{"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": inv}]
        with mock.patch.dict(ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256, {3: "a", 4: "b", 5: "c"}, clear=True):
            self.assertEqual(rs.freeze_guard_problems(5, f, ab(False), repo=None), [])
            with mock.patch.object(ev, "load_round_recoveries", return_value=[]):
                self.assertIn("recovery", rs.freeze_guard_problems(5, f, ab(True), repo=None)[0])
    def test_verify_recovery_exact_chain(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_recovery_repo(pathlib.Path(td))            # helper below: H -> T -> X -> R (rollback) -> A (attestation)
            self.assertEqual(rs.verify_recovery(4, repo["path"]), [])
            self.assertTrue(any("parent(R)" in p for p in rs.verify_recovery(4, repo["path"], r_commit=repo["bad_r"])))
    def test_verify_recovery_tamper_cases(self):
        for tamper, needle in (("r_not_hk_bytes", "sha(HK:path)"), ("attestation_edited_after_A", "A blob"), ("before_sha_wrong", "sha(git show T:path)"), ("removed_aliases_wrong", "removed_aliases"), ("evidence_missing", "review_output_sha256")):
            with tempfile.TemporaryDirectory() as td:
                repo = _mk_recovery_repo(pathlib.Path(td), tamper=tamper)
                self.assertTrue(any(needle in p for p in rs.verify_recovery(4, repo["path"])), tamper)
```

`_mk_recovery_repo(root, tamper=None)` (test helper, ~60 lines): `git init` a temp repo; commit **H** with `search_aliases.json` containing no lexicon-r4 entries (known-good) and `round_outcomes.json`/`round_recoveries.json` (`[]`); commit **T** adding one `origin: lexicon-r4` alias (`notes[word] = {"origin": "lexicon-r4"}`) and `round_freeze.json` `[{"round": 4, "t_policy_files": ["tools/atlassian_docs/intelligence/data/search_aliases.json"], "round_recoveries_sha256": <sha of the [] file>, "round_outcomes_sha256": …}]`; commit **X** appending the `aborted-pre-B` outcome and a `docs/phase3-readiness.md` Round 4 section containing the line `housekeeping_commit: <H sha>` (the binding HK provenance); commit **R** restoring the H bytes of `search_aliases.json` and nothing else; commit **A** appending the attestation `{"round": 4, "t_commit": T, "xpreb_terminal_commit": X, "recovery_commit": R, "recovery_mode": "rollback", "reviewed_base": X, "reviewed_head": R, "reviewed_by": "test", "review_findings": 0, "review_output_sha256": "00"*32, "suite_commit": R, "suite_command": "python -m unittest discover -s tests -t .", "suite_exit_code": 0, "suite_output_sha256": "11"*32, "files": [{"path": …search_aliases.json, "before_sha256": sha(T blob), "after_sha256": sha(R blob), "known_good_sha256": sha(H blob)}], "removed_aliases": [word]}`. `tamper` variants: `r_not_hk_bytes` (R restores different bytes; attestation shas copied from R so only the HK comparison catches it), `attestation_edited_after_A` (a later commit edits `reviewed_by`), `before_sha_wrong`, `removed_aliases_wrong` (`[]`), `evidence_missing` (`review_output_sha256` absent); `bad_r` = a second R on top of R (`parent(bad_r) != X`). Run → FAIL (`freeze_guard_problems`, `verify_recovery` missing).

- [ ] **Step 4: Implement guard, verifier and the Round 4 freeze entry in `round_seal.py`**

```python
HIDDEN_RULES_R4 = tuple(HIDDEN_RULES_R3)
RECOVERY_DIFF_ONLY = ("tests/benchmarks/round_recoveries.json",)

def _git(repo, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()

def verify_recovery(round: int, repo, r_commit=None) -> list:
    """spec §9.5 / AC-R4-10: X -> R -> A exact chain; files[] == t_policy_files; after == known-good == R tree bytes."""
    recs = [r for r in ev.load_round_recoveries(pathlib.Path(repo) / "tests/benchmarks/round_recoveries.json") if r["round"] == round]
    if len(recs) != 1:
        return [f"round_recoveries.json: expected exactly one round {round} record, found {len(recs)}"]
    rec = recs[0]; R = r_commit or rec["recovery_commit"]; out = []
    # Binding provenance (spec §9.5): X, T and HK come from Git history / the X readiness block, never from the record alone.
    X = _git(repo, "log", "--format=%H", "-S", '"aborted-pre-B"', "--", "tests/benchmarks/round_outcomes.json").splitlines()[-1]
    T = _git(repo, "log", "--format=%H", "-S", f'"round": {round}', "--", "tests/benchmarks/round_freeze.json").splitlines()[-1]
    A = _git(repo, "log", "--format=%H", "-S", f'"round": {round}', "--", "tests/benchmarks/round_recoveries.json").splitlines()[-1]
    m = re.search(r"housekeeping_commit:\s*([0-9a-f]{7,40})", _git(repo, "show", f"{X}:docs/phase3-readiness.md").split(f"Round {round} ")[-1])
    if not m: return ["X readiness block has no housekeeping_commit line"]
    HK = _git(repo, "rev-parse", m.group(1))
    if not X.startswith(rec["xpreb_terminal_commit"]): out.append("xpreb_terminal_commit != the commit that introduced the aborted-pre-B outcome")
    if not T.startswith(rec["t_commit"]): out.append("t_commit != the commit that added the freeze entry")
    cur = hashlib.sha256((pathlib.Path(repo) / "tests/benchmarks/round_recoveries.json").read_bytes()).hexdigest()
    blob = hashlib.sha256(subprocess.run(["git", "-C", str(repo), "show", f"{A}:tests/benchmarks/round_recoveries.json"], check=True, capture_output=True).stdout).hexdigest()
    if cur != blob: out.append("current round_recoveries.json != A blob (edited after attestation)")
    if _git(repo, "rev-parse", f"{R}^") != _git(repo, "rev-parse", X): out.append("parent(R) != X")
    if _git(repo, "rev-parse", f"{A}^") != _git(repo, "rev-parse", R): out.append("parent(A) != R")
    freeze = json.loads(_git(repo, "show", f"{X}:tests/benchmarks/round_freeze.json"))
    policy_files = sorted(ev.freeze_for(round, freeze)["t_policy_files"])
    if sorted(_git(repo, "diff", "--name-only", f"{X}..{R}").splitlines()) != policy_files: out.append("diff X..R != RECOVERY_POLICY_FILES")
    if _git(repo, "diff", "--name-only", f"{R}..{A}").splitlines() != list(RECOVERY_DIFF_ONLY): out.append("diff R..A != {round_recoveries.json}")
    if sorted(f["path"] for f in rec["files"]) != policy_files: out.append("files[] != t_policy_files")
    for f in rec["files"]:
        sha = lambda c: hashlib.sha256(subprocess.run(["git", "-C", str(repo), "show", f"{c}:{f['path']}"], check=True, capture_output=True).stdout).hexdigest()
        if sha(T) != f["before_sha256"]: out.append(f"{f['path']}: before_sha256 != sha(git show T:path)")
        if sha(R) != sha(HK): out.append(f"{f['path']}: sha(R:path) != sha(HK:path) — rollback did not restore the known-good bytes")
        if sha(R) != f["after_sha256"] or f["after_sha256"] != f["known_good_sha256"] or sha(HK) != f["known_good_sha256"]: out.append(f"{f['path']}: after/known-good sha mismatch")
    if rec.get("reviewed_base") != X or rec.get("reviewed_head") != R or rec.get("suite_commit") != R: out.append("reviewed_base/head or suite_commit != X/R")
    if rec.get("review_findings") != 0 or rec.get("suite_exit_code") != 0: out.append("review_findings/suite_exit_code != 0")
    hexsha = lambda v: isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None
    if not (hexsha(rec.get("review_output_sha256")) and hexsha(rec.get("suite_output_sha256"))): out.append("review_output_sha256/suite_output_sha256 missing or not sha256 hex")
    if rec.get("recovery_mode") != "rollback" or not str(rec.get("reviewed_by", "")).strip() or not str(rec.get("suite_command", "")).strip(): out.append("recovery_mode/reviewed_by/suite_command incomplete")
    lex = lambda c: {w for w, n in json.loads(_git(repo, "show", f"{c}:tools/atlassian_docs/intelligence/data/search_aliases.json")).get("notes", {}).items() if n.get("origin") == f"lexicon-r{round}"}
    if lex(R): out.append(f"lexicon-r{round} aliases still present at R")
    if sorted(lex(T) - lex(R)) != sorted(rec.get("removed_aliases", [])): out.append("removed_aliases != lexicon-r4 words present at T and absent at R")
    return out
```

(`import re` at the top of `round_seal.py` already exists; `t_commit`/`xpreb_terminal_commit` in the record are cross-checked against the Git-derived values, never trusted.) Then:

```python
def freeze_guard_problems(round: int, freeze, outcomes, repo) -> list:
    out = []
    if ev.pending_round(freeze, outcomes) != round:
        return [f"pending_round is {ev.pending_round(freeze, outcomes)}, not {round}"]
    states = ev.round_states(freeze, outcomes)
    missing = [r for r in range(1, round) if r not in states]
    if missing: out.append(f"undecided lower rounds: {missing}")
    for r, st in states.items():
        if st == "aborted-pre-B" and next(o for o in outcomes if o["round"] == r).get("invalidates_policy"):
            if repo is None and not [x for x in ev.load_round_recoveries() if x["round"] == r]:
                out.append(f"round {r} invalidated its policy: recovery attestation required before round {round}")
            elif repo is not None:
                out += [f"round {r} recovery: {p}" for p in verify_recovery(r, repo)]
    return out
```

`cmd_freeze`: after the duplicate check, `problems = freeze_guard_problems(args.round, freeze, ev.load_round_outcomes(), repo=ROOT)`; print `REFUSED: …` and return 1 if non-empty. `freeze_entry(round, cache_dir, reference_enc=None, doc_sources=None, doc_titles=None, base_commit=None)`: for `round >= 4` require `--doc-title-sources`, `--doc-titles`, `--base-commit` (= `$W/housekeeping_commit`), set `entry["doc_titles_source_bundle_sha256"] = doc_titles.bundle_sha256(doc_sources)`, `entry["doc_titles_snapshot_sha256"] = ev.file_sha256(doc_titles)` after asserting `doc_titles.snapshot(doc_sources)` re-rendered equals the file bytes, `entry["t_policy_files"] = ev.t_policy_files(ROOT, base_commit)` where

```python
T_DATA_FILES = tuple(f"{DATA_REL}/{n}" for n in ("alias_candidates.json", "concept_lexicon.json", "search_aliases.json", "search_ranking.json"))
def t_policy_files(root, base_commit) -> list:
    changed = subprocess.run(["git", "-C", str(root), "diff", "--name-only", base_commit, "--"], check=True, capture_output=True, text=True).stdout.split()
    return sorted(p for p in set(changed) if p in T_DATA_FILES)
```

(both in `evaluator.py`; `freeze_entry` refuses when `changed` contains a path outside the §9.6 allowlist — `ev.T_ALLOWLIST = T_DATA_FILES + ("tests/benchmarks/round_freeze.json", "tests/benchmarks/search_queries.json", "tests/benchmarks/round4-worker-brief.md", "tests/benchmarks/round4-hidden-generation-prompt.md", "tests/benchmarks/round4-hidden-reviewer-prompt.md", "tests/benchmarks/round4-lexicon-generation-prompt.md", "tests/benchmarks/round4-lexicon-review-prompt.md", "tests/benchmarks/round4-method-safety.json")`). `hidden_generation_rules = list(HIDDEN_RULES_R4)` for round 4. CLI: `freeze` gains `--doc-title-sources`, `--doc-titles`, `--base-commit`; new subcommand `validate-terminal --round N --state X_preB --work DIR` → `cmd_validate_terminal` (Task 3 fills its checks; here it returns the problems of `terminal_problems()` which Task 3 implements — leave a `NotImplementedError` guarded by the test being added in Task 3). `verify-freeze` skips entries whose outcome is `aborted-pre-B` (spec §9.1: invalidated freeze 4 is excluded from current-file equality).

Run `tests.benchmarks.test_round_seal` → PASS; canonical suite → OK (expect 555 + new).

- [ ] **Step 5: AC-R4-04 check, commit H13**

```bash
git diff --stat HEAD -- tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py tools/atlassian_docs/intelligence/data/search_ranking.json   # must be empty
python -m unittest discover -s tests -t .
git add tests/benchmarks/round_outcomes.json tests/benchmarks/round_recoveries.json tests/benchmarks/evaluator.py tests/benchmarks/round_seal.py tests/benchmarks/test_evaluator.py tests/benchmarks/test_round_seal.py
git commit -m "H13: round state model — round_outcomes/recoveries, pending_round gap, compound aborted-pre-B, Round 4 freeze keys, freeze guard, recovery verifier

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Documentation-title corpus — `doc_titles.py` (source contract, preflight, acquisition bundle, epoch, snapshot, title extraction, render helpers), renderer extension, Round 4 lexicon prompts, no-benchmark-read invariant, `TOOLING_FILES` (commit H14)

**Files:**
- Create: `tests/benchmarks/doc_titles.py`, `tests/benchmarks/test_doc_titles.py`, `tests/benchmarks/round4-lexicon-generation-prompt.md`, `tests/benchmarks/round4-lexicon-review-prompt.md`, `tests/fixtures/doc_titles/{jira.sitemap.xml, confluence.sitemap.xml, admin.sitemap.xml, index.sitemap.xml, page-space.html, page-release.html, page-notitle.html}`
- Modify: `tests/benchmarks/concept_lexicon_check.py` (`render_lexicon_generation_input(template, internal, ranking_raw, doc_snapshot=None)`, `cmd_render_generation_input` `--doc-titles/--attachment-out`), `tests/benchmarks/evaluator.py` (`TOOLING_FILES`), `tests/benchmarks/round_seal.py` (`freeze_entry` uses `doc_titles.bundle_sha256`/`snapshot`)
- Test: `tests/benchmarks/test_doc_titles.py`, `tests/benchmarks/test_concept_lexicon_check.py`

**Interfaces:**
- Produces: `doc_titles.DOC_SOURCES: tuple[dict]` (rows `{"product","sitemap_url","allowed_loc_prefix"}` exactly as spec §5.1); `preflight(source, sitemap_bytes) -> list[str]`; `parse_sitemap(xml_bytes) -> ("urlset"|"sitemapindex", list[str])`; `extract_title(html_bytes) -> (title_tag: str|None, h1: str|None)`; `acquire(sources, out_dir, fetch, delay=0.25) -> dict` (manifest; `fetch(url) -> (status:int, final_url:str, body:bytes)`); `bundle_sha256(out_dir) -> str`; `snapshot(out_dir) -> dict` (`{"source_bundle_sha256", "sources", "titles": [{"product","url","title","tokens"}]}`); `titles_for(snapshot, token, limit=5) -> list`; `render_block(snapshot, concept_tokens) -> str`; `attachment_text(snapshot) -> str`; CLI `python -m tests.benchmarks.doc_titles acquire --out-dir DIR [--epoch k]`, `snapshot --sources DIR --out FILE`, `render-check --sources DIR --snapshot FILE`.
- Consumes: `act.concept_tokens(internal, noise)`, `ev.file_sha256`, `ev.canonical_sha256`, `tune._norm_tokens`-equivalent singularisation = `ev.singular`.

- [ ] **Step 1: Fixtures and the first failing tests (source contract, sitemap parsing, preflight)**

Fixture sitemaps: `jira.sitemap.xml` = `urlset` with 4 `<loc>` (3 under `https://support.atlassian.com/jira-software-cloud/docs/…/`, 1 under `https://support.atlassian.com/confluence-cloud/docs/…/` — the foreign one), `index.sitemap.xml` = `sitemapindex` pointing at `child-1.xml`, `admin.sitemap.xml` with one `<loc>` on host `example.com`. Fixture pages: `page-space.html` (`<title>What is a space? | Confluence Cloud | Atlassian Support</title>` and `<h1>What is a space?</h1>`), `page-release.html` (`<h1>Release your team&#39;s work in versions</h1>`), `page-notitle.html` (`<title>Only a title | Jira Cloud | Atlassian Support</title>`, no `<h1>`).

```python
class TestSourceContract(unittest.TestCase):
    def test_doc_sources_literal(self):
        self.assertEqual([s["product"] for s in dt.DOC_SOURCES], ["jira-software-cloud", "confluence-cloud", "jira-cloud-administration"])
        self.assertEqual(dt.DOC_SOURCES[0]["sitemap_url"], "https://support.atlassian.com/jira-cloud.xml")
        self.assertEqual(dt.DOC_SOURCES[0]["allowed_loc_prefix"], "https://support.atlassian.com/jira-software-cloud/docs/")
    def test_parse_sitemap_urlset_and_index(self):
        kind, locs = dt.parse_sitemap(FX("jira.sitemap.xml")); self.assertEqual(kind, "urlset"); self.assertEqual(len(locs), 4)
        self.assertEqual(dt.parse_sitemap(FX("index.sitemap.xml"))[0], "sitemapindex")
    def test_preflight_discards_foreign_prefix_and_counts(self):
        kept, discarded, problems = dt.preflight(dt.DOC_SOURCES[0], FX("jira.sitemap.xml"))
        self.assertEqual((len(kept), discarded, problems), (3, 1, []))
        self.assertIn("host", dt.preflight(dt.DOC_SOURCES[2], FX("admin.sitemap.xml"))[2][0])
    def test_preflight_rejects_empty(self):
        self.assertIn("count", dt.preflight(dt.DOC_SOURCES[1], b"<urlset/>")[2][0])
```

Run `python -m unittest tests.benchmarks.test_doc_titles -v` → FAIL (`ModuleNotFoundError: tests.benchmarks.doc_titles`).

- [ ] **Step 2: Implement sources, parsing and preflight**

```python
"""Documentation-title corpus for Round 4 (spec §5, §5.1, §6.1): sitemap acquisition into an immutable raw bundle,
deterministic snapshot of page <h1>/<title> text, and the DOCUMENTATION TITLES block for the lexicon generation input.
This module never reads tests/benchmarks/search_queries.json (AC-R4-05)."""
import argparse, gzip, hashlib, html, json, pathlib, re, sys, time, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlsplit

HOST = "support.atlassian.com"
DOC_SOURCES = (
    {"product": "jira-software-cloud", "sitemap_url": "https://support.atlassian.com/jira-cloud.xml", "allowed_loc_prefix": "https://support.atlassian.com/jira-software-cloud/docs/"},
    {"product": "confluence-cloud", "sitemap_url": "https://support.atlassian.com/confluence-cloud.xml", "allowed_loc_prefix": "https://support.atlassian.com/confluence-cloud/docs/"},
    {"product": "jira-cloud-administration", "sitemap_url": "https://support.atlassian.com/jira-cloud-administration.xml", "allowed_loc_prefix": "https://support.atlassian.com/jira-cloud-administration/docs/"},
)
MAX_FAIL_RATE = 0.05

def parse_sitemap(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    kind = root.tag.split("}")[-1]
    if kind not in ("urlset", "sitemapindex"):
        raise ValueError(f"sitemap root {kind!r}")
    locs = [e.text.strip() for e in root.iter() if e.tag.split("}")[-1] == "loc" and e.text]
    return kind, locs

def preflight(source, sitemap_bytes: bytes):
    """-> (kept_locs, discarded_count, problems). spec §5.1: root kind, host == HOST on every loc, prefix filter, count > 0."""
    try:
        kind, locs = parse_sitemap(sitemap_bytes)
    except (ET.ParseError, ValueError) as e:
        return [], 0, [f"{source['product']}: xml root/parse error: {e}"]
    problems, kept, discarded = [], [], 0
    for loc in locs:
        if urlsplit(loc).netloc != HOST:
            problems.append(f"{source['product']}: loc host != {HOST}: {loc}"); continue
        if kind == "urlset" and not loc.startswith(source["allowed_loc_prefix"]):
            discarded += 1; continue
        kept.append(loc)
    if not kept:
        problems.append(f"{source['product']}: count == 0 after prefix filter")
    return kept, discarded, problems
```

Run → PASS for the three classes above.

- [ ] **Step 3: Failing tests for title extraction, acquisition bundle, redirects, failure rate, bundle sha**

```python
def fake_fetch(pages, redirects=None, statuses=None):
    def fetch(url):
        final = (redirects or {}).get(url, url)
        return (statuses or {}).get(url, 200), final, pages.get(final, b"")
    return fetch

class TestAcquireAndSnapshot(unittest.TestCase):
    def test_extract_title_h1_entities_and_title_fallback(self):
        self.assertEqual(dt.extract_title(FX("page-release.html"))[1], "Release your team's work in versions")
        self.assertEqual(dt.extract_title(FX("page-notitle.html")), ("Only a title | Jira Cloud | Atlassian Support", None))
        self.assertEqual(dt.page_title("Only a title | Jira Cloud | Atlassian Support", None), "Only a title")
    def test_acquire_writes_bundle_manifest_and_gzip_pages(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "src"; m = dt.acquire(SOURCES_FX, out, fake_fetch(PAGES_FX), delay=0)
            self.assertEqual([s["product"] for s in m["sources"]], ["jira-software-cloud"])
            self.assertEqual(m["sources"][0]["discarded_loc_count"], 1); self.assertEqual(m["sources"][0]["page_ok"], 3)
            rows = [json.loads(l) for l in (out / "jira-software-cloud.pages.jsonl").read_text().splitlines()]
            gz = out / "pages" / f"{rows[0]['html_sha256']}.html.gz"
            self.assertEqual(hashlib.sha256(gzip.decompress(gz.read_bytes())).hexdigest(), rows[0]["html_sha256"])
            self.assertEqual(dt.bundle_sha256(out), dt.bundle_sha256(out))           # deterministic
    def test_acquire_redirect_outside_prefix_is_failed(self):
        with tempfile.TemporaryDirectory() as td:
            m = dt.acquire(SOURCES_FX, pathlib.Path(td), fake_fetch(PAGES_FX, redirects={LOC1: "https://support.atlassian.com/confluence-cloud/docs/x/"}), delay=0)
            row = next(r for r in dt.read_pages(pathlib.Path(td), "jira-software-cloud") if r["url"] == LOC1)
            self.assertEqual(row["fail_reason"], "redirect-outside-prefix"); self.assertNotIn("html_sha256", row)
    def test_acquire_rejects_nested_sitemapindex(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaises(SystemExit):
            dt.acquire([dict(dt.DOC_SOURCES[0], sitemap_url=IDX_URL)], pathlib.Path(td), fake_fetch({**PAGES_FX, IDX_URL: FX("index.sitemap.xml"), CHILD_URL: FX("index.sitemap.xml")}), delay=0)
    def test_acquire_aborts_over_fail_rate(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaises(SystemExit):
            dt.acquire(SOURCES_FX, pathlib.Path(td), fake_fetch(PAGES_FX, statuses={LOC1: 500}), delay=0)   # 1/3 > 5 %
    def test_snapshot_reads_only_bundle_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td); dt.acquire(SOURCES_FX, out, fake_fetch(PAGES_FX), delay=0)
            with mock.patch.object(dt, "default_fetch", side_effect=AssertionError("network")):
                snap = dt.snapshot(out)
            self.assertEqual(snap["source_bundle_sha256"], dt.bundle_sha256(out))
            self.assertEqual(json.dumps(snap, sort_keys=True), json.dumps(dt.snapshot(out), sort_keys=True))
            self.assertIn({"product": "jira-software-cloud", "url": LOC2, "title": "What is a space?", "tokens": ["what", "is", "a", "space"]}, snap["titles"])
    def test_snapshot_rejects_content_address_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td); dt.acquire(SOURCES_FX, out, fake_fetch(PAGES_FX), delay=0)
            gz = next((out / "pages").glob("*.html.gz")); gz.write_bytes(gzip.compress(b"<h1>tampered</h1>"))
            with self.assertRaises(SystemExit): dt.snapshot(out)
```

(`SOURCES_FX` = `(DOC_SOURCES[0],)` with a fixture `sitemap_url`; the fake fetch serves the fixture sitemap at that URL and the three pages at `LOC1..LOC3`. Tokens: `norm_tokens` lower-cases, splits on non-alphanumerics, singularises with `ev.singular`, keeps order, drops duplicates.) Run → FAIL.

- [ ] **Step 4: Implement extraction, acquisition, bundle sha, snapshot**

```python
class _Titles(HTMLParser):
    def __init__(self): super().__init__(); self.title = self.h1 = None; self._in = None
    def handle_starttag(self, tag, attrs):
        if tag in ("title", "h1") and (tag == "title" and self.title is None or tag == "h1" and self.h1 is None): self._in, self._buf = tag, []
    def handle_data(self, d):
        if self._in: self._buf.append(d)
    def handle_endtag(self, tag):
        if self._in == tag:
            text = re.sub(r"\s+", " ", html.unescape("".join(self._buf))).strip()
            setattr(self, "title" if tag == "title" else "h1", text); self._in = None

def extract_title(html_bytes: bytes):
    p = _Titles(); p.feed(html_bytes.decode("utf-8", errors="replace")); return p.title, p.h1

def page_title(title_tag, h1):
    return h1 if h1 else (title_tag or "").split(" | ")[0].strip()

def norm_tokens(text: str) -> list:
    from tests.benchmarks.evaluator import singular
    out = []
    for w in re.split(r"[^a-z0-9]+", text.lower()):
        if w and singular(w) not in out: out.append(singular(w))
    return out

def default_fetch(url, timeout=30):
    import urllib.error, urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "atlassian-api-updater round4 corpus"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read()
    except urllib.error.HTTPError as e:                      # 4xx/5xx become a failure row, never an exception
        return e.code, e.geturl() or url, b""
    except urllib.error.URLError as e:
        return 0, url, b""

def acquire(sources, out_dir, fetch=default_fetch, delay=0.25, epoch=1) -> dict:
    out_dir = pathlib.Path(out_dir); (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    manifest = {"epoch": epoch, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": []}
    for src in sources:
        status, _, sm = fetch(src["sitemap_url"])
        if not 200 <= status < 300: raise SystemExit(f"{src['product']}: sitemap HTTP {status}")
        (out_dir / f"{src['product']}.sitemap.xml").write_bytes(sm)
        kind, _ = parse_sitemap(sm); children = []
        locs, discarded, problems = preflight(src, sm)
        if kind == "sitemapindex":                                      # one level, every child kept raw
            kept, locs = locs, []
            for i, child in enumerate(kept, 1):
                st, _, cb = fetch(child)
                if not 200 <= st < 300: raise SystemExit(f"{src['product']}: child sitemap HTTP {st}")
                (out_dir / f"{src['product']}.child-{i}.sitemap.xml").write_bytes(cb)
                children.append({"file": f"{src['product']}.child-{i}.sitemap.xml", "sha256": hashlib.sha256(cb).hexdigest()})
                if parse_sitemap(cb)[0] != "urlset": raise SystemExit(f"{src['product']}: child sitemap {child} is not a urlset (one level only)")
                l, d, p = preflight(src, cb); locs += l; discarded += d; problems += p
        if problems: raise SystemExit("preflight: " + "; ".join(problems))
        rows, ok = [], 0
        for loc in locs:
            st, final, body = fetch(loc); time.sleep(delay)
            if not 200 <= st < 300: rows.append({"url": loc, "final_url": final, "http_status": st, "fail_reason": f"http-{st}"}); continue
            if urlsplit(final).netloc != HOST or not final.startswith(src["allowed_loc_prefix"]):
                rows.append({"url": loc, "final_url": final, "http_status": st, "fail_reason": "redirect-outside-prefix"}); continue
            sha = hashlib.sha256(body).hexdigest(); (out_dir / "pages" / f"{sha}.html.gz").write_bytes(gzip.compress(body, mtime=0))
            rows.append({"url": loc, "final_url": final, "http_status": st, "html_sha256": sha}); ok += 1
        (out_dir / f"{src['product']}.pages.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        failed = len(rows) - ok
        if rows and failed / len(rows) > MAX_FAIL_RATE: raise SystemExit(f"{src['product']}: {failed}/{len(rows)} pages failed (> 5 %)")
        manifest["sources"].append({"product": src["product"], "sitemap_url": src["sitemap_url"], "allowed_loc_prefix": src["allowed_loc_prefix"],
                                    "sitemap_sha256": hashlib.sha256(sm).hexdigest(), "child_sitemaps": children, "loc_count": len(locs) + discarded,
                                    "discarded_loc_count": discarded, "url_count": len(locs), "page_ok": ok, "page_failed": failed})
    manifest["pages_sha256"] = hashlib.sha256(b"".join(sorted(p.read_bytes() for p in (out_dir / "pages").glob("*.html.gz")))).hexdigest()
    (out_dir / "acquisition-manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest

def bundle_sha256(out_dir) -> str:
    out_dir = pathlib.Path(out_dir)
    files = sorted(p for p in out_dir.rglob("*") if p.is_file())
    from tests.benchmarks.evaluator import canonical_sha256
    return canonical_sha256([[str(p.relative_to(out_dir)), hashlib.sha256(p.read_bytes()).hexdigest()] for p in files])

def read_pages(out_dir, product) -> list:
    return [json.loads(l) for l in (pathlib.Path(out_dir) / f"{product}.pages.jsonl").read_text(encoding="utf-8").splitlines()]

def snapshot(out_dir) -> dict:
    """Deterministic, bundle-only (spec §5): titles from the gzip'd HTML; content-address check sha(gunzip) == row == filename."""
    out_dir = pathlib.Path(out_dir); manifest = json.loads((out_dir / "acquisition-manifest.json").read_text(encoding="utf-8"))
    titles = []
    for src in manifest["sources"]:
        for row in read_pages(out_dir, src["product"]):
            if "html_sha256" not in row: continue
            gz = out_dir / "pages" / f"{row['html_sha256']}.html.gz"; body = gzip.decompress(gz.read_bytes())
            if hashlib.sha256(body).hexdigest() != row["html_sha256"]: raise SystemExit(f"content-address mismatch: {gz.name}")
            t = page_title(*extract_title(body))
            if t: titles.append({"product": src["product"], "url": row["url"], "title": t, "tokens": norm_tokens(t)})
    titles.sort(key=lambda e: (e["product"], e["title"], e["url"]))
    return {"source_bundle_sha256": bundle_sha256(out_dir), "sources": manifest["sources"], "titles": titles}
```

Run → PASS (the `default_fetch` patch in `test_snapshot_reads_only_bundle…` proves no network in `snapshot`).

- [ ] **Step 5: Failing tests for the render helpers, the renderer extension and the no-benchmark-read invariant**

```python
class TestRender(unittest.TestCase):
    def test_titles_for_limit_and_order(self):
        snap = {"titles": [{"product": "p", "url": f"u{i}", "title": f"{c} space {i}", "tokens": ["space"]} for i, c in enumerate("fedcba")]}
        got = dt.titles_for(snap, "space"); self.assertEqual(len(got), 5); self.assertEqual([t["title"][0] for t in got], list("abcde"))
        self.assertEqual(dt.titles_for(snap, "zzz"), [])
    def test_render_block_and_attachment(self):
        snap = {"titles": [{"product": "confluence-cloud", "url": "u", "title": "What is a space?", "tokens": ["what", "is", "a", "space"]}]}
        self.assertEqual(dt.render_block(snap, ["space", "issue"]), "space\tconfluence-cloud\tWhat is a space?\nissue\t-")
        self.assertEqual(dt.attachment_text(snap), "confluence-cloud\tWhat is a space?\n")
    def test_module_never_names_the_benchmark(self):
        src = pathlib.Path(dt.__file__).read_text(encoding="utf-8")
        self.assertNotIn("search_queries", src.replace("never reads tests/benchmarks/search_queries.json", ""))
```

In `tests/benchmarks/test_concept_lexicon_check.py`:

```python
    def test_render_generation_input_with_doc_titles_block_and_attachment(self):
        tpl = 'C:\n<one line per concept: "<token>\\t<count>\\t<products>\\t<excerpt>">\nT:\n<one line per concept title: "<token>\\t<product>\\t<title words>">\nV:\n<verb keys>\n'
        snap = {"titles": [{"product": "jira-software-cloud", "url": "u", "title": "Create an issue", "tokens": ["create", "an", "issue"]}]}
        out = clc.render_lexicon_generation_input(tpl, INTERNAL_FX, RANKING_FX, doc_snapshot=snap)
        self.assertIn("issue\tjira-software-cloud\tCreate an issue", out); self.assertNotIn("<one line per concept title", out)
        self.assertEqual(clc.render_lexicon_generation_input(tpl, INTERNAL_FX, RANKING_FX, doc_snapshot=snap), out)
    def test_render_generation_input_never_opens_benchmark(self):
        real_open = open
        def guard(path, *a, **k):
            if "search_queries.json" in str(path): raise AssertionError("benchmark read")
            return real_open(path, *a, **k)
        with mock.patch("builtins.open", guard), mock.patch("pathlib.Path.read_text", autospec=True, side_effect=lambda self, *a, **k: (_ for _ in ()).throw(AssertionError("benchmark read")) if "search_queries" in str(self) else real_open(self, encoding=k.get("encoding", "utf-8")).read()):
            clc.render_lexicon_generation_input(TPL4, INTERNAL_FX, RANKING_FX, doc_snapshot={"titles": []})
```

Run → FAIL (`titles_for`, new placeholder, `doc_snapshot` kwarg missing).

- [ ] **Step 6: Implement render helpers and the renderer extension; write the frozen prompts**

```python
def titles_for(snap, token, limit=5) -> list:
    return sorted((t for t in snap["titles"] if token in t["tokens"]), key=lambda t: (t["product"], t["title"]))[:limit]

def render_block(snap, concept_tokens) -> str:
    lines = []
    for tok in concept_tokens:
        hits = titles_for(snap, tok)
        lines += [f"{tok}\t{h['product']}\t{h['title']}" for h in hits] or [f"{tok}\t-"]
    return "\n".join(lines)

def attachment_text(snap) -> str:
    seen, out = set(), []
    for t in sorted(snap["titles"], key=lambda t: (t["product"], t["title"])):
        if (t["product"], t["title"]) not in seen: seen.add((t["product"], t["title"])); out.append(f"{t['product']}\t{t['title']}\n")
    return "".join(out)
```

`concept_lexicon_check.render_lexicon_generation_input(template, internal, ranking_raw, doc_snapshot=None)`: after the CONCEPTS replacement, if `doc_snapshot is not None` replace `'<one line per concept title: "<token>\\t<product>\\t<title words>">'` with `dt.render_block(doc_snapshot, list(tokens))`; the final placeholder check adds `"<one line per concept title" in out`. `cmd_render_generation_input` gains `--doc-titles PATH` (loads the snapshot JSON) and `--attachment-out PATH` (writes `dt.attachment_text`); prints `doc_titles_attachment_sha256` and `doc_titles_snapshot_sha256` too. `tests/benchmarks/round4-lexicon-generation-prompt.md` = the Round 3 generation prompt (`round3-lexicon-generation-prompt.md`) with: the `-r3`→`-r4` names, a `DOCUMENTATION TITLES:` section holding the new placeholder right after the CONCEPTS section, and this paragraph inserted before the rules (spec §6.2, verbatim):

```
DOCUMENTATION TITLES lists the current titles of the product's official help pages that mention each resource, and the attached
file doc-titles.txt lists all of them. These titles show the words the product's user interface and its users use for each
resource. Propose those words as synonyms. Include such a word even when it is itself a catalog term of a different product,
if users of this product call this resource by it.
```

`round4-lexicon-review-prompt.md` = `round3-lexicon-review-prompt.md` byte-identical except the round name. CLI `main()` for `doc_titles.py`: `acquire --out-dir DIR [--epoch k] [--delay 0.25]` (uses `DOC_SOURCES`, `default_fetch`; prints the manifest), `snapshot --sources DIR --out FILE` (writes the snapshot JSON with `sort_keys`, prints both shas), `render-check --sources DIR --snapshot FILE` (exit 1 if `snapshot(DIR)` != file bytes). `evaluator.TOOLING_FILES += ("tests/benchmarks/doc_titles.py", "tests/benchmarks/test_doc_titles.py")` **only** (the simulation files are added in Task 3 when they exist — `tooling_code_sha256` reads every listed file, so a missing file would make the hash undefined); add `test_tooling_files_exist_and_one_byte_changes_sha` (every `TOOLING_FILES` path exists; a temp copy of the tree with one byte appended to `doc_titles.py` gives a different `tooling_code_sha256`). `round_seal.freeze_entry` (Task 1 Step 4) now imports `doc_titles` for the two shas.

Run `tests.benchmarks.test_doc_titles tests.benchmarks.test_concept_lexicon_check tests.benchmarks.test_evaluator` → PASS.

- [ ] **Step 7: AC-R4-04 check, commit H14**

```bash
git diff --stat HEAD -- tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py tools/atlassian_docs/intelligence/data/search_ranking.json   # empty
python -m unittest discover -s tests -t .
git add tests/benchmarks/doc_titles.py tests/benchmarks/test_doc_titles.py tests/fixtures/doc_titles tests/benchmarks/round4-lexicon-generation-prompt.md tests/benchmarks/round4-lexicon-review-prompt.md tests/benchmarks/concept_lexicon_check.py tests/benchmarks/test_concept_lexicon_check.py tests/benchmarks/evaluator.py tests/benchmarks/test_evaluator.py tests/benchmarks/round_seal.py
git commit -m "H14: documentation-title corpus (source contract, preflight, raw bundle with gzip HTML, deterministic snapshot), DOCUMENTATION TITLES render block, Round 4 lexicon prompts, no-benchmark-read invariant

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Pipeline dry-run gate, cleanup needles, hidden-attempt ledger, `round4_simulation.py` (synthetic bundle, pre-T blockers, X_preB lifecycle), `validate-terminal`, Round 4 names, whole-branch review (commit H15 = `housekeeping_commit`)

**Files:**
- Modify: `tests/tune_search_ranking.py` (`PipelineResult`, `run_pipeline_result`, `main` uses it, `require_round`), `tests/benchmarks/round_seal.py` (`cleanup_needle_manifest_from_artifacts`, `append_attempt_needles`, `artifact_is_ledgered`, `cleanup_authority`, `terminal_problems`, `cmd_validate_terminal`), `tests/diag_search_queries.py` (no code change needed — `--round 4` is data-driven; verify), `tests/benchmarks/evaluator.py` (`TOOLING_FILES += round4_simulation.py, test_round4_simulation.py` — now that both exist)
- Create: `tests/benchmarks/round4_simulation.py`, `tests/benchmarks/test_round4_simulation.py`
- Test: `tests/test_tune_search_ranking.py`, `tests/benchmarks/test_round_seal.py`, `tests/benchmarks/test_round4_simulation.py`

**Interfaces:**
- Produces: `tune.PipelineResult` (dataclass: `selected_point, proposed_actions, validation_errors, seed_result, regression_result, fixture_result, tuning_accept`); `tune.run_pipeline_result(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn, queries, classes) -> PipelineResult` (calls `run_pipeline` then `validate_alias_change` and `tuning_accept`; pure); `tune.main` calls `run_pipeline_result` (test pins it); `rs.cleanup_needle_manifest_from_artifacts(paths) -> list[{words, sha256}]`; `rs.append_attempt_needles(ledger_path, paths) -> int`; `rs.cleanup_authority(ledger_path, standard_manifest_path, present_paths) -> list`; `rs.terminal_problems(round, state, repo, work) -> list[str]`; `sim.pre_t_blockers(result, pre_t_event) -> list[dict]`; `sim.run_pre_t(cache, work)` exit 0 iff `pre_t_blockers == []` ∧ AC-R3-01; `sim.apply_T/apply_B/apply_C/apply_D/apply_F/apply_X/apply_XpreB`; `--phase H` steps `T, B` then branches `D, F, X, XpreB`.
- Consumes: Task 1 state model, Task 2 `doc_titles`.

- [ ] **Step 1: Failing tests — `run_pipeline_result` and the production path**

Append to `tests/test_tune_search_ranking.py`:

```python
class TestPipelineResult(unittest.TestCase):
    def test_run_pipeline_result_fields_and_purity(self):
        perfect = lambda point, raw: ({"passed": 39, "failed": []}, {"raw_passed": 14, "effective_passed": 14, "passed": 14, "failed": []})
        res = tune.run_pipeline_result(perfect, tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE, lambda p, r: [], QUERIES, CLASSES)
        self.assertIsInstance(res, tune.PipelineResult); self.assertTrue(res.tuning_accept); self.assertEqual(res.validation_errors, [])
        self.assertEqual(res.selected_point, BASE)                                        # perfect at baseline → baseline selected
    def test_tuning_accept_false_when_regression_effective_short(self):
        short = lambda point, raw: ({"passed": 39, "failed": []}, {"raw_passed": 10, "effective_passed": 13, "passed": 13, "failed": [{"id": "rn-001"}]})
        self.assertFalse(tune.run_pipeline_result(short, tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE, lambda p, r: [], QUERIES, CLASSES).tuning_accept)
    def test_main_uses_run_pipeline_result(self):
        with mock.patch.object(tune, "run_pipeline_result", side_effect=RuntimeError("pinned")) as m, mock.patch.object(tune, "_with_state", side_effect=lambda c, fn: fn(FAKE_STATE)):
            with self.assertRaises(RuntimeError): tune.main(["--cache-dir", str(FIXTURE_CACHE), "--dry-run"])
        self.assertTrue(m.called)
```

Run → FAIL.

- [ ] **Step 2: Implement `PipelineResult`, `run_pipeline_result`, wire `main`**

```python
@dataclasses.dataclass
class PipelineResult:
    selected_point: dict; proposed_actions: dict; validation_errors: list
    seed_result: dict; regression_result: dict; fixture_result: dict; tuning_accept: bool

def run_pipeline_result(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn, queries, classes) -> PipelineResult:
    """spec §4.1 (Round 4): the ONE production orchestration, pure. main() and round4_simulation --phase pre-T both call it."""
    results, selected, working, patch, seed_res, reg_res, fixture_fail = run_pipeline(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn)
    errors = validate_alias_change(aliases_raw, working, cands_doc["candidates"], queries, classes)
    accept = tuning_accept(seed_res, reg_res, fixture_fail["final"]) and not errors
    return PipelineResult(selected, patch, errors, seed_res, reg_res, fixture_fail, accept)
```

In `main()`, replace the inline `run_pipeline(...)` + `validate_alias_change` + `tuning_accept` sequence with one `run_pipeline_result` call and read the fields (the log line, `_finish` and `--verify` keep their exact outputs — the byte-equality of the Round 3 log tests proves it). `require_round(min_round=3)` stays (pre-T `current_round` is 2 until T appends round 4; the brief runs after T).

Run `tests.test_tune_search_ranking` → PASS (existing `run_pipeline` tests untouched).

- [ ] **Step 3: Failing tests — cleanup needles, attempt ledger, cleanup authority**

Append to `tests/benchmarks/test_round_seal.py`:

```python
class TestCleanupNeedles(unittest.TestCase):
    def test_json_query_fields_exact_and_nonjson_windows(self):
        with tempfile.TemporaryDirectory() as td:
            j = pathlib.Path(td, "a.json"); j.write_text(json.dumps({"held_out": [{"query": "show my starred searches"}], "x": {"query": "list open bugs now"}}))
            m = rs.cleanup_needle_manifest_from_artifacts([j])
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("show my starred searches")}, m)
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("list open bugs now")}, m)
    def test_cleanup_needles_span_line_breaks(self):
        with tempfile.TemporaryDirectory() as td:
            raw = pathlib.Path(td, "attempt.txt"); raw.write_text("candidate answer is: show my starred\nsearches because ...\n")
            m = rs.cleanup_needle_manifest_from_artifacts([raw])
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("show my starred searches")}, m)
            leak = pathlib.Path(td, "leak.md"); leak.write_text("note: show my starred searches\n")
            self.assertEqual(rs.scan_for_needles([td], m, allow=[raw]), [str(leak)])
    def test_attempt_ledger_union_equals_recomputation(self):
        with tempfile.TemporaryDirectory() as td:
            a = pathlib.Path(td, "a.txt"); a.write_text("alpha beta gamma delta\n"); b = pathlib.Path(td, "b.json"); b.write_text('{"query": "one two three"}')
            led = pathlib.Path(td, "hidden_attempt_needles.jsonl")
            rs.append_attempt_needles(led, [a]); rs.append_attempt_needles(led, [b])
            self.assertEqual(sorted(map(json.dumps, rs.cleanup_authority(led, None, []))), sorted(map(json.dumps, rs.cleanup_needle_manifest_from_artifacts([a, b]))))
            std = pathlib.Path(td, "std.json"); std.write_text(json.dumps(rs.needle_manifest(["final set query here"])))
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("final set query here")}, rs.cleanup_authority(led, std, [a]))
    def test_delete_guard_requires_sha_and_needle_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            a = pathlib.Path(td, "a.txt"); a.write_text("alpha beta gamma\n"); led = pathlib.Path(td, "l.jsonl")
            self.assertFalse(rs.artifact_is_ledgered(led, a)); rs.append_attempt_needles(led, [a]); self.assertTrue(rs.artifact_is_ledgered(led, a))
            rows = [json.loads(l) for l in led.read_text().splitlines()]; rows[0]["needles"] = rows[0]["needles"][:-1]       # a row that under-covers its artifact
            led.write_text("".join(json.dumps(r) + "\n" for r in rows)); self.assertFalse(rs.artifact_is_ledgered(led, a))
```

Run → FAIL.

- [ ] **Step 4: Implement the needle helpers in `round_seal.py`**

```python
WINDOW = (3, 7)

def _json_queries(obj) -> list:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "query" and isinstance(v, str): out.append(v)
            else: out += _json_queries(v)
    elif isinstance(obj, list):
        for v in obj: out += _json_queries(v)
    return out

def cleanup_needle_manifest_from_artifacts(paths) -> list:
    """spec §9.4 / AC-R4-09: JSON artifacts → every `query` field (exact needles); non-JSON artifacts → every contiguous
    3..7-word window of the whole AC-18b-normalized word stream (line breaks are whitespace). Hash-only, deduplicated, sorted."""
    seen = {}
    for p in paths:
        text = pathlib.Path(p).read_text(encoding="utf-8", errors="ignore")
        try:
            qs = _json_queries(json.loads(text))
        except json.JSONDecodeError:
            words = _words(text); qs = [" ".join(words[i:i + n]) for n in range(WINDOW[0], WINDOW[1] + 1) for i in range(len(words) - n + 1)]
        for q in qs:
            w = _words(q)
            if w: seen[(len(w), _ngram_sha256(" ".join(w)))] = True
    return [{"words": n, "sha256": s} for n, s in sorted(seen)]

def append_attempt_needles(ledger_path, paths) -> int:
    rows = [{"artifact_sha256": ev.file_sha256(p), "needles": cleanup_needle_manifest_from_artifacts([p])} for p in paths]
    with open(ledger_path, "a", encoding="utf-8") as fh:
        for r in rows: fh.write(json.dumps(r, sort_keys=True) + "\n")
    return sum(len(r["needles"]) for r in rows)

def artifact_is_ledgered(ledger_path, path) -> bool:
    """Deletion guard (spec §9.4): the artifact's sha appears in the ledger AND its recomputed needles ⊆ the union of ledgered needles."""
    if not pathlib.Path(ledger_path).exists(): return False
    rows = [json.loads(l) for l in pathlib.Path(ledger_path).read_text(encoding="utf-8").splitlines()]
    sha = ev.file_sha256(path)
    if not any(r["artifact_sha256"] == sha for r in rows): return False
    ledgered = {(e["words"], e["sha256"]) for r in rows for e in r["needles"]}
    return all((e["words"], e["sha256"]) in ledgered for e in cleanup_needle_manifest_from_artifacts([path]))

def cleanup_authority(ledger_path, standard_manifest_path, present_paths) -> list:
    """union(historical attempt ledger, standard final-set manifest if any, needles recomputed from artifacts still present)."""
    seen = {}
    if pathlib.Path(ledger_path).exists():
        for l in pathlib.Path(ledger_path).read_text(encoding="utf-8").splitlines():
            for e in json.loads(l)["needles"]: seen[(e["words"], e["sha256"])] = True
    if standard_manifest_path:
        for e in json.loads(pathlib.Path(standard_manifest_path).read_text(encoding="utf-8")): seen[(e["words"], e["sha256"])] = True
    for e in cleanup_needle_manifest_from_artifacts(present_paths): seen[(e["words"], e["sha256"])] = True
    return [{"words": n, "sha256": s} for n, s in sorted(seen)]
```

Run → PASS.

- [ ] **Step 5: Failing tests — the Round 4 simulation (pre-T blockers from the dry-run, STOP semantics, X_preB lifecycle, synthetic bundle)**

Create `tests/benchmarks/test_round4_simulation.py`:

```python
class TestPreTBlockers(unittest.TestCase):
    def _res(self, seed_failed=(), reg_eff=14, fixture_final=(), errors=()):
        import tests.tune_search_ranking as tune
        return tune.PipelineResult({}, {}, list(errors), {"passed": 39 - len(seed_failed), "failed": [{"id": i} for i in seed_failed]},
                                   {"raw_passed": 12, "effective_passed": reg_eff, "failed": []}, {"constants": [], "final": list(fixture_final)},
                                   not seed_failed and reg_eff == 14 and not fixture_final and not errors)
    def test_no_blockers_when_pipeline_accepts(self):
        self.assertEqual(sim.pre_t_blockers(self._res(), {"pass": True}), [])
    def test_unreachable_seed_and_tuning_accept_false_are_distinct_blockers(self):
        b = sim.pre_t_blockers(self._res(seed_failed=["s-027"]), {"pass": True})
        self.assertEqual([x["kind"] for x in b], ["unreachable_seed"]); self.assertEqual(b[0]["seeds"], ["s-027"])
        b2 = sim.pre_t_blockers(self._res(reg_eff=13), {"pass": True}); self.assertEqual([x["kind"] for x in b2], ["tuning_accept_false"])
        both = sim.pre_t_blockers(self._res(seed_failed=["s-027"], reg_eff=13, errors=["budget exceeded"]), {"pass": False})
        self.assertEqual([x["kind"] for x in both], ["unreachable_seed", "tuning_accept_false", "alias_validation_error", "inherited_ac_r3_01_failure"])
        b3 = sim.pre_t_blockers(self._res(errors=["budget exceeded"]), {"pass": True}); self.assertEqual([x["kind"] for x in b3], ["alias_validation_error"])
        b4 = sim.pre_t_blockers(self._res(), {"pass": False}); self.assertEqual([x["kind"] for x in b4], ["inherited_ac_r3_01_failure"])
    def test_pre_t_gate_uses_dry_run_not_grid_reachability(self):
        """A seed correct at some grid point the selector never picks stays an unreachable_seed blocker."""
        res = self._res(seed_failed=["s-004"]); diag = {"reachable_by_grid": {"s-004": True}}
        b = sim.pre_t_blockers(res, {"pass": True}, diagnostics=diag)
        self.assertEqual(b[0]["kind"], "unreachable_seed"); self.assertTrue(b[0]["diagnostics"]["reachable_by_grid"]["s-004"])

class TestSyntheticBundle(unittest.TestCase):
    def test_synthetic_bundle_snapshot_and_render(self):
        with tempfile.TemporaryDirectory() as td:
            out = sim.synthetic_doc_bundle(pathlib.Path(td))                    # fixture catalog tokens → 20 fake pages, fake sitemap
            snap = dt.snapshot(out); self.assertEqual(len(snap["titles"]), 20)
            self.assertTrue(any(l.startswith("issue\tjira-software-cloud\t") for l in dt.render_block(snap, ["issue"]).splitlines()))

class TestStopSemantics(unittest.TestCase):
    F124 = [{"round": 1}, {"round": 2}, {"round": 4}]; F12 = [{"round": 1}, {"round": 2}]
    O3 = [{"round": 3, "outcome": "pre-T not reached"}]
    ABORT = {"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": True, "reject_reason": "t", "t_commit": "abc"}
    def _w(self, td, *events):
        w = pathlib.Path(td); (w / "controller-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events)); (w / "o.json").write_text(json.dumps(self.O3)); return w
    def test_outcome_append_refused_in_stop_state_then_allowed_after_user_decision(self):
        with tempfile.TemporaryDirectory() as td:
            w = self._w(td, {"event": "pre_t_checkpoint", "result": "stop_for_amendment"})
            with self.assertRaises(SystemExit): sim.append_outcome(w, {"round": 4, "outcome": "pre-T not reached"}, outcomes_path=w / "o.json", freeze=self.F12)
            (w / "controller-events.jsonl").open("a").write(json.dumps({"event": "user_decision", "decision": "TERMINAL_PRE_T_NOT_REACHED"}) + "\n")
            sim.append_outcome(w, {"round": 4, "outcome": "pre-T not reached"}, outcomes_path=w / "o.json", freeze=self.F12)   # closed without a freeze 4
    def test_aborted_pre_b_needs_the_real_freeze_entry(self):
        with tempfile.TemporaryDirectory() as td:
            w = self._w(td)
            sim.append_outcome(w, dict(self.ABORT), outcomes_path=w / "o.json", freeze=self.F124)                                  # freeze 4 present → ok
            w2 = self._w(td + "/x" if False else tempfile.mkdtemp())
            with self.assertRaises(ValueError): sim.append_outcome(w2, dict(self.ABORT), outcomes_path=w2 / "o.json", freeze=self.F12)   # orphan abort → refused
    def test_apply_outcome_cli_uses_repo_freeze(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ev, "load_round_freeze", return_value=self.F124), mock.patch.object(ev, "OUTCOMES", pathlib.Path(td, "o.json")):
            w = self._w(td); self.assertEqual(sim.main(["--apply-outcome", json.dumps(self.ABORT), "--work", str(w)]), 0)
            self.assertEqual(ev.load_round_outcomes(pathlib.Path(td, "o.json"))[-1]["outcome"], "aborted-pre-B")
```

`--phase H` acceptance (not a unittest; run in Step 8): the driver must print `ALL STEPS PASS` for `T, B` then branches `D, F, X, XpreB2, XpreB3, XpreB4, XpreB5`. `tests/benchmarks/test_round4_simulation.py` also carries the Round 3 synthetic tests adapted (`TestSyntheticHidden` with `round=4`, `TestSyntheticLexiconPhrase` with `sim.ROUND == 4`). Run → FAIL (`round4_simulation` missing).

- [ ] **Step 6: Create `round4_simulation.py`**

Copy `round3_simulation.py` to `round4_simulation.py`, then apply: `ROUND = 4`, `SIM_DIR = ".round4-sim"`, `BRANCHES = ("D", "F", "X", "XpreB")`, docstring. New/changed functions:

```python
def synthetic_doc_bundle(out_dir) -> pathlib.Path:
    """20 fake support pages whose <h1> contain fixture-catalog resource tokens, served through a fake fetch into a real bundle."""
    from tests.benchmarks import doc_titles as dt, round_seal as rs, alias_candidates_tool as act
    _, internal, _, _ = rs.load_catalogs_from_cache(_fixture_cache(), ROUND)
    noise = frozenset(_read(f"{DATA_REL}/search_ranking.json")["path_noise"])
    toks = list(act.concept_tokens(internal, noise))[:20]
    src = dict(dt.DOC_SOURCES[0]); locs = [f"{src['allowed_loc_prefix']}what-is-{t}-{i}/" for i, t in enumerate(toks)]
    pages = {u: f"<html><head><title>What is {t}? | Jira Cloud | Atlassian Support</title></head><body><h1>What is a {t}?</h1></body></html>".encode() for u, t in zip(locs, toks)}
    sm = ("<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in locs) + "</urlset>").encode()
    fetch = lambda url: (200, url, sm if url == src["sitemap_url"] else pages[url])
    dt.acquire([src], out_dir, fetch, delay=0); return pathlib.Path(out_dir)

def pre_t_blockers(result, event, diagnostics=None) -> list:
    """spec §4.1: the four blocker kinds; any → STOP_FOR_AMENDMENT (non-terminal)."""
    out = []                                                   # the four kinds are computed independently (spec §4.1, plan review 2 P1-2)
    unreachable = sorted(f["id"] for f in result.seed_result["failed"])
    if unreachable: out.append({"kind": "unreachable_seed", "seeds": unreachable, "diagnostics": diagnostics or {}})
    broken = {"regression_effective": result.regression_result["effective_passed"], "regression_failed": sorted(f["id"] for f in result.regression_result.get("failed", [])),
              "fixture_final": list(result.fixture_result["final"])}
    if result.regression_result["effective_passed"] != 14 or result.fixture_result["final"]:
        out.append({"kind": "tuning_accept_false", "invariants": broken})
    if result.validation_errors: out.append({"kind": "alias_validation_error", "errors": list(result.validation_errors)})
    if not event["pass"]: out.append({"kind": "inherited_ac_r3_01_failure", "event": {k: event[k] for k in ("seed", "regression_raw", "regression_effective", "fixture_failing", "equivalence_mismatches") if k in event}})
    return out

def append_outcome(work, record, outcomes_path=None, freeze=None):
    """pre-T not reached: only after a ledgered user decision (refused while the last pre-T event is STOP_FOR_AMENDMENT).
    aborted-pre-B: no STOP check (the round has a T), but the strict compound shape against the real freeze."""
    events = [json.loads(l) for l in (pathlib.Path(work) / "controller-events.jsonl").read_text(encoding="utf-8").splitlines()]
    if record["outcome"] == "pre-T not reached":
        last = next((e for e in reversed(events) if e.get("event") == "pre_t_checkpoint"), None)
        decided = any(e.get("event") == "user_decision" and e.get("decision") == "TERMINAL_PRE_T_NOT_REACHED" for e in events)
        if last and last.get("result") == "stop_for_amendment" and not decided:
            raise SystemExit("REFUSED: STOP_FOR_AMENDMENT is not terminal; a user_decision TERMINAL_PRE_T_NOT_REACHED event is required")
    from tests.benchmarks import evaluator as ev
    path = pathlib.Path(outcomes_path or ev.OUTCOMES); cur = ev.load_round_outcomes(path) if path.exists() else []
    fz = freeze if freeze is not None else ev.load_round_freeze()
    ev.round_states(fz, cur + [record])                        # strict shape check against the REAL freeze (aborted-pre-B needs freeze[N])
    path.write_text(json.dumps(cur + [record], indent=1) + "\n", encoding="utf-8")
```

`main()` gains `--apply-outcome JSON --work DIR` → `append_outcome(args.work, json.loads(args.apply_outcome))` (real freeze via `ev.load_round_freeze()`, real `ev.OUTCOMES`), exit 0 on success; this is the CLI Task 9 Step 2d calls. `run_pre_t(cache, work)`: as Round 3, then build the dry-run inputs exactly as `tune.main` does (`GridEvaluator` on `state`, `evaluate_point_fast` with the pre-T aliases as the "B" aliases, `cands_doc = alias_candidates.json`, `grid/baseline` from `rp`, `fixture_fn = fixture_failures_fast`, `queries/classes` from the classified bench), call `tune.run_pipeline_result(...)`, compute diagnostics `reachable_by_grid` (per failing seed: any grid point whose seed failures exclude it while fixture/regression invariants hold) and `dry_run_fixed`, then `blockers = pre_t_blockers(result, e, diagnostics)`; the event gains `pre_t_blockers`, `pipeline_input_sha256` (canonical sha of ranking, aliases, candidates, classified bench, grid), `pipeline_result_sha256` (canonical sha of `dataclasses.asdict(result)`), `result: "pass" | "stop_for_amendment"`, `blocking_reasons`; exit 0 iff `e["pass"] and not blockers`. **No file is written by the dry-run** (test: `tests.test_tune_search_ranking.test_main_uses_run_pipeline_result` plus a simulation test that patches `tune.write_constants`/`_write_log` to raise). `apply_T()`: before the freeze call, `bundle = synthetic_doc_bundle(ROOT / SIM_DIR / "doc-title-sources")`, `snap = dt.snapshot(bundle)` written to `ROOT / SIM_DIR / "doc-titles-snapshot.json"`, and the freeze call becomes `rs.main(["freeze", "--round", "4", "--cache-dir", str(cache), "--reference-enc", str(enc_path), "--doc-title-sources", str(bundle), "--doc-titles", str(snapshot_path), "--base-commit", "HEAD"])`; the synthetic lexicon merge uses `lexicon-r4`. `apply_XpreB()` (new branch, applied after T in its own tree, **without** B): write two synthetic attempt artifacts (one JSON with a `query`, one parse-invalid text with a line-split query) under `SIM_DIR/plain/`, `rs.append_attempt_needles(SIM_DIR/"hidden_attempt_needles.jsonl", …)`, delete them only after `artifact_is_ledgered` is true, write `SIM_DIR/xpreb_cleanup_manifest.json = rs.cleanup_authority(ledger, None, [])`, scan the tree with it (`unexpected_hits == []`), restore tracked policy files to the T tree (`git checkout T -- tools/atlassian_docs/intelligence/data tests/benchmarks/search_queries.json`), append the compound outcome `{"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": true, "reject_reason": "synthetic acquisition defect after T"}` with the sha chain events (`round_outcomes_sha256_at_T` from the freeze, pre-append equality assert, `round_outcomes_sha256_after_append`), render the readiness "Round 4 aborted before B" block, commit touching only `docs/phase3-readiness.md` and `tests/benchmarks/round_outcomes.json`, then `rs.main(["validate-terminal", "--round", "4", "--state", "X_preB", "--work", str(SIM_DIR)])` must return 0 and the suite must be green. `_run_suite_step` for `XpreB` applies it on a copy of the post-T tree (not post-B): adjust `drive()` so branch `XpreB` copies `tree_after_T` (saved right after step `T`). `apply_XpreB(state=2)` takes the spec §9.4 state to simulate: `2` (generator/review plaintext only), `3` (sealed plaintext only, ledgered at seal time), `4` (standard manifest + sealed plaintext, no ciphertext), `5` (ciphertext present, no plaintext); `--phase H` runs the XpreB branch once per state (`XpreB2..XpreB5`) and each must end with `validate-terminal` exit 0 — the unit test `test_xpreb_states_3_4_5_pass_terminal_validation` drives `apply_XpreB` for states 3–5 in a temp tree and asserts `terminal_problems(...) == []` and that the sealed plaintext was ledgered before deletion.

`rs.terminal_problems(round, state, repo, work)` for `state == "X_preB"` checks, each producing a message: freeze entry for `round` exists and no `round{round}_seal` with sealed sections (B absent: `search_queries.json` hidden sections `[]`); `git diff --name-only <T>..HEAD` ⊆ `{docs/phase3-readiness.md, tests/benchmarks/round_outcomes.json}` where `T` = the commit that added the freeze entry (`git log -S'"round": 4' -- round_freeze.json`); no `tests/benchmarks/round{round}-final.json`; outcomes record is compound with `invalidates_policy` a bool and `reject_reason`; ledger has `round_outcomes_sha256_at_T == freeze[round].round_outcomes_sha256`, `round_outcomes_sha256_after_append == current file sha`; ledger has `xpreb_cleanup` event with `cleanup_manifest_sha256` (or `cleanup_manifest: "not_applicable"` + `plaintext_generated: false` when `$W/hidden_attempt_needles.jsonl`, `$W/needle-manifest.json` and `$W/plain/` are all absent) and a scan verdict `unexpected_hits: []`; **the validator recomputes** `rs.cleanup_authority($W/hidden_attempt_needles.jsonl, $W/needle-manifest.json if present else None, remaining plaintext under $W/plain and sealed/round{round}-sealed.json if present)` and requires exact equality with `$W/xpreb_cleanup_manifest.json` (and that no plaintext remains); `hidden_evaluation_count == 0` as its own item: no `tests/benchmarks/round{round}-final.json`, no ledger event among `round{round}_gate_checkpoint`, `diag_run`, `hidden_evaluation`; `ciphertext_exists` consistent with `unused_due_to_X_preB` (`true` + sha, or `"not_applicable"`). `cmd_validate_terminal` prints the problems and returns 1 if any; tests cover each item with a synthetic `$W`.

Also: `evaluator.TOOLING_FILES += ("tests/benchmarks/round4_simulation.py", "tests/benchmarks/test_round4_simulation.py")` (the existence test of Task 2 covers them). Run the three test modules → PASS.

- [ ] **Step 7: Suite, `--phase H`, AC-R4-04, commit H15**

```bash
python -m unittest discover -s tests -t .                                  # expect OK
python -m tests.benchmarks.round4_simulation --phase H                     # expect ALL STEPS PASS (T, B, D, F, X, XpreB2..5)
git diff --stat HEAD -- tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py tools/atlassian_docs/intelligence/data/search_ranking.json   # empty
git add tests/tune_search_ranking.py tests/test_tune_search_ranking.py tests/benchmarks/round_seal.py tests/benchmarks/test_round_seal.py tests/benchmarks/round4_simulation.py tests/benchmarks/test_round4_simulation.py tests/benchmarks/evaluator.py tests/benchmarks/test_evaluator.py
git commit -m "H15: pipeline dry-run gate (PipelineResult, pre_t_blockers), cleanup needles + attempt ledger, round4_simulation (synthetic bundle, X_preB lifecycle), validate-terminal

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 8: Whole-branch review (fresh reviewer, most capable model) over `53b79c2..H15`**

Dispatch `superpowers:requesting-code-review` with the package `53b79c2..HEAD`, the spec path, this plan's Review Focus and the ledger rulings. Critical/Important → one fix pass with RED→GREEN tests, suite, `--phase H` again; the fix commit is H′ (pre-S, no pointer move). The resulting commit is `housekeeping_commit`; the ledger's first controller event pins it as `initial_housekeeping_commit`. **Plan review:** this plan itself goes to the ChatGPT thread before Task 1 starts; its verdict is ledgered in `$W/controller-events.jsonl` as `plan_review` once `$W` exists (Task 4) and in the SDD ledger before that.

---

## Controller procedure (Tasks 4–12)

The controller is this session or a fresh one (AC-R3-08 allows either; no actor saw hidden plaintext). Working dirs: `S=~/.atlassian_api_updater/round4-cache`, `W=~/.atlassian_api_updater/round4-work`, `A=~/.atlassian_api_updater/archive/round2/round2-work`, `R3=~/.atlassian_api_updater/archive/round3/round3-cache` (archived Round 3 S, fingerprint `a759181c…`). Evidence: `$W/controller-events.jsonl`, `$W/attempts.jsonl`, `$W/hidden_attempt_needles.jsonl`. Every "ledger" below = append one JSON line to `controller-events.jsonl`. Every decision point = a message on the ChatGPT review thread, ruling ledgered as `{"event": "ruling", "topic", "review_output_sha256", "decision"}`.

### Task 4: **[controller]** Pin `initial_housekeeping_commit`, create S, acquire the documentation-title corpus (epoch 1), verb inventory

**Files:** create outside the repo `$S`, `$W/{controller-events,attempts}.jsonl`, `$W/doc-title-sources/` (bundle), `$W/doc-titles-snapshot.json`, `$W/doc-titles.txt`; modify `search_ranking.json` (`verb_methods` suffixes only, uncommitted until T); create `tests/benchmarks/round4-method-safety.json` (committed at T).

- [ ] **Step 1: Pin and create S** — as Round 3 plan v16 Task 9 Step 1 with the substitutions, plus: the first ledger event is `{"event": "initial_housekeeping_commit", "sha": <H15 or last H′>, "round4_start_commit": "237d2c9", "controller_actor_id", "session_id", "plan_review": {"verdict", "review_output_sha256"}}`; the S-reuse rule compares the live fetch with the **archived Round 3 S** (`$R3`, fingerprint `a759181c…` and its three spec shas from the Round 3 readiness block) → `s_reused_from_round3: true|false`. Then `round_seal.py catalog --round 4 --cache-dir $S --out $W/round4-generator-catalog.json --internal-out $W/round4-internal-catalog.json`; `export ATLASSIAN_DOCS_ROUND4_CACHE=$S`.
- [ ] **Step 2: Acquire the corpus (network, once per epoch)**

```bash
python -m tests.benchmarks.doc_titles acquire --out-dir $W/doc-title-sources --epoch 1 2>&1 | tee $W/acquire-epoch1.log
python -m tests.benchmarks.doc_titles snapshot --sources $W/doc-title-sources --out $W/doc-titles-snapshot.json
python -m tests.benchmarks.doc_titles render-check --sources $W/doc-title-sources --snapshot $W/doc-titles-snapshot.json   # exit 0
chmod -R a-w $W/doc-title-sources
```

Expected: three sources, `urlset` each, `url_count` ≈ 1,088 / 919 / 428, `page_failed` ≤ 5 % each, ≈ 10–15 min wall-clock. Ledger `doc_titles_acquired` (manifest fields per source, `doc_titles_epoch: 1`, `doc_titles_source_bundle_sha256`) and `doc_titles_snapshot` (`doc_titles_snapshot_sha256`, title count). A preflight failure or > 5 % failures → one manual re-run after the ChatGPT ruling on the cause (acquisition-invalidating before any artifact exists is simply a fresh epoch directory `doc-title-sources-epoch2`); no partial corpus is used.

- [ ] **Step 3: Verb inventory and method-safety** — Round 3 plan v16 Task 9 Steps 2–4 with substitutions (`round4-method-safety.json`; prefix invariant against Round 2 unchanged). Ledger `verb_inventory_sha256`.

### Task 5: **[controller]** Concept lexicon — union of the archived Round 2 inputs and the Round 4 stateless generation with DOCUMENTATION TITLES

**Files:** `$W/lexicon-generation-input-r4.txt`, `$W/doc-titles.txt`, `$W/lexicon_raw_r4.json`, `$W/lexicon_structural.json`, `$W/lexicon-review-input-r4.txt`, `$W/lexicon_review_r4.json`; modify `concept_lexicon.json`, `search_aliases.json` (lexicon-r4 merge only).

- [ ] **Step 1: Save the pre-merge inputs and render** —

```bash
cp tools/atlassian_docs/intelligence/data/search_aliases.json $W/aliases-premerge.json; cp tests/benchmarks/search_queries.json $W/bench-preclassify.json
python tests/benchmarks/concept_lexicon_check.py render-generation-input --cache-dir $S --round 4 --template tests/benchmarks/round4-lexicon-generation-prompt.md \
  --doc-titles $W/doc-titles-snapshot.json --attachment-out $W/doc-titles.txt --out $W/lexicon-generation-input-r4.txt
```

Ledger `lexicon_generation_input_rendered` (`rendered_sha256`, `template_sha256`, `doc_titles_snapshot_sha256`, `doc_titles_attachment_sha256`, concept count). Re-render → identical sha (AC-R4-02).

- [ ] **Step 2: Generate (stateless)** — as Round 3 plan v16 Task 21 Step 2 with substitutions, but **two attachments** (`lexicon-generation-input-r4.txt` and `doc-titles.txt`; the message body is the input text byte-exact); the `attempts.jsonl` line carries both attachment shas and `temporary_chat_unpersonalized: true`. Save the first parseable JSON object as `$W/lexicon_raw_r4.json`.
- [ ] **Step 3: Structural stage over the union, review input, review (second actor), finalize, gate, merge** — Round 3 plan v16 Task 21 Steps 3–4 with substitutions (`--raw $A/lexicon_raw.json $W/lexicon_raw_r4.json`, review/generation-input/review-input lists likewise, `--template tests/benchmarks/round2-lexicon-generation-prompt.md tests/benchmarks/round4-lexicon-generation-prompt.md`, `lexicon-gate --round 4`, `merge --round 4`). `concept_lexicon.json.components` must also record `doc_titles_snapshot_sha256` (finalize gains `--doc-titles` and writes it; add this to Task 2 Step 6's CLI changes — a one-line addition to `cmd_finalize` plus a test asserting the key). Ledger `lexicon_regated` as in Round 3 plus the doc-titles shas.
- [ ] **Step 4: Coverage diagnostic** — Round 3 plan v16 Task 21 Step 5 (`release→version`, `workspace→space`, `starred→favourite`, the two phrase rules); ledger `lexicon_gap_coverage`. Information only; no hand-added entries.

### Task 6: **[controller]** Candidates, R5/R6, AC-13 replay, **binding pre-T dry-run gate**, frozen texts, freeze, commit T, post-T `t_policy_files` check

- [ ] **Step 1: Candidates and classification** — Round 3 plan v16 Task 11 Step 1 (`--round 4`).
- [ ] **Step 2: AC-13 replay** — Round 3 plan v16 Task 11 Step 2 with substitutions; the replay also re-renders the generation input with `--doc-titles $W/doc-titles-snapshot.json` and asserts the rendered sha equals the ledgered one. A mismatch is a tooling defect → H′ (bundle-preserving unless the defect is in `doc_titles.acquire/preflight/parse_sitemap`, which is acquisition-invalidating: new epoch directory, new acquisition, regenerate Tasks 5–6 from Step 1 of Task 5; ledger `h_prime_kind`, `doc_titles_epoch`, `replaces_bundle_sha256`).
- [ ] **Step 3: Binding pre-T checkpoint = AC-R3-01 + dry-run gate (AC-R4-06)**

```bash
python -m tests.benchmarks.round4_simulation --phase pre-T --cache-dir $S --work $W
```

Exit 0 → continue. Exit 1 → the event's `result` is `stop_for_amendment` with `blocking_reasons`; **do not freeze, do not generate hidden records**. Write the blocker report (seed ids, dry-run `seed_result`/`regression_result`/`fixture_result`, `validation_errors`, `reachable_by_grid`/`dry_run_fixed` diagnostics) and take it to the ChatGPT thread; the ruling is one of: (a) amendment B of spec §11 (same-product doc-evidenced synonym) → spec v1.x + plan v+1 + a reviewed H′ implementing it → rerun from Task 5 Step 3 on the same S and bundle; (b) another design amendment (same flow); (c) `TERMINAL_PRE_T_NOT_REACHED` — the user's decision (hard stop: report and wait). STOP never appends to `round_outcomes.json` (Task 3 `append_outcome` refuses).

- [ ] **Step 4: Frozen texts** — `round4-worker-brief.md`, `round4-hidden-generation-prompt.md`, `round4-hidden-reviewer-prompt.md` = the Round 3 plan v16 Task 11 Steps 4–6 texts with substitutions (`ROUND4-WORKER-HANDSHAKE`, `round4-work`, `search-tuning-round4.jsonl`, `-r4` origins, `round4-internal-catalog.jsonl`); nothing else changes (the hidden rules are `HIDDEN_RULES_R4 == HIDDEN_RULES_R3`).
- [ ] **Step 5: Reset the bench hidden sections (if still Round 2 stubs), freeze, commit T, post-T check**

```bash
python - <<'EOF2'
import json, pathlib
b = pathlib.Path("tests/benchmarks/search_queries.json"); d = json.loads(b.read_text(encoding="utf-8"))
before = {s: d[s] for s in ("held_out", "negative")}
d["held_out"], d["negative"] = [], []; b.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"event": "bench_hidden_sections_reset", "previous": before}))
EOF2
HK=$(cat $W/housekeeping_commit)
python tests/benchmarks/round_seal.py freeze --round 4 --cache-dir $S --reference-enc ~/.atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc \
  --doc-title-sources $W/doc-title-sources --doc-titles $W/doc-titles-snapshot.json --base-commit $HK
python -m unittest discover -s tests -t .
TF=$(python -c "from tests.benchmarks import evaluator as ev; print(' '.join(ev.TOOLING_FILES))")
git diff --exit-code "$HK" -- $TF tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py      # AC-05 / AC-R4-04
git diff --name-only "$HK" | sort > $W/t-changed.txt                                                                                # ⊆ §9.6 allowlist (freeze already refused otherwise)
git add tools/atlassian_docs/intelligence/data/search_ranking.json tools/atlassian_docs/intelligence/data/search_aliases.json tools/atlassian_docs/intelligence/data/concept_lexicon.json tools/atlassian_docs/intelligence/data/alias_candidates.json \
        tests/benchmarks/round_freeze.json tests/benchmarks/search_queries.json tests/benchmarks/round4-worker-brief.md tests/benchmarks/round4-hidden-generation-prompt.md tests/benchmarks/round4-hidden-reviewer-prompt.md \
        tests/benchmarks/round4-lexicon-generation-prompt.md tests/benchmarks/round4-lexicon-review-prompt.md tests/benchmarks/round4-method-safety.json
git commit -m "T: Round 4 freeze (verb suffixes, lexicon-r4 with doc-title corpus, candidates, R5/R6, frozen texts, reference set, doc-title bundle/snapshot shas, t_policy_files)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
python - <<'EOF2'
import json, subprocess
from tests.benchmarks import evaluator as ev
hk = open(__import__("os").path.expanduser("~/.atlassian_api_updater/round4-work/housekeeping_commit")).read().strip()
actual = sorted(subprocess.run(["git", "diff", "--name-only", f"{hk}..HEAD"], capture_output=True, text=True).stdout.split())
outside = [p for p in actual if p not in ev.T_ALLOWLIST]
assert not outside, f"T touched files outside the §9.6 allowlist: {outside}"
changed = [p for p in actual if p in ev.T_DATA_FILES]
assert changed == sorted(ev.freeze_for(4)["t_policy_files"]), (changed, ev.freeze_for(4)["t_policy_files"])
print(json.dumps({"event": "post_t_policy_files_check", "t_files": actual, "t_policy_files": changed, "ok": True}))
EOF2
```

Ledger the printed events, the freeze printout (`reference_set.enc_sha256 == c1a3794b…`, `hidden_generation_rules == list(HIDDEN_RULES_R4)`, both doc-title shas, `round_outcomes_sha256`, `round_recoveries_sha256`, `t_policy_files`), and the AC-23 `T` suite checkpoint on the clean HEAD.

### Task 7: **[controller]** Hidden-set generation, machine check, stateless review, attempt-needle ledger, AC-18b hygiene, commit B, encryption

Round 3 plan v16 Task 12 Steps 1–4 with substitutions, plus the spec §9.4 hygiene additions:
- Every artifact that may contain hidden text (generator raw output, each replacement output, the review input/outputs, section-replacement outputs, parse-invalid responses saved for the ledger) is written under `$W/plain/` and **immediately** registered: `python -c "import sys; from tests.benchmarks import round_seal as rs; rs.append_attempt_needles(sys.argv[1], sys.argv[2:])" $W/hidden_attempt_needles.jsonl $W/plain/<the file just written>` — run once per artifact right after writing it, with the artifact's actual path as the argument. A file is deleted only after `rs.artifact_is_ledgered` is true (the controller script for Step 4's `rm -rf $W/plain` first asserts every file under it is ledgered, exactly as Task 9 Step 2d's hygiene script does).
- The sealed plaintext itself is a hidden-text artifact: right after Step 1 stores `~/.atlassian_api_updater/sealed/round4-sealed.json` (and after every `merge_replacements` rewrite of it) run `python -c "import sys; from tests.benchmarks import round_seal as rs; rs.append_attempt_needles(sys.argv[1], sys.argv[2:])" $W/hidden_attempt_needles.jsonl ~/.atlassian_api_updater/sealed/round4-sealed.json` — so spec §9.4 states (3) and (4) can pass the deletion guard (plan review 2 P0-2).
- Step 4 order stays: delete `$W/plain` → standard needle manifest (final 24) → seal `--needle-manifest` → pre-encryption scan → user encrypts → absence/ciphertext checks → commit B → post-B scan. Add after the manifest: ledger `cleanup_authority_sha256 = sha256(json.dumps(rs.cleanup_authority(ledger, manifest, [])))` so a later X check can prove the union was computed.
- If an acquisition/freeze defect is discovered at any point between T and B → **Task 9 Step 2d (X_preB)**, not X.

### Task 8: **[controller]** S checkpoint and worker dispatch (B..C)

Round 3 plan v16 Task 13 with substitutions (`ROUND4-WORKER-HANDSHAKE`, `verify-freeze --round 4`, brief sha == `freeze_for(4)["worker_brief_sha256"]`). The worker's `tune_search_ranking.py` run is the same `run_pipeline_result` the pre-T dry-run executed; the controller ledgers `pipeline_result_sha256` from the run log line and compares it with the pre-T dry-run value only as information (the B aliases differ from pre-T only by the frozen lexicon-r4 merge, which was already in the dry-run input — a mismatch is reported to the review thread, not acted on).

### Task 9: **[controller]** Provenance check, then C (success), F (tuning failure), X (abort) or X_preB (abort before B)

- [ ] **Steps 1, 2a, 2b, 2c** — Round 3 plan v16 Task 14 with substitutions (`verify-freeze --round 4`, readiness rendered by Task 11, AC-18a/AC-R3-06 checkpoints with `round4` names).
- [ ] **Step 2d: X_preB (spec §9.4, AC-R4-09)** — triggered by a corpus/freeze invalidation found after T and before B. First the ruling on the review thread (`invalidates_policy` true iff the invalid corpus reached `lexicon-r4`/`concept_lexicon.json`); then, with `REASON`, `INVALIDATES` (`true`|`false`) and `FOUND_AT=$(git rev-parse HEAD)` set from that ruling:

```bash
W=~/.atlassian_api_updater/round4-work; SEALED=~/.atlassian_api_updater/sealed
T=$(git log --format=%H -S'"round": 4' -- tests/benchmarks/round_freeze.json | tail -1)
sha() { python -c "from tests.benchmarks import evaluator as ev; print(ev.file_sha256('$1'))"; }
python - "$REASON" "$INVALIDATES" "$FOUND_AT" "$T" <<'EOF2'                                   # 1. xpreb_start
import json, sys, pathlib
from tests.benchmarks import evaluator as ev
W = pathlib.Path.home() / ".atlassian_api_updater" / "round4-work"; reason, inv, found, t = sys.argv[1:5]
e = {"event": "xpreb_start", "reason": reason, "found_at_commit": found, "t_commit": t, "invalidates_policy": inv == "true",
     "invalid_doc_titles_source_bundle_sha256": ev.freeze_for(4)["doc_titles_source_bundle_sha256"], "freeze_entry_sha256": ev.canonical_sha256(ev.freeze_for(4))}
open(W / "controller-events.jsonl", "a").write(json.dumps(e) + "\n"); print(json.dumps(e))
EOF2
python - <<'EOF2'                                                                              # 2. hidden hygiene by state (spec §9.4)
import json, pathlib, shutil
from tests.benchmarks import round_seal as rs, evaluator as ev
H = pathlib.Path.home() / ".atlassian_api_updater"; W = H / "round4-work"; led = W / "hidden_attempt_needles.jsonl"; std = W / "needle-manifest.json"
plain = sorted(p for p in (W / "plain").rglob("*") if p.is_file()) if (W / "plain").exists() else []
unsealed = H / "sealed" / "round4-sealed.json"; enc = H / "sealed" / "round4-sealed.json.enc"
present = plain + ([unsealed] if unsealed.exists() else [])
if not led.exists() and not std.exists() and not present:                                    # state (1): nothing was ever generated
    e = {"event": "xpreb_cleanup", "plaintext_generated": False, "cleanup_manifest": "not_applicable", "ciphertext_exists": enc.exists(),
         "unused_due_to_X_preB": (True if enc.exists() else "not_applicable"), "ciphertext_sha256": (ev.file_sha256(enc) if enc.exists() else None)}
else:                                                                                        # states (2)–(5)
    for p in present:
        assert rs.artifact_is_ledgered(led, p), f"unledgered plaintext artifact: {p}"           # ledger first (append_attempt_needles), never delete blind
    manifest = rs.cleanup_authority(led, std if std.exists() else None, present)
    (W / "xpreb_cleanup_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for p in present: p.unlink()
    if (W / "plain").exists(): shutil.rmtree(W / "plain")
    e = {"event": "xpreb_cleanup", "plaintext_generated": True, "cleanup_manifest_sha256": ev.file_sha256(W / "xpreb_cleanup_manifest.json"),
         "standard_manifest_used": std.exists(), "ciphertext_exists": enc.exists(), "unused_due_to_X_preB": (True if enc.exists() else "not_applicable"),
         "ciphertext_sha256": (ev.file_sha256(enc) if enc.exists() else None)}
open(W / "controller-events.jsonl", "a").write(json.dumps(e) + "\n"); print(json.dumps(e))
EOF2
if [ -e $W/xpreb_cleanup_manifest.json ]; then
  python tests/benchmarks/round_seal.py scan --manifest $W/xpreb_cleanup_manifest.json --expect-sha256 "$(sha $W/xpreb_cleanup_manifest.json)" \
    --root ~/.atlassian_api_updater --root . --allow ~/.atlassian_api_updater/round4-cache --allow $W/doc-title-sources --allow ~/.atlassian_api_updater/archive/round2/round2-cache \
    $( [ -e $SEALED/round4-sealed.json.enc ] && echo --allow $SEALED/round4-sealed.json.enc ) | tee -a $W/controller-events.jsonl          # unexpected_hits must be []
fi
git checkout "$T" -- tools/atlassian_docs/intelligence/data tests/benchmarks/search_queries.json                        # 3. restore the T tree
test -z "$(git diff --name-only "$T" -- . ':!docs/phase3-readiness.md' ':!tests/benchmarks/round_outcomes.json')"
AT=$(sha tests/benchmarks/round_outcomes.json)                                                                          # 4. outcomes chain
test "$AT" = "$(python -c "from tests.benchmarks import evaluator as ev; print(ev.freeze_for(4)['round_outcomes_sha256'])")"
echo "{\"event\": \"round_outcomes_sha256_at_T\", \"sha256\": \"$AT\"}" >> $W/controller-events.jsonl
python -m tests.benchmarks.round4_simulation --apply-outcome "{\"round\": 4, \"outcome\": \"aborted-pre-B\", \"invalidated_by\": \"X_preB\", \"invalidates_policy\": $INVALIDATES, \"reject_reason\": \"$REASON\", \"t_commit\": \"$T\"}"
echo "{\"event\": \"round_outcomes_sha256_after_append\", \"sha256\": \"$(sha tests/benchmarks/round_outcomes.json)\"}" >> $W/controller-events.jsonl
```

(`--apply-outcome` is the CLI wrapper of `append_outcome`; for `aborted-pre-B` it bypasses the STOP check and verifies the compound shape via `ev.round_states`.) Then render the readiness "Round 4 aborted before B" block (Task 11; it carries `housekeeping_commit: <sha>` — the binding provenance `verify_recovery` reads), commit `X_preB: Round 4 aborted before B ($REASON)` touching only `docs/phase3-readiness.md` and `tests/benchmarks/round_outcomes.json`; `python tests/benchmarks/round_seal.py validate-terminal --round 4 --state X_preB --work $W` → exit 0; suite green; `terminal_commit` ledger. Continue with Task 12. The recovery protocol (spec §9.5) runs only when the next round starts and only after a ruling on the thread: **R** = `git checkout $HK -- <freeze_for(4)["t_policy_files"]>` committed alone; **A** = the attestation append (fields as Task 1 Step 3's helper, real shas from `git show`), committed alone; `python -c "from tests.benchmarks import round_seal as rs; print(rs.verify_recovery(4, '.'))"` → `[]`.

### Task 10: **[D controller (fresh actor) + user]** Commit D — single gate evaluation, gate checkpoint, Round 2 reference observation

Round 3 plan v16 Task 15 with substitutions (`round4-sealed.json`, `--round 4`, `round4-final.json`, `round4_gate_checkpoint`, `round4_seal_sha256`). Gate (AC-R3-09b inherited): `held_out.passed ≥ 15/16`, `negative_actionable.raw_passed == 4/4`, `negative_abstained.effective_passed == 4/4`, `negative.effective_passed == 8/8`.

### Task 11: **[controller]** Subroutine — render the readiness Round 4 section from the ledgers

Append `## Search Quality Round 4 — decision record (<date>)` after the Round 3 section (never inside it). Fields: Round 3's list with `round4_start_commit 237d2c9`, `initial_housekeeping_commit`, `housekeeping_commit` (+ every `housekeeping_commit_moved` with `h_prime_kind`), spec v1.11 / the plan version that was executed (this file's header — v3 or later), `s_reused_from_round3`, `round4_operational_snapshot`, `round2_regression_snapshot`, `reference_set` (Round 2), **`doc_titles_snapshot`** (sources, fetch time, url/page counts, failed counts, bundle sha, snapshot sha, final `doc_titles_epoch`, `replaces_bundle_sha256[]`), `concept_lexicon.components.doc_titles_snapshot_sha256`, `t_policy_files`, `round_outcomes_sha256` (at T; and `_after_append` on `TERMINAL_PRE_T_NOT_REACHED` / X_preB), `round_recoveries_sha256_at_T`, the pre-T event(s) with `pre_t_blockers`, `pipeline_input_sha256`/`pipeline_result_sha256`, STOP rulings, terminal branch enum `D | F | X | X_preB | pre-T-not-reached`, and on X_preB the `xpreb_cleanup`/`unused_due_to_X_preB`/`invalidates_policy` block.

### Task 12: **[controller]** Post-terminal provenance review, memory, archive, dashboard, finishing

- Round 3 plan v16 Task 17 with substitutions (`terminal_commit` + post-terminal `reference-check` + `post_terminal_plaintext_scan` using the standard manifest, or on X_preB the cleanup manifest; allow list adds `$W/doc-title-sources`).
- Update memory (`search-quality-round4-design-status.md` → outcome; MEMORY.md), archive `round4-cache`, `round4-work` (bundle included) and `sealed/round4-sealed.json.enc` under `~/.atlassian_api_updater/archive/round4/` after the user confirms; republish the dashboard artifact (`https://claude.ai/artifact/ACaztzhjnZuS5tUGiqx3y4`) with the Round 4 state.
- `superpowers:finishing-a-development-branch` (merge/push only on the user's instruction).

## AC coverage map (spec v1.11)

| AC | Where |
|---|---|
| AC-R4-01 | Task 2 (`bundle_sha256`, `snapshot` determinism + content-address check, preflight), Task 6 Step 5 freeze (`--doc-title-sources/--doc-titles`, render-check), Task 4 Step 2 ledger, scans allow the bundle dir |
| AC-R4-02 | Task 2 Step 6 renderer + prompts (no synonym examples), Task 5 Steps 1–3 (stateless chats, both attachment shas, `components.doc_titles_snapshot_sha256`) |
| AC-R4-03 | Task 11 readiness (s-027 recorded as known-unreachable under §6; threshold 36 unchanged; bench sha) |
| AC-R4-04 | every H commit's empty `git diff --stat` on the three files (Tasks 1–3), Task 6 Step 5 `git diff --exit-code` + T allowlist |
| AC-R4-05 | Task 2 `test_module_never_names_the_benchmark`, `test_render_generation_input_never_opens_benchmark` |
| AC-R4-06 | Task 3 `pre_t_blockers` tests + `run_pre_t` dry-run (no writes), Task 6 Step 3 |
| AC-R4-07 | Task 1 state tests, freeze guard, `PRE_FREEZE…[4]`, Task 4 Step 1 start/ancestry ledger |
| AC-R4-08 | Task 2 preflight tests (`discarded_loc_count`, host, count), child sitemaps in `acquire` |
| AC-R4-09 | Task 3 `apply_XpreB` + `terminal_problems`, Task 9 Step 2d |
| AC-R4-10 | Task 1 `verify_recovery` + `freeze_guard_problems` tests, Task 9 Step 2d (6) |
| AC-R3-01..15, AC-18b (inherited) | Round 3 plan v16 mapping with substitutions; AC-01a → §9.2 (Task 4 Step 1), AC-22 → B-after only (Task 9 Step 2c) |

## Self-review notes

- Spec coverage: §4.1 (Task 3 + Task 6), §5/§5.1 (Task 2 + Task 4), §6.1–6.2 (Task 2 + Task 5), §9.1–9.6 (Task 1, Task 3, Task 6 Step 5, Task 9 Step 2d), §10 (map above), §11 B amendment (Task 6 Step 3 ruling path), §13 (H13/H14/H15 = Tasks 1–3).
- Type consistency: `PipelineResult` field names are the spec §4.1 names; `t_policy_files` is produced by `ev.t_policy_files` (Task 1) and consumed by `verify_recovery` (Task 1) and the post-T check (Task 6); `cleanup_needle_manifest_from_artifacts` / `append_attempt_needles` / `cleanup_authority` / `artifact_is_ledgered` are defined in Task 3 Step 4 and used by Task 7 and Task 9.
- Placeholders: none — "as Round 3 plan v16 Task N Step M" imports a committed, reviewed procedure verbatim with the substitution table (accepted by plan review 1 as a modular import, not a placeholder); runtime values in commands are shell/Python variables set in an earlier line of the same step (`$T`, `$HK`, `$REASON`, `$INVALIDATES`, `$FOUND_AT`); the only angle-bracket text left is `<the file just written>` in Task 7, which names the argument the controller substitutes per artifact.
- Rulings carried into the plan (to be ledgered at Task 4): (1) `round_freeze_hashes(4)` reads `round3-regression-reference.json` (AC-R3-02 reference is round-independent); (2) `round_outcomes.json`/`round_recoveries.json` are hashed as freeze keys, not as `TOOLING_FILES`; (3) the existing `run_pipeline` is kept and wrapped by `run_pipeline_result` so the Round 3 `run_pipeline` tests stay byte-invariant.
