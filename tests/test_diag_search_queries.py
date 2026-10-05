"""tests/diag_search_queries.py against a temporary cache built from the fixtures (no skips; spec §9, P0-11)."""
import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from tests import diag_search_queries as diag
from tests.benchmarks import evaluator as ev
from tools.atlassian_docs import storage, sync
from tools.atlassian_docs.intelligence import RegistryManager

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "openapi"
SOURCES = ("jira-platform", "jira-software", "confluence")
FMT = "%Y-%m-%dT%H:%M:%SZ"
SEALED_COUNTS = {"held_out": 16, "negative": 8}


def assert_no_query_key(tc, obj):
    """Recursive exact-key check: a `query` key is forbidden anywhere; `query_sha256` is allowed (a substring test on the JSON would always trip on it)."""
    if isinstance(obj, dict):
        tc.assertNotIn("query", obj)
        for v in obj.values(): assert_no_query_key(tc, v)
    elif isinstance(obj, list):
        for v in obj: assert_no_query_key(tc, v)


def base_bench() -> dict:
    """Bundled bench reduced to what is independent of any round's hidden-set state: seed/regression_negative
    records with an r0 origin (their answers are in the fixtures), empty held_out/negative and only round1_seal (the
    tests rewrite its fingerprint; a later round's seal from the bundled bench is dropped)."""
    b = json.loads(diag.BENCH.read_text(encoding="utf-8"))
    for sect in ("seed", "regression_negative"):
        b[sect] = [r for r in b[sect] if r["origin"].endswith("-r0")]
    b["held_out"], b["negative"] = [], []
    for key in [k for k in b if k.startswith("round") and k.endswith("_seal") and k != "round1_seal"]:
        del b[key]
    return b


def build_fixture_cache(cache: pathlib.Path) -> None:
    with mock.patch.object(storage, "CACHE_DIR", cache):
        md = {}
        for s in SOURCES:
            spec = json.loads((FIXTURES / f"{s}-openapi.json").read_text(encoding="utf-8"))
            storage.write_cache_spec(s, spec)
            md[s] = {"sha256": storage.sha256_of_spec(spec), "api_version": "v3", "last_checked": "2026-09-30T00:00:00Z",
                     "last_updated": "2026-09-30T00:00:00Z", "resolved_documentation_url": "https://d/"}
        storage.write_metadata(md)


def fixture_identity(cache: pathlib.Path):
    with tempfile.TemporaryDirectory() as td:
        copy = pathlib.Path(td) / "c"
        shutil.copytree(cache, copy)
        with mock.patch.object(storage, "CACHE_DIR", copy):
            mgr = RegistryManager(sync_all=lambda force=False: [sync.SyncResult(s, "ok") for s in SOURCES])
            mgr.start()
            st = mgr.active
            return st.registry.fingerprint, {n: p.active_spec_sha256 for n, p in st.provenance.items()}


class TestDiagScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.tmp = pathlib.Path(cls._td.name)
        cls.cache = cls.tmp / "cache"
        build_fixture_cache(cls.cache)
        cls.fp, cls.spec_sha = fixture_identity(cls.cache)
        cls.bench = base_bench()
        cls.good_bench = cls.write_bench("good.json", cls.fp, cls.spec_sha)
        cls.bad_bench = cls.write_bench("bad.json", "0" * 64, cls.spec_sha)
        cls.bad_spec_bench = cls.write_bench("bad_spec.json", cls.fp, {**cls.spec_sha, "confluence": "f" * 64})
        cls.sealed_bench = cls.write_bench("sealed.json", cls.fp, cls.spec_sha,
                                            held_out=cls.sealed_section("held_out"),
                                            negative=cls.sealed_section("negative"))
        seed, reg = cls.bench["seed"], cls.bench["regression_negative"]
        cls.plain = {"held_out": [{**seed[i], "id": f"h-00{i + 1}", "origin": "held_out-r1"} for i in range(2)],
                     "negative": [{**reg[0], "id": "n-001", "origin": "negative-r1"}]}
        cls.plain_path = cls.tmp / "plain.json"
        cls.plain_path.write_text(json.dumps(cls.plain), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    @classmethod
    def write_bench(cls, name, fp, spec_sha, held_out=None, negative=None):
        b = json.loads(json.dumps(cls.bench))
        b["round1_seal"]["registry_fingerprint"], b["round1_seal"]["spec_sha256"] = fp, dict(spec_sha)
        if held_out is not None:
            b["held_out"] = held_out
        if negative is not None:
            b["negative"] = negative
        path = cls.tmp / name
        path.write_text(json.dumps(b), encoding="utf-8")
        return path

    @classmethod
    def sealed_section(cls, name):
        seal = cls.bench["round1_seal"]
        return {"sealed": True, "round": 1, "count": SEALED_COUNTS[name],
                "sha256": seal[f"{name}_sha256"], "distribution": seal[f"{name}_distribution"]}

    def run_diag(self, *args):
        with mock.patch("builtins.print"):
            return diag.run(["--cache-dir", str(self.cache), "--round", "1", *args])

    def test_cache_dir_is_used_and_restored(self):
        before = storage.CACHE_DIR
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--sets", "seed")
        self.assertIs(storage.CACHE_DIR, before)
        self.assertEqual(code, 0)
        self.assertEqual(rep["registry_fingerprint"], self.fp); self.assertEqual(rep["spec_sha256"], self.spec_sha)
        self.assertEqual(set(rep["sets"]), {"seed"})
        self.assertEqual(rep["sets"]["seed"]["passed"], len(self.bench["seed"]))   # fixtures carry every seed answer

    def test_seal_match_with_bench_file_exits_zero(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--sets", "seed,regression_negative")
        self.assertEqual(code, 0); self.assertTrue(rep["seal_match"])

    def test_seal_mismatch_without_hidden_sets_only_warns(self):
        code, rep = self.run_diag("--bench-file", str(self.bad_bench), "--sets", "seed")
        self.assertEqual(code, 0); self.assertFalse(rep["seal_match"]); self.assertIn("seed", rep["sets"])

    def assert_refused(self, bench_file, *extra):
        out = self.tmp / "refused.json"
        with mock.patch.object(ev, "evaluate", side_effect=AssertionError("evaluate called")) as spy:
            code, rep = self.run_diag("--bench-file", str(bench_file), "--bench", str(self.plain_path),
                                      "--json", str(out), *extra)
        spy.assert_not_called()
        self.assertEqual(code, 2); self.assertEqual(rep["sets"], {}); self.assertFalse(rep["seal_match"])
        self.assertNotIn("sealed_sha256", rep); self.assertFalse(out.exists())

    def test_seal_mismatch_with_bench_exits_two_without_evaluation(self):
        self.assert_refused(self.bad_bench)

    def test_seal_mismatch_with_bench_refuses_even_for_unsealed_sets_only(self):
        self.assert_refused(self.bad_bench, "--sets", "seed")

    def test_spec_sha_mismatch_alone_refuses(self):
        self.assert_refused(self.bad_spec_bench)
        self.assert_refused(self.bad_spec_bench, "--sets", "seed")

    def test_plaintext_bench_is_evaluated_and_hashed(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path))
        self.assertEqual(code, 0)
        self.assertEqual(set(rep["sets"]), {"seed", "regression_negative", "held_out", "negative"})
        self.assertEqual(rep["sets"]["held_out"]["total"], 2); self.assertEqual(rep["sets"]["negative"]["total"], 1)
        self.assertEqual(rep["sealed_sha256"], {"held_out": ev.canonical_sha256(self.plain["held_out"]),
                                                "negative": ev.canonical_sha256(self.plain["negative"])})

    def test_default_sets_skip_sealed_sections(self):
        # bench-file built here has held_out/negative as sealed metadata objects, independent of whatever
        # state the bundled tests/benchmarks/search_queries.json happens to be in.
        code, rep = self.run_diag("--bench-file", str(self.sealed_bench))
        self.assertEqual(code, 0); self.assertEqual(set(rep["sets"]), {"seed", "regression_negative"})
        code2, rep2 = self.run_diag("--bench-file", str(self.sealed_bench), "--sets", "held_out,negative")
        self.assertEqual(code2, 0)
        self.assertEqual(rep2["sets"]["held_out"], {"sealed": True, "count": SEALED_COUNTS["held_out"]})
        self.assertEqual(rep2["sets"]["negative"], {"sealed": True, "count": SEALED_COUNTS["negative"]})

    def test_default_sets_evaluate_plaintext_hidden_sections(self):
        # Symmetric case: a bench-file built here carries plaintext held_out/negative, so with default sets they
        # ARE evaluated and show up with passed/total. Runs against the temp fixture cache, never the real cache.
        path = self.write_bench("plain_hidden.json", self.fp, self.spec_sha,
                                held_out=self.plain["held_out"], negative=self.plain["negative"])
        code, rep = self.run_diag("--bench-file", str(path))
        self.assertEqual(code, 0)
        self.assertEqual(set(rep["sets"]), {"seed", "regression_negative", "held_out", "negative"})
        for name in ("held_out", "negative"):
            self.assertIn("passed", rep["sets"][name]); self.assertIn("total", rep["sets"][name])
            self.assertEqual(rep["sets"][name]["total"], len(self.plain[name]))

    def test_json_output_has_every_spec_field(self):
        out = self.tmp / "report.json"
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path), "--json", str(out))
        saved = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(saved, json.loads(json.dumps(rep)))
        for k in ("sets", "failures", "git_commit", "registry_fingerprint", "intelligence_fingerprint", "ranking_sha256",
                  "ranking_structure_sha256", "alias_sha256", "evaluation_code_sha256", "sealed_sha256", "spec_sha256", "run_at"):
            self.assertIn(k, saved)
        self.assertEqual(saved["evaluation_code_sha256"], ev.evaluation_code_sha256(diag.ROOT))

    def test_failures_carry_top5_with_signals(self):
        plain = {"held_out": [{**self.plain["held_out"][0], "expected_top1_any": ["nope:GET:/x"]}], "negative": []}
        p = self.tmp / "failing.json"; p.write_text(json.dumps(plain), encoding="utf-8")
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(p), "--sets", "held_out")
        self.assertEqual(code, 0); self.assertEqual(len(rep["failures"]), 1)
        f = rep["failures"][0]
        self.assertEqual(f["set"], "held_out"); self.assertTrue(1 <= len(f["top5"]) <= 5)
        self.assertEqual(set(f["top5"][0]), {"key", "score", "signals"})

    def test_round_selects_seal_key_and_reports_round(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--sets", "seed")
        self.assertEqual(rep["round"], 1); self.assertTrue(rep["seal_match"])
        with mock.patch("builtins.print"):
            code2, rep2 = diag.run(["--cache-dir", str(self.cache), "--round", "2", "--bench-file", str(self.good_bench), "--sets", "seed"])
        self.assertEqual(code2, 0); self.assertFalse(rep2["seal_match"])               # no round2_seal in this bench

    def test_plaintext_origin_must_match_round(self):
        plain = {"held_out": [{**self.plain["held_out"][0], "origin": "held_out-r2"}], "negative": []}
        p = self.tmp / "wrong_round.json"; p.write_text(json.dumps(plain), encoding="utf-8")
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(p), "--sets", "held_out")
        self.assertEqual(code, 2); self.assertEqual(rep["sets"], {})

    def test_round2_final_fields(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path))
        self.assertEqual(rep["held_out_top3"], {"passed": 2, "total": 2})
        for k in ("alias_sha256", "alias_candidates_sha256", "concept_lexicon_sha256"):
            self.assertIn(k, rep)
        for k in ("alias_candidates_sha256", "concept_lexicon_sha256"):
            path = diag.policy.DATA_DIR / f"{k[:-7]}.json"
            self.assertEqual(rep[k], ev.canonical_sha256(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None)
        code2, rep2 = self.run_diag("--bench-file", str(self.good_bench), "--sets", "seed")
        self.assertIsNone(rep2["held_out_top3"])

    def test_round3_report_fields_raw_effective_and_actionable_failures(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path))
        self.assertEqual(rep["evaluation_domain"], "actionable recommendation queries"); self.assertEqual(rep["policy_version"], 4)
        self.assertEqual(rep["tuning_grid_sha256"], ev.tuning_grid_sha256(json.loads((diag.policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))))
        for name in ("regression_negative", "negative"):
            self.assertEqual(set(rep["sets"][name]) >= {"passed", "raw_passed", "effective_passed", "actionable", "abstained"}, True, name)
        self.assertEqual(rep["negative_actionable"], rep["sets"]["negative"]["actionable"]); self.assertEqual(rep["negative_abstained"], rep["sets"]["negative"]["abstained"])
        plain = {"held_out": [{**self.plain["held_out"][0], "query": "issue attachment details"}], "negative": []}      # verb-less held_out fails as abstained
        p = self.tmp / "abstained.json"; p.write_text(json.dumps(plain), encoding="utf-8")
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(p), "--sets", "held_out")
        self.assertEqual(rep["sets"]["held_out"]["passed"], 0); self.assertEqual(rep["failures"][0]["actionable"], False); self.assertTrue(rep["failures"][0]["raw_ok"])
        self.assertNotIn("query", rep["failures"][0]); self.assertEqual(rep["failures"][0]["query_sha256"], ev.canonical_sha256(plain["held_out"][0]["query"]))   # hidden failures never carry the text
        self.assertNotIn("query", rep["sets"]["held_out"]["failed"][0]); assert_no_query_key(self, rep["sets"]["held_out"]); assert_no_query_key(self, rep["failures"])
        self.assertEqual(set(rep["failures"][0]["top5"][0]["signals"]) >= {"method_order", "path_coverage"}, True)

    def test_reference_block_is_appended_once_and_only_to_the_current_artifact(self):
        out = self.tmp / "final.json"
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path), "--json", str(out))
        ref = {"held_out": [self.plain["held_out"][0], {**self.plain["held_out"][0], "id": "h-098", "query": "issue attachment details"},                 # valid keys, verb-less → fails
                            {**self.plain["held_out"][0], "id": "h-099", "expected_top1_any": ["nope:GET:/x"]}], "negative": list(self.plain["negative"])}
        rp = self.tmp / "ref.json"; rp.write_text(json.dumps(ref), encoding="utf-8")
        code, _ = self.run_diag("--bench-file", str(self.good_bench), "--reference", str(rp), "--reference-round", "1", "--append-to", str(out))
        self.assertEqual(code, 0)
        art = json.loads(out.read_text(encoding="utf-8")); blk = art["reference_round1"]
        self.assertEqual(blk["invalid_key"], [{"id": "h-099", "keys": ["nope:GET:/x"]}]); self.assertEqual(blk["held_out"]["total"], 2); self.assertEqual(blk["held_out"]["passed"], 1)
        fail = blk["held_out"]["failed"][0]; self.assertEqual(fail["id"], "h-098"); self.assertNotIn("query", fail)                     # reference failures are sanitized too
        self.assertEqual(fail["query_sha256"], ev.canonical_sha256("issue attachment details")); assert_no_query_key(self, blk)
        self.assertEqual(set(blk["negative"]) >= {"raw_passed", "effective_passed"}, True); self.assertEqual(set(blk["plaintext_sha256"]), {"held_out", "negative"})
        self.assertEqual(art["sets"], rep["sets"])                                                                  # current-round results untouched
        code2, _ = self.run_diag("--bench-file", str(self.good_bench), "--reference", str(rp), "--reference-round", "1", "--append-to", str(out))
        self.assertEqual(code2, 2)                                                                                  # second append refused
