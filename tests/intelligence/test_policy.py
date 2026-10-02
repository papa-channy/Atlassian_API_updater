import json
import pathlib
import tempfile
import unittest

from tools.atlassian_docs.intelligence import policy


LEGACY_ALIAS_SUBSET_SHA256 = "c430e96177612510b94427fa80c1f98c2e6cb1b0e20872a4505964f5df055be3"   # canonical sha of legacy_alias_subset(file at 95b8de0); equals the Round 1 alias_sha256 because the file has no Round 2 entries yet


def legacy_alias_subset(raw: dict) -> dict:
    keep = {k for k, n in raw["notes"].items() if n.get("origin") in ("phase2.5", "round1")}
    rules = [r for i, r in enumerate(raw["rules"]) if f"rule:{i}" in keep]
    return {"version": raw["version"], "alias_damping": raw["alias_damping"], "rule_damping": raw["rule_damping"],
            "aliases": {w: v for w, v in raw["aliases"].items() if w in keep}, "rules": rules,
            "notes": {k: n for k, n in raw["notes"].items() if k in keep}}


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

    def test_alias_notes_required_and_validated(self):
        ph = {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "phase2.5 §6.1"}
        base = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"fetch": ["get"]},
                "rules": [{"when_all": ["issue", "key"], "add": ["getissue"]}]}
        good = {**base, "notes": {"fetch": ph, "rule:0": ph}}
        self.assertEqual(policy.load_aliases(self._write(good)).aliases["fetch"], ("get",))
        r1 = {"origin": "round1", "seed_query_id": "s-015", "failure_classes": ["R4"], "evidence": "searchAndReconsileIssuesUsingJql"}
        policy.load_aliases(self._write({**base, "notes": {"fetch": r1, "rule:0": ph}}))
        bads = [base, {**base, "notes": {"fetch": ph}}, {**base, "notes": {"fetch": ph, "rule:0": ph, "rule:1": ph}},
                {**base, "notes": {"fetch": ph, "rule:0": ph, "other": ph}},
                {**base, "notes": {"fetch": {**r1, "seed_query_id": None}, "rule:0": ph}},
                {**base, "notes": {"fetch": {**r1, "seed_query_id": "s-15"}, "rule:0": ph}},
                {**base, "notes": {"fetch": {**r1, "failure_classes": ["R1"]}, "rule:0": ph}},
                {**base, "notes": {"fetch": {**ph, "origin": "x"}, "rule:0": ph}},
                {**base, "notes": {"fetch": "text", "rule:0": ph}}, {**base, "notes": []}]
        for bad in bads:
            with self.assertRaises(ValueError, msg=repr(bad)):
                policy.load_aliases(self._write(bad))
        self.assertIsNotNone(policy.load_aliases().sha256)

    def test_round_note_schema_is_round_aware(self):
        ph = {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "phase2.5 §6.1"}
        base = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"feedback": ["comment"]},
                "rules": [{"when_all": ["issue", "key"], "add": ["getissue"]}]}
        r1 = {"origin": "round1", "seed_query_id": "s-015", "failure_classes": ["R4"], "evidence": "x"}
        r2 = {"origin": "round2", "seed_query_id": "s-024", "candidate_word": "feedback", "failure_classes": ["R6"], "evidence": "x"}
        lx = {"origin": "lexicon-r2", "seed_query_id": None, "failure_classes": [], "evidence": "concept lexicon r2"}
        for good in (r1, r2, lx):
            policy.load_aliases(self._write({**base, "notes": {"feedback": good, "rule:0": ph}}))
        bads = [{**r2, "candidate_word": None}, {k: v for k, v in r2.items() if k != "candidate_word"},
                {**r2, "failure_classes": ["R4"]}, {**r2, "seed_query_id": None}, {**r2, "origin": "round0"},
                {**r2, "origin": "round02"}, {**r2, "origin": "round9x"}, {**lx, "seed_query_id": "s-001"},
                {**lx, "failure_classes": ["R6"]}, {**lx, "origin": "lexicon-r0"}, {**r1, "candidate_word": 3}]
        for bad in bads:
            with self.assertRaises(ValueError, msg=repr(bad)):
                policy.load_aliases(self._write({**base, "notes": {"feedback": bad, "rule:0": ph}}))

    def test_legacy_alias_subset_unchanged_by_schema_change(self):
        """AC-17: the phase2.5 + round1 subset of search_aliases.json (aliases, rules, notes) is pinned; Round 2 additions
        (lexicon-r2, round2) are stripped before hashing, so the test survives commit T."""
        raw = json.loads((policy.DATA_DIR / "search_aliases.json").read_text(encoding="utf-8"))
        self.assertEqual(policy.canonical_sha256(legacy_alias_subset(raw)), LEGACY_ALIAS_SUBSET_SHA256)
        policy.load_aliases()                                   # the whole file still loads under the new schema


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


class TestRankingPolicy(unittest.TestCase):
    def _raw(self):
        return json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))

    def test_bundled_loads_and_hashes(self):
        rp = policy.load_ranking()
        self.assertEqual(rp.verb_methods["move"], frozenset({"PUT", "POST"})); self.assertIn("rest", rp.path_noise)
        self.assertEqual(rp.product_hints["jira"], frozenset({"jira-platform", "jira-software"}))
        self.assertEqual(len(policy.CONSTANT_KEYS), 6); self.assertEqual(policy.CONSTANT_KEYS[-1], "resource_match_bonus")
        self.assertEqual(set(rp.constants), set(policy.CONSTANT_KEYS)); self.assertEqual(set(rp.baseline), set(policy.CONSTANT_KEYS)); self.assertEqual(len(rp.sha256), 64)
        from tests.benchmarks import evaluator as ev
        self.assertEqual(rp.structure_sha256, ev.current_round()["structure_sha256"])
        self.assertIs(policy.ranking(), policy.ranking())

    def test_constants_change_only_full_hash(self):
        raw = self._raw(); a = policy.load_ranking()
        other = next(v for v in raw["tuning_grid"]["method_match_bonus"] if v != raw["constants"]["method_match_bonus"])
        raw["constants"]["method_match_bonus"] = other          # any grid value that differs from the current one
        b = self._from(raw)
        self.assertNotEqual(a.sha256, b.sha256); self.assertEqual(a.structure_sha256, b.structure_sha256)

    def _from(self, raw):
        import tempfile, pathlib
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(raw, fh); path = pathlib.Path(fh.name)
        return policy.load_ranking(path)

    def test_constants_outside_grid_rejected(self):
        raw = self._raw(); raw["constants"]["path_unmatched_cap"] = 99
        with self.assertRaises(ValueError):
            self._from(raw)

    def test_loader_contract_violations(self):
        base = self._raw()
        bad = [dict(base, version=0), dict(base, verb_methods={**base["verb_methods"], "Get": ["GET"]}),
               dict(base, verb_methods={**base["verb_methods"], "get": ["GET", "GET"]}),
               dict(base, verb_methods={**base["verb_methods"], "get": ["FETCH"]}),
               dict(base, path_noise=base["path_noise"] + ["rest"]),
               dict(base, product_hints={**base["product_hints"], "jira": ["nowhere"]}),
               dict(base, product_hints={**base["product_hints"], "jira": []}),
               dict(base, tuning_grid={k: v for k, v in base["tuning_grid"].items() if k != "product_hint_bonus"}),
               dict(base, baseline={**base["baseline"], "path_unmatched_cap": 99}),
               dict(base, constants={**base["constants"], "path_unmatched_cap": True}),
               dict(base, constants={**base["constants"], "method_match_bonus": -1.0}),
               dict(base, constants={k: v for k, v in base["constants"].items() if k != "resource_match_bonus"}),
               dict(base, extra=1)]
        for raw in bad:
            with self.assertRaises(ValueError):
                self._from(raw)

    def test_malformed_list_elements_raise_value_error(self):
        """Non-string / nested list elements and newline-suffixed keys raise ValueError, never TypeError."""
        base = self._raw()
        bad = [dict(base, verb_methods={**base["verb_methods"], "get\n": ["GET"]}),              # "$" would accept
               dict(base, product_hints={**base["product_hints"], "jira\n": ["confluence"]}),
               dict(base, path_noise=base["path_noise"] + ["api\n"]),
               dict(base, verb_methods={**base["verb_methods"], "get": ["GET", 1]}),             # non-string element
               dict(base, product_hints={**base["product_hints"], "jira": [7]}),
               dict(base, path_noise=base["path_noise"] + [3]),
               dict(base, verb_methods={**base["verb_methods"], "get": [["GET"]]}),              # nested list element
               dict(base, product_hints={**base["product_hints"], "jira": [["jira-platform"]]}),
               dict(base, path_noise=base["path_noise"] + [["x"]]),
               dict(base, tuning_grid={**base["tuning_grid"], "method_match_bonus": [[1.0], 2.0]}),
               dict(base, tuning_grid={**base["tuning_grid"], "method_match_bonus": [{"a": 1}]})]
        for i, raw in enumerate(bad):
            with self.subTest(case=i), self.assertRaises(ValueError):
                self._from(raw)

    def test_constant_keys_message_counts_keys(self):
        base = self._raw()
        with self.assertRaisesRegex(ValueError, f"{len(policy.CONSTANT_KEYS)} constant keys"):
            self._from(dict(base, baseline={k: v for k, v in base["baseline"].items() if k != "resource_match_bonus"}))

    def test_returned_structures_are_immutable(self):
        rp = policy.ranking()
        with self.assertRaises(TypeError):
            rp.verb_methods["x"] = frozenset()
        with self.assertRaises(TypeError):
            rp.constants["method_match_bonus"] = 9


class TestFingerprintIncludesRanking(unittest.TestCase):
    def test_versions_and_block(self):
        self.assertEqual(policy.POLICY_VERSIONS["search"], 3)
        blk = policy.policy_block("A", "B")
        self.assertEqual(blk["ranking_sha256"], policy.ranking().sha256)
        self.assertEqual(blk["ranking_structure_sha256"], policy.ranking().structure_sha256)

    def test_fingerprint_sensitive_to_ranking(self):
        from unittest import mock
        a = policy.intelligence_fingerprint("reg", "A", "B")
        fake = policy.RankingPolicy(**{**policy.ranking().__dict__, "sha256": "f" * 64})
        with mock.patch.object(policy, "ranking", return_value=fake):
            self.assertNotEqual(a, policy.intelligence_fingerprint("reg", "A", "B"))
