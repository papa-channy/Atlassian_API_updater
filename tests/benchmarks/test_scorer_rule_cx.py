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
