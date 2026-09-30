import unittest

from tools.atlassian_docs.intelligence import oas_schema as oas


class TestNullable(unittest.TestCase):
    def test_nullable_with_string_type(self):
        t = oas.oas30_to_draft7({"type": "string", "nullable": True})
        self.assertEqual(t.schema, {"type": ["string", "null"]})

    def test_nullable_without_type_only_removes_key(self):
        t = oas.oas30_to_draft7({"nullable": True, "enum": ["a"]})
        self.assertEqual(t.schema, {"enum": ["a"]})

    def test_nullable_not_applied_through_allof_parent(self):
        t = oas.oas30_to_draft7({"allOf": [{"type": "object"}], "nullable": True})
        self.assertEqual(t.schema, {"allOf": [{"type": "object"}]})

    def test_nested_recursion(self):
        t = oas.oas30_to_draft7({"type": "object", "properties": {"a": {"type": "integer", "nullable": True}}, "items": {"type": "string", "nullable": True}})
        self.assertEqual(t.schema["properties"]["a"], {"type": ["integer", "null"]}); self.assertEqual(t.schema["items"], {"type": ["string", "null"]})


class TestExclusive(unittest.TestCase):
    def test_true_with_bound(self):
        t = oas.oas30_to_draft7({"type": "number", "minimum": 1, "exclusiveMinimum": True, "maximum": 9, "exclusiveMaximum": True})
        self.assertEqual(t.schema, {"type": "number", "exclusiveMinimum": 1, "exclusiveMaximum": 9})

    def test_false_removed(self):
        t = oas.oas30_to_draft7({"type": "number", "minimum": 1, "exclusiveMinimum": False})
        self.assertEqual(t.schema, {"type": "number", "minimum": 1})

    def test_exclusive_without_bound_is_dropped(self):
        t = oas.oas30_to_draft7({"type": "number", "exclusiveMinimum": True})
        self.assertEqual(t.schema, {"type": "number"})

    def test_numeric_exclusive_passthrough(self):
        t = oas.oas30_to_draft7({"type": "number", "exclusiveMinimum": 3})
        self.assertEqual(t.schema, {"type": "number", "exclusiveMinimum": 3})


class TestReadOnlyAndCleanup(unittest.TestCase):
    def test_readonly_removed_from_required_and_recorded(self):
        t = oas.oas30_to_draft7({"type": "object", "required": ["id", "name"], "properties": {
            "id": {"type": "string", "readOnly": True}, "name": {"type": "string", "writeOnly": True},
            "items": {"type": "array", "items": {"type": "object", "properties": {"ref": {"type": "string", "readOnly": True}}}}}})
        self.assertEqual(t.schema["required"], ["name"])
        self.assertNotIn("readOnly", t.schema["properties"]["id"]); self.assertNotIn("writeOnly", t.schema["properties"]["name"])
        self.assertEqual(set(t.readonly_paths), {("id",), ("items", "items", "ref")})

    def test_oas_only_keys_removed(self):
        t = oas.oas30_to_draft7({"type": "object", "discriminator": {"propertyName": "k"}, "xml": {}, "externalDocs": {}, "deprecated": True, "x-atlassian-narrative": "n", "properties": {"k": {"type": "string", "x-foo": 1}}})
        self.assertEqual(t.schema, {"type": "object", "properties": {"k": {"type": "string"}}})

    def test_input_not_mutated_and_bad_input(self):
        src = {"type": "string", "nullable": True}
        oas.oas30_to_draft7(src); self.assertEqual(src, {"type": "string", "nullable": True})
        with self.assertRaises(ValueError):
            oas.oas30_to_draft7({"type": "object", "properties": []})


class TestFindReadOnly(unittest.TestCase):
    def test_readonly_inside_array_items(self):
        paths = (("id",), ("items", "items", "ref"))
        body = {"id": "x", "items": [{"ref": "a"}, {"other": 1}, {"ref": "b"}]}
        self.assertEqual(oas.find_readonly_values(body, paths), ["body.id", "body.items[0].ref", "body.items[2].ref"])
        self.assertEqual(oas.find_readonly_values({"items": "not-a-list"}, paths), [])


class TestOneOfToAnyOf(unittest.TestCase):
    def test_oneof_becomes_anyof_including_nested(self):
        s = {"type": "object", "oneOf": [{"type": "object"}, {"type": "string"}],
             "properties": {"body": {"oneOf": [{"properties": {"a": {"type": "string", "nullable": True}}}, {"type": "object"}]}}}
        out = oas.oas30_to_draft7(s).schema
        self.assertNotIn("oneOf", out); self.assertEqual(out["anyOf"], [{"type": "object"}, {"type": "string"}])
        body = out["properties"]["body"]
        self.assertNotIn("oneOf", body); self.assertEqual(len(body["anyOf"]), 2)
        self.assertEqual(body["anyOf"][0]["properties"]["a"]["type"], ["string", "null"])   # branches still transpiled

    def test_oneof_alongside_existing_anyof_keeps_both_constraints(self):
        out = oas.oas30_to_draft7({"anyOf": [{"type": "string"}], "oneOf": [{"minLength": 1}]}).schema
        self.assertEqual(out["anyOf"], [{"type": "string"}])
        self.assertEqual(out["allOf"], [{"anyOf": [{"minLength": 1}]}])
