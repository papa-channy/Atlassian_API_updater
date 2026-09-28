"""Durable last-known-good raw spec per source (spec §11.3). Phase 1 owns .atlassian-docs/;
Phase 2 owns only the intelligence/ subdirectory. Atomic write mirrors storage.py without importing its private helper."""
import json
import os
import pathlib
import tempfile
from typing import Optional

from .. import storage


def last_good_dir() -> pathlib.Path:
    return storage.CACHE_DIR / "intelligence"


def last_good_path(source: str) -> pathlib.Path:
    return last_good_dir() / f"{source}.last-good.json"


def read_last_good(source: str) -> Optional[dict]:
    path = last_good_path(source)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (ValueError, OSError):  # ValueError covers JSONDecodeError and UnicodeDecodeError
        return None
    return data if isinstance(data, dict) else None

def write_last_good(source: str, spec: dict) -> None:
    path = last_good_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def last_good_sha(source: str) -> Optional[str]:
    spec = read_last_good(source)
    return storage.sha256_of_spec(spec) if spec is not None else None
