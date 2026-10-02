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


def structural_check(lex, concept_set, catalog_set, verbs, hints, alias_keys):
    kept, rej = {}, {}
    for syn, targets in lex.items():
        reason = ("shape" if not _SHAPE.fullmatch(syn) or len(syn) < 2 or syn in STOPWORDS
                  else "id_like" if not any(c.isalpha() for c in syn) or syn in act.ID_LIKE
                  else "function_word" if syn in act.FUNCTION_WORDS
                  else "verb" if syn in verbs else "product_hint" if syn in hints else "in_catalog" if syn in catalog_set
                  else "alias_conflict" if syn in alias_keys else "multi_target" if len(targets) != 1
                  else "target_not_concept" if targets[0] not in concept_set else None)
        if reason:
            rej[syn] = _rej(reason, targets)
        else:
            kept[syn] = list(targets)
    return kept, rej


def prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys):
    """Order (spec §7.0): normalize -> structural. No cap here: the semantic review sees every surviving synonym."""
    return structural_check(normalize_raw(raw), concept_set, catalog_set, verbs, hints, alias_keys)


def validate_review(review, keys) -> list:
    if not isinstance(review, dict):
        return ["review must be a JSON object keyed by synonym"]
    wanted = set(keys)
    out = [f"missing key {k!r}" for k in keys if k not in review] + [f"extra key {k!r}" for k in review if k not in wanted]
    out += [f"{k!r}: value must be true/false" for k, v in review.items() if k in wanted and not isinstance(v, bool)]
    return out


def apply_review(lex, review):
    problems = validate_review(review, list(lex))
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
        by_concept.setdefault(targets[0], []).append(syn)
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
    kept, r2 = apply_review(kept, review); rejected.update(r2)
    kept, r3 = cap_per_concept(kept); rejected.update(r3)
    return kept, dict(sorted(rejected.items()))


def build(raw, review, concept_set, catalog_set, verbs, hints, alias_keys, df=None):
    kept, rejected = prepare_review(raw, concept_set, catalog_set, verbs, hints, alias_keys)
    lexicon, rejected = finalize(kept, rejected, review)
    for syn, e in rejected.items():
        e["catalog_df"] = (df or {}).get(syn, 0)
    return lexicon, rejected


def merge(aliases_raw, lexicon, round):
    out, skipped = copy.deepcopy(aliases_raw), []
    for syn, targets in sorted(lexicon.items()):
        if syn in out["aliases"]:
            skipped.append(syn); continue
        out["aliases"][syn] = list(targets)
        out["notes"][syn] = {"origin": f"lexicon-r{round}", "seed_query_id": None, "failure_classes": [],
                             "evidence": f"concept lexicon r{round}"}
    return out, skipped


def _read(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _context(args):
    _, internal, fp, shas = rs.load_catalogs_from_cache(args.cache_dir, args.round)
    ranking, aliases = _read(act.DATA / "search_ranking.json"), _read(act.DATA / "search_aliases.json")
    return internal, fp, shas, ranking, aliases, (set(act.concept_tokens(internal, ranking["path_noise"])), act.catalog_vocab(internal),
                                                  set(ranking["verb_methods"]), set(ranking["product_hints"]), act.alias_source_words(aliases))


def cmd_prepare(args):
    _, _, _, _, _, ctx = _context(args)
    kept, rejected = prepare_review(_read(args.raw), *ctx)
    act._write(args.out, {"round": args.round, "lexicon": kept, "rejected": rejected})
    print(f"structural: {len(kept)} kept, {len(rejected)} rejected")
    return 0


def cmd_finalize(args):
    internal, fp, shas, ranking, aliases, ctx = _context(args)
    raw, structural, review = _read(args.raw), _read(args.structural), _read(args.review)
    kept, rejected = prepare_review(raw, *ctx)
    if kept != structural["lexicon"]:
        print("REFUSED: structural file does not match prepare_review(raw) on the current catalog"); return 1
    problems = validate_review(review, list(kept))
    if problems:
        print("\n".join(f"INVALID REVIEW {m}" for m in problems)); return 1
    lexicon, rejected = finalize(kept, rejected, review)
    df = act.catalog_df(internal)
    for syn, e in rejected.items():
        e["catalog_df"] = df.get(syn, 0)
    doc = {"round": args.round, "prompt_template_sha256": _sha(args.template), "generation_input_sha256": _sha(args.generation_input),
           "raw_sha256": canonical_sha256(raw), "review_input_sha256": _sha(args.review_input), "review_output_sha256": canonical_sha256(review),
           "generated_from": act.provenance(fp, shas, {"verb_inventory": canonical_sha256(ranking["verb_methods"]),
                                                        "aliases": canonical_sha256(aliases), "raw_generation": canonical_sha256(raw),
                                                        "semantic_review": canonical_sha256(review)}),
           "lexicon": lexicon, "rejected": rejected, "catalog_df": {s: df.get(s, 0) for s in lexicon}}
    act._write(args.out, doc)
    print(f"lexicon: {len(lexicon)} kept, {len(rejected)} rejected")
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
    p.add_argument("--raw", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("finalize"); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
    for name in ("raw", "structural", "review", "generation-input", "review-input", "template", "out"):
        p.add_argument(f"--{name}", required=True)
    p.set_defaults(fn=cmd_finalize)
    p = sub.add_parser("merge"); p.add_argument("--lexicon", required=True); p.add_argument("--aliases", required=True)
    p.add_argument("--round", type=int, default=2); p.set_defaults(fn=cmd_merge)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
