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
        cls.bench = json.loads(diag.BENCH.read_text(encoding="utf-8"))
        cls.good_bench = cls.write_bench("good.json", cls.fp, cls.spec_sha)
        cls.bad_bench = cls.write_bench("bad.json", "0" * 64, cls.spec_sha)
        seed, reg = cls.bench["seed"], cls.bench["regression_negative"]
        cls.plain = {"held_out": [{**seed[i], "id": f"h-00{i + 1}", "origin": "held_out-r1"} for i in range(2)],
                     "negative": [{**reg[0], "id": "n-001", "origin": "negative-r1"}]}
        cls.plain_path = cls.tmp / "plain.json"
        cls.plain_path.write_text(json.dumps(cls.plain), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    @classmethod
    def write_bench(cls, name, fp, spec_sha):
        b = json.loads(json.dumps(cls.bench))
        b["round1_seal"]["registry_fingerprint"], b["round1_seal"]["spec_sha256"] = fp, dict(spec_sha)
        path = cls.tmp / name
        path.write_text(json.dumps(b), encoding="utf-8")
        return path

    def run_diag(self, *args):
        with mock.patch("builtins.print"):
            return diag.run(["--cache-dir", str(self.cache), *args])

    def test_cache_dir_is_used_and_restored(self):
        before = storage.CACHE_DIR
        code, rep = self.run_diag("--sets", "seed")
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

    def test_seal_mismatch_with_bench_exits_two_without_evaluation(self):
        code, rep = self.run_diag("--bench-file", str(self.bad_bench), "--bench", str(self.plain_path))
        self.assertEqual(code, 2); self.assertEqual(rep["sets"], {}); self.assertFalse(rep["seal_match"])
        self.assertNotIn("sealed_sha256", rep)

    def test_plaintext_bench_is_evaluated_and_hashed(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench), "--bench", str(self.plain_path))
        self.assertEqual(code, 0)
        self.assertEqual(set(rep["sets"]), {"seed", "regression_negative", "held_out", "negative"})
        self.assertEqual(rep["sets"]["held_out"]["total"], 2); self.assertEqual(rep["sets"]["negative"]["total"], 1)
        self.assertEqual(rep["sealed_sha256"], {"held_out": ev.canonical_sha256(self.plain["held_out"]),
                                                "negative": ev.canonical_sha256(self.plain["negative"])})

    def test_default_sets_skip_sealed_sections(self):
        code, rep = self.run_diag("--bench-file", str(self.good_bench))
        self.assertEqual(code, 0); self.assertEqual(set(rep["sets"]), {"seed", "regression_negative"})

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
