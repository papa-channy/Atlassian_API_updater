import json, pathlib, tempfile, unittest
from unittest import mock
from tests.benchmarks import round4_simulation as sim, round_seal as rs, doc_titles as dt, evaluator as ev
from tests.test_diag_search_queries import build_fixture_cache


class TestPreTBlockers(unittest.TestCase):
    """Round 4 spec §4.1: the four blocker kinds are computed independently from the dry-run PipelineResult."""
    def _res(self, seed_failed=(), reg_eff=14, fixture_final=(), errors=()):
        import tests.tune_search_ranking as tune
        return tune.PipelineResult({}, {}, list(errors), {"passed": 39 - len(seed_failed), "failed": [{"id": i} for i in seed_failed]},
                                   {"raw_passed": 12, "effective_passed": reg_eff, "failed": [{"id": "rn-001"}] if reg_eff < 14 else []},
                                   {"constants": [], "final": list(fixture_final)},
                                   not seed_failed and reg_eff == 14 and not fixture_final and not errors)

    def test_no_blockers_when_pipeline_accepts(self):
        self.assertEqual(sim.pre_t_blockers(self._res(), {"pass": True}), [])

    def test_unreachable_seed_and_tuning_accept_false_are_distinct_blockers(self):
        b = sim.pre_t_blockers(self._res(seed_failed=["s-027"]), {"pass": True})
        self.assertEqual([x["kind"] for x in b], ["unreachable_seed"]); self.assertEqual(b[0]["seeds"], ["s-027"])
        b2 = sim.pre_t_blockers(self._res(reg_eff=13), {"pass": True}); self.assertEqual([x["kind"] for x in b2], ["tuning_accept_false"])
        self.assertEqual(b2[0]["invariants"]["regression_failed"], ["rn-001"])
        b3 = sim.pre_t_blockers(self._res(errors=["budget exceeded"]), {"pass": True}); self.assertEqual([x["kind"] for x in b3], ["alias_validation_error"])
        b4 = sim.pre_t_blockers(self._res(), {"pass": False}); self.assertEqual([x["kind"] for x in b4], ["inherited_ac_r3_01_failure"])
        both = sim.pre_t_blockers(self._res(seed_failed=["s-027"], reg_eff=13, errors=["budget exceeded"]), {"pass": False})
        self.assertEqual([x["kind"] for x in both], ["unreachable_seed", "tuning_accept_false", "alias_validation_error", "inherited_ac_r3_01_failure"])

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

    def test_pre_t_terminal_needs_checkpoint_and_a_decision_after_it(self):
        with tempfile.TemporaryDirectory() as td:
            w = self._w(td, {"event": "user_decision", "decision": "TERMINAL_PRE_T_NOT_REACHED"})                       # decision but no checkpoint
            with self.assertRaises(SystemExit): sim.append_outcome(w, {"round": 4, "outcome": "pre-T not reached"}, outcomes_path=w / "o.json", freeze=self.F12)
            (w / "controller-events.jsonl").open("a").write(json.dumps({"event": "pre_t_checkpoint", "result": "stop_for_amendment"}) + "\n")   # stale decision before a new checkpoint
            with self.assertRaises(SystemExit): sim.append_outcome(w, {"round": 4, "outcome": "pre-T not reached"}, outcomes_path=w / "o.json", freeze=self.F12)

    def test_aborted_pre_b_needs_the_real_freeze_entry(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as td2:
            w = self._w(td)
            sim.append_outcome(w, dict(self.ABORT), outcomes_path=w / "o.json", freeze=self.F124)                                  # freeze 4 present → ok
            w2 = self._w(td2)
            with self.assertRaises(ValueError): sim.append_outcome(w2, dict(self.ABORT), outcomes_path=w2 / "o.json", freeze=self.F12)   # orphan abort → refused

    def test_apply_outcome_cli_uses_repo_freeze(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ev, "load_round_freeze", return_value=self.F124), mock.patch.object(ev, "OUTCOMES", pathlib.Path(td, "o.json")):
            w = self._w(td); self.assertEqual(sim.main(["--apply-outcome", json.dumps(self.ABORT), "--work", str(w)]), 0)
            self.assertEqual(ev.load_round_outcomes(pathlib.Path(td, "o.json"))[-1]["outcome"], "aborted-pre-B")


class TestPreTVerdict(unittest.TestCase):
    def test_thresholds(self):
        self.assertTrue(sim.pre_t_verdict(36, 10, 14, [])); self.assertFalse(sim.pre_t_verdict(35, 10, 14, []))

    def test_event_shape(self):
        e = sim.pre_t_event({"passed": 36}, {"raw_passed": 10, "effective_passed": 14}, [], {"ranking_sha256": "a"}, at="2026-10-09T00:00:00Z")
        self.assertEqual(e["event"], "pre_t_checkpoint"); self.assertTrue(e["pass"])


class TestSyntheticHidden(unittest.TestCase):
    def test_synthetic_records_pass_round4_machine_check_on_fixture_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            cache = pathlib.Path(td) / "cache"; build_fixture_cache(cache)
            _, internal, _, _ = rs.load_catalogs_from_cache(cache, 4)
        vm = json.loads((sim.ROOT / "tools/atlassian_docs/intelligence/data/search_ranking.json").read_text(encoding="utf-8"))["verb_methods"]
        plain = sim.synthetic_hidden_records(internal, vm)
        bench = json.loads((sim.ROOT / "tests/benchmarks/search_queries.json").read_text(encoding="utf-8"))
        self.assertEqual(rs.machine_check(plain, bench, internal, round=4, verb_methods=vm), [])
        self.assertEqual(rs.negative_distribution(plain["negative"], vm), (4, 4))


class TestSyntheticLexiconPhrase(unittest.TestCase):
    def test_synthetic_T_merges_a_phrase_rule(self):
        from tests.benchmarks import concept_lexicon_check as clc
        aliases = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {}, "rules": [], "notes": {}}
        out, skipped = clc.merge(aliases, {sim.LEXICON_WORD: [sim.LEXICON_TARGET], sim.LEXICON_PHRASE: [sim.LEXICON_PHRASE_TARGET]}, sim.ROUND)
        self.assertEqual(skipped, []); self.assertEqual(out["rules"], [{"when_all": ["zzalpha", "zzbeta"], "add": ["issue"]}])
        self.assertEqual(out["notes"]["rule:0"]["origin"], "lexicon-r4"); self.assertIn(sim.LEXICON_WORD, out["aliases"])


class TestXpreBStates(unittest.TestCase):
    def test_xpreb_states_3_4_5_pass_terminal_validation(self):
        """spec §9.4 states (3), (4), (5) each leave a validate-terminal-clean tree; the sealed plaintext is ledgered before deletion."""
        for state in (3, 4, 5):
            with tempfile.TemporaryDirectory() as td:
                problems, ledgered_before_delete = sim.simulate_xpreb_in_temp_tree(pathlib.Path(td), state)
                self.assertEqual(problems, [], state); self.assertTrue(ledgered_before_delete, state)
