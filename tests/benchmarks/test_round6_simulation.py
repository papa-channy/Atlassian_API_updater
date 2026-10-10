import hashlib, json, pathlib, subprocess, tempfile, types, unittest
from unittest import mock
from tests.benchmarks import round6_simulation as sim, evaluator as ev


class TestRound6CounterexampleReference(unittest.TestCase):
    def test_counterexample_reference_problems(self):
        """Round 6 plan PR-6: the reference binds the H alias policy (aliases-h.json) and the registry; consistency hashes kept."""
        from tests.benchmarks import counterexample as cx
        with tempfile.TemporaryDirectory() as td:
            w = pathlib.Path(td)
            (w / "aliases-h.json").write_text("{}\n")
            pol = {"aliases": {"ticket": ["issue"]}, "rules": [], "notes": {}}
            cmap = {json.dumps(list(k)): list(v) for k, v in cx.canonical_policy_map(pol).items()}
            good = {"policy": pol, "policy_canonical_sha256": ev.canonical_sha256(pol), "canonical_policy_map": cmap, "canonical_policy_map_sha256": ev.canonical_sha256(cmap),
                    "titles": [], "titles_sha256": ev.canonical_sha256([]),
                    "inputs": {"aliases_h_sha256": ev.file_sha256(w / "aliases-h.json"), "registry_fingerprint": "fp"}}
            self.assertEqual(sim.INPUT_SHA256, {})
            self.assertEqual(sim.counterexample_reference_problems(good, w, "fp"), [])
            extra = json.loads(json.dumps(good)); extra["inputs"]["aliases_premerge_sha256"] = "x"
            self.assertTrue(sim.counterexample_reference_problems(extra, w, "fp"))
            wrong_map = json.loads(json.dumps(good)); wrong_map["canonical_policy_map"] = {}
            self.assertTrue(sim.counterexample_reference_problems(wrong_map, w, "fp"))
            self.assertTrue(sim.counterexample_reference_problems(good, w, "other-fp"))
            (w / "aliases-h.json").write_text("{\"changed\": 1}\n")
            self.assertTrue(sim.counterexample_reference_problems(good, w, "fp"))


class TestRound6PreT(unittest.TestCase):
    M_OK = {"wv": 0, "fr": 0, "ir": 0, "sr3": 55, "src": 50, "srk": 50, "rp3": 3, "rpk": 2, "nab": 19, "n_seed": 55, "n_rp": 3, "n_rn": 19,
            "n_seed_elig": 50, "n_rp_elig": 2}                                       # spec v1.7 eligible denominators

    def _result(self, m, scorer_ok=True, errors=(), fixture_final=(), cx=None):
        r = types.SimpleNamespace(metrics=m, scorer_rule={"ok": scorer_ok, "losses": 0, "eligible": 600}, validation_errors=list(errors),
                                  fixture_result={"final": list(fixture_final), "constants": []}, counterexample_result=cx,
                                  tuning_accept=sim.tune.tuning_accept_r6(m, list(fixture_final), cx, {"ok": scorer_ok}, list(errors)))
        return r

    def test_metric_violations_name_item_value_bound(self):
        v = sim.metric_violations({**self.M_OK, "wv": 1, "srk": 40, "ir": 1})
        self.assertEqual([x["item"] for x in v], ["wv", "ir", "srk"])
        self.assertEqual(v[0], {"item": "wv", "value": 1, "bound": "== 0"})

    def test_blockers(self):
        self.assertEqual(sim.pre_t_blockers_r6(self._result(self.M_OK), {"pass": True}, []), [])
        kinds = lambda r, eq=(): [b["kind"] for b in sim.pre_t_blockers_r6(r, {"pass": True}, list(eq))]
        self.assertEqual(kinds(self._result({**self.M_OK, "wv": 1})), ["metric_threshold"])
        self.assertEqual(kinds(self._result(self.M_OK, scorer_ok=False)), ["scorer_rule_violation"])
        self.assertEqual(kinds(self._result(self.M_OK, fixture_final=["s-001"])), ["fixture_fail"])
        self.assertEqual(kinds(self._result(self.M_OK), eq=[{"point": {}, "query": "q"}]), ["equivalence_mismatch"])

    def test_seeded_work_satisfies_pre_t_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            real, tmp = pathlib.Path(td) / "W", pathlib.Path(td) / "T"
            (real / "inputs/round4").mkdir(parents=True)
            (real / "aliases-h.json").write_text("{}", encoding="utf-8"); (real / "inputs/round4/doc-titles-snapshot.json").write_text("{}", encoding="utf-8")
            events = [{"event": "scorer_rule_corpus_pinned", "corpus_sha256": "c", "registry_fingerprint": "f"},
                      {"event": "relabel_applied", "training_split_sha256": "s", "immutable_split_sha256": "i"}, {"event": "promotion_sealed", "promotion_payload_sha256": "p"},
                      {"event": "other"}]
            (real / "controller-events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            self.assertEqual(sim.load_pre_t_evidence(tmp)[1] != [], True)                  # empty temp work: evidence missing
            sim.seed_rehearsal_work(real, tmp)
            got, probs = sim.load_pre_t_evidence(tmp)
            self.assertEqual(probs, []); self.assertEqual(got["relabel_applied"]["training_split_sha256"], "s")
            (real / "aliases-h.json").unlink()
            with self.assertRaises(SystemExit):
                sim.seed_rehearsal_work(real, pathlib.Path(td) / "T2")

    def test_relabel_chain(self):
        s1, s2, i1, h = "1" * 64, "2" * 64, "3" * 64, "4" * 64
        a = {"event": "relabel_applied", "training_split_sha256": s1, "immutable_split_sha256": i1}
        ruling = {"event": "relabel_rerun_ruling", "from_training_split_sha256": s1, "immutable_split_sha256": i1, "reason": "r",
                  "thread": sim.REVIEW_THREAD, "review_output_sha256": h}
        ok_b = {"event": "relabel_applied", "training_split_sha256": s2, "immutable_split_sha256": i1}
        for bad in ({"thread": "t"}, {"reason": " "}, {"review_output_sha256": "h"}):                   # value formats (plan review 4 P1-1)
            self.assertTrue(sim.relabel_chain_problems([a, {**ruling, **bad}, ok_b]), bad)
        self.assertEqual(sim.relabel_chain_problems([a]), [])
        self.assertEqual(sim.relabel_chain_problems([a, ruling, ok_b]), [])
        self.assertTrue(sim.relabel_chain_problems([a, ok_b]))                                          # no ruling
        self.assertTrue(sim.relabel_chain_problems([a, {"event": "relabel_rerun_ruling"}, ok_b]))       # malformed ruling
        self.assertTrue(sim.relabel_chain_problems([a, {**ruling, "from_training_split_sha256": "0" * 64}, ok_b]))   # wrong generation
        self.assertTrue(sim.relabel_chain_problems([a, ruling, {**ok_b, "immutable_split_sha256": "5" * 64}]))       # seed/query drift

    def test_rehearsal_seed_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(sim, "seed_rehearsal_work", side_effect=SystemExit("boom")), \
                mock.patch.object(sim, "_run_in_tree") as run_in_tree, mock.patch.object(sim.subprocess, "run") as sp_run:
            sp_run.return_value = types.SimpleNamespace(stdout=b"", returncode=0)
            W = pathlib.Path(td) / "W"
            code = sim.run_rehearsal(pathlib.Path(td) / "S", W)
            report = [json.loads(l) for l in (W / "controller-events.jsonl").read_text(encoding="utf-8").splitlines()][-1]
        self.assertEqual(code, 1); run_in_tree.assert_not_called()
        self.assertEqual(report["steps"][0]["exit"], 1)
        self.assertEqual(report["steps"][0]["output_sha256"], hashlib.sha256(b"boom").hexdigest()); self.assertGreaterEqual(report["failures"], 1)

    def test_rehearsal_never_writes_the_working_tree(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=sim.ROOT, capture_output=True, text=True).stdout
        with mock.patch.object(sim, "_run_in_tree", return_value=(0, "ok")) as run_in_tree:
            with tempfile.TemporaryDirectory() as td:
                code = sim.run_rehearsal(pathlib.Path(td) / "S", pathlib.Path(td) / "W", dry=True)
        self.assertEqual(code, 0)
        self.assertTrue(all(str(sim.ROOT) not in str(c.args[0]) for c in run_in_tree.call_args_list))   # every command ran in the temp tree
        self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=sim.ROOT, capture_output=True, text=True).stdout, before)
