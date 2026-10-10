"""Weighted lexical operation search: tokenizer + prebuilt index (spec §13)."""
import contextlib
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


LEGACY_ORDERING_RULES = {"intent_tier": False, "preferred_method_tiebreak": False, "terminal_alias_full_weight": False,
                         "singular_collection_tiebreak": False}


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


def is_identifier_query(query: str) -> bool:
    """Round 3 spec §3.6/§3.7 scope (v1.24.1): a single whitespace-free word that splits into 2+ unigrams (CamelCase / joined
    schema or operation name such as IssueCreateMetadata, createIssue) is an exact-name lookup, not an action query. Multi-word
    queries are never identifier queries, so hyphenated natural language ("update issue-summary") keeps the ordering rules."""
    q = (query or "").strip()
    return bool(q) and not any(ch.isspace() for ch in q) and bool(joined_query_forms(q))


def ordering_rules_for(rules, identifier_query: bool) -> dict:
    """Ordering rules in effect: tier and tie-break are switched off for identifier queries (embedded verbs are not an action
    intent); scoring rules are unaffected."""
    if not identifier_query:
        return dict(rules)
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


# ---- Round 6 spec §3: recommendation rules R0–R3 (boolean, no constants) ----------------------------------------------------
PRODUCT_NAME_TOKENS = frozenset().union(*(tokenize_unigrams(s) for s in sources.SOURCES))   # {confluence, jira, platform, software}
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RULES = ("R0", "R1", "R2", "R3")
_enabled = frozenset(RULES)


@contextlib.contextmanager
def scorer_rules(enabled):
    """Evaluation-only switch (Round 6 plan PR-3): the scorer-rule counterexample compares OFF (()) with ON (RULES). Never read
    from policy files and never set by the MCP server."""
    global _enabled
    prev, _enabled = _enabled, frozenset(enabled)
    try:
        yield
    finally:
        _enabled = prev


def enabled_rules() -> tuple:
    return tuple(r for r in RULES if r in _enabled)


def literal_path_tokens(path) -> tuple:
    """Unigrams of the literal (non-{param}) path segments, digits dropped, noise kept (order preserved, may repeat)."""
    out = []
    for seg in (path or "").split("/"):
        if not seg or (seg.startswith("{") and seg.endswith("}")):
            continue
        out += [t for t in tokenize_unigrams(seg) if not t.isdigit()]
    return tuple(out)


_VOCAB: dict = {}


def op_vocabulary(op) -> frozenset:
    """spec §3.2: operationId · path literal · summary · tag tokens (singular/plural forms)."""
    k = (op.source, op.key, op.operation_id, op.summary, tuple(op.tags))
    if k not in _VOCAB:
        toks = set(tokenize(op.operation_id)) | set(tokenize(op.summary)) | set(expand_token_forms(literal_path_tokens(op.path)))
        for t in op.tags:
            toks |= tokenize(t)
        _VOCAB[k] = frozenset(toks)
    return _VOCAB[k]


_CONCEPTS: dict = {}


def concept_vocabulary(state, noise) -> frozenset:
    """Catalog concept words (singular): path literal tokens minus path_noise, plus tag tokens (Round 3 concept_tokens)."""
    k = (state.registry.fingerprint, frozenset(noise))
    if k not in _CONCEPTS:
        out = set()
        for sr in state.registry.sources.values():
            for op in sr.operations:
                out |= {singular(t) for t in literal_path_tokens(op.path) if t not in noise}
                for tag in op.tags:
                    out |= {singular(t) for t in tokenize_unigrams(tag)}
        _CONCEPTS[k] = frozenset(out)
    return _CONCEPTS[k]


_PLACEHOLDER = re.compile(r"\{[^}]*\}")


def rule_unigrams(query) -> tuple:
    """Round 6 plan PR-7: rule inputs ignore {param} placeholders (a canonical key's parameter names are not resources)."""
    return tokenize_unigrams(_PLACEHOLDER.sub(" ", query or ""))


def content_tokens(unigrams, verb_methods) -> tuple:
    """spec §3.2a content(q): query unigrams minus verb keys minus product-name tokens (unknown words included)."""
    return tuple(t for t in unigrams if t not in verb_methods and t not in PRODUCT_NAME_TOKENS)


def head_info(unigrams, verb_methods, concepts):
    """spec §3.2: the LAST non-verb, non-product-name token whose singular is a catalog concept word."""
    head = None
    for t in unigrams:
        if t in verb_methods or t in PRODUCT_NAME_TOKENS:
            continue
        s = singular(t)
        if s in concepts:
            head = {"concept": s, "original_token": t,
                    "number": "singular" if t == s else "plural" if t in (s + "s", s + "es") else "unknown"}
    return head


R1_BOUNDARY = frozenset({"in", "for", "of", "on", "with", "by", "at"})     # spec v1.7 §3.2 (to/from are not boundaries)


def r1_tokens(query) -> tuple:
    """Placeholder-free, camel-split, lower-case tokens (length >= 2) KEEPING stopwords and duplicates: the R1 span needs the
    prepositions tokenize_unigrams drops."""
    text = _PLACEHOLDER.sub(" ", query or "")
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", text)).lower()
    return tuple(t for t in _SPLIT.split(text) if len(t) >= 2)


def r1_head(query, verb_methods, concepts):
    """spec v1.7 §3.2: head_info over the direct-object span - after the first verb, up to the first boundary preposition."""
    toks = r1_tokens(query)
    first = next((i for i, t in enumerate(toks) if t in verb_methods), None)
    if first is None:
        return None
    span = []
    for t in toks[first + 1:]:
        if t in R1_BOUNDARY:
            break
        if t not in STOPWORDS:
            span.append(t)
    return head_info(tuple(span), verb_methods, concepts)


def covered(token, vocab, aliases) -> bool:
    """spec §3.2a: token_forms(t) ∪ token_forms(direct alias targets of t's forms) meets the operation vocabulary."""
    forms = set(token_forms(token))
    for f in list(forms):
        for target in aliases.get(f, ()):
            forms |= token_forms(target)
    return bool(forms & vocab)


def abstain_reason(*, allowed, top_op, pinned, unigrams, rp, pol, concepts, query=None):
    """spec §3.1 precedence: no_method_intent > no_resource_evidence (R0) > product_conflict (R2) > uncovered_head_resource (R1).
    pinned: the top result is an exact key/operationId pin (counts as R0 evidence, spec §3.2a review 4 P1-1). query: the raw query for
    the R1 direct-object span (spec v1.7); without it the span is read from the rule unigrams."""
    if not allowed:
        return "no_method_intent"
    if top_op is None:
        return None
    vocab = op_vocabulary(top_op)
    if "R0" in _enabled and not pinned and not any(covered(t, vocab, pol.aliases) for t in content_tokens(unigrams, rp.verb_methods)):
        return "no_resource_evidence"
    if "R2" in _enabled:
        hinted = set()
        for t in unigrams:
            hinted |= rp.product_hints.get(t, frozenset())
        if hinted and top_op.source not in hinted:
            return "product_conflict"
    if "R1" in _enabled and top_op.method.upper() in WRITE_METHODS:
        h = r1_head(query if query is not None else " ".join(unigrams), rp.verb_methods, concepts)
        if h is not None and not covered(h["concept"], vocab, pol.aliases):
            return "uncovered_head_resource"
    return None


def _collection_item(coll, item) -> bool:
    """item is coll + one '/{param}' segment, same source and method."""
    base = (coll.path or "").rstrip("/")
    rest = (item.path or "")[len(base):]
    return (coll.source == item.source and coll.method == item.method and (item.path or "").startswith(base + "/")
            and rest.count("/") == 1 and rest.startswith("/{") and rest.endswith("}"))


def _reorder_run(run, number):
    run = list(run)
    ops = [c[1] for c in run]
    pairs = sorted(((a, b) for a in ops for b in ops if _collection_item(a, b)), key=lambda p: (p[0].key, p[1].key))
    for coll, item in pairs:
        pref, other = (item, coll) if number == "singular" else (coll, item)
        keys = [c[1].key for c in run]
        pi, oi = keys.index(pref.key), keys.index(other.key)
        if pi > oi:
            run.insert(oi, run.pop(pi))
    return run


def singular_collection_order(cands, number, group_key) -> list:
    """spec §3.4 R3: inside each run of equal group_key (tier, exact final score), put the single item first for a singular head
    and the collection first for a plural head; nothing else moves."""
    if number not in ("singular", "plural"):
        return list(cands)
    out, i = list(cands), 0
    while i < len(out):
        j = i
        while j + 1 < len(out) and group_key(out[j + 1]) == group_key(out[i]):
            j += 1
        if j > i:
            out[i:j + 1] = _reorder_run(out[i:j + 1], number)
        i = j + 1
    return out


def order_candidates(cands, rules, allowed, preferred, number=None) -> list:
    """Production ordering, shared with the tuning GridEvaluator. cands: (final, op, signals, method)."""
    key = lambda c: _order_key(rules, allowed, preferred, c[0], c[3], c[1].deprecated, c[1].key)
    out = sorted(cands, key=key)
    if "R3" in _enabled and rules.get("singular_collection_tiebreak"):
        out = singular_collection_order(out, number, lambda c: (key(c)[0], c[0]))
    return out


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
    rules = ordering_rules_for(rp.ordering_rules, is_identifier_query(query))
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
    concepts, run = concept_vocabulary(state, rp.path_noise), rule_unigrams(query)
    head = head_info(run, rp.verb_methods, concepts)
    candidates = order_candidates(candidates, rules, allowed, preferred, head["number"] if head else None)
    non_pinned = [c for c in candidates if c[1].key not in pinned_keys]
    pinned_score = (non_pinned[0][0] if non_pinned else 0.0) + 1.0
    results = [_item(op, pinned_score, _zero_signals(), kind) for op, kind in pinned] + \
              [_item(op, final, signals) for final, op, signals, _m in non_pinned]
    payload = {"query": query, "results": results[:limit], "total_matches": len(pinned) + len(non_pinned),
               "exact_match": bool(pinned), "query_tokens": sorted(exp.base),
               "alias_tokens": sorted(exp.direct | exp.cond), "expanded_tokens": sorted(exp.all)}
    shown = payload["results"]
    payload["method_intent_consistent"] = bool(allowed)
    payload["intent_methods"] = sorted(allowed) if allowed else []
    top_op = None
    if shown:
        top_op = state.registry.sources[shown[0]["source"]].operations_by_key[shown[0]["key"]]
    reason = abstain_reason(allowed=allowed, top_op=top_op, pinned=bool(shown) and shown[0]["key"] in pinned_keys,
                            unigrams=run, rp=rp, pol=pol, concepts=concepts, query=query)
    payload["abstain_reason"] = reason
    payload["actionable"] = payload["method_intent_consistent"] and reason is None          # Round 6 spec §3.1
    payload["recommended_operation"] = shown[0]["key"] if payload["actionable"] and shown else None
    ov = policy.overrides()
    payload["intelligence_fingerprint"] = policy.intelligence_fingerprint(
        state.registry.fingerprint, pol.sha256, ov.sha256)
    payload["intelligence_policy"] = policy.policy_block(pol.sha256, ov.sha256)
    search_log.record(payload, {"source": source, "method": method, "tag": tag,
                                 "include_deprecated": include_deprecated, "limit": limit})
    return provenance.with_provenance(payload, state, scope)
