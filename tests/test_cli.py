import unittest
from unittest import mock

from tools.atlassian_docs import __main__ as cli
from tools.atlassian_docs import sync


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
            message="unable to extract OpenAPI specification (no existing cache)",
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

    def test_status_flag_does_not_call_sync_all_and_returns_zero(self):
        with mock.patch("tools.atlassian_docs.__main__.sync.sync_all") as fake_sync_all:
            with mock.patch(
                "tools.atlassian_docs.__main__.storage.read_metadata", return_value={}
            ):
                code = cli.main(["--status"])
        fake_sync_all.assert_not_called()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
