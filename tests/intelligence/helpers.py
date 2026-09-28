import json
import pathlib

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openapi"


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / f"{name}-openapi.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_source_registry_from_fixture(name: str, source: str | None = None):
    """normalize + build for one fixture; returns SourceRegistry."""
    from tools.atlassian_docs import storage
    from tools.atlassian_docs.intelligence import normalizer, registry
    spec = load_fixture(name)
    ns = normalizer.normalize_openapi(source or name, spec)
    return registry.build_source_registry(ns, storage.sha256_of_spec(spec))


def make_state(*fixture_names, source_map=None):
    """ActiveState over fixtures with 'fresh' provenance; for testing intelligence functions."""
    import datetime
    from tools.atlassian_docs import sync
    from tools.atlassian_docs.intelligence import models, provenance, registry
    source_map = source_map or {}
    srcs = {source_map.get(n, n): build_source_registry_from_fixture(n, source_map.get(n)) for n in fixture_names}
    reg = registry.build_registry(srcs, "2026-09-28T00:00:00Z")
    now = datetime.datetime(2026, 9, 28, 1, 0, tzinfo=datetime.timezone.utc)
    obs = {}
    for name, sr in srcs.items():
        obs[name] = provenance.SourceObservation(
            source=name, observed_cache_sha256=sr.spec_sha256, served_from_last_good=False,
            rejected=None, refresh_failed=False, extra_warnings=(),
            metadata={"sha256": sr.spec_sha256, "api_version": "v3", "last_checked": now.strftime(sync.TIMESTAMP_FORMAT),
                      "last_updated": now.strftime(sync.TIMESTAMP_FORMAT), "resolved_documentation_url": "https://x/"})
    prov = provenance.build_provenance(reg, obs, now=now, ttl_seconds=sync.TTL_SECONDS)
    return registry.ActiveState(reg, prov, models.RefreshStatus(sync.TTL_SECONDS, 900, False, None, None, False))
