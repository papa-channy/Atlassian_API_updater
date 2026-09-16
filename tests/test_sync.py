import datetime
import json
import pathlib
import tempfile
import urllib.error
import unittest
from unittest import mock

from tools.atlassian_docs import extractor, sources, storage, sync


class TestDetectApiVersion(unittest.TestCase):
    def test_detects_v3_segment(self):
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/jira/platform/rest/v3/"
        )
        self.assertEqual(version, "v3")
        self.assertEqual(source, "documentation_url")

    def test_detects_v2_segment(self):
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/confluence/rest/v2/"
        )
        self.assertEqual(version, "v2")
        self.assertEqual(source, "documentation_url")

    def test_returns_null_when_no_version_segment(self):
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/jira/software/rest/"
        )
        self.assertIsNone(version)
        self.assertIsNone(source)

    def test_does_not_match_non_version_path_segment(self):
        # Jira Software's real shape: /rest/agile/1.0/... must NOT match.
        version, source = sync.detect_api_version(
            "https://developer.atlassian.com/cloud/jira/software/rest/agile/1.0/"
        )
        self.assertIsNone(version)
        self.assertIsNone(source)

    def test_ignores_version_looking_segments_outside_rest_path(self):
        version, _ = sync.detect_api_version(
            "https://developer.atlassian.com/v3/cloud/jira/software/rest/"
        )
        self.assertIsNone(version)


class TestFetchDocumentationHtml(unittest.TestCase):
    def _fake_response(self, url, body):
        response = mock.MagicMock()
        response.geturl.return_value = url
        response.read.return_value = body.encode("utf-8")
        response.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    def test_returns_resolved_url_and_html_on_success(self):
        fake_response = self._fake_response("https://example.com/final/", "<html>ok</html>")
        with mock.patch(
            "tools.atlassian_docs.sync.urllib.request.urlopen", return_value=fake_response
        ):
            resolved_url, html = sync.fetch_documentation_html("https://example.com/start/")
        self.assertEqual(resolved_url, "https://example.com/final/")
        self.assertEqual(html, "<html>ok</html>")

    def test_wraps_url_error_as_fetch_error(self):
        with mock.patch(
            "tools.atlassian_docs.sync.urllib.request.urlopen",
            side_effect=urllib.error.URLError("boom"),
        ):
            with self.assertRaises(sync.FetchError):
                sync.fetch_documentation_html("https://example.com/start/")

    def test_wraps_timeout_as_fetch_error(self):
        with mock.patch(
            "tools.atlassian_docs.sync.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            with self.assertRaises(sync.FetchError):
                sync.fetch_documentation_html("https://example.com/start/")


SPEC_V1 = {"openapi": "3.0.1", "info": {"title": "X", "version": "1"}, "paths": {"/a": {}}}
SPEC_V2 = {"openapi": "3.0.1", "info": {"title": "X", "version": "2"}, "paths": {"/a": {}, "/b": {}}}


class SyncSourceTestCase(unittest.TestCase):
    """Shared setup: an isolated cache dir, and a helper to seed it."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patcher = mock.patch.object(
            storage, "CACHE_DIR", pathlib.Path(self._tmpdir.name) / ".atlassian-docs"
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def _seed_consistent_cache(self, source_name, spec, last_checked_iso):
        storage.write_cache_spec(source_name, spec)
        metadata = {
            source_name: {
                "resolved_documentation_url": "https://developer.atlassian.com/cloud/x/rest/v1/",
                "extraction_method": "embedded_window_data",
                "api_version": "v1",
                "api_version_source": "documentation_url",
                "spec_info_version": "1",
                "last_checked": last_checked_iso,
                "last_updated": last_checked_iso,
                "sha256": storage.sha256_of_spec(spec),
            }
        }
        return metadata

    def _fresh_timestamp(self):
        return sync._now_iso()

    def _stale_timestamp(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
        return past.strftime(sync._TIMESTAMP_FORMAT)


class TestSyncSourceCacheHit(SyncSourceTestCase):
    def test_uses_cache_without_fetching_when_ttl_valid_and_consistent(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._fresh_timestamp())
        with mock.patch("tools.atlassian_docs.sync.fetch_documentation_html") as fake_fetch:
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        fake_fetch.assert_not_called()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.api_version, "v1")

    def test_force_ignores_fresh_ttl_and_fetches_anyway(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._fresh_timestamp())
        html = "<script>window.__DATA__ = " + json.dumps(SPEC_V1) + ";</script>"
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v1/", html),
        ) as fake_fetch:
            sync.sync_source("jira-platform", "https://x/", metadata, force=True)
        fake_fetch.assert_called_once()


class TestSyncSourceRefresh(SyncSourceTestCase):
    def _html_for(self, spec):
        return "<script>window.__DATA__ = " + json.dumps(spec) + ";</script>"

    def test_refetches_when_ttl_expired_and_marks_ok_if_unchanged(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v1/", self._html_for(SPEC_V1)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "ok")
        # unchanged -> not rewritten, so the cache file still holds exactly
        # what was seeded (it is never deleted or blanked):
        self.assertEqual(storage.read_cache_spec("jira-platform"), SPEC_V1)

    def test_marks_updated_when_spec_content_changes(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v1/", self._html_for(SPEC_V2)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "updated")
        self.assertEqual(storage.read_cache_spec("jira-platform"), SPEC_V2)
        self.assertEqual(metadata["jira-platform"]["sha256"], storage.sha256_of_spec(SPEC_V2))

    def test_marks_version_changed_when_both_versions_are_non_null_and_differ(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v4/", self._html_for(SPEC_V2)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "version_changed")
        self.assertEqual(result.previous_api_version, "v1")
        self.assertEqual(result.api_version, "v4")

    def test_does_not_flag_version_change_when_previous_is_null(self):
        metadata = {}  # first run, no prior metadata for this source
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v3/", self._html_for(SPEC_V1)),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "updated")  # not "version_changed"
        self.assertEqual(result.api_version, "v3")


class TestSyncSourceFailurePolicy(SyncSourceTestCase):
    def test_falls_back_on_fetch_error_when_cache_is_valid(self):
        stale = self._stale_timestamp()
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, stale)
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("network down"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "warn_fallback")
        # last_checked must NOT be updated on failure (AC-23):
        self.assertEqual(metadata["jira-platform"]["last_checked"], stale)

    def test_falls_back_on_extraction_error_when_cache_is_valid(self):
        metadata = self._seed_consistent_cache("jira-platform", SPEC_V1, self._stale_timestamp())
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://x/rest/", "<html>no marker here</html>"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "warn_fallback")

    def test_unavailable_when_fetch_fails_and_no_cache_exists(self):
        metadata = {}
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("network down"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "error_unavailable")

    def test_unavailable_when_fetch_fails_and_local_cache_is_corrupt(self):
        storage.ensure_cache_dir()
        storage.cache_path("jira-platform").write_text("not json", encoding="utf-8")
        metadata = {"jira-platform": {"sha256": "irrelevant", "last_checked": self._stale_timestamp()}}
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("network down"),
        ):
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        self.assertEqual(result.status, "error_unavailable")


class TestSyncSourceSelfHeal(SyncSourceTestCase):
    def test_mismatched_but_structurally_valid_cache_is_still_a_usable_fallback(self):
        # Simulate the crash-recovery scenario from spec §22: cache file
        # on disk doesn't match metadata.sha256 (as if metadata write was
        # interrupted), but the cache file itself is valid JSON+OpenAPI.
        storage.write_cache_spec("jira-platform", SPEC_V1)
        metadata = {
            "jira-platform": {
                "sha256": "0" * 64,  # deliberately wrong, forces a mismatch
                "last_checked": self._fresh_timestamp(),  # even though "fresh"...
                "api_version": "v1",
            }
        }
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html"
        ) as fake_fetch:
            fake_fetch.side_effect = sync.FetchError("network down")
            result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        # mismatch must have skipped the TTL fast-path (fetch was attempted):
        fake_fetch.assert_called_once()
        # and since the cache itself is structurally valid, it's a usable fallback:
        self.assertEqual(result.status, "warn_fallback")

    def test_mismatch_recovery_skips_cache_rewrite_when_content_is_actually_unchanged(self):
        # The on-disk cache already holds SPEC_V1 (this is the "true"
        # content). metadata.sha256 is wrong (simulating an interrupted
        # metadata write), so the TTL fast-path is skipped and a remote
        # fetch is attempted — and the remote happens to return the exact
        # same SPEC_V1. There is nothing to rewrite; only metadata.sha256
        # needs correcting.
        storage.write_cache_spec("jira-platform", SPEC_V1)
        old_last_updated = "2020-01-01T00:00:00Z"
        metadata = {
            "jira-platform": {
                "sha256": "0" * 64,  # wrong on purpose
                "last_checked": self._stale_timestamp(),
                "last_updated": old_last_updated,
                "api_version": "v1",
            }
        }
        html = "<script>window.__DATA__ = " + json.dumps(SPEC_V1) + ";</script>"
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            return_value=("https://developer.atlassian.com/cloud/x/rest/v1/", html),
        ):
            with mock.patch(
                "tools.atlassian_docs.sync.storage.write_cache_spec"
            ) as fake_write_cache:
                result = sync.sync_source("jira-platform", "https://x/", metadata, force=False)
        fake_write_cache.assert_not_called()  # content on disk already matched
        self.assertEqual(result.status, "ok")
        self.assertEqual(metadata["jira-platform"]["sha256"], storage.sha256_of_spec(SPEC_V1))
        self.assertEqual(metadata["jira-platform"]["last_updated"], old_last_updated)  # untouched


class TestSyncAllAndExitCode(SyncSourceTestCase):
    def test_sync_all_returns_one_result_per_configured_source(self):
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("offline"),
        ):
            results = sync.sync_all(force=False)
        self.assertEqual({r.source_name for r in results}, set(sources.SOURCES.keys()))

    def test_one_sources_unexpected_exception_does_not_abort_the_others(self):
        real_sync_source = sync.sync_source

        def flaky_sync_source(source_name, discovery_url, metadata, force):
            if source_name == "jira-platform":
                raise RuntimeError("disk exploded")
            return real_sync_source(source_name, discovery_url, metadata, force)

        with mock.patch("tools.atlassian_docs.sync.sync_source", side_effect=flaky_sync_source):
            with mock.patch(
                "tools.atlassian_docs.sync.fetch_documentation_html",
                side_effect=sync.FetchError("offline"),
            ):
                results = sync.sync_all(force=False)

        self.assertEqual({r.source_name for r in results}, set(sources.SOURCES.keys()))
        failed = next(r for r in results if r.source_name == "jira-platform")
        self.assertEqual(failed.status, "error_unavailable")
        # metadata.json must still have been written for the run to matter:
        self.assertIsInstance(storage.read_metadata(), dict)

    def test_metadata_write_failure_raises_metadata_persistence_error(self):
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=sync.FetchError("offline"),
        ):
            with mock.patch(
                "tools.atlassian_docs.sync.storage.write_metadata",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(sync.MetadataPersistenceError):
                    sync.sync_all(force=False)

    def test_exit_code_all_ok_is_zero(self):
        results = [sync.SyncResult(source_name="a", status="ok")]
        self.assertEqual(sync.exit_code_for(results), 0)

    def test_exit_code_updated_and_version_changed_are_also_zero(self):
        results = [
            sync.SyncResult(source_name="a", status="updated"),
            sync.SyncResult(source_name="b", status="version_changed"),
        ]
        self.assertEqual(sync.exit_code_for(results), 0)

    def test_exit_code_one_warn_fallback_is_one(self):
        results = [
            sync.SyncResult(source_name="a", status="ok"),
            sync.SyncResult(source_name="b", status="warn_fallback"),
        ]
        self.assertEqual(sync.exit_code_for(results), 1)

    def test_exit_code_one_error_unavailable_is_two(self):
        results = [
            sync.SyncResult(source_name="a", status="warn_fallback"),
            sync.SyncResult(source_name="b", status="error_unavailable"),
        ]
        self.assertEqual(sync.exit_code_for(results), 2)


if __name__ == "__main__":
    unittest.main()
