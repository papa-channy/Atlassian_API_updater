import unittest

from tests.intelligence.helpers import build_source_registry_from_fixture
from tools.atlassian_docs.intelligence import registry


def _reg(*names):
    srcs = {n: build_source_registry_from_fixture(n) for n in names}
    return registry.build_registry(srcs, "2026-09-28T00:00:00Z")


class TestSourceRegistry(unittest.TestCase):
    def test_lookup_maps_and_index(self):
        sr = build_source_registry_from_fixture("jira-platform")
        key = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"
        self.assertEqual(sr.operations_by_key[key].operation_id, "addAttachment")
        self.assertEqual(sr.keys_by_operation_id["addAttachment"], (key,))
        self.assertEqual(len(sr.search_index.entries), len(sr.operations))
        self.assertEqual(len(sr.spec_sha256), 64)

    def test_duplicate_operation_ids_listed(self):
        sr = build_source_registry_from_fixture("edge-cases", source="edge")
        self.assertEqual(len(sr.keys_by_operation_id["dupId"]), 2)


class TestRegistry(unittest.TestCase):
    def test_fingerprint_covers_all_configured_sources(self):
        a = registry.compute_fingerprint({"jira-platform": "x", "jira-software": None, "confluence": "y"})
        b = registry.compute_fingerprint({"jira-platform": "x", "confluence": "y"})
        c = registry.compute_fingerprint({"jira-platform": "x", "confluence": "z"})
        self.assertEqual(a, b); self.assertNotEqual(a, c); self.assertEqual(len(a), 64)

    def test_find_by_operation_id_across_sources(self):
        reg = _reg("jira-platform", "confluence")
        self.assertEqual(len(reg.find_by_operation_id(None, "addAttachment")), 1)
        self.assertEqual(reg.find_by_operation_id("confluence", "addAttachment"), ())
        self.assertEqual(reg.list_sources(), ("confluence", "jira-platform"))

    def test_list_operations_filters(self):
        reg = _reg("jira-platform")
        posts = reg.list_operations(method="post")
        self.assertTrue(posts and all(o.method == "POST" for o in posts))
        self.assertTrue(all(not o.deprecated for o in reg.list_operations(include_deprecated=False)))
        self.assertIn("Issues", reg.list_tags("jira-platform"))

    def test_get_schema_returns_copy(self):
        reg = _reg("jira-platform")
        s = reg.get_schema("jira-platform", "MultipartFile")
        s["mutated"] = True
        self.assertNotIn("mutated", reg.get_schema("jira-platform", "MultipartFile"))
        self.assertIsNone(reg.get_schema("jira-platform", "Nope"))
        self.assertIsNone(reg.get_schema("nope", "MultipartFile"))

    def test_registry_with_missing_source_still_builds(self):
        reg = _reg("confluence")
        self.assertIsNone(reg.get_operation("jira-platform:POST:/rest/api/3/issue"))
        self.assertEqual(reg.fingerprint, registry.compute_fingerprint({"confluence": reg.sources["confluence"].spec_sha256}))
