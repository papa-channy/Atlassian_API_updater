"""Spec-external operation knowledge: advisory mining + curated overrides (spec §9)."""
import copy
import re
from dataclasses import asdict, dataclass
from typing import Any, Optional

from . import policy

MINED_HEADERS = ("X-Atlassian-Token",)
_MINED_CANON = {n.lower(): n for n in MINED_HEADERS}   # header identity is always name.lower() (spec §9.1)
_MINE = re.compile(r"`?(X-Atlassian-Token)\s*:\s*([A-Za-z0-9_-]+)`?", re.I)
_CANDIDATE = re.compile(r"\b(X-[A-Za-z0-9-]{2,})\b")


@dataclass(frozen=True)
class HeaderQuirk:
    name: str
    value: Optional[str]
    enforcement: str
    value_policy: str
    origin: str
    note: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MultipartField:
    name: str
    required: bool
    kind: str
    note: Optional[str]


@dataclass(frozen=True)
class OperationQuirks:
    key: str
    headers: tuple
    request_hints: dict
    notes: tuple
    suppressed: tuple

    def to_dict(self) -> dict:
        return {"key": self.key, "headers": [h.to_dict() for h in self.headers],
                "request_hints": dict(self.request_hints), "notes": list(self.notes), "suppressed": list(self.suppressed)}


def mine(op: Any) -> tuple:
    text = op.description or ""
    out, seen = [], set()
    for name, value in _MINE.findall(text):
        if name.lower() in _MINED_CANON and name.lower() not in seen:
            seen.add(name.lower())
            out.append(HeaderQuirk(_MINED_CANON[name.lower()], value, "advisory", "observed", "quirk:description", None))
    return tuple(out)


def for_operation(op: Any, overrides: Optional[policy.QuirkOverrides] = None) -> OperationQuirks:
    ov = overrides if overrides is not None else policy.overrides()
    mined = {h.name.lower(): h for h in mine(op)}
    entry = ov.operations.get(op.key)
    suppressed = []
    if entry is not None:
        for h in entry.headers:
            low = h.name.lower()
            if h.action == "suppress":
                if low in mined:
                    suppressed.append(mined.pop(low).name)
                continue
            mined[low] = HeaderQuirk(h.name, h.value, h.enforcement, h.value_policy, "quirk:override", h.note)
    headers = tuple(sorted(mined.values(), key=lambda h: h.name.lower()))
    hints = copy.deepcopy(entry.request_hints) if entry else {}
    notes = tuple(entry.notes) if entry else ()
    return OperationQuirks(op.key, headers, hints, notes, tuple(suppressed))


def orphaned_override_keys(registry: Any, overrides: Optional[policy.QuirkOverrides] = None) -> tuple:
    ov = overrides if overrides is not None else policy.overrides()
    return tuple(sorted(k for k in ov.operations if registry.get_operation(k) is None))


def header_candidates(registry: Any) -> tuple:
    out = []
    for name in registry.list_sources():
        for op in registry.sources[name].operations:
            for header in sorted(set(_CANDIDATE.findall(op.description or ""))):
                if header.lower() not in _MINED_CANON:
                    out.append({"key": op.key, "header": header})
    return tuple(out)


def outcome(q: HeaderQuirk, present: bool, value_matches: Optional[bool]) -> tuple:
    """(error_rule, warning_rule) per spec §9.3 table."""
    if not present:
        return ("required", None) if q.enforcement == "required" else (None, "advisory_header_missing")
    if value_matches is False:
        return ("quirk_value_mismatch", None) if q.value_policy == "literal" else (None, "quirk_value_mismatch")
    return (None, None)
