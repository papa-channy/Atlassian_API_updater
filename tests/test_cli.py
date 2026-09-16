import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tools.atlassian_docs import __main__ as cli
from tools.atlassian_docs import sources, storage, sync


class TestFormatResultLines(unittest.TestCase):
    def test_ok_status(self):
        result = sync.SyncResult(source_name="jira-platform", status="ok", api_version="v3")
        self.assertEqual(
            cli._format_result_lines(result), ["[OK] jira-platform: cache valid (v3)"]
        )

    def test_updated_status(self):
        result = sync.SyncResult(source_name="confluence", status="updated", api_version="v2")
        self.assertEqual(
            cli._format_result_lines(result),
            ["[UPDATED] confluence: specification changed"],
        )

    def test_version_changed_status(self):
        result = sync.SyncResult(
            source_name="jira-platform",
            status="version_changed",
            api_version="v4",
            previous_api_version="v3",
        )
        self.assertEqual(
            cli._format_result_lines(result),
            ["[VERSION] jira-platform: v3 -> v4", "[UPDATED] jira-platform"],
        )

    def test_warn_fallback_status(self):
        result = sync.SyncResult(
            source_name="jira-software",
            status="warn_fallback",
            message="OpenAPI extraction failed (0 candidates)",
        )
        self.assertEqual(
            cli._format_result_lines(result),
            [
                "[WARN] jira-software: OpenAPI extraction failed (0 candidates)",
                "[WARN] jira-software: using existing cache",
            ],
        )

    def test_error_unavailable_status(self):
        result = sync.SyncResult(
            source_name="confluence",
            status="error_unavailable",
            message="unable to extract OpenAPI specification",
        )
        self.assertEqual(
            cli._format_result_lines(result),
            ["[ERROR] confluence: unable to extract OpenAPI specification (no existing cache)"],
        )


class TestMain(unittest.TestCase):
    def test_returns_exit_code_from_sync_all(self):
        fake_result = sync.SyncResult(source_name="jira-platform", status="ok", api_version="v3")
        with mock.patch(
            "tools.atlassian_docs.__main__.sync.sync_all", return_value=[fake_result]
        ):
            code = cli.main([])
        self.assertEqual(code, 0)

    def test_force_flag_is_passed_through(self):
        fake_result = sync.SyncResult(source_name="jira-platform", status="ok", api_version="v3")
        with mock.patch(
            "tools.atlassian_docs.__main__.sync.sync_all", return_value=[fake_result]
        ) as fake_sync_all:
            cli.main(["--force"])
        fake_sync_all.assert_called_once_with(force=True)

    def test_metadata_persistence_error_returns_exit_one_not_two(self):
        with mock.patch(
            "tools.atlassian_docs.__main__.sync.sync_all",
            side_effect=sync.MetadataPersistenceError("disk full"),
        ):
            code = cli.main([])
        self.assertEqual(code, 1)

    def test_metadata_persistence_error_with_unavailable_source_returns_exit_two(self):
        # Finding #1 of the final whole-branch review: if the final
        # metadata.json write fails on the same run where a source has
        # NO usable cache at all (error_unavailable), that must still
        # surface as exit 2 -- not be downgraded to exit 1 just because
        # the trailing metadata write also failed.
        results = [
            sync.SyncResult(source_name="jira-platform", status="ok", api_version="v3"),
            sync.SyncResult(
                source_name="confluence",
                status="error_unavailable",
                message="unable to extract OpenAPI specification",
            ),
        ]
        with mock.patch(
            "tools.atlassian_docs.__main__.sync.sync_all",
            side_effect=sync.MetadataPersistenceError("disk full", results),
        ):
            code = cli.main([])
        self.assertEqual(code, 2)

    def test_status_flag_does_not_call_sync_all_and_returns_zero(self):
        with mock.patch("tools.atlassian_docs.__main__.sync.sync_all") as fake_sync_all:
            with mock.patch(
                "tools.atlassian_docs.__main__.storage.read_metadata", return_value={}
            ):
                code = cli.main(["--status"])
        fake_sync_all.assert_not_called()
        self.assertEqual(code, 0)


class TestEndToEnd(unittest.TestCase):
    """True end-to-end coverage: main() -> sync_all() -> real sync_source
    -> real storage reads/writes -> formatted output -> exit code, with
    mocking only at the network boundary (fetch_documentation_html).
    Added in response to finding #2 of the final whole-branch review --
    every prior test mocked away either sync_all wholesale or the entire
    per-source fetch, so no test exercised the real wiring end to end.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patcher = mock.patch.object(
            storage, "CACHE_DIR", pathlib.Path(self._tmpdir.name) / ".atlassian-docs"
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmpdir.cleanup()

    def _html_for(self, spec):
        return "<script>window.__DATA__ = " + json.dumps(spec) + ";</script>"

    def _fake_fetch(self, discovery_url, timeout=10.0):
        spec = {
            "openapi": "3.0.1",
            "info": {"title": discovery_url, "version": "1"},
            "paths": {},
        }
        return discovery_url, self._html_for(spec)

    def test_main_round_trips_through_real_sync_and_storage(self):
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=self._fake_fetch,
        ) as fake_fetch:
            code = cli.main([])
        self.assertEqual(code, 0)
        self.assertEqual(fake_fetch.call_count, len(sources.SOURCES))

        cache_dir = storage.CACHE_DIR
        expected_files = [
            "jira-platform.json",
            "jira-software.json",
            "confluence.json",
            "metadata.json",
        ]
        for filename in expected_files:
            self.assertTrue((cache_dir / filename).exists(), f"{filename} missing")

        metadata = storage.read_metadata()
        required_fields = (
            "resolved_documentation_url",
            "extraction_method",
            "api_version",
            "api_version_source",
            "spec_info_version",
            "last_checked",
            "last_updated",
            "sha256",
        )
        for source_name in sources.SOURCES:
            spec = storage.read_cache_spec(source_name)
            self.assertIsNotNone(spec)
            self.assertEqual(spec["openapi"], "3.0.1")

            meta = metadata[source_name]
            for field in required_fields:
                self.assertIn(field, meta, f"{source_name}.{field} missing")
            self.assertEqual(meta["sha256"], storage.sha256_of_spec(spec))

        # Second run within TTL: cache hit, no network calls at all.
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=self._fake_fetch,
        ) as fake_fetch_cached:
            code_cached = cli.main([])
        self.assertEqual(code_cached, 0)
        fake_fetch_cached.assert_not_called()

        # --force ignores the fresh TTL and re-extracts every source.
        with mock.patch(
            "tools.atlassian_docs.sync.fetch_documentation_html",
            side_effect=self._fake_fetch,
        ) as fake_fetch_forced:
            code_forced = cli.main(["--force"])
        self.assertEqual(code_forced, 0)
        self.assertEqual(fake_fetch_forced.call_count, len(sources.SOURCES))


if __name__ == "__main__":
    unittest.main()
