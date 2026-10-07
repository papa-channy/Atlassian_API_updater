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
class PathToken:
    """One distinct non-noise path unigram (origin) and its singular/plural forms (spec §6.4)."""
    origin: str
    forms: frozenset


@dataclass(frozen=True)
class IndexEntry:
    key: str
    fields: Mapping[str, frozenset]
    path_tokens: tuple          # of PathToken
    source: str
    method: str                 # upper-case HTTP method
    terminal_tokens: tuple = () # of str: origins of the last literal path segment (spec §6.5b)


def path_tokens_for(path: Optional[str], noise) -> tuple:
    """Literal (non-{param}) path segments -> unigrams, minus noise, each origin once, in path order."""
    out, seen = [], set()
    for seg in (path or "").split("/"):
        if not seg or (seg.startswith("{") and seg.endswith("}")):
            continue
        for tok in tokenize_unigrams(seg):
            if tok in noise or tok in seen:
                continue
            seen.add(tok); out.append(PathToken(tok, token_forms(tok)))
    return tuple(out)


def terminal_tokens_for(path: Optional[str]) -> tuple:
    """Last literal (non-{param}) path segment -> unigram origins minus all-digit tokens; noise is kept (spec §6.5b)."""
    for seg in reversed((path or "").split("/")):
        if not seg or (seg.startswith("{") and seg.endswith("}")):
            continue
        return tuple(t for t in tokenize_unigrams(seg) if not t.isdigit())
    return ()


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
    from . import policy  # local import: policy imports search at module level
    noise = policy.ranking().path_noise
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
        entries.append(IndexEntry(op.key, fields, path_tokens_for(op.path, noise), op.source, op.method.upper(),
                                  terminal_tokens_for(op.path)))
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


LEGACY_ORDERING_RULES = {"intent_tier": False, "preferred_method_tiebreak": False, "terminal_alias_full_weight": False}


def _score(entry, lexical_base: frozenset, direct: frozenset, cond: frozenset, bonus_tokens: tuple, pol, terminal_full: bool = False):
    """Lexical score of one entry (spec §6.6), all-match bonus included; returns (lexical, matched_base).
    bonus_tokens are the query unigrams: each must hit matched_base in some singular/plural form.
    Joined forms can add score but never cancel the bonus. Deprecation is applied by the caller.
    terminal_full (Round 3 spec §3.8): alias/rule tokens that are forms of the entry's terminal resource count at full weight;
    False reproduces the Round 2 formula exactly."""
    ad, rd = pol.alias_damping, pol.rule_damping
    term = expand_token_forms(entry.terminal_tokens) if terminal_full else frozenset()
    lexical = 0.0
    matched = set()
    for field, weight in FIELD_WEIGHTS.items():
        f = entry.fields[field]
        hb, d, c = lexical_base & f, direct & f, cond & f
        df, cf = d & term, c & term
        lexical += weight * (len(hb) + len(df) + ad * (len(d) - len(df)) + len(cf) + rd * (len(c) - len(cf)))
        matched |= hb
    matched_base = frozenset(matched)
    if lexical and bonus_tokens and all(token_forms(q) & matched_base for q in bonus_tokens):
        lexical += ALL_MATCH_BONUS
    return lexical, matched_base


def ordering_rules_for(rules, joined_forms) -> dict:
    """Round 3 spec §3.6/§3.7 scope (v1.24 ruling): the ordering rules read verb intent from natural-language queries. A query
    that contains an identifier-style word (CamelCase / joined schema or operation name, i.e. joined_query_forms non-empty) is
    an exact-name lookup whose embedded verbs are not an action intent -> legacy order for tier and tie-break (scoring unchanged)."""
    if not joined_forms:
        return rules
    return {**rules, "intent_tier": False, "preferred_method_tiebreak": False}


def _order_key(rules, allowed, preferred, final: float, method: str, deprecated: bool, key: str) -> tuple:
    """Sort key (Round 3 spec §3.6/§3.7, v1.24): (tier, -final, tiebreak, deprecated, key). tier demotes methods outside the
    verb intent; tiebreak prefers the first verb's preferred method among equal scores. All rules false -> the Round 2 order."""
    tier = 1 if rules["intent_tier"] and allowed and method not in allowed else 0
    tb = 1 if rules["preferred_method_tiebreak"] and allowed and preferred in allowed and method != preferred else 0
    return (tier, -final, tb, deprecated, key)


def method_intent(query_unigrams, verb_methods):
    """spec §3.3 (shared with the hidden-set machine check): inventory verbs in query order and the intersection of their
    allowed methods — None when the query has no inventory verb, possibly empty (conflicting verbs)."""
    verbs = [t for t in query_unigrams if t in verb_methods]
    allowed = None
    for v in verbs:
        methods = frozenset(verb_methods[v])
        allowed = methods if allowed is None else (allowed & methods)
    return verbs, allowed


def _structural_signals(entry, query_unigrams: tuple, exp_all: frozenset, rp, intent=None):
    """method intent + path specificity + product hint + terminal resource match (spec §6.3-§6.5b) + Round 3 method order and
    path coverage (Round 3 spec §3.1/§3.2); every number comes from rp. intent = method_intent(...) computed once per query."""
    c = rp.constants
    verbs, allowed = intent if intent is not None else method_intent(query_unigrams, rp.verb_methods)
    if not allowed:
        mi = {"value": 0.0, "allowed": []}
    elif entry.method in allowed:
        mi = {"value": c["method_match_bonus"], "allowed": sorted(allowed)}
    else:
        mi = {"value": 0.0 - c["method_mismatch_penalty"], "allowed": sorted(allowed)}   # 0.0 - x: never -0.0
    unmatched = sorted(pt.origin for pt in entry.path_tokens if not (pt.forms & exp_all))
    pu = {"value": 0.0 - min(len(unmatched), c["path_unmatched_cap"]) * c["path_unmatched_penalty"], "tokens": unmatched}
    hinted = set()
    for t in query_unigrams:
        hinted |= rp.product_hints.get(t, frozenset())
    ph = {"value": c["product_hint_bonus"] if entry.source in hinted else 0.0, "sources": sorted(hinted)}
    term = entry.terminal_tokens
    matched = bool(term) and all(token_forms(t) & exp_all for t in term)
    rm = {"value": c["resource_match_bonus"] if matched else 0.0, "tokens": list(term)}
    preferred = rp.verb_method_order[verbs[0]][0] if verbs else None                        # Round 2 prefix invariant: == Round 2's first
    order_hit = bool(allowed) and preferred in allowed and entry.method == preferred
    mo = {"value": c["method_order_bonus"] if order_hit else 0.0, "verb": verbs[0] if verbs else None, "preferred": preferred}
    covered = sorted({pt.origin for pt in entry.path_tokens if pt.forms & exp_all})
    pc = {"value": c["path_coverage_bonus"] * len(covered), "matched": covered}
    return mi["value"] + pu["value"] + ph["value"] + rm["value"] + mo["value"] + pc["value"], \
        {"method_intent": mi, "path_unmatched": pu, "product_hint": ph, "resource_match": rm, "method_order": mo, "path_coverage": pc}


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


def _zero_signals() -> dict:
    """Signals of a pinned exact match: all zero / empty (spec §6.7). Fresh dict per item."""
    return {"method_intent": {"value": 0.0, "allowed": []},
            "path_unmatched": {"value": 0.0, "tokens": []},
            "product_hint": {"value": 0.0, "sources": []},
            "resource_match": {"value": 0.0, "tokens": []},
            "method_order": {"value": 0.0, "verb": None, "preferred": None},
            "path_coverage": {"value": 0.0, "matched": []}}


def _item(op, s, signals, match=None) -> dict:
    d = {"key": op.key, "source": op.source, "operation_id": op.operation_id, "method": op.method,
         "path": op.path, "summary": op.summary, "tags": list(op.tags), "deprecated": op.deprecated,
         "experimental": op.experimental, "score": round(s, 3), "signals": signals}
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
    pol, rp = policy.aliases(), policy.ranking()
    unigrams = tokenize_unigrams(query)
    intent = method_intent(unigrams, rp.verb_methods)
    verbs, allowed = intent
    preferred = rp.verb_method_order[verbs[0]][0] if verbs else None
    terminal_full = rp.ordering_rules["terminal_alias_full_weight"]
    joined = joined_query_forms(query)
    rules = ordering_rules_for(rp.ordering_rules, joined)
    exp = expand_query(query, pol)                       # exp.base: unigram forms only (spec §6.1)
    lexical_base = exp.base | joined                     # Phase 2.5 exact-name matching kept (spec §6.6)
    scope = [source] if source else sorted(sources.SOURCES)
    pinned = exact_matches(state, query, scope, method, tag, include_deprecated)
    pinned_keys = {op.key for op, _ in pinned}
    if not exp.base and not pinned:
        return provenance.error_response("empty_query", "query has no searchable tokens")
    candidates = []
    for name in scope:
        sr = state.registry.sources.get(name)
        if sr is None:
            continue
        for entry in sr.search_index.entries:
            op = sr.operations_by_key[entry.key]
            if not _passes(op, method, tag, include_deprecated):
                continue
            lexical, _ = _score(entry, lexical_base, exp.direct, exp.cond, unigrams, pol, terminal_full)
            if lexical <= 0:
                continue
            structural, signals = _structural_signals(entry, unigrams, exp.all, rp, intent)
            final = max(lexical + structural, 0.0) * (DEPRECATED_FACTOR if op.deprecated else 1.0)
            if final == 0.0:
                continue
            candidates.append((final, op, signals, entry.method))
    candidates.sort(key=lambda c: _order_key(rules, allowed, preferred, c[0], c[3], c[1].deprecated, c[1].key))
    non_pinned = [c for c in candidates if c[1].key not in pinned_keys]
    pinned_score = (non_pinned[0][0] if non_pinned else 0.0) + 1.0
    results = [_item(op, pinned_score, _zero_signals(), kind) for op, kind in pinned] + \
              [_item(op, final, signals) for final, op, signals, _m in non_pinned]
    payload = {"query": query, "results": results[:limit], "total_matches": len(pinned) + len(non_pinned),
               "exact_match": bool(pinned), "query_tokens": sorted(exp.base),
               "alias_tokens": sorted(exp.direct | exp.cond), "expanded_tokens": sorted(exp.all)}
    verbs, allowed = intent
    shown = payload["results"]
    payload["method_intent_consistent"] = bool(allowed)
    payload["intent_methods"] = sorted(allowed) if allowed else []
    payload["actionable"] = payload["method_intent_consistent"]              # spec §3.3: the product abstains without a clear intent
    payload["recommended_operation"] = shown[0]["key"] if payload["actionable"] and shown else None
    ov = policy.overrides()
    payload["intelligence_fingerprint"] = policy.intelligence_fingerprint(
        state.registry.fingerprint, pol.sha256, ov.sha256)
    payload["intelligence_policy"] = policy.policy_block(pol.sha256, ov.sha256)
    search_log.record(payload, {"source": source, "method": method, "tag": tag,
                                 "include_deprecated": include_deprecated, "limit": limit})
    return provenance.with_provenance(payload, state, scope)
