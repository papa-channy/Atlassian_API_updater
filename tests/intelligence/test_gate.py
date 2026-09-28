import unittest

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs.intelligence import gate


class TestCompatibility(unittest.TestCase):
    def test_supported_dialects(self):
        for name in ("jira-platform", "confluence", "edge-cases"):
            self.assertTrue(gate.check_compatibility(load_fixture(name)).ok, name)

    def test_unsupported_dialect(self):
        r = gate.check_compatibility(load_fixture("unsupported-dialect"))
        self.assertFalse(r.ok); self.assertEqual(r.code, "incompatible_dialect")

    def test_invalid_structure(self):
        r = gate.check_compatibility({"openapi": "3.0.0", "paths": {}})   # no info
        self.assertEqual(r.code, "invalid_structure")

    def test_no_operations(self):
        r = gate.check_compatibility({"openapi": "3.0.0", "info": {}, "paths": {"/x": {"parameters": []}}})
        self.assertEqual(r.code, "no_operations")


class TestBuildCandidate(unittest.TestCase):
    def test_success(self):
        sr, result = gate.build_candidate("confluence", load_fixture("confluence"))
        self.assertTrue(result.ok); self.assertGreater(len(sr.operations), 0)

    def test_gate_failure_returns_none(self):
        sr, result = gate.build_candidate("x", load_fixture("unsupported-dialect"))
        self.assertIsNone(sr); self.assertEqual(result.code, "incompatible_dialect")

    def test_normalization_failure_maps_to_code(self):
        sr, result = gate.build_candidate("x", {"openapi": "3.0.0", "info": {}, "paths": {"/a": {"get": {}}}})
        self.assertTrue(result.ok)  # sanity: minimal op is fine
        # force NormalizationError via non-dict paths is blocked by compatibility; simulate by patching
        from unittest import mock
        with mock.patch("tools.atlassian_docs.intelligence.gate.normalizer.normalize_openapi",
                        side_effect=gate.normalizer.NormalizationError("boom")):
            sr, result = gate.build_candidate("x", load_fixture("confluence"))
        self.assertIsNone(sr); self.assertEqual(result.code, "normalization_failed")

    def test_invalid_components(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {"/a": {"get": {"responses": {}}}}, "components": {"schemas": []}}
        sr, result = gate.build_candidate("x", spec)
        self.assertIsNone(sr); self.assertEqual(result.code, "invalid_components")
