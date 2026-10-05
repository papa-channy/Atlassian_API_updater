"""Round N seal tooling (spec §5.4/§5.5): operation catalogs, machine checks, seal/unseal, freeze.

CLI (run from the repo root):
  python tests/benchmarks/round_seal.py catalog --round N --cache-dir DIR --out GEN.json --internal-out INTERNAL.json
  python tests/benchmarks/round_seal.py check  --round N --plain PLAIN.json --bench BENCH.json --internal-catalog INTERNAL.json
  python tests/benchmarks/round_seal.py seal   --round N --plain PLAIN.json --bench BENCH.json --cache-dir DIR [--needle-manifest M.json]
  python tests/benchmarks/round_seal.py unseal --round N --plain PLAIN.json --bench BENCH.json
  python tests/benchmarks/round_seal.py freeze --round N --cache-dir DIR [--reference-enc ENC]
  python tests/benchmarks/round_seal.py verify-freeze --round N --cache-dir DIR
  python tests/benchmarks/round_seal.py scan --manifest M.json --root R [--root R2 ...] [--allow PATH ...] [--expect-sha256 S]
  python tests/benchmarks/round_seal.py reference-check --round N --reference-enc ENC
Uses tools.atlassian_docs read-only (only to build catalogs from a cache snapshot)."""
import argparse, hashlib, json, os, pathlib, re, sys

if __package__ in (None, ""):  # executed as a script: make `tests.benchmarks` importable
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tests.benchmarks.evaluator import STOPWORDS, canonical_sha256, check_schema, is_sealed, unigram_set
from tests.benchmarks import evaluator as ev
from tools.atlassian_docs.intelligence.search import method_intent, tokenize_unigrams


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
HIDDEN_RULES_R3 = ("schema", "catalog", "words", "ascii", "actionable", "negative-method", "operationId", "summary/tags", "negative-phrase", "reuse",
                   "distribution", "negative-distribution")            # Round 3 spec §4: frozen order; record-level priority = first 10
RECORD_RULES, SECTION_RULES = HIDDEN_RULES_R3[:10], HIDDEN_RULES_R3[10:]
_ASCII_QUERY = re.compile(r"^[A-Za-z0-9 '\-]+$")


def _ascii_checks(rec) -> list:
    """Round 3 spec §4 rule `ascii` (v1.22): the scanner's normalization contract is a generation rule."""
    q = rec.get("query") or ""
    return [] if _ASCII_QUERY.fullmatch(q) else [f"{rec.get('id', '?')}: ascii: query must use ASCII letters, digits, spaces, apostrophes and hyphens only"]


NEGATIVE_SPLIT = (4, 4)
BENCH_PATH = pathlib.Path(__file__).resolve().parent / "search_queries.json"


def intent_of(query, verb_methods):
    return method_intent(tokenize_unigrams(query or ""), verb_methods)[1]       # None (no verb) | frozenset (maybe empty)


def record_actionable(rec, verb_methods) -> bool:
    return bool(intent_of(rec.get("query"), verb_methods))


def _methods(keys) -> set:
    return {k.split(":", 2)[1] for k in keys or [] if k.count(":") >= 2}


def _actionable_checks(rec, verb_methods) -> list:
    """Round 3 spec §4 rule `actionable` (held_out): a verb, a non-empty allowed-method intersection, an expected method inside it."""
    rid, allowed = rec.get("id", "?"), intent_of(rec.get("query"), verb_methods)
    if allowed is None:
        return [f"{rid}: actionable: no inventory verb in the query"]
    if not allowed:
        return [f"{rid}: actionable: recognized verbs have an empty allowed-method intersection"]
    exp = _methods(rec.get("expected_top1_any"))
    if not exp & allowed:
        return [f"{rid}: actionable: expected methods {sorted(exp)} outside intent {sorted(allowed)}"]
    return []


def _negative_method_checks(rec, verb_methods) -> list:
    """Round 3 spec §4 rule `negative-method` (actionable negatives only): methods(forbidden) ∩ intent ≠ ∅."""
    rid, allowed = rec.get("id", "?"), intent_of(rec.get("query"), verb_methods)
    if not allowed:
        return []
    forb = _methods(rec.get("forbidden_top1"))
    return [] if forb & allowed else [f"{rid}: negative-method: forbidden methods {sorted(forb)} outside intent {sorted(allowed)}"]


def negative_distribution(records, verb_methods) -> tuple:
    a = sum(record_actionable(r, verb_methods) for r in records if isinstance(r, dict))
    return a, len(records) - a


def _negative_distribution_checks(records, verb_methods) -> list:
    a, n = negative_distribution(records, verb_methods)
    return [] if (a, n) == NEGATIVE_SPLIT else [f"negative: negative-distribution: {a} actionable / {n} abstained (need {NEGATIVE_SPLIT[0]}/{NEGATIVE_SPLIT[1]})"]


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


def freeze_entry(round: int, cache_dir, reference_enc=None) -> dict:
    """Round 2 spec §4: the per-round freeze record (hashes completed in evaluator.round_freeze_hashes).
    Round 3 spec §9 adds the reference_set binding to the archived Round 2 ciphertext and the frozen generation rules."""
    _, _, fp, shas = load_catalogs_from_cache(cache_dir, round)
    raw = _read_json(RANKING_PATH)
    entry = {"round": round, "structure_sha256": canonical_sha256({k: raw[k] for k in ev.STRUCTURE_KEYS}),
             "verb_inventory_sha256": canonical_sha256(raw["verb_methods"]),
             "source_registry_fingerprint": fp, "source_spec_sha256": shas}
    entry.update(ev.round_freeze_hashes(round))
    if round >= 3:
        if reference_enc is None:
            raise SystemExit("round >= 3 freeze needs --reference-enc (the archived Round 2 ciphertext)")
        r2 = _read_json(BENCH_PATH)["round2_seal"]
        entry["reference_set"] = {"origin": "round2", "enc_sha256": ev.file_sha256(reference_enc),
                                  "held_out_sha256": r2["held_out_sha256"], "negative_sha256": r2["negative_sha256"]}
        entry["hidden_generation_rules"] = list(HIDDEN_RULES_R3)
        entry["hidden_set_origin"] = f"round{round}"
    return entry


def cmd_freeze(args):
    freeze = _read_json(ROUND_FREEZE)
    if not isinstance(freeze, list):
        freeze = [freeze]
    if any(e.get("round") == args.round for e in freeze):
        print(f"REFUSED: round_freeze.json already has a round {args.round} entry")
        return 1
    entry = freeze_entry(args.round, args.cache_dir, reference_enc=getattr(args, "reference_enc", None))
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


def machine_check(plain, bench, internal_catalog, round=1, verb_methods=None) -> list:
    """All machine-checkable §5.4 violations; each message starts with the record id (or section name)."""
    if round >= 3 and verb_methods is None:
        raise ValueError("round >= 3 machine check needs the frozen verb_methods")
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
            if round >= 3:
                out += _ascii_checks(rec)
            if round >= 3 and sect == "held_out":
                out += _actionable_checks(rec, verb_methods)
            if round >= 3 and sect == "negative":
                out += _negative_method_checks(rec, verb_methods)
            hidden.append(rec)
        if sect == "held_out":
            out += _distribution_checks([r for r in recs if isinstance(r, dict)])
    out += _reuse_checks(hidden, bench)
    if round >= 3 and isinstance(plain.get("negative"), list):
        out += _negative_distribution_checks(plain["negative"], verb_methods)
    return out


# ---------------------------------------------------------------- rule ids / replacement state machine (Round 3 spec §4)
_RULE_PATTERNS = ((": ascii:", "ascii"), (": actionable:", "actionable"), (": negative-method:", "negative-method"), ("negative-distribution:", "negative-distribution"),
                  ("held_out: source ", "distribution"), ("held_out: method ", "distribution"), ("held_out: product", "distribution"),
                  ("not in catalog", "catalog"), ("query has ", "words"), ("equals operationId", "operationId"),
                  ("copies consecutive tokens", "summary/tags"), ("negative query equals", "negative-phrase"), ("reuse of", "reuse"))


def rule_id(message: str) -> str:
    """Map a machine_check message to its frozen rule id; everything structural (schema, origin, id prefix, counts, list shape) is `schema`."""
    for needle, rule in _RULE_PATTERNS:
        if needle in message:
            return rule
    return "schema"


def record_rejections(violations) -> list:
    """Fixed-format lines, one per violating record, the rule chosen by RECORD_RULES priority (the controller never chooses)."""
    by_id = {}
    for m in violations:
        rule = rule_id(m)
        if rule in SECTION_RULES:
            continue
        rid = m.split(":", 1)[0]
        if rid not in by_id or RECORD_RULES.index(rule) < RECORD_RULES.index(by_id[rid]):
            by_id[rid] = rule
    return [f"record {rid} rejected: {rule}" for rid, rule in sorted(by_id.items())]


def section_rejections(violations) -> list:
    present = {rule_id(m) for m in violations}
    return [r for r in SECTION_RULES if r in present]


def section_request(section, plain) -> str:
    head = "distribution rejected" if section == "held_out" else "negative distribution rejected"
    return "\n".join([head] + [r["id"] for r in plain[section]])


def next_request(violations, plain, state) -> tuple:
    """Deterministic controller step (Round 3 spec §4): record-level lines first; then section rules in frozen order (held_out
    `distribution`, then `negative-distribution`, each followed by a full re-check). The negative section may be replaced exactly
    once; needing a second replacement makes the whole generation attempt invalid. state: {"negative_section_replacements": int}."""
    if not violations:
        return ("ok", None)
    lines = record_rejections(violations)
    if lines:
        return ("records", lines)
    for rule in section_rejections(violations):
        if rule == "distribution":
            return ("section", "held_out", section_request("held_out", plain))
        if state.get("negative_section_replacements", 0) >= 1:
            return ("invalid", "negative-distribution broken again after the single section replacement (spec §4): attempt invalid")
        return ("section", "negative", section_request("negative", plain))
    return ("ok", None)


def annotate_for_review(plain, verb_methods) -> dict:
    """Reviewer input (spec §4 v1.22): each record plus the machine's verdict so the reviewer judges verb USE, not the mapping."""
    out = {}
    for sect, _ in HIDDEN:
        rows = []
        for rec in plain.get(sect, []):
            verbs, allowed = method_intent(tokenize_unigrams(rec.get("query") or ""), verb_methods)
            rows.append({**rec, "machine": {"matched_verbs": list(verbs), "intent_methods": sorted(allowed) if allowed else [], "machine_actionable": bool(allowed)}})
        out[sect] = rows
    return out


_WORD = re.compile(r"[^a-z0-9]+")
_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")


def _unescape(text: str) -> str:
    """JSON escape sequences as they appear in files (backslash-n/t/r and \\uXXXX) become their characters before tokenizing."""
    text = _UESC.sub(lambda m: chr(int(m.group(1), 16)), text)
    return text.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")


def _ngram_sha256(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()         # spec §5: sha256 of the normalized string bytes


SCAN_SUFFIXES = (".txt", ".json", ".jsonl", ".md", ".log", ".py", ".yaml", ".yml", ".csv")


def _words(text: str) -> list:
    return [w for w in _WORD.split(_unescape(text).lower()) if w]


def needle_manifest(queries) -> list:
    """AC-18b scanner input (spec §5 v1.22): per query the word count and sha256 of the normalized n-gram — never the text."""
    return [{"words": len(_words(q)), "sha256": _ngram_sha256(" ".join(_words(q)))} for q in queries]


def scan_for_needles(roots, manifest, allow=()) -> list:
    """Files under `roots` (text suffixes only) whose normalized word stream contains any manifest n-gram, minus `allow`
    (each entry a file or a directory - a directory allows every file resolving inside it)."""
    by_n = {}
    allowed_files, allowed_dirs = set(), set()
    for p in allow:
        rp = pathlib.Path(p).resolve()
        (allowed_dirs if rp.is_dir() else allowed_files).add(rp)
    for e in manifest:
        by_n.setdefault(e["words"], set()).add(e["sha256"])
    hits = []
    for root in roots:
        for p in sorted(pathlib.Path(root).rglob("*")):
            if not p.is_file() or p.suffix not in SCAN_SUFFIXES or ".git" in p.parts:
                continue
            rp = p.resolve()
            if rp in allowed_files or any(rp.is_relative_to(d) for d in allowed_dirs):
                continue
            words = _words(p.read_text(encoding="utf-8", errors="ignore"))
            if any(_ngram_sha256(" ".join(words[i:i + n])) in shas for n, shas in by_n.items() for i in range(len(words) - n + 1)):
                hits.append(str(p))
    return hits


def verify_reference_ciphertext(enc_path, round=3) -> list:
    """AC-R3-06 checkpoint helper (B, before the D decryption, terminal D/F/X): archive ciphertext sha == freeze reference_set.enc_sha256."""
    want, got = ev.freeze_for(round)["reference_set"]["enc_sha256"], ev.file_sha256(enc_path)
    return [] if got == want else [f"reference ciphertext sha {got} != freeze reference_set.enc_sha256 {want}"]


def render_generation_input(template: str, generator_records, verb_methods) -> str:
    """The exact generator input: catalog TSV lines and the canonical VERB_METHODS JSON (sha == verb_inventory_sha256)."""
    if "<generator catalog lines>" not in template or "<verb methods json>" not in template:
        raise ValueError("generation template must contain <generator catalog lines> and <verb methods json>")
    lines = "\n".join(f"{r['key']}\t{r['source']}\t{r['method']}\t{r['summary']}\t{','.join(r['tags'] or [])}" for r in generator_records)
    block = json.dumps(verb_methods, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return template.replace("<generator catalog lines>", lines).replace("<verb methods json>", block)


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
    vm = _read_json(RANKING_PATH)["verb_methods"] if args.round >= 3 else None
    violations = machine_check(_read_json(args.plain), _read_json(args.bench), _read_json(args.internal_catalog), round=args.round, verb_methods=vm)
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
    if args.round >= 3 and (not args.needle_manifest or not pathlib.Path(args.needle_manifest).exists()):
        print("REFUSED: round >= 3 seal needs --needle-manifest")
        return 1
    try:                                                     # T < B mechanically: the round must be frozen first
        ev.freeze_for(args.round)
    except KeyError:
        print(f"REFUSED: round_freeze.json has no round {args.round} entry; freeze (commit T) before sealing")
        return 1
    problems = verify_freeze(args.round, args.cache_dir)
    if problems:
        for m in problems:
            print(f"MISMATCH {m}")
        print("REFUSED: the snapshot differs from round_freeze")
        return 1
    _, internal, fp, shas = load_catalogs_from_cache(args.cache_dir, args.round)
    vm = _read_json(RANKING_PATH)["verb_methods"] if args.round >= 3 else None
    violations = machine_check(plain, bench, internal, round=args.round, verb_methods=vm)
    if violations:
        _print_violations(violations)
        print("REFUSED: fix the violations before sealing")
        return 1
    held, negs = plain["held_out"], plain["negative"]
    needle_sha = None
    if args.round >= 3:
        want = needle_manifest([r["query"] for r in held + negs])
        if _read_json(args.needle_manifest) != want:
            print("REFUSED: needle manifest does not match the sealed queries")
            return 1
        needle_sha = ev.file_sha256(args.needle_manifest)
    bench["held_out"] = seal_metadata(held, args.round, "held_out")
    bench["negative"] = seal_metadata(negs, args.round, "negative")
    bench[key] = {"held_out_sha256": bench["held_out"]["sha256"], "negative_sha256": bench["negative"]["sha256"],
                  "held_out_distribution": bench["held_out"]["distribution"],
                  "negative_distribution": bench["negative"]["distribution"],
                  "registry_fingerprint": fp, "spec_sha256": shas,
                  "machine_check": "passed", "origins": section_origin(args.round)}
    if needle_sha is not None:
        bench[key]["needle_manifest_sha256"] = needle_sha
    _write_bench(args.bench, bench)
    print(f"sealed held_out sha256={bench['held_out']['sha256']}")
    print(f"sealed negative sha256={bench['negative']['sha256']}")
    print(f"registry_fingerprint: {fp}")
    if args.round >= 3:
        actionable, abstained = negative_distribution(plain["negative"], vm)
        print(f"negative_actionable_split: {actionable}/{abstained}")
    return 0


def cmd_scan(args):
    sha = ev.file_sha256(args.manifest)
    if args.expect_sha256 and sha != args.expect_sha256:
        print(json.dumps({"manifest_sha256": sha, "error": f"manifest sha != expected {args.expect_sha256}"})); return 2
    hits = scan_for_needles(args.root, _read_json(args.manifest), allow=args.allow or [])
    print(json.dumps({"manifest_sha256": sha, "unexpected_hits": hits}))
    return 1 if hits else 0


def cmd_reference_check(args):
    problems = verify_reference_ciphertext(args.reference_enc, args.round)
    for m in problems:
        print(f"MISMATCH {m}")
    print("reference ciphertext ok" if not problems else f"{len(problems)} mismatch(es)")
    return 1 if problems else 0


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
    p.add_argument("--cache-dir", required=True); p.add_argument("--needle-manifest", default=None); p.set_defaults(fn=cmd_seal)
    p = sub.add_parser("unseal"); _round(p); p.add_argument("--plain", required=True); p.add_argument("--bench", required=True)
    p.set_defaults(fn=cmd_unseal)
    p = sub.add_parser("freeze"); _round(p); p.add_argument("--cache-dir", required=True)
    p.add_argument("--reference-enc", default=None); p.set_defaults(fn=cmd_freeze)
    p = sub.add_parser("verify-freeze"); _round(p); p.add_argument("--cache-dir", required=True); p.set_defaults(fn=cmd_verify_freeze)
    p = sub.add_parser("scan"); p.add_argument("--manifest", required=True); p.add_argument("--root", action="append", required=True)
    p.add_argument("--allow", action="append", help="file or directory to exclude from the scan"); p.add_argument("--expect-sha256", default=None); p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("reference-check"); _round(p); p.add_argument("--reference-enc", required=True); p.set_defaults(fn=cmd_reference_check)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
