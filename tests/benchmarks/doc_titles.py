"""Documentation-title corpus for Round 4 (spec §5, §5.1, §6.1): sitemap acquisition into an immutable raw bundle,
deterministic snapshot of page <h1>/<title> text, and the DOCUMENTATION TITLES block for the lexicon generation input.
This module never reads the benchmark (AC-R4-05).

    python -m tests.benchmarks.doc_titles acquire --out-dir DIR [--epoch 1] [--delay 0.25]
    python -m tests.benchmarks.doc_titles snapshot --sources DIR --out FILE
    python -m tests.benchmarks.doc_titles render-check --sources DIR --snapshot FILE
"""
import argparse, gzip, hashlib, html, json, pathlib, re, sys, time, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlsplit

HOST = "support.atlassian.com"
DOC_SOURCES = (
    {"product": "jira-software-cloud", "sitemap_url": "https://support.atlassian.com/jira-cloud.xml", "allowed_loc_prefix": "https://support.atlassian.com/jira-software-cloud/docs/"},
    {"product": "confluence-cloud", "sitemap_url": "https://support.atlassian.com/confluence-cloud.xml", "allowed_loc_prefix": "https://support.atlassian.com/confluence-cloud/docs/"},
    {"product": "jira-cloud-administration", "sitemap_url": "https://support.atlassian.com/jira-cloud-administration.xml", "allowed_loc_prefix": "https://support.atlassian.com/jira-cloud-administration/docs/"},
)
MAX_FAIL_RATE = 0.05


def parse_sitemap(xml_bytes: bytes):
    """-> (root kind 'urlset' | 'sitemapindex', [loc, ...]); raises ValueError on another root."""
    root = ET.fromstring(xml_bytes)
    kind = root.tag.split("}")[-1]
    if kind not in ("urlset", "sitemapindex"):
        raise ValueError(f"sitemap root {kind!r}")
    locs = [e.text.strip() for e in root.iter() if e.tag.split("}")[-1] == "loc" and e.text]
    return kind, locs


def preflight(source, sitemap_bytes: bytes):
    """-> (kept_locs, discarded_count, problems). spec §5.1: root kind, host == HOST on every loc, prefix filter, count > 0."""
    try:
        kind, locs = parse_sitemap(sitemap_bytes)
    except (ET.ParseError, ValueError) as e:
        return [], 0, [f"{source['product']}: xml root/parse error: {e}"]
    problems, kept, discarded = [], [], 0
    for loc in locs:
        if urlsplit(loc).netloc != HOST:
            problems.append(f"{source['product']}: loc host != {HOST}: {loc}"); continue
        if kind == "urlset" and not loc.startswith(source["allowed_loc_prefix"]):
            discarded += 1; continue
        kept.append(loc)
    if not kept:
        problems.append(f"{source['product']}: count == 0 after prefix filter")
    return kept, discarded, problems


class _Titles(HTMLParser):
    """First <title> and first <h1> text of a page (entities decoded, whitespace collapsed); no JavaScript needed."""
    def __init__(self):
        super().__init__(); self.title = self.h1 = None; self._in = None; self._buf = []

    def handle_starttag(self, tag, attrs):
        if self._in is None and ((tag == "title" and self.title is None) or (tag == "h1" and self.h1 is None)):
            self._in, self._buf = tag, []

    def handle_data(self, d):
        if self._in:
            self._buf.append(d)

    def handle_endtag(self, tag):
        if self._in == tag:
            text = re.sub(r"\s+", " ", html.unescape("".join(self._buf))).strip()
            setattr(self, "title" if tag == "title" else "h1", text); self._in = None


def extract_title(html_bytes: bytes):
    p = _Titles(); p.feed(html_bytes.decode("utf-8", errors="replace")); p.close()
    return p.title, p.h1


def page_title(title_tag, h1) -> str:
    """spec §5: the <h1> when present, else the <title> before its ' | product | Atlassian Support' suffix."""
    return h1 if h1 else (title_tag or "").split(" | ")[0].strip()


def norm_tokens(text: str) -> list:
    from tests.benchmarks.evaluator import singular
    out = []
    for w in re.split(r"[^a-z0-9]+", text.lower()):
        if w and singular(w) not in out:
            out.append(singular(w))
    return out


def default_fetch(url, timeout=30):
    """-> (status, final_url, body); HTTP errors become a failure row, never an exception (spec §5)."""
    import http.client, urllib.error, urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "atlassian-api-updater round4 corpus"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.geturl() or url, b""
    except (OSError, http.client.HTTPException):                  # URLError, timeouts, resets, RemoteDisconnected, IncompleteRead …
        return 0, url, b""


def _ok(status) -> bool:
    return 200 <= status < 300


def acquire(sources, out_dir, fetch=default_fetch, delay=0.25, epoch=1) -> dict:
    """spec §5: the immutable raw bundle — sitemap bytes (and one level of child urlsets), every page's full HTML gzip-compressed
    under pages/<sha256>.html.gz, per-product pages.jsonl rows and acquisition-manifest.json. Aborts over MAX_FAIL_RATE."""
    out_dir = pathlib.Path(out_dir); (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    manifest = {"epoch": epoch, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": []}
    for src in sources:
        status, _, sm = fetch(src["sitemap_url"])
        if not _ok(status):
            raise SystemExit(f"{src['product']}: sitemap HTTP {status}")
        (out_dir / f"{src['product']}.sitemap.xml").write_bytes(sm)
        kind, _ = parse_sitemap(sm); children = []
        locs, discarded, problems = preflight(src, sm)
        if kind == "sitemapindex":                                       # one level, every child kept raw (spec §5.1)
            kept, locs, discarded = locs, [], 0
            for i, child in enumerate(kept, 1):
                st, _, cb = fetch(child)
                if not _ok(st):
                    raise SystemExit(f"{src['product']}: child sitemap HTTP {st}")
                (out_dir / f"{src['product']}.child-{i}.sitemap.xml").write_bytes(cb)
                children.append({"file": f"{src['product']}.child-{i}.sitemap.xml", "sha256": hashlib.sha256(cb).hexdigest()})
                if parse_sitemap(cb)[0] != "urlset":
                    raise SystemExit(f"{src['product']}: child sitemap {child} is not a urlset (one level only)")
                l, d, p = preflight(src, cb); locs += l; discarded += d; problems += p
        if problems:
            raise SystemExit("preflight: " + "; ".join(problems))
        rows, ok = [], 0
        for loc in locs:
            st, final, body = fetch(loc); time.sleep(delay)
            if not _ok(st):
                rows.append({"url": loc, "final_url": final, "http_status": st, "fail_reason": f"http-{st}"}); continue
            if urlsplit(final).netloc != HOST or not final.startswith(src["allowed_loc_prefix"]):
                rows.append({"url": loc, "final_url": final, "http_status": st, "fail_reason": "redirect-outside-prefix"}); continue
            sha = hashlib.sha256(body).hexdigest()
            (out_dir / "pages" / f"{sha}.html.gz").write_bytes(gzip.compress(body, mtime=0))
            rows.append({"url": loc, "final_url": final, "http_status": st, "html_sha256": sha}); ok += 1
        (out_dir / f"{src['product']}.pages.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        failed = len(rows) - ok
        if rows and failed / len(rows) > MAX_FAIL_RATE:
            raise SystemExit(f"{src['product']}: {failed}/{len(rows)} pages failed (> 5 %)")
        manifest["sources"].append({"product": src["product"], "sitemap_url": src["sitemap_url"], "allowed_loc_prefix": src["allowed_loc_prefix"],
                                    "sitemap_sha256": hashlib.sha256(sm).hexdigest(), "child_sitemaps": children, "loc_count": len(locs) + discarded,
                                    "discarded_loc_count": discarded, "url_count": len(locs), "page_ok": ok, "page_failed": failed})
    manifest["pages_sha256"] = hashlib.sha256(b"".join(sorted(p.read_bytes() for p in (out_dir / "pages").glob("*.html.gz")))).hexdigest()
    (out_dir / "acquisition-manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def bundle_sha256(out_dir) -> str:
    """canonical sha of [[relative path, sha256(bytes)], ...] over every file of the bundle (manifest, sitemaps, pages.jsonl, HTML gzips)."""
    from tests.benchmarks.evaluator import canonical_sha256
    out_dir = pathlib.Path(out_dir)
    files = sorted(p for p in out_dir.rglob("*") if p.is_file())
    return canonical_sha256([[str(p.relative_to(out_dir)), hashlib.sha256(p.read_bytes()).hexdigest()] for p in files])


def read_pages(out_dir, product) -> list:
    return [json.loads(l) for l in (pathlib.Path(out_dir) / f"{product}.pages.jsonl").read_text(encoding="utf-8").splitlines()]


def snapshot(out_dir) -> dict:
    """Deterministic, bundle-only (spec §5): titles from the gzip'd HTML; content-address check sha(gunzip) == row == filename."""
    out_dir = pathlib.Path(out_dir)
    manifest = json.loads((out_dir / "acquisition-manifest.json").read_text(encoding="utf-8"))
    titles = []
    for src in manifest["sources"]:
        for row in read_pages(out_dir, src["product"]):
            if "html_sha256" not in row:
                continue
            gz = out_dir / "pages" / f"{row['html_sha256']}.html.gz"
            body = gzip.decompress(gz.read_bytes())
            if hashlib.sha256(body).hexdigest() != row["html_sha256"]:
                raise SystemExit(f"content-address mismatch: {gz.name}")
            t = page_title(*extract_title(body))
            if t:
                titles.append({"product": src["product"], "url": row["url"], "title": t, "tokens": norm_tokens(t)})
    titles.sort(key=lambda e: (e["product"], e["title"], e["url"]))
    return {"source_bundle_sha256": bundle_sha256(out_dir), "sources": manifest["sources"], "titles": titles}


# ------------------------------------------------------------------ render helpers (spec §6.1)
def titles_for(snap, token, limit=5) -> list:
    """Titles whose normalized tokens contain `token`, (product, title) order, at most `limit`."""
    return sorted((t for t in snap["titles"] if token in t["tokens"]), key=lambda t: (t["product"], t["title"]))[:limit]


def render_block(snap, concept_tokens) -> str:
    """The DOCUMENTATION TITLES block: per concept token up to 5 lines `token<TAB>product<TAB>title`, or `token<TAB>-`."""
    lines = []
    for tok in concept_tokens:
        hits = titles_for(snap, tok)
        lines += [f"{tok}\t{h['product']}\t{h['title']}" for h in hits] or [f"{tok}\t-"]
    return "\n".join(lines)


def attachment_text(snap) -> str:
    """doc-titles.txt: every distinct (product, title) once, one `product<TAB>title` line each, (product, title) order."""
    seen, out = set(), []
    for t in sorted(snap["titles"], key=lambda t: (t["product"], t["title"])):
        if (t["product"], t["title"]) not in seen:
            seen.add((t["product"], t["title"])); out.append(f"{t['product']}\t{t['title']}\n")
    return "".join(out)


# ------------------------------------------------------------------ CLI
def _dump_snapshot(snap) -> str:
    return json.dumps(snap, sort_keys=True, indent=1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("acquire"); p.add_argument("--out-dir", required=True); p.add_argument("--epoch", type=int, default=1); p.add_argument("--delay", type=float, default=0.25)
    p = sub.add_parser("snapshot"); p.add_argument("--sources", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("render-check"); p.add_argument("--sources", required=True); p.add_argument("--snapshot", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "acquire":
        m = acquire(DOC_SOURCES, args.out_dir, default_fetch, delay=args.delay, epoch=args.epoch)
        print(json.dumps({"event": "doc_titles_acquired", "epoch": args.epoch, "sources": m["sources"], "doc_titles_source_bundle_sha256": bundle_sha256(args.out_dir)}))
        return 0
    if args.cmd == "snapshot":
        snap = snapshot(args.sources); text = _dump_snapshot(snap)
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print(json.dumps({"event": "doc_titles_snapshot", "doc_titles_snapshot_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                          "doc_titles_source_bundle_sha256": snap["source_bundle_sha256"], "titles": len(snap["titles"])}))
        return 0
    same = pathlib.Path(args.snapshot).read_text(encoding="utf-8") == _dump_snapshot(snapshot(args.sources))
    print("render-check ok" if same else "render-check MISMATCH: snapshot file differs from a fresh render of the bundle")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
