# Search Quality Round 6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan version:** v3 (2026-10-11; v3 = plan review 2 (P0 2 / P1 4) applied: Round 6 proposer notes bound to `TUNING_ROUND` (pre-T, rehearsal and worker produce byte-identical alias policies); the H22 training split is immutable (a semantic change after H22 is a STOP, never a re-ledger); `promotion_sealed` is historical evidence only; stricter label provenance; rehearsal seeding failures are reported; v2 = plan review 1 (P0 4 / P1 5) applied: PR-7 adopted as spec v1.6 §3.0; `training_split_sha256` over a `failure_classes`-free projection, pinned at H22 and re-checked at pre-T and freeze; rehearsal work seeded with the pre-T evidence; PR-8 conflict detection → STOP; promotion payload re-checked after relabel; `verb_methods_sha256` provenance; loss reasons; H adoption re-measured before the pin; required label provenance schema)

**Goal:** Make the MCP search fit real agent use — recommend only with evidence, never recommend a wrong write — and judge Round 6 by the usage-grounded Discovery gate (reach@3, recommendation coverage, precision, write safety, abstention) on a fresh sealed hidden set.

**Architecture:** H adds four boolean recommendation/ordering rules (R0–R3) to `search.py` as pure functions shared by the production search and the tuning `GridEvaluator`; the evaluator gains a usage-metric layer; the tuning pipeline switches to a metric vector (`wv, fr, sr3, src, srk, rp3, rpk, nab`) with a scorer-rule counterexample term; a labels tool promotes the Round 5 hidden set and relabels regression records by catalog fact; `round6_simulation` adds a real-data rehearsal phase. The controller lifecycle (S → promotion/relabel → H adoption → review → rehearsal → T → B → worker → C/F/X → D) is inherited from Round 5 plan v8 with substitutions.

**Tech Stack:** Python 3.11 stdlib + the project's MCP SDK; `unittest` (`python -m unittest discover -s tests -t .`); ChatGPT Temporary chats for stateless reviewers; review thread 2 for rulings.

**Spec:** `docs/superpowers/specs/2026-10-11-search-quality-round6-design.md` **v1.6** (review 4: P0 0 / P1 4, "구현 계획으로 진행 가능"; v1.6 = plan review 1 P0-1, the rule token stream §3.0). It inherits Round 5 spec v1.12 (and through it Round 4 v1.13 / Round 3 v1.25.1). "As Round 5 plan v8 Task N" imports that committed procedure verbatim with the substitution table below.

## Global Constraints

- Never call real Jira/Confluence APIs. The only network step is `python -m tools.atlassian_docs` (S creation, once).
- Scorer/policy structure changes (`search.py`, `policy.py`, `search_ranking.json` structure) happen **only in H**; from the H final commit (`housekeeping_commit`) through the terminal commit they are byte-identical (AC-R6-09). B..C may change only `constants` values and aliases (inherited).
- New rules add **no numeric constants** (boolean rules); `POLICY_VERSIONS["search"] = 5`.
- `TOOLING_FILES` are immutable from `housekeeping_commit` through the terminal commit (AGENTS.md); a tool defect before T is fixed in an H′ commit (suite → `--phase H` → fresh reviewer findings 0 → `housekeeping_commit_moved`), after T it ends the round.
- All ratio gates are exact integer comparisons (spec §4.1): reach `16·reach ≥ 15·n`, coverage `16·cov ≥ 14·n`, precision `cov > 0 ∧ 10·correct ≥ 9·cov`, write safety `== 0`, abstention `8·abst ≥ 7·n`; training uses spec §4.2 `accept(m)` exactly.
- Hidden query text never appears in ledgers, final artifacts or commits (hashes only); sealed plaintext is never given to subagents; user encryption/decryption steps are hard stops (Keychain entry `atlassian-round5-sealed` via `-pass stdin` pipe when the user authorizes it).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; push/merge only on the user's instruction; never bare `git stash`.
- Decisions go to review thread 2 (https://chatgpt.com/c/6ac7eb56-eed8-83e8-a55e-a4b67e3088de); the user is stopped only for completion reports and hard stops.
- Review cap (spec §5.3): plan reviews pass at P0 0; P1s are applied in the next version without re-review.

## Name substitutions (applied to every Round 5 plan v8 step this plan imports)

| Round 5 token | Round 6 token |
|---|---|
| `round5` / `Round 5` / `ROUND = 5` / `--round 5` | `round6` / `Round 6` / `ROUND = 6` / `--round 6` |
| `round5-cache` (`$S`), `round5-work` (`$W`) | `round6-cache`, `round6-work` |
| `ATLASSIAN_DOCS_ROUND5_CACHE` | `ATLASSIAN_DOCS_ROUND6_CACHE` |
| `lexicon-r5`, `held_out-r5`/`negative-r5` | `lexicon-r6` (no new lexicon in Round 6), `held_out-r6`/`negative-r6` |
| `round5_seal`, `round5-sealed.json(.enc)`, `round5-final.json`, `search-tuning-round5.jsonl` | `round6_seal`, `round6-sealed.json(.enc)`, `round6-final.json`, `search-tuning-round6.jsonl` |
| `round5-*.md` frozen texts, `round5-method-safety.json`, `round5-counterexample-reference.json` | `round6-*.md`, `round6-method-safety.json`, `round6-counterexample-reference.json` |
| `ROUND5-WORKER-HANDSHAKE`, `round5_gate_checkpoint` | `ROUND6-WORKER-HANDSHAKE`, `round6_gate_checkpoint` |
| `python -m tests.benchmarks.round5_simulation` | `python -m tests.benchmarks.round6_simulation` |
| `round5_start_commit 56b4b0e` | `round6_start_commit 29f298f` (PR #2 merge; spec commits follow on main) |
| KU registry / `round5-known-unreachable.json` | **none** — `KNOWN_UNREACHABLE[6] = ()` (spec §4.2) |
| lexicon resolution (Round 5 Tasks 3–4) | **none** — the Round 5 lexicon and aliases are carried unchanged; only `carry` (Round 5 v1.12) runs at T |

## Review Focus

1. A whitespace-free identifier query whose tokens are all verb keys (`addComment`) or a canonical key must keep its recommendation (exact pin = R0 evidence) while the same words as a phrase (`add comment`) abstain — Task 2 `test_exact_pin_satisfies_r0`.
2. A query whose only content word appears in the top operation through an alias target (not literally) must still be recommended — Task 2 `test_r0_alias_target_counts_as_evidence`.
3. Turning all rules off (`scorer_rules(())`) and the R3 flag false must reproduce the Round 5 ranking and recommendation byte-for-byte on the fixture registry — Task 2 `test_rules_off_equals_round5_behavior`.
4. The memoized `GridEvaluator` and the production `search_operations` must agree on ranked keys **and** recommendation for every training query at sampled grid points (R0–R3 included) — Task 5 `test_grid_evaluator_usage_equivalence` + the pre-T `equivalence_mismatches` check.
5. A regression record relabeled answerable whose old `forbidden_top1` is one of its acceptable keys must not be simultaneously expected and forbidden — Task 6 `test_reconcile_moves_conflicting_forbidden_to_legacy`.

## File map

| File | Responsibility | Task |
|---|---|---|
| `tests/benchmarks/evaluator.py` | usage rows, gate metrics, training vector/accept/fallback order, schema (`regression_positive`, `promoted` origin, label fields), `KNOWN_UNREACHABLE[6]`, `ROUND6_EXTRA_KEYS`, `PRE_FREEZE…[6]`, freeze key set, hidden-rules test fix | 1, 2, 7 |
| `tools/atlassian_docs/intelligence/search.py` | `PRODUCT_NAME_TOKENS`, `concept_vocabulary`, `op_vocabulary`, `head_info`, `content_tokens`, `abstain_reason`, `apply_singular_collection`, `scorer_rules` switch, payload `abstain_reason` | 2 |
| `tools/atlassian_docs/intelligence/policy.py`, `data/search_ranking.json` | `singular_collection_tiebreak` ordering rule, `POLICY_VERSIONS["search"] = 5` | 2 |
| `tools/atlassian_docs/intelligence/search_log.py`, `tools/atlassian_docs/mcp/tools.py` | log fields, `server_session_id`, `call_seq`, selection records, top-10 keys | 3 |
| `tests/benchmarks/scorer_rule_cx.py` (new) | summary-as-query corpus, OFF/ON comparison, `scorer_rule_ok`, metadata | 4 |
| `tests/tune_search_ranking.py` | Round 6 pipeline: usage evaluation (production + memoized), metric vector selection, generalized proposer, `tuning_accept_r6`, log/verify | 5 |
| `tests/diag_search_queries.py` | usage metrics per set, gate block, `regression_positive`, hidden rows hashed | 5 |
| `tests/benchmarks/round6_labels.py` (new), `tests/benchmarks/round6-relabel-prompt.md` (new) | promotion, relabel input/validation/reconcile/apply, forbidden reconcile, catalog closure | 6 |
| `tests/benchmarks/round6_simulation.py` (new, copy of round5), `tests/benchmarks/round_seal.py` | Round 6 pre-T blockers, rehearsal phase, round 6 freeze keys | 7 |
| `docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md` | §18 / §8 amendment footnotes (docs only) | 3 |

## Plan rulings (to be confirmed by plan review)

- **PR-1 (proposer action source):** spec §4.2 makes every acceptance-violation record a proposer input. Alias actions still come from `alias_candidates.json`, whose generator (`alias_candidates_tool.candidates`) is run at T over **seed ∪ regression_positive** (both positive, answerable sets); `regression_negative` records have no principled target-derived candidate (they have no answer) and are logged under `no_actions`; a positive record's safety violation can have candidates. After the proposer, `no_actions` ids that no longer violate are reported under `resolved_after_no_actions` (diagnostic only). The Round 5 `R6`-class gate is replaced by "has candidate actions" (equivalent for seeds: a seed has a candidate word iff it is R6).
- **PR-2 (selector cost):** `scorer_rule_ok` costs two corpus passes per point, so the selector walks the accept pool in Round 3 conservative tie-break order and returns the first point with `scorer_rule_ok` — identical to "filter the pool by `scorer_rule_ok`, then tie-break" (the minimum of a filtered set) without evaluating every grid point.
- **PR-3 (rule switch):** R0–R2 have no policy flag (spec §3); the OFF/ON comparison uses an evaluation-only context switch `search.scorer_rules(enabled)` (module state, default all four on; never read from policy files, never set by the MCP server). R3 additionally requires `ordering_rules.singular_collection_tiebreak`.
- **PR-4 (KU and freeze keys):** with no registry in Round 6, the round-6 freeze entry records `known_unreachable_seeds: []` and omits `known_unreachable_registry_sha256`; `ROUND6_EXTRA_KEYS = ("scorer_rule_corpus_sha256", "scorer_rule_registry_fingerprint", "training_split_sha256")`.
- **PR-5 (pipeline selection by round):** the Round 5 functions (`tuning_accept`, `reachable_results`, `select_candidate`, `propose_aliases`) stay unchanged for the Round 5 simulation and its tests; Round 6 code paths are new functions selected by `TUNING_ROUND = ev.pending_round() or ROUND` (`>= 6`).
- **PR-6 (counterexample reference without a lexicon round):** defined in Task 7.
- **PR-7 (rule token stream) — adopted by plan review 1, now spec v1.6 §3.0:** every R0–R3 input (content tokens, `head_info`, product hints, the R3 number) is computed from `rule_unigrams(q)` = `tokenize_unigrams` of `q` with `{…}` placeholders removed; `method_intent`, scoring and ordering keep the raw unigrams. Measured on fixtures: without it the canonical key `jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment` abstained (`head_info` picked `key` from the placeholder).
- **PR-8 (fixture suite after relabel) — conditional (plan review 1 P0-4):** defined in Task 5; a relabel that makes a historical r0 fixture `forbidden` key an acceptable answer is a conflict → `STOP_FOR_AMENDMENT` (Task 10 Step 4).

---

### Task 1 (H18): Usage-metric layer and benchmark schema in the evaluator

**Files:**
- Modify: `tests/benchmarks/evaluator.py` (constants block near line 7–12, `check_schema` 26–53, new functions after `evaluate` ~line 99, `KNOWN_UNREACHABLE` 195, `freeze_key_set` 287)
- Modify: `tests/benchmarks/test_evaluator.py` (`TestSealIntegrity.test_hidden_plaintext_machine_rules` ~line 223; new classes appended)

**Interfaces:**
- Produces: `ev.WRITE_METHODS`, `ev.REGRESSION_POSITIVE`, `ev.TRAINING_SECTIONS`, `ev.usage_row(rec, ranked, recommended) -> dict`, `ev.usage_rows(records, usage_fn) -> list[dict]` (`usage_fn(query) -> (ranked_keys, recommended_or_None)`), `ev.gate_metrics(held_rows, neg_rows) -> dict` (`{"counts": {...}, "checks": {...}, "pass": bool}`), `ev.training_vector(seed_rows, rp_rows, rn_rows) -> dict`, `ev.accept_vector(m) -> bool`, `ev.FALLBACK_ORDER`, `ev.fallback_key(m) -> tuple` (smaller is better), `ev.violation(row, section) -> bool`, `ev.KNOWN_UNREACHABLE[6] == ()`, `ev.ROUND6_EXTRA_KEYS`, `ev.freeze_key_set(6)`.

- [ ] **Step 1: Write the failing tests** — append to `tests/benchmarks/test_evaluator.py`:

```python
class TestRound6UsageMetrics(unittest.TestCase):
    """Round 6 spec §4.1/§4.2: usage rows, exact-fraction gate metrics, training vector, accept, fallback order."""
    REC = {"id": "h-001", "query": "q", "expected_top1_any": ["jira-platform:GET:/a"], "forbidden_top1": []}
    NEG = {"id": "n-001", "query": "q", "expected_top1_any": [], "forbidden_top1": ["confluence:DELETE:/b"]}

    def test_usage_row_fields(self):
        r = ev.usage_row(self.REC, ["x", "jira-platform:GET:/a", "y"], "jira-platform:GET:/a")
        self.assertEqual((r["top3"], r["rec_correct"], r["wrong_write"], r["abstained"]), (True, True, False, False))
        w = ev.usage_row(self.NEG, ["confluence:DELETE:/b"], "confluence:DELETE:/b")
        self.assertEqual((w["wrong_write"], w["forbidden_recommended"], w["abstained"]), (True, True, False))
        a = ev.usage_row(self.NEG, ["confluence:DELETE:/b"], None)
        self.assertEqual((a["wrong_write"], a["forbidden_recommended"], a["abstained"]), (False, False, True))

    def _held(self, top3, rec, correct):
        rows = []
        for i in range(16):
            rows.append({"id": f"h-{i:03d}", "top1": None, "top1_correct": False, "top3": i < top3, "abstained": i >= rec, "rec_correct": i < correct,
                         "wrong_write": False, "forbidden_recommended": False, "recommended": None if i >= rec else "k"})
        return rows

    def _neg(self, abst, write=0):
        return [{"id": f"n-{i:03d}", "top1": None, "top1_correct": False, "top3": False, "abstained": i < abst, "rec_correct": False, "wrong_write": i >= abst and i - abst < write,
                 "forbidden_recommended": False, "recommended": None if i < abst else "k"} for i in range(8)]

    def test_gate_boundaries_exact_fractions(self):
        ok = ev.gate_metrics(self._held(15, 14, 13), self._neg(7))
        self.assertTrue(ok["pass"], ok)                                    # 15/16, 14/16, 13/14 ≥ 0.9, 0 writes, 7/8
        self.assertFalse(ev.gate_metrics(self._held(14, 14, 13), self._neg(7))["checks"]["reach"])
        self.assertFalse(ev.gate_metrics(self._held(15, 13, 13), self._neg(7))["checks"]["coverage"])
        self.assertFalse(ev.gate_metrics(self._held(15, 14, 12), self._neg(7))["checks"]["precision"])   # 12/14 < 0.9
        self.assertFalse(ev.gate_metrics(self._held(15, 14, 13), self._neg(6))["checks"]["abstention"])
        self.assertFalse(ev.gate_metrics(self._held(15, 14, 13), self._neg(7, write=1))["checks"]["write_safety"])
        self.assertFalse(ev.gate_metrics(self._held(15, 0, 0), self._neg(8))["checks"]["precision"])    # no recommendation -> fail

    def test_training_vector_and_accept(self):
        seed = [{"id": f"s-{i:03d}", "top3": True, "abstained": False, "rec_correct": True, "wrong_write": False,
                 "forbidden_recommended": False} for i in range(10)]
        rp = [{"id": "rn-001", "top3": True, "abstained": False, "rec_correct": True, "wrong_write": False, "forbidden_recommended": False}]
        rn = [{"id": f"rn-{i:03d}", "top3": False, "abstained": True, "rec_correct": False, "wrong_write": False,
               "forbidden_recommended": False} for i in range(2, 10)]
        m = ev.training_vector(seed, rp, rn)
        self.assertEqual({k: m[k] for k in ("wv", "fr", "sr3", "src", "srk", "rp3", "rpk", "nab")},
                         {"wv": 0, "fr": 0, "sr3": 10, "src": 10, "srk": 10, "rp3": 1, "rpk": 1, "nab": 8})
        self.assertTrue(ev.accept_vector(m))
        self.assertFalse(ev.accept_vector({**m, "wv": 1}))
        self.assertFalse(ev.accept_vector({**m, "rpk": 0}))
        self.assertFalse(ev.accept_vector({**m, "nab": 6}))                # 8·6 < 7·8

    def test_fallback_order_covers_accept_components_once(self):
        self.assertEqual([k for k, _ in ev.FALLBACK_ORDER], ["wv", "fr", "sr3", "srk", "src", "rp3", "rpk", "nab"])
        self.assertEqual(sorted(k for k, _ in ev.FALLBACK_ORDER), sorted(ev.ACCEPT_COMPONENTS))
        better = {"wv": 0, "fr": 0, "sr3": 5, "srk": 5, "src": 5, "rp3": 1, "rpk": 1, "nab": 3}
        self.assertLess(ev.fallback_key(better), ev.fallback_key({**better, "wv": 1}))
        self.assertLess(ev.fallback_key(better), ev.fallback_key({**better, "sr3": 4}))

    def test_violation_per_section(self):
        good = {"top3": True, "abstained": False, "rec_correct": True, "wrong_write": False, "forbidden_recommended": False}
        self.assertFalse(ev.violation(good, "seed"))
        self.assertTrue(ev.violation({**good, "abstained": True, "rec_correct": False}, "seed"))
        self.assertTrue(ev.violation({**good, "abstained": False}, "regression_negative"))
        self.assertFalse(ev.violation({**good, "abstained": True, "rec_correct": False}, "regression_negative"))


class TestRound6Schema(unittest.TestCase):
    def test_promoted_origin_and_label_fields(self):
        rec = {"id": "s-040", "query": "q", "expected_top1_any": ["k"], "forbidden_top1": [], "origin": "promoted-r5",
               "failure_classes": [], "ambiguous": False, "promoted_from": {"round": 5, "split": "held_out", "source_id": "h-001",
                                                                             "source_record_sha256": "a" * 64}}
        ev.check_schema("seed", [rec])
        pos = {**rec, "id": "rn-001", "no_answer": False, "forbidden_top1": []}
        ev.check_schema("regression_positive", [pos])
        with self.assertRaises(ValueError):
            ev.check_schema("regression_positive", [{**pos, "no_answer": True}])
        with self.assertRaises(ValueError):
            ev.check_schema("regression_positive", [{**pos, "forbidden_top1": ["k"]}])          # expected ∩ forbidden must be empty
        neg = {"id": "rn-002", "query": "q", "expected_top1_any": [], "forbidden_top1": ["k"], "origin": "seed-r0",
               "failure_classes": [], "ambiguous": False, "no_answer": True}
        ev.check_schema("regression_negative", [neg])
        with self.assertRaises(ValueError):
            ev.check_schema("regression_negative", [{**neg, "no_answer": False}])

    def test_round6_registry_and_keys(self):
        self.assertEqual(ev.KNOWN_UNREACHABLE[6], ())
        self.assertEqual(ev.known_unreachable(6), frozenset())
        keys = ev.freeze_key_set(6)
        self.assertTrue(set(ev.ROUND6_EXTRA_KEYS) <= keys)
        self.assertNotIn("known_unreachable_registry_sha256", keys)
        self.assertIn("known_unreachable_seeds", keys)
        self.assertIn("known_unreachable_registry_sha256", ev.freeze_key_set(5))                 # Round 5 unchanged
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m unittest tests.benchmarks.test_evaluator.TestRound6UsageMetrics tests.benchmarks.test_evaluator.TestRound6Schema -v`
Expected: ERROR `AttributeError: module 'tests.benchmarks.evaluator' has no attribute 'usage_row'` (and `ROUND6_EXTRA_KEYS` / `KeyError: 6`).

- [ ] **Step 3: Implement** in `tests/benchmarks/evaluator.py`:

(a) Replace the `_ORIGIN` regex and add constants right after `ACTIONABLE_SECTIONS`:

```python
_ORIGIN = re.compile(r"^(seed|held_out|negative|promoted)-r\d+$")
REGRESSION_POSITIVE = "regression_positive"                     # Round 6 spec §4.3: answerable relabeled regression records
TRAINING_SECTIONS = ("seed", REGRESSION_POSITIVE, "regression_negative")
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
```

(b) In `check_schema`, after the `ambiguous` check, add:

```python
        if "no_answer" in rec:
            if not isinstance(rec["no_answer"], bool):
                raise ValueError(f"{section_name}/{rid}: no_answer must be a bool")
            if section_name == REGRESSION_POSITIVE and rec["no_answer"]:
                raise ValueError(f"{section_name}/{rid}: regression_positive records must have no_answer false")
            if section_name == "regression_negative" and not rec["no_answer"]:
                raise ValueError(f"{section_name}/{rid}: regression_negative records must have no_answer true")
        if section_name == REGRESSION_POSITIVE and set(exp) & set(forb):
            raise ValueError(f"{section_name}/{rid}: expected_top1_any ∩ forbidden_top1 must be empty (spec §4.3)")
        for lf in ("legacy_forbidden_top1", "catalog_missing_keys"):
            if lf in rec and (not isinstance(rec[lf], list) or not all(isinstance(k, str) for k in rec[lf])):
                raise ValueError(f"{section_name}/{rid}: {lf} must be a list of keys")
```

(c) After `evaluate(...)` add the usage layer:

```python
# ---- Round 6 spec §4.1/§4.2: usage-grounded metrics -------------------------------------------------------------------
def usage_row(rec, ranked, recommended) -> dict:
    """One record judged as the agent sees it: top-3 reach, the recommendation, and its safety."""
    exp, forb = set(rec.get("expected_top1_any") or []), set(rec.get("forbidden_top1") or [])
    method = recommended.split(":")[1] if recommended else None
    wrong = recommended is not None and recommended not in exp
    return {"id": rec["id"], "top1": ranked[0] if ranked else None, "top1_correct": bool(ranked) and ranked[0] in exp,
            "top3": bool(exp & set(ranked[:3])),
            "recommended": recommended, "abstained": recommended is None,
            "rec_correct": recommended is not None and recommended in exp,
            "wrong_write": wrong and method in WRITE_METHODS,
            "forbidden_recommended": recommended is not None and recommended in forb}


def usage_rows(records, usage_fn) -> list:
    """usage_fn(query) -> (ranked_keys, recommended_key_or_None)."""
    out = []
    for rec in records:
        ranked, recommended = usage_fn(rec["query"])
        out.append(usage_row(rec, list(ranked), recommended))
    return out


def gate_metrics(held_rows, neg_rows) -> dict:
    """Round 6 spec §4.1: five exact-fraction checks on the hidden set (n = 16 / 8 in the spec; the fractions generalize)."""
    n_h, n_n = len(held_rows), len(neg_rows)
    reach = sum(r["top3"] for r in held_rows)
    cov = sum(not r["abstained"] for r in held_rows)
    correct = sum(r["rec_correct"] for r in held_rows)
    writes = sum(r["wrong_write"] for r in held_rows + neg_rows)
    abst = sum(r["abstained"] for r in neg_rows)
    checks = {"reach": 16 * reach >= 15 * n_h, "coverage": 16 * cov >= 14 * n_h,
              "precision": cov > 0 and 10 * correct >= 9 * cov, "write_safety": writes == 0, "abstention": 8 * abst >= 7 * n_n}
    counts = {"held_out": n_h, "negative": n_n, "reach3": reach, "recommended": cov, "correct": correct,
              "wrong_writes": writes, "abstained": abst, "top1_correct": sum(r["top1_correct"] for r in held_rows)}   # recorded only
    return {"counts": counts, "checks": checks, "pass": all(checks.values())}


ACCEPT_COMPONENTS = ("wv", "fr", "sr3", "src", "srk", "rp3", "rpk", "nab")
FALLBACK_ORDER = (("wv", -1), ("fr", -1), ("sr3", 1), ("srk", 1), ("src", 1), ("rp3", 1), ("rpk", 1), ("nab", 1))


def training_vector(seed_rows, rp_rows, rn_rows) -> dict:
    """Round 6 spec §4.2 metric vector m(point) over the three training sections."""
    every = list(seed_rows) + list(rp_rows) + list(rn_rows)
    return {"wv": sum(r["wrong_write"] for r in every), "fr": sum(r["forbidden_recommended"] for r in every),
            "sr3": sum(r["top3"] for r in seed_rows), "src": sum(not r["abstained"] for r in seed_rows),
            "srk": sum(r["rec_correct"] for r in seed_rows), "rp3": sum(r["top3"] for r in rp_rows),
            "rpk": sum(r["rec_correct"] for r in rp_rows), "nab": sum(r["abstained"] for r in rn_rows),
            "n_seed": len(seed_rows), "n_rp": len(rp_rows), "n_rn": len(rn_rows)}


def accept_vector(m) -> bool:
    """spec §4.2 accept(m), exact integer comparisons."""
    return (m["wv"] == 0 and m["fr"] == 0 and 10 * m["sr3"] >= 9 * m["n_seed"] and 10 * m["src"] >= 9 * m["n_seed"]
            and 10 * m["srk"] >= 9 * m["src"] and m["rp3"] == m["n_rp"] and m["rpk"] == m["n_rp"] and 8 * m["nab"] >= 7 * m["n_rn"])


def fallback_key(m) -> tuple:
    """spec §4.2 lexicographic fallback: wv, fr minimal; sr3, srk, src, rp3, rpk, nab maximal (smaller tuple = better)."""
    return tuple(m[k] if sign < 0 else -m[k] for k, sign in FALLBACK_ORDER)


def violation(row, section) -> bool:
    """spec §4.2 proposer input: an acceptance-violation record of its section."""
    if row["wrong_write"] or row["forbidden_recommended"]:
        return True
    if section == "regression_negative":
        return not row["abstained"]
    return not row["top3"] or row["abstained"] or not row["rec_correct"]
```

(d) Replace `KNOWN_UNREACHABLE = {5: (...)}` with `KNOWN_UNREACHABLE = {5: ("s-004", "s-027", "s-039"), 6: ()}` and add after `ROUND5_EXTRA_KEYS`:

```python
ROUND6_EXTRA_KEYS = ("scorer_rule_corpus_sha256", "scorer_rule_registry_fingerprint", "training_split_sha256")   # Round 6 plan PR-4
```

(e) Replace the return line of `freeze_key_set`:

```python
    keys = set(_ROUND2_KEYS) | (set(ROUND3_EXTRA_KEYS) if round >= 3 else set()) | (set(ROUND4_EXTRA_KEYS) if round >= 4 else set()) \
        | (set(ROUND5_EXTRA_KEYS) if round >= 5 else set())
    if round >= 6:                                                   # Round 6 plan PR-4: no KU registry file; corpus/split keys
        keys = (keys - {"known_unreachable_registry_sha256"}) | set(ROUND6_EXTRA_KEYS)
    return keys
```

(f) Fix `TestSealIntegrity.test_hidden_plaintext_machine_rules` (Round 5 readiness lesson 3): pass the frozen inventory —

```python
        vm = json.loads((ROOT / "tools/atlassian_docs/intelligence/data/search_ranking.json").read_text(encoding="utf-8"))["verb_methods"]
        self.assertEqual(rs.machine_check({"held_out": self.b["held_out"], "negative": self.b["negative"]}, self.b, internal,
                                          round=rnd, verb_methods=vm), [])
```

(use the module's existing `ROOT`/`json` names; if the test module names the repo root differently, use that name).

- [ ] **Step 4: Run to verify they pass**

Run: `python -m unittest tests.benchmarks.test_evaluator -v 2>&1 | tail -3`
Expected: `OK` (skips as before).

- [ ] **Step 5: Commit**

```bash
git add tests/benchmarks/evaluator.py tests/benchmarks/test_evaluator.py
git commit -m "H18: Round 6 usage-metric layer (usage rows, exact-fraction gate, training vector/accept/fallback), regression_positive + promoted schema, KNOWN_UNREACHABLE[6]=(), round 6 freeze keys, hidden-rules test passes verb_methods

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2 (H19): Scorer rules R0–R3, `abstain_reason`, policy version 5, pending round 6

**Files:**
- Modify: `tools/atlassian_docs/intelligence/search.py` (imports line 2–7; new block after `method_intent` ~line 241; `search_operations` 332–390)
- Modify: `tools/atlassian_docs/intelligence/policy.py:14` (`POLICY_VERSIONS`), `:145` (`ORDERING_RULE_KEYS`)
- Modify: `tools/atlassian_docs/intelligence/data/search_ranking.json` (`ordering_rules`)
- Modify: `tests/benchmarks/evaluator.py` (`PRE_FREEZE_NONVERB_STRUCTURE_SHA256`)
- Create: `tests/fixtures/round5_search_golden.json` (captured **before** any edit, Step 1)
- Create: `tests/intelligence/test_scorer_rules.py`
- Modify: `tests/intelligence/test_policy.py`, `tests/test_diag_search_queries.py` (version/rule-key pins only)

**Interfaces:**
- Produces (module `search`): `rule_unigrams(query) -> tuple` (PR-7), `PRODUCT_NAME_TOKENS: frozenset`, `WRITE_METHODS`, `RULES = ("R0","R1","R2","R3")`, `scorer_rules(enabled)` (context manager), `enabled_rules() -> tuple`, `literal_path_tokens(path) -> tuple`, `op_vocabulary(op) -> frozenset`, `concept_vocabulary(state, noise) -> frozenset`, `content_tokens(unigrams, verb_methods) -> tuple`, `head_info(unigrams, verb_methods, concepts) -> dict | None`, `covered(token, vocab, aliases) -> bool`, `abstain_reason(*, allowed, top_op, pinned, unigrams, rp, pol, concepts) -> str | None`, `singular_collection_order(cands, number, group_key) -> list`, `order_candidates(cands, rules, allowed, preferred, number) -> list` where a candidate is the tuple `(final, op, signals, method)`.
- Payload: `abstain_reason` added; `actionable = method_intent_consistent ∧ abstain_reason is None`; `recommended_operation = results[0].key if actionable and results else None`; `results` identical to the rules-off ordering except R3 pair swaps.
- Consumed by Task 5 (`GridEvaluator` must call `order_candidates` and `abstain_reason`), Task 4 (`scorer_rules`).

- [ ] **Step 1: Capture the Round 5 golden BEFORE editing any file**

```bash
python - <<'EOF'
import json, pathlib
from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import search
bench = json.loads(pathlib.Path("tests/benchmarks/search_queries.json").read_text(encoding="utf-8"))
extra = ["create issue", "add comment", "addComment", "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment", "delete",
         "delete something", "delete xyzzy", "create", "jira delete", "get something", "delete board", "update issue user",
         "get issue user", "update issue sprint", "create page jira", "delete id", "get data", "get user", "get page", "get pages",
         "get attachment", "get attachments", "create board", "list sprints", "delete attachment"]
queries = sorted(set([r["query"] for s in ("seed", "regression_negative") for r in bench[s]] + extra))
st = make_state("jira-platform", "jira-software", "confluence")
out = {}
for q in queries:
    p = search.search_operations(st, q, limit=10)
    if "results" in p:
        out[q] = {"keys": [r["key"] for r in p["results"]], "scores": [r["score"] for r in p["results"]],
                  "actionable": p["actionable"], "recommended": p["recommended_operation"]}
pathlib.Path("tests/fixtures/round5_search_golden.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
print(len(out))
EOF
```

Expected: prints the number of captured queries (> 60). `git diff --stat` shows only the new file.

- [ ] **Step 2: Write the failing tests** — create `tests/intelligence/test_scorer_rules.py`:

```python
"""Round 6 spec §3 / §8: R0–R3, abstain_reason precedence, results invariance, rules-off == Round 5 (golden)."""
import json
import pathlib
import unittest
from unittest import mock

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import policy, search

GOLDEN = json.loads((pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "round5_search_golden.json").read_text(encoding="utf-8"))
JP = "jira-platform:"


class TestScorerRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = make_state("jira-platform", "jira-software", "confluence")

    def s(self, q):
        return search.search_operations(self.st, q, limit=10)

    def test_product_name_tokens_from_sources(self):
        self.assertEqual(search.PRODUCT_NAME_TOKENS, frozenset({"confluence", "jira", "platform", "software"}))
        self.assertFalse({"board", "sprint", "epic", "backlog"} & search.PRODUCT_NAME_TOKENS)

    def test_head_info(self):
        vm = policy.ranking().verb_methods
        concepts = frozenset({"board", "owner", "issue", "page", "person"})
        h = search.head_info(search.tokenize_unigrams("remove this agile board"), vm, concepts)
        self.assertEqual(h, {"concept": "board", "original_token": "board", "number": "singular"})
        self.assertEqual(search.head_info(search.tokenize_unigrams("filter owner jira"), vm, concepts)["concept"], "owner")
        self.assertEqual(search.head_info(search.tokenize_unigrams("get pages"), vm, concepts)["number"], "plural")
        self.assertEqual(search.head_info(search.tokenize_unigrams("get issues"), vm, concepts)["number"], "plural")
        self.assertIsNone(search.head_info(search.tokenize_unigrams("delete xyzzy"), vm, concepts))
        self.assertIsNone(search.head_info(search.tokenize_unigrams("jira delete"), vm, concepts))

    def test_r0_table(self):
        for q in ("delete", "delete something", "delete xyzzy", "create", "jira delete", "get something", "add comment", "get data"):
            p = self.s(q)
            self.assertEqual((p["abstain_reason"], p["actionable"], p["recommended_operation"]), ("no_resource_evidence", False, None), q)
        for q in ("create issue", "get user", "create board", "delete attachment", "delete id"):
            p = self.s(q)
            self.assertIsNone(p["abstain_reason"], q); self.assertTrue(p["actionable"], q)
            self.assertEqual(p["recommended_operation"], p["results"][0]["key"], q)

    def test_exact_pin_satisfies_r0(self):
        for q in ("addComment", JP + "POST:/rest/api/3/issue/{issueIdOrKey}/comment"):
            p = self.s(q)
            self.assertTrue(p["exact_match"], q)
            self.assertEqual(p["recommended_operation"], JP + "POST:/rest/api/3/issue/{issueIdOrKey}/comment", q)
            self.assertIsNone(p["abstain_reason"], q)
        self.assertEqual(self.s("add comment")["abstain_reason"], "no_resource_evidence")      # same words, no pin

    def test_rule_unigrams_strip_placeholders(self):
        self.assertEqual(search.rule_unigrams("jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment"),
                         tuple(t for t in search.tokenize_unigrams("jira-platform:POST:/rest/api/3/issue/ /comment")))
        self.assertEqual(search.rule_unigrams("update issue user"), search.tokenize_unigrams("update issue user"))

    def test_r0_alias_target_counts_as_evidence(self):
        base = policy.aliases()
        ap = policy.AliasPolicy(base.alias_damping, base.rule_damping, {**dict(base.aliases), "ticket": ("issue",)}, base.rules, "x" * 64)
        with mock.patch.object(policy, "aliases", return_value=ap):
            p = self.s("create ticket")
        self.assertEqual(p["results"][0]["key"], JP + "POST:/rest/api/3/issue")
        self.assertIsNone(p["abstain_reason"]); self.assertEqual(p["recommended_operation"], JP + "POST:/rest/api/3/issue")

    def test_r1_write_only(self):
        for q in ("update issue user", "delete issue user"):
            self.assertEqual(self.s(q)["abstain_reason"], "uncovered_head_resource", q)
        self.assertIsNone(self.s("get issue user")["abstain_reason"])                          # GET: R1 not applied

    def test_r2_product_conflict(self):
        p = self.s("create page jira")
        self.assertEqual(p["results"][0]["source"], "confluence")
        self.assertEqual(p["abstain_reason"], "product_conflict")
        self.assertEqual(self.s("update issue sprint")["abstain_reason"], "product_conflict")   # sprint hints jira-software
        self.assertIsNone(self.s("create issue")["abstain_reason"])                              # no hint: not applied

    def test_precedence(self):
        self.assertEqual(self.s("filter owner jira")["abstain_reason"], "no_method_intent")      # no verb wins over everything
        self.assertEqual(self.s("jira delete")["abstain_reason"], "no_resource_evidence")        # R0 before R2
        rp, ap, vm = policy.ranking(), policy.aliases(), policy.ranking().verb_methods
        op = self.st.registry.sources["confluence"].operations_by_key["confluence:POST:/pages"]
        concepts = search.concept_vocabulary(self.st, rp.path_noise)
        un = search.tokenize_unigrams("create issue jira")                                       # R0, R2 and R1 all hold -> R0
        self.assertEqual(search.abstain_reason(allowed=frozenset({"POST"}), top_op=op, pinned=False, unigrams=un, rp=rp, pol=ap,
                                               concepts=concepts), "no_resource_evidence")
        un = search.tokenize_unigrams("create page issue jira")
        self.assertEqual(search.abstain_reason(allowed=frozenset({"POST"}), top_op=op, pinned=False, unigrams=un, rp=rp, pol=ap,
                                               concepts=concepts), "product_conflict")
        un = search.tokenize_unigrams("create page issue")
        self.assertEqual(search.abstain_reason(allowed=frozenset({"POST"}), top_op=op, pinned=False, unigrams=un, rp=rp, pol=ap,
                                               concepts=concepts), "uncovered_head_resource")
        self.assertEqual(search.abstain_reason(allowed=frozenset(), top_op=op, pinned=True, unigrams=un, rp=rp, pol=ap,
                                               concepts=concepts), "no_method_intent")

    def test_r3_singular_collection(self):
        self.assertEqual(self.s("get page")["results"][0]["key"], "confluence:GET:/pages/{id}")
        self.assertEqual([r["key"] for r in self.s("get attachment")["results"][:3]],
                         ["confluence:GET:/attachments/{id}", "confluence:GET:/attachments", JP + "GET:/rest/api/3/attachment/{id}"])
        self.assertEqual(self.s("get pages")["results"][0]["key"], "confluence:GET:/pages")      # 55 vs 45: no tie, no change
        with search.scorer_rules(("R0", "R1", "R2")):
            self.assertEqual(self.s("get page")["results"][0]["key"], "confluence:GET:/pages")

    def test_r3_flag_false_equals_inherited_order(self):
        raw = json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))
        raw["ordering_rules"]["singular_collection_tiebreak"] = False
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            pth = pathlib.Path(td) / "r.json"; pth.write_text(json.dumps(raw), encoding="utf-8")
            rp = policy.load_ranking(pth)
        with mock.patch.object(policy, "ranking", return_value=rp):
            for q, g in GOLDEN.items():
                self.assertEqual([r["key"] for r in self.s(q)["results"]], g["keys"], q)

    def test_rules_off_equals_round5_behavior(self):
        with search.scorer_rules(()):
            for q, g in GOLDEN.items():
                p = self.s(q)
                self.assertEqual(([r["key"] for r in p["results"]], [r["score"] for r in p["results"]], p["actionable"], p["recommended_operation"]),
                                 (g["keys"], g["scores"], g["actionable"], g["recommended"]), q)

    def test_abstention_never_changes_results(self):
        for q, g in GOLDEN.items():
            with search.scorer_rules(("R0", "R1", "R2")):                                         # R3 is the only ordering rule
                p = self.s(q)
            self.assertEqual([r["key"] for r in p["results"]], g["keys"], q)

    def test_r0_generic_token_diagnostics_recorded(self):
        """spec §8 (review 4 P1-2): weak-floor limits, recorded not gated. Values are the fixture registry's."""
        got = {q: self.s(q)["abstain_reason"] for q in ("delete id", "get data", "get user")}
        self.assertEqual(got, {"delete id": None, "get data": "no_resource_evidence", "get user": None})

    def test_policy_version_and_rule_key(self):
        self.assertEqual(policy.POLICY_VERSIONS["search"], 5)
        self.assertIn("singular_collection_tiebreak", policy.ORDERING_RULE_KEYS)
        self.assertTrue(policy.ranking().ordering_rules["singular_collection_tiebreak"])
        self.assertFalse(search.LEGACY_ORDERING_RULES["singular_collection_tiebreak"])
```

- [ ] **Step 3: Run to verify they fail**

Run: `python -m unittest tests.intelligence.test_scorer_rules -v 2>&1 | tail -5`
Expected: errors `AttributeError: module ... has no attribute 'PRODUCT_NAME_TOKENS'` / `KeyError: 'abstain_reason'`.

- [ ] **Step 4: Implement in `search.py`**

(a) Imports: add `import contextlib` next to `import re`.

(b) Insert after `method_intent(...)`:

```python
# ---- Round 6 spec §3: recommendation rules R0–R3 (boolean, no constants) ----------------------------------------------------
PRODUCT_NAME_TOKENS = frozenset().union(*(tokenize_unigrams(s) for s in sources.SOURCES))   # {confluence, jira, platform, software}
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RULES = ("R0", "R1", "R2", "R3")
_enabled = frozenset(RULES)


@contextlib.contextmanager
def scorer_rules(enabled):
    """Evaluation-only switch (Round 6 plan PR-3): the scorer-rule counterexample compares OFF (()) with ON (RULES). Never read
    from policy files and never set by the MCP server."""
    global _enabled
    prev, _enabled = _enabled, frozenset(enabled)
    try:
        yield
    finally:
        _enabled = prev


def enabled_rules() -> tuple:
    return tuple(r for r in RULES if r in _enabled)


def literal_path_tokens(path) -> tuple:
    """Unigrams of the literal (non-{param}) path segments, digits dropped, noise kept (order preserved, may repeat)."""
    out = []
    for seg in (path or "").split("/"):
        if not seg or (seg.startswith("{") and seg.endswith("}")):
            continue
        out += [t for t in tokenize_unigrams(seg) if not t.isdigit()]
    return tuple(out)


_VOCAB: dict = {}


def op_vocabulary(op) -> frozenset:
    """spec §3.2: operationId · path literal · summary · tag tokens (singular/plural forms)."""
    k = (op.source, op.key, op.operation_id, op.summary, tuple(op.tags))
    if k not in _VOCAB:
        toks = set(tokenize(op.operation_id)) | set(tokenize(op.summary)) | set(expand_token_forms(literal_path_tokens(op.path)))
        for t in op.tags:
            toks |= tokenize(t)
        _VOCAB[k] = frozenset(toks)
    return _VOCAB[k]


_CONCEPTS: dict = {}


def concept_vocabulary(state, noise) -> frozenset:
    """Catalog concept words (singular): path literal tokens minus path_noise, plus tag tokens (Round 3 concept_tokens)."""
    k = (state.registry.fingerprint, frozenset(noise))
    if k not in _CONCEPTS:
        out = set()
        for sr in state.registry.sources.values():
            for op in sr.operations:
                out |= {singular(t) for t in literal_path_tokens(op.path) if t not in noise}
                for tag in op.tags:
                    out |= {singular(t) for t in tokenize_unigrams(tag)}
        _CONCEPTS[k] = frozenset(out)
    return _CONCEPTS[k]


_PLACEHOLDER = re.compile(r"\{[^}]*\}")


def rule_unigrams(query) -> tuple:
    """Round 6 plan PR-7: rule inputs ignore {param} placeholders (a canonical key's parameter names are not resources)."""
    return tokenize_unigrams(_PLACEHOLDER.sub(" ", query or ""))


def content_tokens(unigrams, verb_methods) -> tuple:
    """spec §3.2a content(q): query unigrams minus verb keys minus product-name tokens (unknown words included)."""
    return tuple(t for t in unigrams if t not in verb_methods and t not in PRODUCT_NAME_TOKENS)


def head_info(unigrams, verb_methods, concepts):
    """spec §3.2: the LAST non-verb, non-product-name token whose singular is a catalog concept word."""
    head = None
    for t in unigrams:
        if t in verb_methods or t in PRODUCT_NAME_TOKENS:
            continue
        s = singular(t)
        if s in concepts:
            head = {"concept": s, "original_token": t,
                    "number": "singular" if t == s else "plural" if t in (s + "s", s + "es") else "unknown"}
    return head


def covered(token, vocab, aliases) -> bool:
    """spec §3.2a: token_forms(t) ∪ token_forms(direct alias targets of t's forms) meets the operation vocabulary."""
    forms = set(token_forms(token))
    for f in list(forms):
        for target in aliases.get(f, ()):
            forms |= token_forms(target)
    return bool(forms & vocab)


def abstain_reason(*, allowed, top_op, pinned, unigrams, rp, pol, concepts):
    """spec §3.1 precedence: no_method_intent > no_resource_evidence (R0) > product_conflict (R2) > uncovered_head_resource (R1).
    pinned: the top result is an exact key/operationId pin (counts as R0 evidence, spec §3.2a review 4 P1-1)."""
    if not allowed:
        return "no_method_intent"
    if top_op is None:
        return None
    vocab = op_vocabulary(top_op)
    if "R0" in _enabled and not pinned and not any(covered(t, vocab, pol.aliases) for t in content_tokens(unigrams, rp.verb_methods)):
        return "no_resource_evidence"
    if "R2" in _enabled:
        hinted = set()
        for t in unigrams:
            hinted |= rp.product_hints.get(t, frozenset())
        if hinted and top_op.source not in hinted:
            return "product_conflict"
    if "R1" in _enabled and top_op.method.upper() in WRITE_METHODS:
        h = head_info(unigrams, rp.verb_methods, concepts)
        if h is not None and not covered(h["concept"], vocab, pol.aliases):
            return "uncovered_head_resource"
    return None


def _collection_item(coll, item) -> bool:
    """item is coll + one '/{param}' segment, same source and method."""
    base = (coll.path or "").rstrip("/")
    rest = (item.path or "")[len(base):]
    return (coll.source == item.source and coll.method == item.method and (item.path or "").startswith(base + "/")
            and rest.count("/") == 1 and rest.startswith("/{") and rest.endswith("}"))


def _reorder_run(run, number):
    run = list(run)
    ops = [c[1] for c in run]
    pairs = sorted(((a, b) for a in ops for b in ops if _collection_item(a, b)), key=lambda p: (p[0].key, p[1].key))
    for coll, item in pairs:
        pref, other = (item, coll) if number == "singular" else (coll, item)
        keys = [c[1].key for c in run]
        pi, oi = keys.index(pref.key), keys.index(other.key)
        if pi > oi:
            run.insert(oi, run.pop(pi))
    return run


def singular_collection_order(cands, number, group_key) -> list:
    """spec §3.4 R3: inside each run of equal group_key (tier, exact final score), put the single item first for a singular head
    and the collection first for a plural head; nothing else moves."""
    if number not in ("singular", "plural"):
        return list(cands)
    out, i = list(cands), 0
    while i < len(out):
        j = i
        while j + 1 < len(out) and group_key(out[j + 1]) == group_key(out[i]):
            j += 1
        if j > i:
            out[i:j + 1] = _reorder_run(out[i:j + 1], number)
        i = j + 1
    return out


def order_candidates(cands, rules, allowed, preferred, number=None) -> list:
    """Production ordering, shared with the tuning GridEvaluator. cands: (final, op, signals, method)."""
    key = lambda c: _order_key(rules, allowed, preferred, c[0], c[3], c[1].deprecated, c[1].key)
    out = sorted(cands, key=key)
    if "R3" in _enabled and rules.get("singular_collection_tiebreak"):
        out = singular_collection_order(out, number, lambda c: (key(c)[0], c[0]))
    return out
```

(c) `LEGACY_ORDERING_RULES` gains `"singular_collection_tiebreak": False`.

(d) In `search_operations`: replace the line `candidates.sort(key=lambda c: _order_key(...))` with

```python
    concepts, run = concept_vocabulary(state, rp.path_noise), rule_unigrams(query)
    head = head_info(run, rp.verb_methods, concepts)
    candidates = order_candidates(candidates, rules, allowed, preferred, head["number"] if head else None)
```

and replace the two lines setting `payload["actionable"]` / `payload["recommended_operation"]` with

```python
    top_op = None
    if shown:
        top_op = state.registry.sources[shown[0]["source"]].operations_by_key[shown[0]["key"]]
    reason = abstain_reason(allowed=allowed, top_op=top_op, pinned=bool(shown) and shown[0]["key"] in pinned_keys,
                            unigrams=run, rp=rp, pol=pol, concepts=concepts)
    payload["abstain_reason"] = reason
    payload["actionable"] = payload["method_intent_consistent"] and reason is None          # Round 6 spec §3.1
    payload["recommended_operation"] = shown[0]["key"] if payload["actionable"] and shown else None
```

- [ ] **Step 5: Policy** — `policy.py:14` → `POLICY_VERSIONS = {"search": 5, "quirks": 1, "oas_transpiler": 1}   # Round 6 spec §3`; `policy.py:145` → `ORDERING_RULE_KEYS = ("intent_tier", "preferred_method_tiebreak", "terminal_alias_full_weight", "singular_collection_tiebreak")   # + Round 6 spec §3.4`; `search_ranking.json` `ordering_rules` gains `"singular_collection_tiebreak": true` (keep key order alphabetical as the file has it). Update any `test_policy.py` assertion that pins the old version or the old 3-key set, and the `policy_version` literal `4` in `tests/test_diag_search_queries.py::TestDiagScript::test_round3_report_fields_raw_effective_and_actionable_failures`, to the new values (no other test edits).

- [ ] **Step 6: Register the pending round (spec §5.1)** — compute the new non-verb structure hash and add it:

```bash
python -c "import json; from tests.benchmarks import evaluator as ev; print(ev.nonverb_structure_sha256(json.load(open('tools/atlassian_docs/intelligence/data/search_ranking.json'))))"
```

Append to `PRE_FREEZE_NONVERB_STRUCTURE_SHA256` the entry `6: "<printed sha>"   # Round 6 H19: ordering_rules.singular_collection_tiebreak (spec §3.4)` (`EVALUATION_CODE_FILES` is extended in Task 4, when `scorer_rule_cx.py` exists — `files_sha256` reads every listed file). Then `python -c "from tests.benchmarks import evaluator as ev; print(ev.pending_round())"` → `6`.

- [ ] **Step 7: Run to verify**

Run: `python -m unittest tests.intelligence.test_scorer_rules -v 2>&1 | tail -3` → `OK`.
Run: `python -m unittest discover -s tests -t . 2>&1 | tail -3` → `OK` (skips as before). A failure in an inherited fixture-ranking test caused by R3 (exact ties on a singular head) is investigated, not edited away: report it with the query and both orders before changing anything. An inherited assertion of `actionable == True` / a non-null `recommended_operation` for a query that spec §3/§8 now makes abstain (e.g. verb-only or evidence-free queries) is an intended change: update that assertion to the spec value and cite the rule (R0/R1/R2) in a comment; any other failure is investigated before editing.

- [ ] **Step 8: Commit**

```bash
git add tools/atlassian_docs/intelligence/search.py tools/atlassian_docs/intelligence/policy.py tools/atlassian_docs/intelligence/data/search_ranking.json \
        tests/benchmarks/evaluator.py tests/fixtures/round5_search_golden.json tests/intelligence/test_scorer_rules.py tests/intelligence/test_policy.py \
        tests/test_diag_search_queries.py
git commit -m "H19: Round 6 scorer rules R0–R3 + abstain_reason (precedence, exact pin = R0 evidence), singular_collection_tiebreak, POLICY_VERSIONS search 5, PRE_FREEZE[6] (pending round 6), Round 5 golden

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3 (H20): Search log fields, selection records, session correlation; Phase 2.5 spec footnotes

**Files:**
- Modify: `tools/atlassian_docs/intelligence/search_log.py`
- Modify: `tools/atlassian_docs/mcp/tools.py` (`_dispatch` 43–80)
- Modify: `tests/intelligence/test_search_log.py` (append; create the class if the file has another name — `grep -rln "search_log" tests/intelligence` finds it)
- Modify: `docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md` (§18 Discovery row and §8: one footnote each)

**Interfaces:**
- Produces: `search_log.SERVER_SESSION_ID: str` (uuid4 at import), `search_log.next_seq() -> int`, `search_log.record(payload, filters)` (search record now has `actionable`, `recommended_operation`, `abstain_reason`, `method_intent_consistent`, `top` = 10 keys, `server_session_id`, `call_seq`, `kind: "search"`), `search_log.record_selection(tool, key, fingerprint)`, `search_log.qualifying_records(lines, fingerprint) -> list`, `search_log.match_selections(lines) -> list[dict]`.

- [ ] **Step 1: Write the failing tests** (append):

```python
class TestRound6SearchLog(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.td = tempfile.TemporaryDirectory(); self.path = pathlib.Path(self.td.name) / "intelligence" / "search_log.jsonl"
        self.p1 = mock.patch.object(search_log, "log_path", return_value=self.path)
        self.p2 = mock.patch.dict(os.environ, {search_log.ENV_VAR: "1"})
        self.p1.start(); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop(); self.td.cleanup()

    def lines(self):
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]

    def test_search_record_fields(self):
        payload = {"query": "create issue", "results": [{"key": f"k{i}", "score": 1.0} for i in range(12)], "actionable": False,
                   "recommended_operation": None, "abstain_reason": "product_conflict", "method_intent_consistent": True,
                   "intelligence_fingerprint": "fp"}
        search_log.record(payload, {"limit": 10})
        rec = self.lines()[0]
        self.assertEqual(rec["kind"], "search")
        self.assertEqual([t["key"] for t in rec["top"]], [f"k{i}" for i in range(10)])
        for f in ("actionable", "recommended_operation", "abstain_reason", "method_intent_consistent", "server_session_id", "call_seq"):
            self.assertIn(f, rec)
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_selection_record_has_no_argument_values(self):
        search_log.record_selection("build_request_template", "jira-platform:POST:/rest/api/3/issue", "fp")
        rec = self.lines()[0]
        self.assertEqual(set(rec), {"ts", "kind", "tool", "key", "intelligence_fingerprint", "server_session_id", "call_seq"})
        self.assertEqual(rec["kind"], "selection")

    def test_call_seq_increases_and_session_constant(self):
        search_log.record({"query": "a", "results": []}, {}); search_log.record_selection("get_operation", "k", "fp")
        a, b = self.lines()
        self.assertLess(a["call_seq"], b["call_seq"]); self.assertEqual(a["server_session_id"], b["server_session_id"])

    def test_match_most_recent_result_containing_search(self):
        L = [{"kind": "search", "server_session_id": "s", "call_seq": 1, "top": [{"key": "A"}, {"key": "B"}], "recommended_operation": "A"},
             {"kind": "search", "server_session_id": "s", "call_seq": 2, "top": [{"key": "C"}], "recommended_operation": "C"},
             {"kind": "selection", "server_session_id": "s", "call_seq": 3, "key": "B"},
             {"kind": "selection", "server_session_id": "t", "call_seq": 4, "key": "B"},
             {"kind": "selection", "server_session_id": "s", "call_seq": 5, "key": "Z"}]
        m = search_log.match_selections(L)
        self.assertEqual([(x["selection_seq"], x["search_seq"], x["recommended_matches"]) for x in m], [(3, 1, False)])

    def test_qualifying_records_filter_by_fingerprint(self):
        L = [{"kind": "search", "intelligence_fingerprint": "old"}, {"kind": "search", "intelligence_fingerprint": "new"},
             {"kind": "selection", "intelligence_fingerprint": "new"}]
        self.assertEqual(len(search_log.qualifying_records(L, "new")), 1)


class TestDispatchSelectionLogging(unittest.TestCase):
    def test_get_operation_and_template_log_selection(self):
        from tools.atlassian_docs.mcp import tools as T
        mgr = mock.MagicMock()
        with mock.patch.object(T.insp, "get_operation", return_value={"intelligence_fingerprint": "fp"}), \
                mock.patch.object(T.request_template, "build_request_template", return_value={"intelligence_fingerprint": "fp"}), \
                mock.patch.object(T.search_log, "record_selection") as rs:
            T._dispatch(mgr, "get_operation", {"key": "K1"}); T._dispatch(mgr, "build_request_template", {"key": "K2", "values": {"x": 1}})
        self.assertEqual([c.args for c in rs.call_args_list], [("get_operation", "K1", "fp"), ("build_request_template", "K2", "fp")])
```

(use the test module's existing imports; add `import json, os` and `from unittest import mock` if missing.)

- [ ] **Step 2: Run to verify they fail** — `python -m unittest tests.intelligence.test_search_log -v 2>&1 | tail -5` → `AttributeError: ... 'record_selection'`.

- [ ] **Step 3: Implement `search_log.py`** — add after the constants:

```python
import itertools
import uuid

SERVER_SESSION_ID = str(uuid.uuid4())          # Round 6 spec §6: one per MCP server process
_SEQ = itertools.count(1)
TOP_KEYS = 10                                   # spec §6: selection matching needs the top-10 keys


def next_seq() -> int:
    return next(_SEQ)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

In `record`, set `"ts": _now()`, add `"kind": "search"`, change `[:3]` to `[:TOP_KEYS]`, and add the fields

```python
            "actionable": payload.get("actionable"), "recommended_operation": payload.get("recommended_operation"),
            "abstain_reason": payload.get("abstain_reason"), "method_intent_consistent": payload.get("method_intent_consistent"),
            "server_session_id": SERVER_SESSION_ID, "call_seq": next_seq(),
```

Append:

```python
def record_selection(tool: str, key, fingerprint) -> None:
    """spec §6: get_operation / build_request_template calls; never argument values or headers."""
    if not enabled():
        return
    try:
        rec = {"ts": _now(), "kind": "selection", "tool": tool, "key": key, "intelligence_fingerprint": fingerprint,
               "server_session_id": SERVER_SESSION_ID, "call_seq": next_seq()}
        _append(log_path(), json.dumps(rec, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        return


def qualifying_records(lines, fingerprint) -> list:
    """spec §6 qualifying window: search records of the currently adopted fingerprint only."""
    return [l for l in lines if l.get("kind", "search") == "search" and l.get("intelligence_fingerprint") == fingerprint]


def match_selections(lines) -> list:
    """spec §6 (review 2 P1-5): per selection, the most recent earlier search of the same server session whose logged top keys
    contain the selected key; unmatched selections are dropped."""
    out = []
    for i, sel in enumerate(lines):
        if sel.get("kind") != "selection":
            continue
        for s in reversed(lines[:i]):
            if (s.get("kind", "search") == "search" and s.get("server_session_id") == sel.get("server_session_id")
                    and s.get("call_seq", 0) < sel.get("call_seq", 0) and sel.get("key") in [t.get("key") for t in s.get("top", [])]):
                out.append({"selection_seq": sel["call_seq"], "search_seq": s["call_seq"], "key": sel["key"],
                            "recommended_matches": s.get("recommended_operation") == sel["key"]})
                break
    return out
```

- [ ] **Step 4: Implement dispatch logging** in `mcp/tools.py` — add `search_log` to the intelligence import line, and replace the `get_operation` / `build_request_template` branches:

```python
    if name == "get_operation":
        out = insp.get_operation(state, key=args.get("key"), source=args.get("source"), operation_id=args.get("operation_id"),
                                 include_full_description=args.get("include_full_description", False),
                                 include_response_schemas=args.get("include_response_schemas", False),
                                 resolve_schema_depth=args.get("resolve_schema_depth", 0))
        search_log.record_selection("get_operation", (out.get("operation") or {}).get("key") or args.get("key"),
                                    out.get("intelligence_fingerprint"))
        return out
```

and

```python
    if name == "build_request_template":
        out = request_template.build_request_template(state, args.get("key", ""), args.get("values"))
        search_log.record_selection("build_request_template", args.get("key", ""), out.get("intelligence_fingerprint"))
        return out
```

(If `get_operation`'s payload names the resolved key differently, read it from that field — check `insp.get_operation`'s return for the key field once and use it; the test mocks a payload without it, so the `args["key"]` fallback must stay.)

- [ ] **Step 5: Phase 2.5 spec footnotes** — under §18's Discovery row add: `> Round 6 amendment (2026-10-11, docs/superpowers/specs/2026-10-11-search-quality-round6-design.md §4.1): Discovery is judged by reach@3 ≥ 15/16, recommendation coverage ≥ 14/16, precision 10·correct ≥ 9·recommended, wrong write recommendations = 0, negative abstention ≥ 7/8.`; under §8 add: `> Round 6 amendment (§6): search records carry actionable / recommended_operation / abstain_reason / method_intent_consistent, top-10 keys, server_session_id and call_seq; get_operation and build_request_template write selection records; Runtime stability qualification counts only the adopted intelligence_fingerprint.`

- [ ] **Step 6: Run** — `python -m unittest discover -s tests -t . 2>&1 | tail -3` → `OK`.

- [ ] **Step 7: Commit**

```bash
git add tools/atlassian_docs/intelligence/search_log.py tools/atlassian_docs/mcp/tools.py tests/intelligence/test_search_log.py \
        docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md
git commit -m "H20: search log Round 6 fields (recommendation, abstain_reason, top-10, server_session_id, call_seq), selection records, result-containing matching, fingerprint-qualified window; Phase 2.5 §18/§8 amendment footnotes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4 (H21a): Scorer-rule counterexample module

**Files:**
- Create: `tests/benchmarks/scorer_rule_cx.py`
- Create: `tests/benchmarks/test_scorer_rule_cx.py`
- Modify: `tests/benchmarks/evaluator.py` (`EVALUATION_CODE_FILES` += `tests/benchmarks/scorer_rule_cx.py`; `TOOLING_FILES` += `tests/benchmarks/test_scorer_rule_cx.py`)

**Interfaces:**
- Produces: `cx6.corpus(state) -> list[{"query", "key"}]`, `cx6.corpus_metadata(state, corpus) -> {"registry_fingerprint", "operation_count", "corpus_sha256", "generator_sha256"}`, `cx6.usage_with(state, rp, point, alias_policy, enabled) -> fn(query) -> (ranked, recommended, abstain_reason)`, `cx6.compare(state, rp, point, alias_policy, corpus, *, bound_fingerprint, aliases_sha256) -> dict` with keys `registry_fingerprint, ranking_structure_sha256, verb_methods_sha256, aliases_sha256, constants, enabled_rules, corpus_sha256, losses, gains, eligible, losses_write, losses_read, loss_list, ok`, `cx6.scorer_rule_ok(losses, eligible) -> bool`, `cx6.per_rule_off(state, rp, point, alias_policy, corpus, **kw) -> {rule: result}` (diagnostic).

- [ ] **Step 1: Write the failing tests** — `tests/benchmarks/test_scorer_rule_cx.py`:

```python
import ast
import pathlib
import unittest

from tests.benchmarks import scorer_rule_cx as cx6
from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import policy, search


class TestScorerRuleCounterexample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = make_state("jira-platform", "jira-software", "confluence")
        cls.rp, cls.ap = policy.ranking(), policy.aliases()
        cls.corpus = cx6.corpus(cls.st)

    def test_ok_contract(self):
        self.assertFalse(cx6.scorer_rule_ok(0, 0))                    # eligible == 0 fails
        self.assertTrue(cx6.scorer_rule_ok(1, 100)); self.assertFalse(cx6.scorer_rule_ok(2, 100))
        self.assertTrue(cx6.scorer_rule_ok(0, 1))

    def test_corpus_deterministic_and_summary_based(self):
        self.assertEqual(self.corpus, cx6.corpus(self.st))
        self.assertTrue(all(c["query"].strip() for c in self.corpus))
        self.assertEqual(len(self.corpus), 60)                       # every fixture op has a summary (31 + 12 + 17)
        meta = cx6.corpus_metadata(self.st, self.corpus)
        self.assertEqual(meta["registry_fingerprint"], self.st.registry.fingerprint); self.assertEqual(meta["operation_count"], 60)

    def test_corpus_never_reads_benchmarks(self):
        src = pathlib.Path(cx6.__file__).read_text(encoding="utf-8")
        self.assertNotIn("search_queries", src); self.assertNotIn("held_out", src); self.assertNotIn("seed", src)
        names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
        self.assertNotIn("_BENCH", names)

    def test_binding_mismatch_fails(self):
        with self.assertRaises(ValueError):
            cx6.compare(self.st, self.rp, dict(self.rp.constants), self.ap, self.corpus, bound_fingerprint="0" * 64, aliases_sha256="a")

    def test_off_on_same_policy_and_metadata(self):
        r = cx6.compare(self.st, self.rp, dict(self.rp.constants), self.ap, self.corpus,
                        bound_fingerprint=self.st.registry.fingerprint, aliases_sha256="a" * 64)
        for k in ("registry_fingerprint", "ranking_structure_sha256", "verb_methods_sha256", "aliases_sha256", "constants",
                  "enabled_rules", "corpus_sha256", "losses", "gains", "eligible"):
            self.assertIn(k, r)
        self.assertEqual(r["enabled_rules"], list(search.RULES))
        self.assertEqual(r["ok"], cx6.scorer_rule_ok(r["losses"], r["eligible"]))
        self.assertEqual(r["losses"], r["losses_write"] + r["losses_read"])
        self.assertEqual(search.enabled_rules(), search.RULES)        # the switch is restored

    def test_verb_methods_sha_is_the_raw_inventory(self):
        import json
        raw = json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))
        r = cx6.compare(self.st, self.rp, dict(self.rp.constants), self.ap, self.corpus[:5],
                        bound_fingerprint=self.st.registry.fingerprint, aliases_sha256="a" * 64)
        self.assertEqual(r["verb_methods_sha256"], policy.canonical_sha256(raw["verb_methods"]))

    def test_loss_entries_carry_the_reason(self):
        r = cx6.compare(self.st, self.rp, dict(self.rp.constants), self.ap, [{"query": "Add comment", "key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment"}],
                        bound_fingerprint=self.st.registry.fingerprint, aliases_sha256="a" * 64)
        self.assertEqual(r["losses"], 1)                                  # spec §3.2a known loss: both tokens are verb keys
        self.assertEqual(set(r["loss_list"][0]), {"key", "off_recommended", "on_recommended", "on_abstain_reason", "off_rank", "on_rank"})
        self.assertEqual(r["loss_list"][0]["on_abstain_reason"], "no_resource_evidence")

    def test_per_rule_off_includes_r0(self):
        d = cx6.per_rule_off(self.st, self.rp, dict(self.rp.constants), self.ap, self.corpus,
                             bound_fingerprint=self.st.registry.fingerprint, aliases_sha256="a" * 64)
        self.assertEqual(sorted(d), ["R0", "R1", "R2", "R3"])
```

- [ ] **Step 2: Run to verify failure** — `python -m unittest tests.benchmarks.test_scorer_rule_cx -v 2>&1 | tail -3` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `tests/benchmarks/scorer_rule_cx.py`**

```python
"""Round 6 spec §3.5: scorer-rule counterexample. Summary-as-query corpus over the bound snapshot S; OFF (no rules) vs ON (R0–R3)
at the SAME constants and aliases; loss = OFF recommended the query's own operation and ON does not."""
import dataclasses
import hashlib
import pathlib
from types import MappingProxyType
from unittest import mock

from tests.benchmarks import evaluator as ev
from tools.atlassian_docs.intelligence import policy, search

GENERATOR = pathlib.Path(__file__)


def corpus(state) -> list:
    out = []
    for name in sorted(state.registry.sources):
        for op in sorted(state.registry.sources[name].operations, key=lambda o: o.key):
            if (op.summary or "").strip():
                out.append({"query": op.summary.strip(), "key": op.key})
    return out


def corpus_metadata(state, items) -> dict:
    return {"registry_fingerprint": state.registry.fingerprint, "operation_count": sum(len(sr.operations) for sr in state.registry.sources.values()),
            "corpus_sha256": ev.canonical_sha256(items), "generator_sha256": hashlib.sha256(GENERATOR.read_bytes()).hexdigest()}


def scorer_rule_ok(losses: int, eligible: int) -> bool:
    return eligible > 0 and 100 * losses <= eligible


def _rp_at(rp, point):
    return dataclasses.replace(rp, constants=MappingProxyType(dict(point)), sha256=policy.canonical_sha256({"tuning_point": dict(point)}))


def usage_with(state, rp, point, alias_policy, enabled):
    rpp = _rp_at(rp, point)

    def fn(q):
        with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=alias_policy), \
                search.scorer_rules(enabled):
            out = search.search_operations(state, q, limit=5)
        return [r["key"] for r in out.get("results", [])], out.get("recommended_operation"), out.get("abstain_reason")
    return fn


def _rank(keys, key):
    return keys.index(key) + 1 if key in keys else None


def _run(state, rp, point, alias_policy, items, on_rules):
    off, on = usage_with(state, rp, point, alias_policy, ()), usage_with(state, rp, point, alias_policy, on_rules)
    losses, gains, eligible, loss_list = 0, 0, 0, []
    for it in items:
        k_off, r_off, _ = off(it["query"]); k_on, r_on, why = on(it["query"])
        if r_off == it["key"]:
            eligible += 1
            if r_on != it["key"]:
                losses += 1
                loss_list.append({"key": it["key"], "off_recommended": r_off, "on_recommended": r_on, "on_abstain_reason": why,
                                  "off_rank": _rank(k_off, it["key"]), "on_rank": _rank(k_on, it["key"])})   # spec §3.5: key + reason
        elif r_on == it["key"]:
            gains += 1
    return losses, gains, eligible, loss_list


def compare(state, rp, point, alias_policy, items, *, bound_fingerprint, aliases_sha256, on_rules=search.RULES) -> dict:
    if state.registry.fingerprint != bound_fingerprint:
        raise ValueError(f"registry {state.registry.fingerprint} is not the bound Round 6 S {bound_fingerprint}")
    losses, gains, eligible, loss_list = _run(state, rp, point, alias_policy, items, on_rules)
    write = sum(1 for l in loss_list if l["key"].split(":")[1] in search.WRITE_METHODS)
    return {"registry_fingerprint": state.registry.fingerprint, "ranking_structure_sha256": rp.structure_sha256,
            "verb_methods_sha256": policy.canonical_sha256({k: list(v) for k, v in rp.verb_method_order.items()}),   # == sha of the raw verb_methods
            "aliases_sha256": aliases_sha256, "constants": dict(point), "enabled_rules": list(on_rules),
            "corpus_sha256": ev.canonical_sha256(items), "losses": losses, "gains": gains, "eligible": eligible,
            "losses_write": write, "losses_read": losses - write, "loss_list": loss_list, "ok": scorer_rule_ok(losses, eligible)}


def per_rule_off(state, rp, point, alias_policy, items, **kw) -> dict:
    """Diagnostic only (spec §3.5): ON minus one rule, per rule."""
    return {r: compare(state, rp, point, alias_policy, items, on_rules=tuple(x for x in search.RULES if x != r), **kw) for r in search.RULES}
```

`rp.verb_method_order` holds the `verb_methods` lists exactly as the policy file has them (`policy.load_ranking`: `order[k] = tuple(v)`), so the field is the canonical sha of `search_ranking.json["verb_methods"]`; `test_verb_methods_sha_is_the_raw_inventory` pins that.

- [ ] **Step 4: Run** — `python -m unittest tests.benchmarks.test_scorer_rule_cx -v 2>&1 | tail -3` → `OK`; full suite `OK`.

- [ ] **Step 5: Commit**

```bash
git add tests/benchmarks/scorer_rule_cx.py tests/benchmarks/test_scorer_rule_cx.py tests/benchmarks/evaluator.py
git commit -m "H21a: scorer-rule counterexample (summary-as-query corpus bound to S, OFF/ON at the same constants+aliases, eligible>0 ∧ 100·losses ≤ eligible, result metadata, per-rule OFF diagnostic)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5 (H21b): Round 6 tuning pipeline (metric vector, selector, generalized proposer, acceptance) and diag usage metrics

**Files:**
- Modify: `tests/tune_search_ranking.py` (constants block 33–48, `fixture_bench` ~186, `GridEvaluator` 170–206, new Round 6 section before `# ---- pipeline, adoption, verification CLI ----`, `PipelineResult` 486, `main` 567–656, `_finish` 659, `_verify` 796)
- Modify: `tests/benchmarks/alias_candidates_tool.py` (`candidates` 147: record sections)
- Modify: `tools/atlassian_docs/intelligence/policy.py:58` (`_SEED_ID`)
- Modify: `tests/diag_search_queries.py` (`_evaluate` 172–247)
- Test: `tests/test_tune_search_ranking.py`, `tests/test_diag_search_queries.py`, `tests/benchmarks/test_evaluator.py` (append only)

**Interfaces:**
- Consumes: Task 1 (`ev.usage_rows`, `ev.training_vector`, `ev.accept_vector`, `ev.fallback_key`, `ev.violation`, `ev.TRAINING_SECTIONS`), Task 2 (`search.order_candidates`, `search.abstain_reason`, `search.rule_unigrams`, `search.head_info`, `search.concept_vocabulary`), Task 4 (`cx6.compare`, `cx6.corpus`).
- Produces (module `tune`): `TUNING_ROUND`, `usage_fn(state)`, `evaluate_usage(bench, fn) -> {"seed": rows, "regression_positive": rows, "regression_negative": rows, "m": vector}`, `evaluate_usage_point(state, rp, point, bench, alias_policy)`, `evaluate_usage_fast(ge, rp, point, bench)`, `GridEvaluator.usage(query, rp, limit=5) -> (keys, recommended)`, `select_candidate_r6(results, baseline, grid, scorer_ok_fn) -> (point, info)`, `improved(before_row, after_row, section) -> bool`, `no_worse(m0, m1) -> bool`, `round_note_r6(word, sid, target)`, `apply_actions_r6(working, actions, sid)` (notes carry `round{TUNING_ROUND}`), `propose_aliases_r6(eval_fn, bench, base_raw, cands, budget, per_seed, fixture_fn) -> (working, patch)`, `tuning_accept_r6(m, fixture_final, cx, scorer, errors) -> bool`, `run_pipeline_r6(...)`, `run_pipeline_result_r6(...) -> PipelineResult` (new optional fields `metrics`, `scorer_rule`, `selection`), `classes_r6(bench, cands) -> dict`, `verify_replay_r6(...)`.
- Plan ruling **PR-8 (fixture suite after relabel):** `fixture_bench` keeps the inherited r0 suite (23 seed + 6 regression records with an `-r0` origin) wherever the relabel put a record (`regression_negative` or `regression_positive`), and judges the 6 r0 regression records with their **original** label: `expected_top1_any = []`, `forbidden_top1 = forbidden_top1 ∪ legacy_forbidden_top1`. The fixture contract (`23/23`, `6/6` raw) is therefore byte-for-byte the inherited one.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_tune_search_ranking.py`):

```python
def _row(i, **kw):
    base = {"id": i, "top1": None, "top1_correct": False, "top3": True, "recommended": "k", "abstained": False, "rec_correct": True,
            "wrong_write": False, "forbidden_recommended": False}
    base.update(kw); return base


def _usage(seed, rp=(), rn=()):
    out = {"seed": list(seed), "regression_positive": list(rp), "regression_negative": list(rn)}
    out["m"] = ev.training_vector(out["seed"], out["regression_positive"], out["regression_negative"])
    return out


class TestRound6Selector(unittest.TestCase):
    GRID = {k: [1, 2] for k in tune.CONSTANT_KEYS}
    BASE = {k: 1 for k in tune.CONSTANT_KEYS}

    def pts(self):
        return tune.grid_points(self.GRID)[:3]

    def test_pool_filtered_by_scorer_ok_then_tiebreak(self):
        a, b, c = self.pts()
        good = _usage([_row("s-001")] * 10, rn=[_row("rn-001", abstained=True, recommended=None, rec_correct=False)])["m"]
        results = [(a, good), (b, good), (c, good)]
        p, info = tune.select_candidate_r6(results, self.BASE, self.GRID, scorer_ok_fn=lambda pt: pt != a)
        self.assertEqual((p, info["mode"]), (c, "accept_pool"))           # a fails scorer_rule_ok; c's bonus tuple (1, 2) < b's (2, 1)

    def test_fallback_lexicographic(self):
        a, b, c = self.pts()
        m_bad_wv = {**_usage([_row("s-001")] * 10)["m"], "wv": 1}
        m_low_sr3 = {**_usage([_row("s-001")] * 10)["m"], "sr3": 8}
        p, info = tune.select_candidate_r6([(a, m_bad_wv), (b, m_low_sr3)], self.BASE, self.GRID, scorer_ok_fn=lambda pt: True)
        self.assertEqual((p, info["mode"]), (b, "fallback"))               # wv minimal wins before sr3


class TestRound6Proposer(unittest.TestCase):
    def test_improved_by_type(self):
        self.assertTrue(tune.improved(_row("s", top3=False, rec_correct=False), _row("s"), "seed"))
        self.assertTrue(tune.improved(_row("rn", abstained=False), _row("rn", abstained=True, recommended=None), "regression_negative"))
        self.assertTrue(tune.improved(_row("s", wrong_write=True), _row("s", top3=False, rec_correct=False), "seed"))   # safety violation removed
        self.assertFalse(tune.improved(_row("s", top3=False), _row("s", top3=False), "seed"))

    def test_no_worse(self):
        m = _usage([_row("s-001")] * 3)["m"]
        self.assertTrue(tune.no_worse(m, m))
        self.assertFalse(tune.no_worse(m, {**m, "wv": 1}))
        self.assertFalse(tune.no_worse(m, {**m, "srk": m["srk"] - 1}))

    def test_trial_rejected_when_other_metric_drops(self):
        bench = {"seed": [{"id": "s-001", "query": "q1"}, {"id": "s-002", "query": "q2"}], "regression_positive": [], "regression_negative": []}
        cands = {"zz": {"seed_ids": ["s-001"], "targets_by_seed": {"s-001": ["issue"]}, "allowed_targets": ["issue"], "catalog_df": 0}}
        base = {"version": 1, "alias_damping": 0.5, "rule_damping": 0.5, "aliases": {}, "rules": [], "notes": {}}

        def eval_fn(raw):
            fixed = "zz" in raw["aliases"]
            return _usage([_row("s-001", top3=fixed, rec_correct=fixed),
                           _row("s-002", abstained=fixed, recommended=None if fixed else "k", rec_correct=not fixed)])   # src drops
        working, patch = tune.propose_aliases_r6(eval_fn, bench, base, cands)
        self.assertEqual(working["aliases"], {}); self.assertEqual(patch["unresolved"], ["s-001"])

    def test_inputs_cover_every_violation_type(self):
        bench = {"seed": [{"id": "s-001", "query": "q"}], "regression_positive": [{"id": "rn-002", "query": "q"}],
                 "regression_negative": [{"id": "rn-003", "query": "q"}]}
        res = _usage([_row("s-001", abstained=True, recommended=None, rec_correct=False)], rp=[_row("rn-002", top3=False)],
                     rn=[_row("rn-003")])
        base = {"version": 1, "alias_damping": 0.5, "rule_damping": 0.5, "aliases": {}, "rules": [], "notes": {}}
        _, patch = tune.propose_aliases_r6(lambda raw: res, bench, base, {})
        self.assertEqual(sorted(patch["no_actions"]), ["rn-002", "rn-003", "s-001"])

    def test_tuning_accept_r6_requires_scorer_rule_ok(self):
        m = _usage([_row("s-001")] * 10)["m"]
        cx = {"ok": True}
        self.assertTrue(tune.tuning_accept_r6(m, [], cx, {"ok": True}, []))
        self.assertFalse(tune.tuning_accept_r6(m, [], cx, {"ok": False}, []))
        self.assertFalse(tune.tuning_accept_r6(m, ["s-001"], cx, {"ok": True}, []))
        self.assertFalse(tune.tuning_accept_r6(m, [], {"ok": False}, {"ok": True}, []))
        self.assertFalse(tune.tuning_accept_r6(m, [], cx, {"ok": True}, ["err"]))


class TestRound6NoteOrigin(unittest.TestCase):
    """plan review 2 P0-1: the same proposer run before T (ROUND 5, pending 6) and after T (ROUND 6) yields identical aliases."""
    BENCH = {"seed": [{"id": "s-001", "query": "q1"}], "regression_positive": [], "regression_negative": []}
    CANDS = {"zz": {"seed_ids": ["s-001"], "targets_by_seed": {"s-001": ["issue"]}, "allowed_targets": ["issue"], "catalog_df": 0}}
    BASE = {"version": 1, "alias_damping": 0.5, "rule_damping": 0.5, "aliases": {}, "rules": [], "notes": {}}

    def run_at(self, rnd):
        def eval_fn(raw):
            fixed = "zz" in raw["aliases"]
            return _usage([_row("s-001", top3=fixed, rec_correct=fixed)])
        with mock.patch.object(tune, "ROUND", rnd), mock.patch.object(tune, "TUNING_ROUND", 6):
            return tune.propose_aliases_r6(eval_fn, self.BENCH, self.BASE, self.CANDS)

    def test_pre_and_post_t_identical(self):
        (w5, p5), (w6, p6) = self.run_at(5), self.run_at(6)
        self.assertEqual(w5["notes"]["zz"]["origin"], "round6"); self.assertEqual(w5, w6)
        self.assertEqual(tune.result_sha256({"a": 1}, p5), tune.result_sha256({"a": 1}, p6))

    def test_round5_path_unchanged(self):
        with mock.patch.object(tune, "ROUND", 5):
            self.assertEqual(tune.apply_actions(self.BASE, [("zz", "issue")], "s-001")["notes"]["zz"]["origin"], "round5")


class TestRound6FixtureBench(unittest.TestCase):
    def test_r0_regression_records_keep_original_label(self):
        bench = json.loads(tune.BENCH_PATH.read_text(encoding="utf-8"))
        moved = copy.deepcopy(bench)
        r = next(x for x in moved["regression_negative"] if x["origin"].endswith("-r0"))
        moved["regression_negative"].remove(r)
        moved.setdefault("regression_positive", []).append({**r, "expected_top1_any": [r["forbidden_top1"][0]], "forbidden_top1": [],
                                                            "legacy_forbidden_top1": list(r["forbidden_top1"]), "no_answer": False})
        a, b = tune.fixture_bench(bench), tune.fixture_bench(moved)
        key = lambda recs: sorted((x["id"], tuple(x["forbidden_top1"]), tuple(x["expected_top1_any"])) for x in recs)
        self.assertEqual(key(a["regression_negative"]), key(b["regression_negative"]))


class TestGridEvaluatorUsageEquivalence(unittest.TestCase):
    def test_grid_evaluator_usage_equivalence(self):
        st = tune.fixture_state(); rp = policy.ranking(); ap = policy.aliases()
        golden = json.loads((tune.ROOT / "tests/fixtures/round5_search_golden.json").read_text(encoding="utf-8"))
        queries = [q for q in golden if " " in q.strip()]
        ge = tune.GridEvaluator(st, queries, ap, rp.ordering_rules["terminal_alias_full_weight"])
        for p in tune.grid_points(rp.tuning_grid)[::max(1, len(tune.grid_points(rp.tuning_grid)) // 5)] + [dict(rp.baseline)]:
            rpp = tune.ranking_with(rp, p)
            with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=ap):
                for q in queries:
                    o = tune.search_operations(st, q, limit=5)
                    self.assertEqual(ge.usage(q, rpp), ([r["key"] for r in o["results"]], o["recommended_operation"]), (p, q))
```

(the module already imports `copy`, `json`, `mock`, `policy`, `ev`/`tune`; add any that are missing.)

- [ ] **Step 2: Run to verify failure** — `python -m unittest tests.test_tune_search_ranking -v 2>&1 | tail -4` → `AttributeError: module 'tests.tune_search_ranking' has no attribute 'select_candidate_r6'`.

- [ ] **Step 3: Implement — candidates and notes**

`policy.py:58` → `_SEED_ID = re.compile(r"(s|rn)-\d{3}")               # always fullmatch; Round 6: regression_positive ids (rn-) may own a proposer alias`.

`alias_candidates_tool.candidates`: replace `for rec in sorted(bench["seed"], key=lambda r: r["id"]):` with

```python
    records = bench["seed"] + (bench.get("regression_positive") or [] if round >= 6 else [])     # Round 6 plan PR-1
    for rec in sorted(records, key=lambda r: r["id"]):
```

- [ ] **Step 4: Implement — Round 6 evaluation and ordering parity in `tune_search_ranking.py`**

(a) After `LOG_PATH = ROOT / LOG_REL` add `TUNING_ROUND = ev.pending_round() or ROUND                       # Round 6 plan PR-5`.

(b) Replace `fixture_bench`:

```python
def fixture_bench(bench) -> dict:
    """The r0 fixture suite (spec v1.14 AC-06a). Round 6 plan PR-8: r0 regression records are found wherever the relabel put them
    and keep their original label (no expected key; forbidden = active ∪ legacy)."""
    from tests.benchmarks.round6_labels import fixture_label_conflicts
    if fixture_label_conflicts(bench):                                  # plan review 1 P0-4: PR-8 only holds conflict-free
        raise SystemExit(f"error: relabel conflicts with the historical r0 fixture labels {fixture_label_conflicts(bench)} (STOP_FOR_AMENDMENT)")
    reg = [r for s in ("regression_negative", "regression_positive") for r in bench.get(s) or [] if r["origin"].endswith("-r0")]
    out = {"seed": [r for r in bench["seed"] if r["origin"].endswith("-r0")],
           "regression_negative": sorted(({**r, "expected_top1_any": [], "forbidden_top1": sorted(set(r["forbidden_top1"]) | set(r.get("legacy_forbidden_top1") or []))}
                                          for r in reg), key=lambda r: r["id"])}
    if (len(out["seed"]), len(out["regression_negative"])) != FIXTURE_COUNTS:
        raise SystemExit(f"error: r0 fixture suite must have {FIXTURE_COUNTS} records, got "
                         f"{(len(out['seed']), len(out['regression_negative']))}")
    return out
```

(c) Make `GridEvaluator` reproduce the production ordering and recommendation. Replace the body of `ranked` and add `_ordered` / `usage`:

```python
    def _ordered(self, query, rp):
        """Production ordering (search.order_candidates, R3 included) and the rule inputs, for a whitespace query."""
        unigrams, exp_all, _joined = self.meta[query]
        assert rp.ordering_rules["terminal_alias_full_weight"] == self.terminal_full, "GridEvaluator built for a different terminal_alias_full_weight"
        intent = self.S.method_intent(unigrams, rp.verb_methods); verbs, allowed = intent
        rules = self.S.ordering_rules_for(rp.ordering_rules, False)                                  # whitespace query: never an identifier query
        preferred = rp.verb_method_order[verbs[0]][0] if verbs else None
        cands = []
        for entry, op, lexical in self.rows[query]:
            structural, _ = self.S._structural_signals(entry, unigrams, exp_all, rp, intent)
            final = max(lexical + structural, 0.0) * (self.S.DEPRECATED_FACTOR if op.deprecated else 1.0)
            if final == 0.0:
                continue
            cands.append((final, op, None, entry.method))
        run = self.S.rule_unigrams(query); concepts = self.S.concept_vocabulary(self.state, rp.path_noise)
        head = self.S.head_info(run, rp.verb_methods, concepts)
        cands = self.S.order_candidates(cands, rules, allowed, preferred, head["number"] if head else None)
        top = cands[0][1] if cands else None
        reason = self.S.abstain_reason(allowed=allowed, top_op=top, pinned=False, unigrams=run, rp=rp, pol=self.ap, concepts=concepts)
        return cands, allowed, top, reason

    def _fallback(self, query):
        return query not in self.rows or not any(ch.isspace() for ch in query.strip())

    def ranked(self, query, rp, limit=5):
        """(top keys, actionable) exactly as search_operations returns them (actionable includes the Round 6 abstain_reason)."""
        if self._fallback(query):
            with mock.patch.object(policy, "ranking", return_value=rp), mock.patch.object(policy, "aliases", return_value=self.ap):
                return _search_fn(self.state)(query)
        cands, allowed, _top, reason = self._ordered(query, rp)
        return [c[1].key for c in cands[:limit]], bool(allowed) and reason is None

    def usage(self, query, rp, limit=5):
        """(top keys, recommended_operation) exactly as search_operations returns them (Round 6 spec §3)."""
        if self._fallback(query):
            with mock.patch.object(policy, "ranking", return_value=rp), mock.patch.object(policy, "aliases", return_value=self.ap):
                return usage_fn(self.state)(query)
        cands, _allowed, top, reason = self._ordered(query, rp)
        return [c[1].key for c in cands[:limit]], (top.key if top is not None and reason is None else None)
```

`ranked` keeps its `(keys, actionable)` contract, so the inherited parity tests and the Round 5 functions keep working against the Round 6 production search.

(d) After `fixture_failures_fast` add:

```python
# ---- Round 6 spec §4.2: usage evaluation -----------------------------------------------------------------------------------
def usage_fn(state):
    def fn(q):
        out = search_operations(state, q, limit=5)
        return [r["key"] for r in out.get("results", [])], out.get("recommended_operation")
    return fn


def evaluate_usage(bench, fn) -> dict:
    out = {s: ev.usage_rows(bench.get(s) or [], fn) for s in ev.TRAINING_SECTIONS}
    out["m"] = ev.training_vector(out["seed"], out["regression_positive"], out["regression_negative"])
    return out


def evaluate_usage_point(state, rp, point, bench, alias_policy) -> dict:
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), \
            mock.patch.object(policy, "aliases", return_value=alias_policy):
        return evaluate_usage(bench, usage_fn(state))


def evaluate_usage_fast(ge, rp, point, bench) -> dict:
    rpp = ranking_with(rp, point)
    return evaluate_usage(bench, lambda q: ge.usage(q, rpp))
```

- [ ] **Step 5: Implement — selector, proposer, acceptance, pipeline** (new section before `# ---- pipeline, adoption, verification CLI ----`):

```python
# ---- Round 6 spec §4.2: selector, proposer, acceptance ---------------------------------------------------------------------
def _tiebreak(p, baseline, grid):
    return (tuple(p[k] for k in BONUS_KEYS), l1_index_distance(p, baseline, grid), sum(p[k] for k in MAGNITUDE_KEYS), tuple(p[k] for k in CONSTANT_KEYS))


def select_candidate_r6(results, baseline, grid, scorer_ok_fn):
    """results = [(point, m)]. Pool = accept(m) ∧ scorer_rule_ok(point, working aliases), conservative tie-break (walked in
    tie-break order, plan PR-2); empty pool -> spec §4.2 lexicographic fallback over all points, then the same tie-break."""
    if not results:
        raise ValueError("no results to select from")
    pool = sorted((p for p, m in results if ev.accept_vector(m)), key=lambda p: _tiebreak(p, baseline, grid))
    for p in pool:
        if scorer_ok_fn(p):
            return dict(p), {"mode": "accept_pool", "accept_points": len(pool)}
    best = min(ev.fallback_key(m) for _, m in results)
    fb = sorted((p for p, m in results if ev.fallback_key(m) == best), key=lambda p: _tiebreak(p, baseline, grid))
    return dict(fb[0]), {"mode": "fallback", "accept_points": len(pool), "fallback_key": list(best)}


def improved(before, after, section) -> bool:
    """spec §4.2 target improvement by record type."""
    if (before["wrong_write"] or before["forbidden_recommended"]) and not (after["wrong_write"] or after["forbidden_recommended"]):
        return True
    if section == "regression_negative":
        return not before["abstained"] and after["abstained"]
    return (not before["top3"] and after["top3"]) or (not before["rec_correct"] and after["rec_correct"])


def no_worse(m0, m1) -> bool:
    return m1["wv"] <= m0["wv"] and m1["fr"] <= m0["fr"] and all(m1[k] >= m0[k] for k in ("sr3", "src", "srk", "rp3", "rpk", "nab"))


def round_note_r6(word, sid, target) -> dict:
    """plan review 2 P0-1: the Round 6 note origin is TUNING_ROUND, never the module ROUND (which is 5 before T and 6 after)."""
    return {"origin": f"round{TUNING_ROUND}", "seed_query_id": sid, "candidate_word": word, "failure_classes": ["R6"],
            "evidence": f"alias {word} -> {target} for {sid} (frozen candidate, deterministic atomic-action proposer)"}


def apply_actions_r6(working, actions, sid):
    trial = copy.deepcopy(working)
    for word, target in actions:
        trial["aliases"][word] = [target]; trial["notes"][word] = round_note_r6(word, sid, target)
    return trial


def _find(res, section, rid):
    return next(r for r in res[section] if r["id"] == rid)


def propose_aliases_r6(eval_fn, bench, base_raw, cands, budget=BUDGET, per_seed=PER_SEED, fixture_fn=None):
    """spec §4.2: input = every acceptance-violation record of the three training sections (id order); actions = the frozen
    candidates of that record (plan PR-1); a trial is committed iff it improves its record, wv/fr do not rise, no other metric
    falls and the fixture suite stays green. Budgets inherited."""
    working = copy.deepcopy(base_raw)
    first = eval_fn(working)
    patch = {"resolved_by_prior_change": [], "no_actions": [], "unresolved": [], "fixture_fail": [], "trials": 0, "actions_by_seed": {}}
    targets = sorted(((s, r["id"]) for s in ev.TRAINING_SECTIONS for r in first[s] if ev.violation(r, s)), key=lambda t: t[1])
    accepted_n = 0
    for section, rid in targets:
        cur = eval_fn(working); row = _find(cur, section, rid)
        if not ev.violation(row, section):
            patch["resolved_by_prior_change"].append(rid); continue
        actions = atomic_actions(cands, rid, working)
        if not actions:
            patch["no_actions"].append(rid); continue
        found = None
        for combo in trial_order(actions):
            if len(combo) > per_seed or accepted_n + len(combo) > budget:
                continue
            trial = apply_actions_r6(working, combo, rid)
            patch["trials"] += 1
            new = eval_fn(trial)
            if not (improved(row, _find(new, section, rid), section) and no_worse(cur["m"], new["m"])):
                continue
            bad = list(fixture_fn(trial)) if fixture_fn is not None else []
            if bad:
                patch["fixture_fail"].append({"kind": "alias", "actions": [list(a) for a in combo], "seed_query_id": rid, "failing": bad}); continue
            found = (trial, combo); break
        if found is None:
            patch["unresolved"].append(rid); continue
        working, accepted_n = found[0], accepted_n + len(found[1])
        patch["actions_by_seed"][rid] = [list(a) for a in found[1]]
    if patch["no_actions"]:                                          # PR-1 diagnostic: later aliases may have fixed a no-action record
        final = eval_fn(working)
        still = {r["id"] for s in ev.TRAINING_SECTIONS for r in final[s] if ev.violation(r, s)}
        patch["resolved_after_no_actions"] = [i for i in patch["no_actions"] if i not in still]
    patch.update(alias_patch(base_raw, working))
    return working, patch


def tuning_accept_r6(m, fixture_final, cx, scorer, errors) -> bool:
    """spec §4.2 tuning_accept := accept(m) ∧ fixture ∧ alias counterexample ok ∧ scorer_rule_ok ∧ no validation errors."""
    return ev.accept_vector(m) and not fixture_final and (cx is None or cx["ok"]) and bool(scorer and scorer["ok"]) and not errors


def classes_r6(bench, cands) -> dict:
    """validate_alias_change input: seeds keep their bench classes; a regression_positive record owning a frozen candidate word
    is R6 by the generator's construction (alias_candidates_tool.candidates)."""
    out = {r["id"]: r["failure_classes"] for r in bench["seed"]}
    owners = {sid for c in cands.values() for sid in c["seed_ids"]}
    out.update({r["id"]: ["R6"] for r in bench.get("regression_positive") or [] if r["id"] in owners})
    return out


def run_pipeline_r6(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn, scorer_fn):
    """evaluate_fn(point, raw) -> usage dict; fixture_fn(point, raw) -> failing r0 ids; scorer_fn(point, raw) -> scorer-rule
    result. Constants once with the B aliases over the fixture-admissible grid, proposer once at the selected constants."""
    raw_results, excluded = [], []
    for i, point in enumerate(grid_points(grid)):
        if fixture_fn(point, aliases_raw):
            excluded.append(i); continue
        raw_results.append((point, evaluate_fn(point, aliases_raw)["m"]))
    if not raw_results:
        raise SystemExit("error: every constants grid point fails the r0 fixture suite (fixture_fail)")
    selected, info = select_candidate_r6(raw_results, baseline, grid, lambda p: scorer_fn(p, aliases_raw)["ok"])
    working, patch = propose_aliases_r6(lambda raw: evaluate_fn(selected, raw), bench, aliases_raw, cands_doc["candidates"],
                                        fixture_fn=lambda raw: fixture_fn(selected, raw))
    usage = evaluate_fn(selected, working)
    return raw_results, selected, info, working, patch, usage, {"constants": excluded, "final": list(fixture_fn(selected, working))}


def run_pipeline_result_r6(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn, scorer_fn, queries,
                           counterexample_fn=None) -> "PipelineResult":
    results, selected, info, working, patch, usage, fixture_fail = run_pipeline_r6(evaluate_fn, bench, aliases_raw, cands_doc, grid,
                                                                                    baseline, fixture_fn, scorer_fn)
    errors = validate_alias_change(aliases_raw, working, cands_doc["candidates"], queries, classes_r6(bench, cands_doc["candidates"]))
    cxr = counterexample_fn(selected, working) if counterexample_fn is not None else None
    if cxr is not None:
        errors = errors + list(cxr["validation_errors"])
    scorer = scorer_fn(selected, working)
    accept = tuning_accept_r6(usage["m"], fixture_fail["final"], cxr, scorer, errors)
    res = PipelineResult(selected, patch, errors, usage, {}, fixture_fail, accept, cxr, metrics=usage["m"], scorer_rule=scorer, selection=info)
    res.grid_results, res.working_aliases = results, working
    return res
```

Extend `PipelineResult` with `metrics: dict = None`, `scorer_rule: dict = None`, `selection: dict = None` (after `counterexample_result`). `queries` for Round 6 = `{r["id"]: r["query"] for s in ("seed", "regression_positive") for r in bench.get(s) or []}`.

- [ ] **Step 6: Implement — `main` / `_finish` / `_verify` dispatch.** In `main`'s `body(state)`, when `TUNING_ROUND >= 6` run instead:

```python
    def body6(state):
        from tests.benchmarks import scorer_rule_cx as cx6
        fp = state.registry.fingerprint
        if fp != seal.get("registry_fingerprint") or fp != cands_doc["generated_from"]["registry_fingerprint"]:
            raise SystemExit(f"error: registry fingerprint {fp} != round{ROUND}_seal / alias_candidates provenance; wrong snapshot?")
        frozen = ev.freeze_for(ROUND)
        corpus = cx6.corpus(state)
        if ev.canonical_sha256(corpus) != frozen.get("scorer_rule_corpus_sha256") or fp != frozen.get("scorer_rule_registry_fingerprint"):
            raise SystemExit("error: scorer-rule corpus / registry differs from round_freeze (spec §3.5 binding)")
        b_sha = policy.canonical_sha256(aliases_raw)
        queries = [r["query"] for s in ev.TRAINING_SECTIONS for r in bench.get(s) or []]
        fx_state, fx_bench = fixture_state(), fixture_bench(bench)
        tf = rp.ordering_rules["terminal_alias_full_weight"]
        ge = GridEvaluator(state, queries, _alias_policy(aliases_raw), tf)
        ge_fx = GridEvaluator(fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]], _alias_policy(aliases_raw), tf)
        shas = {}
        raw_sha = lambda raw: shas.setdefault(id(raw), policy.canonical_sha256(raw))
        evaluate_fn = lambda point, raw: evaluate_usage_fast(ge, rp, point, bench) if raw_sha(raw) == b_sha else evaluate_usage_point(state, rp, point, bench, _alias_policy(raw))
        fixture_fn = lambda point, raw: fixture_failures_fast(ge_fx, rp, point, fx_bench) if raw_sha(raw) == b_sha else fixture_failures(fx_state, rp, point, fx_bench, _alias_policy(raw))
        scorer_fn = lambda point, raw: cx6.compare(state, rp, point, _alias_policy(raw), corpus, bound_fingerprint=fp, aliases_sha256=raw_sha(raw))
        t0 = time.perf_counter()
        res = run_pipeline_result_r6(evaluate_fn, bench, aliases_raw, cands_doc, rp.tuning_grid, dict(rp.baseline), fixture_fn, scorer_fn,
                                     {r["id"]: r["query"] for s in ("seed", "regression_positive") for r in bench.get(s) or []},
                                     counterexample_fn=final_counterexample_fn(state, rp, aliases_raw))
        slow, fast = evaluate_usage_point(state, rp, res.selected_point, bench, _alias_policy(aliases_raw)), evaluate_usage_fast(ge, rp, res.selected_point, bench)
        if slow != fast:
            raise SystemExit("error: memoized grid evaluator disagrees with search_operations at the selected point")
        if res.validation_errors:
            raise SystemExit("\n".join(f"VIOLATION {v}" for v in res.validation_errors))
        return fp, res, time.perf_counter() - t0
```

and dispatch `if TUNING_ROUND >= 6:` → `fp, res, grid_runtime = _with_state(cache, body6)`; `return _finish6(args, rp, fp, res, baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench), grid_runtime)`, where

```python
def _finish6(args, rp, fp, res, base_sha, grid_runtime) -> int:
    effects = plan_effects(args.dry_run, res.tuning_accept)
    m, fx = res.metrics, res.fixture_result
    pos_fail = [i for i in fx["final"] if i.startswith("s-")]; neg_fail = [i for i in fx["final"] if i.startswith("rn-")]
    line = {"run_id": str(uuid.uuid4()), "run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": _git("rev-parse", "HEAD").strip(), "round": ROUND, "registry_fingerprint": fp, "baseline_sha256": base_sha,
            "events": list(EVENTS), "constants_selected": res.selected_point, "selection": res.selection,
            "grid_size": len(res.grid_results) + len(fx["constants"]), "grid_runtime_s": round(grid_runtime, 1), "fixture_fail": fx,
            "passing_combos": sum(1 for _, mm in res.grid_results if ev.accept_vector(mm)),
            "aliases_proposed": res.proposed_actions, "metrics": m, "scorer_rule": res.scorer_rule,
            "fixture_positive": f"{FIXTURE_COUNTS[0] - len(pos_fail)}/{FIXTURE_COUNTS[0]}",
            "fixture_negative_raw": f"{FIXTURE_COUNTS[1] - len(neg_fail)}/{FIXTURE_COUNTS[1]}",
            "tuning_accept": res.tuning_accept, "tuning_failed": not res.tuning_accept, "counterexample": res.counterexample_result,
            "result_sha256": result_sha256(res.selected_point, res.proposed_actions),
            "dirty": dirty_paths(_git("status", "--porcelain", "--untracked-files=no")), "note": args.note,
            "ranking_structure_sha256": rp.structure_sha256, "baseline": dict(rp.baseline)}
    line["run_log_sha256"] = policy.canonical_sha256(log_core(line))
    line["status"], line["adopted"] = ("pending" if res.tuning_accept else "failed"), False
    if effects["write_constants"]:
        write_constants(res.selected_point)
        ALIASES_PATH.write_text(json.dumps(res.working_aliases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        policy.load_aliases(ALIASES_PATH)
    if effects["append_log"]:
        _write_log(_read_log() + [line])
    else:
        print("dry run: nothing written; would-be log line:"); print(json.dumps(line, ensure_ascii=False, sort_keys=True))
    print(json.dumps({k: line[k] for k in ("run_id", "constants_selected", "metrics", "passing_combos", "tuning_failed", "status", "result_sha256")}, ensure_ascii=False))
    return 0 if res.tuning_accept else 1
```

`_verify`: when `TUNING_ROUND >= 6`, the inner `body` uses

```python
def verify_replay_r6(eval_fn, bench, base_raw, cands, constants, expected_result_sha256, fixture_fn=None) -> list:
    _, patch = propose_aliases_r6(eval_fn, bench, base_raw, cands, fixture_fn=fixture_fn)
    got = result_sha256(constants, patch)
    return [] if got == expected_result_sha256 else [f"replay result_sha256 {got} != adopted {expected_result_sha256}"]
```

with `eval_fn = lambda raw: evaluate_usage_point(state, rp, consts, bench, _alias_policy(raw))`; everything else in `_verify` is unchanged.

- [ ] **Step 7: Diag usage metrics** — in `diag._evaluate`, change `fn` to also keep the recommendation, and after the per-set loop add the Round 6 blocks:

```python
    recommended = {}

    def fn(q):
        out = search_operations(state, q, limit=5)
        keys = [r["key"] for r in out.get("results", [])]
        ranked[q], recommended[q] = keys, out.get("recommended_operation")
        return keys, out["actionable"]
```

```python
    if rnd >= 6:                                                      # Round 6 spec §4.1/§4.2 (recorded per set; gate on hidden only)
        usage = {}
        for name in sets:
            if isinstance(sections.get(name), list):
                rows = ev.usage_rows(sections[name], lambda q: (ranked[q], recommended[q]))
                usage[name] = [{**r, "id": r["id"]} for r in rows] if name not in HIDDEN_SETS else \
                              [{k: v for k, v in r.items() if k != "top1"} for r in rows]
        report["usage"] = usage
        if {"held_out", "negative"} <= set(usage):
            report["gate"] = ev.gate_metrics(usage["held_out"], usage["negative"])
            g = report["gate"]
            print(f"[gate] reach {g['counts']['reach3']}/{g['counts']['held_out']} · coverage {g['counts']['recommended']}/{g['counts']['held_out']}"
                  f" · precision {g['counts']['correct']}/{g['counts']['recommended']} · wrong writes {g['counts']['wrong_writes']}"
                  f" · abstention {g['counts']['abstained']}/{g['counts']['negative']} -> {'PASS' if g['pass'] else 'FAIL'}")
```

Hidden rows carry ids and booleans only (no query text; `recommended` is an operation key, not query text). Add `"regression_positive"` to the diag's default section list wherever `regression_negative` is enumerated (it is a public section).

Test (add to `TestDiagScript` in `tests/test_diag_search_queries.py`; it reuses the class fixtures `good_bench`, `plain`, `cache`):

```python
    def test_round6_gate_block_and_hidden_rows(self):
        b = json.loads(self.good_bench.read_text(encoding="utf-8")); b["round6_seal"] = dict(b["round1_seal"])
        bp = self.tmp / "r6.json"; bp.write_text(json.dumps(b), encoding="utf-8")
        plain = {"held_out": [{**r, "origin": "held_out-r6"} for r in self.plain["held_out"]],
                 "negative": [{**r, "origin": "negative-r6"} for r in self.plain["negative"]]}
        pp = self.tmp / "plain6.json"; pp.write_text(json.dumps(plain), encoding="utf-8")
        with mock.patch("builtins.print"):
            code, rep = diag.run(["--cache-dir", str(self.cache), "--round", "6", "--bench-file", str(bp), "--bench", str(pp)])
        self.assertEqual(code, 0)
        self.assertEqual(set(rep["gate"]["checks"]), {"reach", "coverage", "precision", "write_safety", "abstention"})
        self.assertEqual(rep["gate"]["counts"]["held_out"], 2); self.assertEqual(rep["gate"]["counts"]["negative"], 1)
        assert_no_query_key(self, rep["usage"])
```

Also in Task 2's scope: `test_round3_report_fields_raw_effective_and_actionable_failures` pins `rep["policy_version"], 4` — Task 2 Step 5 changes that literal to `5` (the only edit to that test).

- [ ] **Step 8: Run** — `python -m unittest tests.test_tune_search_ranking tests.test_diag_search_queries -v 2>&1 | tail -3` → `OK`; full suite → `OK`.

- [ ] **Step 9: Commit**

```bash
git add tests/tune_search_ranking.py tests/benchmarks/alias_candidates_tool.py tools/atlassian_docs/intelligence/policy.py \
        tests/diag_search_queries.py tests/test_tune_search_ranking.py tests/test_diag_search_queries.py
git commit -m "H21b: Round 6 tuning pipeline — usage evaluation (production + memoized parity incl. R0–R3), metric-vector selector (accept∧scorer_rule_ok pool, lexicographic fallback), generalized proposer (all violation records, typed improvement, wv/fr no-rise, others no-drop), tuning_accept_r6, fixture suite keeps original r0 labels; diag usage metrics + gate block

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6 (H21c): Promotion and relabel tooling

**Files:**
- Create: `tests/benchmarks/round6_labels.py`, `tests/benchmarks/test_round6_labels.py`, `tests/benchmarks/round6-relabel-prompt.md`
- Modify: `tests/benchmarks/evaluator.py` (`TOOLING_FILES` += the three files above)

**Interfaces:**
- Produces (module `labels`): `PROMOTED_SEED_IDS = s-040…s-055`, `PROMOTED_NEG_IDS = rn-015…rn-022`, `promote(bench, r5_plain, r5_seal) -> (bench, payload)`, `promotion_identity(rec) -> dict`, `source_identity(src) -> dict`, `promotion_payload_sha256(bench) -> str`, `relabel_targets(bench) -> list[{"id","query"}]` (22), `render_relabel_input(targets, template_text) -> str`, `check_review(doc, ids, catalog_keys) -> list[str]`, `disagreements(a, b) -> list[id]`, `final_labels(a, b, c=None) -> dict`, `reconcile_forbidden(rec, acceptable) -> rec`, `apply_labels(bench, labels, migration) -> bench`, `catalog_closure(bench, catalog_keys) -> (bench, stop_ids)`, `training_identity(rec)`, `training_split_sha256(bench) -> str` (over `training_identity`), `fixture_label_conflicts(bench) -> list[id]`, `label_provenance_problems(bench) -> list[str]`; CLI `python -m tests.benchmarks.round6_labels {promote|relabel-input|check-review|apply|closure|verify}`.

- [ ] **Step 1: Write the failing tests** — `tests/benchmarks/test_round6_labels.py`:

```python
import copy
import unittest

from tests.benchmarks import evaluator as ev, round6_labels as L


def _bench():
    seed = [{"id": f"s-{i:03d}", "query": f"get thing {i}", "expected_top1_any": ["a:GET:/x"], "forbidden_top1": [], "origin": "seed-r1",
             "failure_classes": [], "ambiguous": False} for i in range(1, 40)]
    reg = [{"id": f"rn-{i:03d}", "query": f"remove page {i}", "expected_top1_any": [], "forbidden_top1": ["c:DELETE:/p/{id}", "c:GET:/p"],
            "origin": "seed-r1", "failure_classes": [], "ambiguous": False} for i in range(1, 15)]
    return {"seed": seed, "regression_negative": reg}


def _plain():
    held = [{"id": f"h-{i:03d}", "query": f"show alpha {i}", "expected_top1_any": ["a:GET:/y"], "forbidden_top1": [], "origin": "held_out-r5",
             "failure_classes": [], "ambiguous": False} for i in range(1, 17)]
    neg = [{"id": f"n-{i:03d}", "query": f"delete beta {i}", "expected_top1_any": [], "forbidden_top1": ["a:DELETE:/z"], "origin": "negative-r5",
            "failure_classes": [], "ambiguous": False} for i in range(1, 9)]
    return {"held_out": held, "negative": neg}


def _seal(plain):
    return {"held_out_sha256": ev.canonical_sha256(plain["held_out"]), "negative_sha256": ev.canonical_sha256(plain["negative"])}


class TestPromotion(unittest.TestCase):
    def test_ids_origin_provenance_identity(self):
        plain = _plain()
        b, payload = L.promote(_bench(), plain, _seal(plain))
        new_seed = [r for r in b["seed"] if r["origin"] == "promoted-r5"]
        self.assertEqual([r["id"] for r in new_seed], [f"s-{i:03d}" for i in range(40, 56)])
        self.assertEqual([r["promoted_from"]["source_id"] for r in new_seed], [f"h-{i:03d}" for i in range(1, 17)])
        new_rn = [r for r in b["regression_negative"] if r["origin"] == "promoted-r5"]
        self.assertEqual([r["id"] for r in new_rn], [f"rn-{i:03d}" for i in range(15, 23)])
        src = {r["id"]: r for r in plain["held_out"] + plain["negative"]}
        for r in new_seed + new_rn:
            self.assertEqual(r["promoted_from"]["source_record_sha256"], ev.canonical_sha256(src[r["promoted_from"]["source_id"]]))
            self.assertEqual(L.promotion_identity(r), L.source_identity(src[r["promoted_from"]["source_id"]]))
        self.assertEqual(payload["promotion_payload_sha256"], L.promotion_payload_sha256(b))

    def test_seal_mismatch_refused(self):
        plain = _plain(); bad = _seal(plain); bad["negative_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            L.promote(_bench(), plain, bad)

    def test_identity_survives_relabel_and_reconcile(self):
        plain = _plain(); b, _ = L.promote(_bench(), plain, _seal(plain))
        labels = {t["id"]: {"answerable": t["id"] == "rn-015", "acceptable_keys": ["a:DELETE:/z"] if t["id"] == "rn-015" else []}
                  for t in L.relabel_targets(b)}
        b2 = L.apply_labels(b, labels, {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels})
        r = next(x for x in b2["regression_positive"] if x["id"] == "rn-015")
        self.assertEqual(L.promotion_identity(r), L.source_identity(plain["negative"][0]))


class TestRelabel(unittest.TestCase):
    KEYS = {"c:DELETE:/p/{id}", "c:GET:/p", "a:DELETE:/z"}

    def test_targets_are_all_22(self):
        plain = _plain(); b, _ = L.promote(_bench(), plain, _seal(plain))
        t = L.relabel_targets(b)
        self.assertEqual(len(t), 22); self.assertEqual(set(t[0]), {"id", "query"})

    def test_review_schema(self):
        ids = ["rn-001", "rn-002"]
        ok = {"labels": {"rn-001": {"answerable": True, "acceptable_keys": ["c:DELETE:/p/{id}"]}, "rn-002": {"answerable": False, "acceptable_keys": []}}}
        self.assertEqual(L.check_review(ok, ids, self.KEYS), [])
        for bad in ({"labels": {"rn-001": {"answerable": True, "acceptable_keys": []}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": {"answerable": False, "acceptable_keys": ["c:GET:/p"]}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": {"answerable": True, "acceptable_keys": ["c:GET:/p", "c:DELETE:/p/{id}"]}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": {"answerable": True, "acceptable_keys": ["x:GET:/nope"]}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": ok["labels"]["rn-001"]}}):
            self.assertTrue(L.check_review(bad, ids, self.KEYS), bad)

    def test_set_comparison_and_adjudication(self):
        a = {"rn-001": {"answerable": True, "acceptable_keys": ["c:DELETE:/p/{id}", "c:GET:/p"]}, "rn-002": {"answerable": False, "acceptable_keys": []}}
        b = {"rn-001": {"answerable": True, "acceptable_keys": ["c:GET:/p", "c:DELETE:/p/{id}"]}, "rn-002": {"answerable": True, "acceptable_keys": ["c:GET:/p"]}}
        self.assertEqual(L.disagreements(a, b), ["rn-002"])
        with self.assertRaises(ValueError):
            L.final_labels(a, b)                                         # a disagreement needs the third review
        c = {"rn-002": {"answerable": False, "acceptable_keys": []}}
        self.assertFalse(L.final_labels(a, b, c)["rn-002"]["answerable"])

    def test_reconcile_moves_conflicting_forbidden_to_legacy(self):
        rec = {"id": "rn-001", "forbidden_top1": ["c:DELETE:/p/{id}", "c:GET:/p"]}
        out = L.reconcile_forbidden(rec, ["c:DELETE:/p/{id}"])
        self.assertEqual((out["forbidden_top1"], out["legacy_forbidden_top1"]), (["c:GET:/p"], ["c:DELETE:/p/{id}"]))

    def test_apply_moves_sections_and_passes_schema(self):
        b = _bench()
        labels = {r["id"]: {"answerable": r["id"] == "rn-001", "acceptable_keys": ["c:DELETE:/p/{id}"] if r["id"] == "rn-001" else []}
                  for r in b["regression_negative"]}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels}
        out = L.apply_labels(b, labels, mig)
        self.assertEqual([r["id"] for r in out["regression_positive"]], ["rn-001"])
        self.assertTrue(all(r["no_answer"] for r in out["regression_negative"]))
        ev.check_schema("regression_positive", out["regression_positive"]); ev.check_schema("regression_negative", out["regression_negative"])
        self.assertFalse(set(out["regression_positive"][0]["expected_top1_any"]) & set(out["regression_positive"][0]["forbidden_top1"]))

    def test_catalog_closure(self):
        b = _bench(); b["seed"][0]["expected_top1_any"] = ["a:GET:/x", "gone:GET:/old"]
        out, stop = L.catalog_closure(b, {"a:GET:/x"})
        self.assertEqual(out["seed"][0]["expected_top1_any"], ["a:GET:/x"]); self.assertEqual(out["seed"][0]["catalog_missing_keys"], ["gone:GET:/old"])
        self.assertEqual(stop, [])
        b2 = copy.deepcopy(b); b2["seed"][1]["expected_top1_any"] = ["gone:GET:/old"]
        _, stop2 = L.catalog_closure(b2, {"a:GET:/x"})
        self.assertEqual(stop2, ["s-002"])

    def test_split_sha_ignores_failure_classes_only(self):
        b = _bench(); base = L.training_split_sha256(b)
        b2 = copy.deepcopy(b); b2["seed"][0]["failure_classes"] = ["R6"]
        self.assertEqual(L.training_split_sha256(b2), base)
        for mutate in (lambda x: x["seed"][0].update(query="other"), lambda x: x["seed"][0].update(expected_top1_any=["z:GET:/q"]),
                       lambda x: x["regression_negative"][0].update(forbidden_top1=["z:GET:/q"]), lambda x: x["regression_negative"][0].update(no_answer=True),
                       lambda x: x["seed"].pop()):
            b3 = copy.deepcopy(b); mutate(b3)
            self.assertNotEqual(L.training_split_sha256(b3), base)

    def test_fixture_label_conflict_detected(self):
        b = _bench()
        for r in b["regression_negative"]:
            r["origin"] = "seed-r0"
        labels = {r["id"]: {"answerable": r["id"] == "rn-001", "acceptable_keys": ["c:DELETE:/p/{id}"] if r["id"] == "rn-001" else []}
                  for r in b["regression_negative"]}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels}
        self.assertEqual(L.fixture_label_conflicts(L.apply_labels(b, labels, mig)), ["rn-001"])
        labels["rn-001"] = {"answerable": True, "acceptable_keys": ["z:DELETE:/other"]}
        self.assertEqual(L.fixture_label_conflicts(L.apply_labels(b, labels, mig)), [])

    def test_label_provenance_required(self):
        b = _bench()
        labels = {r["id"]: {"answerable": False, "acceptable_keys": []} for r in b["regression_negative"]}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["a" * 64, "a" * 64], "adjudicated": False} for i in labels}   # equal outputs allowed
        out = L.apply_labels(b, labels, mig)
        self.assertEqual(L.label_provenance_problems(out), [])
        for bad in ({"reviewers": ["x", "x"], "review_output_sha256s": ["a" * 64, "b" * 64], "adjudicated": False},
                    {"reviewers": ["x", "y"], "review_output_sha256s": ["a" * 64, None], "adjudicated": False},
                    {"reviewers": ["x", "y", "z"], "review_output_sha256s": ["a" * 64] * 3, "adjudicated": False}):
            o2 = copy.deepcopy(out); o2["regression_negative"][0]["label_migration"] = bad
            self.assertTrue(L.label_provenance_problems(o2), bad)
        out["regression_negative"][0].pop("label_migration")
        self.assertTrue(L.label_provenance_problems(out))

    def test_promotion_payload_unchanged_by_relabel(self):
        plain = _plain(); b, payload = L.promote(_bench(), plain, _seal(plain))
        labels = {t["id"]: {"answerable": t["id"] == "rn-016", "acceptable_keys": ["a:DELETE:/z"] if t["id"] == "rn-016" else []} for t in L.relabel_targets(b)}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels}
        self.assertEqual(L.promotion_payload_sha256(L.apply_labels(b, labels, mig)), payload["promotion_payload_sha256"])

    def test_committed_benchmark_labels(self):
        """Once H22 commits the relabel, the real benchmark satisfies the provenance schema and has no PR-8 conflict."""
        import json
        bench = json.loads((L.ROOT / "tests/benchmarks/search_queries.json").read_text(encoding="utf-8"))
        if "regression_positive" not in bench:
            self.skipTest("relabel not committed yet (before H22)")
        self.assertEqual(L.label_provenance_problems(bench), []); self.assertEqual(L.fixture_label_conflicts(bench), [])

    def test_reviewer_input_has_queries_only(self):
        txt = L.render_relabel_input([{"id": "rn-001", "query": "remove page 1"}], "PROMPT\n{RECORDS}\n")
        self.assertIn('"rn-001"', txt); self.assertIn("remove page 1", txt)
        self.assertNotIn("forbidden", txt); self.assertNotIn("expected", txt)
```

- [ ] **Step 2: Run to verify failure** — `python -m unittest tests.benchmarks.test_round6_labels -v 2>&1 | tail -3` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `tests/benchmarks/round6_labels.py`**

```python
"""Round 6 spec §4.3: promotion of the Round 5 hidden set and catalog-fact relabel of the 22 regression records (controller tool).

    python -m tests.benchmarks.round6_labels promote --plain P --bench B --out B2 --ledger W/controller-events.jsonl
    python -m tests.benchmarks.round6_labels relabel-input --bench B --template tests/benchmarks/round6-relabel-prompt.md --out F
    python -m tests.benchmarks.round6_labels check-review --review R --bench B --catalog C
    python -m tests.benchmarks.round6_labels apply --bench B --review A --review B [--review C] --actors X Y [Z] --out B2
    python -m tests.benchmarks.round6_labels closure --bench B --catalog C --out B2
    python -m tests.benchmarks.round6_labels verify --bench B --plain P --catalog C
"""
import argparse, copy, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
from tests.benchmarks import evaluator as ev  # noqa: E402

PROMOTED_SEED_IDS = tuple(f"s-{i:03d}" for i in range(40, 56))
PROMOTED_NEG_IDS = tuple(f"rn-{i:03d}" for i in range(15, 23))
ORIGIN = "promoted-r5"
LABEL_FIELDS = ("no_answer", "label_migration", "legacy_forbidden_top1", "catalog_missing_keys")


def _sorted_union(*lists):
    return sorted(set().union(*(set(x or []) for x in lists)))


def source_identity(src) -> dict:
    d = {k: v for k, v in src.items() if k not in ("id", "origin")}
    d["forbidden_top1"] = _sorted_union(src.get("forbidden_top1"))
    d["expected_top1_any"] = _sorted_union(src.get("expected_top1_any"))
    return d


def promotion_identity(rec) -> dict:
    """spec §4.3: the record without {id, origin, promoted_from} and the relabel fields; relabel-set expected keys dropped, the
    reconciled forbidden list restored (active ∪ legacy), catalog-closure removals restored."""
    d = {k: v for k, v in rec.items() if k not in ("id", "origin", "promoted_from") + LABEL_FIELDS}
    d["forbidden_top1"] = _sorted_union(rec.get("forbidden_top1"), rec.get("legacy_forbidden_top1"))
    d["expected_top1_any"] = [] if "label_migration" in rec else _sorted_union(rec.get("expected_top1_any"), rec.get("catalog_missing_keys"))
    return d


def promote(bench, r5_plain, r5_seal):
    for split in ("held_out", "negative"):
        if ev.canonical_sha256(r5_plain[split]) != r5_seal[f"{split}_sha256"]:
            raise ValueError(f"Round 5 {split} plaintext does not match round5_seal")
    taken = {r["id"] for s in ("seed", "regression_negative", "regression_positive") for r in bench.get(s) or []}
    if taken & (set(PROMOTED_SEED_IDS) | set(PROMOTED_NEG_IDS)):
        raise ValueError(f"promotion ids already used: {sorted(taken & (set(PROMOTED_SEED_IDS) | set(PROMOTED_NEG_IDS)))}")
    out = copy.deepcopy(bench)
    for split, ids, section in (("held_out", PROMOTED_SEED_IDS, "seed"), ("negative", PROMOTED_NEG_IDS, "regression_negative")):
        src = sorted(r5_plain[split], key=lambda r: r["id"])
        if len(src) != len(ids):
            raise ValueError(f"{split}: expected {len(ids)} records, got {len(src)}")
        for new_id, r in zip(ids, src):
            rec = {**copy.deepcopy(r), "id": new_id, "origin": ORIGIN,
                   "promoted_from": {"round": 5, "split": split, "source_id": r["id"], "source_record_sha256": ev.canonical_sha256(r)}}
            if promotion_identity(rec) != source_identity(r):
                raise ValueError(f"{new_id}: promotion_identity differs from the Round 5 record")
            out[section].append(rec)
    return out, {"promotion_payload_sha256": promotion_payload_sha256(out)}


def promotion_payload_sha256(bench) -> str:
    recs = sorted((r for s in ("seed", "regression_negative", "regression_positive") for r in bench.get(s) or [] if r.get("origin") == ORIGIN),
                  key=lambda r: r["id"])
    return ev.canonical_sha256([{"id": r["id"], "promoted_from": r["promoted_from"], "identity": promotion_identity(r)} for r in recs])


def relabel_targets(bench) -> list:
    """spec §4.3: every existing regression_negative record + the 8 promoted negatives = 22; query only."""
    recs = [r for s in ("regression_negative", "regression_positive") for r in bench.get(s) or []]
    return [{"id": r["id"], "query": r["query"]} for r in sorted(recs, key=lambda r: r["id"])]


def render_relabel_input(targets, template_text) -> str:
    return template_text.replace("{RECORDS}", json.dumps(targets, ensure_ascii=False, indent=1))


def check_review(doc, ids, catalog_keys) -> list:
    out = []
    labels = (doc or {}).get("labels") if isinstance(doc, dict) else None
    if not isinstance(labels, dict) or set(labels) != set(ids):
        return [f"labels must cover exactly {sorted(ids)}"]
    for rid in sorted(ids):
        lab = labels[rid]
        if not isinstance(lab, dict) or set(lab) != {"answerable", "acceptable_keys"} or not isinstance(lab["answerable"], bool) \
                or not isinstance(lab["acceptable_keys"], list) or not all(isinstance(k, str) for k in lab["acceptable_keys"]):
            out.append(f"{rid}: label must be {{answerable: bool, acceptable_keys: [str]}}"); continue
        keys = lab["acceptable_keys"]
        if lab["answerable"] != bool(keys):
            out.append(f"{rid}: answerable must be true iff acceptable_keys is non-empty")
        if keys != sorted(set(keys)):
            out.append(f"{rid}: acceptable_keys must be sorted without duplicates")
        missing = [k for k in keys if k not in catalog_keys]
        if missing:
            out.append(f"{rid}: keys not in the Round 6 S catalog: {missing}")
    return out


def _same(x, y) -> bool:
    return x["answerable"] == y["answerable"] and set(x["acceptable_keys"]) == set(y["acceptable_keys"])


def disagreements(a, b) -> list:
    return sorted(i for i in a if not _same(a[i], b[i]))


def final_labels(a, b, c=None) -> dict:
    dis = disagreements(a, b)
    if dis and (c is None or set(c) < set(dis)):
        raise ValueError(f"disagreements need the third review: {dis}")
    return {i: (c[i] if i in dis else a[i]) for i in sorted(a)}


def reconcile_forbidden(rec, acceptable) -> dict:
    """spec §4.3 (review 3 P0-1): forbidden ∩ expected = ∅ — old forbidden keys that are acceptable move to legacy (provenance only)."""
    out = dict(rec)
    acc = set(acceptable)
    out["forbidden_top1"] = [k for k in rec.get("forbidden_top1") or [] if k not in acc]
    legacy = [k for k in rec.get("forbidden_top1") or [] if k in acc]
    if legacy:
        out["legacy_forbidden_top1"] = legacy
    return out


def apply_labels(bench, labels, migration) -> dict:
    out = copy.deepcopy(bench)
    pool = {r["id"]: r for s in ("regression_negative", "regression_positive") for r in out.get(s) or []}
    if set(pool) != set(labels):
        raise ValueError(f"labels must cover exactly the regression records: {sorted(set(pool) ^ set(labels))}")
    pos, neg = [], []
    for rid in sorted(pool):
        rec, lab = {k: v for k, v in pool[rid].items() if k not in LABEL_FIELDS}, labels[rid]
        rec["forbidden_top1"] = _sorted_union(pool[rid].get("forbidden_top1"), pool[rid].get("legacy_forbidden_top1"))
        rec["label_migration"] = migration[rid]
        if lab["answerable"]:
            rec = reconcile_forbidden(rec, lab["acceptable_keys"])
            rec.update(expected_top1_any=list(lab["acceptable_keys"]), no_answer=False); pos.append(rec)
        else:
            rec.update(expected_top1_any=[], no_answer=True); neg.append(rec)
    out["regression_positive"], out["regression_negative"] = pos, neg
    return out


def catalog_closure(bench, catalog_keys):
    out, stop = copy.deepcopy(bench), []
    for s in ("seed", "regression_positive"):
        for r in out.get(s) or []:
            missing = [k for k in r["expected_top1_any"] if k not in catalog_keys]
            if missing:
                r["catalog_missing_keys"] = missing
                r["expected_top1_any"] = [k for k in r["expected_top1_any"] if k in catalog_keys]
                if not r["expected_top1_any"]:
                    stop.append(r["id"])
    return out, sorted(stop)


def training_identity(rec) -> dict:
    """plan review 1 P0-2: the split identity ignores failure_classes (T's classify rewrites them)."""
    return {k: v for k, v in rec.items() if k != "failure_classes"}


def training_split_sha256(bench) -> str:
    return ev.canonical_sha256({s: [training_identity(r) for r in bench.get(s) or []] for s in ev.TRAINING_SECTIONS})


def fixture_label_conflicts(bench) -> list:
    """plan review 1 P0-4 (PR-8): r0 records relabeled answerable whose acceptable keys include a historical fixture forbidden key."""
    return sorted(r["id"] for r in bench.get("regression_positive") or [] if r["origin"].endswith("-r0")
                  and set(r["expected_top1_any"]) & (set(r.get("forbidden_top1") or []) | set(r.get("legacy_forbidden_top1") or [])))


_SHA = re.compile(r"[0-9a-f]{64}")


def label_provenance_problems(bench) -> list:
    """plan review 1 P1-5: once relabeled, every regression record carries no_answer and a well-formed label_migration."""
    out = []
    for s, want in (("regression_positive", False), ("regression_negative", True)):
        for r in bench.get(s) or []:
            if r.get("no_answer") is not want:
                out.append(f"{r['id']}: no_answer must be {want}")
            m = r.get("label_migration")
            if not (isinstance(m, dict) and set(m) == {"reviewers", "review_output_sha256s", "adjudicated"} and isinstance(m["adjudicated"], bool)
                    and isinstance(m["reviewers"], list) and len(m["reviewers"]) in (2, 3)
                    and all(isinstance(a, str) and a for a in m["reviewers"]) and len(set(m["reviewers"])) == len(m["reviewers"])
                    and isinstance(m["review_output_sha256s"], list) and len(m["review_output_sha256s"]) == len(m["reviewers"])
                    and all(isinstance(h, str) and _SHA.fullmatch(h) for h in m["review_output_sha256s"])
                    and (len(m["reviewers"]) == 3) == m["adjudicated"]):
                out.append(f"{r['id']}: label_migration must be {{reviewers[2|3], review_output_sha256s (same length), adjudicated (== 3 reviewers)}}")
    return out


def _read(p):
    return json.loads(pathlib.Path(p).expanduser().read_text(encoding="utf-8"))


def _write(p, doc):
    pathlib.Path(p).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _catalog_keys(path) -> set:
    doc = _read(path)
    return {r["key"] for r in (doc["operations"] if isinstance(doc, dict) else doc)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("promote", "relabel-input", "check-review", "apply", "closure", "verify"))
    ap.add_argument("--bench", required=True); ap.add_argument("--plain"); ap.add_argument("--out"); ap.add_argument("--catalog")
    ap.add_argument("--template"); ap.add_argument("--review", action="append", default=[]); ap.add_argument("--actors", nargs="*", default=[])
    ap.add_argument("--sealed-payload", default=None, help="promotion_payload_sha256 from the ledger (plan review 1 P1-1)")
    a = ap.parse_args(argv)
    bench = _read(a.bench)
    if a.cmd == "promote":
        out, payload = promote(bench, _read(a.plain), bench["round5_seal"])
        _write(a.out, out); print(json.dumps(payload)); return 0
    if a.cmd == "relabel-input":
        pathlib.Path(a.out).write_text(render_relabel_input(relabel_targets(bench), pathlib.Path(a.template).read_text(encoding="utf-8")), encoding="utf-8")
        print(json.dumps({"records": len(relabel_targets(bench)), "input_sha256": ev.file_sha256(pathlib.Path(a.out))})); return 0
    ids, keys = [t["id"] for t in relabel_targets(bench)], (_catalog_keys(a.catalog) if a.catalog else set())
    if a.cmd == "check-review":
        probs = check_review(_read(a.review[0]), ids, keys)
        print("\n".join(probs) or "ok"); return 1 if probs else 0
    if a.cmd == "apply":
        docs = [_read(r)["labels"] for r in a.review]
        labels = final_labels(docs[0], docs[1], docs[2] if len(docs) > 2 else None)
        dis = set(disagreements(docs[0], docs[1]))
        shas = [ev.file_sha256(pathlib.Path(r)) for r in a.review]
        mig = {i: {"reviewers": a.actors if i in dis else a.actors[:2], "review_output_sha256s": shas if i in dis else shas[:2],
                   "adjudicated": i in dis} for i in labels}
        out = apply_labels(bench, labels, mig); _write(a.out, out)
        print(json.dumps({"positive": len(out["regression_positive"]), "negative": len(out["regression_negative"]), "adjudicated": sorted(dis)})); return 0
    if a.cmd == "closure":
        out, stop = catalog_closure(bench, keys)
        if stop:
            print(json.dumps({"stop": stop})); return 3                                 # spec §4.3: label/catalog migration problem
        _write(a.out, out); print(json.dumps({"training_split_sha256": training_split_sha256(out)})); return 0
    probs = []                                                                          # verify
    plain = _read(a.plain) if a.plain else None
    for r in (x for s in ("seed", "regression_negative", "regression_positive") for x in bench.get(s) or [] if x.get("origin") == ORIGIN):
        src = next((s for s in (plain or {}).get(r["promoted_from"]["split"], []) if s["id"] == r["promoted_from"]["source_id"]), None)
        if plain is not None and (src is None or promotion_identity(r) != source_identity(src)):
            probs.append(f"{r['id']}: promotion_identity differs from its source")
    for r in bench.get("regression_positive") or []:
        if set(r["expected_top1_any"]) & set(r["forbidden_top1"]):
            probs.append(f"{r['id']}: forbidden ∩ expected")
    if a.sealed_payload is not None and promotion_payload_sha256(bench) != a.sealed_payload:
        probs.append("promotion_payload_sha256 differs from the sealed value")
    if bench.get("regression_positive") is not None:
        probs += label_provenance_problems(bench)
        probs += [f"{i}: PR-8 fixture label conflict (STOP_FOR_AMENDMENT)" for i in fixture_label_conflicts(bench)]
    print("\n".join(probs) or "ok"); return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Relabel prompt** — create `tests/benchmarks/round6-relabel-prompt.md`:

```markdown
You are labelling search queries against an API catalog. The attached file is the complete operation catalog (one operation per
line: key, method, path, operationId, summary, tags). For each record below decide only from the catalog whether some operation
answers the query as an action a developer would call.

Rules:
- Use only the attached catalog. Do not guess operations that are not in it.
- answerable = true when one or more catalog operations directly perform what the query asks; list every such key in
  acceptable_keys (exact catalog keys, sorted ascending, no duplicates).
- answerable = false when no catalog operation performs it; acceptable_keys = [].
- Reply with exactly one JSON object and nothing else:
  {"labels": {"<id>": {"answerable": true|false, "acceptable_keys": ["..."]}, ...}} covering every id below.

Records:
{RECORDS}
```

- [ ] **Step 5: Run** — `python -m unittest tests.benchmarks.test_round6_labels -v 2>&1 | tail -3` → `OK`; add the three files to `TOOLING_FILES`; full suite `OK`.

- [ ] **Step 6: Commit**

```bash
git add tests/benchmarks/round6_labels.py tests/benchmarks/test_round6_labels.py tests/benchmarks/round6-relabel-prompt.md tests/benchmarks/evaluator.py
git commit -m "H21c: promotion (s-040..055 / rn-015..022, promoted_from, sealed promotion_identity) and catalog-fact relabel tooling (dual review schema, set comparison, adjudication, forbidden→legacy reconcile, catalog closure, training split sha)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7 (H21d = `housekeeping_commit` candidate): `round6_simulation` (pre-T, H lifecycle, rehearsal), seal/freeze for round 6

**Files:**
- Create: `tests/benchmarks/round6_simulation.py` (from `round5_simulation.py`), `tests/benchmarks/test_round6_simulation.py` (from `test_round5_simulation.py`)
- Modify: `tests/benchmarks/round_seal.py` (`HIDDEN_RULES_R6`, `machine_check` no-answer rule, `freeze_entry` round ≥ 6 block, `_RULE_PATTERNS`)
- Modify: `tests/benchmarks/evaluator.py` (`TOOLING_FILES` += the two simulation files)
- Test: `tests/benchmarks/test_round_seal.py` (append)

**Interfaces:**
- Produces: `sim6.load_pre_t_evidence(work) -> (events, problems)`, `sim6.seed_rehearsal_work(real_work, temp_work) -> {path: sha}`, `sim6.pre_t_blockers_r6(result, event, equivalence, extra=()) -> list` (kinds `metric_threshold`, `training_split_mismatch`, `pre_t_evidence_missing`, `scorer_rule_violation`, `alias_validation_error`, `counterexample_loss`, `counterexample_uncovered_proposer`, `fixture_fail`, `equivalence_mismatch`, `tuning_accept_false`), `sim6.metric_violations(m) -> list[{"item","value","bound"}]`, `sim6.run_pre_t(cache, work) -> int`, `sim6.run_rehearsal(cache, work) -> int` (writes only inside a temp tree; appends `rehearsal_report` to `work/controller-events.jsonl`), `sim6.t_commands(cache, work, tree) -> list[list[str]]` (the exact T command sequence the controller also runs), `rs.HIDDEN_RULES_R6`.
- Plan ruling **PR-6 (counterexample reference in Round 6):** there is no lexicon resolution in Round 6, so `round6-counterexample-reference.json` binds the alias policy at the H final commit (`policy` = `search_aliases.json` at `housekeeping_commit`) with `inputs = {"aliases_h_sha256", "registry_fingerprint"}`; `INPUT_SHA256 = {}`; `counterexample_reference_problems` checks exactly those two inputs plus the internal-consistency hashes (`policy_canonical_sha256`, `canonical_policy_map(_sha256)`, `titles_sha256` over the Round 4 doc-title snapshot copied into `$W/inputs/round4/` as in Round 5).

- [ ] **Step 1: Copy and substitute**

```bash
cp tests/benchmarks/round5_simulation.py tests/benchmarks/round6_simulation.py
cp tests/benchmarks/test_round5_simulation.py tests/benchmarks/test_round6_simulation.py
python - <<'EOF'
import pathlib, re
for f in ("tests/benchmarks/round6_simulation.py", "tests/benchmarks/test_round6_simulation.py"):
    p = pathlib.Path(f); t = p.read_text(encoding="utf-8")
    for a, b in (("round5_simulation", "round6_simulation"), ("ROUND = 5", "ROUND = 6"), (".round5-sim", ".round6-sim"), ("round5-sim", "round6-sim"),
                 ("ROUND5-WORKER-HANDSHAKE", "ROUND6-WORKER-HANDSHAKE"), ("user_decision_round5", "user_decision_round6")):
        t = t.replace(a, b)
    p.write_text(t, encoding="utf-8")
EOF
grep -n "round5\|56b4b0e\|known_unreachable\|ku_" tests/benchmarks/round6_simulation.py tests/benchmarks/test_round6_simulation.py
```

Expected: the grep lists the remaining Round-5-specific lines; each is resolved in Steps 3–5 (none may remain except in comments that cite Round 5 history).

- [ ] **Step 2: Write the failing tests** (append to `tests/benchmarks/test_round6_simulation.py`; delete the copied tests that exercise `registry_blockers`, `approval_blockers`, the KU-aware `pre_t_verdict` and the Round 5 `INPUT_SHA256` table — they test removed Round 5 code):

```python
class TestRound6PreT(unittest.TestCase):
    M_OK = {"wv": 0, "fr": 0, "sr3": 55, "src": 55, "srk": 55, "rp3": 3, "rpk": 3, "nab": 19, "n_seed": 55, "n_rp": 3, "n_rn": 19}

    def _result(self, m, scorer_ok=True, errors=(), fixture_final=(), cx=None):
        r = types.SimpleNamespace(metrics=m, scorer_rule={"ok": scorer_ok, "losses": 0, "eligible": 600}, validation_errors=list(errors),
                                  fixture_result={"final": list(fixture_final), "constants": []}, counterexample_result=cx,
                                  tuning_accept=sim.tune.tuning_accept_r6(m, list(fixture_final), cx, {"ok": scorer_ok}, list(errors)))
        return r

    def test_metric_violations_name_item_value_bound(self):
        v = sim.metric_violations({**self.M_OK, "wv": 1, "srk": 40})
        self.assertEqual([x["item"] for x in v], ["wv", "srk"])
        self.assertEqual(v[0], {"item": "wv", "value": 1, "bound": "== 0"})

    def test_blockers(self):
        self.assertEqual(sim.pre_t_blockers_r6(self._result(self.M_OK), {"pass": True}, []), [])
        kinds = lambda r, eq=(): [b["kind"] for b in sim.pre_t_blockers_r6(r, {"pass": True}, list(eq))]
        self.assertEqual(kinds(self._result({**self.M_OK, "wv": 1})), ["metric_threshold"])
        self.assertEqual(kinds(self._result(self.M_OK, scorer_ok=False)), ["scorer_rule_violation"])
        self.assertEqual(kinds(self._result(self.M_OK, fixture_final=["s-001"])), ["fixture_fail"])
        self.assertEqual(kinds(self._result(self.M_OK), eq=[{"point": {}, "query": "q"}]), ["equivalence_mismatch"])

    def test_seeded_work_satisfies_pre_t_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            real, tmp = pathlib.Path(td) / "W", pathlib.Path(td) / "T"
            (real / "inputs/round4").mkdir(parents=True)
            (real / "aliases-h.json").write_text("{}", encoding="utf-8"); (real / "inputs/round4/doc-titles-snapshot.json").write_text("{}", encoding="utf-8")
            events = [{"event": "scorer_rule_corpus_pinned", "corpus_sha256": "c", "registry_fingerprint": "f"},
                      {"event": "relabel_applied", "training_split_sha256": "s"}, {"event": "promotion_sealed", "promotion_payload_sha256": "p"},
                      {"event": "other"}]
            (real / "controller-events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            self.assertEqual(sim.load_pre_t_evidence(tmp)[1] != [], True)                  # empty temp work: evidence missing
            sim.seed_rehearsal_work(real, tmp)
            got, probs = sim.load_pre_t_evidence(tmp)
            self.assertEqual(probs, []); self.assertEqual(got["relabel_applied"]["training_split_sha256"], "s")
            with open(real / "controller-events.jsonl", "a", encoding="utf-8") as fh:            # silent re-baseline of the split
                fh.write(json.dumps({"event": "relabel_applied", "training_split_sha256": "s2"}) + "\n")
            self.assertTrue(any("relabel_rerun_ruling" in x for x in sim.load_pre_t_evidence(real)[1]))
            with open(real / "controller-events.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"event": "relabel_rerun_ruling"}) + "\n" + json.dumps({"event": "relabel_applied", "training_split_sha256": "s3"}) + "\n")
            self.assertEqual(sum("relabel_rerun_ruling" in x for x in sim.load_pre_t_evidence(real)[1]), 1)   # only the unruled pair
            (real / "aliases-h.json").unlink()
            with self.assertRaises(SystemExit):
                sim.seed_rehearsal_work(real, pathlib.Path(td) / "T2")

    def test_rehearsal_never_writes_the_working_tree(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=sim.ROOT, capture_output=True, text=True).stdout
        with mock.patch.object(sim, "_run_in_tree", return_value=(0, "ok")) as run_in_tree:
            with tempfile.TemporaryDirectory() as td:
                code = sim.run_rehearsal(pathlib.Path(td) / "S", pathlib.Path(td) / "W", dry=True)
        self.assertEqual(code, 0)
        self.assertTrue(all(str(sim.ROOT) not in str(c.args[0]) for c in run_in_tree.call_args_list))   # every command ran in the temp tree
        self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=sim.ROOT, capture_output=True, text=True).stdout, before)
```

(add `import json, types, subprocess, tempfile, pathlib` and `from unittest import mock` if missing; `sim` is the module alias the copied test file already uses.)

Append to `tests/benchmarks/test_round_seal.py`:

```python
class TestRound6Seal(unittest.TestCase):
    def test_hidden_negatives_need_no_answer_true(self):
        self.assertEqual(rs.HIDDEN_RULES_R6[:len(rs.HIDDEN_RULES_R5)], rs.HIDDEN_RULES_R5)
        self.assertEqual(rs.HIDDEN_RULES_R6[-1], "no-answer")
        rec = {"id": "n-001", "query": "q", "expected_top1_any": [], "forbidden_top1": ["k"]}
        self.assertEqual(rs._no_answer_checks(rec), ["n-001: no-answer: hidden negative records must carry no_answer: true"])
        self.assertEqual(rs._no_answer_checks({**rec, "no_answer": True}), [])
```

- [ ] **Step 3: Implement the Round 6 pre-T** in `round6_simulation.py` — delete `registry_blockers`, `approval_blockers`, `pre_t_verdict`, `pre_t_event`; set `INPUT_SHA256 = {}` (PR-6); rewrite `counterexample_reference_problems` to check `inputs == {"aliases_h_sha256": <file sha of $W/aliases-h.json>, "registry_fingerprint": registry_fp}` plus the existing consistency hashes; replace `equivalence_mismatches`, `dry_run_pipeline`, `pre_t_blockers`, `run_pre_t` with:

```python
from tests import tune_search_ranking as tune  # noqa: E402  (module-level: tests use sim.tune)

BOUNDS = (("wv", "== 0"), ("fr", "== 0"), ("sr3", "10·sr3 ≥ 9·|seed|"), ("src", "10·src ≥ 9·|seed|"), ("srk", "10·srk ≥ 9·src"),
          ("rp3", "== |regression_positive|"), ("rpk", "== |regression_positive|"), ("nab", "8·nab ≥ 7·|regression_negative|"))


def metric_violations(m) -> list:
    ok = {"wv": m["wv"] == 0, "fr": m["fr"] == 0, "sr3": 10 * m["sr3"] >= 9 * m["n_seed"], "src": 10 * m["src"] >= 9 * m["n_seed"],
          "srk": 10 * m["srk"] >= 9 * m["src"], "rp3": m["rp3"] == m["n_rp"], "rpk": m["rpk"] == m["n_rp"], "nab": 8 * m["nab"] >= 7 * m["n_rn"]}
    return [{"item": k, "value": m[k], "bound": b} for k, b in BOUNDS if not ok[k]]


def equivalence_mismatches(state, rp, bench, ap, n=20, seed=20261011) -> list:
    """GridEvaluator.usage == search_operations (keys AND recommendation) on S and the fixture registry, sampled grid points + baseline."""
    import random
    from unittest import mock
    from tools.atlassian_docs.intelligence import policy, search
    pts = random.Random(seed).sample(tune.grid_points(rp.tuning_grid), n) + [dict(rp.baseline)]
    fx_state, fx_bench = tune.fixture_state(), tune.fixture_bench(bench)
    pairs = [(state, [r["query"] for s in ev.TRAINING_SECTIONS for r in bench.get(s) or []]),
             (fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]])]
    out = []
    for st, queries in pairs:
        ge = tune.GridEvaluator(st, queries, ap, rp.ordering_rules["terminal_alias_full_weight"])
        for p in pts:
            rpp = tune.ranking_with(rp, p)
            with mock.patch.object(policy, "ranking", return_value=rpp), mock.patch.object(policy, "aliases", return_value=ap):
                for q in queries:
                    o = search.search_operations(st, q, limit=5)
                    if ge.usage(q, rpp) != ([r["key"] for r in o["results"]], o["recommended_operation"]):
                        out.append({"point": p, "query_sha256": ev.canonical_sha256(q)})
    return out


def pre_t_blockers_r6(result, event, equivalence, extra=()) -> list:
    """Round 6 spec §4.2: tuning_accept on the dry-run result; every failing term is a blocker with its evidence."""
    out = []
    mv = metric_violations(result.metrics)
    if mv:
        out.append({"kind": "metric_threshold", "violations": mv})
    if not (result.scorer_rule or {}).get("ok"):
        out.append({"kind": "scorer_rule_violation", "scorer_rule": {k: v for k, v in (result.scorer_rule or {}).items() if k != "loss_list"},
                    "loss_list": (result.scorer_rule or {}).get("loss_list", [])})
    if result.fixture_result["final"]:
        out.append({"kind": "fixture_fail", "failing": list(result.fixture_result["final"])})
    if result.validation_errors:
        out.append({"kind": "alias_validation_error", "errors": list(result.validation_errors)})
    cxr = result.counterexample_result or {}
    if cxr.get("losses"):
        out.append({"kind": "counterexample_loss", "losses": cxr["losses"]})
    if (cxr.get("classes") or {}).get("uncovered_proposer"):
        out.append({"kind": "counterexample_uncovered_proposer", "keys": cxr["classes"]["uncovered_proposer"]})
    if equivalence:
        out.append({"kind": "equivalence_mismatch", "count": len(equivalence), "first": equivalence[:5]})
    if not result.tuning_accept and not out:
        out.append({"kind": "tuning_accept_false", "invariants": {"reason": "dry-run tuning_accept false with no other blocker"}})
    return out + list(extra)


def dry_run_pipeline_r6(state, rp, bench, aliases_raw, cands_doc, corpus):
    from unittest import mock
    from tests.benchmarks import scorer_rule_cx as cx6
    from tools.atlassian_docs.intelligence import policy
    b_sha = policy.canonical_sha256(aliases_raw)
    queries = [r["query"] for s in ev.TRAINING_SECTIONS for r in bench.get(s) or []]
    fx_state, fx_bench = tune.fixture_state(), tune.fixture_bench(bench)
    tf = rp.ordering_rules["terminal_alias_full_weight"]
    ge = tune.GridEvaluator(state, queries, tune._alias_policy(aliases_raw), tf)
    ge_fx = tune.GridEvaluator(fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]], tune._alias_policy(aliases_raw), tf)
    shas = {}
    raw_sha = lambda raw: shas.setdefault(id(raw), policy.canonical_sha256(raw))
    evaluate_fn = lambda p, raw: tune.evaluate_usage_fast(ge, rp, p, bench) if raw_sha(raw) == b_sha else tune.evaluate_usage_point(state, rp, p, bench, tune._alias_policy(raw))
    fixture_fn = lambda p, raw: tune.fixture_failures_fast(ge_fx, rp, p, fx_bench) if raw_sha(raw) == b_sha else tune.fixture_failures(fx_state, rp, p, fx_bench, tune._alias_policy(raw))
    scorer_fn = lambda p, raw: cx6.compare(state, rp, p, tune._alias_policy(raw), corpus, bound_fingerprint=state.registry.fingerprint, aliases_sha256=raw_sha(raw))
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run must not write"))
    with mock.patch.object(tune, "write_constants", boom), mock.patch.object(tune, "_write_log", boom):
        return tune.run_pipeline_result_r6(evaluate_fn, bench, aliases_raw, cands_doc, rp.tuning_grid, dict(rp.baseline), fixture_fn, scorer_fn,
                                           {r["id"]: r["query"] for s in ("seed", "regression_positive") for r in bench.get(s) or []},
                                           counterexample_fn=tune.final_counterexample_fn(state, rp, aliases_raw, round=ROUND, root=ROOT))


PRE_T_EVENTS = ("scorer_rule_corpus_pinned", "relabel_applied")       # promotion_sealed is historical pre-relabel evidence (plan review 2 P1-1)
PRE_T_FILES = ("aliases-h.json", "inputs/round4/doc-titles-snapshot.json")


def load_pre_t_evidence(work) -> tuple:
    """Everything run_pre_t reads from the work dir: the latest of each PRE_T_EVENTS ledger event and the PRE_T_FILES."""
    work, probs = pathlib.Path(work), []
    led = work / "controller-events.jsonl"
    lines = [json.loads(l) for l in led.read_text(encoding="utf-8").splitlines() if l.strip()] if led.exists() else []
    out = {}
    for name in PRE_T_EVENTS:
        e = next((x for x in reversed(lines) if x.get("event") == name), None)
        if e is None:
            probs.append(f"ledger event {name} missing")
        out[name] = e
    for rel in PRE_T_FILES:
        if not (work / rel).is_file():
            probs.append(f"file {rel} missing")
    relabels = [i for i, x in enumerate(lines) if x.get("event") == "relabel_applied"]
    for prev, cur in zip(relabels, relabels[1:]):                   # plan review 2 P0-2: the H22 split is never re-baselined silently
        if not any(x.get("event") == "relabel_rerun_ruling" for x in lines[prev + 1:cur]):
            probs.append("relabel_applied re-ledgered without a relabel_rerun_ruling (training split re-baseline)")
    return out, probs


def seed_rehearsal_work(real_work, temp_work) -> dict:
    """plan review 1 P0-3: copy exactly the pre-T evidence (latest PRE_T_EVENTS lines, PRE_T_FILES) into the rehearsal work dir and
    verify every copied sha; returns {name: sha256}."""
    real_work, temp_work = pathlib.Path(real_work), pathlib.Path(temp_work)
    evidence, probs = load_pre_t_evidence(real_work)
    if probs:
        raise SystemExit(f"error: real work dir lacks pre-T evidence: {probs}")
    temp_work.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(evidence[n]) for n in PRE_T_EVENTS]           # latest event of each kind (already validated on the real ledger)
    (temp_work / "controller-events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shas = {}
    for rel in PRE_T_FILES:
        dst = temp_work / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real_work / rel, dst)
        if ev.file_sha256(dst) != ev.file_sha256(real_work / rel):
            raise SystemExit(f"error: copy of {rel} differs")
        shas[rel] = ev.file_sha256(dst)
    copied, _ = load_pre_t_evidence(temp_work)
    if any(copied[n] != evidence[n] for n in PRE_T_EVENTS):
        raise SystemExit("error: seeded ledger events differ from the real ledger")
    return shas


def run_pre_t(cache: pathlib.Path, work: pathlib.Path) -> int:
    from tests.benchmarks import scorer_rule_cx as cx6
    from tools.atlassian_docs.intelligence import policy
    work = pathlib.Path(work)
    rp, bench = policy.load_ranking(tune.RANKING_PATH), tune._BENCH
    aliases_raw, ranking_raw = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")), json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))
    ap, cands_doc = tune._alias_policy(aliases_raw), json.loads(tune.CANDIDATES_PATH.read_text(encoding="utf-8"))
    evidence, ev_problems = load_pre_t_evidence(work)
    corpus_meta = evidence.get("scorer_rule_corpus_pinned")
    ref = json.loads((ROOT / f"tests/benchmarks/round{ROUND}-counterexample-reference.json").read_text(encoding="utf-8"))

    def body(state):
        corpus = cx6.corpus(state)
        extra = [{"kind": "pre_t_evidence_missing", "problems": ev_problems}] if ev_problems else []
        from tests.benchmarks import round6_labels as labels
        pinned_split = (evidence.get("relabel_applied") or {}).get("training_split_sha256")
        if pinned_split != labels.training_split_sha256(bench):                       # plan review 1 P0-2: H22 pin == pre-T
            extra.append({"kind": "training_split_mismatch", "pinned": pinned_split, "current": labels.training_split_sha256(bench)})
        if corpus_meta is None or corpus_meta["registry_fingerprint"] != state.registry.fingerprint or corpus_meta["corpus_sha256"] != ev.canonical_sha256(corpus):
            extra.append({"kind": "scorer_rule_binding", "problems": ["corpus metadata missing or differs from the ledger pin"]})
        result = dry_run_pipeline_r6(state, rp, bench, aliases_raw, cands_doc, corpus)
        return state.registry.fingerprint, result, equivalence_mismatches(state, rp, bench, ap), extra
    fp, result, eq, extra = tune._with_state(cache, body)
    problems = counterexample_reference_problems(ref, work, fp)
    if problems:
        extra.append({"kind": "counterexample_reference_mismatch", "problems": problems})
    blockers = pre_t_blockers_r6(result, {"pass": True}, eq, extra=extra)
    e = {"event": "pre_t_checkpoint", "round": ROUND, "registry_fingerprint": fp, "metrics": result.metrics, "selection": result.selection,
         "scorer_rule": {k: v for k, v in (result.scorer_rule or {}).items() if k != "loss_list"},
         "pre_t_blockers": blockers, "blocking_reasons": [b["kind"] for b in blockers], "equivalence_mismatches": len(eq),
         "dry_run": {"tuning_accept": result.tuning_accept, "selected_point": result.selected_point, "fixture_final": result.fixture_result["final"],
                     "validation_errors": result.validation_errors},
         "pipeline_input_sha256": pipeline_input_sha256(ranking_raw, aliases_raw, cands_doc, bench),
         "pipeline_result_sha256": policy.canonical_sha256(dataclasses.asdict(result)),
         "result": "pass" if not blockers else "stop_for_amendment",
         "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    work.mkdir(parents=True, exist_ok=True)
    with open(work / "controller-events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(e) + "\n")
    print(json.dumps(e, indent=1)); return 0 if e["result"] == "pass" else 1
```

(`dataclasses.asdict(result)` needs every `PipelineResult` field JSON-serializable; `metrics`/`scorer_rule`/`selection` are plain dicts.)

- [ ] **Step 4: Implement the rehearsal (spec §5.2)**

```python
def _run_in_tree(tree, argv):
    r = subprocess.run(argv, cwd=tree, env=_env(), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def t_commands(cache, work, tree) -> list:
    """The T sequence (Task C5 runs the same list in the real checkout): candidates, classify, carry, freeze."""
    py, d = sys.executable, DATA_REL
    return [[py, "tests/benchmarks/alias_candidates_tool.py", "candidates", "--cache-dir", str(cache), "--round", str(ROUND)],
            [py, "tests/benchmarks/alias_candidates_tool.py", "classify", "--cache-dir", str(cache), "--round", str(ROUND)],
            [py, "tests/benchmarks/concept_lexicon_check.py", "carry", "--lexicon", f"{d}/concept_lexicon.json", "--candidates", f"{d}/alias_candidates.json",
             "--prior-lexicon", str(work / "prior-concept_lexicon.json"), "--prior-candidates", str(work / "prior-alias_candidates.json")],
            [py, "tests/benchmarks/round_seal.py", "freeze", "--round", str(ROUND), "--cache-dir", str(cache),
             "--reference-enc", str(pathlib.Path.home() / ".atlassian_api_updater/archive/round2/sealed/round2-sealed.json.enc")]]


def run_rehearsal(cache, work, dry=False) -> int:
    """spec §5.2: on a throwaway `git archive HEAD` tree — T commands, full suite in the T state, pre-T dry-run, worker-brief
    handshake format; the working tree is never written. Appends rehearsal_report to work/controller-events.jsonl."""
    tree = pathlib.Path(tempfile.mkdtemp(prefix="round6-rehearsal-"))
    temp_work = pathlib.Path(tempfile.mkdtemp(prefix="round6-rehearsal-work-"))
    steps = []
    try:
        if not dry:
            archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
            subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
            for f in sorted((pathlib.Path(work) / "frozen").glob("round6-*")):
                shutil.copyfile(f, tree / "tests/benchmarks" / f.name)
            try:
                seeded = seed_rehearsal_work(work, temp_work); steps.append({"argv": ["seed_rehearsal_work"], "exit": 0, "output_sha256": ev.canonical_sha256(seeded)})
            except SystemExit as exc:                                 # plan review 2 P1-4: a seeding failure is a recorded rehearsal failure
                steps.append({"argv": ["seed_rehearsal_work"], "exit": 1, "output_sha256": hashlib.sha256(str(exc).encode("utf-8")).hexdigest()})
        for argv in ([] if steps and steps[-1]["exit"] else t_commands(cache, work, tree) + [[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                                                     [sys.executable, "tests/benchmarks/round6_simulation.py", "--phase", "pre-T",
                                                      "--cache-dir", str(cache), "--work", str(temp_work)]]):
            code, out = _run_in_tree(tree, argv)
            steps.append({"argv": argv[1:3], "exit": code, "output_sha256": hashlib.sha256(out.encode("utf-8")).hexdigest()})
            if code != 0:
                break
        brief = tree / f"tests/benchmarks/round{ROUND}-worker-brief.md"
        hs_ok = dry or (brief.exists() and handshake_format_ok(brief.read_text(encoding="utf-8")))
        report = {"event": "rehearsal_report", "round": ROUND, "steps": steps, "handshake_format_ok": hs_ok,
                  "failures": sum(1 for s in steps if s["exit"] != 0) + (0 if hs_ok else 1),
                  "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        pathlib.Path(work).mkdir(parents=True, exist_ok=True)
        with open(pathlib.Path(work) / "controller-events.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report) + "\n")
        print(json.dumps(report, indent=1))
        return 0 if report["failures"] == 0 else 1
    finally:
        shutil.rmtree(tree, ignore_errors=True); shutil.rmtree(temp_work, ignore_errors=True)


def handshake_format_ok(text) -> bool:
    return f"ROUND{ROUND}-WORKER-HANDSHAKE" in text and "Acceptance (Round 6 spec §4.2, byte-for-byte)" in text
```

The controller renders `round6-worker-brief.md`, `round6-hidden-generation-prompt.md`, `round6-hidden-reviewer-prompt.md`, `round6-method-safety.json` and `round6-counterexample-reference.json` into `$W/frozen/` first (Task 13 Step 1); `run_rehearsal` copies them into the temp tree and seeds a separate temp work dir with exactly the pre-T evidence (`seed_rehearsal_work`), so the rehearsal's pre-T reads the same evidence as the real one and never writes `$W` or the checkout.

`main`: `--phase` choices `("pre-T", "H", "rehearsal")`; `rehearsal` needs `--cache-dir` and `--work` and calls `run_rehearsal`.

- [ ] **Step 5: H lifecycle steps** — in `apply_T`, drop the KU-registry write and the lexicon *resolution* (Round 6 has none): keep `act.candidates(...)`, the classification and `clc.carry_forward(...)` with the prior lexicon/candidates, the synthetic frozen texts, `write_synthetic_reference` rewritten for PR-6 (`inputs = {"aliases_h_sha256", "registry_fingerprint"}`) and the freeze call. `apply_C`/`_synthetic_tuning_line` build their log line with the Round 6 fields (`metrics`, `scorer_rule`, `selection`) by calling `tune._finish6`'s field set — construct the line as `_finish6` does (same keys) with synthetic values. `synthetic_hidden_records` adds `"no_answer": True` to every negative. Everything else keeps the Round 5 body with the substitutions.

- [ ] **Step 6: Seal/freeze** in `round_seal.py`:

```python
HIDDEN_RULES_R6 = tuple(HIDDEN_RULES_R5) + ("no-answer",)          # Round 6 spec §4.1: every hidden negative is no_answer: true


def _no_answer_checks(rec) -> list:
    return [] if rec.get("no_answer") is True else [f"{rec.get('id', '?')}: no-answer: hidden negative records must carry no_answer: true"]
```

In `machine_check`, after the `round >= 3 and sect == "negative"` line: `if round >= 6 and sect == "negative": out += _no_answer_checks(rec)`. Add `(": no-answer:", "no-answer")` to `_RULE_PATTERNS`. In `freeze_entry`, `hidden_generation_rules` uses `HIDDEN_RULES_R6 if round >= 6 else …`; the `round >= 5` block becomes:

```python
    if round >= 5:                                                     # Round 5 spec §4.1, §6.1, §9; Round 6 plan PR-4
        lex = _read_json(RANKING_PATH.parent / "concept_lexicon.json")
        entry["known_unreachable_seeds"] = sorted(ev.KNOWN_UNREACHABLE[round])
        if round == 5:
            entry["known_unreachable_registry_sha256"] = ev.file_sha256(ROOT / f"tests/benchmarks/round{round}-known-unreachable.json")
        entry["lexicon_union_resolution"] = (lex.get("components") or {}).get("union_resolution")
        entry["counterexample_reference_sha256"] = ev.file_sha256(ROOT / f"tests/benchmarks/round{round}-counterexample-reference.json")
        if entry["lexicon_union_resolution"] != "source-precedence":
            raise SystemExit("REFUSED: concept_lexicon.json was not built by the Round 5 source-precedence resolution")
    if round >= 6:                                                     # Round 6 spec §3.5 binding, §4.3 split
        from tests import tune_search_ranking as tune
        from tests.benchmarks import scorer_rule_cx as cx6, round6_labels as labels
        corpus, sfp = tune._with_state(pathlib.Path(cache_dir), lambda st: (cx6.corpus(st), st.registry.fingerprint))
        entry["scorer_rule_corpus_sha256"], entry["scorer_rule_registry_fingerprint"] = ev.canonical_sha256(corpus), sfp
        entry["training_split_sha256"] = labels.training_split_sha256(_read_json(BENCH_PATH))
```

Append `HIDDEN_RULES_R6` tests (Step 2) and confirm `rs.HIDDEN_RULES_R6` is used by `section_origin`/state machine only through the rule-id list.

- [ ] **Step 7: Run** — `python -m unittest discover -s tests -t . 2>&1 | tail -3` → `OK`; then `python tests/benchmarks/round6_simulation.py --phase H` → `ALL STEPS PASS` (synthetic lifecycle T, B, D, F, X, X_preB2–5 on a throwaway tree). Any failing step is a tooling defect fixed in this task before the commit.

- [ ] **Step 8: Commit**

```bash
git add tests/benchmarks/round6_simulation.py tests/benchmarks/test_round6_simulation.py tests/benchmarks/round_seal.py tests/benchmarks/test_round_seal.py tests/benchmarks/evaluator.py
git commit -m "H21d: round6_simulation (metric-threshold pre-T blockers, usage equivalence preflight, scorer-rule binding, rehearsal phase on a throwaway tree, Round 6 H lifecycle), round_seal no-answer hidden rule + round 6 freeze keys (corpus, registry, split)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Controller tasks

`$S = ~/.atlassian_api_updater/round6-cache`, `$W = ~/.atlassian_api_updater/round6-work` (the ledger `$W/controller-events.jsonl` already holds `runtime_observation_started` and the review-4 ruling). Every STOP below goes to review thread 2 with a written report; the user is interrupted only for hard stops (decryption/encryption, push/merge) and completion reports.

### Task 8: **[controller]** Pin `initial_housekeeping_commit`, create S, pin the scorer-rule corpus

- [ ] **Step 1: Pin** — `python tests/benchmarks/round_seal.py round-start-guard --round 6` → exit 0. Ledger `{"event": "initial_housekeeping_commit", "sha": <H21d or last H′>, "round6_start_commit": "29f298f", "controller_actor_id", "session_id", "plan_review": {"verdict", "review_output_sha256"}}`.
- [ ] **Step 2: Create S** — live fetch `python -m tools.atlassian_docs` (the only network step), compare with the archived Round 5 S (`~/.atlassian_api_updater/archive/round5/round5-cache`): identical spec shas → copy the archive to `$S` (`s_reused_from_round5: true`); else copy the live cache (`false`, ledger the changed spec shas). `python tests/benchmarks/round_seal.py catalog --round 6 --cache-dir $S --out $W/round6-generator-catalog.json --internal-out $W/round6-internal-catalog.json`; `export ATLASSIAN_DOCS_ROUND6_CACHE=$S`.
- [ ] **Step 3: Pin the corpus (spec §3.5, before any H measurement)**

```bash
python - <<'EOF'
import json, os, pathlib
from tests import tune_search_ranking as tune
from tests.benchmarks import scorer_rule_cx as cx6
S, W = pathlib.Path(os.environ["ATLASSIAN_DOCS_ROUND6_CACHE"]), pathlib.Path.home() / ".atlassian_api_updater/round6-work"
meta = tune._with_state(S, lambda st: cx6.corpus_metadata(st, cx6.corpus(st)))
with open(W / "controller-events.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"event": "scorer_rule_corpus_pinned", **meta}) + "\n")
print(meta)
EOF
```

- [ ] **Step 4: Verb inventory** — unchanged from Round 5 (`verb_inventory_sha256` ledgered; a difference → STOP).

### Task 9: **[controller]** Promotion (spec §4.3; Keychain decryption authorized by the user for this archive)

- [ ] **Step 1: Decrypt to `$W` only** — `security find-generic-password -a "$USER" -s atlassian-round5-sealed -w | openssl enc -d -aes-256-cbc -pbkdf2 -pass stdin -in ~/.atlassian_api_updater/archive/round5/sealed/round5-sealed.json.enc -out $W/round5-plain.json` (same cipher parameters as the Round 5 encryption ledger; the password never appears in argv or files). Check `ev.canonical_sha256` of each section against `round5_seal` in the benchmark (also done inside `promote`).
- [ ] **Step 2: Promote and seal the payload** — `python -m tests.benchmarks.round6_labels promote --bench tests/benchmarks/search_queries.json --plain $W/round5-plain.json --out tests/benchmarks/search_queries.json`; ledger `{"event": "promotion_sealed", "promotion_payload_sha256", "seed_ids": "s-040..s-055", "regression_ids": "rn-015..rn-022"}` **before** any relabel step (historical pre-relabel evidence: re-checked at Task 10/H22 and on any H′ benchmark change, not at pre-T — T's classify may rewrite promoted seeds' `failure_classes`); `python -m tests.benchmarks.round6_labels verify --bench tests/benchmarks/search_queries.json --plain $W/round5-plain.json` → `ok`.
- [ ] **Step 3: Remove the plaintext** — `rm $W/round5-plain.json` after Step 2 (the promoted records are now public seed/regression data by spec; the ciphertext stays archived). Ledger `round5_plaintext_removed`.

### Task 10: **[controller]** Relabel the 22 regression records (two stateless reviewers, third on disagreement)

- [ ] **Step 1: Inputs** — `python -m tests.benchmarks.round6_labels relabel-input --bench tests/benchmarks/search_queries.json --template tests/benchmarks/round6-relabel-prompt.md --out $W/relabel-input.txt`; the attachment is `$W/round6-generator-catalog.json`. Ledger both shas and `engine_output_in_input: false`.
- [ ] **Step 2: Reviewers A and B** — two new ChatGPT Temporary chats (personalization off; UI-state screenshot per chat), each given the attachment + the byte-exact input; extract the first JSON object to `$W/relabel-A.json` / `$W/relabel-B.json`; `check-review --review … --catalog $W/round6-internal-catalog.json` → `ok` (a schema failure → one retry with the identical input in a new chat; a second failure → STOP). Actor ids differ from each other and from every earlier generator/reviewer. Ledger each attempt in `$W/attempts.jsonl` (stage `relabel-r6`).
- [ ] **Step 3: Reviewer C (only if A ≠ B on some id)** — same input restricted to the disagreeing ids (render with a bench filtered to those records), same schema check.
- [ ] **Step 4: Apply, close, pin the split** — `round6_labels apply --review $W/relabel-A.json --review $W/relabel-B.json [--review $W/relabel-C.json] --actors A B [C] --bench … --out tests/benchmarks/search_queries.json`; `round6_labels closure --catalog $W/round6-internal-catalog.json --bench … --out tests/benchmarks/search_queries.json` → exit 0 (exit 3 = STOP: label/catalog migration problem to thread 2); `round6_labels verify --bench tests/benchmarks/search_queries.json --sealed-payload <promotion_sealed.promotion_payload_sha256>` → `ok` (it also checks the label provenance schema and PR-8). A `PR-8 fixture label conflict` line → `STOP_FOR_AMENDMENT`: the thread rules on redefining the r0 fixture by the current catalog-fact labels (spec + plan amendment), nothing is committed meanwhile. Ledger `{"event": "relabel_applied", "positive", "negative", "adjudicated", "review_output_sha256s", "training_split_sha256", "promotion_payload_recheck": true}`.
- [ ] **Step 5: Commit the data (H22)** — run the suite (`test_committed_benchmark_labels` now runs instead of skipping); tests that pin the inherited counts (39 seeds / 14 regression records) are updated to the new totals only where they pin counts (`SEED_TOTAL`/`REGRESSION_TOTAL` are computed, not pinned). `git add tests/benchmarks/search_queries.json [count-pinning tests]`; commit `H22: Round 6 promotion (16 seed + 8 regression) and catalog-fact relabel (regression_positive N / regression_negative M); training_split_sha256 <sha>` with the trailer.

### Task 11: **[controller]** H adoption measurement (spec §3.5) — thread-2 ruling

- [ ] **Step 1: Measure** on `$S` at the Round 5 constants and the H aliases:

```bash
python - <<'EOF'
import json, os, pathlib
from tests import tune_search_ranking as tune
from tests.benchmarks import evaluator as ev, scorer_rule_cx as cx6
from tools.atlassian_docs.intelligence import policy, search
S, W = pathlib.Path(os.environ["ATLASSIAN_DOCS_ROUND6_CACHE"]), pathlib.Path.home() / ".atlassian_api_updater/round6-work"
rp, raw = policy.load_ranking(tune.RANKING_PATH), json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8"))
ap, bench, point = tune._alias_policy(raw), tune._BENCH, dict(policy.load_ranking(tune.RANKING_PATH).constants)
def body(st):
    corpus = cx6.corpus(st); kw = dict(bound_fingerprint=st.registry.fingerprint, aliases_sha256=ev.canonical_sha256(raw))
    on = tune.evaluate_usage_point(st, rp, point, bench, ap)
    with search.scorer_rules(()):
        off = tune.evaluate_usage_point(st, rp, point, bench, ap)
    return {"scorer_rule": cx6.compare(st, rp, point, ap, corpus, **kw), "per_rule_off": cx6.per_rule_off(st, rp, point, ap, corpus, **kw),
            "m_on": on["m"], "m_off": off["m"]}
r = tune._with_state(S, body)
r["h_adoption_ok"] = r["scorer_rule"]["ok"] and r["m_on"]["wv"] <= r["m_off"]["wv"] and r["m_on"]["fr"] <= r["m_off"]["fr"] and ev.accept_vector(r["m_on"])
with open(W / "controller-events.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"event": "h_adoption_measurement", **r}) + "\n")
print(json.dumps({k: r[k] for k in ("h_adoption_ok", "m_on", "m_off")}, indent=1)); print(r["scorer_rule"]["loss_list"])
EOF
```

- [ ] **Step 2: Report and rule** — post the measurement (metric vectors ON/OFF, losses with keys and write/read split, gains, per-rule OFF diagnostics, the §8 generic-token diagnostics) to review thread 2. `h_adoption_ok == true` → ruling "adopt" ledgered. `false` → the thread rules on a spec amendment (which rule to drop or reshape); that is a new spec version + plan version + H′, never a threshold exception (spec §3.5).

### Task 12: **[controller + fresh reviewer]** Whole-branch review, `housekeeping_commit`

- [ ] **Step 1: Fresh reviewer** — one fresh reviewer on the most capable model reviews `29f298f..HEAD` (H18–H22) against spec v1.6 + this plan (superpowers:requesting-code-review); findings are fixed as H′ commits (suite → `--phase H` → reviewer re-check) until findings 0.
- [ ] **Step 1b: Re-measure before the pin (plan review 1 P1-4)** — if any H′ landed after Task 11: when `scorer_rule_cx.py` changed, re-run Task 8 Step 3 (new `scorer_rule_corpus_pinned` event); when the benchmark changed, require `training_split_sha256(HEAD) ==` the sealed H22 value (a `failure_classes`-only change keeps it) and re-run `round6_labels verify --sealed-payload <promotion_sealed value>` — **never re-ledger `relabel_applied`**; a different split is a semantic label change → STOP_FOR_AMENDMENT (the thread may rule `relabel_rerun_ruling`, after which Task 10 runs again with new independent reviews and only then a new `relabel_applied` is ledgered; `load_pre_t_evidence` rejects a second `relabel_applied` without that ruling); then always re-run Task 11 Step 1 on HEAD and require `h_adoption_ok == true` (otherwise Task 11 Step 2's ruling path).
- [ ] **Step 2: Pin** — ledger `{"event": "housekeeping_commit", "sha": HEAD, "tooling_code_sha256": ev.tooling_code_sha256(ROOT), "intelligence_fingerprint": <from a search payload on $S>}` and `{"event": "runtime_stability_qualifying_start", "intelligence_fingerprint": <same>, "at": <now>}` (spec §6: the H final fingerprint restarts the qualifying window). From here the TOOLING_FILES and the scorer/policy structure are frozen.

### Task 13: **[controller]** Frozen texts and the real-data T rehearsal (spec §5.2)

- [ ] **Step 1: Frozen texts into `$W/frozen/`** — `round6-worker-brief.md`, `round6-hidden-generation-prompt.md`, `round6-hidden-reviewer-prompt.md` = the Round 5 texts with the substitution table applied; in the worker brief the acceptance line is replaced by exactly: `Acceptance (Round 6 spec §4.2, byte-for-byte): tuning_accept := wv == 0 ∧ fr == 0 ∧ 10·sr3 ≥ 9·|seed| ∧ 10·src ≥ 9·|seed| ∧ 10·srk ≥ 9·src ∧ rp3 == |regression_positive| ∧ rpk == |regression_positive| ∧ 8·nab ≥ 7·|regression_negative| ∧ fixture_positive == 23/23 ∧ fixture_negative_raw == 6/6 ∧ counterexample ok (no loss, no uncovered proposer key) ∧ scorer_rule_ok (eligible > 0 ∧ 100·losses ≤ eligible) ∧ no validation errors`; the generation prompt's negative rule adds `every negative record carries "no_answer": true`; `round6-method-safety.json` as Round 5 Task 3 Step 3; `round6-counterexample-reference.json` per PR-6 (`cp tools/atlassian_docs/intelligence/data/search_aliases.json $W/aliases-h.json` first). `git show <housekeeping_commit>:tools/atlassian_docs/intelligence/data/concept_lexicon.json > $W/prior-concept_lexicon.json` and the same for `alias_candidates.json`.
- [ ] **Step 2: Rehearse** — `python tests/benchmarks/round6_simulation.py --phase rehearsal --cache-dir $S --work $W` → exit 0, `rehearsal_report.failures == 0`, `git status --porcelain` unchanged. A failure is fixed by H′, after which **Task 12 Steps 1 → 1b → 2 run in full** (re-check, re-measurement, `housekeeping_commit_moved`) and the rehearsal runs again (plan review 2 P1-3).

### Task 14: **[controller]** T: candidates, classify, carry, binding pre-T gate, freeze, T commit, post-T check

- [ ] **Step 1: T commands** — run `round6_simulation.t_commands($S, $W, ROOT)` entries 1–3 in the checkout (candidates, classify, carry); never run `lexicon-gate`/`merge` after carry.
- [ ] **Step 2: Binding pre-T gate** — `python tests/benchmarks/round6_simulation.py --phase pre-T --cache-dir $S --work $W` → exit 0 required. Exit 1 → `STOP_FOR_AMENDMENT`: `$W/pre-t-blocker-report.md` (every blocker with `metric_threshold` items/values/bounds, scorer-rule losses, counterexample losses, fixture failures, equivalence mismatches) to review thread 2; rulings as Round 5 Task 5 Step 3 (amendment → spec + plan + reviewed H′ → rerun from the affected step; or `TERMINAL_PRE_T_NOT_REACHED` by user decision only).
- [ ] **Step 3: Frozen texts, freeze, commit T** — `cp $W/frozen/round6-* tests/benchmarks/`; run `t_commands` entry 4 (freeze; prints the round-6 entry incl. `scorer_rule_corpus_sha256`, `scorer_rule_registry_fingerprint`, `training_split_sha256`, `known_unreachable_seeds: []`); `git add` exactly `ev.t_allowlist(6)`; commit `T: Round 6 freeze …`; post-T check against `ev.t_allowlist(6)` and `freeze_for(6)["t_policy_files"]`; the freeze's corpus sha must equal the latest `scorer_rule_corpus_pinned` event and its `training_split_sha256` must equal the latest `relabel_applied` event (plan review 1 P0-2: H22 pin == pre-T == freeze); a mismatch → STOP (tooling defect after T ends the round).

### Task 15: **[controller]** Hidden set, review, attempt ledger, commit B, encryption

As Round 5 plan v8 Task 6 with the substitutions: new hidden set `held_out-r6` (16) / `negative-r6` (8, each `"no_answer": true`) from the frozen Round 6 prompts; actors distinct from every earlier generator/reviewer/relabeler; `rs.machine_check(..., round=6, verb_methods=…)` clean (incl. `no-answer`); attempt-needle ledger; `round6_seal`; commit B. Hidden-text transfer follows spec §5.4 (conversation API read, hash-checked chunks). User encryption of `round6-sealed.json` is a hard stop.

### Task 16: **[controller]** S checkpoint and worker dispatch (B..C)

As Round 5 plan v8 Task 7: a fresh worker with `round6-worker-brief.md`, handshake `ROUND6-WORKER-HANDSHAKE`; the worker runs `python tests/tune_search_ranking.py --cache-dir $S` once; the controller reads `tuning_accept`, `metrics`, `scorer_rule` from the log line and never recomputes them.

### Task 17: **[controller]** C / F / X / X_preB, then D (fresh D controller + user decryption)

- [ ] **Step 1** — as Round 5 plan v8 Task 8 (provenance check, branch commit). On C, ledger `runtime_stability_qualifying_start` for the adopted fingerprint (spec §6). On F caused by `scorer_rule_ok`, the readiness record names it.
- [ ] **Step 2: D** — as Round 5 plan v8 Task 9 with the gate replaced: `python tests/diag_search_queries.py --cache-dir $S --round 6 --bench <decrypted plain> --json tests/benchmarks/round6-final.json`; the verdict is `round6-final.json["gate"]["pass"]` (five checks, spec §4.1); top-1 and the actionable split are recorded only.

### Task 18: **[controller]** Readiness, runtime stability, archive, memory, dashboard, finishing

- [ ] **Step 1: Readiness** — append `## Search Quality Round 6 — decision record (<date>)` to `docs/phase3-readiness.md`: spec version (v1.6 or later) / plan version, `round6_start_commit 29f298f`, `initial_housekeeping_commit`, `housekeeping_commit` (+ moves), `s_reused_from_round5`; the five gate metrics with bounds and results, top-1 (recorded); the training metric vector at the selected point; the H adoption measurement (losses with keys, per-rule OFF, §8 generic-token diagnostics); promotion/relabel summary (positive/negative counts, adjudications, review shas); rehearsal result; pre-T events and blockers; terminal branch; Runtime stability: `runtime_observation_started`, the current `runtime_stability_qualifying_start`, qualifying search records / days from `search_log.qualifying_records` on the user-scope log, and the reference metrics (`match_selections` agreement rate, write recommendations) — not a gate.
- [ ] **Step 2: Post-terminal** — as Round 5 plan v8 Task 11 with the substitutions: archive `round6-cache`, `round6-work` and `sealed/round6-sealed.json.enc` under `~/.atlassian_api_updater/archive/round6/` after the user confirms; memory `search-quality-round6-status.md`; republish the dashboard artifact; superpowers:finishing-a-development-branch (push/merge only on the user's instruction).

## AC coverage map (spec v1.6)

| AC | Tasks |
|---|---|
| AC-R6-01 payload contract, results invariant | 2 (`test_r0_table`, `test_abstention_never_changes_results`) |
| AC-R6-02 R0–R3, `PRODUCT_NAME_TOKENS`, `head_info`, R3 flag | 2 |
| AC-R6-03 scorer-rule counterexample, H adoption, pre-T/B..C term | 4, 5 (`tuning_accept_r6`), 7 (pre-T blocker), 11 |
| AC-R6-04 gate metrics, exact fractions, final artifact | 1, 5 (diag gate), 17 |
| AC-R6-05 metric vector, accept, selector, proposer, `metric_threshold`, `KNOWN_UNREACHABLE[6] == ()` | 1, 5, 7 |
| AC-R6-06 order, promotion, relabel, reconcile, closure | 6, 9, 10 |
| AC-R6-07 rehearsal | 7, 13 |
| AC-R6-08 log fields, selection records, qualification | 3, 12, 17, 18 |
| AC-R6-09 structure frozen after `housekeeping_commit` | 12 (pin), 14 (post-T check), inherited structure check |
