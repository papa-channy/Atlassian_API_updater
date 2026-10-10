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

    def test_lexicon_only_validation_error_is_a_blocker(self):
        lex = {"scope": "lexicon_only", "ok": False, "losses": [], "classes": {"uncovered_proposer": []}, "validation_errors": ["counterexample_diagnostic_incomplete"]}
        b = sim.pre_t_blockers(self._res([]), {"pass": True}, lexicon_cx=lex)
        self.assertEqual([x["kind"] for x in b], ["alias_validation_error"]); self.assertEqual(b[0]["errors"][0]["scope"], "lexicon_only")

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
                    "titles": [], "titles_sha256": ev.canonical_sha256([]),
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


class TestRound5RegistryAgainstStart(unittest.TestCase):
    def test_live_bench_matches_start_commit_identity(self):
        """The real 56b4b0e records (pre-T path): reclassified failure_classes in the live bench never trip the KU check."""
        import subprocess
        r = subprocess.run(["git", "show", "56b4b0e:tests/benchmarks/search_queries.json"], cwd=sim.ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            self.skipTest("round 5 start commit 56b4b0e not in this tree's history (simulation archive tree)")
        base = json.loads(r.stdout)
        bench = json.loads((pathlib.Path(sim.ROOT) / "tests/benchmarks/search_queries.json").read_text(encoding="utf-8"))
        doc = json.loads((pathlib.Path(sim.ROOT) / "tests/benchmarks/round5-known-unreachable.json").read_text(encoding="utf-8"))
        self.assertEqual(sim.registry_blockers(bench, base, doc), [])
        changed = json.loads(json.dumps(bench)); next(r for r in changed["seed"] if r["id"] == "s-039")["expected_top1_any"] = ["x:GET:/y"]
        self.assertEqual([b["kind"] for b in sim.registry_blockers(changed, base, doc)], ["ku_record_mismatch"])
