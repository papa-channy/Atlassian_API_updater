"""Fail-closed PreToolUse guard for the routing-skill sandbox tests (spec 5.1).

Test tooling only: it is registered in .claude/settings.local.json during a
test run and removed afterwards. It never calls Atlassian.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

PREFIX = "mcp__claude_ai_Atlassian_MCP__"
WRITE_SUFFIXES = {
    "createJiraIssue", "editJiraIssue", "transitionJiraIssue",
    "addOrEditJiraIssueComment", "createConfluenceContent",
    "updateConfluenceContent", "executeWrite", "executeDestructive",
}
ALLOWED_PROJECT = "RSBOX"
_ISSUE_KEY = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-\d+\b")
_PROJECT_FIELDS = {"projectKey", "project", "projectIdOrKey", "projectKeys"}


def is_write_tool(tool_name: str) -> bool:
    return tool_name.startswith(PREFIX) and tool_name[len(PREFIX):] in WRITE_SUFFIXES


def _walk(value, project_keys, numbers):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _PROJECT_FIELDS and isinstance(v, str):
                project_keys.add(v)
            elif k in _PROJECT_FIELDS and isinstance(v, list):
                project_keys.update(x for x in v if isinstance(x, str))
            _walk(v, project_keys, numbers)
    elif isinstance(value, list):
        for v in value:
            _walk(v, project_keys, numbers)
    elif isinstance(value, bool):
        pass
    elif isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        numbers.add(str(value))


def decide(tool_name: str, tool_input: dict, allow_ids: set) -> tuple:
    if not is_write_tool(tool_name):
        return True, "read tool"
    project_keys, numbers = set(), set()
    _walk(tool_input, project_keys, numbers)
    keys = {m.group(1) for m in _ISSUE_KEY.finditer(json.dumps(tool_input))} | project_keys
    if keys:
        outside = sorted(keys - {ALLOWED_PROJECT})
        if outside:
            return False, "outside RSBOX: " + ",".join(outside)
        return True, "RSBOX key"
    if numbers and numbers <= allow_ids:
        return True, "allow-listed ids"
    return False, "cannot confirm RSBOX scope (fail-closed)"


def _load_allow(path) -> set:
    try:
        with open(path, encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except (OSError, TypeError):
        return set()


def _log(path, row):
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    log = os.environ.get("ROUTING_TEST_LOG")
    ts = datetime.now(timezone.utc).isoformat()
    try:
        payload = json.loads(sys.stdin.read())
        tool, tool_input = payload["tool_name"], payload.get("tool_input") or {}
    except (ValueError, KeyError, TypeError):
        _log(log, {"ts": ts, "tool": None, "input": None, "allowed": False})
        print("guard: unreadable hook input (fail-closed)", file=sys.stderr)
        return 2
    ok, why = decide(tool, tool_input, _load_allow(os.environ.get("ROUTING_TEST_ALLOW_FILE")))
    _log(log, {"ts": ts, "tool": tool, "input": tool_input, "allowed": ok})
    if not ok:
        print("guard blocked: " + why, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
