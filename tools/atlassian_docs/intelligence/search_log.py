"""Opt-in local jsonl log of search queries (spec §8). Only search_operations writes here."""
import datetime
import json
import os
import pathlib
import re

from .. import storage

ENV_VAR = "ATLASSIAN_DOCS_SEARCH_LOG"
MAX_QUERY_CHARS = 2048
ROTATE_BYTES = 5 * 1024 * 1024
_CONTROL = re.compile(r"[\x00-\x1f]")


def enabled() -> bool:
    return os.environ.get(ENV_VAR, "").strip().lower() in ("1", "true", "yes")


def log_path() -> pathlib.Path:
    return storage.CACHE_DIR / "intelligence" / "search_log.jsonl"


def _append(path: pathlib.Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= ROTATE_BYTES:
        os.replace(path, path.with_name(path.name + ".prev"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def record(payload: dict, filters: dict) -> None:
    if not enabled():
        return
    try:
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query": _CONTROL.sub(" ", str(payload.get("query", "")))[:MAX_QUERY_CHARS],
            "filters": filters,
            "query_tokens": payload.get("query_tokens", []), "alias_tokens": payload.get("alias_tokens", []),
            "exact_match": payload.get("exact_match", False), "total_matches": payload.get("total_matches", 0),
            "top": [{"key": r["key"], "score": r["score"]} for r in payload.get("results", [])[:3]],
            "intelligence_fingerprint": payload.get("intelligence_fingerprint"),
        }
        _append(log_path(), json.dumps(rec, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        return
