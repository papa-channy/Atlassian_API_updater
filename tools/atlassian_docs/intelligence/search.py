"""Weighted lexical operation search: tokenizer + prebuilt index (spec §13)."""
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .. import sources
from . import provenance, schemas

STOPWORDS = frozenset("a an the to of for in on at and or with by from is are be this that".split())
FIELD_WEIGHTS = {"operation_id": 5, "summary": 4, "tags": 3, "path": 3,
                 "schema_names": 2, "method": 1, "description": 1}
DESCRIPTION_INDEX_CHARS = 1000
_CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])")        # fooBar -> foo Bar
_CAMEL_2 = re.compile(r"([A-Z]{2,})([A-Z][a-z])")  # JQLQuery -> JQL Query
_SPLIT = re.compile(r"[^a-z0-9]+")


def tokenize(text: Optional[str]) -> frozenset:
    if not text:
        return frozenset()
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", text)).lower()
    out = set()
    for tok in _SPLIT.split(text):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        out.add(tok)
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
            out.add(tok[:-1])
    return frozenset(out)


@dataclass(frozen=True)
class IndexEntry:
    key: str
    fields: Mapping[str, frozenset]


@dataclass(frozen=True)
class SearchIndex:
    entries: tuple


def _schema_names(op: Any) -> frozenset:
    names: set = set()
    if op.request_body:
        for media in op.request_body.content:
            names.update(schemas.collect_local_ref_names(media.schema))
    for resp in op.responses:
        for media in resp.content:
            names.update(schemas.collect_local_ref_names(media.schema))
    for p in op.parameters:
        names.update(schemas.collect_local_ref_names(p.schema))
    toks: set = set()
    for n in names:
        toks.add(n.lower())          # exact type name, e.g. "issuecreatemetadata"
        toks |= tokenize(n)          # split parts, e.g. "issue", "create", "metadata"
    return frozenset(toks)


def build_index(operations: tuple) -> SearchIndex:
    entries = []
    for op in operations:
        fields = {
            "operation_id": tokenize(op.operation_id),
            "summary": tokenize(op.summary),
            "tags": frozenset().union(*(tokenize(t) for t in op.tags)) if op.tags else frozenset(),
            "path": tokenize(op.path),
            "schema_names": _schema_names(op),
            "method": frozenset({op.method.lower()}),
            "description": tokenize((op.description or "")[:DESCRIPTION_INDEX_CHARS]),
        }
        entries.append(IndexEntry(op.key, fields))
    return SearchIndex(tuple(entries))


MAX_LIMIT = 50
ALL_MATCH_BONUS = 2
DEPRECATED_FACTOR = 0.7
_JOIN = re.compile(r"[^a-z0-9]")


def _query_tokens(query: str) -> frozenset:
    """tokenize() plus each whitespace word's joined lowercase form, so an exact schema
    name typed as one identifier (IssueCreateMetadata) matches the index's exact-name token."""
    toks = set(tokenize(query))
    for word in (query or "").split():
        joined = _JOIN.sub("", word.lower())
        if len(joined) > 3:
            toks.add(joined)
    return frozenset(toks)


def _score(entry: IndexEntry, query_tokens: frozenset, deprecated: bool) -> float:
    score = 0.0
    matched_any_token = set()
    for field, weight in FIELD_WEIGHTS.items():
        hits = query_tokens & entry.fields[field]
        score += weight * len(hits)
        matched_any_token |= hits
    if score and matched_any_token == query_tokens:
        score += ALL_MATCH_BONUS
    return score * DEPRECATED_FACTOR if deprecated else score


def search_operations(state, query: str, *, source=None, method=None, tag=None,
                      include_deprecated: bool = True, limit: int = 10) -> dict:
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return provenance.error_response("invalid_argument", f"limit must be 1..{MAX_LIMIT}")
    if source is not None and source not in sources.SOURCES:
        return provenance.error_response("invalid_argument", f"unknown source {source!r}")
    query_tokens = _query_tokens(query)
    if not query_tokens:
        return provenance.error_response("empty_query", "query has no searchable tokens")
    scope = [source] if source else sorted(sources.SOURCES)
    scored = []
    for name in scope:
        sr = state.registry.sources.get(name)
        if sr is None:
            continue
        for entry in sr.search_index.entries:
            op = sr.operations_by_key[entry.key]
            if method and op.method != method.upper():
                continue
            if tag and tag not in op.tags:
                continue
            if not include_deprecated and op.deprecated:
                continue
            s = _score(entry, query_tokens, op.deprecated)
            if s > 0:
                scored.append((s, op))
    scored.sort(key=lambda item: (-item[0], item[1].deprecated, item[1].source, item[1].key))
    results = [{"key": op.key, "source": op.source, "operation_id": op.operation_id, "method": op.method,
                "path": op.path, "summary": op.summary, "tags": list(op.tags), "deprecated": op.deprecated,
                "experimental": op.experimental, "score": round(s, 3)}
               for s, op in scored[:limit]]
    payload = {"query": query, "results": results, "total_matches": len(scored)}
    return provenance.with_provenance(payload, state, scope)
