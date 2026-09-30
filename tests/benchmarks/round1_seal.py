"""Round 1 seal tooling (spec §5.4/§5.5): operation catalogs, machine checks, seal/unseal.

CLI (run from the repo root):
  python tests/benchmarks/round1_seal.py catalog --cache-dir DIR --out GEN.json --internal-out INTERNAL.json
  python tests/benchmarks/round1_seal.py check  --plain PLAIN.json --bench BENCH.json --internal-catalog INTERNAL.json
  python tests/benchmarks/round1_seal.py seal   --plain PLAIN.json --bench BENCH.json --cache-dir DIR
  python tests/benchmarks/round1_seal.py unseal --plain PLAIN.json --bench BENCH.json
Uses tools.atlassian_docs read-only (only to build catalogs from a cache snapshot)."""
import argparse, json, pathlib, re, sys

if __package__ in (None, ""):  # executed as a script: make `tests.benchmarks` importable
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.benchmarks.evaluator import STOPWORDS, canonical_sha256, check_schema, is_sealed, unigram_set

ROUND = 1
HIDDEN = (("held_out", 16), ("negative", 8))
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


def load_catalogs_from_cache(cache_dir):
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
    reg = registry.build_registry(srcs, "round1-snapshot")
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


def machine_check(plain, bench, internal_catalog) -> list:
    """All machine-checkable §5.4 violations; each message starts with the record id (or section name)."""
    by_key = {r["key"]: r for r in internal_catalog}
    opid_sets = [(r["operation_id"], unigram_set(r["operation_id"])) for r in internal_catalog if r.get("operation_id")]
    out, hidden = [], []
    for sect, count in HIDDEN:
        recs = plain.get(sect)
        if not isinstance(recs, list):
            out.append(f"{sect}: must be a list of {count} records")
            continue
        if len(recs) != count:
            out.append(f"{sect}: expected {count} records, got {len(recs)}")
        ids = [r.get("id") for r in recs if isinstance(r, dict)]
        for dup in sorted({i for i in ids if ids.count(i) > 1}, key=str):
            out.append(f"{dup}: duplicate id in {sect}")
        for rec in recs:
            if not isinstance(rec, dict):
                out.append(f"{sect}: record must be an object")
                continue
            out += _record_checks(sect, rec, by_key, opid_sets)
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
    assert json.loads(new) == bench
    path.write_text(new, encoding="utf-8")


# ---------------------------------------------------------------- CLI commands
def _print_violations(violations):
    for v in violations:
        print(f"VIOLATION {v}")
    print(f"{len(violations)} violation(s)")


def cmd_catalog(args):
    gen, internal, fp, shas = load_catalogs_from_cache(args.cache_dir)
    _write_json(args.out, gen)
    pathlib.Path(args.internal_out).parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.internal_out, internal)
    print(f"operations: {len(internal)}")
    print(f"registry_fingerprint: {fp}")
    for name, sha in shas.items():
        print(f"spec_sha256[{name}]: {sha}")
    return 0


def cmd_check(args):
    violations = machine_check(_read_json(args.plain), _read_json(args.bench), _read_json(args.internal_catalog))
    _print_violations(violations)
    return 1 if violations else 0


def cmd_seal(args):
    plain, bench = _read_json(args.plain), _read_json(args.bench)
    if any(is_sealed(bench.get(s)) or bench.get(s) for s, _ in HIDDEN):
        print("REFUSED: bench held_out/negative are not empty (already sealed or plaintext)")
        return 1
    _, internal, fp, shas = load_catalogs_from_cache(args.cache_dir)
    violations = machine_check(plain, bench, internal)
    if violations:
        _print_violations(violations)
        print("REFUSED: fix the violations before sealing")
        return 1
    held, negs = plain["held_out"], plain["negative"]
    bench["held_out"] = seal_metadata(held, ROUND, "held_out")
    bench["negative"] = seal_metadata(negs, ROUND, "negative")
    bench["round1_seal"] = {"held_out_sha256": bench["held_out"]["sha256"], "negative_sha256": bench["negative"]["sha256"],
                            "held_out_distribution": bench["held_out"]["distribution"],
                            "negative_distribution": bench["negative"]["distribution"],
                            "registry_fingerprint": fp, "spec_sha256": shas}
    _write_bench(args.bench, bench)
    print(f"sealed held_out sha256={bench['held_out']['sha256']}")
    print(f"sealed negative sha256={bench['negative']['sha256']}")
    print(f"registry_fingerprint: {fp}")
    return 0


def cmd_unseal(args):
    plain, bench = _read_json(args.plain), _read_json(args.bench)
    seal, errors = bench.get("round1_seal") or {}, []
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
    print("unsealed held_out/negative (round1_seal kept)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("catalog"); p.add_argument("--cache-dir", required=True)
    p.add_argument("--out", required=True); p.add_argument("--internal-out", required=True)
    p.set_defaults(fn=cmd_catalog)
    p = sub.add_parser("check"); p.add_argument("--plain", required=True); p.add_argument("--bench", required=True)
    p.add_argument("--internal-catalog", required=True); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("seal"); p.add_argument("--plain", required=True); p.add_argument("--bench", required=True)
    p.add_argument("--cache-dir", required=True); p.set_defaults(fn=cmd_seal)
    p = sub.add_parser("unseal"); p.add_argument("--plain", required=True); p.add_argument("--bench", required=True)
    p.set_defaults(fn=cmd_unseal)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
