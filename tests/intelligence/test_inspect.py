import json
import unittest

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import inspect as insp

ATT = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"


class TestResolveOperation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "edge-cases", source_map={"edge-cases": "edge"})

    def test_by_key_and_by_operation_id(self):
        self.assertEqual(insp.resolve_operation(self.state, key=ATT)[0].operation_id, "addAttachment")
        self.assertEqual(insp.resolve_operation(self.state, operation_id="addAttachment")[0].key, ATT)

    def test_errors(self):
        self.assertEqual(insp.resolve_operation(self.state)[1]["error"]["code"], "invalid_argument")
        self.assertEqual(insp.resolve_operation(self.state, key="jira-platform:GET:/nope")[1]["error"]["code"], "operation_not_found")
        self.assertEqual(insp.resolve_operation(self.state, key="confluence:GET:/pages")[1]["error"]["code"], "source_unavailable")
        err = insp.resolve_operation(self.state, operation_id="dupId")[1]["error"]
        self.assertEqual(err["code"], "ambiguous_operation_id"); self.assertEqual(len(err["candidates"]), 2)


class TestGetOperation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform")

    def test_compact_default(self):
        out = insp.get_operation(self.state, key=ATT)
        json.dumps(out)
        self.assertLessEqual(len(out["description"]), 500)
        self.assertTrue(out["description_truncated"])
        self.assertEqual(out["responses"][0]["status"], "200")
        self.assertNotIn("schema", json.dumps(out["responses"]))
        self.assertNotIn('"example"', json.dumps(out))
        self.assertEqual(out["request_body"]["content"][0]["schema"]["items"], {"$ref": "#/components/schemas/MultipartFile"})
        self.assertEqual(set(out["provenance"]), {"jira-platform"})
        self.assertIsInstance(out["security"][0], list)

    def test_full_description_and_response_schemas(self):
        out = insp.get_operation(self.state, key=ATT, include_full_description=True, include_response_schemas=True)
        self.assertFalse(out["description_truncated"])
        self.assertIn("content", out["responses"][0])

    def test_resolve_schema_depth_inlines(self):
        out = insp.get_operation(self.state, key=ATT, resolve_schema_depth=1)
        items = out["request_body"]["content"][0]["schema"]["items"]
        self.assertNotIn("$ref", items); self.assertIn("type", items)
        self.assertEqual(insp.get_operation(self.state, key=ATT, resolve_schema_depth=9)["error"]["code"], "invalid_argument")

    def test_output_is_independent_copy(self):
        out = insp.get_operation(self.state, key=ATT)
        out["request_body"]["content"][0]["schema"]["items"]["$ref"] = "x"
        self.assertEqual(insp.get_operation(self.state, key=ATT)["request_body"]["content"][0]["schema"]["items"]["$ref"],
                         "#/components/schemas/MultipartFile")


class TestGetSchema(unittest.TestCase):
    def test_get_schema_and_limits(self):
        state = make_state("edge-cases", source_map={"edge-cases": "edge"})
        out = insp.get_schema(state, "edge", "Node", max_depth=3)
        self.assertEqual(out["source"], "edge"); self.assertTrue(out["cycles"])
        self.assertEqual(insp.get_schema(state, "edge", "Nope")["error"]["code"], "schema_not_found")
        self.assertEqual(insp.get_schema(state, "confluence", "X")["error"]["code"], "source_unavailable")
        self.assertEqual(insp.get_schema(state, "edge", "Node", max_depth=99)["error"]["code"], "invalid_argument")
