import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from tests.intelligence.helpers import make_state
from tools.atlassian_docs import storage
from tools.atlassian_docs.intelligence import search, search_log


class TestSearchLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(storage, "CACHE_DIR", pathlib.Path(self.tmp.name) / ".atlassian-docs"); p.start(); self.addCleanup(p.stop)
        self.state = make_state("jira-platform")

    def test_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            search.search_operations(self.state, "create issue")
        self.assertFalse(search_log.log_path().exists())

    def test_enabled_writes_record_with_truncation(self):
        with mock.patch.dict(os.environ, {"ATLASSIAN_DOCS_SEARCH_LOG": "YES"}):
            search.search_operations(self.state, "create\x07 issue " + "x" * 3000, limit=3)
        rec = json.loads(search_log.log_path().read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(len(rec["query"]), search_log.MAX_QUERY_CHARS); self.assertNotIn("\x07", rec["query"])
        self.assertEqual(set(rec) >= {"ts", "query", "filters", "query_tokens", "alias_tokens", "exact_match", "total_matches", "top", "intelligence_fingerprint"}, True)
        self.assertLessEqual(len(rec["top"]), 3); self.assertEqual(rec["filters"]["limit"], 3)

    def test_write_failure_is_swallowed(self):
        with mock.patch.dict(os.environ, {"ATLASSIAN_DOCS_SEARCH_LOG": "1"}), \
             mock.patch("tools.atlassian_docs.intelligence.search_log._append", side_effect=OSError("disk")):
            out = search.search_operations(self.state, "create issue")
        self.assertIn("results", out)

    def test_rotation(self):
        with mock.patch.dict(os.environ, {"ATLASSIAN_DOCS_SEARCH_LOG": "1"}), \
             mock.patch.object(search_log, "ROTATE_BYTES", 10):
            search.search_operations(self.state, "create issue")
            search.search_operations(self.state, "create issue")
        self.assertTrue((search_log.log_path().parent / "search_log.jsonl.prev").exists())
