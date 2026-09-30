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


ATTACH = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"


class TestQuirksInCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "edge-cases", source_map={"edge-cases": "edge"})

    def test_required_literal_missing_and_mismatch(self):
        out = rc.check_request(self.state, ATTACH, path_params={"issueIdOrKey": "A-1"}, body=[{}], content_type="multipart/form-data")
        self.assertIn(("header.X-Atlassian-Token", "required"), _rules(out))
        err = next(e for e in out["errors"] if e["rule"] == "required" and e["location"] == "header.X-Atlassian-Token")
        self.assertEqual(err["origin"], "quirk:override")
        bad = rc.check_request(self.state, ATTACH, path_params={"issueIdOrKey": "A-1"}, body=[{}], content_type="multipart/form-data", headers={"X-Atlassian-Token": "yes-check"})
        self.assertIn(("header.X-Atlassian-Token", "quirk_value_mismatch"), _rules(bad)); self.assertFalse(bad["compatible"])

    def test_quirk_header_case_insensitive(self):
        out = rc.check_request(self.state, ATTACH, path_params={"issueIdOrKey": "A-1"}, body=[{}], content_type="multipart/form-data", headers={"x-atlassian-token": "no-check"})
        self.assertNotIn(("header.X-Atlassian-Token", "required"), _rules(out)); self.assertTrue(out["compatible"])
        self.assertIn("quirk_headers", out["checked"]); self.assertEqual(out["quirks"]["applied"][0]["name"], "X-Atlassian-Token")

    def test_multipart_hint_warning(self):
        out = rc.check_request(self.state, ATTACH, path_params={"issueIdOrKey": "A-1"}, body={"other": 1}, content_type="multipart/form-data", headers={"X-Atlassian-Token": "no-check"})
        self.assertIn(("body.file", "multipart_field_missing"), _rules(out, "warnings"))

    def test_advisory_when_no_override(self):
        from unittest import mock
        from tools.atlassian_docs.intelligence import policy
        empty = policy.QuirkOverrides({}, None)
        with mock.patch("tools.atlassian_docs.intelligence.quirks.policy.overrides", return_value=empty), \
             mock.patch("tools.atlassian_docs.intelligence.request_check.policy.overrides", return_value=empty):
            out = rc.check_request(self.state, ATTACH, path_params={"issueIdOrKey": "A-1"}, body=[{}], content_type="multipart/form-data")
        self.assertIn(("header.X-Atlassian-Token", "advisory_header_missing"), _rules(out, "warnings")); self.assertTrue(out["compatible"])

    def test_structural_fields_present(self):
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={"name": "n"}, content_type="application/json")
        self.assertEqual(out["body_check"], "structural"); self.assertEqual(len(out["intelligence_fingerprint"]), 64)


class TestFallbackReasons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "edge-cases", source_map={"edge-cases": "edge"})

    def test_not_installed_reason(self):
        from unittest import mock
        with mock.patch("tools.atlassian_docs.intelligence.request_check._jsonschema_available", return_value=False):
            out = rc.check_request(self.state, "jira-platform:POST:/rest/api/3/issue", content_type="application/json", body={"fields": {}})
        self.assertEqual((out["body_check"], out["body_check_reason"]), ("structural", "jsonschema_not_installed"))
        self.assertEqual(out["validation_engine"]["engine"], "structural")

    def test_oas31_reason_without_sdk(self):
        out = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json", body={"name": "n"})
        self.assertEqual(out["body_check_reason"], "oas31_not_supported")

    def test_transpile_failure_reason(self):
        from unittest import mock
        with mock.patch("tools.atlassian_docs.intelligence.request_check._jsonschema_available", return_value=True), \
             mock.patch("tools.atlassian_docs.intelligence.request_check.oas_schema.oas30_to_draft7", side_effect=ValueError("bad")):
            out = rc.check_request(self.state, "jira-platform:POST:/rest/api/3/issue", content_type="application/json", body={"fields": {}})
        self.assertEqual(out["body_check_reason"], "schema_transpile_failed")

    def test_no_body_vs_no_body_schema(self):
        missing = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, content_type="application/json")
        self.assertEqual(missing["body_check_reason"], "no_body")
        amb = rc.check_request(self.state, CREATE, path_params={"thingId": "1"}, body={})
        self.assertEqual(amb["body_check_reason"], "no_body_schema")
        undeclared = rc.check_request(self.state, "edge:GET:/things/{thingId}", path_params={"thingId": "1"}, query={"limit": "1"}, body={"id": "x"})
        self.assertEqual(undeclared["body_check_reason"], "no_body_schema")


class TestCredentialHeaderPresence(unittest.TestCase):
    """I3: a supplied credential header counts as present for `required`; its value never appears."""
    KEY = "jira-software:POST:/rest/builds/0.1/bulk"
    BODY = {"builds": [{"pipelineId": "p", "buildNumber": 1, "displayName": "d", "url": "https://x", "state": "successful",
                        "lastUpdated": "2026-01-01T00:00:00Z", "updateSequenceNumber": 1, "description": "d",
                        "label": "l", "issueKeys": ["A-1"]}]}

    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "jira-software")

    def test_present_credential_header_satisfies_required(self):
        import json
        out = rc.check_request(self.state, self.KEY, headers={"authorization": "JWT SECRETVAL9f3a"}, body=self.BODY,
                               content_type="application/json")
        self.assertNotIn(("header.Authorization", "required"), _rules(out))
        self.assertTrue(out["compatible"], out)
        self.assertIn("credential_header_ignored", [w["rule"] for w in out["warnings"]])
        self.assertNotIn("SECRETVAL9f3a", json.dumps(out))

    def test_absent_credential_header_still_missing(self):
        out = rc.check_request(self.state, self.KEY, body=self.BODY, content_type="application/json")
        self.assertIn(("header.Authorization", "required"), _rules(out)); self.assertFalse(out["compatible"])
