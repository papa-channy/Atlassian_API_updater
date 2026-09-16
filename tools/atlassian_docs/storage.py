"""Local file I/O for the cache and metadata. Knows nothing about Jira,
Confluence, or HTTP — just JSON files under CACHE_DIR, written atomically.
"""
import hashlib
import json
import os
import pathlib
import tempfile
from typing import Optional

CACHE_DIR = pathlib.Path(".atlassian-docs")
METADATA_FILENAME = "metadata.json"


def canonical_json_bytes(spec: dict) -> bytes:
    return json.dumps(
        spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_of_spec(spec: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(spec)).hexdigest()


def cache_path(source_name: str) -> pathlib.Path:
    return CACHE_DIR / f"{source_name}.json"


def metadata_path() -> pathlib.Path:
    return CACHE_DIR / METADATA_FILENAME


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path: pathlib.Path, text: str) -> None:
    ensure_cache_dir()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def read_metadata() -> dict:
    path = metadata_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return {}


def write_metadata(metadata: dict) -> None:
    text = json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False)
    _atomic_write_text(metadata_path(), text)


def read_cache_spec(source_name: str) -> Optional[dict]:
    path = cache_path(source_name)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return None


def write_cache_spec(source_name: str, spec: dict) -> None:
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False)
    _atomic_write_text(cache_path(source_name), text)
