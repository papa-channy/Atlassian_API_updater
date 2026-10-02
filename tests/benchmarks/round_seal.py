"""Round N seal tooling (spec §5.4/§5.5): operation catalogs, machine checks, seal/unseal, freeze.

CLI (run from the repo root):
  python tests/benchmarks/round_seal.py catalog --round N --cache-dir DIR --out GEN.json --internal-out INTERNAL.json
  python tests/benchmarks/round_seal.py check  --round N --plain PLAIN.json --bench BENCH.json --internal-catalog INTERNAL.json
  python tests/benchmarks/round_seal.py seal   --round N --plain PLAIN.json --bench BENCH.json --cache-dir DIR
  python tests/benchmarks/round_seal.py unseal --round N --plain PLAIN.json --bench BENCH.json
  python tests/benchmarks/round_seal.py freeze --round N --cache-dir DIR
  python tests/benchmarks/round_seal.py verify-freeze --round N --cache-dir DIR
Uses tools.atlassian_docs read-only (only to build catalogs from a cache snapshot)."""
import argparse, json, os, pathlib, re, sys

if __package__ in (None, ""):  # executed as a script: make `tests.benchmarks` importable
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.benchmarks.evaluator import STOPWORDS, canonical_sha256, check_schema, is_sealed, unigram_set
from tests.benchmarks import evaluator as ev


def section_origin(round: int) -> dict:
    return {"held_out": f"held_out-r{round}", "negative": f"negative-r{round}"}


def seal_key(round: int) -> str:
    return f"round{round}_seal"


HIDDEN = (("held_out", 16), ("negative", 8))
SECTION_ID_PREFIX = {"held_out": "h-", "negative": "n-"}
GENERATOR_FIELDS = ("key", "source", "method", "summary", "tags")
MIN_SOURCE = {"jira-platform": 6, "jira-software": 4, "confluence": 5}
MIN_METHOD = {"GET": 4, "POST": 4, "PUT": 2, "DELETE": 2}
MIN_PRODUCT_NAMED, MIN_PRODUCT_UNNAMED = 4, 9
PRODUCT_WORDS = frozenset({"jira", "confluence"})
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------- catalogs
def _catalog_record(op) -> dict:
    return {"key": op.key, "source": op.source, "method": op.method, "operation_id": op.operation_id,
            "summary": op.summary, "tags": list(op.tags or ()), "description": op.description}


def generator_view(internal_records) -> list:
    """Generator catalog (spec §5.4 (a)): no operation_id, no description."""
    return [{f: r.get(f) for f in GENERATOR_FIELDS} for r in internal_records]


def load_catalogs_from_cache(cache_dir, round=1):
    """-> (generator_records, internal_records, registry_fingerprint, spec_sha256_by_source)."""
    from tools.atlassian_docs import sources, storage
    from tools.atlassian_docs.intelligence import normalizer, registry
    saved = storage.CACHE_DIR
    storage.CACHE_DIR = pathlib.Path(cache_dir)
    try:
        srcs = {}
        for name in sorted(sources.SOURCES):
            spec = storage.read_cache_spec(name)
            if spec is None:
                raise SystemExit(f"cache {cache_dir}: missing or unreadable {name}.json")
            srcs[name] = registry.build_source_registry(normalizer.normalize_openapi(name, spec),
                                                        storage.sha256_of_spec(spec))
    finally:
        storage.CACHE_DIR = saved
    reg = registry.build_registry(srcs, f"round{round}-snapshot")
    internal = sorted((_catalog_record(op) for sr in reg.sources.values() for op in sr.operations),
                      key=lambda r: r["key"])
    shas = {name: sr.spec_sha256 for name, sr in sorted(reg.sources.items())}
    return generator_view(internal), internal, reg.fingerprint, shas


# ---------------------------------------------------------------- distribution / metadata
def _anchor_key(rec, section_name):
    keys = rec.get("forbidden_top1" if section_name in ("negative", "regression_negative") else "expected_top1_any") or []
    return keys[0] if keys else None


def distribution(records, section_name) -> dict:
    """source/method of expected_top1_any[0] (held_out/seed) or forbidden_top1[0] (negative), parsed from the key."""
    src, meth, named = {}, {}, 0
    for rec in records:
        key = _anchor_key(rec, section_name)
        if key and key.count(":") >= 2:
            s, m, _ = key.split(":", 2)
            src[s] = src.get(s, 0) + 1
            meth[m] = meth.get(m, 0) + 1
        if unigram_set(rec.get("query", "")) & PRODUCT_WORDS:
            named += 1
    return {"source": dict(sorted(src.items())), "method": dict(sorted(meth.items())), "product_named": named}


def seal_metadata(records, round, section_name) -> dict:
    return {"sealed": True, "round": round, "count": len(records), "sha256": canonical_sha256(records),
            "distribution": distribution(records, section_name)}


def _content_tokens(text):
    return [t for t in _TOKEN_SPLIT.split((text or "").lower()) if len(t) >= 2 and t not in STOPWORDS]


def _bigrams(tokens):
    return set(zip(tokens, tokens[1:]))


# ---------------------------------------------------------------- machine checks (spec §5.4)
def _record_checks(section, rec, by_key, opid_sets):
    rid, q, out = rec.get("id", "?"), rec.get("query") or "", []
    try:
        check_schema(section, [rec])
    except ValueError as exc:
        out.append(f"{rid}: schema: {exc}")
    n = len(q.split())
    if not 3 <= n <= 7:
        out.append(f"{rid}: query has {n} words (must be 3-7)")
    qset = unigram_set(q)
    hits = sorted(oid for oid, s in opid_sets if s == qset)
    if hits:
        out.append(f"{rid}: query unigram set equals operationId {hits[0]!r}")
    exp, forb = rec.get("expected_top1_any") or [], rec.get("forbidden_top1") or []
    if section == "negative":
        if exp:
            out.append(f"{rid}: negative must have expected_top1_any == []")
        if not forb:
            out.append(f"{rid}: negative needs >= 1 forbidden_top1 key")
    qbi = _bigrams(_content_tokens(q))
    for key in exp:
        op = by_key.get(key)
        if op is None:
            continue
        for label, text in [("summary", op.get("summary"))] + [("tag", t) for t in op.get("tags") or []]:
            shared = qbi & _bigrams(_content_tokens(text))
            if shared:
                out.append(f"{rid}: copies consecutive tokens {' '.join(sorted(shared)[0])!r} "
                           f"from expected op {label} (summary/tags rule)")
    for key in exp + forb:
        if key not in by_key:
            out.append(f"{rid}: key {key!r} not in catalog")
    return out


def _reuse_checks(hidden, bench):
    out, prior = [], []
    for sect in ("seed", "regression_negative"):
        recs = bench.get(sect)
        if isinstance(recs, list):
            prior += [(r.get("id", "?"), r.get("query") or "") for r in recs]
    seen = list(prior)
    for rec in hidden:
        rid, q = rec.get("id", "?"), rec.get("query") or ""
        qn, qs = " ".join(q.lower().split()), unigram_set(q)
        for oid, oq in seen:
            if qn == " ".join(oq.lower().split()):
                out.append(f"{rid}: query string reuse of {oid}")
                break
            if qs == unigram_set(oq):
                out.append(f"{rid}: query unigram-set reuse of {oid}")
                break
        seen.append((rid, q))
    return out


def phrase_tokens(text) -> tuple:
    return tuple(ev.singular(t) for t in _TOKEN_SPLIT.split((text or "").lower()) if t and t not in STOPWORDS)


def _last_literal_segment(key) -> str:
    for seg in reversed(key.split(":", 2)[2].split("/")):
        if seg and not (seg.startswith("{") and seg.endswith("}")):
            return seg
    return ""


def _negative_phrase_checks(rec, internal_catalog):
    # Round 2 spec 5.3 machine rule: a negative query must not equal an op summary or last-path-segment phrase.
    q, out = phrase_tokens(rec.get("query") or ""), []
    for op in internal_catalog:
        if q == phrase_tokens(op.get("summary")):
            out.append(f"{rec.get('id', '?')}: negative query equals summary phrase of {op['key']}"); break
        if q == phrase_tokens(_last_literal_segment(op["key"])):
            out.append(f"{rec.get('id', '?')}: negative query equals path phrase of {op['key']}"); break
    return out


def validate_reviewer_output(obj, ids) -> list:
    # Hidden semantic reviewer output: exactly the record ids, each {"accept": bool, "reason": str}.
    if not isinstance(obj, dict):
        return ["reviewer output must be a JSON object keyed by record id"]
    wanted = set(ids)
    out = [f"missing id {i}" for i in ids if i not in obj] + [f"extra key {k!r}" for k in obj if k not in wanted]
    for k, v in obj.items():
        if k in wanted and (not isinstance(v, dict) or not isinstance(v.get("accept"), bool) or not isinstance(v.get("reason"), str)):
            out.append(f"{k}: value must be {{accept: bool, reason: str}}")
    return out


def validate_replacement_output(obj, expected_ids) -> list:
    """A replacement response must contain exactly the requested record ids (as a list of records) and nothing else."""
    if not isinstance(obj, list) or not all(isinstance(r, dict) for r in obj):
        return ["replacement output must be a JSON list of records"]
    got = [r.get("id") for r in obj]
    out = [f"missing replacement {i}" for i in expected_ids if i not in got] + [f"unexpected record {i!r}" for i in got if i not in set(expected_ids)]
    if len(set(got)) != len(got):
        out.append("duplicate ids in replacement output")
    return out


def merge_replacements(plain, replacements) -> dict:
    """Deterministic: replace records in place by id (section inferred from the id prefix); other records untouched."""
    by_id = {r["id"]: r for r in replacements}
    out = {sect: [by_id.get(r.get("id"), r) for r in plain.get(sect, [])] for sect, _ in HIDDEN}
    return out


def verify_coverage(manifest, plain, attempts) -> list:
    """Every final record must be covered by a valid review attempt whose input contained exactly this record
    (same canonical sha) and whose output accepted its id. Review attempts in the ledger carry
    reviewed_record_shas {id: sha} and accepted_ids [...] (both derived from the attempt's input/output files)."""
    by_no = {a["attempt_no"]: a for a in attempts if a.get("stage") == "review" and a.get("status") == "valid"}
    out = []
    for sect, _ in HIDDEN:
        for r in plain[sect]:
            m, sha = manifest.get(r["id"]), canonical_sha256(r)
            if m is None or m["record_sha256"] != sha:
                out.append(f"{r['id']}: manifest missing or stale"); continue
            a = by_no.get(m["accepted_review_attempt"])
            if a is None:
                out.append(f"{r['id']}: accepting review attempt {m['accepted_review_attempt']} is not a valid review attempt")
            elif a.get("reviewed_record_shas", {}).get(r["id"]) != sha:
                out.append(f"{r['id']}: review attempt {a['attempt_no']} did not review this exact record")
            elif r["id"] not in (a.get("accepted_ids") or []):
                out.append(f"{r['id']}: review attempt {a['attempt_no']} did not accept this id")
    return out


def coverage_manifest(plain, review_attempt_by_id) -> dict:
    """B-time evidence: every final record -> its canonical sha and the review attempt that accepted it."""
    return {r["id"]: {"record_sha256": canonical_sha256(r), "accepted_review_attempt": review_attempt_by_id[r["id"]]}
            for sect, _ in HIDDEN for r in plain[sect]}


def verify_freeze(round: int, cache_dir) -> list:
    # S integrity checkpoint (spec 5.7): the snapshot still matches the round_freeze source fields.
    _, _, fp, shas = load_catalogs_from_cache(cache_dir, round)
    entry, out = ev.freeze_for(round), []
    if fp != entry.get("source_registry_fingerprint"):
        out.append("registry fingerprint differs from round_freeze")
    want = entry.get("source_spec_sha256") or {}
    for name in sorted(set(shas) | set(want)):
        if shas.get(name) != want.get(name):
            out.append(f"spec_sha256[{name}] differs from round_freeze")
    return out


def cmd_verify_freeze(args):
    problems = verify_freeze(args.round, args.cache_dir)
    for m in problems:
        print(f"MISMATCH {m}")
    print("freeze ok" if not problems else f"{len(problems)} mismatch(es)")
    return 1 if problems else 0


ROUND_FREEZE = pathlib.Path(__file__).resolve().parent / "round_freeze.json"
RANKING_PATH = pathlib.Path(__file__).resolve().parents[2] / "tools" / "atlassian_docs" / "intelligence" / "data" / "search_ranking.json"


def freeze_entry(round: int, cache_dir) -> dict:
    """Round 2 spec §4: the per-round freeze record (hashes completed in evaluator.round_freeze_hashes)."""
    _, _, fp, shas = load_catalogs_from_cache(cache_dir, round)
    raw = _read_json(RANKING_PATH)
    entry = {"round": round, "structure_sha256": canonical_sha256({k: raw[k] for k in ev.STRUCTURE_KEYS}),
             "verb_inventory_sha256": canonical_sha256(raw["verb_methods"]),
             "source_registry_fingerprint": fp, "source_spec_sha256": shas}
    entry.update(ev.round_freeze_hashes(round))
    return entry


def cmd_freeze(args):
    freeze = _read_json(ROUND_FREEZE)
    if not isinstance(freeze, list):
        freeze = [freeze]
    if any(e.get("round") == args.round for e in freeze):
        print(f"REFUSED: round_freeze.json already has a round {args.round} entry")
        return 1
    entry = freeze_entry(args.round, args.cache_dir)
    _write_json(ROUND_FREEZE, freeze + [entry])
    for k, v in entry.items():
        print(f"{k}: {v}")
    return 0


def _distribution_checks(records):
    d, out = distribution(records, "held_out"), []
    for s, lo in MIN_SOURCE.items():
        if d["source"].get(s, 0) < lo:
            out.append(f"held_out: source {s}={d['source'].get(s, 0)} (need >= {lo})")
    for m, lo in MIN_METHOD.items():
        if d["method"].get(m, 0) < lo:
            out.append(f"held_out: method {m}={d['method'].get(m, 0)} (need >= {lo})")
    unnamed = len(records) - d["product_named"]
    if d["product_named"] < MIN_PRODUCT_NAMED:
        out.append(f"held_out: product_named={d['product_named']} (need >= {MIN_PRODUCT_NAMED})")
    if unnamed < MIN_PRODUCT_UNNAMED:
        out.append(f"held_out: product-unnamed={unnamed} (need >= {MIN_PRODUCT_UNNAMED}; product_named rule)")
    return out


def machine_check(plain, bench, internal_catalog, round=1) -> list:
    """All machine-checkable §5.4 violations; each message starts with the record id (or section name)."""
    by_key = {r["key"]: r for r in internal_catalog}
    opid_sets = [(r["operation_id"], unigram_set(r["operation_id"])) for r in internal_catalog if r.get("operation_id")]
    origins = section_origin(round)
    out, hidden, seen_ids = [], [], {}
    for sect, count in HIDDEN:
        recs = plain.get(sect)
        if not isinstance(recs, list):
            out.append(f"{sect}: must be a list of {count} records")
            continue
        if len(recs) != count:
            out.append(f"{sect}: expected {count} records, got {len(recs)}")
        for rec in recs:
            if not isinstance(rec, dict):
                out.append(f"{sect}: record must be an object")
                continue
            rid = rec.get("id", "?")
            if rid in seen_ids:
                out.append(f"{rid}: duplicate id in {sect} (already used in {seen_ids[rid]})")
            else:
                seen_ids[rid] = sect
            if not str(rid).startswith(SECTION_ID_PREFIX[sect]):
                out.append(f"{rid}: id in {sect} must start with {SECTION_ID_PREFIX[sect]!r}")
            if rec.get("origin") != origins[sect]:
                out.append(f"{rid}: origin {rec.get('origin')!r} in {sect} must be {origins[sect]!r}")
            out += _record_checks(sect, rec, by_key, opid_sets)
            if sect == "negative" and round >= 2:
                out += _negative_phrase_checks(rec, internal_catalog)
            hidden.append(rec)
        if sect == "held_out":
            out += _distribution_checks([r for r in recs if isinstance(r, dict)])
    out += _reuse_checks(hidden, bench)
    return out


# ---------------------------------------------------------------- file I/O
def _read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _write_json(path, obj):
    pathlib.Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fmt_value(v):
    if isinstance(v, list) and v:
        return "[\n" + ",\n".join("    " + json.dumps(r, ensure_ascii=False) for r in v) + "\n  ]"
    return json.dumps(v, ensure_ascii=False)


def _write_bench(path, bench):
    """Rewrite from the "held_out" key onward (one record per line); keep the hand-formatted prefix byte-for-byte."""
    path = pathlib.Path(path)
    text, keys = path.read_text(encoding="utf-8"), list(bench)
    marker = '\n  "held_out":'
    if marker in text and "held_out" in keys:
        prefix, tail_keys = text[:text.index(marker) + 1], keys[keys.index("held_out"):]  # prefix ends with ",\n"
    else:
        prefix, tail_keys = "{\n", keys
    new = prefix + ",\n".join(f"  {json.dumps(k)}: {_fmt_value(bench[k])}" for k in tail_keys) + "\n}\n"
    try:
        same = json.loads(new) == bench
    except ValueError:
        same = False
    if not same:  # prefix keys changed in memory, or unexpected layout: fall back to full rewrite
        new = "{\n" + ",\n".join(f"  {json.dumps(k)}: {_fmt_value(v)}" for k, v in bench.items()) + "\n}\n"
    if json.loads(new) != bench:
        raise RuntimeError(f"{path}: rewritten bench does not round-trip; refusing to write")
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- CLI commands
def _print_violations(violations):
    for v in violations:
        print(f"VIOLATION {v}")
    print(f"{len(violations)} violation(s)")


def cmd_catalog(args):
    gen, internal, fp, shas = load_catalogs_from_cache(args.cache_dir, args.round)
    _write_json(args.out, gen)
    pathlib.Path(args.internal_out).parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.internal_out, internal)
    print(f"operations: {len(internal)}")
    print(f"registry_fingerprint: {fp}")
    for name, sha in shas.items():
        print(f"spec_sha256[{name}]: {sha}")
    return 0


def cmd_check(args):
    violations = machine_check(_read_json(args.plain), _read_json(args.bench), _read_json(args.internal_catalog), round=args.round)
    _print_violations(violations)
    return 1 if violations else 0


def cmd_seal(args):
    plain, bench = _read_json(args.plain), _read_json(args.bench)
    if any(is_sealed(bench.get(s)) or bench.get(s) for s, _ in HIDDEN):
        print("REFUSED: bench held_out/negative are not empty (already sealed or plaintext)")
        return 1
    key = seal_key(args.round)
    if key in bench:
        print(f"REFUSED: bench already has a {key} key")
        return 1
    _, internal, fp, shas = load_catalogs_from_cache(args.cache_dir, args.round)
    violations = machine_check(plain, bench, internal, round=args.round)
    if violations:
        _print_violations(violations)
        print("REFUSED: fix the violations before sealing")
        return 1
    held, negs = plain["held_out"], plain["negative"]
    bench["held_out"] = seal_metadata(held, args.round, "held_out")
    bench["negative"] = seal_metadata(negs, args.round, "negative")
    bench[key] = {"held_out_sha256": bench["held_out"]["sha256"], "negative_sha256": bench["negative"]["sha256"],
                  "held_out_distribution": bench["held_out"]["distribution"],
                  "negative_distribution": bench["negative"]["distribution"],
                  "registry_fingerprint": fp, "spec_sha256": shas,
                  "machine_check": "passed", "origins": section_origin(args.round)}
    _write_bench(args.bench, bench)
    print(f"sealed held_out sha256={bench['held_out']['sha256']}")
    print(f"sealed negative sha256={bench['negative']['sha256']}")
    print(f"registry_fingerprint: {fp}")
    return 0


def cmd_unseal(args):
    plain, bench = _read_json(args.plain), _read_json(args.bench)
    key = seal_key(args.round)
    seal, errors = bench.get(key) or {}, []
    for sect, _ in HIDDEN:
        section, recs = bench.get(sect), plain.get(sect)
        if not is_sealed(section):
            errors.append(f"{sect}: bench section is not sealed")
            continue
        got = canonical_sha256(recs)
        if got != section.get("sha256") or got != seal.get(f"{sect}_sha256"):
            errors.append(f"{sect}: plaintext sha256 {got} does not match sealed {section.get('sha256')}")
    if errors:
        for e in errors:
            print(f"REFUSED {e}")
        return 1
    for sect, _ in HIDDEN:
        bench[sect] = plain[sect]
    _write_bench(args.bench, bench)
    print(f"unsealed held_out/negative ({key} kept)")
    return 0


def _round(p):
    p.add_argument("--round", type=int, default=1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("catalog"); _round(p); p.add_argument("--cache-dir", required=True)
    p.add_argument("--out", required=True); p.add_argument("--internal-out", required=True)
    p.set_defaults(fn=cmd_catalog)
    p = sub.add_parser("check"); _round(p); p.add_argument("--plain", required=True); p.add_argument("--bench", required=True)
    p.add_argument("--internal-catalog", required=True); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("seal"); _round(p); p.add_argument("--plain", required=True); p.add_argument("--bench", required=True)
    p.add_argument("--cache-dir", required=True); p.set_defaults(fn=cmd_seal)
    p = sub.add_parser("unseal"); _round(p); p.add_argument("--plain", required=True); p.add_argument("--bench", required=True)
    p.set_defaults(fn=cmd_unseal)
    p = sub.add_parser("freeze"); _round(p); p.add_argument("--cache-dir", required=True); p.set_defaults(fn=cmd_freeze)
    p = sub.add_parser("verify-freeze"); _round(p); p.add_argument("--cache-dir", required=True); p.set_defaults(fn=cmd_verify_freeze)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
