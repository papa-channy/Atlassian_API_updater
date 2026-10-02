"""Shared benchmark evaluator (Round 1 spec §5.1): one record schema, sealed-section awareness.
Deliberately stdlib-only and independent of tools/ so its hash (evaluation_code_sha256) is meaningful."""
import hashlib, json, pathlib, re

STOPWORDS = frozenset("a an the to of for in on at and or with by from is are be this that".split())
_CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])"); _CAMEL_2 = re.compile(r"([A-Z]{2,})([A-Z][a-z])"); _SPLIT = re.compile(r"[^a-z0-9]+")
_ID = re.compile(r"^(s|rn|h|n)-\d{3}$"); _ORIGIN = re.compile(r"^(seed|held_out|negative)-r\d+$")
_CLASSES = {"R1", "R2", "R3", "R4", "R5", "R6"}
NEGATIVE_SECTIONS = ("regression_negative", "negative")


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


def evaluate(records, search_fn):
    if is_sealed(records):
        return {"sealed": True, "count": records.get("count")}
    failed = []
    for rec in records:
        expected = rec.get("expected_top1_any") or []
        forbidden = rec.get("forbidden_top1") or []
        if not expected and not forbidden:
            raise ValueError(f"benchmark record {rec.get('query')!r} must set expected_top1_any or forbidden_top1")
        ranked = search_fn(rec["query"])
        top1 = ranked[0] if ranked else None
        ok = (not expected or top1 in expected) and (top1 not in forbidden)
        if not ok:
            failed.append({"id": rec.get("id"), "query": rec["query"], "top1": top1,
                           "expected_top1_any": expected, "forbidden_top1": forbidden})
    return {"passed": len(records) - len(failed), "failed": failed, "total": len(records)}


IRREGULAR_SINGULAR = {"statuses": "status"}; UNCHANGED_PLURAL = frozenset({"series", "species", "news"})


def singular(t: str) -> str:
    if t in IRREGULAR_SINGULAR: return IRREGULAR_SINGULAR[t]
    if t in UNCHANGED_PLURAL or len(t) <= 3: return t
    if t.endswith("ies"): return t[:-3] + "y"
    if t.endswith(("sses", "shes", "ches", "xes")): return t[:-2]
    if t.endswith(("ss", "us", "is")): return t
    return t[:-1] if t.endswith("s") else t


STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid", "baseline")
ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUND_FREEZE = pathlib.Path(__file__).resolve().parent / "round_freeze.json"
DATA_REL = "tools/atlassian_docs/intelligence/data"


def load_round_freeze(path=ROUND_FREEZE) -> list:
    freeze = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(freeze, list) or not freeze:
        raise ValueError("round_freeze.json must be a non-empty list of round entries")
    return freeze


def current_round(freeze=None) -> dict:
    return (freeze if freeze is not None else load_round_freeze())[-1]


def freeze_for(round: int, freeze=None) -> dict:
    for e in freeze if freeze is not None else load_round_freeze():
        if e.get("round") == round:
            return e
    raise KeyError(f"round {round} is not in round_freeze.json")


def files_sha256(root, files) -> str:
    """sha256 over path + NUL + raw bytes + NUL for each file, sorted by relative path."""
    root, h = pathlib.Path(root), hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes() + b"\0")
    return h.hexdigest()


EVALUATION_CODE_FILES = tuple(sorted(("tests/benchmarks/evaluator.py", "tests/benchmarks/test_evaluator.py",
                                      "tests/diag_search_queries.py", "tests/tune_search_ranking.py",
                                      "tests/benchmarks/round_seal.py", "tests/benchmarks/alias_candidates_tool.py")))
TOOLING_FILES = tuple(sorted(EVALUATION_CODE_FILES + ("tests/benchmarks/concept_lexicon_check.py",
                                                      "tests/benchmarks/test_round_seal.py", "tests/test_tune_search_ranking.py",
                                                      "tests/test_diag_search_queries.py", "tests/intelligence/test_policy.py")))


def evaluation_code_sha256(root) -> str:
    return files_sha256(root, EVALUATION_CODE_FILES)


def tooling_code_sha256(root) -> str:
    return files_sha256(root, TOOLING_FILES)


def lexicon_aliases_sha256(raw_aliases: dict, round: int) -> str:
    """Canonical hash of the alias words whose notes.origin == lexicon-r{round} (aliases + notes subsets)."""
    origin = f"lexicon-r{round}"
    notes = raw_aliases.get("notes") or {}
    words = sorted(w for w, n in notes.items() if isinstance(n, dict) and n.get("origin") == origin and w in (raw_aliases.get("aliases") or {}))
    return canonical_sha256({"aliases": {w: raw_aliases["aliases"][w] for w in words}, "notes": {w: notes[w] for w in words}})


def round_freeze_hashes(round: int, root=ROOT) -> dict:
    root = pathlib.Path(root)
    j = lambda rel: canonical_sha256(json.loads((root / rel).read_text(encoding="utf-8")))
    aliases = json.loads((root / DATA_REL / "search_aliases.json").read_text(encoding="utf-8"))
    return {"concept_lexicon_sha256": j(f"{DATA_REL}/concept_lexicon.json"),
            "lexicon_aliases_sha256": lexicon_aliases_sha256(aliases, round),
            "alias_candidates_sha256": j(f"{DATA_REL}/alias_candidates.json"),
            "worker_brief_sha256": files_sha256(root, (f"tests/benchmarks/round{round}-worker-brief.md",)),
            "hidden_generation_prompt_sha256": files_sha256(root, (f"tests/benchmarks/round{round}-hidden-generation-prompt.md",)),
            "hidden_reviewer_prompt_sha256": files_sha256(root, (f"tests/benchmarks/round{round}-hidden-reviewer-prompt.md",)),
            "tooling_code_sha256": tooling_code_sha256(root),
            "evaluation_code_sha256_at_T": evaluation_code_sha256(root)}
