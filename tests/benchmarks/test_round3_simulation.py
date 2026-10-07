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


if __name__ == "__main__":
    unittest.main()


class TestSyntheticLexiconPhrase(unittest.TestCase):
    def test_synthetic_T_merges_a_phrase_rule(self):
        """v1.24: the synthetic lexicon-r3 merge exercises the phrase -> when_all rule path and its lexicon-r3 rule note."""
        from tests.benchmarks import concept_lexicon_check as clc, round3_simulation as sim
        aliases = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {}, "rules": [], "notes": {}}
        out, skipped = clc.merge(aliases, {sim.LEXICON_WORD: [sim.LEXICON_TARGET], sim.LEXICON_PHRASE: [sim.LEXICON_PHRASE_TARGET]}, sim.ROUND)
        self.assertEqual(skipped, []); self.assertEqual(out["rules"], [{"when_all": ["zzalpha", "zzbeta"], "add": ["issue"]}])
        self.assertEqual(out["notes"]["rule:0"]["origin"], "lexicon-r3"); self.assertIn(sim.LEXICON_WORD, out["aliases"])
