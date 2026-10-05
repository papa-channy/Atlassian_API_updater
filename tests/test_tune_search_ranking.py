import json
import pathlib
import unittest
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
BENCH2 = {"seed": [{"id": "s-001", "query": "browse pages inside this workspace", "failure_classes": ["R6"]},
                   {"id": "s-002", "query": "leave feedback on this ticket", "failure_classes": ["R5", "R6"]},
                   {"id": "s-003", "query": "read feedback on the issue", "failure_classes": ["R6"]}], "regression_negative": [{"id": "rn-001", "query": "x"}]}
QUERIES = {r["id"]: r["query"] for r in BENCH2["seed"]}
CLASSES = {r["id"]: r["failure_classes"] for r in BENCH2["seed"]}


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

    def test_seed_without_r6_is_skipped(self):
        """Review I-1 (s-014 "fetch page by id" shape): a failing seed whose bench classes lack R6 never gets a change."""
        bench = json.loads(json.dumps(BENCH2)); bench["seed"][0]["failure_classes"] = ["R5"]
        fn = fake_eval({("workspace", "page"): ["s-001"], ("feedback", "comment"): ["s-002", "s-003"]})
        _, patch = tune.propose_aliases(fn, bench, BASE_RAW, CANDS)
        self.assertEqual(patch["aliases"], {"feedback": ["comment"]}); self.assertEqual(patch["not_r6"], ["s-001"])
        self.assertEqual(patch["trials"], 1)                                  # no trial was spent on s-001

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
        return tune.validate_alias_change(BASE_RAW, after, CANDS, QUERIES, CLASSES, **kw)

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
        not_r6 = self.after(workspace=("page", "s-001"))
        self.assertTrue(any("not R6" in m for m in tune.validate_alias_change(BASE_RAW, not_r6, CANDS, QUERIES, {**CLASSES, "s-001": ["R5"]})))
        bad_note = self.after(workspace=("page", "s-001")); bad_note["notes"]["workspace"]["failure_classes"] = []
        self.assertTrue(any("not R6" in m for m in self.v(bad_note)))
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
        self.assertEqual(ev_sig["exit_code"], 1)                                                   # from unittest's FAILED summary
        self.assertEqual(tune.suite_evidence("Ran 3 tests\n\nOK\n")["failing_tests"], [])
        self.assertEqual(tune.suite_evidence("Ran 3 tests\n\nOK\n")["exit_code"], 0)
        self.assertEqual(tune.suite_evidence(text + "exit_code: 3\n")["exit_code"], 3)            # explicit capture line wins (M-8)
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
            tune.run_pipeline(lambda point, raw: ({"passed": S, "failed": []}, {"passed": R, "failed": []}), tune._BENCH, BASE_RAW, {"candidates": {}}, GRID, BASE,
                              lambda point, raw: [])
        self.assertEqual(calls, ["select", "propose"])


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
        self.assertEqual(patch["fixture_fail"], [{"kind": "alias", "word": "workspace", "target": "page", "seed_query_id": "s-001", "failing": ["s-022"]}])
        self.assertEqual(tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS, fixture_fn=breaks)[1], patch)
        _, unconstrained = tune.propose_aliases(fn, BENCH2, BASE_RAW, CANDS)
        self.assertEqual(unconstrained["aliases"]["workspace"], ["page"])                          # the constraint made the difference

    def test_real_fixture_suite_rejects_a_synthetic_breaking_alias(self):
        """On the real fixtures: the live policy passes the r0 suite (23/6), a synthetic alias summary -> create breaks s-022."""
        rp = policy.load_ranking(); state, fb = tune.fixture_state(), tune.fixture_bench(tune._BENCH)
        self.assertEqual((len(fb["seed"]), len(fb["regression_negative"])), (23, 6))
        raw = json.loads(tune.ALIASES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(tune.fixture_failures(state, rp, dict(rp.constants), fb, tune._alias_policy(raw)), [])
        raw["aliases"]["summary"] = ["create"]
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
