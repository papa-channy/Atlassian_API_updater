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

    def test_body_without_declared_schema_reason(self):
        out = rc.check_request(self.state, "edge:GET:/things/{thingId}", path_params={"thingId": "1"}, query={"limit": "1"}, body={"id": "x"})
        self.assertEqual((out["body_check"], out["body_check_reason"]), ("structural", "no_body_schema"))

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


def _resolved(schema, cycles=()):
    from tools.atlassian_docs.intelligence import schemas
    return schemas.ResolvedSchema(schema=schema, truncated=False, unresolved=(), cycles=cycles, node_count=1)


@unittest.skipUnless(HAS, "jsonschema not installed (pip install -r requirements-validate.txt)")
class TestJsonSchemaHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "confluence")

    def _issue(self, body):
        return rc.check_request(self.state, ISSUE, content_type="application/json", body=body)

    def test_values_never_echoed_in_messages(self):
        secret = "Bearer " + "s3cr3tTOKEN" * 120
        page = {"spaceId": secret, "status": secret, "title": {"nested": secret}, "body": secret, "bogus": secret}
        out = rc.check_request(self.state, "confluence:POST:/pages", content_type="application/json", body=page)
        self.assertFalse(out["compatible"])
        self.assertNotIn("s3cr3tTOKEN", json.dumps(out))
        bad = self._issue({"fields": secret, "transition": {"id": 42}, "properties": [secret]})
        self.assertNotIn("s3cr3tTOKEN", json.dumps(bad))
        root = rc.check_request(self.state, ISSUE, content_type="application/json", body=secret)
        self.assertNotIn("s3cr3tTOKEN", json.dumps(root)); self.assertFalse(root["compatible"])

    def test_message_shapes(self):
        out = rc.check_request(self.state, "confluence:POST:/pages", content_type="application/json",
                               body={"spaceId": "1", "status": "nope", "title": 42})
        msgs = {(e["location"], e["rule"]): e["message"] for e in out["errors"]}
        self.assertEqual(msgs[("body.title", "schema:type")], "expected type string")
        self.assertTrue(msgs[("body.status", "schema:enum")].startswith("must be one of ["))

    def test_readonly_property_present(self):
        body = dict(ISSUE_BODY, transition={"id": "1", "fields": {}, "expand": "x"})
        out = self._issue(body)
        self.assertEqual(out["body_check"], "jsonschema")
        warns = [(w["location"], w["rule"]) for w in out["warnings"]]
        self.assertIn(("body.transition.fields", "readonly_property_present"), warns)
        self.assertIn(("body.transition.expand", "readonly_property_present"), warns)

    def test_not_fully_resolvable_cycle_marker(self):
        from unittest import mock
        cyc = _resolved({"$ref": "#/components/schemas/X", "_cycle": True}, cycles=("#/components/schemas/X",))
        with mock.patch("tools.atlassian_docs.intelligence.request_check.schemas.resolve", return_value=cyc):
            out = self._issue(ISSUE_BODY)
        self.assertEqual((out["body_check"], out["body_check_reason"]), ("structural", "schema_not_fully_resolvable"))

    def test_schema_error_and_runtime_error_reasons(self):
        from unittest import mock
        import jsonschema
        with mock.patch.object(jsonschema.Draft7Validator, "check_schema", side_effect=jsonschema.exceptions.SchemaError("x")):
            self.assertEqual(self._issue(ISSUE_BODY)["body_check_reason"], "jsonschema_schema_error")
        from referencing.exceptions import Unresolvable
        for exc in (jsonschema.exceptions.SchemaError("x"), Unresolvable(ref="#/nope")):
            with mock.patch.object(jsonschema.Draft7Validator, "check_schema"), \
                 mock.patch.object(jsonschema.Draft7Validator, "iter_errors", side_effect=exc):   # check_schema uses iter_errors
                out = self._issue(ISSUE_BODY)
            self.assertEqual((out["body_check"], out["body_check_reason"]), ("structural", "jsonschema_runtime_error"))

    def test_other_exceptions_propagate(self):
        from unittest import mock
        import jsonschema
        with mock.patch.object(jsonschema.Draft7Validator, "check_schema"), \
             mock.patch.object(jsonschema.Draft7Validator, "iter_errors", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._issue(ISSUE_BODY)

    def test_errors_truncated_and_sorted(self):
        from unittest import mock
        schema = {"type": "object", "properties": {f"p{i:02d}": {"type": "string"} for i in reversed(range(60))}}
        body = {f"p{i:02d}": i for i in reversed(range(60))}
        with mock.patch("tools.atlassian_docs.intelligence.request_check.schemas.resolve",
                        return_value=_resolved(schema)):
            out = self._issue(body)
        self.assertEqual(len(out["errors"]), 50)
        self.assertEqual([e["location"] for e in out["errors"]], [f"body.p{i:02d}" for i in range(50)])
        self.assertIn(("body", "errors_truncated"), [(w["location"], w["rule"]) for w in out["warnings"]])
