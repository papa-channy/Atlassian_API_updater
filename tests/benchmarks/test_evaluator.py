import json, os, pathlib, re, unittest
from unittest import mock
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
STRUCTURE_KEYS = ev.STRUCTURE_KEYS
ROUND2_HASH_KEYS = {"structure_sha256", "verb_inventory_sha256", "concept_lexicon_sha256", "lexicon_aliases_sha256",
                    "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256",
                    "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T"}
SHA_KEYS_R3 = ROUND2_HASH_KEYS | {"regression_reference_sha256", "tuning_grid_sha256"}
SHA_KEYS_R4 = SHA_KEYS_R3 | {"doc_titles_source_bundle_sha256", "doc_titles_snapshot_sha256", "round_outcomes_sha256", "round_recoveries_sha256"}   # t_policy_files is a list


def ranking_structure_sha256(raw: dict) -> str:
    return ev.canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS})


class TestRankingTablesFrozen(unittest.TestCase):
    def test_structure_hash_matches_commit_t_or_pre_freeze_window(self):
        """Round 3 (spec §8 v1.14): between H1 and T the NON-VERB structure equals the H1 constant and verb_methods satisfies the
        Round 2 prefix invariant (suffixes may be added before T); from T the full structure equals the Round 3 freeze."""
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(ev.structure_check_problems(raw), [])
        if ev.current_round()["round"] >= 3:
            self.assertIsNone(ev.pending_round()); self.assertEqual(ranking_structure_sha256(raw), ev.freeze_for(ev.current_round()["round"])["structure_sha256"])
        else:
            pending = ev.pending_round()                      # Round 4 spec §9.1: Round 3 is closed in round_outcomes.json, so 4 is pending
            self.assertEqual(pending, 4); self.assertEqual(raw["version"], 2)
            self.assertEqual(ev.nonverb_structure_sha256(raw), ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256[pending])
            suffixed = json.loads(json.dumps(raw)); suffixed["verb_methods"]["get"] = ["GET", "POST"]            # a T-style suffix is allowed before T
            self.assertEqual(ev.structure_check_problems(suffixed), [])
            reordered = json.loads(json.dumps(raw)); reordered["verb_methods"]["change"] = ["POST", "PUT"]
            self.assertTrue(ev.structure_check_problems(reordered))
            moved = json.loads(json.dumps(raw)); moved["path_noise"] = moved["path_noise"] + ["zz"]
            self.assertTrue(ev.structure_check_problems(moved))

    def test_tuning_grid_sha256_helper(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(ev.tuning_grid_sha256(raw), ev.canonical_sha256(raw["tuning_grid"]))
        other = json.loads(json.dumps(raw)); other["constants"]["method_match_bonus"] = 1.0
        self.assertEqual(ev.tuning_grid_sha256(other), ev.tuning_grid_sha256(raw))        # constants do not change the grid hash

    def test_round_freeze_file_shape(self):
        f = ev.load_round_freeze()
        rounds = [e["round"] for e in f]
        self.assertIsInstance(f, list); self.assertEqual(rounds, sorted(rounds)); self.assertEqual(rounds[0], 1)
        decided = ev.round_states(f, ev.load_round_outcomes())                                 # Round 4 spec §9.1: gaps are closed rounds
        for r in range(1, rounds[-1] + 1):
            self.assertIn(r, decided, f"round {r} is neither frozen nor decided in round_outcomes.json")
        self.assertEqual(set(f[0]), {"round", "commit_T", "structure_sha256"})
        for e in f[1:]:
            self.assertEqual(set(e), ev.freeze_key_set(e["round"]), e["round"])
            self.assertNotIn("commit_T", e)                                                     # spec §9: T sha is not inside the T file
            sha_keys = SHA_KEYS_R4 if e["round"] >= 4 else (SHA_KEYS_R3 if e["round"] >= 3 else ROUND2_HASH_KEYS)
            for k in sha_keys | {"source_registry_fingerprint"}:
                self.assertRegex(e[k], r"^[0-9a-f]{64}$", k)
            if e["round"] >= 4:
                self.assertEqual(e["t_policy_files"], sorted(set(e["t_policy_files"])))
                self.assertTrue(set(e["t_policy_files"]) <= set(ev.T_DATA_FILES))
            self.assertEqual(set(e["source_spec_sha256"]), {"jira-platform", "jira-software", "confluence"})
            if e["round"] >= 3:
                self.assertEqual(set(e["reference_set"]), {"origin", "enc_sha256", "held_out_sha256", "negative_sha256"})
                self.assertEqual(e["reference_set"]["origin"], "round2"); self.assertEqual(e["hidden_set_origin"], f"round{e['round']}")
                self.assertIsInstance(e["hidden_generation_rules"], list)
        self.assertEqual(ev.current_round(), f[-1]); self.assertEqual(ev.freeze_for(1), f[0])

    def test_current_round_freeze_hashes_match_files(self):
        e = ev.current_round()
        if e["round"] < 2:
            print("round 2 not frozen yet: hash equality checked after commit T"); return
        if ev.pending_round() is not None:
            print(f"round {ev.pending_round()} structure/tooling committed at H; freeze hashes checked after its commit T"); return
        if ev.round_states(ev.load_round_freeze(), ev.load_round_outcomes()).get(e["round"]) == "aborted-pre-B":
            print(f"round {e['round']} freeze entry invalidated by X_preB: verified by the recovery chain, not current-file equality (spec §9.1)"); return
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
                if k.startswith("rule:"):                                                           # v1.24 phrase rule (Round 3 spec §6)
                    self.assertGreaterEqual(r, 3, k); rule = raw["rules"][int(k.split(":")[1])]
                    self.assertEqual(len(rule["when_all"]), 2, k); self.assertEqual(len(rule["add"]), 1, k)
                self.assertIsNone(n["seed_query_id"], k); self.assertEqual(n["failure_classes"], [], k)
                self.assertTrue(isinstance(n.get("evidence"), str) and n["evidence"], k)
                if lex is not None and lex.get("round") == r:
                    if k.startswith("rule:"):                                                       # phrase key == sorted token pair (v1.24)
                        match = [v for pk, v in lex["lexicon"].items() if " " in pk and frozenset(pk.split(" ")) == frozenset(rule["when_all"])]
                        self.assertEqual([rule["add"]], match, f"{k}: differs from concept_lexicon.json")
                    else:
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
            self.assertEqual(l["baseline"], {k: raw["baseline"][k] for k in l["baseline"]})   # logged axes are unchanged (baseline only grows)
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
                   "tests/benchmarks/round_seal.py", "tests/benchmarks/alias_candidates_tool.py",
                   "tests/benchmarks/regression_reference.py")


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
        self.assertEqual(ev.tooling_code_sha256(ROOT), ev.files_sha256(ROOT, ev.TOOLING_FILES))   # every tooling file exists
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
        out = set(sources.SOURCES) | self.catalog_tokens() | {t for k in lexicon for t in k.split(" ")}   # phrase keys contribute their tokens (v1.24)
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
        classes = {r["id"]: r["failure_classes"] for r in b["seed"]}
        self.assertEqual(tune.validate_alias_change(tune.strip_round_entries(raw, rnd), raw, cands, queries, classes), [])
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


FINAL_R3 = pathlib.Path(__file__).resolve().parent / "round3-final.json"


class TestRound3FinalArtifact(unittest.TestCase):
    """Guarded (mirrors TestRound2FinalArtifact): checked once tests/benchmarks/round3-final.json exists (after
    round3_simulation.py --phase H's commit D, or the real Round 3 commit D)."""

    def test_round3_final_artifact(self):
        if not FINAL_R3.exists():
            print("round3-final.json absent: checked after commit D"); return
        art = json.loads(FINAL_R3.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8")); seal = b["round3_seal"]
        e = ev.freeze_for(3)
        self.assertEqual(art["round"], 3)
        self.assertEqual(art["sealed_sha256"], {"held_out": seal["held_out_sha256"], "negative": seal["negative_sha256"]})
        self.assertEqual(art["evaluation_code_sha256"], e["evaluation_code_sha256_at_T"])
        self.assertEqual(art["tuning_grid_sha256"], e["tuning_grid_sha256"])
        self.assertEqual(set(art["sets"]["negative"]) >= {"raw_passed", "effective_passed"}, True)
        self.assertEqual(art["negative_actionable"]["total"], 4); self.assertEqual(art["negative_abstained"]["total"], 4)
        ref = art["reference_round2"]
        self.assertIsInstance(ref["invalid_key"], list); self.assertEqual(ref["enc_sha256"], e["reference_set"]["enc_sha256"])
        self.assertEqual(art["evaluation_domain"], "actionable recommendation queries")


class TestRound2PreTProvenance(unittest.TestCase):
    """AC-08 / AC-13 / spec §10.1 "pre-T order" / §10.2: the persisted pre-T artifacts were built from S and after the
    verb inventory was fixed. Guarded: checked once the round >= 2 freeze entry and the artifact exist."""

    def _doc(self, path):
        e = ev.current_round()
        if e["round"] < 2 or not path.exists():
            print(f"{path.name} or the round >= 2 freeze absent: checked after commit T"); return None, e
        return json.loads(path.read_text(encoding="utf-8")), e

    def test_registry_fingerprint_matches_freeze_source(self):
        for path in (LEXICON, CANDIDATES_DOC):
            doc, e = self._doc(path)
            if doc is not None:
                self.assertEqual(doc["generated_from"]["registry_fingerprint"], e["source_registry_fingerprint"], path.name)

    def test_lexicon_generated_from_frozen_verb_inventory(self):
        doc, e = self._doc(LEXICON)
        if doc is not None:
            self.assertEqual(doc["generated_from"]["inputs"]["verb_inventory"], e["verb_inventory_sha256"])


class TestFreezeFileHashes(unittest.TestCase):
    def test_brief_and_prompt_hashes_are_plain_file_sha256(self):
        """Review M-3: worker brief / prompt shas equal `shasum -a 256` of the file (no path prefix)."""
        import hashlib, tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "brief.md"; p.write_bytes(b"brief\n")
            self.assertEqual(ev.file_sha256(p), hashlib.sha256(b"brief\n").hexdigest())
            self.assertNotEqual(ev.file_sha256(p), ev.files_sha256(td, ("brief.md",)))


class TestLexiconAliasesSha256(unittest.TestCase):
    """spec §10.1: lexicon_aliases_sha256 covers only the lexicon-r{N} subset (aliases + notes)."""

    def test_unchanged_by_round_alias_changed_by_lexicon_edit(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "search_aliases.json"
            shutil.copyfile(ALIASES, p)                                   # never the live file
            raw = json.loads(p.read_text(encoding="utf-8"))
            raw["aliases"]["zzsynonym"] = ["issue"]
            raw["notes"]["zzsynonym"] = {"origin": "lexicon-r2", "seed_query_id": None, "failure_classes": [], "evidence": "concept lexicon r2"}
            p.write_text(json.dumps(raw), encoding="utf-8")
            base = ev.lexicon_aliases_sha256(json.loads(p.read_text(encoding="utf-8")), 2)
            self.assertNotEqual(base, ev.lexicon_aliases_sha256(json.loads(p.read_text(encoding="utf-8")), 3))   # other round: empty subset
            raw["aliases"]["zzcandidate"] = ["page"]                      # a round2 alias added in B..C
            raw["notes"]["zzcandidate"] = {"origin": "round2", "seed_query_id": "s-001", "candidate_word": "zzcandidate",
                                           "failure_classes": ["R6"], "evidence": "x"}
            raw["rules"].append({"when_all": ["zzcandidate", "issue"], "add": ["page"]})
            raw["notes"][f"rule:{len(raw['rules']) - 1}"] = dict(raw["notes"]["zzcandidate"])
            p.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(ev.lexicon_aliases_sha256(json.loads(p.read_text(encoding="utf-8")), 2), base)
            for edit in (lambda r: r["aliases"].__setitem__("zzsynonym", ["page"]),
                         lambda r: r["notes"]["zzsynonym"].__setitem__("evidence", "edited")):
                edited = json.loads(p.read_text(encoding="utf-8")); edit(edited)
                self.assertNotEqual(ev.lexicon_aliases_sha256(edited, 2), base)


    def test_lexicon_aliases_sha256_covers_lexicon_rules(self):                                        # H10 review I4 (v1.24 phrase rules)
        raw = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"starred": ["favourite"]},
               "rules": [{"when_all": ["entry", "time"], "add": ["worklog"]}, {"when_all": ["issue", "key"], "add": ["getissue"]}],
               "notes": {"starred": {"origin": "lexicon-r3", "seed_query_id": None, "failure_classes": [], "evidence": "x"},
                         "rule:0": {"origin": "lexicon-r3", "seed_query_id": None, "failure_classes": [], "evidence": "x phrase"},
                         "rule:1": {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "legacy"}}}
        base = ev.lexicon_aliases_sha256(raw, 3)
        changed = json.loads(json.dumps(raw)); changed["rules"][0]["add"] = ["blogpost"]
        self.assertNotEqual(base, ev.lexicon_aliases_sha256(changed, 3))                               # a lexicon-r3 rule edit changes the hash
        legacy = json.loads(json.dumps(raw)); legacy["rules"][1]["add"] = ["other"]
        self.assertEqual(base, ev.lexicon_aliases_sha256(legacy, 3))                                   # non-lexicon rules stay outside the subset
        self.assertEqual(ev.lexicon_aliases_sha256(raw, 2), ev.lexicon_aliases_sha256({**raw, "rules": [], "notes": {}}, 2))   # round 2 unaffected

class TestRound3SymmetricJudgement(unittest.TestCase):
    """Round 3 spec §4 / §13: held_out requires actionable; negatives pass when abstained; seed is raw top-1; a legacy
    search_fn (ranked keys only) is read as actionable=True so Round 1/2 judgements never change."""
    def rec(self, i, q, exp, forb, origin):
        return {"id": i, "query": q, "expected_top1_any": exp, "forbidden_top1": forb, "origin": origin, "failure_classes": [], "ambiguous": False}

    def setUp(self):
        self.H = [self.rec("h-001", "get the ticket", ["A"], [], "held_out-r3"), self.rec("h-002", "ticket details", ["A"], [], "held_out-r3")]
        self.N = [self.rec("n-001", "ticket owner list", [], ["F"], "negative-r3"), self.rec("n-002", "get the owner", [], ["F"], "negative-r3")]
        self.table = {"get the ticket": (["A"], True), "ticket details": (["A"], False), "ticket owner list": (["F"], False), "get the owner": (["F"], True)}
        self.fn = lambda q: self.table[q]
        self.legacy = lambda q: self.table[q][0]

    def test_held_out_requires_actionable(self):
        res = ev.evaluate(self.H, self.fn, section="held_out")
        self.assertEqual((res["passed"], res["raw_passed"], res["effective_passed"]), (1, 2, 1))
        self.assertEqual([f["id"] for f in res["failed"]], ["h-002"]); self.assertEqual((res["failed"][0]["actionable"], res["failed"][0]["raw_ok"]), (False, True))
        self.assertEqual(res["actionable"], {"total": 1, "raw_passed": 1}); self.assertEqual(res["abstained"], {"total": 1, "effective_passed": 0})

    def test_negative_passes_when_abstained_fails_when_actionable(self):
        res = ev.evaluate(self.N, self.fn, section="negative")
        self.assertEqual((res["passed"], res["raw_passed"], res["effective_passed"]), (1, 0, 1))
        self.assertEqual([f["id"] for f in res["failed"]], ["n-002"])
        self.assertEqual(res["actionable"], {"total": 1, "raw_passed": 0}); self.assertEqual(res["abstained"], {"total": 1, "effective_passed": 1})
        same = ev.evaluate(self.N, self.fn, section="regression_negative")
        self.assertEqual((same["passed"], same["raw_passed"]), (1, 0))

    def test_seed_section_is_raw_top1(self):
        res = ev.evaluate(self.H, self.fn, section="seed")
        self.assertEqual((res["passed"], res["failed"]), (2, [])); self.assertNotIn("raw_passed", res)

    def test_legacy_search_fn_is_actionable_true(self):                                                 # review focus 4
        self.assertEqual(ev.ranked_and_actionable(self.legacy, "ticket details"), (["A"], True))
        self.assertEqual(ev.ranked_and_actionable(self.fn, "ticket details"), (["A"], False))
        self.assertEqual(ev.evaluate(self.H, self.legacy, section="held_out")["passed"], 2)
        self.assertEqual(ev.evaluate(self.N, self.legacy, section="negative")["passed"], 0)
        res = ev.evaluate(self.N, self.legacy)                                                           # Round 1 call form, no section
        self.assertEqual(res["passed"], 0); self.assertNotIn("raw_passed", res)
        self.assertEqual(set(res["failed"][0]), {"id", "query", "top1", "expected_top1_any", "forbidden_top1"})   # Round 1 failure shape


class TestRound3FreezeKeys(unittest.TestCase):
    def test_freeze_key_set_per_round(self):
        self.assertEqual(ev.freeze_key_set(1), {"round", "commit_T", "structure_sha256"})
        self.assertEqual(ev.freeze_key_set(2), ROUND2_HASH_KEYS | {"round", "source_registry_fingerprint", "source_spec_sha256"})
        self.assertEqual(ev.freeze_key_set(3), ev.freeze_key_set(2) | set(ev.ROUND3_EXTRA_KEYS))
        self.assertNotIn("commit_T", ev.freeze_key_set(3))
        self.assertEqual(ev.freeze_key_set(2), set(ev.freeze_for(2)))


class TestRoundStateModel(unittest.TestCase):
    """Round 4 spec §9.1: closed / frozen / aborted-pre-B states, pending_round skips decided rounds, round 4 freeze keys."""
    F12 = [{"round": 1}, {"round": 2}]

    def test_pending_round_skips_closed_round(self):
        with mock.patch.dict(ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256, {3: "a", 4: "b"}, clear=True):
            self.assertEqual(ev.pending_round(self.F12, [{"round": 3, "outcome": "pre-T not reached"}]), 4)
            self.assertEqual(ev.pending_round(self.F12, []), 3)                       # Round 3 history without outcomes

    def test_round_states_three_kinds_and_rejections(self):
        f = self.F12 + [{"round": 4}]
        o = [{"round": 3, "outcome": "pre-T not reached"}, {"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": False}]
        self.assertEqual(ev.round_states(f, o), {1: "frozen", 2: "frozen", 3: "closed", 4: "aborted-pre-B"})
        with self.assertRaises(ValueError):
            ev.round_states(f, [{"round": 4, "outcome": "pre-T not reached"}])        # freeze + ordinary outcome
        with self.assertRaises(ValueError):
            ev.round_states(self.F12, [{"round": 3, "outcome": "aborted-pre-B", "invalidated_by": "X_preB"}])   # orphan abort (no freeze)
        with self.assertRaises(ValueError):
            ev.round_states(f, [{"round": 4, "outcome": "aborted-pre-B"}])            # abort without invalidated_by

    def test_current_round_is_max_not_last(self):
        self.assertEqual(ev.current_round([{"round": 4}, {"round": 2}])["round"], 4)

    def test_freeze_key_set_round4(self):
        self.assertEqual(ev.freeze_key_set(4), ev.freeze_key_set(3) | set(ev.ROUND4_EXTRA_KEYS))
        self.assertNotIn("commit_T", ev.freeze_key_set(4))

    def test_committed_outcomes_file_shape(self):
        o = ev.load_round_outcomes()
        self.assertEqual(o[0]["round"], 3); self.assertEqual(o[0]["outcome"], "pre-T not reached")
        self.assertEqual([e["round"] for e in o], sorted(e["round"] for e in o))
        ev.round_states(ev.load_round_freeze(), o)                                       # every record is a valid decided state (raises otherwise)
        for r in ev.load_round_recoveries():
            self.assertEqual(r.get("recovery_mode"), "rollback")


class TestToolingFilesRound4(unittest.TestCase):
    def test_tooling_files_exist_and_one_byte_changes_sha(self):
        import shutil, tempfile
        for rel in ev.TOOLING_FILES:
            self.assertTrue((ROOT / rel).exists(), rel)
        self.assertIn("tests/benchmarks/doc_titles.py", ev.TOOLING_FILES)
        with tempfile.TemporaryDirectory() as td:
            copy = pathlib.Path(td)
            for rel in ev.TOOLING_FILES:
                (copy / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / rel, copy / rel)
            before = ev.tooling_code_sha256(copy)
            with open(copy / "tests/benchmarks/doc_titles.py", "ab") as fh:
                fh.write(b"#")
            self.assertNotEqual(ev.tooling_code_sha256(copy), before)


class TestChangedFilesSince(unittest.TestCase):
    def test_changed_files_since_includes_untracked(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td); run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)
            run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
            (repo / "a.txt").write_text("a"); run("add", "-A"); run("commit", "-q", "-m", "base")
            (repo / "a.txt").write_text("b"); (repo / "new.txt").write_text("n")
            self.assertEqual(ev.changed_files_since(repo, "HEAD"), ["a.txt", "new.txt"])
