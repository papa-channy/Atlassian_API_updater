import json, os, pathlib, re, unittest
from tests.benchmarks.evaluator import evaluate
from tests.benchmarks import evaluator as ev

BENCH = pathlib.Path(__file__).resolve().parent / "search_queries.json"
HIDDEN_COUNTS = (("held_out", 16), ("negative", 8))


def demoted(b: dict, rnd: int) -> bool:
    """Round rnd's hidden sets were observed at its commit D and demoted into seed / regression_negative (Round 1 ->
    Round 2 pre-work). Then held_out/negative are empty although round{rnd}_seal exists."""
    return (sum(r["origin"] == f"held_out-r{rnd}" for r in b["seed"]) == 16
            and sum(r["origin"] == f"negative-r{rnd}" for r in b["regression_negative"]) == 8)


def demoted_rounds(b: dict) -> list:
    """Rounds >= 1 whose held_out records sit in seed (r0 origins are the original Phase 2.5 tuning records)."""
    return sorted({n for n in (int(r["origin"].rsplit("-r", 1)[1]) for r in b["seed"] if r["origin"].startswith("held_out-r")) if n >= 1})


class TestEvaluator(unittest.TestCase):
    def test_pass_fail_semantics(self):
        recs = [{"query": "a", "expected_top1_any": ["k1"], "forbidden_top1": []},
                {"query": "b", "expected_top1_any": [], "forbidden_top1": ["k1"]}]
        res = evaluate(recs, lambda q: ["k1"])
        self.assertEqual(res["passed"], 1); self.assertEqual(res["failed"][0]["query"], "b")
        self.assertEqual(evaluate(recs[:1], lambda q: [])["failed"][0]["top1"], None)

    def test_degenerate_record_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([{"query": "x", "expected_top1_any": [], "forbidden_top1": []}], lambda q: [])

    def test_frozen_file_has_no_degenerate_records(self):
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        for sect in ("seed", "regression_negative"):
            if ev.is_sealed(b[sect]):
                continue
            evaluate(b[sect], lambda q: [])   # must not raise


class TestSchemaAndSemantics(unittest.TestCase):
    def test_regression_negative_passes_when_top1_not_forbidden_or_empty(self):
        recs = [{"id": "rn-001", "query": "x", "expected_top1_any": [], "forbidden_top1": ["k1"],
                 "origin": "negative-r0", "failure_classes": [], "ambiguous": False}]
        self.assertEqual(ev.evaluate(recs, lambda q: ["k2"])["failed"], [])
        self.assertEqual(ev.evaluate(recs, lambda q: [])["failed"], [])
        self.assertEqual(len(ev.evaluate(recs, lambda q: ["k1"])["failed"]), 1)

    def test_schema_invariants(self):
        good = {"id": "s-001", "query": "a b", "expected_top1_any": ["k"], "forbidden_top1": [],
                "origin": "seed-r0", "failure_classes": ["R1"], "ambiguous": False}
        ev.check_schema("seed", [good])
        for bad in ({**good, "expected_top1_any": []}, {**good, "id": "x-1"}, {**good, "origin": "seed"},
                    {**good, "failure_classes": ["R9"]}, {**good, "ambiguous": "no"}):
            with self.assertRaises(ValueError):
                ev.check_schema("seed", [bad])
        neg = {**good, "id": "rn-001", "expected_top1_any": [], "forbidden_top1": ["k"], "origin": "negative-r0"}
        ev.check_schema("regression_negative", [neg])
        with self.assertRaises(ValueError):
            ev.check_schema("regression_negative", [{**neg, "expected_top1_any": ["k"]}])
        with self.assertRaises(ValueError):
            ev.check_schema("seed", [good, {**good}])   # duplicate id

    def test_bundled_file_schema_and_counts(self):
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        self.assertEqual(b["version"], 2)
        for sect in ("seed", "regression_negative", "held_out", "negative"):
            if not ev.is_sealed(b[sect]):
                ev.check_schema(sect, b[sect])
        k = len(demoted_rounds(b))                    # every demoted round adds 16 seed + 8 regression records
        self.assertEqual(len(b["seed"]), 23 + 16 * k); self.assertEqual(len(b["regression_negative"]), 6 + 8 * k)
        # Round 1 hidden sets were observed at commit D and demoted before Round 2 (s-024..s-039, rn-007..rn-014)
        self.assertEqual([r["id"] for r in b["seed"][23:39]], [f"s-{i:03d}" for i in range(24, 40)])
        self.assertEqual({r["origin"] for r in b["seed"][23:39]}, {"held_out-r1"})
        self.assertEqual([r["id"] for r in b["regression_negative"][6:14]], [f"rn-{i:03d}" for i in range(7, 15)])
        self.assertEqual({r["origin"] for r in b["regression_negative"][6:14]}, {"negative-r1"})
        # hidden sections belong to the current round: [] only before its commit B (no round{N}_seal) or once demoted
        rnd = ev.current_round()["round"]
        seal = b.get(f"round{rnd}_seal")
        for sect, count in HIDDEN_COUNTS:
            section = b[sect]
            if seal is None or demoted(b, rnd):
                self.assertEqual(section, [], f"{sect}: round {rnd} has no seal (or was demoted): must be []")
            elif ev.is_sealed(section):
                self.assertEqual((section["round"], section["count"]), (rnd, count), sect)
            else:
                self.assertEqual(len(section), count, sect)
                self.assertEqual({r["origin"] for r in section}, {f"{sect}-r{rnd}"}, sect)

    def test_no_query_reuse_across_sets(self):
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        seen_q, seen_t = set(), set()
        for sect in ("seed", "regression_negative", "held_out", "negative"):
            if ev.is_sealed(b[sect]):
                continue
            for r in b[sect]:
                self.assertNotIn(r["query"], seen_q); self.assertNotIn(ev.unigram_set(r["query"]), seen_t)
                seen_q.add(r["query"]); seen_t.add(ev.unigram_set(r["query"]))

    def test_canonical_sha256_and_unigrams(self):
        self.assertEqual(ev.canonical_sha256({"b": 1, "a": [1, 2]}), ev.canonical_sha256({"a": [1, 2], "b": 1}))
        self.assertEqual(ev.unigram_set("Get the issueIdOrKey"), frozenset({"get", "issue", "id", "key"}))

    def test_sealed_section_is_reported_not_evaluated(self):
        sealed = {"sealed": True, "round": 1, "count": 16, "sha256": "0" * 64, "distribution": {}}
        self.assertTrue(ev.is_sealed(sealed)); self.assertFalse(ev.is_sealed([]))
        self.assertEqual(ev.evaluate(sealed, lambda q: []), {"sealed": True, "count": 16})


RANKING = pathlib.Path(__file__).resolve().parents[2] / "tools" / "atlassian_docs" / "intelligence" / "data" / "search_ranking.json"
# The ranking-table structure hash frozen at the current round's commit T lives in a data file, so a new round
# re-freezes by editing round_freeze.json rather than test code (which is part of evaluation_code_sha256).
ROUND_FREEZE = pathlib.Path(__file__).resolve().parent / "round_freeze.json"
RANKING_STRUCTURE_SHA256 = ev.current_round()["structure_sha256"]
STRUCTURE_KEYS = ev.STRUCTURE_KEYS
ROUND2_HASH_KEYS = {"structure_sha256", "verb_inventory_sha256", "concept_lexicon_sha256", "lexicon_aliases_sha256",
                    "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256",
                    "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T"}


def ranking_structure_sha256(raw: dict) -> str:
    return ev.canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS})


class TestRankingTablesFrozen(unittest.TestCase):
    def test_structure_hash_matches_commit_t(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(ranking_structure_sha256(raw), RANKING_STRUCTURE_SHA256)

    def test_round_freeze_file_shape(self):
        f = ev.load_round_freeze()
        self.assertIsInstance(f, list); self.assertEqual([e["round"] for e in f], list(range(1, len(f) + 1)))
        self.assertEqual(set(f[0]), {"round", "commit_T", "structure_sha256"})
        for e in f[1:]:
            self.assertEqual(set(e), ROUND2_HASH_KEYS | {"round", "source_registry_fingerprint", "source_spec_sha256"})
            for k in ROUND2_HASH_KEYS | {"source_registry_fingerprint"}:
                self.assertRegex(e[k], r"^[0-9a-f]{64}$", k)
            self.assertEqual(set(e["source_spec_sha256"]), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(ev.current_round(), f[-1]); self.assertEqual(ev.freeze_for(1), f[0])

    def test_round2_freeze_hashes_match_files(self):
        e = ev.current_round()
        if e["round"] < 2:
            print("round 2 not frozen yet: hash equality checked after commit T"); return
        got = ev.round_freeze_hashes(e["round"])
        for k, v in got.items():
            self.assertEqual(e[k], v, k)
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(e["verb_inventory_sha256"], ev.canonical_sha256(raw["verb_methods"]))
        self.assertEqual(e["structure_sha256"], ranking_structure_sha256(raw))

    def test_constants_inside_grid(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(set(raw["constants"]), set(raw["tuning_grid"])); self.assertEqual(set(raw["baseline"]), set(raw["tuning_grid"]))
        for k, v in raw["constants"].items():
            self.assertIn(v, raw["tuning_grid"][k], k); self.assertIn(raw["baseline"][k], raw["tuning_grid"][k], k)


class TestSealIntegrity(unittest.TestCase):
    def setUp(self):
        self.b = json.loads(BENCH.read_text(encoding="utf-8"))

    def test_sealed_or_plain_matches_current_round_seal(self):
        """spec §10.2: the hidden sections are checked against round{N}_seal of the current round N."""
        rnd = ev.current_round()["round"]
        seal = self.b.get(f"round{rnd}_seal")
        for sect, expected_count in HIDDEN_COUNTS:
            section = self.b[sect]
            if ev.is_sealed(section):          # B..D
                self.assertIsNotNone(seal, f"sealed {sect} requires round{rnd}_seal")
                self.assertEqual(section["count"], expected_count); self.assertEqual(section["round"], rnd)
                self.assertRegex(section["sha256"], r"^[0-9a-f]{64}$"); self.assertEqual(section["sha256"], seal[f"{sect}_sha256"])
                self.assertEqual(section["distribution"], seal[f"{sect}_distribution"])
            elif section:                       # plaintext after commit D
                from tests.benchmarks import round_seal as rs
                self.assertIsNotNone(seal, f"plaintext hidden sets require round{rnd}_seal")
                self.assertEqual(len(section), expected_count)
                self.assertEqual(ev.canonical_sha256(section), seal[f"{sect}_sha256"])
                self.assertEqual(rs.distribution(section, sect), seal[f"{sect}_distribution"])
            else:                               # [] only before this round's commit B, or after demotion
                self.assertTrue(seal is None or demoted(self.b, rnd), f"{sect}: round{rnd}_seal exists but the section is empty")

    def test_hidden_plaintext_machine_rules(self):
        from tests.benchmarks import round_seal as rs
        if ev.is_sealed(self.b["held_out"]) or not self.b["held_out"]:
            print("hidden sets sealed or absent: machine rules checked at commit D"); return
        rnd = ev.current_round()["round"]
        cache = os.environ.get(f"ATLASSIAN_DOCS_ROUND{rnd}_CACHE")
        if not cache or not pathlib.Path(cache).exists():
            self.skipTest("snapshot not available for catalog rules")
        _, internal, _, _ = rs.load_catalogs_from_cache(pathlib.Path(cache), rnd)
        self.assertEqual(rs.machine_check({"held_out": self.b["held_out"], "negative": self.b["negative"]}, self.b, internal,
                                          round=rnd), [])


ALIASES = RANKING.parent / "search_aliases.json"
LEXICON = RANKING.parent / "concept_lexicon.json"
TUNING_LOG = pathlib.Path(__file__).resolve().parent / "search-tuning-round1.jsonl"
FINAL_R1 = pathlib.Path(__file__).resolve().parent / "round1-final.json"
NOTE_ORIGIN = re.compile(r"^(phase2\.5|round(\d+)|lexicon-r(\d+))$")
# The constants adopted by Round 1 (the single adopted line of search-tuning-round1.jsonl, itself sha-pinned in
# TestRound1Invariants). Pinned here so the Round 1 check never reads the live constants, which Round >= 2 may tune.
R1_ADOPTED_CONSTANTS = {"method_match_bonus": 2.0, "method_mismatch_penalty": 2.0, "path_unmatched_penalty": 1.0,
                        "path_unmatched_cap": 3, "product_hint_bonus": 3.0, "resource_match_bonus": 10.0}


class TestAliasNotesAndTuningLog(unittest.TestCase):
    def test_alias_notes_per_origin(self):
        """spec §8/§10.2, per origin: phase2.5 unchanged; round1 -> R4; round{N>=2} -> §7.2 (the full candidate /
        target / budget check for the current round is test_round2_aliases_within_frozen_candidates); lexicon-r{N} ->
        §7.0 form (aliases only, seed_query_id null, no failure classes, the frozen lexicon's own targets)."""
        raw = json.loads(ALIASES.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8"))
        rnd = ev.current_round()["round"]
        lex = json.loads(LEXICON.read_text(encoding="utf-8")) if LEXICON.exists() else None
        seed_ids = {r["id"]: r for r in b["seed"]}
        expected_keys = set(raw["aliases"]) | {f"rule:{i}" for i in range(len(raw["rules"]))}
        self.assertEqual(set(raw["notes"]), expected_keys)
        per_seed = {}
        for k, n in raw["notes"].items():
            m = NOTE_ORIGIN.match(n["origin"])
            self.assertIsNotNone(m, f"{k}: origin {n['origin']!r}")
            if m.group(2) is not None:                                       # round{N}
                r = int(m.group(2))
                self.assertEqual(n["origin"], f"round{r}", k); self.assertTrue(1 <= r <= rnd, k)
                self.assertIn(n["seed_query_id"], seed_ids, k)
                per_seed[(r, n["seed_query_id"])] = per_seed.get((r, n["seed_query_id"]), 0) + 1
                cls = "R4" if r == 1 else "R6"
                self.assertIn(cls, n["failure_classes"], k); self.assertIn(cls, seed_ids[n["seed_query_id"]]["failure_classes"], k)
                if r >= 2:
                    self.assertIsInstance(n.get("candidate_word"), str, k)
                    self.assertTrue(isinstance(n.get("evidence"), str) and n["evidence"], k)
            elif m.group(3) is not None:                                     # lexicon-r{N}
                r = int(m.group(3))
                self.assertEqual(n["origin"], f"lexicon-r{r}", k); self.assertTrue(2 <= r <= rnd, k)
                self.assertFalse(k.startswith("rule:"), f"{k}: lexicon entries are aliases only")
                self.assertIsNone(n["seed_query_id"], k); self.assertEqual(n["failure_classes"], [], k)
                self.assertTrue(isinstance(n.get("evidence"), str) and n["evidence"], k)
                if lex is not None and lex.get("round") == r:
                    self.assertEqual(raw["aliases"][k], lex["lexicon"].get(k), f"{k}: differs from concept_lexicon.json")
            else:                                                            # phase2.5
                self.assertIsNone(n["seed_query_id"], k)
        self.assertTrue(all(c <= 1 for c in per_seed.values()), per_seed)

    def test_tuning_log_adopted(self):
        """Round 1 log (frozen): judged against the Round 1 freeze and the pinned Round 1 constants, not the live file."""
        raw = json.loads(RANKING.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8"))
        r1_structure = ev.freeze_for(1)["structure_sha256"]
        lines = [json.loads(l) for l in TUNING_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        for l in lines:   # every logged run, adopted or not
            for k, v in l["selected"].items():
                self.assertIn(v, raw["tuning_grid"][k])
            self.assertEqual(l["registry_fingerprint"], b["round1_seal"]["registry_fingerprint"])
            if l["ranking_structure_sha256"] == r1_structure:
                self.assertEqual(l["baseline"], raw["baseline"])
            else:   # pre-T2 run (spec v1.4 §0.4): logged under the 5-key table; its recorded axes must be unchanged
                self.assertEqual(l["baseline"], {k: raw["baseline"][k] for k in l["baseline"]})
        adopted = [l for l in lines if l.get("adopted")]
        self.assertEqual(len(adopted), 1); self.assertEqual(adopted[0]["selected"], R1_ADOPTED_CONSTANTS)
        final = json.loads(FINAL_R1.read_text(encoding="utf-8"))
        self.assertEqual(final["ranking_structure_sha256"], r1_structure)
        if ev.canonical_sha256({k: raw[k] for k in ev.STRUCTURE_KEYS}) == r1_structure:   # still the Round 1 table
            self.assertEqual(ev.canonical_sha256({**raw, "constants": R1_ADOPTED_CONSTANTS}), final["ranking_sha256"])

    def test_every_round1_alias_has_one_false_to_true_transition(self):
        raw = json.loads(ALIASES.read_text(encoding="utf-8"))
        lines = [json.loads(l) for l in TUNING_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        changes = [l["alias_change"] for l in lines if l.get("alias_change")]
        for key, n in raw["notes"].items():
            if n["origin"] != "round1":
                continue
            mine = [c for c in changes if c["policy_key"] == key]
            self.assertEqual(len(mine), 1, key); self.assertEqual((mine[0]["before_pass"], mine[0]["after_pass"]), (False, True), key)
            self.assertEqual(mine[0]["seed_query_id"], n["seed_query_id"])


ROOT = pathlib.Path(__file__).resolve().parents[2]
EVAL_CODE_FILES = ("tests/benchmarks/evaluator.py", "tests/benchmarks/test_evaluator.py",
                   "tests/diag_search_queries.py", "tests/tune_search_ranking.py",
                   "tests/benchmarks/round_seal.py", "tests/benchmarks/alias_candidates_tool.py")


R1_FINAL_SHA256 = "b573ba0f8deeb826e4cdea88f83a45ae028871c836f02945c66af21d78d31090"      # pinned Step 3
R1_TUNING_LOG_SHA256 = "7988b81ef010e42e18128878619df402a81a15743a43b43e027b47426f2f018f"
R1_SEAL_SHA256 = "253869a09f0f588d0610ad00174c0b725651789ca95d1a84f146202c14b75b0c"
R1_READINESS_SECTION_SHA256 = "319d1d535562952f29053b5d3cc554139cab3483618257ef91c001149409fbee"
READINESS = ROOT / "docs" / "phase3-readiness.md"


def readiness_round1_section(text: str) -> str:
    start = text.index("## Search Quality Round 1 — decision record")
    end = text.index("### Round 2 pre-work", start)
    return text[start:end]


class TestRound1Invariants(unittest.TestCase):
    """AC-09: Round 1 artifacts never change after the pre-work merge 95b8de0."""
    def test_round1_artifacts_unchanged(self):
        self.assertEqual(ev.files_sha256(ROOT, ("tests/benchmarks/round1-final.json",)), R1_FINAL_SHA256)
        self.assertEqual(ev.files_sha256(ROOT, ("tests/benchmarks/search-tuning-round1.jsonl",)), R1_TUNING_LOG_SHA256)
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        self.assertEqual(ev.canonical_sha256(b["round1_seal"]), R1_SEAL_SHA256)
        section = readiness_round1_section(READINESS.read_text(encoding="utf-8"))
        self.assertEqual(ev.canonical_sha256(section), R1_READINESS_SECTION_SHA256)

    def test_schema_accepts_r5_r6(self):
        good = {"id": "s-001", "query": "a b", "expected_top1_any": ["k"], "forbidden_top1": [],
                "origin": "seed-r0", "failure_classes": ["R5", "R6"], "ambiguous": False}
        ev.check_schema("seed", [good])
        with self.assertRaises(ValueError):
            ev.check_schema("seed", [{**good, "failure_classes": ["R7"]}])


class TestEvaluationCodeSha256(unittest.TestCase):
    def test_evaluation_code_sha256_is_stable_and_path_sensitive(self):
        import hashlib, shutil, tempfile
        self.assertEqual(tuple(sorted(EVAL_CODE_FILES)), ev.EVALUATION_CODE_FILES)
        self.assertTrue(set(ev.EVALUATION_CODE_FILES) <= set(ev.TOOLING_FILES))
        if all((ROOT / p).exists() for p in ev.TOOLING_FILES):
            self.assertEqual(ev.tooling_code_sha256(ROOT), ev.files_sha256(ROOT, ev.TOOLING_FILES))
        else:
            print("tooling incomplete")
        if not all((ROOT / p).exists() for p in EVAL_CODE_FILES):
            print("evaluation code files incomplete: checked once alias_candidates_tool.py exists (Task 4)"); return
        h = ev.evaluation_code_sha256(ROOT)
        self.assertRegex(h, r"^[0-9a-f]{64}$"); self.assertEqual(h, ev.evaluation_code_sha256(ROOT))
        blob = b"".join(p.encode() + b"\0" + (ROOT / p).read_bytes() + b"\0" for p in sorted(EVAL_CODE_FILES))
        self.assertEqual(h, hashlib.sha256(blob).hexdigest())
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            for p in EVAL_CODE_FILES:
                (tmp / p).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / p, tmp / p)
            self.assertEqual(ev.evaluation_code_sha256(tmp), h)      # relative paths: root location is irrelevant
            target = tmp / EVAL_CODE_FILES[2]
            raw = bytearray(target.read_bytes()); raw[0] ^= 1; target.write_bytes(bytes(raw))
            self.assertNotEqual(ev.evaluation_code_sha256(tmp), h)


FIXTURES = ROOT / "tests" / "fixtures" / "openapi"
SPEC_R1 = ROOT / "docs" / "superpowers" / "specs" / "2026-09-30-search-quality-round1-design.md"
# spec §10.2: the verb table (verb_methods, spec-authored in §6) is outside this check. The remaining words of the
# Round 1 spec §6.2 tables (frozen at commit T, b3c2ba5, before the hidden sets were generated) that occur in neither
# a seed query nor a fixture operationId/path: "epic" (product hint) and "read" (the phase2.5 alias read -> get).
# Exact equality below: a new uncovered word fails, and so does a stale entry.
PROVENANCE_EXCEPTIONS = frozenset({"epic", "read"})
CANDIDATES_DOC = RANKING.parent / "alias_candidates.json"


class TestPolicyVocabularyProvenance(unittest.TestCase):
    """Word-provenance check only (spec §7/§10.2): every policy word (verb table excluded) comes from a seed query, a
    fixture operationId/path, a source name or a frozen concept-lexicon key; every alias/rule target comes from the
    catalog (fixtures), the frozen lexicon's targets or the frozen candidates' targets. It is NOT a seal proof — it
    cannot show that no hidden query influenced the policy."""

    @staticmethod
    def frozen_docs():
        lex = json.loads(LEXICON.read_text(encoding="utf-8")) if LEXICON.exists() else {"lexicon": {}}
        cands = json.loads(CANDIDATES_DOC.read_text(encoding="utf-8"))["candidates"] if CANDIDATES_DOC.exists() else {}
        return lex["lexicon"], cands

    def catalog_tokens(self):
        from tools.atlassian_docs import sources
        out = set()
        for name in sources.SOURCES:
            spec = json.loads((FIXTURES / f"{name}-openapi.json").read_text(encoding="utf-8"))
            for path, item in spec["paths"].items():
                out |= ev.unigram_set(path)
                for op in item.values():
                    if isinstance(op, dict) and isinstance(op.get("operationId"), str):
                        out |= ev.unigram_set(op["operationId"]); out.add(op["operationId"].lower())
        return out

    def allowed_words(self):
        from tools.atlassian_docs import sources
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        lexicon, _ = self.frozen_docs()
        out = set(sources.SOURCES) | self.catalog_tokens() | set(lexicon)
        for rec in b["seed"]:
            out |= ev.unigram_set(rec["query"])   # every seed record (r0 + demoted r1) is Round 2 tuning vocabulary
        return out

    def allowed_targets(self):
        lexicon, cands = self.frozen_docs()
        out = self.catalog_tokens()
        for targets in lexicon.values():
            out |= set(targets)
        for c in cands.values():
            out |= set(c["allowed_targets"])
        return out

    def policy_words_and_targets(self):
        rk = json.loads(RANKING.read_text(encoding="utf-8")); al = json.loads(ALIASES.read_text(encoding="utf-8"))
        words, targets = set(rk["product_hints"]) | set(rk["path_noise"]), set()
        for k, v in al["aliases"].items():
            words.add(k); targets |= set(v)
        for rule in al["rules"]:
            words |= set(rule["when_all"]); targets |= set(rule["add"])
        return words, targets

    def test_policy_vocabulary_provenance(self):
        words, targets = self.policy_words_and_targets()
        uncovered = (words - self.allowed_words()) | (targets - self.allowed_targets())
        self.assertEqual(uncovered, set(PROVENANCE_EXCEPTIONS), sorted(uncovered))
        spec_text = SPEC_R1.read_text(encoding="utf-8")
        for w in PROVENANCE_EXCEPTIONS:
            self.assertIn(f'"{w}"', spec_text, w)

    def test_round_n_entries_inside_candidates_x_targets(self):
        """round{N>=2} alias/rule: candidate_word is a frozen candidate and every target is one of its targets."""
        al = json.loads(ALIASES.read_text(encoding="utf-8"))
        _, cands = self.frozen_docs()
        for key, n in al["notes"].items():
            m = NOTE_ORIGIN.match(n["origin"])
            if not (m and m.group(2) and int(m.group(2)) >= 2):
                continue
            word = n["candidate_word"]
            self.assertIn(word, cands, key)
            added = al["rules"][int(key[5:])]["add"] if key.startswith("rule:") else al["aliases"][key]
            self.assertTrue(set(added) <= set(cands[word]["allowed_targets"]), key)


FINAL = pathlib.Path(__file__).resolve().parent / "round1-final.json"
REPORT_FIELDS = ("sets", "failures", "git_commit", "registry_fingerprint", "intelligence_fingerprint", "ranking_sha256",
                 "ranking_structure_sha256", "alias_sha256", "evaluation_code_sha256", "sealed_sha256", "spec_sha256", "run_at")


class TestFinalArtifact(unittest.TestCase):
    """spec §5.8 (b),(c) / AC-10, made round-independent. The artifact is checked for internal consistency with
    round1_seal only: sealed_sha256, registry_fingerprint, spec_sha256, 40-hex git_commit, 64-hex
    evaluation_code_sha256, and evaluated (not sealed) held_out/negative results with totals 16/8.
    Two commit-D-only checks were dropped: equality of evaluation_code_sha256 with the current tree (evaluation code
    changes after D, e.g. this file) and plaintext r1 sections in the bundled bench (demoted into seed /
    regression_negative before Round 2). `git_commit == C` and the C-record hash were compared at D against
    docs/phase3-readiness.md."""

    def test_final_artifact(self):
        found = sorted(FINAL.parent.glob("round1-final*.json"))
        if not FINAL.exists():
            self.assertEqual(found, [])
            print("round1-final.json absent: final artifact checked at commit D"); return
        self.assertEqual(found, [FINAL], "exactly one final artifact")
        art = json.loads(FINAL.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8"))
        seal = b["round1_seal"]
        for k in REPORT_FIELDS:
            self.assertIn(k, art)
        self.assertRegex(art["git_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(art["sealed_sha256"], {"held_out": seal["held_out_sha256"], "negative": seal["negative_sha256"]})
        self.assertEqual(art["registry_fingerprint"], seal["registry_fingerprint"])
        self.assertEqual(art["spec_sha256"], seal["spec_sha256"])
        self.assertRegex(art["evaluation_code_sha256"], r"^[0-9a-f]{64}$")
        for sect, total in (("held_out", 16), ("negative", 8)):
            res = art["sets"][sect]
            self.assertNotIn("sealed", res, sect)
            self.assertTrue({"passed", "failed", "total"} <= set(res), sect)
            self.assertEqual(res["total"], total, sect)


CANDIDATES = RANKING.parent / "alias_candidates.json"
TUNING_LOG_R2 = pathlib.Path(__file__).resolve().parent / "search-tuning-round2.jsonl"


class TestRound2AliasesAndLog(unittest.TestCase):
    def test_round2_aliases_within_frozen_candidates(self):
        rnd = ev.current_round()["round"]
        if rnd < 2 or not CANDIDATES.exists():
            print("alias_candidates.json absent: checked after commit T"); return
        from tests import tune_search_ranking as tune
        raw = json.loads(ALIASES.read_text(encoding="utf-8")); cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
        b = json.loads(BENCH.read_text(encoding="utf-8")); queries = {r["id"]: r["query"] for r in b["seed"]}
        self.assertEqual(tune.validate_alias_change(tune.strip_round_entries(raw, rnd), raw, cands, queries), [])
        seeds = {r["id"]: r for r in b["seed"]}
        for n in raw["notes"].values():
            if n["origin"] == f"round{rnd}":
                self.assertIn("R6", seeds[n["seed_query_id"]]["failure_classes"])

    def test_round2_tuning_log_one_way(self):
        if not TUNING_LOG_R2.exists():
            print("round 2 tuning log absent: checked after tuning"); return
        from tests import tune_search_ranking as tune
        lines = [json.loads(l) for l in TUNING_LOG_R2.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len({l["run_id"] for l in lines}), len(lines))
        for l in lines:
            self.assertEqual(l["round"], 2); self.assertEqual(l["events"], list(tune.EVENTS))
            self.assertRegex(l["baseline_sha256"], r"^[0-9a-f]{64}$"); self.assertRegex(l["result_sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(l["status"], ("pending", "adopted", "failed", "rejected")); self.assertEqual(l["adopted"], l["status"] == "adopted")
            self.assertEqual(l["run_log_sha256"], ev.canonical_sha256(tune.log_core(l)))
        self.assertEqual(len({l["baseline_sha256"] for l in lines}), 1)
        valid = [l for l in lines if not l["tuning_failed"]]
        self.assertLessEqual(len({l["result_sha256"] for l in valid}), 1)
        adopted = [l for l in lines if l["adopted"]]
        self.assertLessEqual(len(adopted), 1)
        if adopted:
            self.assertEqual(adopted[0], valid[0])
            raw = json.loads(RANKING.read_text(encoding="utf-8")); self.assertEqual(adopted[0]["constants_selected"], raw["constants"])
            self.assertEqual(tune._current_result_sha256(), adopted[0]["result_sha256"])     # files reproduce the adopted result


FINAL_R2 = pathlib.Path(__file__).resolve().parent / "round2-final.json"


class TestRound2FinalArtifact(unittest.TestCase):
    def test_round2_final_artifact(self):
        if not FINAL_R2.exists():
            print("round2-final.json absent: checked after commit D"); return
        art = json.loads(FINAL_R2.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8")); seal = b["round2_seal"]
        e = ev.freeze_for(2)
        self.assertEqual(art["round"], 2); self.assertRegex(art["git_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(art["sealed_sha256"], {"held_out": seal["held_out_sha256"], "negative": seal["negative_sha256"]})
        self.assertEqual(art["registry_fingerprint"], e["source_registry_fingerprint"]); self.assertEqual(art["spec_sha256"], e["source_spec_sha256"])
        self.assertEqual(art["alias_candidates_sha256"], e["alias_candidates_sha256"]); self.assertEqual(art["concept_lexicon_sha256"], e["concept_lexicon_sha256"])
        self.assertEqual(art["alias_sha256"], ev.canonical_sha256(json.loads(ALIASES.read_text(encoding="utf-8"))))
        self.assertEqual(art["evaluation_code_sha256"], e["evaluation_code_sha256_at_T"])
        self.assertEqual(set(art["held_out_top3"]), {"passed", "total"}); self.assertEqual(art["held_out_top3"]["total"], 16)
        for sect, total in (("held_out", 16), ("negative", 8)):
            self.assertEqual(art["sets"][sect]["total"], total)
