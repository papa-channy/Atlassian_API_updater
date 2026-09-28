import unittest

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import request_check as rc

THING = "edge:GET:/things/{thingId}"
CREATE = "edge:POST:/things/{thingId}"
MERGE = "edge:POST:/merge"
CHOICE = "edge:POST:/choice"


def _rules(out, kind="errors"):
    return sorted((e["location"], e["rule"]) for e in out[kind])


class TestParameters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})

    def test_required_missing(self):
        out = rc.check_request(self.state, THING)
        self.assertFalse(out["compatible"]); self.assertNotIn("valid", out)
        self.assertIn(("path.thingId", "required"), _rules(out)); self.assertIn(("query.limit", "required"), _rules(out))
        self.assertIn(("cookie.session", "cookie_not_checked"), _rules(out, "warnings"))

    def test_coercion_rules(self):
        ok = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": "5", "expand": "x"})
        self.assertTrue(ok["compatible"], ok)
        bad = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": "5.5", "expand": "zzz"})
        self.assertIn(("query.limit", "type"), _rules(bad)); self.assertIn(("query.expand", "enum"), _rules(bad))

    def test_bool_is_not_integer(self):
        out = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": True})
        self.assertIn(("query.limit", "type"), _rules(out))

    def test_unknown_parameter_warning_and_header_case(self):
        out = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": 1, "foo": 1}, headers={"x-y": "1"})
        self.assertTrue(out["compatible"])
        self.assertIn(("query.foo", "unknown_parameter"), _rules(out, "warnings"))
        self.assertIn(("header.x-y", "unknown_parameter"), _rules(out, "warnings"))


class TestBody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})

    def test_body_required_vs_explicit_null(self):
        self.assertIn(("body", "body_required"), _rules(rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json")))
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body=None, content_type="application/json")
        self.assertNotIn(("body", "body_required"), _rules(out)); self.assertIn(("body", "body_root_type"), _rules(out))

    def test_content_type_rules(self):
        bad = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={"name": "n"}, content_type="text/plain")
        self.assertIn(("content_type", "content_type"), _rules(bad))
        amb = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={})
        self.assertIn(("content_type", "content_type_ambiguous"), _rules(amb, "warnings"))
        self.assertTrue(amb["compatible"])  # body schema check skipped, nothing else wrong

    def test_body_rules_on_strict_schema(self):
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json",
                               body={"count": "x", "kind": "z", "extra": 1, "note": None})
        r = _rules(out)
        self.assertIn(("body.name", "body_required_properties"), r)
        self.assertIn(("body.count", "body_property_type"), r)
        self.assertIn(("body.kind", "body_property_enum"), r)
        self.assertIn(("body.extra", "body_unknown_property"), r)     # additionalProperties:false -> error
        self.assertNotIn(("body.note", "body_property_type"), r)      # nullable
        good = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json", body={"name": "n"})
        self.assertTrue(good["compatible"])

    def test_non_dict_body_against_object_schema_is_root_type_error(self):
        for bad in (["not", "a", "dict"], "a string body", 42):
            out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json", body=bad)
            self.assertIn(("body", "body_root_type"), _rules(out), bad)
            self.assertFalse(out["compatible"])

    def test_allof_merge_and_conflict(self):
        out = rc.check_request(self.state, MERGE, body={"id": "1"})
        self.assertIn(("body.extra", "body_required_properties"), _rules(out))
        self.assertIn(("body.shared", "conflicting_allof_property"), _rules(out, "warnings"))
        out = rc.check_request(self.state, MERGE, body={"id": "1", "extra": 2, "shared": "anything"})
        self.assertTrue(out["compatible"])

    def test_oneof_not_checked(self):
        out = rc.check_request(self.state, CHOICE, body={"whatever": 1})
        self.assertIn(("body", "structure_not_checked"), _rules(out, "warnings")); self.assertTrue(out["compatible"])

    def test_checked_lists_present(self):
        out = rc.check_request(self.state, CHOICE)
        self.assertIn("required", out["checked"]); self.assertIn("oneOf/anyOf", out["not_checked"])


class TestFinalReviewFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})

    def test_body_on_operation_without_request_body_warns(self):
        out = rc.check_request(self.state, THING, path_params={"thingId": "1"}, query={"limit": "5"}, body={"a": 1})
        self.assertIn(("body", "body_not_declared"), _rules(out, "warnings"))
        self.assertTrue(out["compatible"]); self.assertIn("body_not_declared", out["checked"])

    def test_content_type_parameters_ignored(self):
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={"name": "n"},
                               content_type="application/json; charset=utf-8")
        self.assertNotIn("content_type", [e["rule"] for e in out["errors"]])
        self.assertTrue(out["compatible"])

    def test_transport_and_credential_headers(self):
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={},
                               headers={"Content-Type": "application/json", "Authorization": "Basic x"})
        warn = _rules(out, "warnings")
        self.assertNotIn(("header.Content-Type", "unknown_parameter"), warn)
        self.assertNotIn(("header.Authorization", "unknown_parameter"), warn)
        self.assertEqual([w for w in out["warnings"] if w["rule"] == "credential_header_ignored"][0]["location"],
                         "header.Authorization")
        self.assertEqual(sum(1 for w in out["warnings"] if w["rule"] == "credential_header_ignored"), 1)
        self.assertNotIn("Basic x", repr(out))
        self.assertIn(("body.name", "body_required_properties"), _rules(out))
