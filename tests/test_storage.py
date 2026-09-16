import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tools.atlassian_docs import storage


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patcher = mock.patch.object(
            storage, "CACHE_DIR", pathlib.Path(self._tmpdir.name) / ".atlassian-docs"
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()


class TestCanonicalJson(StorageTestCase):
    def test_key_order_does_not_affect_hash(self):
        spec_a = {"openapi": "3.0.1", "info": {"title": "X"}, "paths": {}}
        spec_b = {"paths": {}, "info": {"title": "X"}, "openapi": "3.0.1"}
        self.assertEqual(storage.sha256_of_spec(spec_a), storage.sha256_of_spec(spec_b))

    def test_different_content_produces_different_hash(self):
        spec_a = {"openapi": "3.0.1", "info": {"title": "X"}, "paths": {}}
        spec_b = {"openapi": "3.0.1", "info": {"title": "Y"}, "paths": {}}
        self.assertNotEqual(storage.sha256_of_spec(spec_a), storage.sha256_of_spec(spec_b))


class TestMetadataRoundtrip(StorageTestCase):
    def test_read_missing_metadata_returns_empty_dict(self):
        self.assertEqual(storage.read_metadata(), {})

    def test_write_then_read_roundtrips(self):
        metadata = {"jira-platform": {"api_version": "v3"}}
        storage.write_metadata(metadata)
        self.assertEqual(storage.read_metadata(), metadata)

    def test_write_creates_cache_dir(self):
        self.assertFalse(storage.CACHE_DIR.exists())
        storage.write_metadata({})
        self.assertTrue(storage.CACHE_DIR.is_dir())

    def test_write_leaves_no_tmp_files_behind(self):
        storage.write_metadata({"a": 1})
        leftovers = list(storage.CACHE_DIR.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class TestCacheSpecRoundtrip(StorageTestCase):
    def test_read_missing_cache_returns_none(self):
        self.assertIsNone(storage.read_cache_spec("jira-platform"))

    def test_write_then_read_roundtrips(self):
        spec = {"openapi": "3.0.1", "info": {"title": "X"}, "paths": {}}
        storage.write_cache_spec("jira-platform", spec)
        self.assertEqual(storage.read_cache_spec("jira-platform"), spec)

    def test_read_malformed_cache_file_returns_none(self):
        storage.ensure_cache_dir()
        storage.cache_path("jira-platform").write_text("{not valid json", encoding="utf-8")
        self.assertIsNone(storage.read_cache_spec("jira-platform"))

    def test_cache_filename_has_no_version_in_it(self):
        self.assertEqual(storage.cache_path("jira-platform").name, "jira-platform.json")


if __name__ == "__main__":
    unittest.main()
