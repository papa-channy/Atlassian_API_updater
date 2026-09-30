import datetime
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tests.intelligence.helpers import load_fixture
from tools.atlassian_docs import storage, sync
from tools.atlassian_docs.intelligence import lastgood, manager, registry, search

NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=datetime.timezone.utc)
FMT = sync.TIMESTAMP_FORMAT


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


class Harness(unittest.TestCase):
    """Real storage under a temp CACHE_DIR; sync replaced by a controllable fake."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(storage, "CACHE_DIR", pathlib.Path(self.tmp.name) / ".atlassian-docs"); p.start(); self.addCleanup(p.stop)
        self.clock = FakeClock()
        self.sync_calls = 0
        self.sync_behaviour = "ok"  # "ok" | "fail" | "raise" | "metadata_error"

    def write_cache(self, source, spec, checked=NOW):
        storage.write_cache_spec(source, spec)
        md = storage.read_metadata()
        md[source] = {"sha256": storage.sha256_of_spec(spec), "api_version": "v3", "last_checked": checked.strftime(FMT),
                      "last_updated": checked.strftime(FMT), "resolved_documentation_url": "https://d/"}
        storage.write_metadata(md)

    def fake_sync(self, force=False):
        self.sync_calls += 1
        if self.sync_behaviour == "raise":
            raise OSError("network down")
        results = [sync.SyncResult(s, "ok") for s in ("jira-platform", "jira-software", "confluence")]
        if self.sync_behaviour == "fail":
            results[0] = sync.SyncResult("jira-platform", "warn_fallback", message="boom")
        if self.sync_behaviour == "metadata_error":
            raise sync.MetadataPersistenceError("disk", results)
        return results

    def make(self):
        m = manager.RegistryManager(sync_all=self.fake_sync, clock=self.clock, now=lambda: NOW)
        m.start()
        return m


class TestStartup(Harness):
    def test_cache_first_no_network(self):
        self.write_cache("confluence", load_fixture("confluence"))
        m = self.make()
        self.assertEqual(self.sync_calls, 0)
        self.assertEqual(m.active.provenance["confluence"].status, "fresh")
        self.assertEqual(m.active.provenance["jira-platform"].status, "unavailable")
        self.assertTrue(lastgood.last_good_path("confluence").exists())

    def test_ttl_expired_still_no_network_at_startup(self):
        self.write_cache("confluence", load_fixture("confluence"), checked=NOW - datetime.timedelta(hours=30))
        m = self.make()
        self.assertEqual(self.sync_calls, 0)
        self.assertEqual(m.active.provenance["confluence"].reason, "ttl_expired")

    def test_no_cache_triggers_single_sync_then_unavailable_error(self):
        with self.assertRaises(registry.RegistryUnavailableError):
            self.make()
        self.assertEqual(self.sync_calls, 1)

    def test_no_cache_sync_populates(self):
        def sync_and_write(force=False):
            self.write_cache("confluence", load_fixture("confluence")); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        self.assertIn("confluence", m.active.registry.sources)

    def test_incompatible_cache_falls_back_to_last_good(self):
        self.write_cache("confluence", load_fixture("confluence"))
        self.make()  # writes last-good
        self.write_cache("confluence", load_fixture("unsupported-dialect"))
        m = self.make()
        p = m.active.provenance["confluence"]
        self.assertEqual((p.status, p.reason), ("stale", "served_from_last_good"))
        self.assertEqual(p.candidate["rejected_reason"], "incompatible_dialect")
        self.assertGreater(p.operation_count, 0)

    def test_non_dict_metadata_is_tolerated(self):
        self.write_cache("confluence", load_fixture("confluence"))
        m = manager.RegistryManager(sync_all=self.fake_sync, read_metadata=lambda: [], clock=self.clock, now=lambda: NOW)
        m.start()
        self.assertIn("confluence", m.active.registry.sources)
        self.assertEqual(self.sync_calls, 0)

    def test_startup_from_last_good_only(self):  # AC-26
        lastgood.write_last_good("confluence", load_fixture("confluence"))
        m = self.make()
        self.assertEqual(self.sync_calls, 0)
        p = m.active.provenance["confluence"]
        self.assertEqual((p.status, p.reason), ("stale", "served_from_last_good"))


class TestRefresh(Harness):
    def setUp(self):
        super().setUp()
        self.write_cache("confluence", load_fixture("confluence"), checked=NOW - datetime.timedelta(hours=30))

    def test_ensure_fresh_syncs_and_rebuilds_on_sha_change(self):
        m = self.make(); before = m.active.registry.fingerprint
        new = load_fixture("confluence"); new["paths"]["/zzz-new"] = {"get": {"operationId": "zzzNew", "summary": "brand new op", "responses": {}}}
        def sync_and_write(force=False):
            self.write_cache("confluence", new); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        m.ensure_fresh()
        self.assertEqual(self.sync_calls, 1)
        self.assertNotEqual(m.active.registry.fingerprint, before)
        self.assertIsNotNone(m.active.registry.get_operation("confluence:GET:/zzz-new"))
        self.assertEqual(lastgood.last_good_sha("confluence"), storage.sha256_of_spec(new))
        self.assertEqual(m.active.provenance["confluence"].status, "fresh")

    def test_unchanged_sha_reuses_source_registry(self):
        m = self.make(); sr = m.active.registry.sources["confluence"]
        self.write_cache("confluence", load_fixture("confluence"))  # same content, fresh metadata
        m.refresh()
        self.assertIs(m.active.registry.sources["confluence"], sr)

    def test_failed_refresh_backoff_only_after_failure(self):
        self.sync_behaviour = "raise"
        m = self.make()
        m.ensure_fresh(); m.ensure_fresh()
        self.assertEqual(self.sync_calls, 1)
        self.assertTrue(m.backoff_active)
        self.assertEqual(m.active.provenance["confluence"].reason, "refresh_failed")
        self.clock.t += 901
        m.ensure_fresh()
        self.assertEqual(self.sync_calls, 2)
        self.sync_behaviour = "ok"; self.clock.t += 901
        self.write_cache("confluence", load_fixture("confluence"))
        m.refresh()   # ensure_fresh would short-circuit: the rewritten metadata is already fresh
        self.assertFalse(m.backoff_active)
        self.assertEqual(m.active.provenance["confluence"].status, "fresh")

    def test_warn_fallback_counts_as_failed(self):
        self.write_cache("jira-platform", load_fixture("jira-platform"), checked=NOW - datetime.timedelta(hours=30))
        self.sync_behaviour = "fail"
        m = self.make(); m.ensure_fresh()
        self.assertTrue(m.backoff_active)
        self.assertEqual(m.active.provenance["jira-platform"].reason, "refresh_failed")
        self.assertNotEqual(m.active.provenance["confluence"].reason, "refresh_failed")

    def test_unreadable_cache_does_not_break_ensure_fresh(self):
        state = {"broken": False}
        def reader(source):
            if state["broken"] and source == "confluence":
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
            return storage.read_cache_spec(source)
        m = manager.RegistryManager(sync_all=self.fake_sync, read_cache_spec=reader, clock=self.clock, now=lambda: NOW)
        m.start()
        state["broken"] = True
        m.ensure_fresh()
        self.assertIn("confluence", m.active.registry.sources)
        self.assertTrue(any(w["kind"] == "cache_read_failed" for w in m.active.provenance["confluence"].warnings))

    def test_ensure_fresh_never_raises_and_refresh_reports_failed(self):
        m = self.make(); before = m.active
        def boom(): raise AttributeError("kaboom")
        m._rebuild = lambda **kw: boom()
        m.ensure_fresh()
        self.assertIs(m.active, before)
        self.assertTrue(m.backoff_active)
        self.clock.t += 901
        out = m.refresh()
        self.assertEqual(out["status"], "failed")
        self.assertIn("kaboom", out["error"])

    def test_metadata_persistence_error_counts_as_failed_refresh(self):
        self.sync_behaviour = "metadata_error"
        m = self.make(); m.ensure_fresh()
        self.assertTrue(m.backoff_active)
        self.assertIn("confluence", m.active.registry.sources)

    def test_gate_failure_keeps_previous_and_does_not_recheck_same_sha(self):
        m = self.make(); before = m.active.registry.sources["confluence"]
        bad = load_fixture("unsupported-dialect")
        def sync_and_write(force=False):
            self.write_cache("confluence", bad); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        m.ensure_fresh()
        p = m.active.provenance["confluence"]
        self.assertEqual((p.status, p.reason), ("stale", "incompatible_dialect"))
        self.assertEqual(p.active_spec_sha256, before.spec_sha256)
        self.assertEqual(p.observed_cache_sha256, storage.sha256_of_spec(bad))
        with mock.patch("tools.atlassian_docs.intelligence.manager.gate.build_candidate", wraps=manager.gate.build_candidate) as bc:
            m.refresh()
            self.assertEqual(bc.call_count, 0)  # same rejected sha skipped

    def test_unavailable_source_recovers_at_runtime(self):
        m = self.make()
        self.assertEqual(m.active.provenance["jira-platform"].status, "unavailable")
        def sync_and_write(force=False):
            self.write_cache("jira-platform", load_fixture("jira-platform")); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        self.assertTrue(m.needs_refresh("jira-platform"))
        m.ensure_fresh()
        self.assertEqual(m.active.provenance["jira-platform"].status, "fresh")

    def test_refresh_tool_semantics(self):
        m = self.make()
        out = m.refresh()
        self.assertEqual(out["status"], "completed"); self.assertIn("registry_rebuilt", out)
        m._lock.acquire()
        try:
            self.assertEqual(m.refresh(), {"status": "refresh_in_progress"})
            n = self.sync_calls
            m.ensure_fresh()  # lock busy -> silently keep current
            self.assertEqual(self.sync_calls, n)
        finally:
            m._lock.release()

    def test_state_snapshot_is_consistent(self):
        orig_sha = storage.sha256_of_spec(load_fixture("confluence"))
        new = load_fixture("confluence"); new["paths"]["/zzz-snap"] = {"get": {"operationId": "zzzSnap", "responses": {}}}
        def sync_and_write(force=False):
            self.write_cache("confluence", new); return self.fake_sync(force)
        m = manager.RegistryManager(sync_all=sync_and_write, clock=self.clock, now=lambda: NOW); m.start()
        before = m.active
        m.ensure_fresh()
        after = m.active
        self.assertIsNot(after, before)
        self.assertNotEqual(before.registry.fingerprint, after.registry.fingerprint)
        self.assertEqual(before.provenance["confluence"].active_spec_sha256, before.registry.sources["confluence"].spec_sha256)
        self.assertEqual(after.provenance["confluence"].active_spec_sha256, after.registry.sources["confluence"].spec_sha256)
        self.assertEqual(before.registry.sources["confluence"].spec_sha256, orig_sha)

    def test_refresh_bypasses_backoff(self):
        self.sync_behaviour = "raise"
        m = self.make()
        m.ensure_fresh()
        self.assertEqual(self.sync_calls, 1)
        self.assertTrue(m.backoff_active)
        m.refresh()
        self.assertEqual(self.sync_calls, 2)

    def test_rejected_then_accepted_then_rejected_again_keeps_record(self):
        a = load_fixture("unsupported-dialect")
        b = load_fixture("confluence"); b["paths"]["/zzz-b"] = {"get": {"operationId": "zzzB", "responses": {}}}
        m = self.make()
        for spec in (a, b, a):
            self.write_cache("confluence", spec)
            m.refresh()
        p = m.active.provenance["confluence"]
        self.assertEqual((p.status, p.reason), ("stale", "incompatible_dialect"))
        self.assertEqual(p.candidate["sha256"], storage.sha256_of_spec(a))
        self.assertEqual(p.active_spec_sha256, storage.sha256_of_spec(b))

    def test_last_good_write_failure_does_not_block_swap(self):
        def boom(source, spec): raise OSError("disk full")
        m = manager.RegistryManager(sync_all=self.fake_sync, write_last_good=boom, clock=self.clock, now=lambda: NOW); m.start()
        self.assertIn("confluence", m.active.registry.sources)
        self.assertTrue(any(w["kind"] == "last_good_write_failed" for w in m.active.provenance["confluence"].warnings))

    def test_rejected_cache_does_not_refresh_every_call(self):
        self.write_cache("confluence", load_fixture("confluence"))                      # make setUp's stale cache fresh
        self.write_cache("jira-software", load_fixture("jira-software"))                # otherwise uncached -> always refreshes
        self.write_cache("jira-platform", load_fixture("unsupported-dialect"))          # fresh metadata, rejected by gate
        m = self.make()
        self.assertEqual(m.active.provenance["jira-platform"].status, "unavailable")
        self.sync_calls = 0
        before = (storage.CACHE_DIR / "metadata.json").stat().st_mtime_ns
        for _ in range(5):
            m.ensure_fresh()
        self.assertEqual(self.sync_calls, 0)
        self.assertEqual((storage.CACHE_DIR / "metadata.json").stat().st_mtime_ns, before)
        with mock.patch.object(m, "_now", return_value=NOW + datetime.timedelta(hours=25)):
            m.ensure_fresh()
        self.assertEqual(self.sync_calls, 1)
