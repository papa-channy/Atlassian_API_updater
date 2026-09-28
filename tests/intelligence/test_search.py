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
        self.assertEqual(search.tokenize("statuses"), frozenset({"statuses", "statuse"}))
        self.assertEqual(search.tokenize("status"), frozenset({"status"}))
        self.assertEqual(search.tokenize("process"), frozenset({"process"}))
        self.assertEqual(search.tokenize("analysis"), frozenset({"analysis"}))
        self.assertEqual(search.tokenize("issues"), frozenset({"issues", "issue"}))

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
