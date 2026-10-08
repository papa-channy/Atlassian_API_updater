import gzip, hashlib, json, pathlib, tempfile, unittest
from unittest import mock
from tests.benchmarks import doc_titles as dt

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "doc_titles"
FX = lambda name: (FIX / name).read_bytes()
PREFIX = "https://support.atlassian.com/jira-software-cloud/docs/"
LOC1, LOC2, LOC3 = PREFIX + "release-your-teams-work-in-versions/", PREFIX + "what-is-a-space/", PREFIX + "only-a-title/"
SM_URL = "https://support.atlassian.com/jira-cloud.xml"
IDX_URL, CHILD_URL = "https://support.atlassian.com/jira-index.xml", "https://support.atlassian.com/jira-software-cloud/child-1.xml"
SOURCES_FX = (dict(dt.DOC_SOURCES[0], sitemap_url=SM_URL),)
PAGES_FX = {SM_URL: FX("jira.sitemap.xml"), LOC1: FX("page-release.html"), LOC2: FX("page-space.html"), LOC3: FX("page-notitle.html")}


def fake_fetch(pages, redirects=None, statuses=None):
    def fetch(url):
        final = (redirects or {}).get(url, url)
        return (statuses or {}).get(url, 200), final, pages.get(final, b"")
    return fetch


class TestSourceContract(unittest.TestCase):
    def test_doc_sources_literal(self):
        self.assertEqual([s["product"] for s in dt.DOC_SOURCES], ["jira-software-cloud", "confluence-cloud", "jira-cloud-administration"])
        self.assertEqual(dt.DOC_SOURCES[0]["sitemap_url"], "https://support.atlassian.com/jira-cloud.xml")
        self.assertEqual(dt.DOC_SOURCES[0]["allowed_loc_prefix"], "https://support.atlassian.com/jira-software-cloud/docs/")

    def test_parse_sitemap_urlset_and_index(self):
        kind, locs = dt.parse_sitemap(FX("jira.sitemap.xml")); self.assertEqual(kind, "urlset"); self.assertEqual(len(locs), 4)
        self.assertEqual(dt.parse_sitemap(FX("index.sitemap.xml"))[0], "sitemapindex")

    def test_preflight_discards_foreign_prefix_and_counts(self):
        kept, discarded, problems = dt.preflight(dt.DOC_SOURCES[0], FX("jira.sitemap.xml"))
        self.assertEqual((len(kept), discarded, problems), (3, 1, []))
        self.assertIn("host", dt.preflight(dt.DOC_SOURCES[2], FX("admin.sitemap.xml"))[2][0])

    def test_preflight_rejects_empty(self):
        self.assertIn("count", dt.preflight(dt.DOC_SOURCES[1], b"<urlset/>")[2][0])


class TestAcquireAndSnapshot(unittest.TestCase):
    def test_extract_title_h1_entities_and_title_fallback(self):
        self.assertEqual(dt.extract_title(FX("page-release.html"))[1], "Release your team's work in versions")
        self.assertEqual(dt.extract_title(FX("page-notitle.html")), ("Only a title | Jira Cloud | Atlassian Support", None))
        self.assertEqual(dt.page_title("Only a title | Jira Cloud | Atlassian Support", None), "Only a title")

    def test_acquire_writes_bundle_manifest_and_gzip_pages(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "src"; m = dt.acquire(SOURCES_FX, out, fake_fetch(PAGES_FX), delay=0)
            self.assertEqual([s["product"] for s in m["sources"]], ["jira-software-cloud"])
            self.assertEqual(m["sources"][0]["discarded_loc_count"], 1); self.assertEqual(m["sources"][0]["page_ok"], 3)
            rows = [json.loads(l) for l in (out / "jira-software-cloud.pages.jsonl").read_text().splitlines()]
            gz = out / "pages" / f"{rows[0]['html_sha256']}.html.gz"
            self.assertEqual(hashlib.sha256(gzip.decompress(gz.read_bytes())).hexdigest(), rows[0]["html_sha256"])
            self.assertEqual(dt.bundle_sha256(out), dt.bundle_sha256(out))           # deterministic

    def test_acquire_redirect_outside_prefix_is_failed(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(dt, "MAX_FAIL_RATE", 1.0):      # 1/3 failed would otherwise abort (see the fail-rate test)
            dt.acquire(SOURCES_FX, pathlib.Path(td), fake_fetch(PAGES_FX, redirects={LOC1: "https://support.atlassian.com/confluence-cloud/docs/x/"}), delay=0)
            row = next(r for r in dt.read_pages(pathlib.Path(td), "jira-software-cloud") if r["url"] == LOC1)
            self.assertEqual(row["fail_reason"], "redirect-outside-prefix"); self.assertNotIn("html_sha256", row)

    def test_acquire_rejects_nested_sitemapindex(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaises(SystemExit):
            dt.acquire([dict(dt.DOC_SOURCES[0], sitemap_url=IDX_URL)], pathlib.Path(td), fake_fetch({**PAGES_FX, IDX_URL: FX("index.sitemap.xml"), CHILD_URL: FX("index.sitemap.xml")}), delay=0)

    def test_acquire_index_with_urlset_child(self):
        with tempfile.TemporaryDirectory() as td:
            m = dt.acquire([dict(dt.DOC_SOURCES[0], sitemap_url=IDX_URL)], pathlib.Path(td), fake_fetch({**PAGES_FX, IDX_URL: FX("index.sitemap.xml"), CHILD_URL: FX("jira.sitemap.xml")}), delay=0)
            self.assertEqual(len(m["sources"][0]["child_sitemaps"]), 1); self.assertEqual(m["sources"][0]["page_ok"], 3)

    def test_acquire_aborts_over_fail_rate(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaises(SystemExit):
            dt.acquire(SOURCES_FX, pathlib.Path(td), fake_fetch(PAGES_FX, statuses={LOC1: 500}), delay=0)   # 1/3 > 5 %

    def test_snapshot_reads_only_bundle_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td); dt.acquire(SOURCES_FX, out, fake_fetch(PAGES_FX), delay=0)
            with mock.patch.object(dt, "default_fetch", side_effect=AssertionError("network")):
                snap = dt.snapshot(out)
            self.assertEqual(snap["source_bundle_sha256"], dt.bundle_sha256(out))
            self.assertEqual(json.dumps(snap, sort_keys=True), json.dumps(dt.snapshot(out), sort_keys=True))
            self.assertIn({"product": "jira-software-cloud", "url": LOC2, "title": "What is a space?", "tokens": ["what", "is", "a", "space"]}, snap["titles"])

    def test_snapshot_rejects_content_address_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td); dt.acquire(SOURCES_FX, out, fake_fetch(PAGES_FX), delay=0)
            gz = next((out / "pages").glob("*.html.gz")); gz.write_bytes(gzip.compress(b"<h1>tampered</h1>"))
            with self.assertRaises(SystemExit): dt.snapshot(out)


class TestRender(unittest.TestCase):
    def test_titles_for_limit_and_order(self):
        snap = {"titles": [{"product": "p", "url": f"u{i}", "title": f"{c} space {i}", "tokens": ["space"]} for i, c in enumerate("fedcba")]}
        got = dt.titles_for(snap, "space"); self.assertEqual(len(got), 5); self.assertEqual([t["title"][0] for t in got], list("abcde"))
        self.assertEqual(dt.titles_for(snap, "zzz"), [])

    def test_render_block_and_attachment(self):
        snap = {"titles": [{"product": "confluence-cloud", "url": "u", "title": "What is a space?", "tokens": ["what", "is", "a", "space"]}]}
        self.assertEqual(dt.render_block(snap, ["space", "issue"]), "space\tconfluence-cloud\tWhat is a space?\nissue\t-")
        self.assertEqual(dt.attachment_text(snap), "confluence-cloud\tWhat is a space?\n")

    def test_module_never_names_the_benchmark(self):
        src = pathlib.Path(dt.__file__).read_text(encoding="utf-8")
        self.assertNotIn("search_queries", src)


class TestFetchErrors(unittest.TestCase):
    def test_default_fetch_turns_read_errors_into_failure_rows(self):
        import urllib.request
        for exc in (TimeoutError("read timed out"), ConnectionResetError(), __import__("http.client").client.RemoteDisconnected("gone")):
            with mock.patch.object(urllib.request, "urlopen", side_effect=exc):
                self.assertEqual(dt.default_fetch("https://support.atlassian.com/x")[0], 0)
