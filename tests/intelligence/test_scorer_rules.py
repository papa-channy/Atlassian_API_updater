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
