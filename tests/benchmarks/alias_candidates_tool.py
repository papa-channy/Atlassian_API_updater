"""Round 2 pre-T tooling (spec §5.1/§5.2/§7.1, extended by Round 3 spec §6/AC-R3-12): concept tokens, verb report,
method-safety, alias candidates, R5/R6 classification, lexicon-seed gate. Every --cache-dir command reads only the
source snapshot S.

  python tests/benchmarks/alias_candidates_tool.py concept-tokens     --cache-dir S --out concept_tokens.json
  python tests/benchmarks/alias_candidates_tool.py verb-report        --cache-dir S --out verb_report.json
  python tests/benchmarks/alias_candidates_tool.py method-safety      --cache-dir S --out method_safety.json
  python tests/benchmarks/alias_candidates_tool.py lexicon-gate       --cache-dir S --lexicon tools/.../concept_lexicon.json
  python tests/benchmarks/alias_candidates_tool.py candidates         --cache-dir S --out tools/.../alias_candidates.json
  python tests/benchmarks/alias_candidates_tool.py classify           --cache-dir S
  python tests/benchmarks/alias_candidates_tool.py verb-prefix-check
"""
import argparse, collections, json, pathlib, sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.benchmarks import evaluator as ev
from tests.benchmarks import round_seal as rs
from tests.benchmarks.evaluator import STOPWORDS, canonical_sha256
from tools.atlassian_docs.intelligence.search import method_intent, singular, tokenize_unigrams

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "tools" / "atlassian_docs" / "intelligence" / "data"
BENCH_PATH = ROOT / "tests" / "benchmarks" / "search_queries.json"
TOOL_VERSION = "round3.1"
FUNCTION_WORDS = frozenset("my me this that these those another every which what who now today please into onto brand own "
                           "current some any all one two few several inside up".split())
ID_LIKE = frozenset({"id", "ids", "key", "keys"})
TARGET_EXCLUDE = FUNCTION_WORDS | ID_LIKE | STOPWORDS


def norm_tokens(text) -> tuple:
    return tuple(dict.fromkeys(singular(t) for t in tokenize_unigrams(text)))


def path_literal_tokens(path) -> tuple:
    out = []
    for seg in (path or "").split("/"):
        if seg and not (seg.startswith("{") and seg.endswith("}")):
            out += [t for t in norm_tokens(seg) if not t.isdigit()]
    return tuple(dict.fromkeys(out))


def op_vocab(op) -> frozenset:
    path = op["key"].split(":", 2)[2]
    toks = set(norm_tokens(op.get("operation_id") or "")) | set(path_literal_tokens(path)) | set(norm_tokens(op.get("summary") or ""))
    for tag in op.get("tags") or []:
        toks |= set(norm_tokens(tag))
    return frozenset(toks)


def catalog_vocab(internal) -> frozenset:
    out = set()
    for op in internal:
        out |= op_vocab(op)
    return frozenset(out)


def catalog_df(internal) -> dict:
    df = collections.Counter()
    for op in internal:
        df.update(op_vocab(op))
    return dict(df)


def concept_tokens(internal, noise) -> dict:
    """Catalog concept tokens: literal path-segment unigrams (minus noise/digits) and tag unigrams, with counts/sources."""
    out = {}
    for op in internal:
        toks = set(path_literal_tokens(op["key"].split(":", 2)[2])) - set(noise)
        for tag in op.get("tags") or []:
            toks |= set(norm_tokens(tag))
        for t in toks:
            e = out.setdefault(t, {"count": 0, "sources": set()})
            e["count"] += 1; e["sources"].add(op["source"])
    return {t: {"count": e["count"], "sources": sorted(e["sources"])} for t, e in sorted(out.items())}


def verb_report(internal, verb_methods) -> dict:
    """Diagnostic only (spec §6): method distribution of ops whose operationId/summary contains the verb token."""
    rep = {}
    for verb, allowed in sorted(verb_methods.items()):
        methods = collections.Counter(op["method"] for op in internal
                                      if verb in norm_tokens(op.get("operation_id") or "") or verb in norm_tokens(op.get("summary") or ""))
        outside = sorted(set(methods) - set(allowed))
        rep[verb] = {"methods": dict(sorted(methods.items())), "outside": outside, "review": bool(outside)}
    return rep


def allowed_methods(query, verb_methods):
    """None when the query has no inventory verb; else the intersection (may be empty = intent 0). The production helper
    (search.method_intent) so the machine check, the evaluator's inputs and the scorer agree (Round 3 spec §4)."""
    return method_intent(tokenize_unigrams(query), verb_methods)[1]


def expected_methods(rec) -> frozenset:
    return frozenset(k.split(":")[1] for k in rec.get("expected_top1_any") or [])


def method_safety(bench, verb_methods) -> list:
    """spec §5.2.2: (a) no verb or empty intersection, or (b) some expected op method is allowed."""
    rows = []
    for rec in bench["seed"]:
        allowed, exp = allowed_methods(rec["query"], verb_methods), expected_methods(rec)
        ok = allowed is None or not allowed or bool(allowed & exp)
        rows.append({"id": rec["id"], "verbs": [t for t in tokenize_unigrams(rec["query"]) if t in verb_methods],
                     "allowed": sorted(allowed) if allowed is not None else None, "expected_methods": sorted(exp), "ok": ok})
    return rows


def resource_vocab(op) -> frozenset:
    """Round 3 spec §6: resource evidence of an operation = normalized tokens of its literal path segments (terminal segment
    included) and of its tags. summary / operationId words are NOT resource evidence."""
    toks = set(path_literal_tokens(op["key"].split(":", 2)[2]))
    for tag in op.get("tags") or []:
        toks |= set(norm_tokens(tag))
    return frozenset(toks)


def expected_vocab(rec, by_key, noise) -> frozenset:
    """Round 3 spec §6 target eligibility: tokens of the seed's expected ops' resource vocabulary minus function words, path
    noise, id-like tokens, stopwords and digits. Verb-inventory and product_hints membership are not exclusion reasons."""
    toks = set()
    for key in rec.get("expected_top1_any") or []:
        op = by_key.get(key)
        if op is not None:
            toks |= resource_vocab(op)
    drop = TARGET_EXCLUDE | set(noise)
    return frozenset(t for t in toks if t not in drop and not t.isdigit())


round2_verb_inventory, verb_prefix_violations = ev.round2_verb_inventory, ev.verb_prefix_violations      # defined in the stdlib-only evaluator (Task 1)


def alias_source_words(aliases_raw) -> frozenset:
    words = set(aliases_raw.get("aliases") or {})
    for rule in aliases_raw.get("rules") or []:
        words |= set(rule.get("when_all") or [])
    return frozenset(words)


def _identifiers(internal) -> frozenset:
    return frozenset((op.get("operation_id") or "").lower() for op in internal)


def candidates(bench, internal, ranking_raw, aliases_raw, round=2) -> dict:
    """spec §7.1: deterministic seed-derived candidate words with per-seed targets. Excludes exactly the tokens that
    classify() treats as known (id-like, path noise and digit tokens included), so a seed has a candidate word iff
    it is R6."""
    by_key = {op["key"]: op for op in internal}
    verbs, noise, hints = ranking_raw["verb_methods"], frozenset(ranking_raw["path_noise"]), ranking_raw["product_hints"]
    idents = _identifiers(internal)
    alias_words, df = alias_source_words(aliases_raw), catalog_df(internal)
    cands, reasons = {}, {}
    for rec in sorted(bench["seed"], key=lambda r: r["id"]):
        vocab = expected_vocab(rec, by_key, noise)
        for tok in norm_tokens(rec["query"]):
            reason = ("verb" if tok in verbs else "function_word" if tok in FUNCTION_WORDS or tok in STOPWORDS else "product_hint" if tok in hints
                      else "existing_alias" if tok in alias_words else "expected_vocab" if tok in vocab
                      else "identifier" if tok in idents else "id_like" if tok in ID_LIKE
                      else "path_noise" if tok in noise else "digit" if tok.isdigit() else None)
            if reason:
                reasons.setdefault(tok, reason); continue
            c = cands.setdefault(tok, {"seed_ids": [], "targets_by_seed": {}, "allowed_targets": [], "catalog_df": df.get(tok, 0)})
            c["seed_ids"].append(rec["id"]); c["targets_by_seed"][rec["id"]] = sorted(vocab)
    for c in cands.values():
        c["allowed_targets"] = sorted(set().union(*c["targets_by_seed"].values()))
    excluded = {t: r for t, r in sorted(reasons.items()) if t not in cands}
    return {"round": round, "candidates": dict(sorted(cands.items())), "excluded": excluded}


def classify(bench, internal, ranking_raw, aliases_raw) -> dict:
    """spec §0.2 (independent definitions): R5 = no inventory verb, or the allowed methods cover no expected op
    (∃ semantics); R6 = some query token is in none of expected-op vocab / verbs / existing alias words /
    product hints / function words (id-like, noise and digits are ignored)."""
    by_key = {op["key"]: op for op in internal}
    verbs, noise, hints = ranking_raw["verb_methods"], frozenset(ranking_raw["path_noise"]), ranking_raw["product_hints"]
    alias_words, idents, out = alias_source_words(aliases_raw), _identifiers(internal), {}
    for rec in bench["seed"]:
        allowed, classes = allowed_methods(rec["query"], verbs), []
        if allowed is None or not (allowed & expected_methods(rec)):
            classes.append("R5")
        known = (expected_vocab(rec, by_key, noise) | set(verbs) | alias_words | set(hints)
                 | FUNCTION_WORDS | STOPWORDS | ID_LIKE | noise | idents)
        if any(t not in known and not t.isdigit() for t in norm_tokens(rec["query"])):
            classes.append("R6")
        out[rec["id"]] = classes
    return out

def lexicon_gate(lexicon_doc, bench, by_key, ranking_raw, regression_check=None):
    """spec §5.2.3: a lexicon synonym that occurs in a seed query must target that seed's expected vocabulary.
    Round 3 spec §6 (v1.25): `regression_check(syn, targets, seeds) -> bool` (True = merging this entry alone flips one of those
    seeds' raw top-1 from pass to fail) rejects the entry as `seed-regression`; checked only after the vocabulary gate."""
    verbs, noise, hints = ranking_raw["verb_methods"], frozenset(ranking_raw["path_noise"]), ranking_raw["product_hints"]
    rejected_now = []
    for syn in sorted(lexicon_doc["lexicon"]):
        toks = syn.split(" ")                                                       # v1.24: a phrase is gated by seeds containing all its tokens
        seeds = [r for r in bench["seed"] if all(t in norm_tokens(r["query"]) for t in toks)]
        if not seeds:
            continue
        allowed = set().union(*(expected_vocab(r, by_key, noise) for r in seeds))
        reason = None
        if not set(lexicon_doc["lexicon"][syn]) & allowed:
            reason = "seed-incompatible"
        elif regression_check is not None and regression_check(syn, list(lexicon_doc["lexicon"][syn]), seeds):
            reason = "seed-regression"
        if reason:
            lexicon_doc["rejected"][syn] = {"reason": reason, "targets": lexicon_doc["lexicon"].pop(syn),
                                            "catalog_df": lexicon_doc.get("catalog_df", {}).get(syn, 0)}
            rejected_now.append(syn)
    return lexicon_doc, rejected_now


def seed_regression_checker(cache_dir, aliases_raw, round):
    """Production-scorer checker for lexicon_gate (spec §6 v1.25): returns (check, cleanup). check merges ONE lexicon entry into
    `aliases_raw` (the pre-merge aliases) and compares the raw top-1 of the given seeds before/after on the snapshot registry."""
    import json, tempfile
    from unittest import mock
    from tests.benchmarks import concept_lexicon_check as clc, regression_reference as rr
    from tools.atlassian_docs.intelligence import policy, search
    state, cleanup = rr._state_from_cache(pathlib.Path(cache_dir))
    rp = policy.load_ranking()

    def load(raw):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(raw, fh)
        return policy.load_aliases(pathlib.Path(fh.name))

    def top1_ok(rec, ap):
        with mock.patch.object(policy, "ranking", return_value=rp), mock.patch.object(policy, "aliases", return_value=ap):
            res = search.search_operations(state, rec["query"], limit=1).get("results", [])
        return bool(res) and res[0]["key"] in (rec.get("expected_top1_any") or [])

    base_ap = load(aliases_raw)

    def check(syn, targets, seeds):
        merged, _ = clc.merge(aliases_raw, {syn: targets}, round)
        ap = load(merged)
        return any(top1_ok(r, base_ap) and not top1_ok(r, ap) for r in seeds)
    return check, cleanup


def provenance(fp, shas, inputs) -> dict:
    return {"registry_fingerprint": fp, "spec_sha256": dict(sorted(shas.items())), "inputs": dict(sorted(inputs.items())),
            "tool_version": TOOL_VERSION}


def _read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _write(path, obj):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _load(args):
    _, internal, fp, shas = rs.load_catalogs_from_cache(args.cache_dir, args.round)
    ranking, aliases, bench = _read(DATA / "search_ranking.json"), _read(DATA / "search_aliases.json"), _read(args.bench)
    inputs = {"ranking": canonical_sha256(ranking), "aliases": canonical_sha256(aliases), "bench": canonical_sha256(bench),
              "verb_inventory": canonical_sha256(ranking["verb_methods"])}
    return internal, fp, shas, ranking, aliases, bench, inputs


def cmd_concept_tokens(args):
    internal, fp, shas, ranking, _, _, inputs = _load(args)
    _write(args.out, {"round": args.round, "generated_from": provenance(fp, shas, {"ranking": inputs["ranking"]}),
                      "tokens": concept_tokens(internal, ranking["path_noise"])})
    return 0


def cmd_verb_report(args):
    internal, fp, shas, ranking, _, _, inputs = _load(args)
    rep = verb_report(internal, ranking["verb_methods"])
    for verb, row in rep.items():
        if row["review"]:
            print(f"REVIEW {verb}: methods={row['methods']} outside={row['outside']}")
    if args.out:
        _write(args.out, {"round": args.round, "generated_from": provenance(fp, shas, inputs), "report": rep})
    return 0


def cmd_method_safety(args):
    internal, fp, shas, ranking, _, bench, inputs = _load(args)
    rows = method_safety(bench, ranking["verb_methods"])
    bad = [r for r in rows if not r["ok"]]
    for r in bad:
        print(f"VIOLATION {r['id']}: allowed={r['allowed']} expected={r['expected_methods']}")
    _write(args.out, {"round": args.round, "generated_from": provenance(fp, shas, inputs), "rows": rows, "violations": len(bad)})
    return 1 if bad else 0


def cmd_lexicon_gate(args):
    internal, _, _, ranking, aliases, bench, _ = _load(args)
    doc = _read(args.lexicon)
    check, cleanup = seed_regression_checker(args.cache_dir, aliases, args.round)        # aliases = pre-merge state at gate time
    try:
        doc, rejected = lexicon_gate(doc, bench, {op["key"]: op for op in internal}, ranking, regression_check=check)
    finally:
        cleanup()
    doc.setdefault("generated_from", {}).setdefault("inputs", {})["bench"] = canonical_sha256(bench)
    _write(args.lexicon, doc)
    print(f"gate rejected: {rejected}")
    return 0


def cmd_candidates(args):
    internal, fp, shas, ranking, aliases, bench, inputs = _load(args)
    doc = candidates(bench, internal, ranking, aliases, args.round)
    doc["generated_from"] = provenance(fp, shas, inputs)
    _write(args.out, doc)
    print(f"candidates: {len(doc['candidates'])}, excluded: {len(doc['excluded'])}")
    return 0


def cmd_classify(args):
    internal, _, _, ranking, aliases, bench, _ = _load(args)
    cls = classify(bench, internal, ranking, aliases)
    for rec in bench["seed"]:
        keep = [c for c in rec["failure_classes"] if c not in ("R5", "R6")]
        rec["failure_classes"] = keep + cls[rec["id"]]
    rs._write_bench(pathlib.Path(args.bench), bench)
    print(json.dumps({k: v for k, v in cls.items() if v}, sort_keys=True))
    return 0


def cmd_verb_prefix_check(args):
    live = _read(DATA / "search_ranking.json")["verb_methods"]
    problems = verb_prefix_violations(round2_verb_inventory(), live)
    for m in problems:
        print(f"VIOLATION {m}")
    print("prefix ok" if not problems else f"{len(problems)} violation(s)")
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, extra in (("concept-tokens", cmd_concept_tokens, ("out",)), ("verb-report", cmd_verb_report, ("out?",)),
                            ("method-safety", cmd_method_safety, ("out",)), ("lexicon-gate", cmd_lexicon_gate, ("lexicon",)),
                            ("candidates", cmd_candidates, ("out",)), ("classify", cmd_classify, ())):
        p = sub.add_parser(name); p.add_argument("--cache-dir", required=True); p.add_argument("--round", type=int, default=2)
        p.add_argument("--bench", default=str(BENCH_PATH))
        for e in extra:
            p.add_argument(f"--{e.rstrip('?')}", required=not e.endswith("?"))
        p.set_defaults(fn=fn)
    p = sub.add_parser("verb-prefix-check"); p.set_defaults(fn=cmd_verb_prefix_check)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
