"""Curated policy data (aliases, quirk overrides), canonical hashes and fingerprints (spec §6.1, §9.3, §10)."""
import functools
import hashlib
import json
import pathlib
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from . import search
from .headers import CREDENTIAL_HEADERS

POLICY_VERSIONS = {"search": 2, "quirks": 1, "oas_transpiler": 1}
DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
_KEY = re.compile(r"^[a-z][a-z0-9-]*:[A-Z]+:/")
_ACTIONS, _ENFORCEMENT, _VALUE_POLICY = ("set", "suppress"), ("advisory", "required"), ("observed", "literal")


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _read(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _token_ok(tok) -> bool:
    """A token is normalized if tokenize(tok) returns exactly {tok}, or -
    for a plural spec token like "transitions" - {tok, singular(tok)}."""
    if not isinstance(tok, str) or not tok:
        return False
    toks = search.tokenize(tok)
    if toks == frozenset({tok}):
        return True
    if len(tok) > 3 and tok.endswith("s") and toks == frozenset({tok, tok[:-1]}):
        return True
    return False


@dataclass(frozen=True)
class AliasRule:
    when_all: frozenset
    add: tuple


@dataclass(frozen=True)
class AliasPolicy:
    alias_damping: float
    rule_damping: float
    aliases: Mapping[str, tuple]
    rules: tuple
    sha256: str


def load_aliases(path: Optional[pathlib.Path] = None) -> AliasPolicy:
    raw = _read(path or DATA_DIR / "search_aliases.json")
    if not isinstance(raw, dict) or not isinstance(raw.get("aliases") or {}, dict) \
            or not isinstance(raw.get("rules") or [], list):
        raise ValueError("alias policy must be an object with an 'aliases' object and a 'rules' list")
    for k in ("alias_damping", "rule_damping"):
        v = raw.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 1:
            raise ValueError(f"{k} must be a number in 0..1")
    aliases = {}
    for key, vals in (raw.get("aliases") or {}).items():
        if not _token_ok(key) or not isinstance(vals, list) or not vals or not all(_token_ok(v) for v in vals):
            raise ValueError(f"alias entry {key!r} is not a normalized token -> [tokens]")
        aliases[key] = tuple(vals)
    rules = []
    for r in raw.get("rules") or []:
        if not isinstance(r, dict):
            raise ValueError(f"invalid rule {r!r}")
        when, add = r.get("when_all"), r.get("add")
        if not isinstance(when, list) or not when or not isinstance(add, list) or not add \
                or not all(_token_ok(t) for t in when + add):
            raise ValueError(f"invalid rule {r!r}")
        rules.append(AliasRule(frozenset(when), tuple(add)))
    return AliasPolicy(float(raw["alias_damping"]), float(raw["rule_damping"]),
                       MappingProxyType(aliases), tuple(rules), canonical_sha256(raw))


@dataclass(frozen=True)
class HeaderOverride:
    name: str
    action: str
    value: Optional[str]
    enforcement: str
    value_policy: str
    note: Optional[str]


@dataclass(frozen=True)
class OverrideEntry:
    headers: tuple
    request_hints: dict
    notes: tuple


@dataclass(frozen=True)
class QuirkOverrides:
    operations: Mapping[str, OverrideEntry]
    sha256: Optional[str]


def load_quirk_overrides(path: Optional[pathlib.Path] = None) -> QuirkOverrides:
    path = path or DATA_DIR / "operation_quirks.json"
    if not path.exists():
        return QuirkOverrides(MappingProxyType({}), None)
    raw = _read(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("operations") or {}, dict):
        raise ValueError("quirk overrides must be an object with an 'operations' object")
    ops = {}
    for key, entry in (raw.get("operations") or {}).items():
        if not _KEY.match(key) or not isinstance(entry, dict):
            raise ValueError(f"invalid override key {key!r}")
        seen: dict = {}
        headers = []
        if not isinstance(entry.get("headers") or [], list):
            raise ValueError(f"headers must be a list in {key}")
        for h in entry.get("headers") or []:
            if not isinstance(h, dict):
                raise ValueError(f"invalid header override in {key}: {h!r}")
            name, action = h.get("name"), h.get("action", "set")
            if not isinstance(name, str) or not name or action not in _ACTIONS:
                raise ValueError(f"invalid header override in {key}: {h!r}")
            low = name.lower()
            if low in CREDENTIAL_HEADERS:   # a quirk must never inject a credential header (spec §14)
                raise ValueError(f"credential header {name!r} not allowed in overrides ({key})")
            if h.get("note") is not None and not isinstance(h.get("note"), str):
                raise ValueError(f"header note must be a string in {key}")
            if low in seen:
                raise ValueError(f"duplicate or conflicting header {name!r} in {key}")
            seen[low] = action
            if action == "suppress":
                headers.append(HeaderOverride(name, action, None, "advisory", "observed", h.get("note")))
                continue
            enf, vp = h.get("enforcement", "required"), h.get("value_policy", "literal")
            if enf not in _ENFORCEMENT or vp not in _VALUE_POLICY:
                raise ValueError(f"invalid enforcement/value_policy in {key}: {h!r}")
            value = h.get("value")
            if value is not None and not isinstance(value, str):
                raise ValueError(f"header value must be a string in {key}")
            headers.append(HeaderOverride(name, action, value, enf, vp, h.get("note")))
        hints = entry.get("request_hints") or {}
        if not isinstance(hints, dict):
            raise ValueError(f"request_hints must be an object in {key}")
        if not isinstance(hints.get("multipart_fields", []), list):
            raise ValueError(f"multipart_fields must be a list in {key}")
        for f in hints.get("multipart_fields", []):
            if not isinstance(f, dict) or not isinstance(f.get("name"), str) or f.get("kind") not in ("file", "text") \
                    or not isinstance(f.get("required", False), bool):
                raise ValueError(f"invalid multipart field in {key}: {f!r}")
        notes = entry.get("notes") or []
        if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
            raise ValueError(f"notes must be a list of strings in {key}")
        ops[key] = OverrideEntry(tuple(headers), json.loads(json.dumps(hints)), tuple(notes))
    return QuirkOverrides(MappingProxyType(ops), canonical_sha256(raw))


@functools.lru_cache(maxsize=1)
def aliases() -> AliasPolicy:
    return load_aliases()


@functools.lru_cache(maxsize=1)
def overrides() -> QuirkOverrides:
    return load_quirk_overrides()


def intelligence_fingerprint(registry_fingerprint: str, aliases_sha256: str, overrides_sha256: Optional[str]) -> str:
    blob = "\n".join([registry_fingerprint, aliases_sha256, overrides_sha256 or "-",
                      json.dumps(POLICY_VERSIONS, sort_keys=True, separators=(",", ":"))])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def policy_block(aliases_sha256: str, overrides_sha256: Optional[str]) -> dict:
    return {"aliases_sha256": aliases_sha256, "overrides_sha256": overrides_sha256, "versions": dict(POLICY_VERSIONS)}
