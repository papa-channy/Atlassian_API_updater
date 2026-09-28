import unittest

from tests.intelligence.helpers import load_fixture
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
        index = search.build_index(ns.operations, ns.schemas)
        entry = next(e for e in index.entries if e.key.endswith("/attachments"))
        self.assertIn("attachment", entry.fields["operation_id"])
        self.assertIn("multipartfile", entry.fields["schema_names"])
        self.assertEqual(entry.fields["method"], frozenset({"post"}))
        self.assertIn("issue", entry.fields["path"])

    def test_nested_schema_names_indexed(self):
        ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))
        index = search.build_index(ns.operations, ns.schemas)
        entry = next(e for e in index.entries if e.key == "edge:POST:/things/{thingId}")
        self.assertIn("strict", entry.fields["schema_names"])
        merge = next(e for e in index.entries if e.key == "edge:POST:/merge")
        self.assertTrue({"merged", "base"} <= merge.fields["schema_names"])  # via allOf
