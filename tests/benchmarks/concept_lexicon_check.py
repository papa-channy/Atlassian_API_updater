"""Round 2 concept lexicon (spec §7.0): normalize a stateless generator's output, validate it against the catalog,
apply the stateless semantic review (validated: exact keys, booleans), cap per concept AFTER the review, and merge
into search_aliases.json as origin lexicon-rN.

  python tests/benchmarks/concept_lexicon_check.py prepare  --cache-dir S --raw RAW.json --out lexicon_structural.json
  python tests/benchmarks/concept_lexicon_check.py finalize --cache-dir S --raw RAW.json --structural lexicon_structural.json
         --review REVIEW.json --generation-input GEN_INPUT.txt --review-input REV_INPUT.txt
         --template tests/benchmarks/round2-lexicon-generation-prompt.md --out tools/.../concept_lexicon.json
  python tests/benchmarks/concept_lexicon_check.py merge --lexicon LEX.json --aliases tools/.../search_aliases.json --round 2
"""
import argparse, copy, hashlib, json, pathlib, re, sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.benchmarks import alias_candidates_tool as act
from tests.benchmarks import round_seal as rs
from tests.benchmarks.evaluator import STOPWORDS, canonical_sha256

MAX_PER_CONCEPT = 5
_SHAPE = re.compile(r"^[a-z0-9]+$")


def _rej(reason, targets, df=0):
    return {"reason": reason, "targets": list(targets), "catalog_df": df}


def phrase_set(key: str) -> frozenset:
    return frozenset(key.split(" "))


def normalize_raw(raw) -> dict:
    """Round 3 spec §6 (v1.25): a two-token phrase keeps the token order it was first seen in (the reviewer reads natural
    language); phrases with the same token set merge into that first key (when_all is a set), differing targets -> multi_target."""
    out, phrase_key = {}, {}
    for syn, targets in (raw or {}).items():
        toks = act.norm_tokens(str(syn))
        key = " ".join(toks) if toks else str(syn).lower()
        if len(toks) == 2:
            key = phrase_key.setdefault(frozenset(toks), key)
        vals = [t for target in (targets if isinstance(targets, list) else [targets]) for t in act.norm_tokens(str(target))]
        out.setdefault(key, set()).update(vals)
    return {k: sorted(v) for k, v in sorted(out.items())}


def is_phrase(key: str) -> bool:
    return " " in key


def _cross_product(syn, targets, token_sources) -> bool:
    """spec §6 v1.25: a catalog word may alias a target only when the word itself is a RESOURCE token somewhere and its resource
    sources are disjoint from the target's (workspace: jira-software vs space: confluence). A word that is catalog vocabulary only
    through summaries/operationIds has no resource sources and stays `in_catalog` (H12 review I1)."""
    if not token_sources or len(targets) != 1:
        return False
    own = set(token_sources.get(syn, ()))
    return bool(own) and not (own & set(token_sources.get(targets[0], ())))


def structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets=frozenset(), token_sources=None):
    """Single-word keys -> alias candidates (Round 2 rules; v1.25: `in_catalog` is waived when the word and its target are
    resources of disjoint products, `token_sources`). Two-token keys -> conditional-rule candidates (Round 3 spec §6 v1.24):
    catalog membership is not a rejection reason for a phrase (it adds context), an existing rule with the same when_all set is
    `rule_conflict`; three or more tokens are `shape`."""
    kept, rej = {}, {}
    for syn, targets in lex.items():
        toks = syn.split(" ")
        if len(toks) > 2 or any(not _SHAPE.fullmatch(t) or len(t) < 2 or t in STOPWORDS for t in toks):
            reason = "shape"
        elif len(toks) == 2:
            reason = ("id_like" if any(not any(c.isalpha() for c in t) or t in act.ID_LIKE for t in toks)
                      else "function_word" if any(t in act.FUNCTION_WORDS for t in toks)
                      else "verb" if any(t in verbs for t in toks) else "product_hint" if any(t in hints for t in toks)
                      else "rule_conflict" if frozenset(toks) in rule_sets else "multi_target" if len(targets) != 1
                      else "target_not_concept" if targets[0] not in concept_set else None)
        else:
            reason = ("id_like" if not any(c.isalpha() for c in syn) or syn in act.ID_LIKE
                      else "function_word" if syn in act.FUNCTION_WORDS
                      else "verb" if syn in verbs else "product_hint" if syn in hints
                      else "in_catalog" if syn in catalog_set and not _cross_product(syn, targets, token_sources)
                      else "alias_conflict" if syn in alias_keys else "multi_target" if len(targets) != 1
                      else "target_not_concept" if targets[0] not in concept_set else None)
        if reason:
            rej[syn] = _rej(reason, targets)
        else:
            kept[syn] = list(targets)
    return kept, rej


def prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets=frozenset(), token_sources=None):
    """Order (spec §7.0): normalize -> structural. No cap here: the semantic review sees every surviving synonym."""
    return structural_check(normalize_raw(raw), concept_set, catalog_set, verbs, hints, alias_keys, rule_sets, token_sources)


def union_docs(docs) -> dict:
    """Round 3 spec §5(b): several raw (or review) documents, first occurrence of a key wins (archive first)."""
    out = {}
    for d in docs:
        for k, v in (d or {}).items():
            out.setdefault(k, v)
    return out


SOURCE_RANK = {"round2_archive": 0, "round4_generation": 1}        # Round 5 spec §6.1: source identity, never CLI order


def canonical_key(syn: str) -> tuple:
    """A word -> (word,); a phrase -> its sorted token tuple (phrases with the same token set are one key)."""
    toks = tuple(syn.split(" "))
    return tuple(sorted(toks)) if len(toks) > 1 else toks


def review_pairs(review_input_text: str, review: dict) -> dict:
    """Round 5 spec §6.3: the verdict of every (key, targets) pair the reviewer actually saw (the ENTRIES object of its input)."""
    body = review_input_text.split("ENTRIES:", 1)[1].lstrip()
    entries, _ = json.JSONDecoder().raw_decode(body)
    out = {}
    for syn, targets in entries.items():
        if isinstance(review.get(syn), bool):
            out[(canonical_key(" ".join(act.norm_tokens(syn)) or syn), tuple(sorted(targets)))] = review[syn]
    return out


def merge_verdicts(pair_maps) -> tuple:
    """Agreeing past verdicts are reused; a pair judged both ways is a conflict (re-reviewed, never resolved by recency)."""
    seen = {}
    for m in pair_maps:
        for pair, v in m.items():
            seen.setdefault(pair, set()).add(v)
    return {p: next(iter(v)) for p, v in seen.items() if len(v) == 1}, sorted(p for p, v in seen.items() if len(v) > 1)


def resolve_verdicts(historical_maps, fresh_maps) -> tuple:
    """Round 5 spec §6.3: agreed historical verdicts are reused; a fresh (Round 5) verdict is authoritative only for pairs without an
    agreed historical verdict (unreviewed or conflicting) and is never merged into the conflicting set."""
    agreed, conflicts = merge_verdicts(historical_maps)
    fresh = {}
    for m in fresh_maps:
        for pair, v in m.items():
            if pair in agreed:
                continue                                            # fresh verdicts never override an agreed historical verdict
            if fresh.get(pair, v) != v:
                raise ValueError(f"two fresh reviews disagree on {pair}")
            fresh[pair] = v
    return {**agreed, **fresh}, [c for c in conflicts if c not in fresh]


def resolve_sources(sources, ctx, verdicts) -> dict:
    """Round 5 spec §6.1: keep every candidate, eligible = structural ∧ review (no benchmark input), highest source rank wins,
    then the inherited per-concept cap. `pending` lists (canonical key, targets, display key) with no agreed verdict."""
    concept_set, catalog_set, verbs, hints, alias_keys, rule_sets, token_sources = ctx
    cands = {}
    for src in sorted(sources, key=lambda s: SOURCE_RANK[s["id"]]):
        lex = normalize_raw(src["raw"])
        kept, rej = structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets, token_sources)
        for syn, targets in lex.items():
            cands.setdefault(canonical_key(syn), []).append({"source": src["id"], "rank": SOURCE_RANK[src["id"]], "key": syn,
                                                             "targets": list(targets), "reasons": [] if syn in kept else [rej[syn]["reason"]]})
    lexicon, rejected, selected, pending = {}, {}, {}, set()
    for ck, cs in sorted(cands.items()):
        eligible = []
        for c in cs:
            if c["reasons"]:
                continue
            v = verdicts.get((ck, tuple(sorted(c["targets"]))))
            if v is None:
                pending.add((ck, tuple(sorted(c["targets"])), c["key"])); c["reasons"] = ["unreviewed"]
            elif v:
                eligible.append(c)
            else:
                c["reasons"] = ["semantic-reject"]
        if eligible:
            best = max(eligible, key=lambda c: c["rank"])
            lexicon[best["key"]] = best["targets"]; selected[best["key"]] = {"source": best["source"], "provenance_rank": best["rank"]}
        else:
            last = cs[-1]
            rejected[last["key"]] = {**_rej("no-eligible-candidate", last["targets"]),
                                     "candidates": [{"source": c["source"], "provenance_rank": c["rank"], "targets": c["targets"], "reasons": c["reasons"]} for c in cs]}
    lexicon, capped = cap_per_concept(lexicon)
    rejected.update(capped)                                         # `selected` stays the resolution provenance ledger (cap → gate_reason "concept-cap")
    return {"lexicon": lexicon, "rejected": dict(sorted(rejected.items())), "selected": dict(sorted(selected.items())), "pending": sorted(pending)}


REVIEW_PLACEHOLDER = '<the "lexicon" object of lexicon_structural.json>'


def render_pending_review(template: str, pending) -> list:
    """Unreviewed pairs as review inputs (the committed Round 4 review template, byte-identical); pairs sharing a display key go
    to different batches so every ENTRIES object has unique keys."""
    batches = []
    for _ck, targets, key in sorted(pending, key=lambda p: (p[2], p[1])):
        for b in batches:
            if key not in b:
                b[key] = list(targets); break
        else:
            batches.append({key: list(targets)})
    if REVIEW_PLACEHOLDER not in template:
        raise ValueError("review template placeholder not found")
    return [template.replace(REVIEW_PLACEHOLDER, json.dumps(b, indent=1, ensure_ascii=False, sort_keys=True)) for b in batches]


def validate_review(review, keys, structurally_rejected=()) -> list:
    """Exact keys and booleans. `structurally_rejected`: synonyms the current structural stage rejected; a review that
    also judged them (a prior round's review re-gated on a later catalog/alias state, Round 3 spec §5) is still valid."""
    if not isinstance(review, dict):
        return ["review must be a JSON object keyed by synonym"]
    wanted, tolerated = set(keys), set(structurally_rejected)
    out = [f"missing key {k!r}" for k in keys if k not in review] + [f"extra key {k!r}" for k in review if k not in wanted and k not in tolerated]
    out += [f"{k!r}: value must be true/false" for k, v in review.items() if k in wanted and not isinstance(v, bool)]
    return out


def apply_review(lex, review, structurally_rejected=()):
    problems = validate_review(review, list(lex), structurally_rejected)
    if problems:
        raise ValueError("invalid semantic review: " + "; ".join(problems))
    kept, rej = {}, {}
    for syn, targets in lex.items():
        if review[syn]:
            kept[syn] = list(targets)
        else:
            rej[syn] = _rej("semantic-reject", targets)
    return kept, rej


def cap_per_concept(lex, limit=MAX_PER_CONCEPT):
    by_concept, kept, rej = {}, {}, {}
    for syn, targets in sorted(lex.items()):
        by_concept.setdefault((targets[0], is_phrase(syn)), []).append(syn)         # words and phrases capped separately (v1.24)
    for concept, syns in by_concept.items():
        for i, syn in enumerate(sorted(syns)):
            if i < limit:
                kept[syn] = lex[syn]
            else:
                rej[syn] = _rej("concept-cap", lex[syn])
    return dict(sorted(kept.items())), rej


def finalize(kept, rejected, review):
    """review (validated) -> per-concept cap; rejected entries accumulate."""
    rejected = dict(rejected)
    kept, r2 = apply_review(kept, review, rejected); rejected.update(r2)
    kept, r3 = cap_per_concept(kept); rejected.update(r3)
    return kept, dict(sorted(rejected.items()))


def build(raw, review, concept_set, catalog_set, verbs, hints, alias_keys, df=None, rule_sets=frozenset(), token_sources=None):
    kept, rejected = prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets, token_sources)
    lexicon, rejected = finalize(kept, rejected, review)
    for syn, e in rejected.items():
        e["catalog_df"] = (df or {}).get(syn, 0)
    return lexicon, rejected


def merge(aliases_raw, lexicon, round):
    out, skipped = copy.deepcopy(aliases_raw), []
    for syn, targets in sorted(lexicon.items()):
        if is_phrase(syn):                                                             # Round 3 spec §6 (v1.24): phrase -> when_all rule
            when_all = sorted(phrase_set(syn))
            if any(frozenset(r["when_all"]) == frozenset(when_all) for r in out["rules"]):
                skipped.append(syn); continue
            out["rules"].append({"when_all": when_all, "add": list(targets)})
            out["notes"][f"rule:{len(out['rules']) - 1}"] = {"origin": f"lexicon-r{round}", "seed_query_id": None, "failure_classes": [],
                                                              "evidence": f"concept lexicon r{round} phrase"}
            continue
        if syn in out["aliases"]:
            skipped.append(syn); continue
        out["aliases"][syn] = list(targets)
        out["notes"][syn] = {"origin": f"lexicon-r{round}", "seed_query_id": None, "failure_classes": [],
                             "evidence": f"concept lexicon r{round}"}
    return out, skipped


_WS = re.compile(r"\s+")


def _excerpt(description: str, limit: int = 160) -> str:
    """First sentence of an operation description, whitespace collapsed, '-' when empty (Round 3 spec §5(b) grounding excerpt)."""
    text = _WS.sub(" ", (description or "")).strip()
    if not text:
        return "-"
    first = text.split(". ")[0]
    first = first if first.endswith(".") or first == text else first + "."
    return first[:limit]


DOC_TITLES_PLACEHOLDER = '<one line per concept title: "<token>\\t<product>\\t<title words>">'


def render_lexicon_generation_input(template: str, internal, ranking_raw, doc_snapshot=None) -> str:
    """Round 3 spec §5(b): every concept token with count/products and a grounding excerpt (first sentence of the description of
    the lexicographically smallest op whose terminal literal segment is that token; '-' when none), plus the verb keys.
    Round 4 spec §6.1: with `doc_snapshot` the DOCUMENTATION TITLES placeholder becomes doc_titles.render_block(...). The bench
    is never an input of this function (AC-R4-05)."""
    noise = frozenset(ranking_raw["path_noise"])
    tokens = act.concept_tokens(internal, noise)
    by_terminal = {}
    for op in sorted(internal, key=lambda o: o["key"]):
        segs = act.path_literal_tokens(op["key"].split(":", 2)[2])
        if segs and segs[-1] not in noise:
            by_terminal.setdefault(segs[-1], op)
    lines = [f"{t}\t{e['count']}\t{','.join(e['sources'])}\t{_excerpt((by_terminal.get(t) or {}).get('description', ''))}" for t, e in tokens.items()]
    out = template.replace('<one line per concept: "<token>\\t<count>\\t<products>\\t<excerpt>">', "\n".join(lines))
    out = out.replace("<verb keys>", ", ".join(sorted(ranking_raw["verb_methods"])))
    if doc_snapshot is not None:
        from tests.benchmarks import doc_titles as dt
        out = out.replace(DOC_TITLES_PLACEHOLDER, dt.render_block(doc_snapshot, list(tokens)))
    if "<one line per concept" in out or "<verb keys>" in out:
        raise ValueError("generation template placeholders not found")
    return out


def _read(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _context(args):
    _, internal, fp, shas = rs.load_catalogs_from_cache(args.cache_dir, args.round)
    ranking, aliases = _read(act.DATA / "search_ranking.json"), _read(act.DATA / "search_aliases.json")
    rule_sets = frozenset(frozenset(r["when_all"]) for r in aliases.get("rules") or [])
    concepts = act.concept_tokens(internal, ranking["path_noise"])
    token_sources = {t: set(e["sources"]) for t, e in concepts.items()}                       # resource sources (spec §6 v1.25)
    return internal, fp, shas, ranking, aliases, (set(concepts), act.catalog_vocab(internal),
                                                  set(ranking["verb_methods"]), set(ranking["product_hints"]), act.alias_source_words(aliases), rule_sets, token_sources)


def _union(paths):
    return union_docs([_read(p) for p in paths])


def cmd_prepare(args):
    _, _, _, _, _, ctx = _context(args)
    kept, rejected = prepare_review(_union(args.raw), *ctx)
    act._write(args.out, {"round": args.round, "lexicon": kept, "rejected": rejected})
    print(f"structural: {len(kept)} kept, {len(rejected)} rejected")
    return 0


def cmd_finalize(args):
    internal, fp, shas, ranking, aliases, ctx = _context(args)
    raw, structural, review = _union(args.raw), _read(args.structural), _union(args.review)
    kept, rejected = prepare_review(raw, *ctx)
    if kept != structural["lexicon"]:
        print("REFUSED: structural file does not match prepare_review(raw) on the current catalog"); return 1
    problems = validate_review(review, list(kept), rejected)
    if problems:
        print("\n".join(f"INVALID REVIEW {m}" for m in problems)); return 1
    lexicon, rejected = finalize(kept, rejected, review)
    df = act.catalog_df(internal)
    for syn, e in rejected.items():
        e["catalog_df"] = df.get(syn, 0)
    doc = {"round": args.round, "prompt_template_sha256": _sha(args.template[0]), "generation_input_sha256": _sha(args.generation_input[0]),
           "raw_sha256": canonical_sha256(raw), "review_input_sha256": _sha(args.review_input[0]), "review_output_sha256": canonical_sha256(review),
           "components": {"raw": [_sha(p) for p in args.raw], "review": [_sha(p) for p in args.review],                       # file-byte shas (ledger kind)
                          "templates": [_sha(t) for t in args.template], "generation_inputs": [_sha(g) for g in args.generation_input],
                          "review_inputs": [_sha(r) for r in args.review_input],
                          **({"doc_titles_snapshot_sha256": _sha(args.doc_titles)} if getattr(args, "doc_titles", None) else {})},   # Round 4 spec §9
           "generated_from": act.provenance(fp, shas, {"verb_inventory": canonical_sha256(ranking["verb_methods"]),
                                                        "aliases": canonical_sha256(aliases), "raw_generation": canonical_sha256(raw),
                                                        "semantic_review": canonical_sha256(review)}),
           "lexicon": lexicon, "rejected": rejected, "catalog_df": {s: df.get(s, 0) for s in lexicon}}
    act._write(args.out, doc)
    print(f"lexicon: {len(lexicon)} kept, {len(rejected)} rejected")
    return 0


def cmd_render_generation_input(args):
    internal, _, _, ranking, _, _ = _context(args)
    snap = _read(args.doc_titles) if args.doc_titles else None
    text = render_lexicon_generation_input(pathlib.Path(args.template).read_text(encoding="utf-8"), internal, ranking, doc_snapshot=snap)
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(text, encoding="utf-8")
    info = {"rendered_sha256": _sha(args.out), "template_sha256": _sha(args.template), "concepts": len(act.concept_tokens(internal, ranking["path_noise"]))}
    if snap is not None:
        from tests.benchmarks import doc_titles as dt
        info["doc_titles_snapshot_sha256"] = _sha(args.doc_titles)
        if args.attachment_out:
            pathlib.Path(args.attachment_out).write_text(dt.attachment_text(snap), encoding="utf-8")
            info["doc_titles_attachment_sha256"] = _sha(args.attachment_out)
    print(json.dumps(info))
    return 0


def cmd_merge(args):
    aliases, doc = _read(args.aliases), _read(args.lexicon)
    out, skipped = merge(aliases, doc["lexicon"], args.round)
    pathlib.Path(args.aliases).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from tools.atlassian_docs.intelligence import policy
    policy.load_aliases(pathlib.Path(args.aliases))          # must still load
    print(f"merged {len(out['aliases']) - len(aliases['aliases'])} aliases; skipped {skipped}")
    return 0


def cmd_resolve(args):
    internal, fp, shas, ranking, aliases, ctx = _context(args)
    sources, pair_maps, fresh_maps, comp = [], [], [], []
    for sid, raw_p, rev_p, rin_p in args.source:
        raw = _read(raw_p); sources.append({"id": sid, "raw": raw})
        pair_maps.append(review_pairs(pathlib.Path(rin_p).read_text(encoding="utf-8"), _read(rev_p)))
        comp.append({"id": sid, "rank": SOURCE_RANK[sid], "raw_sha256": _sha(raw_p), "review_sha256": _sha(rev_p), "review_input_sha256": _sha(rin_p)})
    for rev_p, rin_p in args.review_r5 or []:
        fresh_maps.append(review_pairs(pathlib.Path(rin_p).read_text(encoding="utf-8"), _read(rev_p)))
        comp.append({"id": "round5_review", "review_sha256": _sha(rev_p), "review_input_sha256": _sha(rin_p)})
    verdicts, conflicts = resolve_verdicts(pair_maps, fresh_maps)
    out = resolve_sources(sources, ctx, verdicts)
    if out["pending"]:
        d = pathlib.Path(args.pending_out); d.mkdir(parents=True, exist_ok=True)
        texts = render_pending_review(pathlib.Path(args.template).read_text(encoding="utf-8"), out["pending"])
        for i, t in enumerate(texts, 1):
            (d / f"review-input-{i}.txt").write_text(t, encoding="utf-8")
        print(json.dumps({"pending": len(out["pending"]), "conflicts": len(conflicts), "batches": len(texts)})); return 3
    doc = {"round": args.round, "components": {"union_resolution": "source-precedence", "sources": comp, "template_sha256": _sha(args.template),
                                               "review_conflicts": [list(map(list, c)) for c in conflicts]},
           "generated_from": act.provenance(fp, shas, {"verb_inventory": canonical_sha256(ranking["verb_methods"]), "aliases": canonical_sha256(aliases)}),
           "lexicon": out["lexicon"], "rejected": out["rejected"], "selected": out["selected"]}
    act._write(args.out, doc)
    print(f"lexicon: {len(out['lexicon'])} kept, {len(out['rejected'])} rejected"); return 0


def cmd_round4_reference(args):
    """Round 5 spec §8: the Round 4 first-wins resolution of the same inputs (archive first), for the counterexample baseline."""
    internal, fp, shas, ranking, aliases, ctx = _context(args)
    lexicon, rejected = build(union_docs([_read(p) for p in args.raw]), union_docs([_read(p) for p in args.review]), *ctx[:5],
                              rule_sets=ctx[5], token_sources=ctx[6])
    act._write(args.out, {"round": 4, "lexicon": lexicon, "rejected": rejected,
                          "components": {"union_resolution": "first-wins", "raw": [_sha(p) for p in args.raw], "review": [_sha(p) for p in args.review]}})
    print(f"round4 reference lexicon: {len(lexicon)} kept"); return 0


def carry_forward(lexicon_doc, prior_lexicon_doc, cands_doc, prior_cands_doc, prior_shas) -> tuple:
    """Round 5 spec v1.12 (thread 2 ruling A′): the frozen lexicon is a cumulative provenance snapshot — prior lexicon entries the
    current resolution does not define are carried with entry-level provenance (current values/provenance win on collision); prior
    candidates are kept only in the provenance-only `carried_candidates` field, never in the active `candidates` surface."""
    lex, cands = copy.deepcopy(lexicon_doc), copy.deepcopy(cands_doc)
    prior_lexicon_doc, prior_cands_doc = copy.deepcopy(prior_lexicon_doc), copy.deepcopy(prior_cands_doc)   # outputs never alias the prior files
    prior, prior_carried = prior_lexicon_doc.get("lexicon") or {}, prior_lexicon_doc.get("carried_selected") or {}
    carried = {w: t for w, t in sorted(prior.items()) if w not in lex["lexicon"]}
    lex["lexicon"] = {**carried, **lex["lexicon"]}
    lex["carried_selected"] = {w: prior_carried.get(w) or {"from_round": prior_lexicon_doc.get("round"), "targets": list(t),
                                                             **({"selected": prior_lexicon_doc["selected"][w]} if w in (prior_lexicon_doc.get("selected") or {}) else {})}
                               for w, t in carried.items()}
    lex["components"] = {**(lex.get("components") or {}), "carried_from": {"round": prior_lexicon_doc.get("round"), **prior_shas}}
    old = {**(prior_cands_doc.get("carried_candidates") or {}), **(prior_cands_doc.get("candidates") or {})}
    cands["carried_candidates"] = {w: c for w, c in sorted(old.items()) if w not in cands["candidates"]}
    return lex, cands


def cmd_carry(args):
    pl, pc = pathlib.Path(args.prior_lexicon), pathlib.Path(args.prior_candidates)
    lex, cands = carry_forward(_read(args.lexicon), _read(pl), _read(args.candidates), _read(pc),
                               {"concept_lexicon_sha256": _sha(pl), "alias_candidates_sha256": _sha(pc)})
    act._write(args.lexicon, lex); act._write(args.candidates, cands)
    print(f"carried {len(lex['carried_selected'])} lexicon entries, {len(cands['carried_candidates'])} provenance-only candidates"); return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
    p.add_argument("--raw", required=True, nargs="+"); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("finalize"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
    for name in ("raw", "review", "generation-input", "review-input", "template"):                 # v1.24: parallel lists, archive first
        p.add_argument(f"--{name}", required=True, nargs="+")
    for name in ("structural", "out"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--doc-titles", default=None); p.set_defaults(fn=cmd_finalize)
    p = sub.add_parser("render-generation-input"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=3)
    p.add_argument("--template", required=True); p.add_argument("--out", required=True)
    p.add_argument("--doc-titles", default=None); p.add_argument("--attachment-out", default=None); p.set_defaults(fn=cmd_render_generation_input)
    p = sub.add_parser("carry"); p.add_argument("--lexicon", required=True); p.add_argument("--candidates", required=True)
    p.add_argument("--prior-lexicon", required=True); p.add_argument("--prior-candidates", required=True); p.set_defaults(fn=cmd_carry)
    p = sub.add_parser("merge"); p.add_argument("--lexicon", required=True); p.add_argument("--aliases", required=True)
    p.add_argument("--round", type=int, default=2); p.set_defaults(fn=cmd_merge)
    p = sub.add_parser("resolve"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=5)
    p.add_argument("--source", nargs=4, action="append", required=True, metavar=("ID", "RAW", "REVIEW", "REVIEW_INPUT"))
    p.add_argument("--review-r5", nargs=2, action="append", metavar=("REVIEW", "REVIEW_INPUT"))
    p.add_argument("--template", required=True); p.add_argument("--pending-out", required=True); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_resolve)
    p = sub.add_parser("round4-reference"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=5)
    p.add_argument("--raw", nargs="+", required=True); p.add_argument("--review", nargs="+", required=True); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_round4_reference)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
