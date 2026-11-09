"""Opt-in local jsonl log of search queries (spec §8) and, since Round 6 (spec §6), selection records from get_operation / build_request_template."""
import datetime
import itertools
import json
import os
import pathlib
import re
import uuid

from .. import storage

ENV_VAR = "ATLASSIAN_DOCS_SEARCH_LOG"
MAX_QUERY_CHARS = 2048
ROTATE_BYTES = 5 * 1024 * 1024
_CONTROL = re.compile(r"[\x00-\x1f]")
SERVER_SESSION_ID = str(uuid.uuid4())          # Round 6 spec §6: one per MCP server process
_SEQ = itertools.count(1)
TOP_KEYS = 10                                   # spec §6: selection matching needs the top-10 keys


def next_seq() -> int:
    return next(_SEQ)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enabled() -> bool:
    return os.environ.get(ENV_VAR, "").strip().lower() in ("1", "true", "yes")


def log_path() -> pathlib.Path:
    return storage.CACHE_DIR / "intelligence" / "search_log.jsonl"


def _append(path: pathlib.Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= ROTATE_BYTES:
        os.replace(path, path.with_name(path.name + ".prev"))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)   # raw queries: owner-only, like the cache
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def record(payload: dict, filters: dict) -> None:
    if not enabled():
        return
    try:
        rec = {
            "ts": _now(), "kind": "search",
            "query": _CONTROL.sub(" ", str(payload.get("query", "")))[:MAX_QUERY_CHARS],
            "filters": filters,
            "query_tokens": payload.get("query_tokens", []), "alias_tokens": payload.get("alias_tokens", []),
            "exact_match": payload.get("exact_match", False), "total_matches": payload.get("total_matches", 0),
            "top": [{"key": r["key"], "score": r["score"]} for r in payload.get("results", [])[:TOP_KEYS]],
            "intelligence_fingerprint": payload.get("intelligence_fingerprint"),
            "actionable": payload.get("actionable"), "recommended_operation": payload.get("recommended_operation"),
            "abstain_reason": payload.get("abstain_reason"), "method_intent_consistent": payload.get("method_intent_consistent"),
            "server_session_id": SERVER_SESSION_ID, "call_seq": next_seq(),
        }
        _append(log_path(), json.dumps(rec, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        return


def record_selection(tool: str, key, fingerprint) -> None:
    """spec §6: get_operation / build_request_template calls; never argument values or headers."""
    if not enabled():
        return
    try:
        rec = {"ts": _now(), "kind": "selection", "tool": tool, "key": key, "intelligence_fingerprint": fingerprint,
               "server_session_id": SERVER_SESSION_ID, "call_seq": next_seq()}
        _append(log_path(), json.dumps(rec, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        return


def qualifying_records(lines, fingerprint) -> list:
    """spec §6 qualifying window: search records of the currently adopted fingerprint only."""
    return [l for l in lines if l.get("kind", "search") == "search" and l.get("intelligence_fingerprint") == fingerprint]


def match_selections(lines) -> list:
    """spec §6 (review 2 P1-5): per selection, the most recent earlier search of the same server session whose logged top keys
    contain the selected key; unmatched selections are dropped."""
    out = []
    for i, sel in enumerate(lines):
        if sel.get("kind") != "selection":
            continue
        for s in reversed(lines[:i]):
            if (s.get("kind", "search") == "search" and s.get("server_session_id") == sel.get("server_session_id")
                    and s.get("call_seq", 0) < sel.get("call_seq", 0) and sel.get("key") in [t.get("key") for t in s.get("top", [])]):
                out.append({"selection_seq": sel["call_seq"], "search_seq": s["call_seq"], "key": sel["key"],
                            "recommended_matches": s.get("recommended_operation") == sel["key"]})
                break
    return out
