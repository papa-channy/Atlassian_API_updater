import json
import pathlib
import unittest
from tests import tune_search_ranking as tune
from tools.atlassian_docs.intelligence import policy

GRID = {"method_match_bonus": [1.0, 2.0, 3.0], "method_mismatch_penalty": [0.0, 1.0, 2.0, 3.0], "path_unmatched_penalty": [0.5, 1.0, 1.5, 2.0],
        "path_unmatched_cap": [2, 3, 4], "product_hint_bonus": [2.0, 3.0, 4.0],
        "resource_match_bonus": [6.0, 8.0, 10.0, 12.0]}
BASE = {"method_match_bonus": 2.0, "method_mismatch_penalty": 2.0, "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0, "resource_match_bonus": 10.0}
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
        self.assertEqual(len(pts), 1728); self.assertEqual(pts, sorted(pts, key=lambda p: tuple(p[k] for k in tune.CONSTANT_KEYS)))
        self.assertEqual(len(tune.grid_points(policy.load_ranking().tuning_grid)), 1728)   # the loaded (frozen) grid

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
                "aliases_proposed": {"aliases": {"workspace": ["page"]}, "rules": [], "notes": {"workspace": tune.round2_note("workspace", "s-001", "page", "alias")}}}
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
        self.assertEqual(tune.suite_evidence("Ran 3 tests\n\nOK\n")["failing_tests"], [])
        line = {"constants_selected": {**BASE, "method_match_bonus": 3.0}, "aliases_proposed": {"aliases": {"workspace": ["page"]}, "rules": [], "notes": {"workspace": tune.round2_note("workspace", "s-001", "page", "alias")}}}
        ranking, aliases = tune.materialize_candidate(line, BASE_RAW, {"constants": dict(BASE), "version": 1})
        self.assertEqual(ranking["constants"]["method_match_bonus"], 3.0); self.assertEqual(aliases["aliases"]["workspace"], ["page"])
        self.assertEqual(tune.alias_patch(BASE_RAW, aliases), line["aliases_proposed"])
        self.assertEqual(tune.result_sha256(ranking["constants"], tune.alias_patch(BASE_RAW, aliases)), tune.result_sha256(line["constants_selected"], line["aliases_proposed"]))

    def test_pipeline_calls_selector_once_then_proposer_once(self):
        from unittest import mock
        calls = []
        with mock.patch.object(tune, "select_candidate", side_effect=lambda *a, **k: calls.append("select") or dict(BASE)), \
             mock.patch.object(tune, "propose_aliases", side_effect=lambda *a, **k: calls.append("propose") or (json.loads(json.dumps(BASE_RAW)), {"aliases": {}, "rules": {}, "notes": {}, "resolved_by_prior_change": [], "unresolved": [], "trials": 0})):
            tune.run_pipeline(lambda point, raw: ({"passed": S, "failed": []}, {"passed": R, "failed": []}), tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE)
        self.assertEqual(calls, ["select", "propose"])
