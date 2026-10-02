import copy, json, unittest
from tests.benchmarks import alias_candidates_tool as act
from tests.benchmarks.test_round_seal import CAT, A, B, C, D, E, F, G, H

WS = {"key": "jira-platform:GET:/rest/api/3/workspace", "source": "jira-platform", "method": "GET", "operation_id": "getLinkedWorkspaces",
      "summary": "Get linked workspaces", "tags": ["Workspaces"], "description": "x"}
CAT2 = CAT + [WS]
VERBS = {"get": ["GET"], "browse": ["GET"], "create": ["POST"], "delete": ["DELETE"], "list": ["GET"], "publish": ["POST"]}
RANK = {"verb_methods": VERBS, "path_noise": ["rest", "api", "agile"], "product_hints": {"jira": ["jira-platform"], "confluence": ["confluence"]}}
ALIASES = {"aliases": {"ticket": ["issue"]}, "rules": [{"when_all": ["issue", "key"], "add": ["getissue"]}], "notes": {}}


def seed(i, q, key, fc=()):
    return {"id": f"s-{i:03d}", "query": q, "expected_top1_any": [key], "forbidden_top1": [], "origin": "seed-r0",
            "failure_classes": list(fc), "ambiguous": False}


BENCH = {"seed": [seed(1, "browse pages inside this workspace", G), seed(2, "get issue by key", A),
                  seed(3, "publish a brand new document", B), seed(4, "create and delete the issue", C)],
         "regression_negative": []}
BY_KEY = {r["key"]: r for r in CAT2}


class TestTokens(unittest.TestCase):
    def test_norm_tokens_singular_and_order(self):
        self.assertEqual(act.norm_tokens("Browse the Pages workspaces files"), ("browse", "page", "workspace", "file"))

    def test_concept_tokens_from_paths_and_tags(self):
        ct = act.concept_tokens(CAT2, frozenset(RANK["path_noise"]))
        self.assertIn("issue", ct); self.assertIn("page", ct); self.assertNotIn("rest", ct)
        self.assertEqual(ct["sprint"]["sources"], ["jira-software"]); self.assertGreaterEqual(ct["issue"]["count"], 3)

    def test_verb_report_flags_methods_outside_inventory(self):
        rep = act.verb_report(CAT2, {"get": ["POST"], "create": ["POST"]})
        self.assertTrue(rep["get"]["review"]); self.assertIn("GET", rep["get"]["outside"])
        self.assertFalse(rep["create"]["review"])


class TestMethodSafety(unittest.TestCase):
    def test_allowed_methods(self):
        self.assertIsNone(act.allowed_methods("show me the ticket", VERBS))
        self.assertEqual(act.allowed_methods("get issue", VERBS), frozenset({"GET"}))
        self.assertEqual(act.allowed_methods("create and delete the issue", VERBS), frozenset())

    def test_method_safety_conflicting_verbs_is_intent_zero(self):
        rows = {r["id"]: r for r in act.method_safety(BENCH, VERBS)}
        self.assertTrue(rows["s-004"]["ok"]); self.assertEqual(rows["s-004"]["allowed"], [])
        self.assertTrue(rows["s-002"]["ok"]); self.assertTrue(rows["s-001"]["ok"])
        bad = act.method_safety({"seed": [seed(9, "get the page", B)]}, VERBS)[0]   # GET verb, POST target
        self.assertFalse(bad["ok"]); self.assertEqual(bad["expected_methods"], ["POST"])


class TestCandidates(unittest.TestCase):
    def test_expected_vocab_excludes_verbs_noise_hints_ids(self):
        v = act.expected_vocab(BENCH["seed"][1], BY_KEY, VERBS, frozenset(RANK["path_noise"]), RANK["product_hints"])
        self.assertIn("issue", v); self.assertNotIn("get", v); self.assertNotIn("rest", v); self.assertNotIn("id", v); self.assertNotIn("key", v)

    def test_candidate_relative_to_expected_vocab_not_global_catalog(self):
        doc = act.candidates(BENCH, CAT2, RANK, ALIASES)
        c = doc["candidates"]
        self.assertIn("workspace", c); self.assertEqual(c["workspace"]["catalog_df"], 1)      # in the catalog, still a candidate
        self.assertEqual(c["workspace"]["seed_ids"], ["s-001"]); self.assertIn("page", c["workspace"]["targets_by_seed"]["s-001"])
        self.assertEqual(c["workspace"]["allowed_targets"], c["workspace"]["targets_by_seed"]["s-001"])
        self.assertIn("document", c); self.assertIn("page", c["document"]["allowed_targets"])
        self.assertNotIn("inside", c); self.assertNotIn("this", c); self.assertNotIn("brand", c)      # function words
        self.assertNotIn("browse", c); self.assertNotIn("issue", c); self.assertNotIn("key", c)      # verb / expected vocab
        self.assertEqual(doc["excluded"]["browse"], "verb"); self.assertEqual(doc["excluded"]["inside"], "function_word")
        self.assertEqual(json.dumps(doc, sort_keys=True), json.dumps(act.candidates(BENCH, CAT2, RANK, ALIASES), sort_keys=True))

    def test_identifier_and_existing_alias_excluded(self):
        b = {"seed": [seed(5, "getissue for my ticket", A)], "regression_negative": []}
        doc = act.candidates(b, CAT2, RANK, ALIASES)
        self.assertEqual(doc["candidates"], {}); self.assertEqual(doc["excluded"]["getissue"], "identifier")
        self.assertEqual(doc["excluded"]["ticket"], "existing_alias")

    def test_classify_r5_r6(self):
        cls = act.classify(BENCH, CAT2, RANK, ALIASES)
        self.assertEqual(cls["s-001"], ["R6"]); self.assertEqual(cls["s-002"], [])      # key is id-like, not R6
        self.assertEqual(cls["s-004"], ["R5"])                      # conflicting verbs -> no expected method covered
        no_verb = {"seed": [seed(7, "ticket details overview", A)], "regression_negative": []}
        self.assertEqual(act.classify(no_verb, CAT2, RANK, ALIASES)["s-007"], ["R5", "R6"])   # ticket is an alias; details/overview are not

    def test_classify_recognizes_identifiers_like_candidates_does(self):
        b = {"seed": [seed(5, "getissue for my ticket", A)], "regression_negative": []}
        # getissue is an identifier (candidates() excludes it as "identifier"); ticket is an existing alias.
        # No inventory verb present -> R5 stays, but neither token should trigger R6.
        self.assertEqual(act.classify(b, CAT2, RANK, ALIASES)["s-005"], ["R5"])

    def test_candidates_exclude_what_classify_treats_as_known(self):
        """Review I-1: s-014 "fetch page by id" - id is id-like, so it is neither a candidate nor an R6 trigger."""
        b = {"seed": [seed(14, "fetch page by id", G), seed(15, "list rest api 2024 boards", D)], "regression_negative": []}
        verbs = {**VERBS, "fetch": ["GET"]}
        doc = act.candidates(b, CAT2, {**RANK, "verb_methods": verbs}, ALIASES)
        self.assertEqual(doc["candidates"], {})
        self.assertEqual(doc["excluded"]["id"], "id_like"); self.assertEqual(doc["excluded"]["rest"], "path_noise")
        self.assertEqual(doc["excluded"]["2024"], "digit")
        cls = act.classify(b, CAT2, {**RANK, "verb_methods": verbs}, ALIASES)
        self.assertEqual((cls["s-014"], cls["s-015"]), ([], []))
        for bench in (BENCH, b):                          # a seed has a candidate word iff classify marks it R6
            d, c = act.candidates(bench, CAT2, RANK, ALIASES), act.classify(bench, CAT2, RANK, ALIASES)
            with_cand = {sid for w in d["candidates"].values() for sid in w["seed_ids"]}
            self.assertEqual(with_cand, {sid for sid, k in c.items() if "R6" in k})


class TestLexiconGate(unittest.TestCase):
    def test_gate_keeps_compatible_and_rejects_incompatible(self):
        lex = {"lexicon": {"workspace": ["page"], "document": ["issue"], "note": ["comment"]}, "rejected": {}}
        out, rejected = act.lexicon_gate(copy.deepcopy(lex), BENCH, BY_KEY, RANK)
        self.assertIn("workspace", out["lexicon"]); self.assertNotIn("document", out["lexicon"]); self.assertIn("note", out["lexicon"])
        self.assertEqual(out["rejected"]["document"]["reason"], "seed-incompatible"); self.assertEqual(rejected, ["document"])
