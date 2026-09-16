import urllib.error
import unittest
from unittest import mock

from tools.atlassian_docs import sync


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


if __name__ == "__main__":
    unittest.main()
