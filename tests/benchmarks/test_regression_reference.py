"""AC-R3-02: the Round 3 scorer with the two new constants at 0, the B aliases and the B inventory reproduces the Round 2
scorer's whole ranked list (keys, scores, total_matches) on the pinned reference (snapshot S2 + fixture registry)."""
import json, os, pathlib, unittest
from tests.benchmarks import evaluator as ev
from tests.benchmarks import regression_reference as rr

REF = pathlib.Path(__file__).resolve().parent / "round3-regression-reference.json"
BENCH = pathlib.Path(__file__).resolve().parent / "search_queries.json"


class TestRegressionReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = json.loads(REF.read_text(encoding="utf-8"))

    def test_reference_provenance_is_the_round2_b_policy(self):
        r, e2 = self.ref, ev.freeze_for(2)
        self.assertEqual(r["reference_commit"], "29dba38"); self.assertEqual(r["tool_version"], rr.TOOL_VERSION); self.assertEqual(r["limit"], 50)
        self.assertEqual(r["aliases_sha256"], ev.canonical_sha256(r["b_aliases"])); self.assertEqual(r["ranking_sha256"], ev.canonical_sha256(r["b_ranking"]))
        self.assertEqual(ev.canonical_sha256(r["b_ranking"]["verb_methods"]), e2["verb_inventory_sha256"])
        self.assertEqual(r["registry_fingerprint"], e2["source_registry_fingerprint"]); self.assertEqual(r["spec_sha256"], e2["source_spec_sha256"])
        self.assertRegex(r["search_py_sha256"], r"^[0-9a-f]{64}$")
        bench = json.loads(BENCH.read_text(encoding="utf-8")); snap_q, fix_q = rr.query_sets(bench)
        self.assertEqual(r["query_set_sha256"], ev.canonical_sha256({"snapshot": snap_q, "fixture": fix_q}))
        self.assertEqual((len(r["snapshot"]), len(r["fixture"])), (53, 29))
        for block in (r["snapshot"], r["fixture"]):
            for q, row in block.items():
                self.assertEqual(set(row), {"keys", "scores", "total_matches"}); self.assertEqual(len(row["keys"]), len(row["scores"]))
                self.assertGreaterEqual(row["total_matches"], len(row["keys"]))

    def test_fixture_part_matches_current_scorer(self):
        self.assertEqual(rr.verify_reference(self.ref, cache_dir=None), [])

    def test_snapshot_part_matches_current_scorer_when_archive_present(self):
        cache = os.environ.get("ATLASSIAN_DOCS_ROUND2_CACHE") or str(pathlib.Path.home() / ".atlassian_api_updater" / "archive" / "round2" / "round2-cache")
        if not pathlib.Path(cache).is_dir():
            print("archived Round 2 snapshot not available: snapshot part of AC-R3-02 checked by the controller (ledger)"); return
        self.assertEqual(rr.verify_reference(self.ref, cache_dir=pathlib.Path(cache)), [])

    def test_reference_runs_in_legacy_ordering_mode(self):                                              # AC-R3-02 (v1.24)
        from tools.atlassian_docs.intelligence import policy, search
        rp, _ = rr._pinned_policies(self.ref, policy)
        self.assertEqual(dict(rp.ordering_rules), search.LEGACY_ORDERING_RULES)

    def test_round3_freeze_pins_the_reference(self):
        if ev.current_round()["round"] < 3:
            print("round 3 not frozen yet: regression_reference_sha256 checked after commit T"); return
        self.assertEqual(ev.freeze_for(3)["regression_reference_sha256"], ev.canonical_sha256(self.ref))
