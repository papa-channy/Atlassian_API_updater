"""Weighted lexical operation search: tokenizer + prebuilt index (spec §13)."""
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .. import sources
from . import provenance, schemas, search_log

STOPWORDS = frozenset("a an the to of for in on at and or with by from is are be this that".split())
FIELD_WEIGHTS = {"operation_id": 5, "summary": 4, "tags": 3, "path": 3,
                 "schema_names": 2, "method": 1, "description": 1}
DESCRIPTION_INDEX_CHARS = 1000
_CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])")        # fooBar -> foo Bar
_CAMEL_2 = re.compile(r"([A-Z]{2,})([A-Z][a-z])")  # JQLQuery -> JQL Query
_SPLIT = re.compile(r"[^a-z0-9]+")


IRREGULAR_SINGULAR = {"statuses": "status"}          # observed in the real cache vocabulary only (spec §6.1)
UNCHANGED_PLURAL = frozenset({"series", "species", "news"})


def tokenize_unigrams(text: Optional[str]) -> tuple:
    if not text:
        return ()
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", text)).lower()
    out, seen = [], set()
    for tok in _SPLIT.split(text):
        if len(tok) < 2 or tok in STOPWORDS or tok in seen:
            continue
        seen.add(tok); out.append(tok)
    return tuple(out)


def singular(t: str) -> str:
    if t in IRREGULAR_SINGULAR:
        return IRREGULAR_SINGULAR[t]
    if t in UNCHANGED_PLURAL or len(t) <= 3:
        return t
    if t.endswith("ies"):
        return t[:-3] + "y"
    if t.endswith(("sses", "shes", "ches", "xes")):
        return t[:-2]
    if t.endswith(("ss", "us", "is")):
        return t
    if t.endswith("s"):
        return t[:-1]
    return t


def token_forms(t: str) -> frozenset:
    return frozenset({t, singular(t)})


def expand_token_forms(tokens) -> frozenset:
    out = set()
    for t in tokens:
        out |= token_forms(t)
    return frozenset(out)


def tokenize(text: Optional[str]) -> frozenset:
    return expand_token_forms(tokenize_unigrams(text))


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


def joined_query_forms(query: str) -> frozenset:
    """Each whitespace word that splits into 2+ unigrams contributes its joined lowercase form,
    so an exact schema name typed as one identifier (IssueCreateMetadata) matches the index's
    exact-name token (Phase 2.5 §5)."""
    out = set()
    for word in (query or "").split():
        joined = _JOIN.sub("", word.lower())
        if len(tokenize_unigrams(word)) >= 2 and len(joined) > 3 and joined not in STOPWORDS:
            out.add(joined)
    return frozenset(out)


def _query_tokens(query: str) -> frozenset:
    """Legacy helper retained for exact-identifier callers: tokenize() plus joined query forms."""
    return tokenize(query) | joined_query_forms(query)


@dataclass(frozen=True)
class QueryExpansion:
    base: frozenset
    direct: frozenset
    cond: frozenset

    @property
    def all(self) -> frozenset:
        return self.base | self.direct | self.cond


def expand_query(query: str, pol) -> QueryExpansion:
    """base -> direct aliases once -> conditional rules once over base ∪ direct. No cascade (spec §6.2).
    base never contains joined forms (spec §6.1/§6.6)."""
    base = expand_token_forms(tokenize_unigrams(query))
    direct = set()
    for t in base:
        direct.update(pol.aliases.get(t, ()))
    direct = expand_token_forms(direct) - base
    trigger = base | direct
    cond = set()
    for rule in pol.rules:
        if rule.when_all <= trigger:
            cond.update(rule.add)
    cond = expand_token_forms(cond) - base - direct
    return QueryExpansion(frozenset(base), frozenset(direct), frozenset(cond))


def _score(entry: IndexEntry, exp: QueryExpansion, deprecated: bool, bonus_tokens: frozenset, pol) -> float:
    """bonus_tokens (tokenize(query), no joined forms) decide the all-match bonus, counted over base hits only."""
    ad, rd = pol.alias_damping, pol.rule_damping
    score = 0.0
    matched = set()
    for field, weight in FIELD_WEIGHTS.items():
        f = entry.fields[field]
        hb, hd, hc = exp.base & f, exp.direct & f, exp.cond & f
        score += weight * (len(hb) + ad * len(hd) + rd * len(hc))
        matched |= hb
    if score and bonus_tokens and bonus_tokens <= matched:
        score += ALL_MATCH_BONUS
    return score * DEPRECATED_FACTOR if deprecated else score


def _passes(op, method, tag, include_deprecated) -> bool:
    if method and op.method != method.upper():
        return False
    if tag and tag not in op.tags:
        return False
    return include_deprecated or not op.deprecated


def exact_matches(state, query: str, scope, method=None, tag=None, include_deprecated: bool = True) -> list:
    """Whitespace-free query equal to an operation key or operationId (case-sensitive first,
    case-insensitive fallback). Returns [(Operation, match_kind)] in key order, deduplicated."""
    q = (query or "").strip()
    if not q or any(ch.isspace() for ch in q):
        return []
    ops = [op for name in scope if (sr := state.registry.sources.get(name)) for op in sr.operations
           if _passes(op, method, tag, include_deprecated)]
    hits = [(op, "exact_key") for op in ops if op.key == q] + \
           [(op, "exact_operation_id") for op in ops if op.operation_id == q]
    if not hits:
        ql = q.lower()
        hits = [(op, "exact_operation_id_ci") for op in ops if op.operation_id and op.operation_id.lower() == ql]
    seen, out = set(), []
    for op, kind in sorted(hits, key=lambda h: h[0].key):
        if op.key not in seen:
            seen.add(op.key); out.append((op, kind))
    return out


def _item(op, s, match=None) -> dict:
    d = {"key": op.key, "source": op.source, "operation_id": op.operation_id, "method": op.method,
         "path": op.path, "summary": op.summary, "tags": list(op.tags), "deprecated": op.deprecated,
         "experimental": op.experimental, "score": round(s, 3)}
    if match:
        d["match"] = match
    return d


def search_operations(state, query: str, *, source=None, method=None, tag=None,
                      include_deprecated: bool = True, limit: int = 10) -> dict:
    from . import policy  # local import: policy imports search at module level
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        return provenance.error_response("invalid_argument", f"limit must be 1..{MAX_LIMIT}")
    if source is not None and source not in sources.SOURCES:
        return provenance.error_response("invalid_argument", f"unknown source {source!r}")
    pol = policy.aliases()
    exp = expand_query(query, pol)
    # Phase 2.5 lexical behaviour: joined identifier forms (e.g. "issuecreatemetadata") still
    # match the index's exact-name tokens, but never appear in QueryExpansion itself (spec §6.1).
    exp_lex = QueryExpansion(exp.base | joined_query_forms(query), exp.direct, exp.cond)
    bonus_tokens = tokenize(query)
    scope = [source] if source else sorted(sources.SOURCES)
    pinned = exact_matches(state, query, scope, method, tag, include_deprecated)
    pinned_keys = {op.key for op, _ in pinned}
    if not exp.base and not pinned:
        return provenance.error_response("empty_query", "query has no searchable tokens")
    scored = []
    for name in scope:
        sr = state.registry.sources.get(name)
        if sr is None:
            continue
        for entry in sr.search_index.entries:
            op = sr.operations_by_key[entry.key]
            if op.key in pinned_keys or not _passes(op, method, tag, include_deprecated):
                continue
            s = _score(entry, exp_lex, op.deprecated, bonus_tokens, pol)
            if s > 0:
                scored.append((s, op))
    scored.sort(key=lambda item: (-item[0], item[1].deprecated, item[1].source, item[1].key))
    top = (scored[0][0] if scored else 0.0) + 1.0
    results = [_item(op, top, kind) for op, kind in pinned] + [_item(op, s) for s, op in scored]
    payload = {"query": query, "results": results[:limit], "total_matches": len(pinned) + len(scored),
               "exact_match": bool(pinned), "query_tokens": sorted(exp.base),
               "alias_tokens": sorted(exp.direct | exp.cond), "expanded_tokens": sorted(exp.all)}
    ov = policy.overrides()
    payload["intelligence_fingerprint"] = policy.intelligence_fingerprint(
        state.registry.fingerprint, pol.sha256, ov.sha256)
    payload["intelligence_policy"] = policy.policy_block(pol.sha256, ov.sha256)
    search_log.record(payload, {"source": source, "method": method, "tag": tag,
                                 "include_deprecated": include_deprecated, "limit": limit})
    return provenance.with_provenance(payload, state, scope)
