import importlib.util
import json
import pathlib
import unittest

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import request_check as rc

HAS = importlib.util.find_spec("jsonschema") is not None
REQ = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "requests"
ISSUE = "jira-platform:POST:/rest/api/3/issue"
ISSUE_BODY = {"fields": {"project": {"key": "P"}, "summary": "s", "issuetype": {"name": "Task"}}}


@unittest.skipUnless(HAS, "jsonschema not installed (pip install -r requirements-validate.txt)")
class TestJsonSchemaPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "confluence", "edge-cases", source_map={"edge-cases": "edge"})

    def _fixture(self, name):
        return json.loads((REQ / name).read_text(encoding="utf-8"))

    def test_create_issue_positive_and_nested_negative(self):
        f = self._fixture("create_issue.json")
        ok = rc.check_request(self.state, f["key"], body=f["body"], content_type=f["content_type"])
        self.assertEqual(ok["body_check"], "jsonschema"); self.assertTrue(ok["compatible"], ok["errors"])
        bad = rc.check_request(self.state, f["key"], body=f["negative_body"], content_type=f["content_type"])
        self.assertFalse(bad["compatible"])
        self.assertTrue(any(e["location"] == f["negative_expect_location"] and e["rule"].startswith("schema:") for e in bad["errors"]), bad["errors"])

    def test_create_page_positive_and_negative(self):
        f = self._fixture("create_page.json")
        self.assertTrue(rc.check_request(self.state, f["key"], body=f["body"], content_type=f["content_type"])["compatible"])
        bad = rc.check_request(self.state, f["key"], body=f["negative_body"], content_type=f["content_type"])
        self.assertTrue(any(e["location"] == f["negative_expect_location"] for e in bad["errors"]), bad["errors"])

    def test_cycle_schema_falls_back(self):
        out = rc.check_request(self.state, "edge:GET:/things/{thingId}", path_params={"thingId": "1"}, query={"limit": "1"}, body={"id": "x"})
        self.assertEqual(out["body_check"], "structural")   # no requestBody on GET -> body_not_declared; still structural

    def test_readonly_inside_array_items(self):
        from unittest import mock
        from tools.atlassian_docs.intelligence import oas_schema
        real = oas_schema.oas30_to_draft7
        def spy(schema):
            t = real(schema)
            return oas_schema.TranspiledSchema(t.schema, t.readonly_paths + (("fields", "items", "id"),))
        with mock.patch("tools.atlassian_docs.intelligence.request_check.oas_schema.oas30_to_draft7", side_effect=spy):
            out = rc.check_request(self.state, ISSUE, content_type="application/json", body=ISSUE_BODY)
        self.assertNotIn(("body.fields.items[0].id", "readonly_property_present"), [(w["location"], w["rule"]) for w in out["warnings"]])
        out2 = rc.check_request(self.state, ISSUE, content_type="application/json", body=ISSUE_BODY)
        self.assertEqual(out2["body_check"], "jsonschema")

    def test_engine_and_fingerprint(self):
        out = rc.check_request(self.state, ISSUE, content_type="application/json", body=ISSUE_BODY)
        self.assertEqual(out["validation_engine"]["engine"], "jsonschema"); self.assertIsNotNone(out["validation_engine"]["version"])
        self.assertEqual(len(out["validation_fingerprint"]), 64); self.assertNotEqual(out["validation_fingerprint"], out["intelligence_fingerprint"])
        self.assertIn("jsonschema:body", out["checked"]); self.assertEqual(out["not_checked"], ["format", "cookie parameters"])

    def test_oas31_source_falls_back(self):
        st = make_state("edge-cases", source_map={"edge-cases": "edge"})   # edge fixture is openapi 3.1.0
        out = rc.check_request(st, "edge:POST:/things/{thingId}", path_params={"thingId": "1"}, content_type="application/json", body={"name": "n"})
        self.assertEqual((out["body_check"], out["body_check_reason"]), ("structural", "oas31_not_supported"))
