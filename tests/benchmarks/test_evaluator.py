import json, pathlib, unittest
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
