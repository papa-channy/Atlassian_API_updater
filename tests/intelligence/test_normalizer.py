import unittest

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs.intelligence import normalizer


def _find(ns, method, path):
    for op in ns.operations:
        if op.method == method and op.path == path:
            return op
    raise AssertionError(f"{method} {path} not found")


class TestRealFixtures(unittest.TestCase):
    def test_all_three_fixtures_normalize(self):
        for name in ("jira-platform", "jira-software", "confluence"):
            ns = normalizer.normalize_openapi(name, load_fixture(name))
            self.assertGreater(len(ns.operations), 0, name)
            self.assertEqual(ns.source, name)
            self.assertFalse(ns.normalization_partial, ns.warnings)

    def test_canonical_key_and_upper_method(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        op = _find(ns, "POST", "/rest/api/3/issue/{issueIdOrKey}/attachments")
        self.assertEqual(op.key, "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")
        self.assertEqual(op.operation_id, "addAttachment")
        self.assertTrue(op.parameters[0].required)          # path param forced required
        self.assertEqual(op.request_body.content[0].content_type, "multipart/form-data")

    def test_oauth2_scopes_flattened_from_object_array(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        op = _find(ns, "POST", "/rest/api/3/issue")
        self.assertIn("write:jira-work", op.oauth2_scopes)
        self.assertEqual(len(op.oauth2_scopes), len(set(op.oauth2_scopes)))

    def test_path_level_parameters_merged_for_jira_software(self):
        ns = normalizer.normalize_openapi("jira-software", load_fixture("jira-software"))
        op = _find(ns, "POST", "/rest/builds/0.1/bulk")
        self.assertTrue(any(p.location == "header" for p in op.parameters))

    def test_confluence_requestbody_ref_resolved(self):
        ns = normalizer.normalize_openapi("confluence", load_fixture("confluence"))
        op = _find(ns, "POST", "/blogposts")
        self.assertIsNotNone(op.request_body)
        self.assertTrue(op.request_body.content)

    def test_examples_are_stripped_everywhere(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        import json
        blob = json.dumps([op.to_dict() for op in ns.operations]) + json.dumps(ns.schemas)
        self.assertNotIn('"example"', blob)
        self.assertNotIn('"examples"', blob)

    def test_deterministic(self):
        spec = load_fixture("confluence")
        a = normalizer.normalize_openapi("confluence", spec)
        b = normalizer.normalize_openapi("confluence", spec)
        self.assertEqual([o.key for o in a.operations], [o.key for o in b.operations])
        self.assertEqual(a.tags, b.tags)


class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))

    def test_operation_without_operation_id(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        self.assertIsNone(op.operation_id)

    def test_operation_level_overrides_path_level_by_name_and_location(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        expands = [p for p in op.parameters if p.name == "expand"]
        self.assertEqual(len(expands), 1)
        self.assertEqual(expands[0].schema["enum"], ["x", "y"])
        self.assertEqual([p.name for p in op.parameters][:2], ["thingId", "expand"])  # path-level order first

    def test_parameter_ref_resolved_schema_ref_kept(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        limit = [p for p in op.parameters if p.name == "limit"][0]
        self.assertTrue(limit.required)
        node = _find(self.ns, "GET", "/things/{thingId}").responses[0].content[0].schema
        self.assertEqual(node, {"$ref": "#/components/schemas/Node"})  # schema-level ref stays raw

    def test_cookie_parameter_preserved(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        self.assertTrue(any(p.location == "cookie" for p in op.parameters))

    def test_empty_security_alternative_preserved(self):
        op = _find(self.ns, "POST", "/things/{thingId}")
        self.assertEqual(len(op.security), 2)
        self.assertEqual(op.security[0].requirements, ())
        and_part = op.security[1].requirements
        self.assertEqual([r.scheme for r in and_part], ["OAuth2", "basicAuth"])
        self.assertEqual(and_part[0].scopes, ("write:thing",))

    def test_top_level_security_inherited(self):
        op = _find(self.ns, "GET", "/things/{thingId}")
        self.assertEqual(op.security[0].requirements[0].scheme, "basicAuth")

    def test_experimental_only_when_bool_true(self):
        self.assertFalse(_find(self.ns, "POST", "/things/{thingId}").experimental)
        self.assertTrue(_find(self.ns, "DELETE", "/things/{thingId}").experimental)
        self.assertTrue(any(w["kind"] == "experimental_value_ignored" for w in self.ns.warnings))

    def test_oauth2_scopes_deduped_in_order(self):
        op = _find(self.ns, "POST", "/things/{thingId}")
        self.assertEqual(op.oauth2_scopes, ("write:thing", "read:thing"))

    def test_example_inside_media_type_dropped(self):
        op = _find(self.ns, "POST", "/things/{thingId}")
        self.assertEqual(op.request_body.content[0].schema, {"$ref": "#/components/schemas/Strict"})

    def test_duplicate_operation_ids_both_kept(self):
        self.assertEqual(sum(1 for o in self.ns.operations if o.operation_id == "dupId"), 2)


class TestFailures(unittest.TestCase):
    def test_paths_not_dict_raises(self):
        with self.assertRaises(normalizer.NormalizationError):
            normalizer.normalize_openapi("x", {"openapi": "3.0.0", "info": {}, "paths": []})

    def test_broken_operation_is_skipped_and_flagged(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {
            "/ok": {"get": {"responses": {}}},
            "/bad": {"get": {"parameters": "not-a-list", "responses": {}}},
        }}
        ns = normalizer.normalize_openapi("x", spec)
        self.assertEqual([o.path for o in ns.operations], ["/ok"])
        self.assertTrue(ns.normalization_partial)
        self.assertEqual(ns.warnings[0]["kind"], "operation_skipped")

    def test_path_item_ref_is_skipped_with_warning(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {"/r": {"$ref": "#/x"}}}
        ns = normalizer.normalize_openapi("x", spec)
        self.assertEqual(ns.operations, ())
        self.assertEqual(ns.warnings[0]["kind"], "path_item_ref_unsupported")
