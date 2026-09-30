import json
import pathlib
import tempfile
import unittest

from tools.atlassian_docs.intelligence import policy


class TestCanonicalHash(unittest.TestCase):
    def test_whitespace_invariant(self):
        a = policy.canonical_sha256(json.loads('{"b": 1, "a": [1, 2]}'))
        b = policy.canonical_sha256(json.loads('{ "a":[1,2] ,"b":1}'))
        self.assertEqual(a, b); self.assertEqual(len(a), 64)


class TestAliases(unittest.TestCase):
    def test_bundled_file_loads_and_is_normalized(self):
        p = policy.load_aliases()
        self.assertEqual(p.alias_damping, 0.5); self.assertEqual(p.rule_damping, 1.0)
        self.assertEqual(p.aliases["fetch"], ("get",))
        self.assertTrue(any(r.when_all == frozenset({"transition", "issue"}) for r in p.rules))
        self.assertEqual(len(p.sha256), 64)

    def _write(self, obj):
        d = tempfile.mkdtemp(); path = pathlib.Path(d) / "a.json"
        path.write_text(json.dumps(obj), encoding="utf-8"); return path

    def test_rejects_unnormalized_token(self):
        with self.assertRaises(ValueError):
            policy.load_aliases(self._write({"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"Fetch": ["get"]}, "rules": []}))
        with self.assertRaises(ValueError):
            policy.load_aliases(self._write({"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"fetch": ["get issue"]}, "rules": []}))

    def test_rejects_bad_damping_and_rule_shape(self):
        with self.assertRaises(ValueError):
            policy.load_aliases(self._write({"version": 1, "alias_damping": 2, "rule_damping": 1.0, "aliases": {}, "rules": []}))
        with self.assertRaises(ValueError):
            policy.load_aliases(self._write({"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {}, "rules": [{"when_all": [], "add": ["x"]}]}))


class TestOverrides(unittest.TestCase):
    def test_bundled_file_has_four_operations(self):
        o = policy.load_quirk_overrides()
        self.assertEqual(len(o.operations), 4)
        e = o.operations["jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"]
        self.assertEqual(e.headers[0].enforcement, "required"); self.assertEqual(e.headers[0].value_policy, "literal")
        self.assertEqual(e.request_hints["multipart_fields"][0]["name"], "file")
        self.assertEqual(len(o.sha256), 64)

    def _write(self, ops):
        d = tempfile.mkdtemp(); path = pathlib.Path(d) / "q.json"
        path.write_text(json.dumps({"version": 1, "operations": ops}), encoding="utf-8"); return path

    def test_rejects_bad_key_enum_and_conflicts(self):
        good = {"name": "X-Foo", "action": "set", "value": "1", "enforcement": "required", "value_policy": "literal"}
        with self.assertRaises(ValueError):
            policy.load_quirk_overrides(self._write({"bad key": {"headers": [good]}}))
        with self.assertRaises(ValueError):
            policy.load_quirk_overrides(self._write({"x:GET:/a": {"headers": [{**good, "enforcement": "maybe"}]}}))
        with self.assertRaises(ValueError):   # duplicate normalized header
            policy.load_quirk_overrides(self._write({"x:GET:/a": {"headers": [good, {**good, "name": "x-foo"}]}}))
        with self.assertRaises(ValueError):   # set + suppress
            policy.load_quirk_overrides(self._write({"x:GET:/a": {"headers": [good, {"name": "X-FOO", "action": "suppress"}]}}))

    def test_missing_file_is_empty(self):
        o = policy.load_quirk_overrides(pathlib.Path(tempfile.mkdtemp()) / "none.json")
        self.assertEqual(o.operations, {}); self.assertIsNone(o.sha256)


class TestFingerprint(unittest.TestCase):
    def test_changes_with_policy_only(self):
        a = policy.intelligence_fingerprint("reg", "A", "B")
        self.assertNotEqual(a, policy.intelligence_fingerprint("reg", "A2", "B"))
        self.assertNotEqual(a, policy.intelligence_fingerprint("reg", "A", None))
        self.assertEqual(a, policy.intelligence_fingerprint("reg", "A", "B"))
        self.assertEqual(policy.policy_block("A", "B")["versions"], policy.POLICY_VERSIONS)


class TestMalformedPolicyData(unittest.TestCase):
    """M4: malformed data raises ValueError (never AttributeError); overrides may not name credential headers."""

    def _raw(self, name, obj):
        d = tempfile.mkdtemp(); path = pathlib.Path(d) / name
        path.write_text(json.dumps(obj), encoding="utf-8"); return path

    def test_aliases_malformed_shapes(self):
        base = {"alias_damping": 0.5, "rule_damping": 1.0}
        for bad in ([], {**base, "aliases": ["x"]}, {**base, "aliases": {}, "rules": "x"},
                    {**base, "aliases": {}, "rules": ["not-a-dict"]}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                policy.load_aliases(self._raw("a.json", bad))

    def test_overrides_malformed_shapes(self):
        good = {"name": "X-Foo", "action": "set", "value": "1"}
        for bad in ([], {"operations": ["x"]}, {"operations": {"x:GET:/a": {"headers": ["not-a-dict"]}}},
                    {"operations": {"x:GET:/a": {"headers": good}}},
                    {"operations": {"x:GET:/a": {"headers": [good], "notes": "abc"}}},
                    {"operations": {"x:GET:/a": {"headers": [{**good, "note": 5}]}}},
                    {"operations": {"x:GET:/a": {"request_hints": {"multipart_fields": [
                        {"name": "file", "kind": "file", "required": "yes"}]}}}}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                policy.load_quirk_overrides(self._raw("q.json", bad))

    def test_overrides_reject_credential_header_names(self):
        for name in ("Authorization", "x-api-key", "COOKIE"):
            for h in ({"name": name, "action": "set", "value": "v"}, {"name": name, "action": "suppress"}):
                with self.assertRaises(ValueError, msg=repr(h)):
                    policy.load_quirk_overrides(self._raw("q.json", {"operations": {"x:GET:/a": {"headers": [h]}}}))


class TestTranspilerVersionSync(unittest.TestCase):
    def test_policy_version_matches_transpiler(self):
        from tools.atlassian_docs.intelligence import oas_schema
        self.assertEqual(policy.POLICY_VERSIONS["oas_transpiler"], oas_schema.TRANSPILER_VERSION)
