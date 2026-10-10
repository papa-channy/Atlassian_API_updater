import unittest
from tests.benchmarks import counterexample as cx

BASE = {"aliases": {"ticket": ["issue"]}, "rules": [{"when_all": ["blog", "entry"], "add": ["blogpost"]}], "notes": {}}


def raw(aliases=None, rules=None):
    return {"aliases": dict(BASE["aliases"], **(aliases or {})), "rules": list(BASE["rules"]) + list(rules or []), "notes": {}}


INDEX = [{"key": "a:GET:/version", "summary_tokens": frozenset({"get", "version"}), "opid_path_tokens": frozenset({"version"})},
         {"key": "a:GET:/release", "summary_tokens": frozenset({"get", "release"}), "opid_path_tokens": frozenset({"release"})},
         {"key": "a:GET:/build", "summary_tokens": frozenset({"get", "build"}), "opid_path_tokens": frozenset({"build"})}]


class TestCounterexample(unittest.TestCase):
    def test_tokens_projection(self):
        self.assertEqual(cx.counterexample_tokens(("alias", "search")), ("search",))
        self.assertEqual(cx.counterexample_tokens(("phrase", ("issue", "type"))), ("issue", "type"))
        self.assertNotIn("alias", cx.counterexample_tokens(("alias", "search"))); self.assertNotIn("phrase", cx.counterexample_tokens(("phrase", ("issue", "type"))))

    def test_canonical_map_and_diff(self):
        a, b = cx.canonical_policy_map(raw()), cx.canonical_policy_map(raw({"release": ["version"]}))
        self.assertEqual(cx.diff(a, b), [("alias", "release")])
        self.assertIn(("phrase", ("blog", "entry")), a)

    def test_old_to_absent_is_a_changed_key(self):
        pre, post = raw({"release": ["build"]}), raw()
        self.assertEqual(cx.diff(cx.canonical_policy_map(pre), cx.canonical_policy_map(post)), [("alias", "release")])

    def test_loss_detection_and_classes(self):
        top1 = lambda policy, q: "a:GET:/build" if ("release" in policy["aliases"] and "release" in q) else {"get version": "a:GET:/version", "get release": "a:GET:/release", "get build": "a:GET:/build"}[q]
        out = cx.suite(INDEX, top1, raw(), raw({"release": ["build"]}), raw({"release": ["build"]}), summaries={"a:GET:/version": "get version", "a:GET:/release": "get release", "a:GET:/build": "get build"})
        self.assertEqual(out["classes"]["covered_static"], [["alias", "release"]]); self.assertEqual(out["losses"], [{"key": ["alias", "release"], "op": "a:GET:/release"}])

    def test_uncovered_proposer_key_blocks_accept(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw(), raw(), raw({"zzword": ["version"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX})
        self.assertEqual(out["classes"]["uncovered_proposer"], [["alias", "zzword"]]); self.assertFalse(out["ok"])

    def test_proposer_wins_when_both_changed(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw({"zzword": ["build"]}), raw({"zzword": ["release"]}), raw({"zzword": ["version"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX})
        self.assertEqual(out["classes"]["uncovered_proposer"], [["alias", "zzword"]]); self.assertEqual(out["classes"]["uncovered_static"], [])

    def test_uncovered_static_is_recorded_not_blocking(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX},
                       provenance={("alias", "zzword"): {"source": "round4_generation", "provenance_rank": 1}})
        self.assertTrue(out["ok"]); self.assertEqual([d["key"] for d in out["uncovered_static_diagnostics"]], [["alias", "zzword"]])

    def test_missing_provenance_is_incomplete_and_shas_bound(self):
        top1 = lambda policy, q: "a:GET:/version"
        sm = {k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX}
        out = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"]}), summaries=sm)
        self.assertIn("counterexample_diagnostic_incomplete", out["validation_errors"]); self.assertFalse(out["ok"])
        good = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"]}), summaries=sm,
                        provenance={("alias", "zzword"): {"source": "round4_generation", "provenance_rank": 1}}, scope="final_policy", selected_constants={"a": 1})
        self.assertTrue(good["ok"]); self.assertEqual(good["scope"], "final_policy"); self.assertEqual(good["selected_constants"], {"a": 1})
        other = cx.suite(INDEX, top1, raw(), raw({"zzword": ["version"]}), raw({"zzword": ["version"], "yy": ["build"]}), summaries=sm,
                         provenance={("alias", "zzword"): {"source": "round4_generation", "provenance_rank": 1}})
        self.assertNotEqual(good["post_policy_sha256"], other["post_policy_sha256"])

    def test_provenance_from_lexicon(self):
        doc = {"selected": {"release": {"source": "round4_generation", "provenance_rank": 1}}, "rejected": {"release": {"reason": "seed-incompatible"},
               "fresh": {"reason": "no-eligible-candidate", "candidates": [{"source": "round2_archive"}]}}}
        prov = cx.provenance_from_lexicon(doc)
        self.assertEqual(prov[("alias", "release")], {"source": "round4_generation", "provenance_rank": 1, "gate_reason": "seed-incompatible"})
        capped = cx.provenance_from_lexicon({"selected": {"fff": {"source": "round4_generation", "provenance_rank": 1}}, "rejected": {"fff": {"reason": "concept-cap"}}})
        self.assertEqual(capped[("alias", "fff")]["gate_reason"], "concept-cap")
        self.assertIsNone(prov[("alias", "fresh")]["source"])

    def test_partition_invariant(self):
        top1 = lambda policy, q: "a:GET:/version"
        out = cx.suite(INDEX, top1, raw(), raw({"release": ["version"]}), raw({"release": ["version"], "zzword": ["build"]}), summaries={k["key"]: " ".join(sorted(k["summary_tokens"])) for k in INDEX})
        parts = [tuple(map(tuple, v)) for v in out["classes"].values()]
        flat = [k for p in parts for k in p]
        self.assertEqual(sorted(flat), sorted(map(tuple, out["scope_keys"]))); self.assertEqual(len(flat), len(set(flat)))
