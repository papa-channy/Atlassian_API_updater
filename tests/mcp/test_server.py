import asyncio
import importlib.util
import json
import tempfile
import unittest

from tests.mcp.test_tools import ATT, make_manager

HAS_MCP = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(HAS_MCP, "mcp SDK not installed (pip install -r requirements-mcp.txt)")
class TestServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.m, patcher = make_manager(self.tmp.name, "jira-platform", "confluence"); self.addCleanup(patcher.stop)

    def _call(self, coro):
        return asyncio.run(coro)

    def _client(self):
        # mcp 2.x: the high-level Client connects in-process when given an MCPServer instance.
        from mcp import Client
        from tools.atlassian_docs.mcp import server
        return Client(server.create_server(self.m))

    def test_tools_list_has_exactly_seven(self):
        async def go():
            async with self._client() as client:
                result = await client.list_tools()
                return sorted(t.name for t in result.tools)
        from tools.atlassian_docs.mcp import tools
        self.assertEqual(self._call(go()), sorted(tools.TOOL_NAMES))

    def test_each_tool_call_succeeds(self):
        cases = {
            "search_operations": {"query": "upload attachment to issue"},
            "get_operation": {"key": ATT},
            "get_schema": {"source": "jira-platform", "name": "MultipartFile"},
            "build_request_template": {"key": ATT},
            "check_request": {"key": ATT, "path_params": {"issueIdOrKey": "A-1"}},
            "get_api_status": {},
            "refresh_api_docs": {},
        }
        async def go():
            async with self._client() as client:
                out = {}
                for name, args in cases.items():
                    res = await client.call_tool(name, args)
                    out[name] = (res.is_error, json.loads(res.content[0].text))
                return out
        results = self._call(go())
        self.assertEqual(set(results), set(cases))
        for name, (is_error, payload) in results.items():
            self.assertFalse(is_error, name); self.assertNotIn("error", payload, name)

    def test_error_marks_is_error(self):
        async def go():
            async with self._client() as client:
                res = await client.call_tool("get_operation", {"key": "jira-platform:GET:/nope"})
                return res.is_error, json.loads(res.content[0].text)
        is_error, payload = self._call(go())
        self.assertTrue(is_error); self.assertEqual(payload["error"]["code"], "operation_not_found")

    def test_check_request_body_forwarded(self):
        async def go():
            async with self._client() as client:
                res = await client.call_tool("check_request", {"key": ATT, "path_params": {"issueIdOrKey": "A"},
                                                               "body": [{}], "content_type": "multipart/form-data"})
                return res.is_error, json.loads(res.content[0].text)
        is_error, payload = self._call(go())
        self.assertFalse(is_error); self.assertFalse(any(e["rule"] == "body_required" for e in payload["errors"]))

    def test_check_request_body_present_false_warns(self):
        async def go():
            async with self._client() as client:
                res = await client.call_tool("check_request", {"key": ATT, "path_params": {"issueIdOrKey": "A"},
                                                               "body_present": False, "body": {"x": 1},
                                                               "content_type": "multipart/form-data"})
                return res.is_error, json.loads(res.content[0].text)
        is_error, payload = self._call(go())
        self.assertFalse(is_error)
        self.assertTrue(any(w["rule"] == "body_ignored" for w in payload["warnings"]))
        self.assertTrue(any(e["rule"] == "body_required" for e in payload["errors"]))
