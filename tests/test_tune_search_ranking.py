import json
import pathlib
import unittest
from unittest import mock
from tests import tune_search_ranking as tune
from tools.atlassian_docs.intelligence import policy

GRID = {"method_match_bonus": [1.0, 2.0, 3.0], "method_mismatch_penalty": [0.0, 1.0, 2.0, 3.0], "path_unmatched_penalty": [0.5, 1.0, 1.5, 2.0],
        "path_unmatched_cap": [2, 3, 4], "product_hint_bonus": [2.0, 3.0, 4.0],
        "resource_match_bonus": [6.0, 8.0, 10.0, 12.0],
        "method_order_bonus": [0.0, 0.5, 1.0], "path_coverage_bonus": [0.0, 0.5, 1.0]}
BASE = {"method_match_bonus": 2.0, "method_mismatch_penalty": 2.0, "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0, "resource_match_bonus": 10.0,
        "method_order_bonus": 0.0, "path_coverage_bonus": 0.0}
S, R = tune.SEED_TOTAL, tune.REGRESSION_TOTAL   # totals of the bundled bench


def pt(**over):
    return {**BASE, **over}


class TestSelector(unittest.TestCase):
    def test_totals_match_benchmark(self):
        import json, pathlib
        path = pathlib.Path(__file__).resolve().parent / "benchmarks" / "search_queries.json"
        with path.open(encoding="utf-8") as fh:
            b = json.load(fh)
        self.assertEqual((tune.SEED_TOTAL, tune.REGRESSION_TOTAL), (39, 14))
        self.assertEqual((tune.SEED_TOTAL, tune.REGRESSION_TOTAL), (len(b["seed"]), len(b["regression_negative"])))

    def test_grid_cardinality_and_order(self):
        pts = tune.grid_points(GRID)
        self.assertEqual(len(pts), 15552); self.assertEqual(pts, sorted(pts, key=lambda p: tuple(p[k] for k in tune.CONSTANT_KEYS)))
        self.assertEqual(len(tune.grid_points(policy.load_ranking().tuning_grid)), 23328)   # the loaded (frozen) grid

    def test_l1_index_distance(self):
        self.assertEqual(tune.l1_index_distance(BASE, BASE, GRID), 0)
        self.assertEqual(tune.l1_index_distance(pt(method_mismatch_penalty=0.0, path_unmatched_cap=4), BASE, GRID), 3)

    def test_perfect_beats_non_perfect(self):
        res = [(pt(method_match_bonus=3.0), S, R), (BASE, S - 1, R)]
        self.assertEqual(tune.select_candidate(res, BASE, GRID), pt(method_match_bonus=3.0))

    def test_l1_then_magnitude_then_lexicographic(self):
        near, far = pt(product_hint_bonus=4.0), pt(method_match_bonus=1.0, path_unmatched_cap=4)
        self.assertEqual(tune.select_candidate([(far, S, R), (near, S, R)], BASE, GRID), near)          # L1 1 < 2
        a, b = pt(method_match_bonus=1.0), pt(method_match_bonus=3.0)                                   # both L1 = 1
        self.assertEqual(tune.select_candidate([(b, S, R), (a, S, R)], BASE, GRID), a)                  # smaller magnitude sum
        c, d = pt(method_mismatch_penalty=1.0), pt(path_unmatched_penalty=0.5)                          # L1 1, sums 7.0 vs 7.5
        self.assertEqual(tune.select_candidate([(d, S, R), (c, S, R)], BASE, GRID), c)
        e, f = pt(method_match_bonus=1.0, method_mismatch_penalty=3.0), pt(method_match_bonus=3.0, method_mismatch_penalty=1.0)
        self.assertEqual(tune.select_candidate([(f, S, R), (e, S, R)], BASE, GRID), e)                  # 6-tuple lexicographic
        g, h = pt(resource_match_bonus=8.0), pt(resource_match_bonus=12.0)                              # only the new axis differs, L1 1
        self.assertEqual(tune.select_candidate([(h, S, R), (g, S, R)], BASE, GRID), g)                  # magnitude sum includes it
        x, y = pt(method_match_bonus=1.0, resource_match_bonus=12.0), pt(method_match_bonus=3.0, resource_match_bonus=8.0)
        self.assertEqual(tune.select_candidate([(x, S, R), (y, S, R)], BASE, GRID), y)                  # L1 2 each; sums 19 vs 17 beat lexicographic

    def test_fallback_when_no_perfect(self):
        res = [(pt(product_hint_bonus=4.0), S - 2, R - 1), (BASE, S - 2, R), (pt(method_match_bonus=1.0), S - 3, R)]
        self.assertEqual(tune.select_candidate(res, BASE, GRID), BASE)                                 # seed max, then regression max


class TestConservativeSelector(unittest.TestCase):
    def test_smaller_bonus_pair_beats_l1_distance(self):
        near, far = pt(method_order_bonus=0.5), pt(method_match_bonus=1.0, path_unmatched_cap=4)          # bonuses (0,0.5) L1 1 vs (0,0) L1 2
        self.assertEqual(tune.select_candidate([(near, S, R), (far, S, R)], BASE, GRID), far)             # bonus tuple first
        o, c = pt(method_order_bonus=0.5), pt(path_coverage_bonus=0.5)                                     # (0,0.5) < (0.5,0)
        self.assertEqual(tune.select_candidate([(c, S, R), (o, S, R)], BASE, GRID), o)
        self.assertEqual(tune.select_candidate([(o, S, R), (BASE, S, R)], BASE, GRID), BASE)
        self.assertEqual(tune.select_candidate([(o, S, R), (BASE, S - 1, R)], BASE, GRID), o)             # perfect still beats non-perfect
        self.assertEqual(tune.BONUS_KEYS, ("path_coverage_bonus", "method_order_bonus"))


class TestCrossCheckMismatch(unittest.TestCase):
    """I2 (H' final-review fix): the memoized/production cross-check must compare failing-record identity, not
    just counts - a same-count, different-id disagreement is exactly the case counts alone would miss."""

    def test_identical_failures_is_no_mismatch(self):
        s = {"passed": 2, "failed": [{"id": "s-001"}]}
        r = {"passed": 1, "failed": []}
        self.assertEqual(tune.cross_check_mismatch(s, r, s, r), [])

    def test_same_count_different_ids_is_detected(self):
        slow_s = {"passed": 2, "failed": [{"id": "s-001"}]}
        fast_s = {"passed": 2, "failed": [{"id": "s-002"}]}          # same failure COUNT, different record
        slow_r = {"passed": 1, "failed": []}
        fast_r = {"passed": 1, "failed": []}
        self.assertEqual(tune.cross_check_mismatch(slow_s, slow_r, fast_s, fast_r), ["s-001", "s-002"])

    def test_regression_side_mismatch_is_also_detected(self):
        s = {"passed": 2, "failed": []}
        slow_r = {"passed": 1, "failed": [{"id": "rn-001"}]}
        fast_r = {"passed": 1, "failed": [{"id": "rn-002"}]}
        self.assertEqual(tune.cross_check_mismatch(s, slow_r, s, fast_r), ["rn-001", "rn-002"])


class TestEffects(unittest.TestCase):
    def test_plan_effects(self):
        self.assertEqual(tune.plan_effects(dry_run=True, perfect=True), {"write_constants": False, "append_log": False})
        self.assertEqual(tune.plan_effects(dry_run=True, perfect=False), {"write_constants": False, "append_log": False})
        self.assertEqual(tune.plan_effects(dry_run=False, perfect=True), {"write_constants": True, "append_log": True})
        self.assertEqual(tune.plan_effects(dry_run=False, perfect=False), {"write_constants": False, "append_log": True})

    def test_dirty_paths_excludes_log_and_untracked(self):
        porcelain = (f" M tools/a.py\nM  tests/b.py\n?? scratch.txt\n M {tune.LOG_REL}\n"
                     "R  old.py -> new.py\n")
        self.assertEqual(tune.dirty_paths(porcelain), ["new.py", "tests/b.py", "tools/a.py"])


BASE_RAW = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"ticket": ["issue"]}, "rules": [],
            "notes": {"ticket": {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "x"}}}


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
QUERIES = {r["id"]: r["query"] for r in BENCH2["seed"]}
CLASSES = {r["id"]: r["failure_classes"] for r in BENCH2["seed"]}


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


class TestValidator(unittest.TestCase):
    def after(self, **aliases):
        raw = json.loads(json.dumps(BASE_RAW))
        for w, (t, sid) in aliases.items():
            raw["aliases"][w] = [t]; raw["notes"][w] = tune.round_note(w, sid, t)
        return raw

    def v(self, after, **kw):
        return tune.validate_alias_change(BASE_RAW, after, CANDS, QUERIES, CLASSES, **kw)

    def test_accepts_proposer_shape(self):
        self.assertEqual(self.v(self.after(workspace=("page", "s-001"))), [])
        # NOTE (task-7 concern): Round 3 rejects any added rule outright (direct aliases only); this case now carries
        # exactly that one violation instead of being clean, since the old Round 2 "accepted rule shape" case is moot.
        rule = json.loads(json.dumps(BASE_RAW)); rule["rules"] = [{"when_all": ["workspace", "browse"], "add": ["page"]}]
        rule["notes"]["rule:0"] = tune.round_note("workspace", "s-001", "page")
        self.assertEqual(self.v(rule), ["rules are not proposed in Round 3 (direct aliases only)"])

    def test_rejects_bad_shapes(self):
        two = self.after(workspace=("page", "s-001")); two["aliases"]["workspace"] = ["page", "space"]
        self.assertTrue(any("exactly 1" in m for m in self.v(two)))
        self.assertTrue(any("candidate" in m for m in self.v(self.after(release=("version", "s-001")))))
        self.assertTrue(any("target" in m for m in self.v(self.after(workspace=("issue", "s-001")))))
        self.assertTrue(any("target" in m for m in self.v(self.after(feedback=("issue", "s-002")))))      # allowed overall, not for s-002
        self.assertTrue(any("seed" in m for m in self.v(self.after(workspace=("page", "s-002")))))
        # NOTE (task-7 concern): the per-seed cap moved from 1 (Round 2) to 2 (Round 3 PER_SEED); three notes on one
        # seed are needed to trigger it now, and the message text changed to "atomic actions".
        twice = self.after(workspace=("page", "s-001")); twice["aliases"]["feedback"] = ["comment"]
        twice["notes"]["feedback"] = tune.round_note("feedback", "s-001", "comment")
        twice["aliases"]["starred"] = ["favourite"]; twice["notes"]["starred"] = tune.round_note("starred", "s-001", "favourite")
        self.assertTrue(any("atomic actions" in m for m in self.v(twice)))
        self.assertTrue(any("budget" in m for m in self.v(self.after(workspace=("page", "s-001")), budget=0)))
        damped = self.after(workspace=("page", "s-001")); damped["alias_damping"] = 0.9
        self.assertTrue(any("alias_damping" in m for m in self.v(damped)))
        removed = self.after(); del removed["aliases"]["ticket"]; del removed["notes"]["ticket"]
        self.assertTrue(any("removed" in m for m in self.v(removed)))
        rule = json.loads(json.dumps(BASE_RAW)); rule["rules"] = [{"when_all": ["workspace", "browse", "page"], "add": ["page"]}]
        rule["notes"]["rule:0"] = tune.round_note("workspace", "s-001", "page")
        self.assertTrue(any("context" in m for m in self.v(rule)))
        not_r6 = self.after(workspace=("page", "s-001"))
        self.assertTrue(any("not R6" in m for m in tune.validate_alias_change(BASE_RAW, not_r6, CANDS, QUERIES, {**CLASSES, "s-001": ["R5"]})))
        bad_note = self.after(workspace=("page", "s-001")); bad_note["notes"]["workspace"]["failure_classes"] = []
        self.assertTrue(any("not R6" in m for m in self.v(bad_note)))
        rule2 = json.loads(json.dumps(BASE_RAW)); rule2["rules"] = [{"when_all": ["workspace", "sprint"], "add": ["page"]}]
        rule2["notes"]["rule:0"] = tune.round_note("workspace", "s-001", "page")
        self.assertTrue(any("context" in m for m in self.v(rule2)))                                   # sprint not in the query

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

    def test_abort_verify_requires_both_policy_files_at_b(self):
        cands = {"generated_from": {"inputs": {"aliases": policy.canonical_sha256(BASE_RAW), "ranking": policy.canonical_sha256({"constants": dict(BASE)})}}}
        self.assertEqual(tune.baseline_mismatch(BASE_RAW, {"constants": dict(BASE)}, cands), [])
        tampered = {"constants": {**BASE, "method_match_bonus": 3.0}}                      # aliases == B, ranking != B
        self.assertEqual(tune.baseline_mismatch(BASE_RAW, tampered, cands), ["ranking"])    # --verify (abort) must fail on this

    def test_verify_abort_mode_rejects_tampered_ranking(self):
        """Integration-level: _verify itself (not only the helper) must fail when aliases == B but ranking != B."""
        from unittest import mock
        rejected = {"run_id": "r1", "status": "rejected", "adopted": False, "constants_selected": dict(BASE), "result_sha256": "0" * 64}
        cands = {"generated_from": {"inputs": {"aliases": policy.canonical_sha256(BASE_RAW), "ranking": policy.canonical_sha256({"constants": dict(BASE)})}}, "candidates": {}}
        rp = policy.load_ranking()
        with mock.patch.object(tune, "_read_log", return_value=[rejected]), mock.patch.object(tune, "_with_state", side_effect=AssertionError("replay must not run")):
            with mock.patch("sys.stderr") as err:
                code = tune._verify(pathlib.Path("unused"), tune._BENCH, rp, BASE_RAW, {"constants": {**BASE, "method_match_bonus": 3.0}}, cands)
        self.assertEqual(code, 1); self.assertTrue(any("MISMATCH abort branch" in str(c) for c in err.write.call_args_list))

    def test_materialize_refuses_when_files_do_not_reproduce_result_sha(self):
        import tempfile
        from unittest import mock
        line = {"run_id": "r2", "constants_selected": {**BASE, "method_match_bonus": 3.0}, "result_sha256": "f" * 64,
                "aliases_proposed": {"aliases": {"workspace": ["page"]}, "rules": [], "notes": {"workspace": tune.round_note("workspace", "s-001", "page")}}}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(tune, "_read_log", return_value=[line]), \
             mock.patch.object(tune, "ALIASES_PATH", pathlib.Path(td) / "a.json"), mock.patch.object(tune, "RANKING_PATH", pathlib.Path(td) / "r.json"), mock.patch("sys.stderr"):
            (pathlib.Path(td) / "a.json").write_text(json.dumps(BASE_RAW)); (pathlib.Path(td) / "r.json").write_text(json.dumps({"constants": dict(BASE)}))
            self.assertEqual(tune._materialize("r2", pathlib.Path(td) / "out"), 2)        # recorded sha is wrong -> refused
            line["result_sha256"] = tune.result_sha256(line["constants_selected"], line["aliases_proposed"])
            self.assertEqual(tune._materialize("r2", pathlib.Path(td) / "out"), 0)

    def test_suite_evidence_and_materialize(self):
        text = ("======================================================================\nFAIL: test_a (tests.x.TestA.test_a)\n"
                "----------------------------------------------------------------------\nTraceback (most recent call last):\n  ...\nAssertionError: 1 != 2\n\n"
                "ERROR: test_b (tests.y.TestB)\n\nRan 3 tests in 0.010s\n\nFAILED (failures=1, errors=1)\n")   # 3.12 and pre-3.12 header forms
        ev_sig = tune.suite_evidence(text)
        self.assertEqual(ev_sig["failing_tests"], ["tests.x.TestA.test_a", "tests.y.TestB.test_b"]); self.assertRegex(ev_sig["output_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(ev_sig["exit_code"], 1)                                                   # from unittest's FAILED summary
        self.assertEqual(tune.suite_evidence("Ran 3 tests\n\nOK\n")["failing_tests"], [])
        self.assertEqual(tune.suite_evidence("Ran 3 tests\n\nOK\n")["exit_code"], 0)
        self.assertEqual(tune.suite_evidence(text + "exit_code: 3\n")["exit_code"], 3)            # explicit capture line wins (M-8)
        line = {"constants_selected": {**BASE, "method_match_bonus": 3.0}, "aliases_proposed": {"aliases": {"workspace": ["page"]}, "rules": [], "notes": {"workspace": tune.round_note("workspace", "s-001", "page")}}}
        ranking, aliases = tune.materialize_candidate(line, BASE_RAW, {"constants": dict(BASE), "version": 1})
        self.assertEqual(ranking["constants"]["method_match_bonus"], 3.0); self.assertEqual(aliases["aliases"]["workspace"], ["page"])
        self.assertEqual(tune.alias_patch(BASE_RAW, aliases), line["aliases_proposed"])
        self.assertEqual(tune.result_sha256(ranking["constants"], tune.alias_patch(BASE_RAW, aliases)), tune.result_sha256(line["constants_selected"], line["aliases_proposed"]))

    def test_pipeline_calls_selector_once_then_proposer_once(self):
        from unittest import mock
        calls = []
        with mock.patch.object(tune, "select_candidate", side_effect=lambda *a, **k: calls.append("select") or dict(BASE)), \
             mock.patch.object(tune, "propose_aliases", side_effect=lambda *a, **k: calls.append("propose") or (json.loads(json.dumps(BASE_RAW)), {"aliases": {}, "rules": {}, "notes": {}, "resolved_by_prior_change": [], "unresolved": [], "trials": 0, "actions_by_seed": {}, "fixture_fail": []})):
            tune.run_pipeline(lambda point, raw: ({"passed": S, "failed": []}, {"passed": R, "failed": []}), tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE,
                              lambda point, raw: [])
        self.assertEqual(calls, ["select", "propose"])


class TestGridEvaluator(unittest.TestCase):
    """spec §3.4 v1.22: the memoized grid path must rank exactly like search_operations (review focus 3)."""
    @classmethod
    def setUpClass(cls):
        cls.state = tune.fixture_state(); cls.rp = policy.load_ranking(); cls.bench = tune.fixture_bench(tune._BENCH)
        cls.queries = [r["query"] for r in cls.bench["seed"] + cls.bench["regression_negative"]] + ["issue status field values", "create and delete issue", "list page versions", "update issue-summary", "get project-versions"]
        cls.ap = tune._alias_policy(json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8")))
        cls.ge = tune.GridEvaluator(cls.state, cls.queries, cls.ap, cls.rp.ordering_rules["terminal_alias_full_weight"])

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


class TestFixtureConstraint(unittest.TestCase):
    """spec v1.14 AC-06a: the r0 fixture suite is a hard constraint on every candidate (never an objective)."""

    def test_constants_point_breaking_a_fixture_is_excluded_and_logged(self):
        perfect = lambda point, raw: ({"passed": S, "failed": []}, {"passed": R, "failed": []})
        pts = tune.grid_points(GRID)
        base_i = pts.index(BASE)
        breaks_base = lambda point, raw: ["s-022"] if point == BASE else []          # synthetic: BASE breaks a fixture
        results, selected, _, _, _, _, ff = tune.run_pipeline(perfect, BENCH2, BASE_RAW, {"candidates": {}}, GRID, BASE, breaks_base)
        self.assertNotEqual(selected, BASE); self.assertEqual(ff, {"constants": [base_i], "final": []})
        self.assertEqual(len(results), len(pts) - 1)
        self.assertEqual(selected, tune.select_candidate([(p, S, R) for p in pts if p != BASE], BASE, GRID))   # next by the same order
        _, again, _, _, _, _, ff2 = tune.run_pipeline(perfect, BENCH2, BASE_RAW, {"candidates": {}}, GRID, BASE, breaks_base)
        self.assertEqual((again, ff2), (selected, ff))                                                        # deterministic
        with self.assertRaises(SystemExit):
            tune.run_pipeline(perfect, BENCH2, BASE_RAW, {"candidates": {}}, GRID, BASE, lambda point, raw: ["s-001"])

    def test_alias_trial_breaking_a_fixture_is_not_accepted(self):
        fn = fake_eval({("workspace", "page"): ["s-001"], ("workspace", "space"): ["s-001"], ("feedback", "comment"): ["s-002", "s-003"]})
        breaks = lambda raw: ["s-022"] if raw["aliases"].get("workspace") == ["page"] else []    # synthetic fixture breaker
        _, patch = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, fixture_fn=breaks)
        self.assertEqual(patch["aliases"], {"workspace": ["space"], "feedback": ["comment"]})      # page skipped, space adopted
        # NOTE (task-7 concern): fixture_fail entries now describe atomic-action combos ("actions": [[word, target], ...])
        # rather than a single word/target pair, since the proposer tries size-1/size-2 action combos, not single words.
        self.assertEqual(patch["fixture_fail"], [{"kind": "alias", "actions": [["workspace", "page"]], "seed_query_id": "s-001", "failing": ["s-022"]}])
        self.assertEqual(tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, fixture_fn=breaks)[1], patch)
        _, unconstrained = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(unconstrained["aliases"]["workspace"], ["page"])                          # the constraint made the difference

    def test_real_fixture_suite_rejects_a_synthetic_breaking_alias(self):
        """On the real fixtures: the live policy passes the r0 suite (23/6), a synthetic alias summary -> property breaks s-022
        (v1.24: the former summary -> create no longer breaks it - the intent tier demotes POST /issue for 'update issue summary')."""
        rp = policy.load_ranking(); state, fb = tune.fixture_state(), tune.fixture_bench(tune._BENCH)
        self.assertEqual((len(fb["seed"]), len(fb["regression_negative"])), (23, 6))
        raw = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(tune.fixture_failures(state, rp, dict(rp.constants), fb, tune._alias_policy(raw)), [])
        raw["aliases"]["summary"] = ["property"]
        raw["notes"]["summary"] = {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "synthetic"}
        self.assertIn("s-022", tune.fixture_failures(state, rp, dict(rp.constants), fb, tune._alias_policy(raw)))
        with self.assertRaises(SystemExit):
            tune.fixture_bench({"seed": fb["seed"][1:], "regression_negative": fb["regression_negative"]})


class TestRequireRound(unittest.TestCase):
    """main() must refuse every subcommand before the Round 2 freeze entry exists, before any file/log I/O."""

    def test_main_refuses_every_subcommand_before_round_2_freeze_and_touches_no_file(self):
        import hashlib
        from unittest import mock
        with mock.patch.object(tune.ev, "current_round", return_value={"round": 1}):
            with self.assertRaises(SystemExit):
                tune.require_round()   # the underlying guard, checked fresh (not the cached module-level ROUND)
        r1_log = tune.ROOT / "tests" / "benchmarks" / "search-tuning-round1.jsonl"
        before = hashlib.sha256(r1_log.read_bytes()).hexdigest()
        argvs = [["--cache-dir", "/nonexistent-snapshot"], ["--adopt", "some-run-id"],
                 ["--reject", "some-run-id", "--evidence", "/nonexistent-evidence.txt"],
                 ["--materialize", "some-run-id"], ["--verify", "--cache-dir", "/nonexistent-snapshot"]]
        with mock.patch.object(tune.ev, "current_round", return_value={"round": 1}), mock.patch("sys.stderr"):
            for argv in argvs:
                self.assertNotEqual(tune.main(argv), 0, argv)
        self.assertEqual(hashlib.sha256(r1_log.read_bytes()).hexdigest(), before)


class TestRunLifecycleGuards(unittest.TestCase):
    """Review M-1 / M-2: --verify compares the files with the adopted sha; one decided run per log; adopt only the first."""

    def line(self, run_id, status):
        return {"run_id": run_id, "status": status, "adopted": status == "adopted", "tuning_failed": status == "failed",
                "constants_selected": dict(BASE), "result_sha256": "a" * 64}

    def test_adopt_requires_first_non_failed_run(self):
        from unittest import mock
        lines = [self.line("f1", "failed"), self.line("p1", "pending"), self.line("p2", "pending")]
        with mock.patch.object(tune, "_read_log", return_value=lines), mock.patch.object(tune, "_write_log") as wl, \
             mock.patch.object(tune, "_current_result_sha256", return_value="a" * 64), mock.patch("sys.stderr"), mock.patch("builtins.print"):
            self.assertEqual(tune._adopt("p2"), 2); wl.assert_not_called()
            self.assertEqual(tune._adopt("p1"), 0); wl.assert_called_once()

    def test_new_pipeline_run_refused_when_log_has_a_decided_run(self):
        import tempfile
        from unittest import mock
        for status in ("pending", "rejected", "adopted"):
            with tempfile.TemporaryDirectory() as td:
                for src in tune.SOURCES:
                    (pathlib.Path(td) / f"{src}.json").write_text("{}")
                cands = pathlib.Path(td) / "c.json"; cands.write_text(json.dumps({"generated_from": {"inputs": {}}, "candidates": {}}))
                with mock.patch.object(tune.ev, "current_round", return_value={"round": 2}), mock.patch.object(tune.rs, "verify_freeze", return_value=[]), \
                     mock.patch.object(tune, "CANDIDATES_PATH", cands), mock.patch.object(tune, "_read_log", return_value=[self.line("x", status)]), \
                     mock.patch.object(tune, "baseline_mismatch", side_effect=AssertionError("must refuse first")), mock.patch("sys.stderr"):
                    self.assertEqual(tune.main(["--cache-dir", td]), 2, status)

    def test_verify_success_branch_compares_files_with_adopted_sha(self):
        from unittest import mock
        adopted = self.line("a1", "adopted")
        rp = policy.load_ranking()
        cands = {"generated_from": {"inputs": {"aliases": policy.canonical_sha256(BASE_RAW)}}, "candidates": {}}
        adopted["constants_selected"] = dict(rp.constants)
        with mock.patch.object(tune, "_read_log", return_value=[adopted]), mock.patch.object(tune, "_with_state", return_value=[]), \
             mock.patch.object(tune, "_current_result_sha256", return_value="b" * 64), mock.patch("builtins.print") as out:
            self.assertEqual(tune._verify(pathlib.Path("unused"), tune._BENCH, rp, BASE_RAW, {}, cands), 1)
        self.assertTrue(any("do not reproduce the adopted run" in str(c) for c in out.call_args_list))
        with mock.patch.object(tune, "_read_log", return_value=[adopted]), mock.patch.object(tune, "_with_state", return_value=[]), \
             mock.patch.object(tune, "_current_result_sha256", return_value="a" * 64), mock.patch("builtins.print"):
            self.assertEqual(tune._verify(pathlib.Path("unused"), tune._BENCH, rp, BASE_RAW, {}, cands), 0)


class TestPipelineResult(unittest.TestCase):
    """Round 4 spec §4.1: ONE pure production orchestration (run_pipeline_result) shared by main() and the pre-T dry-run."""
    PERFECT = staticmethod(lambda point, raw: ({"passed": S, "failed": []}, {"raw_passed": R, "effective_passed": R, "passed": R, "failed": []}))

    def test_run_pipeline_result_fields_and_purity(self):
        res = tune.run_pipeline_result(self.PERFECT, tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE, lambda p, r: [], QUERIES, CLASSES)
        self.assertIsInstance(res, tune.PipelineResult); self.assertTrue(res.tuning_accept); self.assertEqual(res.validation_errors, [])
        self.assertEqual(res.selected_point, BASE); self.assertEqual(res.fixture_result["final"], [])

    def test_tuning_accept_false_when_regression_effective_short(self):
        short = lambda point, raw: ({"passed": S, "failed": []}, {"raw_passed": 10, "effective_passed": R - 1, "passed": R - 1, "failed": [{"id": "rn-001", "query": "q"}]})
        res = tune.run_pipeline_result(short, tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE, lambda p, r: [], QUERIES, CLASSES)
        self.assertFalse(res.tuning_accept)

    def test_main_uses_run_pipeline_result(self):
        import inspect
        src = inspect.getsource(tune.main)
        self.assertIn("run_pipeline_result(", src); self.assertNotIn(" run_pipeline(", src)
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


class TestRound5Wiring(unittest.TestCase):
    """Round 5 plan Task 2 Step 6 pin tests: round identity and the final-policy counterexample built by main."""
    def test_round_identity(self):
        import importlib
        from tests.benchmarks import evaluator as ev
        self.assertEqual(tune.KU, ev.known_unreachable(5))                     # before T: KU from the pending round
        try:
            with mock.patch.object(ev, "load_round_freeze", return_value=[{"round": 1}, {"round": 2}, {"round": 5}]):
                importlib.reload(tune)
                self.assertEqual(tune.ROUND, 5); self.assertEqual(tune.KU, ev.known_unreachable(5))
                self.assertTrue(tune.LOG_REL.endswith("search-tuning-round5.jsonl"))
                self.assertEqual(tune.round_note("w", "s-001", "t")["origin"], "round5")
        finally:
            importlib.reload(tune)

    def test_main_loads_reference(self):
        import tempfile
        from tests.benchmarks import counterexample as cx
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); (root / "tests/benchmarks").mkdir(parents=True)
            ref = {"policy": {"aliases": {"ticket": ["issue"]}, "rules": [], "notes": {}}, "titles": [{"product": "jira", "url": "u", "title": "t"}]}
            (root / "tests/benchmarks/round5-counterexample-reference.json").write_text(json.dumps(ref), encoding="utf-8")
            calls = []
            from tests.benchmarks import evaluator as ev
            with mock.patch.object(cx, "catalog_index", return_value=([], {})), mock.patch.object(cx, "production_top1", return_value="TOP1"), \
                    mock.patch.object(cx, "suite", side_effect=lambda *a, **k: calls.append((a, k)) or {"ok": True}), \
                    mock.patch.object(ev, "load_round_freeze", return_value=[{"round": 2}]):          # wiring only; the freeze binding has its own test
                fn = tune.final_counterexample_fn(object(), policy.load_ranking(), {"aliases": {}}, round=5, root=root)
                fn({"c": 1}, {"aliases": {"x": ["y"]}})
                self.assertIsNone(tune.final_counterexample_fn(object(), policy.load_ranking(), {}, round=4, root=root))
        (a, k), = calls
        self.assertEqual((k["scope"], k["selected_constants"], k["titles"]), ("final_policy", {"c": 1}, ref["titles"]))
        self.assertEqual((a[1], a[2], a[3], a[4]), ("TOP1", ref["policy"], {"aliases": {}}, {"aliases": {"x": ["y"]}}))


class TestRound5ReviewFixes(unittest.TestCase):
    """Round 5 whole-branch review fixes (Important 1, Important 2)."""
    def test_replay_proposer_never_sees_ku(self):
        seen = []
        def eval_fn(raw):
            return frozenset({"s-004", "s-028"}), frozenset()
        def fake_propose(eval_fn, bench, base, cands, fixture_fn=None):
            seen.append(eval_fn(base)[0]); return base, {"aliases": {}, "rules": [], "notes": {}}
        with mock.patch.object(tune, "propose_aliases", fake_propose), mock.patch.object(tune, "KU", frozenset({"s-004"})):
            tune.verify_replay(eval_fn, {"seed": []}, {"aliases": {}, "rules": [], "notes": {}}, {}, {}, "x")
        self.assertEqual(seen, [frozenset({"s-028"})])

    def test_counterexample_reference_bound_to_freeze(self):
        import tempfile
        from tests.benchmarks import counterexample as cx, evaluator as ev
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); (root / "tests/benchmarks").mkdir(parents=True)
            f = root / "tests/benchmarks/round5-counterexample-reference.json"
            f.write_text(json.dumps({"policy": {"aliases": {}, "rules": [], "notes": {}}, "titles": []}), encoding="utf-8")
            good = ev.file_sha256(f)
            with mock.patch.object(cx, "catalog_index", return_value=([], {})):
                with mock.patch.object(ev, "load_round_freeze", return_value=[{"round": 5, "counterexample_reference_sha256": "0" * 64}]):
                    with self.assertRaises(SystemExit):
                        tune.final_counterexample_fn(object(), policy.load_ranking(), {}, round=5, root=root)
                with mock.patch.object(ev, "load_round_freeze", return_value=[{"round": 5, "counterexample_reference_sha256": good}]):
                    self.assertIsNotNone(tune.final_counterexample_fn(object(), policy.load_ranking(), {}, round=5, root=root))
                with mock.patch.object(ev, "load_round_freeze", return_value=[{"round": 2}]):           # before T: nothing frozen yet
                    self.assertIsNotNone(tune.final_counterexample_fn(object(), policy.load_ranking(), {}, round=5, root=root))


class TestRound5CarriedCandidates(unittest.TestCase):
    def test_proposer_never_reads_carried_candidates(self):
        seen = []
        def fake_propose(eval_fn, bench, base, cands, fixture_fn=None):
            seen.append(set(cands)); return base, {"aliases": {}, "rules": [], "notes": {}}
        consts = json.loads(tune.RANKING_PATH.read_text(encoding="utf-8"))["constants"]
        grid = {k: [v] for k, v in consts.items()}
        ev_fn = lambda p, r: ({"passed": 39, "failed": [], "total": 39}, {"passed": 14, "failed": [], "effective_passed": 14, "raw_passed": 10})
        doc = {"candidates": {"hour": {"targets": ["time"]}}, "carried_candidates": {"feedback": {"targets": ["comment"]}}}
        with mock.patch.object(tune, "propose_aliases", fake_propose):
            tune.run_pipeline(ev_fn, {"seed": []}, {"aliases": {}, "rules": [], "notes": {}}, doc, grid, dict(consts), lambda p, r: [])
        self.assertEqual(seen, [{"hour"}])
