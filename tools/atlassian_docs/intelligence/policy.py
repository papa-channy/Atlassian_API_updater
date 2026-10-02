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

POLICY_VERSIONS = {"search": 3, "quirks": 1, "oas_transpiler": 1}
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
    if toks == frozenset({tok, search.singular(tok)}):
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


_NOTE_ORIGIN = re.compile(r"^(phase2\.5|round([1-9]\d*)|lexicon-r([1-9]\d*))$")
_SEED_ID = re.compile(r"s-\d{3}")               # always fullmatch


def _check_alias_notes(notes, expected_keys: set) -> None:
    """Round 2 spec §8: provenance notes per alias word / rule:<index>, schema branched by origin:
    phase2.5 (legacy), round1 (seed_query_id + R4), round>=2 (seed_query_id + candidate_word + R6),
    lexicon-rN (seed_query_id null, failure_classes empty)."""
    if not isinstance(notes, dict) or set(notes) != expected_keys:
        raise ValueError("alias 'notes' must cover exactly the alias words and rule:<index> keys")
    for key, n in notes.items():
        if not isinstance(n, dict) or not isinstance(n.get("origin"), str) \
                or not isinstance(n.get("failure_classes"), list) or not isinstance(n.get("evidence"), str):
            raise ValueError(f"alias note {key!r} must have origin, failure_classes and evidence")
        m = _NOTE_ORIGIN.fullmatch(n["origin"])
        if m is None:
            raise ValueError(f"alias note {key!r} has unknown origin {n['origin']!r}")
        cw, sid = n.get("candidate_word"), n.get("seed_query_id")
        if cw is not None and (not isinstance(cw, str) or not cw):
            raise ValueError(f"alias note {key!r}: candidate_word must be a non-empty string")
        if m.group(2):                                          # round N
            if not isinstance(sid, str) or not _SEED_ID.fullmatch(sid):
                raise ValueError(f"{n['origin']} alias note {key!r} needs seed_query_id s-NNN")
            if int(m.group(2)) == 1:
                if "R4" not in n["failure_classes"]:
                    raise ValueError(f"round1 alias note {key!r} needs R4 in failure_classes")
            elif "R6" not in n["failure_classes"] or cw is None:
                raise ValueError(f"{n['origin']} alias note {key!r} needs candidate_word and R6 in failure_classes")
        else:                                                   # phase2.5 / lexicon-rN
            if sid is not None:
                raise ValueError(f"{n['origin']} alias note {key!r} must have seed_query_id null")
            if m.group(3) and n["failure_classes"] != []:
                raise ValueError(f"{n['origin']} alias note {key!r} must have empty failure_classes")


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
    _check_alias_notes(raw.get("notes"), set(aliases) | {f"rule:{i}" for i in range(len(rules))})
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


_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid", "baseline")
CONSTANT_KEYS = ("method_match_bonus", "method_mismatch_penalty", "path_unmatched_penalty", "path_unmatched_cap", "product_hint_bonus",
                 "resource_match_bonus")
_WORD = re.compile(r"[a-z]+"); _NOISE = re.compile(r"[a-z0-9]+")   # always fullmatch ("get\n" must not pass)


def _str_list(v) -> bool:
    """A non-empty list of strings without duplicates (checked before set() so bad elements never raise TypeError)."""
    return isinstance(v, list) and bool(v) and all(isinstance(x, str) for x in v) and len(set(v)) == len(v)


@dataclass(frozen=True)
class RankingPolicy:
    version: int
    verb_methods: Mapping[str, frozenset]
    path_noise: frozenset
    product_hints: Mapping[str, frozenset]
    tuning_grid: Mapping[str, tuple]
    baseline: Mapping[str, float]
    constants: Mapping[str, float]
    sha256: str
    structure_sha256: str


def _num(v, name, integer=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")) or v < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    if integer and not isinstance(v, int):
        raise ValueError(f"{name} must be an int")
    return int(v) if integer else float(v)


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


def load_ranking(path: Optional[pathlib.Path] = None) -> RankingPolicy:
    from .. import sources
    raw = _read(path or DATA_DIR / "search_ranking.json")
    if not isinstance(raw, dict) or set(raw) != {"version", *STRUCTURE_KEYS, "constants"}:
        raise ValueError("ranking policy must have exactly version, verb_methods, path_noise, product_hints, tuning_grid, baseline, constants")
    if not isinstance(raw["version"], int) or isinstance(raw["version"], bool) or raw["version"] < 1:
        raise ValueError("version must be an int >= 1")
    verbs = {}
    for k, v in (raw["verb_methods"] or {}).items() if isinstance(raw["verb_methods"], dict) else [(None, None)]:
        if k is None or not _WORD.fullmatch(k) or not _str_list(v) or not set(v) <= _METHODS:
            raise ValueError(f"invalid verb_methods entry {k!r}")
        verbs[k] = frozenset(v)
    noise = raw["path_noise"]
    if not isinstance(noise, list) or not all(isinstance(t, str) and _NOISE.fullmatch(t) for t in noise) or len(set(noise)) != len(noise):
        raise ValueError("invalid path_noise")
    hints = {}
    for k, v in (raw["product_hints"] or {}).items() if isinstance(raw["product_hints"], dict) else [(None, None)]:
        if k is None or not _WORD.fullmatch(k) or not _str_list(v) or not set(v) <= set(sources.SOURCES):
            raise ValueError(f"invalid product_hints entry {k!r}")
        hints[k] = frozenset(v)
    grid, consts, basel = raw["tuning_grid"], raw["constants"], raw["baseline"]
    if not all(isinstance(d, dict) and set(d) == set(CONSTANT_KEYS) for d in (grid, consts, basel)):
        raise ValueError(f"tuning_grid, baseline and constants must each have exactly the {len(CONSTANT_KEYS)} constant keys")
    out_grid, out_consts, out_base = {}, {}, {}
    for k in CONSTANT_KEYS:
        integer = k == "path_unmatched_cap"
        vals = grid[k]
        if not isinstance(vals, list) or not vals:
            raise ValueError(f"tuning_grid[{k}] must be a non-empty list without duplicates")
        out_grid[k] = tuple(_num(v, f"tuning_grid[{k}]", integer) for v in vals)   # rejects non-numbers first
        if len(set(out_grid[k])) != len(vals):
            raise ValueError(f"tuning_grid[{k}] must be a non-empty list without duplicates")
        for name, src, dst in (("constants", consts, out_consts), ("baseline", basel, out_base)):
            c = _num(src[k], f"{name}[{k}]", integer)
            if c not in out_grid[k]:
                raise ValueError(f"{name}[{k}]={c} is outside its tuning grid")
            dst[k] = c
    return RankingPolicy(raw["version"], MappingProxyType(verbs), frozenset(noise), MappingProxyType(hints),
                         MappingProxyType(out_grid), MappingProxyType(out_base), MappingProxyType(out_consts),
                         canonical_sha256(raw), canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS}))


@functools.lru_cache(maxsize=1)
def ranking() -> RankingPolicy:
    return load_ranking()


@functools.lru_cache(maxsize=1)
def aliases() -> AliasPolicy:
    return load_aliases()


@functools.lru_cache(maxsize=1)
def overrides() -> QuirkOverrides:
    return load_quirk_overrides()


def intelligence_fingerprint(registry_fingerprint: str, aliases_sha256: str, overrides_sha256: Optional[str]) -> str:
    blob = "\n".join([registry_fingerprint, aliases_sha256, overrides_sha256 or "-", ranking().sha256,
                      json.dumps(POLICY_VERSIONS, sort_keys=True, separators=(",", ":"))])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def policy_block(aliases_sha256: str, overrides_sha256: Optional[str]) -> dict:
    return {"aliases_sha256": aliases_sha256, "overrides_sha256": overrides_sha256, "versions": dict(POLICY_VERSIONS),
            "ranking_sha256": ranking().sha256, "ranking_structure_sha256": ranking().structure_sha256}
