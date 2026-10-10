# Search Quality Round 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the lexicon union's first-wins defect with a seed-free source-precedence resolution, declare the three representation-limited seeds as a frozen known-unreachable (KU) registry that acceptance, proposer and selector all respect, guard every Round 5 vocabulary change with a non-target counterexample suite, and then repeat the sealed Discovery procedure once against a new hidden set.

**Architecture:** Scorer code and policy structure are untouched (spec §3, AC-R5-05). Two tooling commits extend `tests/` only: H16 (lexicon union + pair-level review reuse in `concept_lexicon_check.py`) and H17 (KU registry, acceptance/selector/proposer wiring in `tune_search_ranking.py`, new `tests/benchmarks/counterexample.py`, per-round T allowlist and Round 5 freeze keys in `evaluator.py`/`round_seal.py`, `round5_simulation.py`). The controller procedure is the Round 4 plan v7 procedure (Tasks 4–12) with the Round 5 deltas written out in Tasks 3–11 below; no lexicon generation and no corpus acquisition happen in Round 5.

**Tech Stack:** Python 3.11 stdlib; `unittest`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-09-search-quality-round5-design.md` **v1.10** (v1.7 passed review 8 with P0 0 / P1 3 "구현 계획으로 진행 가능"; v1.8 applied those P1s; v1.9 and v1.10 are planning-time deltas ruled on review thread 2: counterexample reference file at T, per-round T allowlist, and removal of §6.2 doc-relation extraction). The spec inherits Round 4 v1.13 (`docs/superpowers/specs/2026-10-09-search-quality-round4-design.md`) and, through it, Round 3 v1.25.1. "As Round 4 plan v7 Task N Step M" means `docs/superpowers/plans/2026-10-09-search-quality-round4-implementation.md` with the substitution table below applied verbatim.

**Plan version:** v4 (2026-10-10; v4 = plan review 3 (P0 1/P1 3): pre-T blockers read the selected-constants counterexample and the dry-run `tuning_accept` (not only the lexicon-only check), exact reference input-key set checked against `$W` files, registry schema checks round/id types/uniqueness, reference-checker tests; v3 = plan review 2 (P0 2/P1 4): KU registry schema validator used by the H test and pre-T, ruling records carry date/summary; `selected` kept as the resolution provenance ledger through the concept cap; `prov` computed before use; single authority for validation blockers; blocker-kind list aligned; counterexample-reference self-check; v2 = plan review 1 (P0 3/P1 3): fresh Round 5 verdicts replace only pending pairs (`resolve_verdicts`), tuning round identity pinned by tests (dynamic `current_round`, KU via pending round before T), counterexample result carries scope/policy shas/selected constants and the final call gets titles+provenance with strict provenance validation, richer reference-file provenance, normalized path tokens, split blocker kinds).

## Global Constraints

- Canonical test command: `python -m unittest discover -s tests -t .` (**616 OK, 1 skipped** at `b8f4e78`, Python 3.11.15). `canonical_full_suite_pass := exit code 0 of exactly this command`. Simulation always runs as `python -m tests.benchmarks.round5_simulation …`.
- `round5_start_commit := 56b4b0e` (spec §9). Spec/plan commits after it touch only `docs/`. Ancestry: `56b4b0e < initial_housekeeping_commit ≤ housekeeping_commit < T < B < terminal` (or `T < X_preB`, B absent).
- **Scorer invariance (spec §3, AC-R5-05):** at every H/H′: `git diff --stat 56b4b0e..HEAD -- tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py` is empty; `search_ranking.json` keys `version`, `path_noise`, `product_hints`, `tuning_grid`, `baseline`, `ordering_rules` and the constant key set equal `56b4b0e`; `constants` values change only in the B..C adoption commit; `verb_methods` only by inherited sorted suffixes at T.
- **Inputs reused, never regenerated (spec §5):** the full SHA-256 table of spec §5 (Round 2 archive raw/review/review input/generation input, Round 4 generation raw/review/review input/generation input) and the Round 4 doc-title bundle `44f3378684201473d6267dd6f0296bb8babf904dc120320d594ed569d9de14fe` / snapshot `2d3caa6e02e0a67c523940add30e083cac415564302deb7e51a832ead50e6453` are checked before use; any mismatch → STOP. Archive paths are read-only (`~/.atlassian_api_updater/archive/round{2,4}/…`); the controller copies what it needs into `$W` and verifies the copy's sha.
- **KU registry (spec §4.1):** exactly `KNOWN_UNREACHABLE[5] == ("s-004", "s-027", "s-039")`, mirrored in `tests/benchmarks/round5-known-unreachable.json` (H artifact, never changed at T). A failing seed outside the registry is a `unreachable_seed` blocker → `STOP_FOR_AMENDMENT`; adding a seed to the registry requires a spec amendment ruled on the review thread.
- **T commit allowlist (spec §9, exact):** `tools/atlassian_docs/intelligence/data/{search_ranking.json (verb_methods suffix only), search_aliases.json (lexicon-r5 merge only), concept_lexicon.json, alias_candidates.json}`, `tests/benchmarks/round_freeze.json` (round 5 entry appended), `tests/benchmarks/search_queries.json` (seed `failure_classes`; hidden sections `[]`), `tests/benchmarks/round5-worker-brief.md`, `round5-hidden-generation-prompt.md`, `round5-hidden-reviewer-prompt.md`, `round5-method-safety.json`, `round5-counterexample-reference.json`. Nothing else; `evaluator.t_allowlist(5)` is this set.
- `TOOLING_FILES` gains `tests/benchmarks/counterexample.py`, `tests/benchmarks/test_counterexample.py`, `tests/benchmarks/round5_simulation.py`, `tests/benchmarks/test_round5_simulation.py` in the commit that creates them (Task 2, H17); immutable from `housekeeping_commit` to the terminal commit.
- Round state: freeze `[1, 2]`, outcomes rounds 3 and 4 `pre-T not reached`, `pending_round() == 5` (already true at `f745f80`). `freeze --round 5` needs `N == pending_round` and complete lower rounds (inherited guard).
- Pre-T gate (spec §4.2, §8, AC-R5-09): T only if AC-R3-01 (`failed ⊆ registry`, regression raw ≥ 10, effective 14, fixture 0) ∧ `pre_t_blockers == []` from the write-free production dry-run (kinds: `unreachable_seed` (non-KU only), `tuning_accept_false`, `alias_validation_error`, `inherited_ac_r3_01_failure`, `counterexample_loss`, `counterexample_uncovered_proposer`, `ku_record_mismatch`, `ku_approval_mismatch`, `input_sha_mismatch`, `counterexample_reference_mismatch`). Any blocker → `STOP_FOR_AMENDMENT` (non-terminal) → review thread. `TERMINAL_PRE_T_NOT_REACHED` is a user decision only.
- Session separation: this session (`42e25099…`) never saw hidden plaintext; lexicon reviewer and hidden generator/reviewer are stateless ChatGPT Temporary chats (personalization off) with actor ids distinct from every earlier generator/reviewer; the tuning worker is a fresh subagent; the D controller is a fresh actor. Hidden plaintext `~/.atlassian_api_updater/sealed/round5-sealed.json` is never given to subagents.
- Decision protocol: every judgement call goes to review thread 2 (`https://chatgpt.com/c/6ac7eb56-eed8-83e8-a55e-a4b67e3088de`), opened in its own browser tab (never the user's other ChatGPT tabs); the ruling text is saved byte-exact to `$W/rulings/<date>-<n>.md` and ledgered with its sha. The user is interrupted only by the four hard stops and the completion report; this run is authorized to push/PR/merge at completion only if the user says so again.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never call real Jira/Confluence APIs; the only network step is `python -m tools.atlassian_docs` (catalog refresh for the S comparison).

## Name substitutions (applied to every Round 4 plan v7 step this plan imports)

| Round 4 token | Round 5 token |
|---|---|
| `round4` / `Round 4` / `ROUND = 4` / `--round 4` | `round5` / `Round 5` / `ROUND = 5` / `--round 5` |
| `~/.atlassian_api_updater/round4-cache` (`$S`), `round4-work` (`$W`) | `round5-cache`, `round5-work` |
| `ATLASSIAN_DOCS_ROUND4_CACHE` | `ATLASSIAN_DOCS_ROUND5_CACHE` |
| `lexicon-r4`, `held_out-r4`/`negative-r4` | `lexicon-r5`, `held_out-r5`/`negative-r5` |
| `round4_seal`, `round4-sealed.json(.enc)`, `round4-final.json`, `search-tuning-round4.jsonl` | `round5_seal`, `round5-sealed.json(.enc)`, `round5-final.json`, `search-tuning-round5.jsonl` |
| `round4-*.md` frozen texts, `round4-method-safety.json` | `round5-*.md` (worker brief, two hidden prompts only), `round5-method-safety.json` |
| `HIDDEN_RULES_R4` | `HIDDEN_RULES_R5` (same ids, same order) |
| `ROUND4-WORKER-HANDSHAKE`, `round4_gate_checkpoint` | `ROUND5-WORKER-HANDSHAKE`, `round5_gate_checkpoint` |
| `python -m tests.benchmarks.round4_simulation` | `python -m tests.benchmarks.round5_simulation` |
| `round4_start_commit 237d2c9` | `round5_start_commit 56b4b0e` |
| doc-title acquisition (Round 4 Task 4 Step 2) | **none** — the Round 4 epoch-1 bundle is reused read-only (Task 3 Step 2) |
| lexicon generation (Round 4 Task 5 Step 2) | **none** — one stateless review of unreviewed pairs only (Task 4) |

## Review Focus

1. A key whose newest-precedence candidate is selected and then removed by the post-resolution seed gate must disappear from the Round 5 policy (no fallback to the older candidate) and must appear in the counterexample `changed_keys` as old→absent (Task 1 `test_gate_removal_never_falls_back`, Task 2 `test_old_to_absent_is_a_changed_key`).
2. A grid point whose only failures are KU seeds must enter the selector's acceptance pool, and two points that differ only in how many KU seeds pass must select identically (Task 2 `test_selector_ignores_ku_pass_counts`).
3. An alias the proposer adds for a word that no catalog summary contains must make `tuning_accept` false even when every other condition holds (Task 2 `test_uncovered_proposer_key_blocks_accept`).
4. A (key, targets) pair that two past reviews judged differently must be re-reviewed, never resolved by recency (Task 1 `test_conflicting_past_verdicts_are_pending`).
5. A KU id whose seed record changed (same id, different query) must stop the pre-T gate (Task 2 `test_ku_record_mismatch_is_a_blocker`).

---
### Task 1: Source-precedence lexicon union and pair-level review reuse (commit H16)

**Files:**
- Modify: `tests/benchmarks/concept_lexicon_check.py` (new `SOURCE_RANK`, `canonical_key`, `review_pairs`, `merge_verdicts`, `resolve_sources`, `render_pending_review`, CLI `resolve`, `round4-reference`; `union_docs`/`build` stay for the Round 4 replay)
- Test: `tests/benchmarks/test_concept_lexicon_check.py` (new class `TestRound5Union`)

**Interfaces:**
- Consumes: `normalize_raw`, `structural_check`, `cap_per_concept`, `build`, `union_docs`, `_context` (existing); `act.norm_tokens`.
- Produces: `SOURCE_RANK: dict[str, int]` (`{"round2_archive": 0, "round4_generation": 1}`); `canonical_key(syn: str) -> tuple`; `review_pairs(review_input_text: str, review: dict) -> dict[tuple, bool]` keyed by `(canonical_key, tuple(sorted(targets)))`; `merge_verdicts(pair_maps: list) -> (dict, list)` = (agreed historical verdicts, conflicting pairs); `resolve_verdicts(historical_maps: list, fresh_maps: list) -> (dict, list)` = (effective verdicts, conflicts left without a fresh verdict) — a fresh verdict replaces a pair only if that pair has no agreed historical verdict; `resolve_sources(sources: list[dict], ctx: tuple, verdicts: dict) -> dict` with keys `lexicon`, `rejected`, `selected`, `pending` (each `sources` item is `{"id": <source id>, "raw": <dict>}`; `ctx` is the 7-tuple `_context` returns); `render_pending_review(template: str, pending: list) -> list[str]` (one review-input text per batch of unique display keys). Task 2 consumes `canonical_key`; Task 5 consumes the CLI.

- [ ] **Step 1: Write the failing tests**

Append to `tests/benchmarks/test_concept_lexicon_check.py`:

```python
CTX5 = (CONCEPTS | {"build", "favourite", "filter"}, CATALOG | {"build"}, VERBS, HINTS, ALIAS_KEYS, frozenset(), None)


class TestRound5Union(unittest.TestCase):
    """Round 5 spec §6.1/§6.3: source precedence, seed-free eligibility, no fallback, pair-level review reuse."""
    def _src(self, r2=None, r4=None):
        return [{"id": "round2_archive", "raw": r2 or {}}, {"id": "round4_generation", "raw": r4 or {}}]

    def test_lower_rank_ineligible_higher_rank_eligible(self):                       # (a)
        v = {(("release",), ("version",)): True, (("release",), ("build",)): False}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertEqual(out["lexicon"], {"release": ["version"]}); self.assertEqual(out["selected"]["release"]["source"], "round4_generation")

    def test_both_eligible_highest_rank_wins(self):                                   # (b)
        v = {(("release",), ("version",)): True, (("release",), ("build",)): True}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertEqual(out["lexicon"]["release"], ["version"]); self.assertEqual(out["selected"]["release"]["provenance_rank"], 1)

    def test_higher_rank_rejected_lower_rank_used(self):                              # (c)
        v = {(("release",), ("version",)): False, (("release",), ("build",)): True}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertEqual(out["lexicon"]["release"], ["build"])

    def test_all_ineligible_records_every_candidate(self):                             # (d)
        v = {(("release",), ("version",)): False, (("release",), ("build",)): False}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertNotIn("release", out["lexicon"])
        self.assertEqual([c["source"] for c in out["rejected"]["release"]["candidates"]], ["round2_archive", "round4_generation"])

    def test_input_order_does_not_matter(self):                                        # (e)
        v = {(("release",), ("version",)): True, (("release",), ("build",)): True}
        a = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        b = clc.resolve_sources(list(reversed(self._src({"release": ["build"]}, {"release": ["version"]}))), CTX5, v)
        self.assertEqual(a, b)

    def test_resolution_reads_no_benchmark(self):                                       # (f) seed-independence
        src = self._src({"release": ["build"]}, {"release": ["version"]}); v = {(("release",), ("version",)): True}
        with mock.patch("builtins.open", side_effect=AssertionError("resolution must not read files")), \
             mock.patch("pathlib.Path.read_text", side_effect=AssertionError("resolution must not read files")):
            out = clc.resolve_sources(src, CTX5, v)
        self.assertEqual(out["lexicon"], {"release": ["version"]})

    def test_gate_removal_never_falls_back(self):                                       # (g)
        from tests.benchmarks import alias_candidates_tool as act
        v = {(("release",), ("version",)): True, (("release",), ("build",)): True}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        doc = {"lexicon": dict(out["lexicon"]), "rejected": dict(out["rejected"])}
        bench = {"seed": [{"id": "s-1", "query": "publish a release", "expected_top1_any": ["p:POST:/build"]}]}
        by_key = {"p:POST:/build": {"key": "p:POST:/build", "operation_id": "build", "summary": "build", "tags": []}}
        ranking = {"verb_methods": {"publish": ["POST"]}, "path_noise": [], "product_hints": {}}
        doc, rejected = act.lexicon_gate(doc, bench, by_key, ranking)
        self.assertEqual(rejected, ["release"]); self.assertNotIn("release", doc["lexicon"])      # removed, not replaced by release→build

    def test_review_pairs_and_conflicts(self):
        text = 'header\nENTRIES:\n{\n "access combination": ["combination"],\n "release": ["build"]\n}\n'
        pairs = clc.review_pairs(text, {"access combination": False, "release": True})
        self.assertEqual(pairs, {(("access", "combination"), ("combination",)): False, (("release",), ("build",)): True})
        agreed, conflicts = clc.merge_verdicts([pairs, {(("release",), ("build",)): False}])
        self.assertEqual(conflicts, [(("release",), ("build",))]); self.assertNotIn((("release",), ("build",)), agreed)

    def test_conflicting_past_verdicts_are_pending(self):
        agreed, conflicts = clc.merge_verdicts([{(("release",), ("version",)): True}, {(("release",), ("version",)): False}])
        out = clc.resolve_sources(self._src(None, {"release": ["version"]}), CTX5, agreed)
        self.assertEqual(out["pending"], [(("release",), ("version",), "release")]); self.assertNotIn("release", out["lexicon"])

    def test_cap_removed_entry_keeps_provenance(self):
        raw4 = {w: ["issue"] for w in ("aaa", "bbb", "ccc", "ddd", "eee", "fff")}           # 6 words on one concept → cap keeps 5
        v = {((w,), ("issue",)): True for w in raw4}
        out = clc.resolve_sources(self._src(None, raw4), (CONCEPTS, CATALOG, VERBS, HINTS, set(), frozenset(), None), v)
        self.assertEqual(out["rejected"]["fff"]["reason"], "concept-cap"); self.assertEqual(out["selected"]["fff"]["source"], "round4_generation")
        self.assertNotIn("fff", out["lexicon"])

    def test_fresh_verdict_resolves_conflict(self):
        past = [{(("release",), ("version",)): True}, {(("release",), ("version",)): False}]
        for fresh_v in (True, False):
            eff, left = clc.resolve_verdicts(past, [{(("release",), ("version",)): fresh_v}])
            self.assertEqual(eff[(("release",), ("version",))], fresh_v); self.assertEqual(left, [])
        eff, left = clc.resolve_verdicts(past, [])
        self.assertNotIn((("release",), ("version",)), eff); self.assertEqual(left, [(("release",), ("version",))])
        eff, _ = clc.resolve_verdicts([{(("ticket",), ("issue",)): True}], [{(("ticket",), ("issue",)): False}])
        self.assertTrue(eff[(("ticket",), ("issue",))])                                   # fresh never overrides an agreed past verdict

    def test_render_pending_review_batches_unique_keys(self):
        tpl = 'Reply ONLY with JSON.\n\nENTRIES:\n<the "lexicon" object of lexicon_structural.json>\n'
        texts = clc.render_pending_review(tpl, [(("release",), ("version",), "release"), (("release",), ("build",), "release")])
        self.assertEqual(len(texts), 2)
        self.assertEqual([json.loads(t.split("ENTRIES:\n", 1)[1]) for t in texts], [{"release": ["build"]}, {"release": ["version"]}])
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python -m unittest tests.benchmarks.test_concept_lexicon_check.TestRound5Union -v`
Expected: every test ERRORs with `AttributeError: module 'tests.benchmarks.concept_lexicon_check' has no attribute 'resolve_sources'` (or `review_pairs` / `merge_verdicts` / `render_pending_review`).

- [ ] **Step 3: Implement the resolution helpers**

Insert after `union_docs` in `tests/benchmarks/concept_lexicon_check.py`:

```python
SOURCE_RANK = {"round2_archive": 0, "round4_generation": 1}        # Round 5 spec §6.1: source identity, never CLI order


def canonical_key(syn: str) -> tuple:
    """A word -> (word,); a phrase -> its sorted token tuple (phrases with the same token set are one key)."""
    toks = tuple(syn.split(" "))
    return tuple(sorted(toks)) if len(toks) > 1 else toks


def review_pairs(review_input_text: str, review: dict) -> dict:
    """Round 5 spec §6.3: the verdict of every (key, targets) pair the reviewer actually saw (the ENTRIES object of its input)."""
    body = review_input_text.split("ENTRIES:", 1)[1].lstrip()
    entries, _ = json.JSONDecoder().raw_decode(body)
    out = {}
    for syn, targets in entries.items():
        if isinstance(review.get(syn), bool):
            out[(canonical_key(" ".join(act.norm_tokens(syn)) or syn), tuple(sorted(targets)))] = review[syn]
    return out


def merge_verdicts(pair_maps) -> tuple:
    """Agreeing past verdicts are reused; a pair judged both ways is a conflict (re-reviewed, never resolved by recency)."""
    seen = {}
    for m in pair_maps:
        for pair, v in m.items():
            seen.setdefault(pair, set()).add(v)
    return {p: next(iter(v)) for p, v in seen.items() if len(v) == 1}, sorted(p for p, v in seen.items() if len(v) > 1)


def resolve_verdicts(historical_maps, fresh_maps) -> tuple:
    """Round 5 spec §6.3: agreed historical verdicts are reused; a fresh (Round 5) verdict is authoritative only for pairs without an
    agreed historical verdict (unreviewed or conflicting) and is never merged into the conflicting set."""
    agreed, conflicts = merge_verdicts(historical_maps)
    fresh = {}
    for m in fresh_maps:
        for pair, v in m.items():
            if pair in agreed:
                continue                                            # fresh verdicts never override an agreed historical verdict
            if fresh.get(pair, v) != v:
                raise ValueError(f"two fresh reviews disagree on {pair}")
            fresh[pair] = v
    return {**agreed, **fresh}, [c for c in conflicts if c not in fresh]


def resolve_sources(sources, ctx, verdicts) -> dict:
    """Round 5 spec §6.1: keep every candidate, eligible = structural ∧ review (no benchmark input), highest source rank wins,
    then the inherited per-concept cap. `pending` lists (canonical key, targets, display key) with no agreed verdict."""
    concept_set, catalog_set, verbs, hints, alias_keys, rule_sets, token_sources = ctx
    cands = {}
    for src in sorted(sources, key=lambda s: SOURCE_RANK[s["id"]]):
        lex = normalize_raw(src["raw"])
        kept, rej = structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets, token_sources)
        for syn, targets in lex.items():
            cands.setdefault(canonical_key(syn), []).append({"source": src["id"], "rank": SOURCE_RANK[src["id"]], "key": syn,
                                                             "targets": list(targets), "reasons": [] if syn in kept else [rej[syn]["reason"]]})
    lexicon, rejected, selected, pending = {}, {}, {}, set()
    for ck, cs in sorted(cands.items()):
        eligible = []
        for c in cs:
            if c["reasons"]:
                continue
            v = verdicts.get((ck, tuple(sorted(c["targets"]))))
            if v is None:
                pending.add((ck, tuple(sorted(c["targets"])), c["key"])); c["reasons"] = ["unreviewed"]
            elif v:
                eligible.append(c)
            else:
                c["reasons"] = ["semantic-reject"]
        if eligible:
            best = max(eligible, key=lambda c: c["rank"])
            lexicon[best["key"]] = best["targets"]; selected[best["key"]] = {"source": best["source"], "provenance_rank": best["rank"]}
        else:
            last = cs[-1]
            rejected[last["key"]] = {**_rej("no-eligible-candidate", last["targets"]),
                                     "candidates": [{"source": c["source"], "provenance_rank": c["rank"], "targets": c["targets"], "reasons": c["reasons"]} for c in cs]}
    lexicon, capped = cap_per_concept(lexicon)
    rejected.update(capped)                                         # `selected` stays the resolution provenance ledger (cap → gate_reason "concept-cap")
    return {"lexicon": lexicon, "rejected": dict(sorted(rejected.items())), "selected": dict(sorted(selected.items())), "pending": sorted(pending)}


REVIEW_PLACEHOLDER = '<the "lexicon" object of lexicon_structural.json>'


def render_pending_review(template: str, pending) -> list:
    """Unreviewed pairs as review inputs (the committed Round 4 review template, byte-identical); pairs sharing a display key go
    to different batches so every ENTRIES object has unique keys."""
    batches = []
    for _ck, targets, key in sorted(pending, key=lambda p: (p[2], p[1])):
        for b in batches:
            if key not in b:
                b[key] = list(targets); break
        else:
            batches.append({key: list(targets)})
    if REVIEW_PLACEHOLDER not in template:
        raise ValueError("review template placeholder not found")
    return [template.replace(REVIEW_PLACEHOLDER, json.dumps(b, indent=1, ensure_ascii=False, sort_keys=True)) for b in batches]
```

- [ ] **Step 4: Run the tests**

Run: `python -m unittest tests.benchmarks.test_concept_lexicon_check.TestRound5Union -v`
Expected: 12 tests OK.

- [ ] **Step 5: CLI `resolve` and `round4-reference` (failing test first)**

Add to `TestRound5Union`:

```python
    def test_cli_resolve_writes_pending_then_lexicon(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td); tpl = d / "tpl.md"; tpl.write_text('ENTRIES:\n<the "lexicon" object of lexicon_structural.json>\n')
            (d / "r2.json").write_text(json.dumps({"release": ["build"]})); (d / "r4.json").write_text(json.dumps({"release": ["version"]}))
            (d / "rv2.json").write_text(json.dumps({"release": False})); (d / "ri2.txt").write_text('ENTRIES:\n{"release": ["build"]}\n')
            (d / "rv4.json").write_text(json.dumps({})); (d / "ri4.txt").write_text('ENTRIES:\n{}\n')
            args = ["resolve", "--cache-dir", "unused", "--round", "5", "--template", str(tpl),
                    "--source", "round2_archive", str(d / "r2.json"), str(d / "rv2.json"), str(d / "ri2.txt"),
                    "--source", "round4_generation", str(d / "r4.json"), str(d / "rv4.json"), str(d / "ri4.txt"),
                    "--pending-out", str(d / "pending"), "--out", str(d / "lex.json")]
            with mock.patch.object(clc, "_context", return_value=(None, "fp", {}, {"verb_methods": {}}, {}, CTX5)):
                self.assertEqual(clc.main(args), 3)                                    # release→version unreviewed
                (d / "rv5.json").write_text(json.dumps({"release": True}))
                self.assertEqual(clc.main(args + ["--review-r5", str(d / "rv5.json"), str(d / "pending" / "review-input-1.txt")]), 0)
            doc = json.loads((d / "lex.json").read_text())
            self.assertEqual(doc["lexicon"], {"release": ["version"]}); self.assertEqual(doc["components"]["union_resolution"], "source-precedence")
```

Run: `python -m unittest tests.benchmarks.test_concept_lexicon_check.TestRound5Union.test_cli_resolve_writes_pending_then_lexicon -v` → Expected: FAIL (`resolve` is not a valid choice).

Implement in `concept_lexicon_check.py` (before `main`):

```python
def cmd_resolve(args):
    internal, fp, shas, ranking, aliases, ctx = _context(args)
    sources, pair_maps, fresh_maps, comp = [], [], [], []
    for sid, raw_p, rev_p, rin_p in args.source:
        raw = _read(raw_p); sources.append({"id": sid, "raw": raw})
        pair_maps.append(review_pairs(pathlib.Path(rin_p).read_text(encoding="utf-8"), _read(rev_p)))
        comp.append({"id": sid, "rank": SOURCE_RANK[sid], "raw_sha256": _sha(raw_p), "review_sha256": _sha(rev_p), "review_input_sha256": _sha(rin_p)})
    for rev_p, rin_p in args.review_r5 or []:
        fresh_maps.append(review_pairs(pathlib.Path(rin_p).read_text(encoding="utf-8"), _read(rev_p)))
        comp.append({"id": "round5_review", "review_sha256": _sha(rev_p), "review_input_sha256": _sha(rin_p)})
    verdicts, conflicts = resolve_verdicts(pair_maps, fresh_maps)
    out = resolve_sources(sources, ctx, verdicts)
    if out["pending"]:
        d = pathlib.Path(args.pending_out); d.mkdir(parents=True, exist_ok=True)
        texts = render_pending_review(pathlib.Path(args.template).read_text(encoding="utf-8"), out["pending"])
        for i, t in enumerate(texts, 1):
            (d / f"review-input-{i}.txt").write_text(t, encoding="utf-8")
        print(json.dumps({"pending": len(out["pending"]), "conflicts": len(conflicts), "batches": len(texts)})); return 3
    doc = {"round": args.round, "components": {"union_resolution": "source-precedence", "sources": comp, "template_sha256": _sha(args.template),
                                               "review_conflicts": [list(map(list, c)) for c in conflicts]},
           "generated_from": act.provenance(fp, shas, {"verb_inventory": canonical_sha256(ranking["verb_methods"]), "aliases": canonical_sha256(aliases)}),
           "lexicon": out["lexicon"], "rejected": out["rejected"], "selected": out["selected"]}
    act._write(args.out, doc)
    print(f"lexicon: {len(out['lexicon'])} kept, {len(out['rejected'])} rejected"); return 0


def cmd_round4_reference(args):
    """Round 5 spec §8: the Round 4 first-wins resolution of the same inputs (archive first), for the counterexample baseline."""
    internal, fp, shas, ranking, aliases, ctx = _context(args)
    lexicon, rejected = build(union_docs([_read(p) for p in args.raw]), union_docs([_read(p) for p in args.review]), *ctx[:5],
                              rule_sets=ctx[5], token_sources=ctx[6])
    act._write(args.out, {"round": 4, "lexicon": lexicon, "rejected": rejected,
                          "components": {"union_resolution": "first-wins", "raw": [_sha(p) for p in args.raw], "review": [_sha(p) for p in args.review]}})
    print(f"round4 reference lexicon: {len(lexicon)} kept"); return 0
```

and in `main` add:

```python
    p = sub.add_parser("resolve"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=5)
    p.add_argument("--source", nargs=4, action="append", required=True, metavar=("ID", "RAW", "REVIEW", "REVIEW_INPUT"))
    p.add_argument("--review-r5", nargs=2, action="append", metavar=("REVIEW", "REVIEW_INPUT"))
    p.add_argument("--template", required=True); p.add_argument("--pending-out", required=True); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_resolve)
    p = sub.add_parser("round4-reference"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=5)
    p.add_argument("--raw", nargs="+", required=True); p.add_argument("--review", nargs="+", required=True); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_round4_reference)
```

Run: `python -m unittest tests.benchmarks.test_concept_lexicon_check -v` → Expected: all OK.

- [ ] **Step 6: Suite, AC-R5-05, commit H16**

```bash
python -m unittest discover -s tests -t . 2>&1 | tail -3           # Expected: OK (627 tests or more), 1 skipped
git diff --stat 56b4b0e..HEAD -- tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py   # Expected: empty
git add tests/benchmarks/concept_lexicon_check.py tests/benchmarks/test_concept_lexicon_check.py
git commit -m "H16: source-precedence lexicon union (seed-free eligibility, no fallback) and pair-level review reuse; CLI resolve/round4-reference

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: KU registry, KU-aware acceptance/selector/proposer, counterexample suite, Round 5 freeze keys, `round5_simulation` (commit H17 = `housekeeping_commit`)

**Files:**
- Create: `tests/benchmarks/counterexample.py`, `tests/benchmarks/test_counterexample.py`, `tests/benchmarks/round5-known-unreachable.json`, `tests/benchmarks/round5_simulation.py`, `tests/benchmarks/test_round5_simulation.py`
- Modify: `tests/benchmarks/evaluator.py` (`KNOWN_UNREACHABLE`, `known_unreachable`, `t_allowlist`, `T_ALLOWLIST = t_allowlist(4)`, `ROUND5_EXTRA_KEYS`, `freeze_key_set`, `ku_record_problems`, `TOOLING_FILES`), `tests/benchmarks/round_seal.py` (`HIDDEN_RULES_R5`, `freeze_entry` uses `ev.t_allowlist(round)` and adds the round ≥ 5 keys), `tests/tune_search_ranking.py` (`KU`, `run_pipeline`, `tuning_accept`, `PipelineResult.counterexample_result`, `run_pipeline_result(counterexample_fn=None)`, `main`/`_finish`)
- Test: `tests/benchmarks/test_evaluator.py`, `tests/benchmarks/test_round_seal.py`, `tests/test_tune_search_ranking.py`

**Interfaces:**
- Consumes: Task 1 `canonical_key`; existing `select_candidate`, `propose_aliases`, `validate_alias_change`, `evaluate_point`, `ranking_with`, `_alias_policy`.
- Produces: `ev.KNOWN_UNREACHABLE: dict[int, tuple]`, `ev.known_unreachable(round) -> frozenset`, `ev.t_allowlist(round) -> tuple`, `ev.ku_record_problems(round, bench, base_bench, registry_doc) -> list[str]`; `counterexample.canonical_policy_map(raw) -> dict`, `counterexample.diff(a, b) -> list`, `counterexample.counterexample_tokens(ckey) -> tuple`, `counterexample.suite(index, top1, pre_raw, static_raw, post_raw, titles=()) -> dict`, `counterexample.catalog_index(state) -> list`, `counterexample.production_top1(state, rp, point) -> callable`; `tune.tuning_accept(seed_res, reg_res, fixture_final, ku=frozenset(), cx=None) -> bool`; `PipelineResult.counterexample_result: dict | None`; `round5_simulation.pre_t_blockers(result, event, diagnostics=None, ku=…, cx=None, extra=())`.

- [ ] **Step 1: KU registry, per-round allowlist, Round 5 freeze keys — failing tests**

Append to `tests/benchmarks/test_evaluator.py`:

```python
class TestRound5Registry(unittest.TestCase):
    """Round 5 spec §4.1/§9: exact KU set mirrored from the spec, record machine-check, per-round T allowlist, freeze keys."""
    SPEC = pathlib.Path(__file__).resolve().parents[2] / "docs/superpowers/specs/2026-10-09-search-quality-round5-design.md"

    def test_registry_equals_spec_set(self):
        import re
        m = re.search(r"`KNOWN_UNREACHABLE = \{5: \(([^)]*)\)\}`", self.SPEC.read_text(encoding="utf-8"))
        self.assertEqual(ev.KNOWN_UNREACHABLE[5], tuple(re.findall(r'"(s-\d+)"', m.group(1))))
        self.assertEqual(ev.known_unreachable(5), frozenset({"s-004", "s-027", "s-039"})); self.assertEqual(ev.known_unreachable(4), frozenset())

    def test_t_allowlist_round4_unchanged_round5_exact(self):
        self.assertEqual(ev.T_ALLOWLIST, ev.t_allowlist(4))
        self.assertIn("tests/benchmarks/round5-counterexample-reference.json", ev.t_allowlist(5))
        self.assertFalse(any("lexicon-generation-prompt" in p or "lexicon-review-prompt" in p for p in ev.t_allowlist(5)))
        self.assertNotIn("tests/benchmarks/round5-known-unreachable.json", ev.t_allowlist(5))

    def test_round5_freeze_keys(self):
        self.assertEqual(ev.freeze_key_set(5) - ev.freeze_key_set(4),
                         {"known_unreachable_seeds", "known_unreachable_registry_sha256", "lexicon_union_resolution", "counterexample_reference_sha256"})

    def test_ku_record_check(self):
        rec = {"id": "s-004", "query": "transition issue status", "expected_top1_any": ["k"], "forbidden_top1": [], "failure_classes": []}
        bench = {"seed": [rec]}; doc = {"seeds": [{"id": "s-004", "query_sha256": ev.sha256_text(rec["query"]), "record_sha256": ev.canonical_sha256(rec)}]}
        self.assertEqual(ev.ku_record_problems(5, bench, bench, doc, ids=("s-004",)), [])
        changed = {"seed": [{**rec, "query": "transition an issue"}]}
        self.assertTrue(ev.ku_record_problems(5, changed, bench, doc, ids=("s-004",)))       # same id, different query → problem

    def test_committed_registry_file_matches_bench(self):
        doc = json.loads((pathlib.Path(__file__).resolve().parent / "round5-known-unreachable.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(s["id"] for s in doc["seeds"]), sorted(ev.KNOWN_UNREACHABLE[5]))
        bench = json.loads(BENCH.read_text(encoding="utf-8"))
        self.assertEqual(ev.ku_record_problems(5, bench, bench, doc), []); self.assertEqual(ev.ku_registry_schema_problems(5, doc), [])

    def test_registry_schema_validator(self):
        good = {"round": 5, "approval": {"rulings": [{**{f: "x" for f in ev.KU_RULING_FIELDS}, "file": f"r{i}.md"} for i in range(5)], "user_decision": {"date": "d", "words": "w", "event_sha256": "e"}},
                "seeds": [{f: (sid if f == "id" else "x") for f in ev.KU_SEED_FIELDS} for sid in ev.KNOWN_UNREACHABLE[5]]}
        self.assertEqual(ev.ku_registry_schema_problems(5, good), [])
        bad = json.loads(json.dumps(good)); del bad["approval"]["rulings"][0]["summary"]; bad["seeds"] = bad["seeds"][:2]
        self.assertEqual(len(ev.ku_registry_schema_problems(5, bad)), 2)
        self.assertTrue(ev.ku_registry_schema_problems(5, {**good, "round": 4}))
        self.assertTrue(ev.ku_registry_schema_problems(5, {**good, "seeds": good["seeds"] + [{"cause": "no id"}]}))   # reported, no exception
```

Run: `python -m unittest tests.benchmarks.test_evaluator.TestRound5Registry -v` → Expected: ERROR `AttributeError: … 'KNOWN_UNREACHABLE'`.

- [ ] **Step 1b: Save the approval evidence (controller, before the registry file exists)**

`W=~/.atlassian_api_updater/round5-work; mkdir -p $W/rulings`. Open review thread 2 in its own tab and save, byte-exact (the answer's `innerText` after the `ChatGPT 답변:` marker up to the `ChatGPT는 실수할 수 있습니다` footer, no header, one trailing newline), each Round 5 ruling as `$W/rulings/2026-10-09-<n>.md`: (1) approach ruling (A/B/C), (2) S2 re-ruling after the counterexample measurement, (3) zero-slice re-ruling, (4) verb-conflict ruling (b), (5) spec review 8 verdict. Append the user decision event: `{"event": "user_decision_round5", "role": "user", "timestamp": "2026-10-09", "exact_text": "좋아 Round 5 진행해보자"}` to `$W/controller-events.jsonl`. Ledger the five file shas.

- [ ] **Step 2: Implement the registry pieces**

In `tests/benchmarks/evaluator.py` (after `T_ALLOWLIST`'s old definition, which this replaces):

```python
def t_allowlist(round: int) -> tuple:
    """Round 4 spec §9.6 / Round 5 spec §9 (exact, per round)."""
    common = T_DATA_FILES + ("tests/benchmarks/round_freeze.json", "tests/benchmarks/search_queries.json",
                             f"tests/benchmarks/round{round}-worker-brief.md", f"tests/benchmarks/round{round}-hidden-generation-prompt.md",
                             f"tests/benchmarks/round{round}-hidden-reviewer-prompt.md", f"tests/benchmarks/round{round}-method-safety.json")
    if round == 4:
        return common[:-1] + ("tests/benchmarks/round4-lexicon-generation-prompt.md", "tests/benchmarks/round4-lexicon-review-prompt.md",
                              "tests/benchmarks/round4-method-safety.json")
    return common + ((f"tests/benchmarks/round{round}-counterexample-reference.json",) if round >= 5 else ())


T_ALLOWLIST = t_allowlist(4)                                       # byte-identical to the Round 4 tuple (order included)
KNOWN_UNREACHABLE = {5: ("s-004", "s-027", "s-039")}              # Round 5 spec §4.1 (exact, frozen)
ROUND5_EXTRA_KEYS = ("known_unreachable_seeds", "known_unreachable_registry_sha256", "lexicon_union_resolution", "counterexample_reference_sha256")


def known_unreachable(round: int) -> frozenset:
    return frozenset(KNOWN_UNREACHABLE.get(round, ()))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


KU_RULING_FIELDS = ("thread", "date", "summary", "file", "review_output_sha256")
KU_SEED_FIELDS = ("id", "query_sha256", "record_sha256", "cause", "mechanisms_tried", "official_source_check")


def ku_registry_schema_problems(round, registry_doc) -> list:
    """Round 5 spec §4.1 / AC-R5-03: required approval and seed fields, exactly the registry ids, five rulings."""
    out = []
    ap = registry_doc.get("approval") or {}
    rulings = ap.get("rulings") or []
    if len(rulings) != 5:
        out.append(f"approval.rulings: expected 5, got {len(rulings)}")
    out += [f"ruling {i}: missing {f}" for i, r in enumerate(rulings) for f in KU_RULING_FIELDS if not r.get(f)]
    ud = ap.get("user_decision") or {}
    out += [f"user_decision: missing {f}" for f in ("date", "words", "event_sha256") if not ud.get(f)]
    if registry_doc.get("round") != round:
        out.append(f"round: expected {round}, got {registry_doc.get('round')!r}")
    seeds = registry_doc.get("seeds") or []
    if not all(isinstance(s, dict) and isinstance(s.get("id"), str) and s.get("id") for s in seeds):
        return out + ["seeds: every entry must be an object with a non-empty string id"]
    ids = [s["id"] for s in seeds]
    if len(ids) != len(set(ids)) or sorted(ids) != sorted(KNOWN_UNREACHABLE.get(round, ())):
        out.append("seeds: ids differ from KNOWN_UNREACHABLE (exact, unique)")
    files = [r.get("file") for r in rulings]
    if len(files) != len(set(files)):
        out.append("approval.rulings: duplicate ruling files")
    out += [f"seed {s['id']}: missing {f}" for s in seeds for f in KU_SEED_FIELDS if not s.get(f)]
    return out


def ku_record_problems(round, bench, base_bench, registry_doc, ids=None) -> list:
    """Round 5 spec §4.1: every KU seed record equals the start-commit record and the registry's query/record hashes."""
    ids = tuple(ids) if ids is not None else KNOWN_UNREACHABLE.get(round, ())
    cur = {r["id"]: r for r in bench["seed"]}; base = {r["id"]: r for r in base_bench["seed"]}
    reg = {s["id"]: s for s in registry_doc.get("seeds", [])}
    out = []
    for sid in ids:
        r, b, g = cur.get(sid), base.get(sid), reg.get(sid)
        if r is None or b is None or g is None:
            out.append(f"{sid}: missing in bench/base/registry"); continue
        if canonical_sha256(r) != canonical_sha256(b):
            out.append(f"{sid}: seed record differs from the start commit")
        if g.get("query_sha256") != sha256_text(r["query"]) or g.get("record_sha256") != canonical_sha256(r):
            out.append(f"{sid}: registry query/record sha mismatch")
    return out
```

Change `freeze_key_set` to `… | (set(ROUND4_EXTRA_KEYS) if round >= 4 else set()) | (set(ROUND5_EXTRA_KEYS) if round >= 5 else set())`. Make sure `T_ALLOWLIST`'s old literal is removed (the new `t_allowlist(4)` reproduces it; `test_t_allowlist_round4_unchanged_round5_exact` plus the existing Round 4 tests guard it). Create `tests/benchmarks/round5-known-unreachable.json` by running this once (it reads the committed bench; the approval block is filled with the review-output shas the controller saved — at H the ruling files are `docs`-independent copies under `$W/rulings/`, so H17 records them; if a ruling file is missing, stop and save it first):

```bash
python - <<'EOF'
import json, pathlib, hashlib
from tests.benchmarks import evaluator as ev
W = pathlib.Path.home() / ".atlassian_api_updater/round5-work"
bench = json.loads(pathlib.Path("tests/benchmarks/search_queries.json").read_text(encoding="utf-8")); seeds = {r["id"]: r for r in bench["seed"]}
CAUSE = {"s-004": ("constants/ordering: POST /bulk/issues/transition summary contains every query word (46 vs 42)",
                   [{"mechanism": "bulk-variant tier v2", "counterexample": {"slice": "my+bulk summary-as-query (41 ops)", "hit_miss_before": [35, 6], "hit_miss_after": [33, 8],
                     "losses": ["Get issue panel pin status for projects", "Get available transitions (ambiguous)"]}}]),
         "s-027": ("needs search→filter (verb-inventory key, same-product token) and 'my' literal-terminal handling",
                   [{"mechanism": "query 'my' neutralization", "counterexample": {"slice": "my+bulk summary-as-query (41 ops)", "hit_miss_before": [35, 6], "hit_miss_after": [13, 28],
                     "losses": ["Get my filters"]}}]),
         "s-039": ("workspace→space has no official-source support (0 doc titles; Confluence API 'workspace' = site)",
                   [{"mechanism": "compound-suffix split", "counterexample": {"slice": "seed+regression queries", "hit_miss_before": None, "hit_miss_after": None,
                     "losses": [], "note": "workspace is itself a catalog token; rule never applies"}}])}
rulings = sorted((W / "rulings").glob("*.md"))
assert rulings, "save the review-thread rulings first (Step 1b)"
ud = [json.loads(l) for l in (W / "controller-events.jsonl").read_text(encoding="utf-8").splitlines() if '"user_decision_round5"' in l][-1]
UD_SHA = ev.canonical_sha256({k: ud[k] for k in ("role", "timestamp", "exact_text")})
SUMMARIES = ["approach: A modified / B narrow / C rejected", "S2 after counterexample measurement; KU {s-004, s-027, s-039}",
             "zero-slice re-ruling: uncovered static non-blocking, uncovered proposer blocks", "verb conflict (b): doc_relation removed",
             "spec review 8: P0 0 / P1 3, ready for the implementation plan"]
assert len(rulings) == len(SUMMARIES), "exactly the five Round 5 rulings, in Step 1b order"
doc = {"round": 5, "approval": {"rulings": [{"thread": "review thread 2", "date": p.name[:10], "summary": SUMMARIES[i], "file": p.name,
                                             "review_output_sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for i, p in enumerate(rulings)],
                                "user_decision": {"date": "2026-10-09", "words": "좋아 Round 5 진행해보자", "event_sha256": UD_SHA}},
       "seeds": [{"id": sid, "query_sha256": ev.sha256_text(seeds[sid]["query"]), "record_sha256": ev.canonical_sha256(seeds[sid]),
                  "cause": CAUSE[sid][0], "mechanisms_tried": CAUSE[sid][1], "official_source_check": "Round 4 doc-title snapshot 2d3caa6e…"}
                 for sid in ev.KNOWN_UNREACHABLE[5]]}
pathlib.Path("tests/benchmarks/round5-known-unreachable.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
print(len(doc["approval"]["rulings"]), "rulings recorded")
EOF
```


Run: `python -m unittest tests.benchmarks.test_evaluator.TestRound5Registry -v` → Expected: 6 OK. Run the whole `tests.benchmarks.test_evaluator` and `tests.benchmarks.test_round_seal` → Expected: OK (the Round 4 allowlist tests still pass because `T_ALLOWLIST` is unchanged).

- [ ] **Step 3: `round_seal` Round 5 freeze entry — failing test, then implementation**

Append to `tests/benchmarks/test_round_seal.py`:

```python
class TestRound5FreezeEntry(TestRound4FreezeEntry):
    """Round 5 spec §4.1/§9: KU, registry, union-resolution and counterexample-reference keys; per-round allowlist."""
    def _entry5(self, td, changed, union="source-precedence"):
        out, snap = self._bundle(td)
        hashes = {k: "0" * 64 for k in ev.freeze_key_set(4) - {"round", "structure_sha256", "verb_inventory_sha256", "source_registry_fingerprint", "source_spec_sha256",
                                                                "reference_set", "hidden_generation_rules", "hidden_set_origin", "doc_titles_source_bundle_sha256", "doc_titles_snapshot_sha256", "t_policy_files"}}
        ranking = {"verb_methods": {"get": ["GET"]}, "path_noise": [], "product_hints": [], "tuning_grid": {}, "baseline": {}, "ordering_rules": {},
                   "round2_seal": {"held_out_sha256": "1" * 64, "negative_sha256": "2" * 64}}
        real_sha = ev.file_sha256
        with mock.patch.object(rs, "load_catalogs_from_cache", return_value=([], [], "f" * 64, {"jira-platform": "a" * 64})), \
             mock.patch.object(ev, "round_freeze_hashes", return_value=hashes), mock.patch.object(ev, "changed_files_since", return_value=changed), \
             mock.patch.object(ev, "file_sha256", side_effect=lambda p: real_sha(p) if pathlib.Path(p).exists() else "e" * 64), \
             mock.patch.object(rs, "_read_json", side_effect=lambda p: {"components": {"union_resolution": union}} if str(p).endswith("concept_lexicon.json") else ranking):
            enc = pathlib.Path(td, "r2.enc"); enc.write_bytes(b"x")
            return rs.freeze_entry(5, pathlib.Path(td), reference_enc=enc, doc_sources=out, doc_titles_path=snap, base_commit="HEAD")

    def test_round5_keys(self):
        with tempfile.TemporaryDirectory() as td:
            e = self._entry5(td, [ev.T_DATA_FILES[2], "tests/benchmarks/round5-counterexample-reference.json"])
            self.assertEqual(set(e), ev.freeze_key_set(5)); self.assertEqual(e["known_unreachable_seeds"], ["s-004", "s-027", "s-039"])
            self.assertEqual(e["lexicon_union_resolution"], "source-precedence"); self.assertEqual(e["hidden_generation_rules"], list(rs.HIDDEN_RULES_R5))

    def test_registry_change_at_T_refused(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaises(SystemExit):
            self._entry5(td, ["tests/benchmarks/round5-known-unreachable.json"])

    def test_non_round5_lexicon_refused(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaises(SystemExit):
            self._entry5(td, [], union="first-wins")
```

Run: `python -m unittest tests.benchmarks.test_round_seal.TestRound5FreezeEntry -v` → Expected: FAIL/ERROR (`HIDDEN_RULES_R5` missing, keys missing).

Implement in `freeze_entry` (inside `if round >= 4:` replace `ev.T_ALLOWLIST` with `ev.t_allowlist(round)`), then add:

```python
    if round >= 5:                                                     # Round 5 spec §4.1, §6.1, §9
        lex = _read_json(RANKING_PATH.parent / "concept_lexicon.json")
        entry["known_unreachable_seeds"] = sorted(ev.KNOWN_UNREACHABLE[round])
        entry["known_unreachable_registry_sha256"] = ev.file_sha256(ROOT / f"tests/benchmarks/round{round}-known-unreachable.json")
        entry["lexicon_union_resolution"] = (lex.get("components") or {}).get("union_resolution")
        entry["counterexample_reference_sha256"] = ev.file_sha256(ROOT / f"tests/benchmarks/round{round}-counterexample-reference.json")
        if entry["lexicon_union_resolution"] != "source-precedence":
            raise SystemExit("REFUSED: concept_lexicon.json was not built by the Round 5 source-precedence resolution")
```

and `HIDDEN_RULES_R5 = tuple(HIDDEN_RULES_R4)`; `entry["hidden_generation_rules"] = list(HIDDEN_RULES_R5 if round >= 5 else HIDDEN_RULES_R4 if round >= 4 else HIDDEN_RULES_R3)`. Run the test → Expected: 3 OK (plus the inherited Round 4 tests).

- [ ] **Step 4: Counterexample module — failing tests**

Create `tests/benchmarks/test_counterexample.py`:

```python
import unittest
from tests.benchmarks import counterexample as cx

BASE = {"aliases": {"ticket": ["issue"]}, "rules": [{"when_all": ["blog", "entry"], "add": ["blogpost"]}], "notes": {}}


def raw(aliases=None, rules=None):
    return {"aliases": dict(BASE["aliases"], **(aliases or {})), "rules": list(BASE["rules"]) + list(rules or []), "notes": {}}


INDEX = [{"key": "a:GET:/version", "summary_tokens": frozenset({"get", "version"}), "opid_path_tokens": frozenset({"version"})},
         {"key": "a:GET:/release", "summary_tokens": frozenset({"get", "release"}), "opid_path_tokens": frozenset({"release"})},
         {"key": "a:GET:/build", "summary_tokens": frozenset({"get", "build"}), "opid_path_tokens": frozenset({"build"})}]


class TestCounterexample(unittest.TestCase):
    def test_tokens_projection(self):
        self.assertEqual(cx.counterexample_tokens(("alias", "search")), ("search",))
        self.assertEqual(cx.counterexample_tokens(("phrase", ("issue", "type"))), ("issue", "type"))
        self.assertNotIn("alias", cx.counterexample_tokens(("alias", "search"))); self.assertNotIn("phrase", cx.counterexample_tokens(("phrase", ("issue", "type"))))

    def test_canonical_map_and_diff(self):
        a, b = cx.canonical_policy_map(raw()), cx.canonical_policy_map(raw({"release": ["version"]}))
        self.assertEqual(cx.diff(a, b), [("alias", "release")])
        self.assertIn(("phrase", ("blog", "entry")), a)

    def test_old_to_absent_is_a_changed_key(self):
        pre, post = raw({"release": ["build"]}), raw()
        self.assertEqual(cx.diff(cx.canonical_policy_map(pre), cx.canonical_policy_map(post)), [("alias", "release")])

    def test_loss_detection_and_classes(self):
        top1 = lambda policy, q: "a:GET:/build" if ("release" in policy["aliases"] and "release" in q) else {"get version": "a:GET:/version", "get release": "a:GET:/release", "get build": "a:GET:/build"}[q]
        out = cx.suite(INDEX, top1, raw(), raw({"release": ["build"]}), raw({"release": ["build"]}), summaries={"a:GET:/version": "get version", "a:GET:/release": "get release", "a:GET:/build": "get build"})
        self.assertEqual(out["classes"]["covered_static"], [["alias", "release"]]); self.assertEqual(out["losses"], [{"key": ["alias", "release"], "op": "a:GET:/release"}])

    def test_uncovered_proposer_key_blocks_accept(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw(), raw(), raw({"zzword": ["version"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX})
        self.assertEqual(out["classes"]["uncovered_proposer"], [["alias", "zzword"]]); self.assertFalse(out["ok"])

    def test_proposer_wins_when_both_changed(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw({"zzword": ["build"]}), raw({"zzword": ["release"]}), raw({"zzword": ["version"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX})
        self.assertEqual(out["classes"]["uncovered_proposer"], [["alias", "zzword"]]); self.assertEqual(out["classes"]["uncovered_static"], [])

    def test_uncovered_static_is_recorded_not_blocking(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX},
                       provenance={("alias", "zzword"): {"source": "round4_generation", "provenance_rank": 1}})
        self.assertTrue(out["ok"]); self.assertEqual([d["key"] for d in out["uncovered_static_diagnostics"]], [["alias", "zzword"]])

    def test_missing_provenance_is_incomplete_and_shas_bound(self):
        top1 = lambda policy, q: "a:GET:/version"
        sm = {k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX}
        out = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"]}), summaries=sm)
        self.assertIn("counterexample_diagnostic_incomplete", out["validation_errors"]); self.assertFalse(out["ok"])
        good = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"]}), summaries=sm,
                        provenance={("alias", "zzword"): {"source": "round4_generation", "provenance_rank": 1}}, scope="final_policy", selected_constants={"a": 1})
        self.assertTrue(good["ok"]); self.assertEqual(good["scope"], "final_policy"); self.assertEqual(good["selected_constants"], {"a": 1})
        other = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"], "yy": ["build"]}), summaries=sm,
                         provenance={("alias", "zzword"): {"source": "round4_generation", "provenance_rank": 1}})
        self.assertNotEqual(good["post_policy_sha256"], other["post_policy_sha256"])

    def test_provenance_from_lexicon(self):
        doc = {"selected": {"release": {"source": "round4_generation", "provenance_rank": 1}}, "rejected": {"release": {"reason": "seed-incompatible"},
               "fresh": {"reason": "no-eligible-candidate", "candidates": [{"source": "round2_archive"}]}}}
        prov = cx.provenance_from_lexicon(doc)
        self.assertEqual(prov[("alias", "release")], {"source": "round4_generation", "provenance_rank": 1, "gate_reason": "seed-incompatible"})
        capped = cx.provenance_from_lexicon({"selected": {"fff": {"source": "round4_generation", "provenance_rank": 1}}, "rejected": {"fff": {"reason": "concept-cap"}}})
        self.assertEqual(capped[("alias", "fff")]["gate_reason"], "concept-cap")
        self.assertIsNone(prov[("alias", "fresh")]["source"])

    def test_partition_invariant(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw(), raw({"release": ["version"]}), raw({"release": ["version"], "zzword": ["build"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX})
        parts = [tuple(map(tuple, v)) for v in out["classes"].values()]
        flat = [k for p in parts for k in p]
        self.assertEqual(sorted(flat), sorted(map(tuple, out["scope_keys"]))); self.assertEqual(len(flat), len(set(flat)))
```

Run: `python -m unittest tests.benchmarks.test_counterexample -v` → Expected: ERROR `ModuleNotFoundError: … counterexample`.

- [ ] **Step 5: Implement `tests/benchmarks/counterexample.py`**

```python
"""Round 5 spec §8: non-target counterexample suite (summary-as-query) over the canonical policy diff, four key classes,
uncovered-static diagnostics, partition and completeness validation. Pure core (`suite`) + production bindings."""
import pathlib, sys
if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tests.benchmarks import alias_candidates_tool as act
from tests.benchmarks.evaluator import canonical_sha256

CLASSES = ("covered_static", "uncovered_static", "covered_proposer", "uncovered_proposer")
DIAG_FIELDS = ("key", "provenance", "summary_slice_size", "opid_path_coverage", "title_rows", "changed_title_rows")


def canonical_policy_map(raw) -> dict:
    out = {("alias", w): tuple(sorted(t)) for w, t in (raw.get("aliases") or {}).items()}
    for r in raw.get("rules") or []:
        out[("phrase", tuple(sorted(r["when_all"])))] = tuple(sorted(r["add"]))
    return out


def diff(a: dict, b: dict) -> list:
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def counterexample_tokens(ckey) -> tuple:
    tag, body = ckey
    return (body,) if tag == "alias" else tuple(body)


def provenance_from_lexicon(lexicon_doc) -> dict:
    """Spec §8 provenance rules from concept_lexicon.json: selected entry → source/rank (+ gate_reason when the post-resolution gate
    removed it); no eligible candidate → source null + rejected_candidates."""
    out, rej = {}, lexicon_doc.get("rejected") or {}
    def ck(word):
        toks = tuple(word.split(" "))
        return ("phrase", tuple(sorted(toks))) if len(toks) > 1 else ("alias", word)
    for word, sel in (lexicon_doc.get("selected") or {}).items():
        out[ck(word)] = {"source": sel["source"], "provenance_rank": sel["provenance_rank"], **({"gate_reason": rej[word]["reason"]} if word in rej else {})}
    for word, r in rej.items():
        if ck(word) not in out and r.get("candidates"):
            out[ck(word)] = {"source": None, "rejected_candidates": r["candidates"]}
    return out


def suite(index, top1, pre_raw, static_raw, post_raw, summaries, titles=(), provenance=None, scope="lexicon_only", selected_constants=None) -> dict:
    """index: [{key, summary_tokens, opid_path_tokens}]; top1(policy_raw, query) -> op key or None; summaries: {op key: summary};
    titles: [{product, url, title}] (diagnostic only); provenance: {ckey: dict} for uncovered-static rows."""
    scope_name = scope
    pre, static, post = (canonical_policy_map(r) for r in (pre_raw, static_raw, post_raw))
    proposer = set(diff(static, post)); scope = diff(pre, post)
    classes = {c: [] for c in CLASSES}; losses, counts, diags, errors = [], {}, [], []
    for k in scope:
        toks = set(counterexample_tokens(k)); origin = "proposer" if k in proposer else "static"
        sl = [e for e in index if toks <= e["summary_tokens"]]
        cls = ("covered_" if sl else "uncovered_") + origin; classes[cls].append(list(k))
        pre_h = post_h = 0
        for e in sorted(sl, key=lambda e: e["key"]):
            q = summaries[e["key"]]; a, b = top1(pre_raw, q) == e["key"], top1(post_raw, q) == e["key"]
            pre_h += a; post_h += b
            if a and not b:
                losses.append({"key": list(k), "op": e["key"]})
        counts[" ".join(map(str, (k[0],) + tuple(counterexample_tokens(k))))] = {"slice": len(sl), "pre_hits": pre_h, "post_hits": post_h}
        if cls == "uncovered_static":
            rows = sorted({(t["product"], t["url"], t["title"]) for t in titles if toks <= set(act.norm_tokens(t["title"]))})
            seen, uniq = set(), []
            for r in rows:
                if r[1] not in seen:
                    seen.add(r[1]); uniq.append(r)
            changed = [{"title": r[2], "url": r[1], "pre_top1": top1(pre_raw, r[2]), "post_top1": top1(post_raw, r[2])} for r in uniq]
            prov = (provenance or {}).get(k)
            if prov is None or (prov.get("source") is None and not prov.get("rejected_candidates")):
                errors.append("counterexample_diagnostic_incomplete")
            diags.append({"key": list(k), "provenance": prov, "summary_slice_size": 0,
                          "opid_path_coverage": sorted(e["key"] for e in index if toks <= e["opid_path_tokens"]),
                          "title_rows": len(uniq), "changed_title_rows": [c for c in changed if c["pre_top1"] != c["post_top1"]]})
    flat = [tuple(map(lambda x: tuple(x) if isinstance(x, list) else x, v)) for c in CLASSES for v in classes[c]]
    if sorted(flat) != sorted(scope) or len(flat) != len(set(flat)):
        errors.append("counterexample_classification_invalid")
    if sorted(tuple(map(lambda x: tuple(x) if isinstance(x, list) else x, d["key"])) for d in diags) != sorted(map(tuple, (tuple(map(lambda x: tuple(x) if isinstance(x, list) else x, v)) for v in classes["uncovered_static"]))) \
            or any(f not in d for d in diags for f in DIAG_FIELDS):
        errors.append("counterexample_diagnostic_incomplete")
    errors = sorted(set(errors))
    return {"scope": scope_name, "scope_keys": [list(k) for k in scope], "classes": classes, "losses": losses, "per_key_counts": counts,
            "uncovered_static_diagnostics": diags, "validation_errors": errors, "selected_constants": dict(selected_constants or {}),
            "pre_policy_sha256": canonical_sha256(pre_raw), "static_policy_sha256": canonical_sha256(static_raw), "post_policy_sha256": canonical_sha256(post_raw),
            "ok": not losses and not classes["uncovered_proposer"] and not errors}


def catalog_index(state):
    index, summaries = [], {}
    for _name, sr in sorted(state.registry.sources.items()):
        for e in sr.search_index.entries:
            op = sr.operations_by_key[e.key]; summaries[e.key] = op.summary or ""
            index.append({"key": e.key, "summary_tokens": frozenset(act.norm_tokens(op.summary or "")),
                          "opid_path_tokens": frozenset(act.norm_tokens(op.operation_id or "")) | frozenset(t for p in e.path_tokens for t in act.norm_tokens(p.origin))})
    return index, summaries


def production_top1(state, rp, point):
    """top1(policy_raw, query) on the production search path at `point` (one alias policy load per distinct raw object)."""
    from unittest import mock
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy, search
    cache = {}
    def top1(raw, q):
        ap = cache.setdefault(id(raw), (raw, tune._alias_policy(raw)))[1]
        with mock.patch.object(policy, "ranking", return_value=tune.ranking_with(rp, point)), mock.patch.object(policy, "aliases", return_value=ap):
            res = search.search_operations(state, q, limit=1).get("results") or []
        return res[0]["key"] if res else None
    return top1
```

Run: `python -m unittest tests.benchmarks.test_counterexample -v` → Expected: 9 OK. (Keys in `classes`/`losses` are JSON-ready lists; `scope_keys` is the canonical tuple list as lists.)

- [ ] **Step 6: KU-aware pipeline and the counterexample term in `tune_search_ranking.py` — failing tests, then implementation**

Append to `tests/test_tune_search_ranking.py`:

```python
class TestRound5KU(unittest.TestCase):
    """Round 5 spec §4.2: KU semantics in acceptance, proposer input and selector; counterexample term; equivalences."""
    def _res(self, failed):
        return {"passed": 39 - len(failed), "failed": [{"id": i} for i in failed]}

    def test_tuning_accept_ku_and_equivalence(self):
        reg = {"effective_passed": tune.REGRESSION_TOTAL}
        ku = frozenset({"s-004", "s-027", "s-039"})
        self.assertTrue(tune.tuning_accept(self._res(["s-004", "s-039"]), reg, [], ku=ku))
        self.assertFalse(tune.tuning_accept(self._res(["s-004", "s-028"]), reg, [], ku=ku))
        self.assertEqual(tune.tuning_accept(self._res(["s-004"]), reg, []), tune.tuning_accept(self._res(["s-004"]), reg, [], ku=frozenset()))
        self.assertFalse(tune.tuning_accept(self._res([]), reg, [], ku=ku, cx={"ok": False}))

    def test_selector_ignores_ku_pass_counts(self):
        ku = frozenset({"s-004", "s-027", "s-039"})
        a = tune.reachable_results([({"p": 1}, self._res(["s-004"]), {"passed": 14})], ku)
        b = tune.reachable_results([({"p": 1}, self._res(["s-004", "s-027", "s-039"]), {"passed": 14})], ku)
        self.assertEqual(a, b)                                   # same reachable performance → same selector input
        c = tune.reachable_results([({"p": 2}, self._res(["s-028"]), {"passed": 14})], ku)
        self.assertEqual(c[0][1], tune.SEED_TOTAL - len(ku) - 1)

    def test_proposer_never_sees_ku(self):
        seen = []
        def evaluate_fn(point, raw):
            return self._res(["s-004", "s-028"]), {"passed": 14, "failed": [], "effective_passed": 14, "raw_passed": 10}
        def fake_propose(eval_fn, bench, base, cands, fixture_fn=None):
            seen.append(eval_fn(base)[0]); return base, {"aliases": {}, "rules": [], "notes": {}}
        consts = json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))["constants"]
        grid = {k: [v] for k, v in consts.items()}                    # one grid point: every CONSTANT_KEY present
        with mock.patch.object(tune, "propose_aliases", fake_propose), mock.patch.object(tune, "KU", frozenset({"s-004"})):
            tune.run_pipeline(evaluate_fn, {"seed": []}, {"aliases": {}, "rules": [], "notes": {}}, {"candidates": {}},
                              grid, dict(consts), lambda p, r: [])
        self.assertEqual(seen, [frozenset({"s-028"})])
```

Run: `python -m unittest tests.test_tune_search_ranking.TestRound5KU -v` → Expected: FAIL/ERROR (`unexpected keyword argument 'ku'`, no `reachable_results`, no `KU`).

Implement in `tests/tune_search_ranking.py`:

```python
KU = ev.known_unreachable(ev.pending_round() or ROUND)                 # Round 5 spec §4.1: the pending round before T (pre-T dry-run), the frozen round after T; empty without a registry


def reachable_results(raw_results, ku):
    """(point, seed_res, reg_res) -> (point, reachable_passed, regression_passed); KU pass counts never enter selection."""
    total = SEED_TOTAL - len(ku)
    return [(p, total - len({f["id"] for f in s["failed"]} - ku), r["passed"]) for p, s, r in raw_results]


def tuning_accept(seed_res, reg_res, fixture_final, ku=frozenset(), cx=None) -> bool:
    """Round 5 spec §4.2 base_tuning_accept: failed ⊆ KU ∧ regression effective ∧ fixture ∧ counterexample ok (when computed)."""
    failed = {f["id"] for f in seed_res["failed"]}
    return failed <= set(ku) and reg_res["effective_passed"] == REGRESSION_TOTAL and not fixture_final and (cx is None or cx["ok"])
```

In `run_pipeline`: collect `raw = [(point, s, r)]` instead of `results.append((point, s["passed"], r["passed"]))`, then `results = reachable_results(raw, KU)` and `selected = select_candidate(results, baseline, grid, seed_total=SEED_TOTAL - len(KU))`; in the nested `eval_fn` return `frozenset(f["id"] for f in s["failed"]) - KU` for the seed set. Add `counterexample_result: dict = None` as the last `PipelineResult` field. Change `run_pipeline_result` to:

```python
def run_pipeline_result(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn, queries, classes, counterexample_fn=None) -> PipelineResult:
    results, selected, working, patch, seed_res, reg_res, fixture_fail = run_pipeline(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn)
    errors = validate_alias_change(aliases_raw, working, cands_doc["candidates"], queries, classes)
    cxr = counterexample_fn(selected, working) if counterexample_fn is not None else None
    if cxr is not None:
        errors = errors + list(cxr["validation_errors"])
    accept = tuning_accept(seed_res, reg_res, fixture_fail["final"], ku=KU, cx=cxr) and not errors      # PipelineResult.tuning_accept (spec §4.2)
    res = PipelineResult(selected, patch, errors, seed_res, reg_res, fixture_fail, accept, cxr)
    res.grid_results, res.working_aliases = results, working
    return res
```

In `main`, when `ROUND >= 5`: load `ref = json.loads((ROOT / f"tests/benchmarks/round{ROUND}-counterexample-reference.json").read_text())`, `pre_raw = ref["policy"]`, `titles = ref["titles"]`, `prov = cx.provenance_from_lexicon(json.loads(policy.DATA_DIR.joinpath("concept_lexicon.json").read_text()))`, build `index, summaries = cx.catalog_index(state)` inside `body`, and pass `counterexample_fn=lambda point, working: cx.suite(index, cx.production_top1(state, rp, point), pre_raw, aliases_raw, working, summaries, titles=titles, provenance=prov, scope="final_policy", selected_constants=point)`. Pin tests (append to `TestRound5KU`): `test_round_identity` — in this tree before T `tune.KU == ev.known_unreachable(5)`; with `ev.load_round_freeze` patched to `[{"round": 1}, {"round": 2}, {"round": 5}]`, `importlib.reload(tune)` gives `tune.ROUND == 5`, `tune.KU == ev.known_unreachable(5)`, `tune.LOG_REL.endswith("search-tuning-round5.jsonl")` and `tune.round_note("w", "s-001", "t")["origin"] == "round5"` (reload again afterwards to restore); `test_main_loads_reference` — a `main` dry-run with the reference file and `_with_state` patched asserts `counterexample_fn` was built with `scope="final_policy"`. (`tune.ROUND` is `ev.current_round()["round"]`, i.e. 5 from T on; `KU` uses `pending_round()` only before T, when the freeze round is still 2.) Pass `res.tuning_accept` into `_finish` (new parameter `accept`) and delete the recomputation `accept = tuning_accept(...)` there; add `"counterexample": res.counterexample_result` to the log line. The `--adopt` path is unchanged (it reads `tuning_accept` from the log line). Run: `python -m unittest tests.test_tune_search_ranking -v` → Expected: all OK. `KU` is non-empty in this tree (pending round 5); any pre-existing `run_pipeline` test whose fake seed ids collide with `s-004`/`s-027`/`s-039` patches `tune.KU` to `frozenset()` for that test (ledger a `Task 2: Ruling:` line naming each such test); `test_proposer_never_sees_ku` patches `KU` itself.

- [ ] **Step 7: `round5_simulation.py` — failing tests, then the module**

Create `tests/benchmarks/test_round5_simulation.py` with:

```python
import json, pathlib, unittest
from unittest import mock
from tests.benchmarks import round5_simulation as sim, evaluator as ev


class TestRound5PreT(unittest.TestCase):
    def _res(self, failed, reg_eff=14, errors=(), accept=True):
        class R: pass
        r = R(); r.seed_result = {"passed": 39 - len(failed), "failed": [{"id": i} for i in failed]}
        r.regression_result = {"effective_passed": reg_eff, "raw_passed": 10, "failed": []}; r.fixture_result = {"final": []}
        r.validation_errors, r.tuning_accept, r.counterexample_result = list(errors), accept, None
        return r

    def test_ku_failures_are_not_blockers(self):
        self.assertEqual(sim.pre_t_blockers(self._res(["s-004", "s-027", "s-039"]), {"pass": True}), [])

    def test_non_ku_failure_is_a_blocker(self):
        b = sim.pre_t_blockers(self._res(["s-004", "s-028"]), {"pass": True})
        self.assertEqual([x["kind"] for x in b], ["unreachable_seed"]); self.assertEqual(b[0]["seeds"], ["s-028"])

    def test_counterexample_loss_and_record_mismatch_are_blockers(self):
        b = sim.pre_t_blockers(self._res([]), {"pass": True}, lexicon_cx={"scope": "lexicon_only", "ok": False, "losses": [{"key": ["alias", "release"], "op": "x"}], "classes": {"uncovered_proposer": []}, "validation_errors": []},
                               extra=[{"kind": "ku_record_mismatch", "problems": ["s-004: seed record differs from the start commit"]}])
        self.assertEqual(sorted(x["kind"] for x in b), ["counterexample_loss", "ku_record_mismatch"])

    def test_selected_constants_counterexample_failure_is_a_blocker(self):
        r = self._res([], accept=False)
        r.counterexample_result = {"scope": "final_policy", "ok": False, "losses": [{"key": ["alias", "release"], "op": "x"}], "classes": {"uncovered_proposer": []}, "validation_errors": []}
        b = sim.pre_t_blockers(r, {"pass": True}, lexicon_cx={"scope": "lexicon_only", "ok": True, "losses": [], "classes": {"uncovered_proposer": []}, "validation_errors": []})
        self.assertEqual([x["kind"] for x in b], ["counterexample_loss"]); self.assertEqual(b[0]["losses"][0]["scope"], "final_policy")

    def test_false_accept_alone_is_a_blocker(self):
        self.assertEqual([x["kind"] for x in sim.pre_t_blockers(self._res([], accept=False), {"pass": True})], ["tuning_accept_false"])

    def test_counterexample_reference_problems(self):
        from tests.benchmarks import counterexample as cx
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            w = pathlib.Path(td)
            for n in ("aliases-premerge.json", "round4-reference-lexicon.json"):
                (w / n).write_text("{}\n")
            pol = {"aliases": {"ticket": ["issue"]}, "rules": [], "notes": {}}
            cmap = {json.dumps(list(k)): list(v) for k, v in cx.canonical_policy_map(pol).items()}
            good = {"policy": pol, "policy_canonical_sha256": ev.canonical_sha256(pol), "canonical_policy_map": cmap, "canonical_policy_map_sha256": ev.canonical_sha256(cmap),
                    "inputs": {**sim.INPUT_SHA256, "aliases_premerge_sha256": ev.file_sha256(w / "aliases-premerge.json"),
                               "round4_reference_lexicon_sha256": ev.file_sha256(w / "round4-reference-lexicon.json"), "registry_fingerprint": "fp"}}
            self.assertEqual(sim.counterexample_reference_problems(good, w, "fp"), [])
            missing = json.loads(json.dumps(good)); del missing["inputs"]["round2/lexicon_raw.json"]
            self.assertTrue(sim.counterexample_reference_problems(missing, w, "fp"))
            wrong_map = json.loads(json.dumps(good)); wrong_map["canonical_policy_map"] = {}
            self.assertTrue(sim.counterexample_reference_problems(wrong_map, w, "fp"))
            self.assertTrue(sim.counterexample_reference_problems(good, w, "other-fp"))

    def test_ku_record_mismatch_is_a_blocker(self):
        bench = json.loads((pathlib.Path(sim.ROOT) / "tests/benchmarks/search_queries.json").read_text(encoding="utf-8"))
        doc = json.loads((pathlib.Path(sim.ROOT) / "tests/benchmarks/round5-known-unreachable.json").read_text(encoding="utf-8"))
        changed = json.loads(json.dumps(bench)); next(r for r in changed["seed"] if r["id"] == "s-027")["query"] = "show my favourite filters"
        self.assertEqual([x["kind"] for x in sim.registry_blockers(changed, bench, doc)], ["ku_record_mismatch"])

    def test_input_sha_table_matches_spec(self):
        spec = (pathlib.Path(sim.ROOT) / "docs/superpowers/specs/2026-10-09-search-quality-round5-design.md").read_text(encoding="utf-8")
        for name, sha in sim.INPUT_SHA256.items():
            self.assertIn(sha, spec, name)
```

Run: `python -m unittest tests.benchmarks.test_round5_simulation -v` → Expected: ERROR `ModuleNotFoundError`.

Create `tests/benchmarks/round5_simulation.py` as a copy of `tests/benchmarks/round4_simulation.py` (`cp`, then edit), with exactly these changes:
1. `ROUND = 5`, `SIM_DIR = ".round5-sim"`, docstrings say Round 5; `HIDDEN_EVAL_EVENTS`/checkpoint names use `round5`.
2. Add the input table and the registry checks:

```python
INPUT_SHA256 = {   # Round 5 spec §5 (full sha256); files are copied into $W/inputs/ by the controller (Task 3 Step 2)
    "round2/lexicon_raw.json": "acc5cebeafc5c48236a9de5d685b888fb2a83532340405556d77b801468a6872",
    "round2/lexicon_review.json": "c5ba256f8acd082febe06724d6646bff631e136dc437f4fa1528286117bd62f4",
    "round2/lexicon-review-input.txt": "17efa0b87647cf89357fffe3c2aaf2f0effb24539ce1c44b399a0a574eb3a484",
    "round2/lexicon-generation-input.txt": "9125fa8444453762076cdb5c6791f166f46a15579fd016bfcbb8cd4412bd857e",
    "round4/lexicon_raw_r4.json": "929e996ea4b69286811f24de9c379b6143b07f127705558d1abc633329d18105",
    "round4/lexicon_review_r4.json": "308e115be3d944bd0f36108255a03bd14edc1a06b5f9182a9c5042aad35e325b",
    "round4/lexicon-review-input-r4.txt": "8da851f5f00830428d15f6f722d3ca102ea33f1c3ef083cb52143660f50edd27",
    "round4/lexicon-generation-input-r4.txt": "6bfacc2589ab2a715391a299f9106d680689038b879752a0d216504845bbd9c1",
    "round4/doc-titles-snapshot.json": "2d3caa6e02e0a67c523940add30e083cac415564302deb7e51a832ead50e6453",
}


def input_blockers(work) -> list:
    bad = [n for n, sha in INPUT_SHA256.items() if not (work / "inputs" / n).exists() or ev.file_sha256(work / "inputs" / n) != sha]
    return [{"kind": "input_sha_mismatch", "files": bad}] if bad else []


def registry_blockers(bench, base_bench, registry_doc) -> list:
    p = ev.ku_registry_schema_problems(ROUND, registry_doc) + ev.ku_record_problems(ROUND, bench, base_bench, registry_doc)
    return [{"kind": "ku_record_mismatch", "problems": p}] if p else []


def counterexample_reference_problems(ref, work, registry_fp) -> list:
    """Round 5 spec §8/§9: the T-committed reference is internally consistent and bound to this run's inputs."""
    from tests.benchmarks import counterexample as cx
    out = []
    cmap = {json.dumps(list(k)): list(v) for k, v in cx.canonical_policy_map(ref["policy"]).items()}
    if ev.canonical_sha256(ref["policy"]) != ref.get("policy_canonical_sha256"):
        out.append("policy_canonical_sha256")
    if cmap != ref.get("canonical_policy_map") or ev.canonical_sha256(cmap) != ref.get("canonical_policy_map_sha256"):
        out.append("canonical_policy_map")
    inputs = ref.get("inputs") or {}
    expected = set(INPUT_SHA256) | {"aliases_premerge_sha256", "round4_reference_lexicon_sha256", "registry_fingerprint"}
    if set(inputs) != expected:
        out.append(f"input keys {sorted(set(inputs) ^ expected)}")
    out += [f"input {n}" for n, sha in INPUT_SHA256.items() if inputs.get(n) != sha]
    for key, fname in (("aliases_premerge_sha256", "aliases-premerge.json"), ("round4_reference_lexicon_sha256", "round4-reference-lexicon.json")):
        f = work / fname
        if not f.exists() or inputs.get(key) != ev.file_sha256(f):
            out.append(key)
    if inputs.get("registry_fingerprint") != registry_fp:
        out.append("registry_fingerprint")
    return out


def approval_blockers(work, registry_doc) -> list:
    """Round 5 spec §4.1: each ruling file sha and the user-decision event sha recompute exactly."""
    probs = []
    for r in registry_doc.get("approval", {}).get("rulings", []):
        f = work / "rulings" / r["file"]
        if not f.exists() or ev.file_sha256(f) != r["review_output_sha256"]:
            probs.append(f"ruling {r['file']}")
    ud = registry_doc.get("approval", {}).get("user_decision", {})
    events = [json.loads(l) for l in (work / "controller-events.jsonl").read_text(encoding="utf-8").splitlines()] if (work / "controller-events.jsonl").exists() else []
    if not any(e.get("event") == "user_decision_round5" and ev.canonical_sha256({k: e[k] for k in ("role", "timestamp", "exact_text")}) == ud.get("event_sha256") for e in events):
        probs.append("user_decision event")
    return [{"kind": "ku_approval_mismatch", "problems": probs}] if probs else []
```

3. Replace `pre_t_blockers` with:

```python
def pre_t_blockers(result, event, diagnostics=None, ku=None, lexicon_cx=None, extra=()) -> list:
    """Round 5 spec §4.2/§8/AC-R5-09: only non-KU failures are unreachable; both counterexample results (lexicon-only at baseline
    constants and final policy at the selected constants) and registry problems are blockers; the dry-run tuning_accept stays the
    authority (a false accept with no other blocker is still a blocker)."""
    ku = ev.known_unreachable(ROUND) if ku is None else ku
    out = []
    unreachable = sorted({f["id"] for f in result.seed_result["failed"]} - set(ku))
    if unreachable:
        out.append({"kind": "unreachable_seed", "seeds": unreachable, "diagnostics": diagnostics or {}})
    broken = {"regression_effective": result.regression_result["effective_passed"], "fixture_final": list(result.fixture_result["final"])}
    if result.regression_result["effective_passed"] != 14 or result.fixture_result["final"]:
        out.append({"kind": "tuning_accept_false", "invariants": broken})
    if result.validation_errors:
        out.append({"kind": "alias_validation_error", "errors": list(result.validation_errors)})
    if not event["pass"]:
        out.append({"kind": "inherited_ac_r3_01_failure", "event": {k: event.get(k) for k in ("seed", "regression_raw", "regression_effective", "fixture_failing")}})
    results = [c for c in (lexicon_cx, getattr(result, "counterexample_result", None)) if c is not None]
    losses = sorted({(c.get("scope"), json.dumps(l["key"]), l["op"]) for c in results for l in c.get("losses", [])})
    if losses:
        out.append({"kind": "counterexample_loss", "losses": [{"scope": sc, "key": json.loads(k), "op": op} for sc, k, op in losses]})
    unc = sorted({(c.get("scope"), json.dumps(k)) for c in results for k in c["classes"].get("uncovered_proposer", [])})
    if unc:
        out.append({"kind": "counterexample_uncovered_proposer", "keys": [{"scope": sc, "key": json.loads(k)} for sc, k in unc]})
    # counterexample validation errors reach result.validation_errors via run_pipeline_result (single authority, no duplicate blocker)
    if not result.tuning_accept and not out:
        out.append({"kind": "tuning_accept_false", "invariants": {"reason": "dry-run tuning_accept false with no other blocker"}})
    return out + list(extra)
```

4. `pre_t_verdict(seed_passed, …)` becomes `pre_t_verdict(failed_ids, reg_raw, reg_eff, fixture_failing)` = `set(failed_ids) <= ev.known_unreachable(ROUND) and reg_raw >= 10 and reg_eff == 14 and not fixture_failing`; `pre_t_event` passes the failed id list.
5. `run_pre_t(cache, work)`: first load `ref = round5-counterexample-reference.json`, `pre_raw = ref["policy"]`, `snapshot_titles = ref["titles"]` and `prov = cx.provenance_from_lexicon(concept_lexicon.json)` (all before any `cx.suite` call); then compute `extra = input_blockers(work) + registry_blockers(bench, base_bench, registry_doc) + approval_blockers(work, registry_doc)` plus `[{"kind": "counterexample_reference_mismatch", "problems": p}]` when `p = counterexample_reference_problems(ref, work, fp)` is non-empty where `base_bench` is the `56b4b0e` blob of `tests/benchmarks/search_queries.json` (`git show 56b4b0e:tests/benchmarks/search_queries.json`) and `registry_doc` the committed `round5-known-unreachable.json`; compute the lexicon-only counterexample at baseline constants: `cxr = cx.suite(index, cx.production_top1(state, rp, dict(rp.constants)), pre_raw, aliases_raw, aliases_raw, summaries, titles=snapshot_titles, provenance=prov)` (the reference is written by the controller in Task 4 Step 5; a lexicon-only pre-T check with `cx.suite(…, scope="lexicon_only")` follows); pass `counterexample_fn=lambda point, working: cx.suite(index, cx.production_top1(state, rp, point), pre_raw, aliases_raw, working, summaries, titles=snapshot_titles, provenance=prov, scope="final_policy", selected_constants=point)` into `dry_run_pipeline` → `tune.run_pipeline_result`; call `pre_t_blockers(result, event, diagnostics, lexicon_cx=cxr, extra=extra)`; record `cxr`, `result.counterexample_result`, `result.tuning_accept`, all blockers and `pipeline_result_sha256` (which now includes `counterexample_result`) in the event. Event name stays `pre_t_checkpoint`.
6. `apply_T`: after the synthetic merge write `concept_lexicon.json["components"]["union_resolution"] = "source-precedence"` and `concept_lexicon.json["selected"]` for the synthetic entries (`{"source": "round4_generation", "provenance_rank": 1}`), and write `tests/benchmarks/round5-counterexample-reference.json` = `{"round": 5, "policy": <pre-merge aliases raw>, "policy_canonical_sha256": canonical_sha256(…), "canonical_policy_map": …, "titles": <synthetic bundle snapshot titles>, "inputs": {}}` before the freeze call.
7. `BRANCHES`, X_preB and recovery helpers are unchanged apart from the round number.

Run: `python -m unittest tests.benchmarks.test_round5_simulation -v` → Expected: 8 OK.

- [ ] **Step 8: Suite, `--phase H`, AC-R5-05, `TOOLING_FILES`, commit H17**

Add to `TOOLING_FILES`: `"tests/benchmarks/counterexample.py", "tests/benchmarks/test_counterexample.py", "tests/benchmarks/round5_simulation.py", "tests/benchmarks/test_round5_simulation.py"` (comment `# Round 5 (H17)`).

```bash
python -m unittest discover -s tests -t . 2>&1 | tail -3                      # Expected: OK, 1+ skipped (Round 4 X_preB test)
python -m tests.benchmarks.round5_simulation --phase H 2>&1 | tail -12        # Expected: ALL STEPS PASS (T, B, D, F, X, XpreB2..5)
git diff --stat 56b4b0e..HEAD -- tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py   # Expected: empty
git add tests/benchmarks/evaluator.py tests/benchmarks/round_seal.py tests/tune_search_ranking.py tests/benchmarks/counterexample.py tests/benchmarks/test_counterexample.py \
        tests/benchmarks/round5-known-unreachable.json tests/benchmarks/round5_simulation.py tests/benchmarks/test_round5_simulation.py \
        tests/benchmarks/test_evaluator.py tests/benchmarks/test_round_seal.py tests/test_tune_search_ranking.py
git commit -m "H17: KU registry and KU-aware acceptance/selector/proposer, counterexample suite, Round 5 freeze keys and per-round T allowlist, round5_simulation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 9: Whole-branch review (fresh reviewer, most capable model) over `b8f4e78..H17`**

`superpowers:executing-plans` Final Review: review package `56b4b0e..HEAD` restricted to `tests/`, spec v1.10, this plan, the Review Focus list verbatim, and the ledger `Ruling:` lines. Re-grade; one TDD fix pass for Critical/Important (each RED→GREEN, suite green, `--phase H` again); minors → ledger. The final reviewed commit is `housekeeping_commit`.

---
### Task 3: **[controller]** Pin `initial_housekeeping_commit`, create S, bind the reused inputs, verb inventory

- [ ] **Step 1: Pin and create S** — `python tests/benchmarks/round_seal.py round-start-guard --round 5` → exit 0; then as Round 4 plan v7 Task 4 Step 1 with the substitutions: first ledger event `{"event": "initial_housekeeping_commit", "sha": <H17 or last H′>, "round5_start_commit": "56b4b0e", "controller_actor_id", "session_id", "plan_review": {"verdict", "review_output_sha256"}}`; live fetch `python -m tools.atlassian_docs`, compared with the **archived Round 4 S** (`~/.atlassian_api_updater/archive/round4/round4-cache`, registry `d69b9ca6e6f106939d5f9d19515365df05006652d659ce7b8169cf8b6b24e882`) → identical: copy the archived S to `$S` (`s_reused_from_round4: true`); different: copy the live cache (`false`, ledger the changed spec shas). `round_seal.py catalog --round 5 --cache-dir $S --out $W/round5-generator-catalog.json --internal-out $W/round5-internal-catalog.json`; `export ATLASSIAN_DOCS_ROUND5_CACHE=$S`.
- [ ] **Step 2: Bind the reused inputs (spec §5)** — copy into `$W/inputs/round2/` the four Round 2 archive files and into `$W/inputs/round4/` the four Round 4 lexicon files plus `doc-titles-snapshot.json` (names as in `round5_simulation.INPUT_SHA256`); re-render the snapshot from the archived bundle (`python -m tests.benchmarks.doc_titles snapshot --sources ~/.atlassian_api_updater/archive/round4/round4-work/doc-title-sources --out $W/inputs/round4/doc-titles-snapshot.rerender.json`) and require byte equality with the copy; `python -c "from tests.benchmarks import round5_simulation as s, pathlib; print(s.input_blockers(pathlib.Path('$W')))"` → `[]`. Ledger `inputs_bound` with every sha. Any mismatch → STOP (review thread).
- [ ] **Step 3: Verb inventory and method-safety** — Round 4 plan v7 Task 4 Step 3 with substitutions (`round5-method-safety.json`). Ledger `verb_inventory_sha256` (expected unchanged `d66317db…`).

### Task 4: **[controller]** Lexicon by source-precedence resolution (no generation) and the Round 4 reference policy

- [ ] **Step 1: Save the pre-merge state** — `cp tools/atlassian_docs/intelligence/data/search_aliases.json $W/aliases-premerge.json; cp tests/benchmarks/search_queries.json $W/bench-preclassify.json`; ledger both shas.
- [ ] **Step 2: Resolve; render pending pairs**

```bash
I=$W/inputs; T=tests/benchmarks/round4-lexicon-review-prompt.md
python tests/benchmarks/concept_lexicon_check.py resolve --cache-dir $S --round 5 --template $T \
  --source round2_archive $I/round2/lexicon_raw.json $I/round2/lexicon_review.json $I/round2/lexicon-review-input.txt \
  --source round4_generation $I/round4/lexicon_raw_r4.json $I/round4/lexicon_review_r4.json $I/round4/lexicon-review-input-r4.txt \
  --pending-out $W/pending --out $W/concept_lexicon.r5.json
```

Expected: exit 3 with `pending ≥ 1` (at least `release→version`). Ledger `lexicon_pending` (count, conflicts, batch file shas).
- [ ] **Step 3: Stateless review of the pending pairs** — for each `$W/pending/review-input-<n>.txt`: a new ChatGPT Temporary chat (personalization off, screenshot `$W/lexicon-review-r5-<n>-ui-state.jpg`), attachment + byte-exact body, extract the first parseable JSON object to `$W/lexicon_review_r5_<n>.json`; the actor id must differ from every earlier lexicon generator/reviewer (`6ac806e9…`, `6ac80af3…` and the Round 2/3 actors in their ledgers); a non-JSON or incomplete answer → one retry with the identical input in a new chat; a second failure → STOP (spec §6.3). Ledger each attempt in `$W/attempts.jsonl` (stage `lexicon-review-r5`).
- [ ] **Step 4: Resolve with the Round 5 reviews, gate, merge** — rerun Step 2's command with `--review-r5 $W/lexicon_review_r5_<n>.json $W/pending/review-input-<n>.txt` for every batch → exit 0; `cp $W/concept_lexicon.r5.json tools/atlassian_docs/intelligence/data/concept_lexicon.json`; `python tests/benchmarks/alias_candidates_tool.py lexicon-gate --cache-dir $S --round 5 --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json`; `python tests/benchmarks/concept_lexicon_check.py merge --lexicon tools/atlassian_docs/intelligence/data/concept_lexicon.json --aliases tools/atlassian_docs/intelligence/data/search_aliases.json --round 5`. Ledger `lexicon_regated` (kept, gate-removed with reasons, merged counts, `selected` source counts).
- [ ] **Step 5: Round 4 reference policy (spec §8, v1.9)** — on copies only:

```bash
python tests/benchmarks/concept_lexicon_check.py round4-reference --cache-dir $S --round 5 \
  --raw $I/round2/lexicon_raw.json $I/round4/lexicon_raw_r4.json --review $I/round2/lexicon_review.json $I/round4/lexicon_review_r4.json --out $W/round4-reference-lexicon.json
cp $W/aliases-premerge.json $W/round4-reference-aliases.json
# gate the reference with the same pre-merge aliases state (lexicon-gate reads the live aliases file: run it with the live file restored to the pre-merge copy, then put the Round 5 merge back)
cp tools/atlassian_docs/intelligence/data/search_aliases.json $W/aliases-r5-merged.json; cp $W/aliases-premerge.json tools/atlassian_docs/intelligence/data/search_aliases.json
python tests/benchmarks/alias_candidates_tool.py lexicon-gate --cache-dir $S --round 5 --lexicon $W/round4-reference-lexicon.json
cp $W/aliases-r5-merged.json tools/atlassian_docs/intelligence/data/search_aliases.json
python tests/benchmarks/concept_lexicon_check.py merge --lexicon $W/round4-reference-lexicon.json --aliases $W/round4-reference-aliases.json --round 4
python - <<'EOF'
import json, pathlib
from tests.benchmarks.evaluator import canonical_sha256
W = pathlib.Path.home() / ".atlassian_api_updater/round5-work"; pol = json.loads((W / "round4-reference-aliases.json").read_text(encoding="utf-8"))
from tests.benchmarks import counterexample as cx, evaluator as ev, round5_simulation as sim
snap = json.loads((W / "inputs/round4/doc-titles-snapshot.json").read_text(encoding="utf-8"))
cmap = {json.dumps(list(k)): list(v) for k, v in cx.canonical_policy_map(pol).items()}
doc = {"round": 5, "policy": pol, "policy_canonical_sha256": canonical_sha256(pol), "canonical_policy_map": cmap, "canonical_policy_map_sha256": canonical_sha256(cmap),
       "titles": sorted(({"product": t["product"], "url": t["url"], "title": t["title"]} for t in snap["titles"]), key=lambda t: (t["product"], t["url"])),
       "inputs": {"aliases_premerge_sha256": ev.file_sha256(W / "aliases-premerge.json"),
                  "round4_reference_lexicon_sha256": ev.file_sha256(W / "round4-reference-lexicon.json"),
                  **{n: ev.file_sha256(W / "inputs" / n) for n in sim.INPUT_SHA256},
                  "registry_fingerprint": json.loads((W / "round5-internal-catalog.json").read_text(encoding="utf-8")).get("registry_fingerprint")}}
pathlib.Path("tests/benchmarks/round5-counterexample-reference.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
print(doc["policy_canonical_sha256"])
EOF
```

If S was reused from Round 4, the reference policy's `lexicon-r4` entries must equal the archived Round 4 merge (`archive/round4/round4-work/final-uncommitted/search_aliases.json`, origin relabel only) — compare and ledger `round4_reference_replay: identical|differs` (a difference is a tooling defect → H′). Ledger `counterexample_reference_written`.
- [ ] **Step 6: Suite** — `python -m unittest discover -s tests -t .`; the expected failures are only the freeze-dependent tests named in the Round 4 ledger (`test_alias_notes_per_origin`, `test_policy_vocabulary_provenance`, `test_registry_fingerprint_matches_freeze_source`) until T; anything else → systematic debugging / H′.

### Task 5: **[controller]** Candidates, AC-13 replay, binding pre-T gate, frozen texts, freeze, T, post-T check

- [ ] **Step 1: Candidates and classification** — Round 4 plan v7 Task 6 Step 1 (`--round 5`).
- [ ] **Step 2: Replay** — on a temp copy: rerun Task 4 Steps 2–5 from the ledgered input files and require identical `concept_lexicon.json`, merged `lexicon-r5` subset (`ev.lexicon_aliases_sha256(…, 5)`), `round5-counterexample-reference.json` and `alias_candidates.json` (canonical shas). A mismatch is a tooling defect → H′ (fix → suite → `--phase H` → fresh reviewer findings 0 → `housekeeping_commit_moved`).
- [ ] **Step 3: Binding pre-T gate (AC-R5-09)** — `python -m tests.benchmarks.round5_simulation --phase pre-T --cache-dir $S --work $W` → exit 0 required. Exit 1 → `STOP_FOR_AMENDMENT`: write `$W/pre-t-blocker-report.md` (blockers, failing seed ids, counterexample losses/uncovered keys, registry/approval/input problems) and take it to review thread 2; rulings follow Round 4 plan v7 Task 6 Step 3 (amendment → spec v1.x + plan v+1 + reviewed H′ → rerun from the affected step; or `TERMINAL_PRE_T_NOT_REACHED` by user decision only).
- [ ] **Step 4: Frozen texts** — `round5-worker-brief.md`, `round5-hidden-generation-prompt.md`, `round5-hidden-reviewer-prompt.md` = the Round 4 texts (`~/.atlassian_api_updater/archive/round4/round4-work/final-uncommitted/round4-*.md`) with the substitution table applied, plus in the worker brief the acceptance line replaced by: `Acceptance (Round 5 spec §4.2, byte-for-byte): tuning_accept := failed seed ids ⊆ {s-004, s-027, s-039} ∧ regression_effective == 14/14 ∧ fixture_positive == 23/23 ∧ fixture_negative_raw == 6/6 ∧ counterexample ok (no loss, no uncovered proposer key) ∧ no validation errors` and the allowed-inputs line extended with `tests/benchmarks/round5-counterexample-reference.json`.
- [ ] **Step 5: Freeze, T, post-T check** — Round 4 plan v7 Task 6 Step 5 with substitutions; the freeze command has no new arguments (`freeze_entry` reads the KU registry, the reference file and the lexicon components itself); `git add` the exact `ev.t_allowlist(5)` set; after the T commit, the post-T check compares against `ev.t_allowlist(5)` and `freeze_for(5)["t_policy_files"]`. Ledger the freeze printout including `known_unreachable_seeds`, `known_unreachable_registry_sha256`, `lexicon_union_resolution`, `counterexample_reference_sha256`.

### Task 6: **[controller]** Hidden-set generation, review, attempt-needle ledger, commit B, encryption

As Round 4 plan v7 Task 7 with the substitutions (new hidden set `held_out-r5`/`negative-r5`; actors distinct from every earlier generator/reviewer; attempt-needle ledger; user encryption is a hard stop).

### Task 7: **[controller]** S checkpoint and worker dispatch (B..C)

As Round 4 plan v7 Task 8; the worker brief is the Round 5 text (Task 5 Step 4). The worker's tuning log line now carries `counterexample`; the controller checks `tuning_accept` from the line, never recomputes it.

### Task 8: **[controller]** Provenance check, then C (success), F (tuning failure), X (abort) or X_preB (abort before B)

As Round 4 plan v7 Task 9 (Steps 1, 2a–2d) with the substitutions. On F caused only by the counterexample term, the readiness record says so explicitly (`counterexample_loss_at_selected` / `uncovered_proposer_keys`).

### Task 9: **[D controller (fresh actor) + user]** Commit D — single gate evaluation

As Round 4 plan v7 Task 10 (Discovery gate unchanged: held_out ≥ 15/16 actionable, negative 0 failures).

### Task 10: **[controller]** Readiness Round 5 section

Append `## Search Quality Round 5 — decision record (<date>)` after the Round 4 section. Fields: Round 4's list with `round5_start_commit 56b4b0e`, `initial_housekeeping_commit`, `housekeeping_commit` (+ moves), spec v1.10 / plan version, `s_reused_from_round4`, inputs table (spec §5 shas, `inputs_bound`), the `known_unreachable` table (id, cause, mechanisms tried with counterexample numbers, approval shas, record check result), status line `reachable seed: N/36 · KU registry: 3/3 validated · KU observed: pass X / fail 3−X`, `lexicon_union_resolution: source-precedence` with `selected` source counts and Round 5 review attempts, the counterexample results (pre-T lexicon-only and at selected constants: classes, losses, uncovered-static diagnostics), the pre-T event(s) with blockers and `pipeline_result_sha256`, STOP rulings, terminal branch `D | F | X | X_preB | pre-T-not-reached`.

### Task 11: **[controller]** Post-terminal provenance, memory, archive, dashboard, finishing

As Round 4 plan v7 Task 12 with the substitutions; archive `round5-cache`, `round5-work` (inputs, rulings, pending/review files) and any `sealed/round5-sealed.json.enc` under `~/.atlassian_api_updater/archive/round5/` after the user confirms; republish the dashboard artifact `https://claude.ai/artifact/ACaztzhjnZuS5tUGiqx3y4`; remove the probe worktree `/private/tmp/claude-501/r5probe` (`git worktree remove --force` is acceptable only for that throwaway path, after listing its contents); `superpowers:finishing-a-development-branch` (push/merge only on the user's instruction).

## AC coverage map (spec v1.10)

| AC | Where |
|---|---|
| AC-R5-01 | Task 1 tests (a)–(g), `components.union_resolution`, `selected` provenance |
| AC-R5-02 | removed in spec v1.10 (no doc-relation extraction) |
| AC-R5-03 | Task 2 Steps 1–3 (`TestRound5Registry`, `round5-known-unreachable.json`, freeze keys), Task 5 Step 3 (`registry_blockers`, `approval_blockers`), T allowlist excludes the registry file |
| AC-R5-04 | Task 2 Step 6 (`TestRound5KU`), Task 2 Step 7 (`pre_t_blockers` KU) |
| AC-R5-05 | Global Constraints scorer invariance checks at H16/H17 and every H′; Task 8 post-terminal diff |
| AC-R5-06 | Task 1 pair-level reuse tests; Task 4 Step 3 actor separation and attempts ledger |
| AC-R5-07 | Task 3 Step 2 (`input_blockers`, snapshot re-render equality) |
| AC-R5-08 | Task 2 Steps 4–6 (`test_counterexample.py`, `counterexample_fn`), Task 5 Step 3 (pre-T lexicon-only), tuning log `counterexample` |
| AC-R5-09 | Task 5 Step 3 |
| inherited | Round 4 plan v7 AC map with substitutions |
