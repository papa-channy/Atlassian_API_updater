import copy, json, unittest
from tests.benchmarks import alias_candidates_tool as act
from tests.benchmarks.evaluator import canonical_sha256
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
    def test_expected_vocab_is_resource_evidence_minus_function_noise_id(self):
        """Round 3 spec §6: targets must appear in the expected op's path/terminal/tag tokens; verbs and hint keys are allowed."""
        op = {"key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment", "source": "jira-platform", "method": "POST",
              "operation_id": "addComment", "summary": "Add comment", "tags": ["Issue comments"]}
        rec = {"expected_top1_any": [op["key"]]}
        self.assertEqual(act.resource_vocab(op), frozenset({"rest", "api", "issue", "comment"}))
        vocab = act.expected_vocab(rec, {op["key"]: op}, ["rest", "api"])
        self.assertEqual(vocab, frozenset({"issue", "comment"}))                       # comment is a verb-inventory key and still a target
        self.assertNotIn("add", vocab)                                                   # summary/operationId words are not resource evidence
        sprint = {"key": "jira-software:POST:/rest/agile/1.0/sprint", "source": "jira-software", "method": "POST", "operation_id": "createSprint",
                  "summary": "Create sprint", "tags": ["Sprint"]}
        self.assertEqual(act.expected_vocab({"expected_top1_any": [sprint["key"]]}, {sprint["key"]: sprint}, ["rest", "agile"]), frozenset({"sprint"}))   # hint key allowed; "1.0" dropped (digits), "create" absent

    def test_resource_vocab_targets_on_real_fixtures(self):
        from tests.benchmarks import round_seal as rs
        from tests.intelligence.helpers import make_state
        state = make_state("jira-platform", "jira-software", "confluence")
        internal = {op.key: rs._catalog_record(op) for sr in state.registry.sources.values() for op in sr.operations}
        noise = ["rest", "api", "agile", "software", "wiki"]
        ev_ = lambda key: act.expected_vocab({"expected_top1_any": [key]}, internal, noise)
        self.assertIn("comment", ev_("jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment"))     # feedback -> comment (s-024 shape)
        self.assertIn("sprint", ev_("jira-software:POST:/rest/agile/1.0/sprint"))                         # iteration -> sprint (s-032 shape)
        self.assertIn("post", ev_("confluence:POST:/blogposts"))                                           # blog entry -> post via tag "Blog Post"
        for key in ("jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment", "confluence:POST:/blogposts"):
            self.assertFalse({"get", "create", "add", "rest", "api", "id"} & ev_(key), key)                 # pure action tokens / noise / id-like never qualify

    def test_allowed_methods_is_the_production_helper(self):
        from tools.atlassian_docs.intelligence import search
        vm = {"get": ["GET"], "delete": ["DELETE"], "change": ["PUT", "POST"], "add": ["POST"]}
        for q in ("get the issue", "issue status", "get and delete issue", "change add x"):
            self.assertEqual(act.allowed_methods(q, vm), search.method_intent(search.tokenize_unigrams(q), vm)[1], q)
        self.assertIsNone(act.allowed_methods("issue status", vm)); self.assertEqual(act.allowed_methods("get and delete issue", vm), frozenset())

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

    def test_lexicon_gate_phrase_requires_both_tokens_in_seed(self):                                # Round 3 spec §6 (v1.24)
        internal = [{"key": "jira-platform:GET:/rest/api/3/issue/{issueIdOrKey}/worklog", "source": "jira-platform", "method": "GET",
                     "operation_id": "getIssueWorklog", "summary": "Get issue worklogs", "tags": ["Issue worklogs"]},
                    {"key": "confluence:GET:/pages", "source": "confluence", "method": "GET", "operation_id": "getPages", "summary": "Get pages", "tags": ["Page"]}]
        by_key = {op["key"]: op for op in internal}
        bench = {"seed": [{"id": "s-001", "query": "show time entries for ticket", "expected_top1_any": [internal[0]["key"]], "failure_classes": []}]}
        doc = {"lexicon": {"time entry": ["worklog"], "blog entry": ["page"]}, "rejected": {}, "catalog_df": {}}
        doc, rejected = act.lexicon_gate(doc, bench, by_key, RANK)
        self.assertEqual(rejected, [])                       # 'time entry' targets the seed's vocabulary; no seed contains both 'blog' and 'entry'
        doc2 = {"lexicon": {"time entry": ["page"]}, "rejected": {}, "catalog_df": {}}
        doc2, rejected2 = act.lexicon_gate(doc2, bench, by_key, RANK)
        self.assertEqual(rejected2, ["time entry"]); self.assertEqual(doc2["rejected"]["time entry"]["reason"], "seed-incompatible")

    def test_lexicon_gate_seed_regression_check(self):                                              # spec §6 v1.25
        internal = [{"key": "confluence:PUT:/blogposts/{id}", "source": "confluence", "method": "PUT", "operation_id": "updateBlogPost", "summary": "Update blog post", "tags": ["Blog Post"]},
                    {"key": "jira-platform:GET:/rest/api/3/issue/{issueIdOrKey}/worklog", "source": "jira-platform", "method": "GET", "operation_id": "getIssueWorklog", "summary": "Get issue worklogs", "tags": ["Issue worklogs"]}]
        by_key = {op["key"]: op for op in internal}
        bench = {"seed": [{"id": "s-036", "query": "rewrite this wiki blog entry", "expected_top1_any": [internal[0]["key"]], "failure_classes": []},
                          {"id": "s-030", "query": "show time entries for ticket", "expected_top1_any": [internal[1]["key"]], "failure_classes": []}]}
        calls = []
        def check(syn, targets, seeds):
            calls.append((syn, tuple(targets), tuple(r["id"] for r in seeds)))
            return syn == "blog entry"                                                               # merging it flips s-036 from pass to fail
        doc = {"lexicon": {"blog entry": ["post"], "time entry": ["worklog"], "unrelated": ["page"], "wiki blog": ["issue"]}, "rejected": {}, "catalog_df": {}}
        doc, rejected = act.lexicon_gate(doc, bench, by_key, RANK, regression_check=check)
        self.assertEqual(rejected, ["blog entry", "wiki blog"])
        self.assertEqual(doc["rejected"]["blog entry"]["reason"], "seed-regression"); self.assertEqual(doc["rejected"]["wiki blog"]["reason"], "seed-incompatible")
        self.assertEqual(sorted(doc["lexicon"]), ["time entry", "unrelated"])
        self.assertEqual(calls, [("blog entry", ("post",), ("s-036",)), ("time entry", ("worklog",), ("s-030",))])   # only vocab-passing entries with seeds are checked


class TestVerbPrefixInvariant(unittest.TestCase):
    """AC-R3-12: the live inventory keeps Round 2's rows and each Round 2 list as an exact prefix; suffixes sorted."""
    def test_live_inventory_satisfies_prefix_invariant(self):
        base = act.round2_verb_inventory()
        self.assertEqual(canonical_sha256(base), "d66317db7a6a3d047f30197791eefdb93448747b913544da7545136f91dbffc0")   # Round 2 verb_inventory_sha256
        live = json.loads((act.DATA / "search_ranking.json").read_text(encoding="utf-8"))["verb_methods"]
        self.assertEqual(act.verb_prefix_violations(base, live), [])

    def test_verb_prefix_invariant_rejects_reorder_and_truncation(self):                                   # review focus 5
        base = {"change": ["PUT", "POST"], "get": ["GET"], "leave": ["POST", "DELETE"]}
        self.assertEqual(act.verb_prefix_violations(base, {"change": ["PUT", "POST", "DELETE"], "get": ["GET"], "leave": ["POST", "DELETE"]}), [])
        self.assertTrue(act.verb_prefix_violations(base, {"change": ["POST", "PUT"], "get": ["GET"], "leave": ["POST", "DELETE"]}))       # same set, reordered
        self.assertTrue(act.verb_prefix_violations(base, {"change": ["PUT"], "get": ["GET"], "leave": ["POST", "DELETE"]}))              # truncated
        self.assertTrue(act.verb_prefix_violations(base, {"change": ["PUT", "POST"], "get": ["GET"]}))                                   # row removed
        self.assertTrue(act.verb_prefix_violations(base, {**base, "zz": ["GET"]}))                                                       # row added
        self.assertTrue(act.verb_prefix_violations(base, {**base, "get": ["GET", "POST", "DELETE"]}))                                    # suffix not sorted
        self.assertEqual(act.verb_prefix_violations(base, {**base, "get": ["GET", "DELETE", "POST"]}), [])
