import unittest

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs.intelligence import normalizer, schemas


class TestParseAndLookup(unittest.TestCase):
    def setUp(self):
        self.ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))

    def test_parse_local_ref(self):
        self.assertEqual(schemas.parse_local_ref("#/components/schemas/Node"), ("schemas", "Node"))
        self.assertEqual(schemas.parse_local_ref("#/components/requestBodies/X"), ("requestBodies", "X"))
        self.assertIsNone(schemas.parse_local_ref("https://x/y.json#/components/schemas/A"))
        self.assertIsNone(schemas.parse_local_ref("#/paths/~1x"))

    def test_lookup(self):
        node, status = schemas.lookup_ref(self.ns, "#/components/schemas/Node")
        self.assertEqual(status, "ok"); self.assertEqual(node["type"], "object")
        self.assertEqual(schemas.lookup_ref(self.ns, "#/components/schemas/Nope"), (None, "missing"))
        self.assertEqual(schemas.lookup_ref(self.ns, "file://a.json#/x"), (None, "external"))


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))

    def test_single_ref_inlined(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Strict"}, self.ns, max_depth=1)
        self.assertEqual(r.schema["required"], ["name"])
        self.assertFalse(r.truncated); self.assertEqual(r.unresolved, ())

    def test_cycle_marked_not_infinite(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Node"}, self.ns, max_depth=8)
        parent = r.schema["properties"]["parent"]
        self.assertEqual(parent, {"$ref": "#/components/schemas/Node", "_cycle": True})
        self.assertIn("#/components/schemas/Node", r.cycles)

    def test_depth_truncation(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Merged"}, self.ns, max_depth=1)
        base = r.schema["allOf"][0]
        self.assertEqual(base["_truncated"], "depth"); self.assertTrue(r.truncated)

    def test_missing_and_external_markers(self):
        node = {"type": "object", "properties": {
            "ext": {"$ref": "https://example.com/other.json#/components/schemas/X"},
            "gone": {"$ref": "#/components/schemas/DoesNotExist"}}}
        r = schemas.resolve(node, self.ns)
        self.assertEqual(r.schema["properties"]["ext"]["_unresolved"], "external")
        self.assertEqual(r.schema["properties"]["gone"]["_unresolved"], "missing")
        self.assertEqual(len(r.unresolved), 2)

    def test_node_budget(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Node"}, self.ns, max_depth=8, max_nodes=1)
        self.assertEqual(r.node_count, 1)
        self.assertIn("#/components/schemas/Node", r.cycles)

    def test_cycle_precedence_over_budget(self):
        r = schemas.resolve({"$ref": "#/components/schemas/Node"}, self.ns, max_depth=8, max_nodes=1)
        parent = r.schema["properties"]["parent"]
        self.assertEqual(parent, {"$ref": "#/components/schemas/Node", "_cycle": True})
        self.assertIn("#/components/schemas/Node", r.cycles)

    def test_input_not_mutated_and_output_independent(self):
        node = {"$ref": "#/components/schemas/Strict"}
        r = schemas.resolve(node, self.ns, max_depth=1)
        self.assertEqual(node, {"$ref": "#/components/schemas/Strict"})
        r.schema["required"].append("mutated")
        self.assertEqual(self.ns.schemas["Strict"]["required"], ["name"])

    def test_limits_enforced(self):
        with self.assertRaises(ValueError):
            schemas.resolve({}, self.ns, max_depth=9)
        with self.assertRaises(ValueError):
            schemas.resolve({}, self.ns, max_nodes=2001)


class TestCollectRefNames(unittest.TestCase):
    def test_collects_nested_refs_without_resolving(self):
        node = {"type": "array", "items": {"$ref": "#/components/schemas/MultipartFile"},
                "allOf": [{"properties": {"a": {"$ref": "#/components/schemas/Inner"}}}],
                "x": {"$ref": "https://ext/#/components/schemas/Ext"}}
        self.assertEqual(schemas.collect_local_ref_names(node), ("Inner", "MultipartFile"))

    def test_none_and_scalars(self):
        self.assertEqual(schemas.collect_local_ref_names(None), ())
