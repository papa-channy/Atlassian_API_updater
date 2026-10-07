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


def normalize_raw(raw) -> dict:
    out = {}
    for syn, targets in (raw or {}).items():
        toks = act.norm_tokens(str(syn))
        key = " ".join(toks) if toks else str(syn).lower()
        vals = [t for target in (targets if isinstance(targets, list) else [targets]) for t in act.norm_tokens(str(target))]
        out.setdefault(key, set()).update(vals)
    return {k: sorted(v) for k, v in sorted(out.items())}


def is_phrase(key: str) -> bool:
    return " " in key


def structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets=frozenset()):
    """Single-word keys -> alias candidates (Round 2 rules). Two-token keys -> conditional-rule candidates (Round 3 spec §6 v1.24):
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
                      else "verb" if syn in verbs else "product_hint" if syn in hints else "in_catalog" if syn in catalog_set
                      else "alias_conflict" if syn in alias_keys else "multi_target" if len(targets) != 1
                      else "target_not_concept" if targets[0] not in concept_set else None)
        if reason:
            rej[syn] = _rej(reason, targets)
        else:
            kept[syn] = list(targets)
    return kept, rej


def prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets=frozenset()):
    """Order (spec §7.0): normalize -> structural. No cap here: the semantic review sees every surviving synonym."""
    return structural_check(normalize_raw(raw), concept_set, catalog_set, verbs, hints, alias_keys, rule_sets)


def union_docs(docs) -> dict:
    """Round 3 spec §5(b): several raw (or review) documents, first occurrence of a key wins (archive first)."""
    out = {}
    for d in docs:
        for k, v in (d or {}).items():
            out.setdefault(k, v)
    return out


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


def build(raw, review, concept_set, catalog_set, verbs, hints, alias_keys, df=None, rule_sets=frozenset()):
    kept, rejected = prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys, rule_sets)
    lexicon, rejected = finalize(kept, rejected, review)
    for syn, e in rejected.items():
        e["catalog_df"] = (df or {}).get(syn, 0)
    return lexicon, rejected


def merge(aliases_raw, lexicon, round):
    out, skipped = copy.deepcopy(aliases_raw), []
    for syn, targets in sorted(lexicon.items()):
        if is_phrase(syn):                                                             # Round 3 spec §6 (v1.24): phrase -> when_all rule
            when_all = sorted(syn.split(" "))
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


def render_lexicon_generation_input(template: str, internal, ranking_raw) -> str:
    """Round 3 spec §5(b): every concept token with count/products and a grounding excerpt (first sentence of the description of
    the lexicographically smallest op whose terminal literal segment is that token; '-' when none), plus the verb keys."""
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
    return internal, fp, shas, ranking, aliases, (set(act.concept_tokens(internal, ranking["path_noise"])), act.catalog_vocab(internal),
                                                  set(ranking["verb_methods"]), set(ranking["product_hints"]), act.alias_source_words(aliases), rule_sets)


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
           "components": {"raw": [canonical_sha256(_read(p)) for p in args.raw], "review": [canonical_sha256(_read(p)) for p in args.review],
                          "templates": [_sha(t) for t in args.template], "generation_inputs": [_sha(g) for g in args.generation_input],
                          "review_inputs": [_sha(r) for r in args.review_input]},
           "generated_from": act.provenance(fp, shas, {"verb_inventory": canonical_sha256(ranking["verb_methods"]),
                                                        "aliases": canonical_sha256(aliases), "raw_generation": canonical_sha256(raw),
                                                        "semantic_review": canonical_sha256(review)}),
           "lexicon": lexicon, "rejected": rejected, "catalog_df": {s: df.get(s, 0) for s in lexicon}}
    act._write(args.out, doc)
    print(f"lexicon: {len(lexicon)} kept, {len(rejected)} rejected")
    return 0


def cmd_render_generation_input(args):
    internal, _, _, ranking, _, _ = _context(args)
    text = render_lexicon_generation_input(pathlib.Path(args.template).read_text(encoding="utf-8"), internal, ranking)
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps({"rendered_sha256": _sha(args.out), "template_sha256": _sha(args.template), "concepts": len(act.concept_tokens(internal, ranking["path_noise"]))}))
    return 0


def cmd_merge(args):
    aliases, doc = _read(args.aliases), _read(args.lexicon)
    out, skipped = merge(aliases, doc["lexicon"], args.round)
    pathlib.Path(args.aliases).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from tools.atlassian_docs.intelligence import policy
    policy.load_aliases(pathlib.Path(args.aliases))          # must still load
    print(f"merged {len(out['aliases']) - len(aliases['aliases'])} aliases; skipped {skipped}")
    return 0


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
    p.set_defaults(fn=cmd_finalize)
    p = sub.add_parser("render-generation-input"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=3)
    p.add_argument("--template", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_render_generation_input)
    p = sub.add_parser("merge"); p.add_argument("--lexicon", required=True); p.add_argument("--aliases", required=True)
    p.add_argument("--round", type=int, default=2); p.set_defaults(fn=cmd_merge)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
