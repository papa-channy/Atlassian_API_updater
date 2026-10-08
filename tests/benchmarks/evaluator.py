"""Shared benchmark evaluator (Round 1 spec §5.1): one record schema, sealed-section awareness.
Deliberately stdlib-only and independent of tools/ so its hash (evaluation_code_sha256) is meaningful."""
import hashlib, json, pathlib, re

STOPWORDS = frozenset("a an the to of for in on at and or with by from is are be this that".split())
_CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])"); _CAMEL_2 = re.compile(r"([A-Z]{2,})([A-Z][a-z])"); _SPLIT = re.compile(r"[^a-z0-9]+")
_ID = re.compile(r"^(s|rn|h|n)-\d{3}$"); _ORIGIN = re.compile(r"^(seed|held_out|negative)-r\d+$")
_CLASSES = {"R1", "R2", "R3", "R4", "R5", "R6"}
NEGATIVE_SECTIONS = ("regression_negative", "negative")
ACTIONABLE_SECTIONS = ("held_out",)          # Round 3 spec §4 v1.20: only held_out requires actionable; seed/fixture positive are raw top-1


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def unigram_set(query: str) -> frozenset:
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", query or "")).lower()
    return frozenset(t for t in _SPLIT.split(text) if len(t) >= 2 and t not in STOPWORDS)


def is_sealed(section) -> bool:
    return isinstance(section, dict) and section.get("sealed") is True


def check_schema(section_name: str, records) -> None:
    if not isinstance(records, list):
        raise ValueError(f"{section_name}: records must be a list")
    seen = set()
    for rec in records:
        if not isinstance(rec, dict):
            raise ValueError(f"{section_name}: record must be an object")
        rid = rec.get("id")
        if not isinstance(rid, str) or not _ID.match(rid) or rid in seen:
            raise ValueError(f"{section_name}: bad or duplicate id {rid!r}")
        seen.add(rid)
        if not isinstance(rec.get("query"), str) or not rec["query"].strip():
            raise ValueError(f"{section_name}/{rid}: query must be a non-empty string")
        exp, forb = rec.get("expected_top1_any"), rec.get("forbidden_top1")
        if not isinstance(exp, list) or not isinstance(forb, list) or not all(isinstance(k, str) for k in exp + forb):
            raise ValueError(f"{section_name}/{rid}: expected_top1_any/forbidden_top1 must be lists of keys")
        if section_name in NEGATIVE_SECTIONS:
            if exp or not forb:
                raise ValueError(f"{section_name}/{rid}: negative records need empty expected and non-empty forbidden")
        elif not exp:
            raise ValueError(f"{section_name}/{rid}: expected_top1_any must not be empty")
        if not isinstance(rec.get("origin"), str) or not _ORIGIN.match(rec["origin"]):
            raise ValueError(f"{section_name}/{rid}: bad origin {rec.get('origin')!r}")
        fc = rec.get("failure_classes")
        if not isinstance(fc, list) or not set(fc) <= _CLASSES or len(set(fc)) != len(fc):
            raise ValueError(f"{section_name}/{rid}: bad failure_classes {fc!r}")
        if not isinstance(rec.get("ambiguous"), bool):
            raise ValueError(f"{section_name}/{rid}: ambiguous must be a bool")


def ranked_and_actionable(search_fn, query):
    """Round 3 spec §4: search_fn returns (ranked_keys, actionable) or - the Round 1/2 call form - ranked_keys only, which the
    adapter reads as actionable=True (historical judgements never turn into abstentions)."""
    out = search_fn(query)
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], bool):
        return list(out[0]), out[1]
    return list(out), True


def evaluate(records, search_fn, section=None):
    """Symmetric judgement (Round 3 spec §4). held_out: top1 ∈ expected AND actionable. negatives: top1 ∉ forbidden OR abstained.
    Everything else (seed, fixtures, Round 1 callers with section=None): raw top-1 only."""
    if is_sealed(records):
        return {"sealed": True, "count": records.get("count")}
    failed, raw_passed, act_total, act_raw = [], 0, 0, 0
    for rec in records:
        expected = rec.get("expected_top1_any") or []
        forbidden = rec.get("forbidden_top1") or []
        if not expected and not forbidden:
            raise ValueError(f"benchmark record {rec.get('id')!r} must set expected_top1_any or forbidden_top1")
        ranked, actionable = ranked_and_actionable(search_fn, rec["query"])
        top1 = ranked[0] if ranked else None
        raw_ok = (not expected or top1 in expected) and (top1 not in forbidden)
        raw_passed += raw_ok
        if actionable:
            act_total += 1; act_raw += raw_ok
        if section in ACTIONABLE_SECTIONS:
            ok = raw_ok and actionable
        elif section in NEGATIVE_SECTIONS:
            ok = raw_ok or not actionable
        else:
            ok = raw_ok
        if not ok:
            f = {"id": rec.get("id"), "query": rec["query"], "top1": top1, "expected_top1_any": expected, "forbidden_top1": forbidden}
            if section is not None:
                f.update(actionable=actionable, raw_ok=raw_ok)
            failed.append(f)
    out = {"passed": len(records) - len(failed), "failed": failed, "total": len(records)}
    if section in ACTIONABLE_SECTIONS or section in NEGATIVE_SECTIONS:
        abstained = len(records) - act_total
        out.update(raw_passed=raw_passed, effective_passed=out["passed"], actionable={"total": act_total, "raw_passed": act_raw},
                   abstained={"total": abstained, "effective_passed": abstained if section in NEGATIVE_SECTIONS else 0})
    return out


IRREGULAR_SINGULAR = {"statuses": "status"}; UNCHANGED_PLURAL = frozenset({"series", "species", "news"})


def singular(t: str) -> str:
    if t in IRREGULAR_SINGULAR: return IRREGULAR_SINGULAR[t]
    if t in UNCHANGED_PLURAL or len(t) <= 3: return t
    if t.endswith("ies"): return t[:-3] + "y"
    if t.endswith(("sses", "shes", "ches", "xes")): return t[:-2]
    if t.endswith(("ss", "us", "is")): return t
    return t[:-1] if t.endswith("s") else t


STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid", "baseline", "ordering_rules")
ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUND_FREEZE = pathlib.Path(__file__).resolve().parent / "round_freeze.json"
DATA_REL = "tools/atlassian_docs/intelligence/data"


def load_round_freeze(path=ROUND_FREEZE) -> list:
    freeze = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(freeze, list) or not freeze:
        raise ValueError("round_freeze.json must be a non-empty list of round entries")
    return freeze


def current_round(freeze=None) -> dict:
    """The highest-numbered freeze entry (Round 4 spec §9.1: round_freeze.json may be non-contiguous, e.g. [1, 2, 4])."""
    return max(freeze if freeze is not None else load_round_freeze(), key=lambda e: e["round"])


def freeze_for(round: int, freeze=None) -> dict:
    for e in freeze if freeze is not None else load_round_freeze():
        if e.get("round") == round:
            return e
    raise KeyError(f"round {round} is not in round_freeze.json")


OUTCOMES = pathlib.Path(__file__).resolve().parent / "round_outcomes.json"
RECOVERIES = pathlib.Path(__file__).resolve().parent / "round_recoveries.json"
ROUND4_EXTRA_KEYS = ("doc_titles_source_bundle_sha256", "doc_titles_snapshot_sha256", "round_outcomes_sha256", "round_recoveries_sha256", "t_policy_files")
TERMINAL_OUTCOMES = ("pre-T not reached", "aborted-pre-B")


def load_round_outcomes(path=OUTCOMES) -> list:
    """Round 4 spec §9.1: rounds that ended before T (closed) or between T and B (aborted-pre-B); [] when the file is absent."""
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8")) if pathlib.Path(path).exists() else []


def load_round_recoveries(path=RECOVERIES) -> list:
    """Round 4 spec §9.5: append-only recovery attestations (X -> R -> A); [] when the file is absent."""
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8")) if pathlib.Path(path).exists() else []


def round_states(freeze, outcomes) -> dict:
    """spec §9.1: every round is exactly one of frozen (freeze entry only) | closed ('pre-T not reached' outcome only) |
    aborted-pre-B (freeze entry + X_preB outcome with a boolean invalidates_policy); any other combination is a load failure."""
    fr = {e["round"] for e in freeze}; by = {}
    for o in outcomes:
        if o["round"] in by or o.get("outcome") not in TERMINAL_OUTCOMES:
            raise ValueError(f"round_outcomes.json: bad or duplicate record for round {o['round']}")
        by[o["round"]] = o
    out = {}
    for r in sorted(fr | set(by)):
        o = by.get(r)
        if r in fr and o is not None:
            if o["outcome"] != "aborted-pre-B" or o.get("invalidated_by") != "X_preB" or not isinstance(o.get("invalidates_policy"), bool):
                raise ValueError(f"round {r}: freeze entry + outcome is only valid as aborted-pre-B/X_preB with invalidates_policy")
            out[r] = "aborted-pre-B"
        elif o is not None:
            if o["outcome"] != "pre-T not reached":
                raise ValueError(f"round {r}: outcome {o['outcome']!r} without a freeze entry (orphan abort)")
            out[r] = "closed"
        else:
            out[r] = "frozen"
    return out


def closed_rounds(outcomes) -> set:
    return {o["round"] for o in outcomes}


T_DATA_FILES = tuple(f"{DATA_REL}/{n}" for n in ("alias_candidates.json", "concept_lexicon.json", "search_aliases.json", "search_ranking.json"))
T_ALLOWLIST = T_DATA_FILES + ("tests/benchmarks/round_freeze.json", "tests/benchmarks/search_queries.json", "tests/benchmarks/round4-worker-brief.md",
                              "tests/benchmarks/round4-hidden-generation-prompt.md", "tests/benchmarks/round4-hidden-reviewer-prompt.md",
                              "tests/benchmarks/round4-lexicon-generation-prompt.md", "tests/benchmarks/round4-lexicon-review-prompt.md",
                              "tests/benchmarks/round4-method-safety.json")                  # Round 4 spec §9.6 (exact)


def changed_files_since(root, base_commit) -> list:
    """Tracked files that differ between base_commit and the working tree (what a T commit would contain)."""
    import subprocess
    out = subprocess.run(["git", "-C", str(root), "diff", "--name-only", base_commit, "--"], check=True, capture_output=True, text=True).stdout.split()
    untracked = subprocess.run(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"], check=True, capture_output=True, text=True).stdout.split()
    return sorted(set(out) | set(untracked))


def t_policy_files(root, base_commit) -> list:
    """Round 4 spec §9.6: the subset of the four policy data files that T actually changes (= RECOVERY_POLICY_FILES, spec §9.5)."""
    return sorted(p for p in changed_files_since(root, base_commit) if p in T_DATA_FILES)


ROUND3_EXTRA_KEYS = ("regression_reference_sha256", "reference_set", "hidden_generation_rules", "tuning_grid_sha256", "hidden_set_origin")
_ROUND2_KEYS = frozenset({"round", "structure_sha256", "verb_inventory_sha256", "source_registry_fingerprint", "source_spec_sha256",
                          "concept_lexicon_sha256", "lexicon_aliases_sha256", "alias_candidates_sha256", "worker_brief_sha256",
                          "hidden_generation_prompt_sha256", "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T"})


def freeze_key_set(round: int) -> set:
    """Canonical key set of a round_freeze.json entry (Round 3 spec §9): round 1 legacy; round 2 as frozen; round >= 3 adds
    ROUND3_EXTRA_KEYS. No entry after round 1 carries commit_T (self-reference)."""
    if round == 1:
        return {"round", "commit_T", "structure_sha256"}
    return set(_ROUND2_KEYS) | (set(ROUND3_EXTRA_KEYS) if round >= 3 else set()) | (set(ROUND4_EXTRA_KEYS) if round >= 4 else set())


def files_sha256(root, files) -> str:
    """sha256 over path + NUL + raw bytes + NUL for each file, sorted by relative path."""
    root, h = pathlib.Path(root), hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes() + b"\0")
    return h.hexdigest()


EVALUATION_CODE_FILES = tuple(sorted(("tests/benchmarks/evaluator.py", "tests/benchmarks/test_evaluator.py",
                                      "tests/diag_search_queries.py", "tests/tune_search_ranking.py",
                                      "tests/benchmarks/round_seal.py", "tests/benchmarks/alias_candidates_tool.py",
                                      "tests/benchmarks/regression_reference.py")))
TOOLING_FILES = tuple(sorted(EVALUATION_CODE_FILES + ("tests/benchmarks/concept_lexicon_check.py",
                                                      "tests/benchmarks/test_round_seal.py", "tests/test_tune_search_ranking.py",
                                                      "tests/test_diag_search_queries.py", "tests/intelligence/test_policy.py",
                                                      "tests/benchmarks/test_regression_reference.py",
                                                      "tests/benchmarks/round3_simulation.py", "tests/benchmarks/test_round3_simulation.py",
                                                      "tests/benchmarks/doc_titles.py", "tests/benchmarks/test_doc_titles.py",            # Round 4 (H14)
                                                      "tests/benchmarks/round4_simulation.py", "tests/benchmarks/test_round4_simulation.py")))   # Round 4 (H15)


def evaluation_code_sha256(root) -> str:
    return files_sha256(root, EVALUATION_CODE_FILES)


def tooling_code_sha256(root) -> str:
    return files_sha256(root, TOOLING_FILES)


def lexicon_aliases_sha256(raw_aliases: dict, round: int) -> str:
    """Canonical hash of the alias words whose notes.origin == lexicon-r{round} (aliases + notes subsets)."""
    origin = f"lexicon-r{round}"
    notes = raw_aliases.get("notes") or {}
    words = sorted(w for w, n in notes.items() if isinstance(n, dict) and n.get("origin") == origin and w in (raw_aliases.get("aliases") or {}))
    rules = raw_aliases.get("rules") or []
    rule_keys = sorted((k for k, n in notes.items() if isinstance(n, dict) and n.get("origin") == origin and k.startswith("rule:")
                        and k.split(":")[1].isdigit() and int(k.split(":")[1]) < len(rules)), key=lambda k: int(k.split(":")[1]))
    out = {"aliases": {w: raw_aliases["aliases"][w] for w in words}, "notes": {w: notes[w] for w in words}}
    if rule_keys:                                                                   # v1.24 phrase rules; Round 2 (no lexicon rules) hashes unchanged
        out["rules"] = {k: rules[int(k.split(":")[1])] for k in rule_keys}; out["rule_notes"] = {k: notes[k] for k in rule_keys}
    return canonical_sha256(out)


def file_sha256(path) -> str:
    """Plain sha256 of the file bytes - the value `shasum -a 256 FILE` prints."""
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def round_freeze_hashes(round: int, root=ROOT) -> dict:
    """The hashes of round_freeze.json computed from files (spec §4). JSON data files: canonical_sha256 of the parsed
    object; the worker brief and the two hidden prompts: plain sha256 of the file bytes (file_sha256, equal to
    `shasum -a 256`, so a controller can check the brief it forwards); tooling/evaluation code: files_sha256."""
    root = pathlib.Path(root)
    j = lambda rel: canonical_sha256(json.loads((root / rel).read_text(encoding="utf-8")))
    aliases = json.loads((root / DATA_REL / "search_aliases.json").read_text(encoding="utf-8"))
    out = {"concept_lexicon_sha256": j(f"{DATA_REL}/concept_lexicon.json"),
           "lexicon_aliases_sha256": lexicon_aliases_sha256(aliases, round),
           "alias_candidates_sha256": j(f"{DATA_REL}/alias_candidates.json"),
           "worker_brief_sha256": file_sha256(root / f"tests/benchmarks/round{round}-worker-brief.md"),
           "hidden_generation_prompt_sha256": file_sha256(root / f"tests/benchmarks/round{round}-hidden-generation-prompt.md"),
           "hidden_reviewer_prompt_sha256": file_sha256(root / f"tests/benchmarks/round{round}-hidden-reviewer-prompt.md"),
           "tooling_code_sha256": tooling_code_sha256(root),
           "evaluation_code_sha256_at_T": evaluation_code_sha256(root)}
    if round >= 3:
        # Round 4 ruling: the AC-R3-02 reference is the Round 2 isolated scorer and is round-independent (byte-invariant file).
        out["regression_reference_sha256"] = j("tests/benchmarks/round3-regression-reference.json")
        out["tuning_grid_sha256"] = tuning_grid_sha256(json.loads((root / DATA_REL / "search_ranking.json").read_text(encoding="utf-8")))
    if round >= 4:
        out["round_outcomes_sha256"] = file_sha256(root / "tests/benchmarks/round_outcomes.json")
        out["round_recoveries_sha256"] = file_sha256(root / "tests/benchmarks/round_recoveries.json")
    return out


PRE_FREEZE_NONVERB_STRUCTURE_SHA256 = {3: "1e99c67ec445163f777b0cdfb933ac6d0cac22d638c1994743028678a862c9f1",
                                       4: "1e99c67ec445163f777b0cdfb933ac6d0cac22d638c1994743028678a862c9f1"}   # Round 4 spec §3: structure unchanged
NONVERB_STRUCTURE_KEYS = tuple(k for k in STRUCTURE_KEYS if k != "verb_methods")
ROUND2_SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-10-02-search-quality-round2-design.md"


def tuning_grid_sha256(raw: dict) -> str:
    """spec AC-R3-13b: sha256(canonical_json(search_ranking.json["tuning_grid"])); freeze, tests and readiness share it."""
    return canonical_sha256(raw["tuning_grid"])


def nonverb_structure_sha256(raw: dict) -> str:
    return canonical_sha256({k: raw[k] for k in NONVERB_STRUCTURE_KEYS})


def pending_round(freeze=None, outcomes=None):
    """The round whose H structure/tooling is committed but whose freeze entry (commit T) does not exist yet, or None:
    the smallest PRE_FREEZE key above the current freeze round that is not a decided (closed / aborted) round (Round 4
    spec §9.1). While a round is pending, the previous round's freeze entry is history: its file hashes are no longer
    compared with the live tree (the tooling and the ranking structure legitimately changed at H)."""
    freeze = freeze if freeze is not None else load_round_freeze()
    outcomes = outcomes if outcomes is not None else load_round_outcomes()
    cur = current_round(freeze)["round"]; decided = set(round_states(freeze, outcomes))
    return next((r for r in sorted(PRE_FREEZE_NONVERB_STRUCTURE_SHA256) if r > cur and r not in decided), None)


def round2_verb_inventory() -> dict:
    """The frozen Round 2 inventory: the JSON block under '## 6.' of the Round 2 spec (verb_inventory_sha256 d66317db…)."""
    lines = ROUND2_SPEC.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("## 6."))
    fence = next(i for i in range(start, len(lines)) if lines[i].startswith("```json"))
    end = next(i for i in range(fence + 1, len(lines)) if lines[i].startswith("```"))
    return json.loads("{" + "\n".join(lines[fence + 1:end]) + "}")["verb_methods"]


def verb_prefix_violations(base: dict, live: dict) -> list:
    """AC-R3-12: same row set; each base list is an exact prefix of the live list; the appended suffix is sorted, no duplicates."""
    out = [f"verb {v!r} removed" for v in base if v not in live] + [f"verb {v!r} added" for v in live if v not in base]
    for v, methods in base.items():
        cur = list(live.get(v) or [])
        if not cur:
            continue
        if cur[:len(methods)] != list(methods):
            out.append(f"verb {v!r}: Round 2 list {list(methods)} is not an exact prefix of {cur}")
            continue
        suffix = cur[len(methods):]
        if suffix != sorted(suffix):
            out.append(f"verb {v!r}: suffix {suffix} is not sorted")
        if len(set(cur)) != len(cur):
            out.append(f"verb {v!r}: duplicate methods in {cur}")
    return out


def structure_check_problems(raw: dict, freeze=None) -> list:
    """spec §8 (v1.14). Pending round N (H committed, no T yet): the non-verb structure must equal PRE_FREEZE_NONVERB_STRUCTURE_SHA256[N]
    and verb_methods must satisfy the Round 2 prefix invariant (T may append sorted suffixes). Otherwise the full structure hash
    must equal the current round's freeze."""
    p = pending_round(freeze)
    if p is None:
        want, got = current_round(freeze)["structure_sha256"], canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS})
        return [] if got == want else [f"structure_sha256 {got} != current freeze {want}"]
    out = [] if nonverb_structure_sha256(raw) == PRE_FREEZE_NONVERB_STRUCTURE_SHA256[p] else ["non-verb ranking structure differs from the H1 constant"]
    return out + verb_prefix_violations(round2_verb_inventory(), raw["verb_methods"])
