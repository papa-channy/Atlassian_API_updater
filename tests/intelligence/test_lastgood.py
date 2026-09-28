import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tools.atlassian_docs import storage
from tools.atlassian_docs.intelligence import lastgood


class TestLastGood(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(storage, "CACHE_DIR", pathlib.Path(self.tmp.name) / ".atlassian-docs")
        patcher.start(); self.addCleanup(patcher.stop)

    def test_round_trip_and_sha(self):
        spec = {"openapi": "3.0.0", "info": {}, "paths": {"/a": {"get": {}}}}
        self.assertIsNone(lastgood.read_last_good("confluence")); self.assertIsNone(lastgood.last_good_sha("confluence"))
        lastgood.write_last_good("confluence", spec)
        self.assertEqual(lastgood.read_last_good("confluence"), spec)
        self.assertEqual(lastgood.last_good_sha("confluence"), storage.sha256_of_spec(spec))
        self.assertTrue(lastgood.last_good_path("confluence").name.endswith(".last-good.json"))
        self.assertEqual(lastgood.last_good_path("confluence").parent, storage.CACHE_DIR / "intelligence")

    def test_invalid_json_reads_as_none(self):
        lastgood.last_good_dir().mkdir(parents=True)
        lastgood.last_good_path("jira-platform").write_text("{not json", encoding="utf-8")
        self.assertIsNone(lastgood.read_last_good("jira-platform"))

    def test_write_is_atomic_no_tmp_left(self):
        lastgood.write_last_good("x", {"a": 1})
        self.assertEqual([p.name for p in lastgood.last_good_dir().iterdir()], ["x.last-good.json"])
