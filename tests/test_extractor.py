import pathlib
import unittest

from tools.atlassian_docs import extractor

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestExtractOpenApiSpec(unittest.TestCase):
    def test_extracts_top_level_spec(self):
        spec = extractor.extract_openapi_spec(_read("jira-platform-minimal.html"))
        self.assertEqual(spec["openapi"], "3.0.1")
        self.assertEqual(spec["info"]["title"], "Jira Cloud Platform REST API")

    def test_extracts_nested_spec(self):
        spec = extractor.extract_openapi_spec(_read("confluence-nested-minimal.html"))
        self.assertEqual(spec["info"]["title"], "Confluence Cloud REST API")

    def test_tolerates_marker_whitespace_variants(self):
        spec = extractor.extract_openapi_spec(_read("marker-whitespace-variant.html"))
        self.assertEqual(spec["info"]["title"], "Whitespace Variant API")

    def test_missing_marker_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("missing-data.html"))

    def test_malformed_json_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("malformed-data.html"))

    def test_zero_candidates_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("no-openapi.html"))

    def test_multiple_candidates_raises_ambiguous_error(self):
        with self.assertRaises(extractor.AmbiguousExtractionError):
            extractor.extract_openapi_spec(_read("multiple-openapi.html"))

    def test_ambiguous_error_is_an_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("multiple-openapi.html"))

    def test_multiple_data_markers_raises_extraction_error(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_openapi_spec(_read("multiple-data-markers.html"))


class TestIsOpenApiCandidate(unittest.TestCase):
    def test_accepts_empty_paths(self):
        node = {"openapi": "3.0.1", "info": {}, "paths": {}}
        self.assertTrue(extractor.is_openapi_candidate(node))

    def test_rejects_missing_info(self):
        node = {"openapi": "3.0.1", "paths": {}}
        self.assertFalse(extractor.is_openapi_candidate(node))

    def test_rejects_missing_paths(self):
        node = {"openapi": "3.0.1", "info": {}}
        self.assertFalse(extractor.is_openapi_candidate(node))

    def test_rejects_non_dict(self):
        self.assertFalse(extractor.is_openapi_candidate("not a dict"))
        self.assertFalse(extractor.is_openapi_candidate(["a", "list"]))
        self.assertFalse(extractor.is_openapi_candidate(None))


class TestFindOpenApiCandidates(unittest.TestCase):
    def test_finds_candidate_nested_in_list(self):
        data = {"items": [{"not": "it"}, {"openapi": "3.0.1", "info": {}, "paths": {}}]}
        candidates = extractor.find_openapi_candidates(data)
        self.assertEqual(len(candidates), 1)

    def test_returns_empty_list_when_no_candidates(self):
        self.assertEqual(extractor.find_openapi_candidates({"a": 1, "b": [1, 2, 3]}), [])


if __name__ == "__main__":
    unittest.main()
