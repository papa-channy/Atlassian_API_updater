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
