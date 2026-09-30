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
        self.assertEqual(len(b["seed"]), 23); self.assertEqual(len(b["regression_negative"]), 6)

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
RANKING_STRUCTURE_SHA256 = "8bcd33bb905e3d4946218f05d0edcebe9df6c30060d9de567e88157c820dcf9f"
STRUCTURE_KEYS = ("verb_methods", "path_noise", "product_hints", "tuning_grid", "baseline")


def ranking_structure_sha256(raw: dict) -> str:
    return ev.canonical_sha256({k: raw[k] for k in STRUCTURE_KEYS})


class TestRankingTablesFrozen(unittest.TestCase):
    def test_structure_hash_matches_commit_t(self):
        raw = json.loads(RANKING.read_text(encoding="utf-8"))
        self.assertEqual(ranking_structure_sha256(raw), RANKING_STRUCTURE_SHA256)

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
                from tests.benchmarks import round1_seal as rs
                self.assertIsNotNone(seal, "plaintext hidden sets require round1_seal")
                self.assertEqual(len(section), expected_count)
                self.assertEqual(ev.canonical_sha256(section), seal[f"{sect}_sha256"])
                self.assertEqual(rs.distribution(section, sect), seal[f"{sect}_distribution"])
            # empty list before commit B: nothing to check

    def test_hidden_plaintext_machine_rules(self):
        from tests.benchmarks import round1_seal as rs
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
            self.assertEqual(l["baseline"], raw["baseline"])
        adopted = [l for l in lines if l.get("adopted")]
        if not adopted:
            self.skipTest("Round 1: seed shortfall pending controller ruling")
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
