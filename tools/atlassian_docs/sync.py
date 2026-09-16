"""Orchestration: HTTP fetch, TTL, version detection, cache/metadata
reconciliation, and per-source failure policy. This is the only module
that knows about HTTP and ties extractor.py + storage.py together.
"""
import re
import urllib.error
import urllib.parse
import urllib.request

_VERSION_SEGMENT_PATTERN = re.compile(r"/rest/(v\d+)(?:/|$)")


class FetchError(Exception):
    """Raised when the discovery URL cannot be fetched successfully."""


def detect_api_version(resolved_url: str):
    """Returns (api_version, api_version_source). Both None if the URL
    path has no explicit /rest/vN/ segment. See spec §15 — this is the
    ONLY source of api_version; info.version and paths are never used.
    """
    path = urllib.parse.urlparse(resolved_url).path
    match = _VERSION_SEGMENT_PATTERN.search(path)
    if match is None:
        return None, None
    return match.group(1), "documentation_url"


def fetch_documentation_html(discovery_url: str, timeout: float = 10.0):
    """GET discovery_url, following redirects (urllib does this by
    default). Returns (resolved_url, html). Raises FetchError on any
    network/HTTP failure.
    """
    request = urllib.request.Request(
        discovery_url, headers={"User-Agent": "atlassian-docs-sync/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            resolved_url = response.geturl()
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"failed to fetch {discovery_url}: {exc}") from exc
    return resolved_url, html
