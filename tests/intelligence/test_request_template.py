import unittest

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import request_template as rt

ATT = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"
THING = "edge:GET:/things/{thingId}"
CREATE = "edge:POST:/things/{thingId}"


class TestTemplate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "edge-cases", source_map={"edge-cases": "edge"})

    def test_no_values(self):
        out = rt.build_request_template(self.state, ATT)
        self.assertEqual(out["method"], "POST"); self.assertIsNone(out["path"]); self.assertIsNone(out["server"])
        self.assertEqual(out["path_params"]["issueIdOrKey"]["required"], True)
        self.assertEqual(out["selected_content_type"], "multipart/form-data")
        self.assertTrue(out["body_required"]); self.assertIn("body", out["missing_required"]); self.assertIn("issueIdOrKey", out["missing_required"])
        self.assertIn("server URL and Authorization are out of scope for Phase 2", out["notes"])

    def test_path_substitution_encodes(self):
        out = rt.build_request_template(self.state, ATT, {"path_params": {"issueIdOrKey": "AB C/1"}, "body": [{"file": "x"}]})
        self.assertEqual(out["path"], "/rest/api/3/issue/AB%20C%2F1/attachments")
        self.assertEqual(out["missing_required"], []); self.assertEqual(out["body"], [{"file": "x"}])

    def test_non_primitive_path_value_is_invalid(self):
        self.assertEqual(rt.build_request_template(self.state, ATT, {"path_params": {"issueIdOrKey": {"a": 1}}})["error"]["code"], "invalid_argument")

    def test_query_headers_unknown_and_case_insensitive(self):
        out = rt.build_request_template(self.state, THING, {"path_params": {"thingId": "1"}, "query": {"limit": 5, "foo": 1},
                                                              "headers": {"X-Custom": "v"}})
        self.assertEqual(out["query"]["limit"]["value"], 5)
        self.assertEqual(out["unknown_parameters"]["query"], ["foo"])
        self.assertEqual(out["unknown_parameters"]["headers"], ["X-Custom"])
        self.assertIn("session", out["cookies"])

    def test_invalid_content_type_not_silently_replaced(self):
        out = rt.build_request_template(self.state, CREATE, {"content_type": "text/plain"})
        self.assertIsNone(out["selected_content_type"]); self.assertIsNone(out["body_schema"])
        self.assertEqual(out["errors"][0]["rule"], "invalid_content_type")

    def test_content_type_defaulted_note_when_ambiguous(self):
        out = rt.build_request_template(self.state, CREATE)
        self.assertEqual(out["selected_content_type"], "application/json"); self.assertIn("content_type_defaulted", out["notes"])
        out = rt.build_request_template(self.state, CREATE, {"content_type": "multipart/form-data"})
        self.assertEqual(out["selected_content_type"], "multipart/form-data"); self.assertEqual(out["body_schema"], {"type": "object"})

    def test_credential_headers_dropped(self):
        out = rt.build_request_template(self.state, THING, {"headers": {"Authorization": "Basic xxx", "Cookie": "a=b"}})
        self.assertNotIn("Basic xxx", str(out)); self.assertIn("credential_header_dropped", out["notes"])
        self.assertEqual(out["unknown_parameters"]["headers"], [])

    def test_security_and_scopes_and_error(self):
        out = rt.build_request_template(self.state, CREATE)
        self.assertEqual(out["security"][0], []); self.assertEqual(out["oauth2_scopes"], ["write:thing", "read:thing"])
        self.assertEqual(rt.build_request_template(self.state, "edge:GET:/nope")["error"]["code"], "operation_not_found")

    def test_returned_schema_is_independent_of_registry(self):
        out = rt.build_request_template(self.state, ATT)
        out["path_params"]["issueIdOrKey"]["schema"]["mutated"] = True
        again = rt.build_request_template(self.state, ATT)
        self.assertNotIn("mutated", again["path_params"]["issueIdOrKey"]["schema"])

    def test_same_name_query_and_header_do_not_collide(self):
        from types import SimpleNamespace
        from unittest import mock
        from tools.atlassian_docs.intelligence import models
        q = models.Parameter("foo", "query", True, None, {"type": "string"}, False)
        h = models.Parameter("foo", "header", True, None, {"type": "string"}, False)
        real = self.state.registry.get_operation(THING)
        fake = models.Operation(**{**real.__dict__, "parameters": (q, h)})
        with mock.patch("tools.atlassian_docs.intelligence.request_template.insp.resolve_operation", return_value=(fake, None)):
            out = rt.build_request_template(self.state, THING, {"query": {"foo": "1"}})
        self.assertEqual(out["missing_required"], ["foo"])          # only the header is missing
        self.assertEqual(out["query"]["foo"]["value"], "1")


class TestTransportHeaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})

    def test_content_type_header_is_transport_not_unknown(self):
        out = rt.build_request_template(self.state, CREATE, {"headers": {"Content-Type": "application/json"}})
        self.assertEqual(out["transport_headers"], [{"name": "Content-Type", "value": "application/json"}])
        self.assertNotIn("Content-Type", out["unknown_parameters"]["headers"])

    def test_content_type_with_parameters_selects_base_type(self):
        out = rt.build_request_template(self.state, CREATE, {"content_type": "application/json; charset=utf-8"})
        self.assertEqual(out["selected_content_type"], "application/json"); self.assertEqual(out["errors"], [])
