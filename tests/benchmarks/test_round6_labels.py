import copy
import unittest

from tests.benchmarks import evaluator as ev, round6_labels as L


def _bench():
    seed = [{"id": f"s-{i:03d}", "query": f"get thing {i}", "expected_top1_any": ["a:GET:/x"], "forbidden_top1": [], "origin": "seed-r1",
             "failure_classes": [], "ambiguous": False} for i in range(1, 40)]
    reg = [{"id": f"rn-{i:03d}", "query": f"remove page {i}", "expected_top1_any": [], "forbidden_top1": ["c:DELETE:/p/{id}", "c:GET:/p"],
            "origin": "seed-r1", "failure_classes": [], "ambiguous": False} for i in range(1, 15)]
    return {"seed": seed, "regression_negative": reg}


def _plain():
    held = [{"id": f"h-{i:03d}", "query": f"show alpha {i}", "expected_top1_any": ["a:GET:/y"], "forbidden_top1": [], "origin": "held_out-r5",
             "failure_classes": [], "ambiguous": False} for i in range(1, 17)]
    neg = [{"id": f"n-{i:03d}", "query": f"delete beta {i}", "expected_top1_any": [], "forbidden_top1": ["a:DELETE:/z"], "origin": "negative-r5",
            "failure_classes": [], "ambiguous": False} for i in range(1, 9)]
    return {"held_out": held, "negative": neg}


def _seal(plain):
    return {"held_out_sha256": ev.canonical_sha256(plain["held_out"]), "negative_sha256": ev.canonical_sha256(plain["negative"])}


class TestPromotion(unittest.TestCase):
    def test_ids_origin_provenance_identity(self):
        plain = _plain()
        b, payload = L.promote(_bench(), plain, _seal(plain))
        new_seed = [r for r in b["seed"] if r["origin"] == "promoted-r5"]
        self.assertEqual([r["id"] for r in new_seed], [f"s-{i:03d}" for i in range(40, 56)])
        self.assertEqual([r["promoted_from"]["source_id"] for r in new_seed], [f"h-{i:03d}" for i in range(1, 17)])
        new_rn = [r for r in b["regression_negative"] if r["origin"] == "promoted-r5"]
        self.assertEqual([r["id"] for r in new_rn], [f"rn-{i:03d}" for i in range(15, 23)])
        src = {r["id"]: r for r in plain["held_out"] + plain["negative"]}
        for r in new_seed + new_rn:
            self.assertEqual(r["promoted_from"]["source_record_sha256"], ev.canonical_sha256(src[r["promoted_from"]["source_id"]]))
            self.assertEqual(L.promotion_identity(r), L.source_identity(src[r["promoted_from"]["source_id"]]))
        self.assertEqual(payload["promotion_payload_sha256"], L.promotion_payload_sha256(b))

    def test_promotion_empties_the_observed_hidden_sections(self):
        """The Round 5 plaintext moves (not copies) into seed/regression: held_out/negative become the next round's empty slots."""
        plain = _plain(); bench = {**_bench(), "held_out": copy.deepcopy(plain["held_out"]), "negative": copy.deepcopy(plain["negative"])}
        b, _ = L.promote(bench, plain, _seal(plain))
        self.assertEqual((b["held_out"], b["negative"]), ([], []))
        other = {**_bench(), "held_out": [], "negative": []}
        self.assertEqual(L.promote(other, plain, _seal(plain))[0]["held_out"], [])

    def test_seal_mismatch_refused(self):
        plain = _plain(); bad = _seal(plain); bad["negative_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            L.promote(_bench(), plain, bad)

    def test_identity_survives_relabel_and_reconcile(self):
        plain = _plain(); b, _ = L.promote(_bench(), plain, _seal(plain))
        labels = {t["id"]: {"answerable": t["id"] == "rn-015", "acceptable_keys": ["a:DELETE:/z"] if t["id"] == "rn-015" else []}
                  for t in L.relabel_targets(b)}
        b2 = L.apply_labels(b, labels, {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels})
        r = next(x for x in b2["regression_positive"] if x["id"] == "rn-015")
        self.assertEqual(L.promotion_identity(r), L.source_identity(plain["negative"][0]))


class TestRelabel(unittest.TestCase):
    KEYS = {"c:DELETE:/p/{id}", "c:GET:/p", "a:DELETE:/z"}

    def test_targets_are_all_22(self):
        plain = _plain(); b, _ = L.promote(_bench(), plain, _seal(plain))
        t = L.relabel_targets(b)
        self.assertEqual(len(t), 22); self.assertEqual(set(t[0]), {"id", "query"})

    def test_review_schema(self):
        ids = ["rn-001", "rn-002"]
        ok = {"labels": {"rn-001": {"answerable": True, "acceptable_keys": ["c:DELETE:/p/{id}"]}, "rn-002": {"answerable": False, "acceptable_keys": []}}}
        self.assertEqual(L.check_review(ok, ids, self.KEYS), [])
        for bad in ({"labels": {"rn-001": {"answerable": True, "acceptable_keys": []}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": {"answerable": False, "acceptable_keys": ["c:GET:/p"]}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": {"answerable": True, "acceptable_keys": ["c:GET:/p", "c:DELETE:/p/{id}"]}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": {"answerable": True, "acceptable_keys": ["x:GET:/nope"]}, "rn-002": ok["labels"]["rn-002"]}},
                    {"labels": {"rn-001": ok["labels"]["rn-001"]}}):
            self.assertTrue(L.check_review(bad, ids, self.KEYS), bad)

    def test_set_comparison_and_adjudication(self):
        a = {"rn-001": {"answerable": True, "acceptable_keys": ["c:DELETE:/p/{id}", "c:GET:/p"]}, "rn-002": {"answerable": False, "acceptable_keys": []}}
        b = {"rn-001": {"answerable": True, "acceptable_keys": ["c:GET:/p", "c:DELETE:/p/{id}"]}, "rn-002": {"answerable": True, "acceptable_keys": ["c:GET:/p"]}}
        self.assertEqual(L.disagreements(a, b), ["rn-002"])
        with self.assertRaises(ValueError):
            L.final_labels(a, b)                                         # a disagreement needs the third review
        c = {"rn-002": {"answerable": False, "acceptable_keys": []}}
        self.assertFalse(L.final_labels(a, b, c)["rn-002"]["answerable"])

    def test_reconcile_moves_conflicting_forbidden_to_legacy(self):
        rec = {"id": "rn-001", "forbidden_top1": ["c:DELETE:/p/{id}", "c:GET:/p"]}
        out = L.reconcile_forbidden(rec, ["c:DELETE:/p/{id}"])
        self.assertEqual((out["forbidden_top1"], out["legacy_forbidden_top1"]), (["c:GET:/p"], ["c:DELETE:/p/{id}"]))

    def test_apply_moves_sections_and_passes_schema(self):
        b = _bench()
        labels = {r["id"]: {"answerable": r["id"] == "rn-001", "acceptable_keys": ["c:DELETE:/p/{id}"] if r["id"] == "rn-001" else []}
                  for r in b["regression_negative"]}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels}
        out = L.apply_labels(b, labels, mig)
        self.assertEqual([r["id"] for r in out["regression_positive"]], ["rn-001"])
        self.assertTrue(all(r["no_answer"] for r in out["regression_negative"]))
        ev.check_schema("regression_positive", out["regression_positive"]); ev.check_schema("regression_negative", out["regression_negative"])
        self.assertFalse(set(out["regression_positive"][0]["expected_top1_any"]) & set(out["regression_positive"][0]["forbidden_top1"]))

    def test_catalog_closure(self):
        b = _bench(); b["seed"][0]["expected_top1_any"] = ["a:GET:/x", "gone:GET:/old"]
        out, stop = L.catalog_closure(b, {"a:GET:/x"})
        self.assertEqual(out["seed"][0]["expected_top1_any"], ["a:GET:/x"]); self.assertEqual(out["seed"][0]["catalog_missing_keys"], ["gone:GET:/old"])
        self.assertEqual(stop, [])
        b2 = copy.deepcopy(b); b2["seed"][1]["expected_top1_any"] = ["gone:GET:/old"]
        _, stop2 = L.catalog_closure(b2, {"a:GET:/x"})
        self.assertEqual(stop2, ["s-002"])

    def test_split_sha_ignores_failure_classes_only(self):
        b = _bench(); base = L.training_split_sha256(b)
        b2 = copy.deepcopy(b); b2["seed"][0]["failure_classes"] = ["R6"]
        self.assertEqual(L.training_split_sha256(b2), base)
        for mutate in (lambda x: x["seed"][0].update(query="other"), lambda x: x["seed"][0].update(expected_top1_any=["z:GET:/q"]),
                       lambda x: x["regression_negative"][0].update(forbidden_top1=["z:GET:/q"]), lambda x: x["regression_negative"][0].update(no_answer=True),
                       lambda x: x["seed"].pop()):
            b3 = copy.deepcopy(b); mutate(b3)
            self.assertNotEqual(L.training_split_sha256(b3), base)

    def test_immutable_split_ignores_relabel_fields_only(self):
        b = _bench(); base = L.immutable_split_sha256(b)
        labels = {r["id"]: {"answerable": r["id"] == "rn-001", "acceptable_keys": ["c:DELETE:/p/{id}"] if r["id"] == "rn-001" else []}
                  for r in b["regression_negative"]}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["a" * 64] * 2, "adjudicated": False} for i in labels}
        relabeled = L.apply_labels(b, labels, mig)
        self.assertEqual(L.immutable_split_sha256(relabeled), base)                    # placement/expected/no_answer/legacy move: same
        self.assertNotEqual(L.training_split_sha256(relabeled), L.training_split_sha256(b))
        for mutate in (lambda x: x["seed"][0].update(query="other"), lambda x: x["seed"][0].update(expected_top1_any=["z:GET:/q"]),
                       lambda x: x["regression_negative"][0].update(query="other"), lambda x: x["regression_negative"].pop()):
            b2 = copy.deepcopy(b); mutate(b2)
            self.assertNotEqual(L.immutable_split_sha256(b2), base)

    def test_immutable_normalizations(self):
        """plan review 4 P1-3: active↔legacy forbidden and expected↔catalog_missing moves keep the projection; a changed union does not."""
        b = _bench(); base = L.immutable_split_sha256(b)
        r = copy.deepcopy(b); r["regression_negative"][0]["forbidden_top1"] = ["c:GET:/p"]
        r["regression_negative"][0]["legacy_forbidden_top1"] = ["c:DELETE:/p/{id}"]
        self.assertEqual(L.immutable_split_sha256(r), base)
        s = copy.deepcopy(b); s["seed"][0]["expected_top1_any"] = []; s["seed"][0]["catalog_missing_keys"] = ["a:GET:/x"]
        self.assertEqual(L.immutable_split_sha256(s), base)
        u = copy.deepcopy(r); u["regression_negative"][0]["legacy_forbidden_top1"] = ["c:DELETE:/other"]
        self.assertNotEqual(L.immutable_split_sha256(u), base)
        v = copy.deepcopy(s); v["seed"][0]["catalog_missing_keys"] = ["a:GET:/y"]
        self.assertNotEqual(L.immutable_split_sha256(v), base)

    def test_fixture_label_conflict_detected(self):
        b = _bench()
        for r in b["regression_negative"]:
            r["origin"] = "seed-r0"
        labels = {r["id"]: {"answerable": r["id"] == "rn-001", "acceptable_keys": ["c:DELETE:/p/{id}"] if r["id"] == "rn-001" else []}
                  for r in b["regression_negative"]}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels}
        self.assertEqual(L.fixture_label_conflicts(L.apply_labels(b, labels, mig)), ["rn-001"])
        labels["rn-001"] = {"answerable": True, "acceptable_keys": ["z:DELETE:/other"]}
        self.assertEqual(L.fixture_label_conflicts(L.apply_labels(b, labels, mig)), [])

    def test_label_provenance_required(self):
        b = _bench()
        labels = {r["id"]: {"answerable": False, "acceptable_keys": []} for r in b["regression_negative"]}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["a" * 64, "a" * 64], "adjudicated": False} for i in labels}   # equal outputs allowed
        out = L.apply_labels(b, labels, mig)
        self.assertEqual(L.label_provenance_problems(out), [])
        for bad in ({"reviewers": ["x", "x"], "review_output_sha256s": ["a" * 64, "b" * 64], "adjudicated": False},
                    {"reviewers": ["x", "y"], "review_output_sha256s": ["a" * 64, None], "adjudicated": False},
                    {"reviewers": ["x", "y", "z"], "review_output_sha256s": ["a" * 64] * 3, "adjudicated": False}):
            o2 = copy.deepcopy(out); o2["regression_negative"][0]["label_migration"] = bad
            self.assertTrue(L.label_provenance_problems(o2), bad)
        out["regression_negative"][0].pop("label_migration")
        self.assertTrue(L.label_provenance_problems(out))

    def test_promotion_payload_unchanged_by_relabel(self):
        plain = _plain(); b, payload = L.promote(_bench(), plain, _seal(plain))
        labels = {t["id"]: {"answerable": t["id"] == "rn-016", "acceptable_keys": ["a:DELETE:/z"] if t["id"] == "rn-016" else []} for t in L.relabel_targets(b)}
        mig = {i: {"reviewers": ["x", "y"], "review_output_sha256s": ["1", "2"], "adjudicated": False} for i in labels}
        self.assertEqual(L.promotion_payload_sha256(L.apply_labels(b, labels, mig)), payload["promotion_payload_sha256"])

    def test_committed_benchmark_labels(self):
        """Once H22 commits the relabel, the real benchmark satisfies the provenance schema and has no PR-8 conflict."""
        import json
        bench = json.loads((L.ROOT / "tests/benchmarks/search_queries.json").read_text(encoding="utf-8"))
        if "regression_positive" not in bench:
            self.skipTest("relabel not committed yet (before H22)")
        self.assertEqual(L.label_provenance_problems(bench), []); self.assertEqual(L.fixture_label_conflicts(bench), [])

    def test_reviewer_input_has_queries_only(self):
        txt = L.render_relabel_input([{"id": "rn-001", "query": "remove page 1"}], "PROMPT\n{RECORDS}\n")
        self.assertIn('"rn-001"', txt); self.assertIn("remove page 1", txt)
        self.assertNotIn("forbidden", txt); self.assertNotIn("expected", txt)


class TestCliWritesBenchFormat(unittest.TestCase):
    def test_promote_output_uses_the_benchmark_writer(self):
        """A CLI rewrite of search_queries.json keeps round_seal._write_bench's layout (one record per line), so H22 diffs stay additive."""
        import json, pathlib, tempfile
        from tests.benchmarks import round_seal as rs
        plain = _plain(); bench = {**_bench(), "held_out": [], "negative": [], "round5_seal": _seal(plain)}
        with tempfile.TemporaryDirectory() as td:
            b, pp, ref = pathlib.Path(td) / "b.json", pathlib.Path(td) / "p.json", pathlib.Path(td) / "ref.json"
            for f in (b, ref):
                f.write_text("{}\n", encoding="utf-8")
            rs._write_bench(b, bench); pp.write_text(json.dumps(plain), encoding="utf-8")
            self.assertEqual(L.main(["promote", "--bench", str(b), "--plain", str(pp), "--out", str(b)]), 0)
            rs._write_bench(ref, json.loads(b.read_text(encoding="utf-8")))
            self.assertEqual(b.read_text(encoding="utf-8"), ref.read_text(encoding="utf-8"))
