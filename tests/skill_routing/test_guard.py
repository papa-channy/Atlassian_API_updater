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
    assert guard.decide(P + "executeDestructive", args, {"version:10001"})[0] is True


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


ALLOW = {"issue:10004", "version:10000", "project:10001"}


def test_lowercase_scrum_key_blocked():
    ok, why = guard.decide(P + "editJiraIssue", {"issueIdOrKey": "scrum-1"}, ALLOW)
    assert ok is False and "SCRUM" in why


def test_rsbox_mention_in_description_does_not_authorize_numeric_id():
    args = {"issueIdOrKey": "10500", "fields": {"description": "relates to RSBOX-1"}}
    assert guard.decide(P + "editJiraIssue", args, ALLOW)[0] is False


def test_nested_project_dict_scrum_blocked():
    args = {"fields": {"project": {"key": "SCRUM"}, "summary": "dup of RSBOX-2"}}
    assert guard.decide(P + "createJiraIssue", args, ALLOW)[0] is False


def test_jql_other_project_blocked():
    args = {"name": "x", "inputs": {"jql": "project = SCRUM AND key != RSBOX-1"}}
    assert guard.decide(P + "executeWrite", args, ALLOW)[0] is False


def test_version_id_is_not_valid_as_project_id():
    args = {"name": "x", "inputs": {"fields": {"project": {"id": "10000"}}}}
    assert guard.decide(P + "executeWrite", args, ALLOW)[0] is False


def test_typed_project_id_allowed():
    args = {"name": "x", "inputs": {"projectId": "10001"}}
    assert guard.decide(P + "executeWrite", args, ALLOW)[0] is True


def test_iso_8601_in_free_text_does_not_block_rsbox_write():
    args = {"projectKey": "RSBOX", "summary": "ISO-8601 and UTF-8 report", "description": "SHA-256"}
    assert guard.decide(P + "createJiraIssue", args, ALLOW)[0] is True


def test_add_graph_context_is_a_write_tool():
    args = {"objectIdentifier": "SCRUM-1"}
    assert guard.is_write_tool(P + "addGraphContext") is True
    assert guard.decide(P + "addGraphContext", args, ALLOW)[0] is False
