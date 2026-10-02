import json, os, pathlib, unittest
from tests.benchmarks.evaluator import evaluate
from tests.benchmarks import evaluator as ev

BENCH = pathlib.Path(__file__).resolve().parent / "search_queries.json"


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
        self.assertEqual(len(b["seed"]), 39); self.assertEqual(len(b["regression_negative"]), 14)
        # Round 1 hidden sets were observed at commit D and demoted before Round 2 (s-024..s-039, rn-007..rn-014)
        self.assertEqual([r["id"] for r in b["seed"][23:]], [f"s-{i:03d}" for i in range(24, 40)])
        self.assertEqual({r["origin"] for r in b["seed"][23:]}, {"held_out-r1"})
        self.assertEqual([r["id"] for r in b["regression_negative"][6:]], [f"rn-{i:03d}" for i in range(7, 15)])
        self.assertEqual({r["origin"] for r in b["regression_negative"][6:]}, {"negative-r1"})
        self.assertEqual((b["held_out"], b["negative"]), ([], []))

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

    def test_sealed_or_plain_matches_round1_seal(self):
        seal = self.b.get("round1_seal")
        for sect in ("held_out", "negative"):
            section = self.b[sect]
            expected_count = 16 if sect == "held_out" else 8
            if ev.is_sealed(section):
                self.assertEqual(section["count"], expected_count); self.assertEqual(section["round"], 1)
                self.assertRegex(section["sha256"], r"^[0-9a-f]{64}$"); self.assertEqual(section["sha256"], seal[f"{sect}_sha256"])
                self.assertEqual(section["distribution"], seal[f"{sect}_distribution"])
            elif section:                       # plaintext after commit D
                from tests.benchmarks import round_seal as rs
                self.assertIsNotNone(seal, "plaintext hidden sets require round1_seal")
                self.assertEqual(len(section), expected_count)
                self.assertEqual(ev.canonical_sha256(section), seal[f"{sect}_sha256"])
                self.assertEqual(rs.distribution(section, sect), seal[f"{sect}_distribution"])
            # empty list before commit B: nothing to check

    def test_hidden_plaintext_machine_rules(self):
        from tests.benchmarks import round_seal as rs
        if ev.is_sealed(self.b["held_out"]) or not self.b["held_out"]:
            print("hidden sets sealed or absent: machine rules checked at commit D"); return
        cache = os.environ.get("ATLASSIAN_DOCS_ROUND1_CACHE")
        if not cache or not pathlib.Path(cache).exists():
            self.skipTest("snapshot not available for catalog rules")
        _, internal, _, _ = rs.load_catalogs_from_cache(pathlib.Path(cache))
        self.assertEqual(rs.machine_check({"held_out": self.b["held_out"], "negative": self.b["negative"]}, self.b, internal), [])


ALIASES = RANKING.parent / "search_aliases.json"
TUNING_LOG = pathlib.Path(__file__).resolve().parent / "search-tuning-round1.jsonl"


class TestAliasNotesAndTuningLog(unittest.TestCase):
    def test_alias_notes_r4_only(self):
        raw = json.loads(ALIASES.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8"))
        seed_ids = {r["id"]: r for r in b["seed"]}
        expected_keys = set(raw["aliases"]) | {f"rule:{i}" for i in range(len(raw["rules"]))}
        self.assertEqual(set(raw["notes"]), expected_keys)
        per_seed = {}
        for k, n in raw["notes"].items():
            self.assertIn(n["origin"], ("phase2.5", "round1"))
            if n["origin"] == "round1":
                self.assertIn(n["seed_query_id"], seed_ids); self.assertIn("R4", n["failure_classes"])
                self.assertIn("R4", seed_ids[n["seed_query_id"]]["failure_classes"])
                per_seed[n["seed_query_id"]] = per_seed.get(n["seed_query_id"], 0) + 1
        self.assertTrue(all(c <= 1 for c in per_seed.values()), per_seed)

    def test_tuning_log_adopted(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8")); b = json.loads(BENCH.read_text(encoding="utf-8"))
        lines = [json.loads(l) for l in TUNING_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        for l in lines:   # every logged run, adopted or not
            for k, v in l["selected"].items():
                self.assertIn(v, raw["tuning_grid"][k])
            self.assertEqual(l["registry_fingerprint"], b["round1_seal"]["registry_fingerprint"])
            if l["ranking_structure_sha256"] == RANKING_STRUCTURE_SHA256:
                self.assertEqual(l["baseline"], raw["baseline"])
            else:   # pre-T2 run (spec v1.4 §0.4): logged under the 5-key table; its recorded axes must be unchanged
                self.assertEqual(l["baseline"], {k: raw["baseline"][k] for k in l["baseline"]})
        adopted = [l for l in lines if l.get("adopted")]
        self.assertEqual(len(adopted), 1); self.assertEqual(adopted[0]["selected"], raw["constants"])

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
# Words of the spec §6.2 tables (frozen at commit T, b3c2ba5, before the hidden sets were generated) that occur in
# neither a seed query nor a fixture operationId/path. Exact equality below: a new uncovered word fails, and so does
# a stale entry. Pending controller ruling (Task 8 report).
PROVENANCE_EXCEPTIONS = frozenset({"epic", "find", "read", "rename"})


class TestPolicyVocabularyProvenance(unittest.TestCase):
    """Word-provenance check only (spec §7): every policy word comes from a seed query, a fixture operationId/path,
    or a source name. It is NOT a seal proof — it cannot show that no hidden query influenced the policy."""

    def allowed(self):
        from tools.atlassian_docs import sources
        b = json.loads(BENCH.read_text(encoding="utf-8"))
        out = set(sources.SOURCES)
        for rec in b["seed"]:
            out |= ev.unigram_set(rec["query"])   # every seed record (r0 + demoted r1) is Round 2 tuning vocabulary
        for name in sources.SOURCES:
            spec = json.loads((FIXTURES / f"{name}-openapi.json").read_text(encoding="utf-8"))
            for path, item in spec["paths"].items():
                out |= ev.unigram_set(path)
                for op in item.values():
                    if isinstance(op, dict) and isinstance(op.get("operationId"), str):
                        out |= ev.unigram_set(op["operationId"]); out.add(op["operationId"].lower())
        return out

    def policy_words(self):
        rk = json.loads(RANKING.read_text(encoding="utf-8")); al = json.loads(ALIASES.read_text(encoding="utf-8"))
        words = set(rk["verb_methods"]) | set(rk["product_hints"]) | set(rk["path_noise"])
        for k, v in al["aliases"].items():
            words |= {k, *v}
        for rule in al["rules"]:
            words |= set(rule["when_all"]) | set(rule["add"])
        return words

    def test_policy_vocabulary_provenance(self):
        uncovered = self.policy_words() - self.allowed()
        self.assertEqual(uncovered, set(PROVENANCE_EXCEPTIONS), sorted(uncovered))
        spec_text = SPEC_R1.read_text(encoding="utf-8")
        for w in PROVENANCE_EXCEPTIONS:
            self.assertIn(f'"{w}"', spec_text, w)


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
        if not CANDIDATES.exists():
            print("alias_candidates.json absent: checked after commit T"); return
        from tests import tune_search_ranking as tune
        raw = json.loads(ALIASES.read_text(encoding="utf-8")); cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
        b = json.loads(BENCH.read_text(encoding="utf-8")); queries = {r["id"]: r["query"] for r in b["seed"]}
        self.assertEqual(tune.validate_alias_change(tune.strip_round_entries(raw, 2), raw, cands, queries), [])
        seeds = {r["id"]: r for r in b["seed"]}
        for n in raw["notes"].values():
            if n["origin"] == "round2":
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
