"""Orchestration: HTTP fetch, TTL, version detection, cache/metadata
reconciliation, and per-source failure policy. This is the only module
that knows about HTTP and ties extractor.py + storage.py together.
"""
import dataclasses
import datetime
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from . import extractor, sources, storage

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


TTL_SECONDS = 24 * 60 * 60
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TIMESTAMP_FORMAT = _TIMESTAMP_FORMAT


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(_TIMESTAMP_FORMAT)


def _parse_timestamp(value: Optional[str]):
    if value is None:
        return None
    return datetime.datetime.strptime(value, _TIMESTAMP_FORMAT).replace(
        tzinfo=datetime.timezone.utc
    )


@dataclasses.dataclass
class SyncResult:
    source_name: str
    status: str  # "ok" | "updated" | "version_changed" | "warn_fallback" | "error_unavailable"
    api_version: Optional[str] = None
    previous_api_version: Optional[str] = None
    message: str = ""


def _read_valid_cache_spec(source_name: str):
    """The cached spec if it exists, parses as JSON, and passes OpenAPI
    structural validation — regardless of whether it matches metadata.
    This is what "usable as a fallback" means (spec §22).
    """
    spec = storage.read_cache_spec(source_name)
    if spec is None or not extractor.is_openapi_candidate(spec):
        return None
    return spec


def _cache_matches_metadata(source_name: str, source_meta: dict) -> bool:
    """True only if the on-disk cache is structurally valid AND its
    canonical hash equals metadata.sha256. This gates the TTL fast-path —
    it is stricter than _read_valid_cache_spec, which only gates fallback
    eligibility after a failed refresh.
    """
    valid_spec = _read_valid_cache_spec(source_name)
    if valid_spec is None:
        return False
    expected_sha = source_meta.get("sha256")
    if expected_sha is None:
        return False
    return storage.sha256_of_spec(valid_spec) == expected_sha


def sync_source(
    source_name: str, discovery_url: str, metadata: dict, force: bool
) -> SyncResult:
    """Implements the Update Algorithm from spec §20. Mutates
    metadata[source_name] in place on any successful attempt.
    """
    source_meta = metadata.get(source_name, {})
    has_valid_fallback = _read_valid_cache_spec(source_name) is not None

    if not force and _cache_matches_metadata(source_name, source_meta):
        last_checked = _parse_timestamp(source_meta.get("last_checked"))
        if last_checked is not None:
            age = (datetime.datetime.now(datetime.timezone.utc) - last_checked).total_seconds()
            if age < TTL_SECONDS:
                return SyncResult(
                    source_name=source_name,
                    status="ok",
                    api_version=source_meta.get("api_version"),
                    message=f"cache valid ({source_meta.get('api_version') or 'unknown'})",
                )

    try:
        resolved_url, html = fetch_documentation_html(discovery_url)
        spec = extractor.extract_openapi_spec(html)
    except (FetchError, extractor.ExtractionError) as exc:
        if has_valid_fallback:
            return SyncResult(
                source_name=source_name,
                status="warn_fallback",
                api_version=source_meta.get("api_version"),
                message=str(exc),
            )
        return SyncResult(source_name=source_name, status="error_unavailable", message=str(exc))

    digest = storage.sha256_of_spec(spec)
    api_version, api_version_source = detect_api_version(resolved_url)
    previous_api_version = source_meta.get("api_version")
    now_iso = _now_iso()

    new_meta = dict(source_meta)
    new_meta.update(
        {
            "resolved_documentation_url": resolved_url,
            "extraction_method": "embedded_window_data",
            "api_version": api_version,
            "api_version_source": api_version_source,
            "spec_info_version": spec.get("info", {}).get("version"),
            "last_checked": now_iso,
            "sha256": digest,
        }
    )

    # Compare against the ACTUAL on-disk cache content, not source_meta's
    # (possibly stale/mismatched) sha256 field. This matters for the
    # self-heal path: if metadata was stale but the on-disk cache file
    # already holds the same content the remote just returned, there is
    # nothing to rewrite — only the metadata bookkeeping needs fixing.
    on_disk_spec = _read_valid_cache_spec(source_name)
    on_disk_digest = storage.sha256_of_spec(on_disk_spec) if on_disk_spec is not None else None
    changed = digest != on_disk_digest
    if changed:
        storage.write_cache_spec(source_name, spec)  # write cache BEFORE metadata is mutated below
        new_meta["last_updated"] = now_iso
    else:
        new_meta["last_updated"] = source_meta.get("last_updated", now_iso)

    metadata[source_name] = new_meta  # only mutated after any cache write above has succeeded

    version_changed = (
        previous_api_version is not None
        and api_version is not None
        and previous_api_version != api_version
    )

    if version_changed:
        status = "version_changed"
    elif changed:
        status = "updated"
    else:
        status = "ok"

    return SyncResult(
        source_name=source_name,
        status=status,
        api_version=api_version,
        previous_api_version=previous_api_version if version_changed else None,
        message="specification changed" if changed else f"cache valid ({api_version or 'unknown'})",
    )


class MetadataPersistenceError(Exception):
    """Raised when metadata.json cannot be saved after all sources were
    processed. Distinct from source unavailability: every cache file is
    already safely on disk (each was atomic-replaced before this point) —
    only the freshness/version bookkeeping failed to persist for this
    run. __main__.py treats this as degraded (exit 1), never as
    unavailable (exit 2) -- unless the per-source results it carries show
    a genuine unavailable source, in which case exit 2 still applies.
    """

    def __init__(self, message, results=None):
        super().__init__(message)
        self.results = results if results is not None else []


def sync_all(force: bool = False) -> list:
    metadata = storage.read_metadata()
    results = []
    for name, config in sources.SOURCES.items():
        try:
            result = sync_source(name, config["discovery_url"], metadata, force)
        except Exception as exc:  # noqa: BLE001 - contain one source's surprise
            # failure (e.g. a disk error inside storage.write_cache_spec) so
            # the remaining sources still get processed and metadata.json
            # still gets written for them. If the existing on-disk cache
            # for this source is still valid, this is degraded (fallback
            # usable), not unavailable -- same distinction sync_source
            # itself makes for FetchError/ExtractionError.
            if _read_valid_cache_spec(name) is not None:
                status = "warn_fallback"
            else:
                status = "error_unavailable"
            result = SyncResult(source_name=name, status=status, message=str(exc))
        results.append(result)

    try:
        storage.write_metadata(metadata)  # written once, after every cache file is on disk
    except OSError as exc:
        raise MetadataPersistenceError(str(exc), results) from exc

    return results


def exit_code_for(results) -> int:
    if any(r.status == "error_unavailable" for r in results):
        return 2
    if any(r.status == "warn_fallback" for r in results):
        return 1
    return 0
