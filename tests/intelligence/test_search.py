import unittest

from tests.intelligence.helpers import load_fixture, make_state
from tools.atlassian_docs.intelligence import normalizer, search


class TestTokenize(unittest.TestCase):
    def test_camel_case_and_path(self):
        self.assertEqual(search.tokenize("issueIdOrKey"), frozenset({"issue", "id", "key"}))  # "or" is a stopword
        self.assertTrue({"rest", "api", "issue", "id", "key", "attachments", "attachment"}
                        <= search.tokenize("/rest/api/3/issue/{issueIdOrKey}/attachments"))

    def test_acronyms_and_digits(self):
        self.assertEqual(search.tokenize("OAuth2"), frozenset({"oauth2"}))
        self.assertEqual(search.tokenize("JQLQuery"), frozenset({"jql", "query"}))
        self.assertEqual(search.tokenize("IssueCreateMetadata"), frozenset({"issue", "create", "metadata"}))

    def test_plural_variants(self):
        self.assertEqual(search.tokenize("statuses"), frozenset({"statuses", "status"}))
        self.assertEqual(search.tokenize("status"), frozenset({"status"}))
        self.assertEqual(search.tokenize("process"), frozenset({"process"}))
        self.assertEqual(search.tokenize("analysis"), frozenset({"analysis"}))
        self.assertEqual(search.tokenize("issues"), frozenset({"issues", "issue"}))

    def test_singular_contract(self):
        cases = {"properties": "property", "queries": "query", "statuses": "status", "status": "status", "access": "access",
                 "issues": "issue", "databases": "database", "schemes": "scheme", "boards": "board", "classes": "class",
                 "series": "series", "news": "news", "jsis": "jsis", "id": "id"}
        for word, want in cases.items():
            self.assertEqual(search.singular(word), want, word)

    def test_unigrams_forms_and_joined(self):
        self.assertEqual(search.tokenize_unigrams("Get the issueIdOrKey properties"), ("get", "issue", "id", "key", "properties"))
        self.assertEqual(search.token_forms("properties"), frozenset({"properties", "property"}))
        self.assertEqual(search.expand_token_forms(("issues", "get")), frozenset({"issues", "issue", "get"}))
        self.assertEqual(search.joined_query_forms("IssueCreateMetadata get"), frozenset({"issuecreatemetadata"}))
        self.assertEqual(search.joined_query_forms("issue attachment"), frozenset())
        self.assertEqual(search._query_tokens("IssueCreateMetadata"), search.tokenize("IssueCreateMetadata") | {"issuecreatemetadata"})

    def test_expansion_never_contains_joined_forms(self):
        exp = search.expand_query("IssueCreateMetadata getIssue", policy.aliases())
        self.assertNotIn("issuecreatemetadata", exp.all); self.assertNotIn("getissue", exp.all)
        self.assertEqual(exp.base, frozenset({"issue", "create", "metadata", "get"}))

    def test_stopwords_short_tokens_and_dedupe(self):
        self.assertEqual(search.tokenize("a to the x issue issue"), frozenset({"issue"}))
        self.assertEqual(search.tokenize(""), frozenset())
        self.assertEqual(search.tokenize(None), frozenset())

    def test_snake_and_kebab(self):
        self.assertEqual(search.tokenize("create_issue"), frozenset({"create", "issue"}))
        self.assertEqual(search.tokenize("jira-platform"), frozenset({"jira", "platform"}))


class TestBuildIndex(unittest.TestCase):
    def test_index_fields_for_attachment_operation(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        index = search.build_index(ns.operations)
        entry = next(e for e in index.entries if e.key.endswith("/attachments"))
        self.assertIn("attachment", entry.fields["operation_id"])
        self.assertIn("multipartfile", entry.fields["schema_names"])
        self.assertEqual(entry.fields["method"], frozenset({"post"}))
        self.assertIn("issue", entry.fields["path"])

    def test_nested_schema_names_indexed(self):
        ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))
        index = search.build_index(ns.operations)
        entry = next(e for e in index.entries if e.key == "edge:POST:/things/{thingId}")
        self.assertIn("strict", entry.fields["schema_names"])
        merge = next(e for e in index.entries if e.key == "edge:POST:/merge")
        self.assertIn("merged", merge.fields["schema_names"])  # body is a bare $ref; no resolution (spec §13.2)


class TestSearchOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "jira-software", "confluence")

    def _keys(self, **kw):
        return [r["key"] for r in search.search_operations(self.state, **kw)["results"]]

    def test_attachment_query_top1(self):
        self.assertEqual(self._keys(query="upload attachment to issue")[0],
                         "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")

    def test_plural_and_singular_agree(self):
        self.assertEqual(self._keys(query="issue attachments")[0], self._keys(query="issue attachment")[0])

    def test_sprint_query_prefers_jira_software(self):
        top3 = self._keys(query="sprint board backlog")[:3]
        self.assertEqual(len(top3), 3)
        self.assertTrue(all(k.startswith("jira-software:") for k in top3), top3)

    def test_create_confluence_page(self):
        self.assertEqual(self._keys(query="create confluence page")[0], "confluence:POST:/pages")

    def test_exact_schema_name(self):
        self.assertEqual(self._keys(query="MultipartFile")[0], "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")
        # getCreateIssueMeta is deprecated in the real spec (x0.7), so only top-2 is pinned
        self.assertIn("jira-platform:GET:/rest/api/3/issue/createmeta", self._keys(query="IssueCreateMetadata")[:2])

    def test_query_tokens_includes_joined_word_and_empty_for_stopwords(self):
        self.assertIn("issuecreatemetadata", search._query_tokens("IssueCreateMetadata"))
        self.assertEqual(search._query_tokens("a to"), frozenset())

    def test_joined_token_only_for_multi_token_words(self):
        self.assertEqual(search._query_tokens("with"), frozenset())
        self.assertEqual(search._query_tokens("attachment"), frozenset({"attachment"}))
        self.assertNotIn("issueattachment", search._query_tokens("issue attachment"))

    def test_all_match_bonus_ignores_joined_forms(self):
        import types
        fields = {f: frozenset() for f in search.FIELD_WEIGHTS}
        first = next(iter(search.FIELD_WEIGHTS))
        fields[first] = frozenset({"issue", "attachment"})
        entry = types.SimpleNamespace(fields=fields)
        q = "issue attachment"
        pol = policy.AliasPolicy(0.5, 1.0, {}, (), "x")
        exp = lambda text: search.QueryExpansion(search._query_tokens(text), frozenset(), frozenset())
        with_bonus = search._score(entry, exp(q), False, search.tokenize(q), pol)
        self.assertEqual(with_bonus, 2 * search.FIELD_WEIGHTS[first] + search.ALL_MATCH_BONUS)
        q2 = "IssueAttachment"   # joined token absent from the entry must not cancel the bonus
        self.assertIn("issueattachment", search._query_tokens(q2))
        self.assertEqual(search._score(entry, exp(q2), False, search.tokenize(q2), pol), with_bonus)

    def test_source_filter(self):
        self.assertTrue(all(k.startswith("confluence:") for k in self._keys(query="issue page", source="confluence")))

    def test_method_tag_and_deprecated_filters(self):
        self.assertTrue(all(":GET:" in k for k in self._keys(query="issue", method="get")))
        out = search.search_operations(self.state, "issue", include_deprecated=False)
        self.assertTrue(all(not r["deprecated"] for r in out["results"]))
        tag = self.state.registry.sources["jira-platform"].operations[0].tags[0]
        self.assertTrue(all(tag in r["tags"] for r in search.search_operations(self.state, "issue", tag=tag)["results"]))

    def test_deterministic_order(self):
        self.assertEqual(self._keys(query="issue"), self._keys(query="issue"))

    def test_limit_bounds_and_provenance_scope(self):
        out = search.search_operations(self.state, "issue", limit=2)
        self.assertEqual(len(out["results"]), 2)
        self.assertEqual(set(out["provenance"]), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(set(search.search_operations(self.state, "issue", source="confluence")["provenance"]), {"confluence"})
        self.assertEqual(search.search_operations(self.state, "issue", limit=51)["error"]["code"], "invalid_argument")
        self.assertEqual(search.search_operations(self.state, "issue", source="github")["error"]["code"], "invalid_argument")

    def test_stopword_only_query_is_empty_query_error(self):
        self.assertEqual(search.search_operations(self.state, "a to")["error"]["code"], "empty_query")
        self.assertEqual(search.search_operations(self.state, "")["error"]["code"], "empty_query")

    def test_unavailable_source_filter_returns_empty_not_error(self):
        state = make_state("confluence")
        out = search.search_operations(state, "issue", source="jira-platform")
        self.assertEqual(out["results"], [])
        self.assertEqual(out["provenance"]["jira-platform"]["status"], "unavailable")


import json, pathlib
from tests.benchmarks.evaluator import evaluate
from tools.atlassian_docs.intelligence import policy

BENCH = json.loads((pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "search_queries.json").read_text(encoding="utf-8"))


class TestExpansion(unittest.TestCase):
    def test_direction_and_order(self):
        e = search.expand_query("fetch page", policy.aliases())
        self.assertIn("fetch", e.base); self.assertIn("get", e.direct); self.assertEqual(e.cond, frozenset())

    def test_rule_sees_direct_but_no_cascade(self):
        p = policy.AliasPolicy(0.5, 1.0, {"edit": ("update",)}, (policy.AliasRule(frozenset({"update", "page"}), ("updatepage",)),
                               policy.AliasRule(frozenset({"updatepage"}), ("cascade",))), "x")
        e = search.expand_query("edit page", p)
        self.assertIn("updatepage", e.cond); self.assertNotIn("cascade", e.cond)

    def test_no_cascade_through_alias_values(self):
        p = policy.AliasPolicy(0.5, 1.0, {"read": ("get",), "get": ("obtain",)}, (), "x")
        e = search.expand_query("read", p)
        self.assertEqual(e.direct, frozenset({"get"}))          # "obtain" must not appear


class TestExactMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "jira-software", "confluence")

    def test_identifier_pinned_case_sensitive_first(self):
        out = search.search_operations(self.state, "createIssue")
        self.assertTrue(out["exact_match"]); self.assertEqual(out["results"][0]["match"], "exact_operation_id")
        self.assertEqual(out["results"][0]["key"], "jira-platform:POST:/rest/api/3/issue")
        ci = search.search_operations(self.state, "createissue")
        self.assertEqual(ci["results"][0]["match"], "exact_operation_id_ci")

    def test_duplicate_operation_ids_pinned_in_key_order(self):
        keys = [r["key"] for r in search.search_operations(self.state, "getIssue")["results"][:2]]
        self.assertEqual(keys, sorted(keys)); self.assertTrue(all(k.split(":")[2].endswith("issue/{issueIdOrKey}") for k in keys))

    def test_whitespace_query_is_not_pinned(self):
        out = search.search_operations(self.state, "get issue")
        self.assertFalse(out["exact_match"]); self.assertNotIn("match", out["results"][0])

    def test_exact_score_is_lexical_max_plus_one(self):
        out = search.search_operations(self.state, "createIssue")
        rest = [r["score"] for r in out["results"] if "match" not in r]
        self.assertAlmostEqual(out["results"][0]["score"], (max(rest) if rest else 0) + 1.0, places=3)

    def test_exact_key_and_filters(self):
        out = search.search_operations(self.state, "jira-platform:POST:/rest/api/3/issue")
        self.assertEqual(out["results"][0]["match"], "exact_key")
        conf = search.search_operations(self.state, "createIssue", source="confluence")
        self.assertFalse(conf["exact_match"]); self.assertTrue(all("match" not in r for r in conf["results"]))


class TestSeedBenchmark(unittest.TestCase):
    @unittest.skip("enabled in Round 1 Task 7")
    def test_seed_passes_on_fixtures(self):
        state = make_state("jira-platform", "jira-software", "confluence")
        fn = lambda q: [r["key"] for r in search.search_operations(state, q, limit=5)["results"]]
        res = evaluate(BENCH["seed"], fn)
        self.assertEqual(res["failed"], [], res)
        res_neg = evaluate(BENCH["regression_negative"], fn)
        self.assertEqual(res_neg["failed"], [], res_neg)

    def test_fields_and_fingerprint(self):
        state = make_state("jira-platform")
        out = search.search_operations(state, "fetch issue")
        self.assertIn("get", out["alias_tokens"]); self.assertIn("fetch", out["query_tokens"])
        self.assertEqual(set(out["expanded_tokens"]), set(out["query_tokens"]) | set(out["alias_tokens"]))
        self.assertEqual(len(out["intelligence_fingerprint"]), 64); self.assertEqual(out["intelligence_policy"]["versions"]["search"], 2)

    def test_alias_damped_and_bonus_on_base_only(self):
        state = make_state("jira-platform")
        with_alias = search.search_operations(state, "fetch issue")["results"][0]["score"]
        plain = search.search_operations(state, "get issue")["results"][0]["score"]
        self.assertLess(with_alias, plain)   # damped alias contributes less than the real token
