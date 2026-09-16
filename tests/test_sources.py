import unittest

from tools.atlassian_docs import sources


class TestSources(unittest.TestCase):
    def test_has_exactly_the_three_expected_sources(self):
        self.assertEqual(
            set(sources.SOURCES.keys()),
            {"jira-platform", "jira-software", "confluence"},
        )

    def test_each_source_has_only_a_discovery_url(self):
        for name, config in sources.SOURCES.items():
            self.assertEqual(set(config.keys()), {"discovery_url"})
            self.assertTrue(config["discovery_url"].startswith("https://developer.atlassian.com/"))

    def test_no_version_strings_in_configuration(self):
        # AC-02/AC-03: no version or CDN URLs baked into config.
        serialized = str(sources.SOURCES)
        for forbidden in ("v1", "v2", "v3", "v4", "dac-static", "swagger"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
