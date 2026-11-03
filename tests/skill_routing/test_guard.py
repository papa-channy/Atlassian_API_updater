import json
import os
import subprocess
import sys

from tests.skill_routing import guard

P = "mcp__claude_ai_Atlassian_MCP__"


def test_read_tool_always_allowed():
    ok, _ = guard.decide(P + "getJiraIssue", {"issueIdOrKey": "SCRUM-1"}, set())
    assert ok is True


def test_write_with_rsbox_key_allowed():
    ok, _ = guard.decide(P + "createJiraIssue", {"projectKey": "RSBOX", "summary": "x"}, set())
    assert ok is True


def test_write_with_scrum_key_blocked():
    ok, why = guard.decide(P + "editJiraIssue", {"issueIdOrKey": "SCRUM-1"}, set())
    assert ok is False
    assert "SCRUM" in why


def test_mixed_keys_blocked():
    ok, _ = guard.decide(
        P + "editJiraIssue", {"issueIdOrKey": "RSBOX-1", "note": "see SCRUM-1"}, set()
    )
    assert ok is False


def test_numeric_id_blocked_unless_allowlisted():
    args = {"name": "manageJiraProjectVersion", "inputs": {"versionId": "10001"}}
    assert guard.decide(P + "executeDestructive", args, set())[0] is False
    assert guard.decide(P + "executeDestructive", args, {"10001"})[0] is True


def test_write_without_any_identifier_blocked():
    ok, _ = guard.decide(P + "executeWrite", {"name": "x", "inputs": {}}, set())
    assert ok is False


def _run_main(stdin, env_extra):
    env = dict(os.environ, **env_extra)
    return subprocess.run(
        [sys.executable, "-m", "tests.skill_routing.guard"],
        input=stdin, capture_output=True, text=True, env=env,
    )


def test_main_bad_json_blocks_write_tool(tmp_path):
    r = _run_main("{not json", {"ROUTING_TEST_LOG": str(tmp_path / "l.jsonl"),
                               "ROUTING_TEST_ALLOW_FILE": str(tmp_path / "a.txt")})
    assert r.returncode == 2


def test_main_logs_every_call(tmp_path):
    log = tmp_path / "l.jsonl"
    payload = json.dumps({"tool_name": P + "getJiraIssue",
                          "tool_input": {"issueIdOrKey": "RSBOX-1"}})
    r = _run_main(payload, {"ROUTING_TEST_LOG": str(log),
                            "ROUTING_TEST_ALLOW_FILE": str(tmp_path / "a.txt")})
    assert r.returncode == 0
    row = json.loads(log.read_text().splitlines()[0])
    assert set(row) >= {"ts", "tool", "input", "allowed"}
    assert row["allowed"] is True
