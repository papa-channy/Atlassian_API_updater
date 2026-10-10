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


class TestSearchLogMode(unittest.TestCase):
    """M8: the log holds raw user queries -> created owner-only (0600), like the cache's last-good files."""

    @unittest.skipIf(os.name != "posix", "POSIX file modes only")
    def test_log_file_created_0600(self):
        import stat
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "intelligence" / "search_log.jsonl"
            old = os.umask(0o022)
            try:
                search_log._append(path, "{}")
            finally:
                os.umask(old)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


class TestRound6SearchLog(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.td = tempfile.TemporaryDirectory(); self.path = pathlib.Path(self.td.name) / "intelligence" / "search_log.jsonl"
        self.p1 = mock.patch.object(search_log, "log_path", return_value=self.path)
        self.p2 = mock.patch.dict(os.environ, {search_log.ENV_VAR: "1"})
        self.p1.start(); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop(); self.td.cleanup()

    def lines(self):
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]

    def test_search_record_fields(self):
        payload = {"query": "create issue", "results": [{"key": f"k{i}", "score": 1.0} for i in range(12)], "actionable": False,
                   "recommended_operation": None, "abstain_reason": "product_conflict", "method_intent_consistent": True,
                   "intelligence_fingerprint": "fp"}
        search_log.record(payload, {"limit": 10})
        rec = self.lines()[0]
        self.assertEqual(rec["kind"], "search")
        self.assertEqual([t["key"] for t in rec["top"]], [f"k{i}" for i in range(10)])
        for f in ("actionable", "recommended_operation", "abstain_reason", "method_intent_consistent", "server_session_id", "call_seq"):
            self.assertIn(f, rec)
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_selection_record_has_no_argument_values(self):
        search_log.record_selection("build_request_template", "jira-platform:POST:/rest/api/3/issue", "fp")
        rec = self.lines()[0]
        self.assertEqual(set(rec), {"ts", "kind", "tool", "key", "intelligence_fingerprint", "server_session_id", "call_seq"})
        self.assertEqual(rec["kind"], "selection")

    def test_call_seq_increases_and_session_constant(self):
        search_log.record({"query": "a", "results": []}, {}); search_log.record_selection("get_operation", "k", "fp")
        a, b = self.lines()
        self.assertLess(a["call_seq"], b["call_seq"]); self.assertEqual(a["server_session_id"], b["server_session_id"])

    def test_match_most_recent_result_containing_search(self):
        L = [{"kind": "search", "server_session_id": "s", "call_seq": 1, "top": [{"key": "A"}, {"key": "B"}], "recommended_operation": "A"},
             {"kind": "search", "server_session_id": "s", "call_seq": 2, "top": [{"key": "C"}], "recommended_operation": "C"},
             {"kind": "selection", "server_session_id": "s", "call_seq": 3, "key": "B"},
             {"kind": "selection", "server_session_id": "t", "call_seq": 4, "key": "B"},
             {"kind": "selection", "server_session_id": "s", "call_seq": 5, "key": "Z"}]
        m = search_log.match_selections(L)
        self.assertEqual([(x["selection_seq"], x["search_seq"], x["recommended_matches"]) for x in m], [(3, 1, False)])

    def test_qualifying_records_filter_by_fingerprint(self):
        L = [{"kind": "search", "intelligence_fingerprint": "old"}, {"kind": "search", "intelligence_fingerprint": "new"},
             {"kind": "selection", "intelligence_fingerprint": "new"}]
        self.assertEqual(len(search_log.qualifying_records(L, "new")), 1)


class TestDispatchSelectionLogging(unittest.TestCase):
    def test_get_operation_and_template_log_selection(self):
        from tools.atlassian_docs.mcp import tools as T
        mgr = mock.MagicMock()
        with mock.patch.object(T.insp, "get_operation", return_value={"intelligence_fingerprint": "fp"}), \
                mock.patch.object(T.request_template, "build_request_template", return_value={"intelligence_fingerprint": "fp"}), \
                mock.patch.object(T.search_log, "record_selection") as rs:
            T._dispatch(mgr, "get_operation", {"key": "K1"}); T._dispatch(mgr, "build_request_template", {"key": "K2", "values": {"x": 1}})
        self.assertEqual([c.args for c in rs.call_args_list], [("get_operation", "K1", "fp"), ("build_request_template", "K2", "fp")])
