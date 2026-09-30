import datetime
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs import storage, sync
from tools.atlassian_docs.intelligence import manager
from tools.atlassian_docs.mcp import tools

NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=datetime.timezone.utc)
ATT = "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments"


def make_manager(tmpdir, *fixtures):
    cache = pathlib.Path(tmpdir) / ".atlassian-docs"
    patcher = mock.patch.object(storage, "CACHE_DIR", cache); patcher.start()
    md = {}
    for name in fixtures:
        spec = load_fixture(name); storage.write_cache_spec(name, spec)
        md[name] = {"sha256": storage.sha256_of_spec(spec), "api_version": "v3", "last_checked": NOW.strftime(sync.TIMESTAMP_FORMAT),
                    "last_updated": NOW.strftime(sync.TIMESTAMP_FORMAT), "resolved_documentation_url": "https://d/"}
    storage.write_metadata(md)
    calls = []
    def fake_sync(force=False):
        calls.append(force); return [sync.SyncResult(s, "ok") for s in ("jira-platform", "jira-software", "confluence")]
    m = manager.RegistryManager(sync_all=fake_sync, clock=lambda: 0.0, now=lambda: NOW); m.start()
    m._test_sync_calls = calls  # type: ignore[attr-defined]
    return m, patcher


class TestRunTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.m, patcher = make_manager(self.tmp.name, "jira-platform", "confluence"); self.addCleanup(patcher.stop)

    def test_all_seven_tools_return_dicts(self):
        cases = {
            "search_operations": {"query": "upload attachment to issue"},
            "get_operation": {"key": ATT},
            "get_schema": {"source": "jira-platform", "name": "MultipartFile"},
            "build_request_template": {"key": ATT},
            "check_request": {"key": ATT, "path_params": {"issueIdOrKey": "A-1"}, "body": [{}], "content_type": "multipart/form-data"},
            "get_api_status": {},
            "refresh_api_docs": {},
        }
        for name in tools.TOOL_NAMES:
            out = tools.run_tool(self.m, name, cases[name])
            self.assertIsInstance(out, dict, name); self.assertNotIn("error", out, (name, out))
            json.dumps(out)

    def test_status_shape_and_no_ensure_fresh(self):
        out = tools.run_tool(self.m, "get_api_status", {})
        self.assertEqual(set(out["sources"]), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(out["execution"], "disabled"); self.assertIn("backoff_active", out["refresh"])
        self.assertEqual(self.m._test_sync_calls, [])
        self.assertFalse(out["refresh"]["in_progress"])

    def test_status_reports_in_progress_while_lock_held(self):
        with self.m._lock:
            out = tools.run_tool(self.m, "get_api_status", {})
        self.assertTrue(out["refresh"]["in_progress"])

    def test_ensure_fresh_called_only_for_intelligence_tools(self):
        with mock.patch.object(self.m, "ensure_fresh", wraps=self.m.ensure_fresh) as ef:
            tools.run_tool(self.m, "get_api_status", {})
            tools.run_tool(self.m, "refresh_api_docs", {})
            self.assertEqual(ef.call_count, 0)
            tools.run_tool(self.m, "search_operations", {"query": "issue"})
            tools.run_tool(self.m, "get_schema", {"source": "jira-platform", "name": "MultipartFile"})
            self.assertEqual(ef.call_count, 2)

    def test_body_absent_vs_null(self):
        absent = tools.run_tool(self.m, "check_request", {"key": ATT, "path_params": {"issueIdOrKey": "A"}, "content_type": "multipart/form-data"})
        self.assertTrue(any(e["rule"] == "body_required" for e in absent["errors"]))
        null = tools.run_tool(self.m, "check_request", {"key": ATT, "path_params": {"issueIdOrKey": "A"}, "body": None, "content_type": "multipart/form-data"})
        self.assertFalse(any(e["rule"] == "body_required" for e in null["errors"]))

    def test_unknown_tool_and_internal_error(self):
        self.assertEqual(tools.run_tool(self.m, "nope", {})["error"]["code"], "invalid_argument")
        with mock.patch("tools.atlassian_docs.mcp.tools.search.search_operations", side_effect=RuntimeError("kaboom")):
            out = tools.run_tool(self.m, "search_operations", {"query": "x"})
        self.assertEqual(out["error"]["code"], "internal_error")
        self.assertEqual(out["error"]["message"], "RuntimeError")

    def test_size_guard(self):
        big = {"blob": "x" * (tools.MAX_RESULT_BYTES + 1)}
        self.assertEqual(tools.guard_size(big)["error"]["code"], "result_too_large")
        self.assertEqual(tools.guard_size({"a": 1}), {"a": 1})
        self.assertEqual(tools.payload_size({"é": 1}), len(json.dumps({"é": 1}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
