"""Round 5 spec §8: non-target counterexample suite (summary-as-query) over the canonical policy diff, four key classes,
uncovered-static diagnostics, partition and completeness validation. Pure core (`suite`) + production bindings."""
import pathlib, sys
if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tests.benchmarks import alias_candidates_tool as act
from tests.benchmarks.evaluator import canonical_sha256

CLASSES = ("covered_static", "uncovered_static", "covered_proposer", "uncovered_proposer")
DIAG_FIELDS = ("key", "provenance", "summary_slice_size", "opid_path_coverage", "title_rows", "changed_title_rows")


def canonical_policy_map(raw) -> dict:
    out = {("alias", w): tuple(sorted(t)) for w, t in (raw.get("aliases") or {}).items()}
    for r in raw.get("rules") or []:
        out[("phrase", tuple(sorted(r["when_all"])))] = tuple(sorted(r["add"]))
    return out


def diff(a: dict, b: dict) -> list:
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def counterexample_tokens(ckey) -> tuple:
    tag, body = ckey
    return (body,) if tag == "alias" else tuple(body)


def provenance_from_lexicon(lexicon_doc) -> dict:
    """Spec §8 provenance rules from concept_lexicon.json: selected entry → source/rank (+ gate_reason when the post-resolution gate
    removed it); no eligible candidate → source null + rejected_candidates."""
    out, rej = {}, lexicon_doc.get("rejected") or {}
    def ck(word):
        toks = tuple(word.split(" "))
        return ("phrase", tuple(sorted(toks))) if len(toks) > 1 else ("alias", word)
    for word, sel in (lexicon_doc.get("selected") or {}).items():
        out[ck(word)] = {"source": sel["source"], "provenance_rank": sel["provenance_rank"], **({"gate_reason": rej[word]["reason"]} if word in rej else {})}
    for word, r in rej.items():
        if ck(word) not in out and r.get("candidates"):
            out[ck(word)] = {"source": None, "rejected_candidates": r["candidates"]}
    return out


def suite(index, top1, pre_raw, static_raw, post_raw, summaries, titles=(), provenance=None, scope="lexicon_only", selected_constants=None) -> dict:
    """index: [{key, summary_tokens, opid_path_tokens}]; top1(policy_raw, query) -> op key or None; summaries: {op key: summary};
    titles: [{product, url, title}] (diagnostic only); provenance: {ckey: dict} for uncovered-static rows."""
    scope_name = scope
    pre, static, post = (canonical_policy_map(r) for r in (pre_raw, static_raw, post_raw))
    proposer = set(diff(static, post)); scope = diff(pre, post)
    classes = {c: [] for c in CLASSES}; losses, counts, diags, errors = [], {}, [], []
    for k in scope:
        toks = set(counterexample_tokens(k)); origin = "proposer" if k in proposer else "static"
        sl = [e for e in index if toks <= e["summary_tokens"]]
        cls = ("covered_" if sl else "uncovered_") + origin; classes[cls].append(list(k))
        pre_h = post_h = 0
        for e in sorted(sl, key=lambda e: e["key"]):
            q = summaries[e["key"]]; a, b = top1(pre_raw, q) == e["key"], top1(post_raw, q) == e["key"]
            pre_h += a; post_h += b
            if a and not b:
                losses.append({"key": list(k), "op": e["key"]})
        counts[" ".join(map(str, (k[0],) + tuple(counterexample_tokens(k))))] = {"slice": len(sl), "pre_hits": pre_h, "post_hits": post_h}
        if cls == "uncovered_static":
            rows = sorted({(t["product"], t["url"], t["title"]) for t in titles if toks <= set(act.norm_tokens(t["title"]))})
            seen, uniq = set(), []
            for r in rows:
                if r[1] not in seen:
                    seen.add(r[1]); uniq.append(r)
            changed = [{"title": r[2], "url": r[1], "pre_top1": top1(pre_raw, r[2]), "post_top1": top1(post_raw, r[2])} for r in uniq]
            prov = (provenance or {}).get(k)
            if prov is None or (prov.get("source") is None and not prov.get("rejected_candidates")):
                errors.append("counterexample_diagnostic_incomplete")
            diags.append({"key": list(k), "provenance": prov, "summary_slice_size": 0,
                          "opid_path_coverage": sorted(e["key"] for e in index if toks <= e["opid_path_tokens"]),
                          "title_rows": len(uniq), "changed_title_rows": [c for c in changed if c["pre_top1"] != c["post_top1"]]})
    flat = [tuple(map(lambda x: tuple(x) if isinstance(x, list) else x, v)) for c in CLASSES for v in classes[c]]
    if sorted(flat) != sorted(scope) or len(flat) != len(set(flat)):
        errors.append("counterexample_classification_invalid")
    if sorted(tuple(map(lambda x: tuple(x) if isinstance(x, list) else x, d["key"])) for d in diags) != sorted(map(tuple, (tuple(map(lambda x: tuple(x) if isinstance(x, list) else x, v)) for v in classes["uncovered_static"]))) \
            or any(f not in d for d in diags for f in DIAG_FIELDS):
        errors.append("counterexample_diagnostic_incomplete")
    errors = sorted(set(errors))
    return {"scope": scope_name, "scope_keys": [list(k) for k in scope], "classes": classes, "losses": losses, "per_key_counts": counts,
            "uncovered_static_diagnostics": diags, "validation_errors": errors, "selected_constants": dict(selected_constants or {}),
            "pre_policy_sha256": canonical_sha256(pre_raw), "static_policy_sha256": canonical_sha256(static_raw), "post_policy_sha256": canonical_sha256(post_raw),
            "ok": not losses and not classes["uncovered_proposer"] and not errors}


def catalog_index(state):
    index, summaries = [], {}
    for _name, sr in sorted(state.registry.sources.items()):
        for e in sr.search_index.entries:
            op = sr.operations_by_key[e.key]; summaries[e.key] = op.summary or ""
            index.append({"key": e.key, "summary_tokens": frozenset(act.norm_tokens(op.summary or "")),
                          "opid_path_tokens": frozenset(act.norm_tokens(op.operation_id or "")) | frozenset(t for p in e.path_tokens for t in act.norm_tokens(p.origin))})
    return index, summaries


def production_top1(state, rp, point):
    """top1(policy_raw, query) on the production search path at `point` (one alias policy load per distinct raw object)."""
    from unittest import mock
    from tests import tune_search_ranking as tune
    from tools.atlassian_docs.intelligence import policy, search
    cache = {}
    def top1(raw, q):
        ap = cache.setdefault(id(raw), (raw, tune._alias_policy(raw)))[1]
        with mock.patch.object(policy, "ranking", return_value=tune.ranking_with(rp, point)), mock.patch.object(policy, "aliases", return_value=ap):
            res = search.search_operations(state, q, limit=1).get("results") or []
        return res[0]["key"] if res else None
    return top1
