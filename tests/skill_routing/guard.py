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
    "addGraphContext",
}
ALLOWED_PROJECT = "RSBOX"
# Free text never identifies a target: a summary like "ISO-8601" or a description
# mentioning RSBOX-1 must neither block nor authorize a write.
_FREE_TEXT = {"summary", "description", "comment", "body", "title", "text",
              "environment", "name", "message"}
# Input fields that name the write target, and what kind of id they carry.
_TARGET_KIND = {
    "issueIdOrKey": "issue", "issueKey": "issue", "issueId": "issue", "issueIds": "issue",
    "versionId": "version",
    "projectId": "project", "projectIdOrKey": "project", "projectKey": "project",
    "projectKeys": "project", "project": "project",
}
_ISSUE_KEY = re.compile(r"\b([A-Za-z][A-Za-z0-9]{1,9})-\d+\b")
_JQL_PROJECT = re.compile(
    r'project\s*(?:=|!=|in)\s*\(?\s*((?:"?[A-Za-z0-9_]+"?\s*,?\s*)+)', re.IGNORECASE)


def is_write_tool(tool_name: str) -> bool:
    return tool_name.startswith(PREFIX) and tool_name[len(PREFIX):] in WRITE_SUFFIXES


def _scalars(value):
    if isinstance(value, list):
        for v in value:
            yield from _scalars(v)
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, (str, int)):
        yield str(value)


def _walk(value, field, strings, targets):
    """Collect scannable strings and (kind, value) targets, skipping free text."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _FREE_TEXT:
                continue
            if k in _TARGET_KIND and not isinstance(v, dict):
                for sc in _scalars(v):
                    targets.append((_TARGET_KIND[k], sc))
            elif k in _TARGET_KIND and isinstance(v, dict):
                for sub, kind in (("key", "project"), ("id", "project")):
                    if sub in v:
                        for sc in _scalars(v[sub]):
                            targets.append((kind, sc))
            _walk(v, k, strings, targets)
    elif isinstance(value, list):
        for v in value:
            _walk(v, field, strings, targets)
    elif isinstance(value, str):
        strings.append(value)


def decide(tool_name: str, tool_input: dict, allow_ids: set) -> tuple:
    if not is_write_tool(tool_name):
        return True, "read tool"
    strings, targets = [], []
    _walk(tool_input, None, strings, targets)
    projects, recognized = set(), False
    for text in strings:
        for m in _ISSUE_KEY.finditer(text):
            projects.add(m.group(1).upper())
        for m in _JQL_PROJECT.finditer(text):
            projects.update(t.strip('" ').upper() for t in m.group(1).split(",") if t.strip('" '))
    for kind, val in targets:
        if val.isdigit():
            if f"{kind}:{val}" not in allow_ids:
                return False, f"unlisted {kind} id {val} (fail-closed)"
            recognized = True
        elif kind == "project":
            projects.add(val.upper())
    outside = sorted(projects - {ALLOWED_PROJECT})
    if outside:
        return False, "outside RSBOX: " + ",".join(outside)
    if ALLOWED_PROJECT in projects:
        recognized = True
    if not recognized:
        return False, "cannot confirm RSBOX scope (fail-closed)"
    return True, "RSBOX scope confirmed"


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
