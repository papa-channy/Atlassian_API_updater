"""Manual smoke test against the real Atlassian documentation site.

NOT run by `python -m unittest discover` — it hits the network. Run it
directly when you want to check whether Atlassian's page structure still
matches what extractor.py expects:

    python tests/live_smoke.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.atlassian_docs import extractor, sources, sync


def main() -> int:
    failures = []
    for source_name, config in sources.SOURCES.items():
        try:
            resolved_url, html = sync.fetch_documentation_html(config["discovery_url"])
            spec = extractor.extract_openapi_spec(html)
        except (sync.FetchError, extractor.ExtractionError) as exc:
            failures.append(source_name)
            print(f"[FAIL] {source_name}: {exc}")
            continue
        api_version, _ = sync.detect_api_version(resolved_url)
        print(
            f"[OK] {source_name}: resolved={resolved_url} "
            f"api_version={api_version} openapi={spec.get('openapi')} "
            f"paths={len(spec.get('paths', {}))}"
        )
    if failures:
        print(f"\n{len(failures)} source(s) failed live extraction: {', '.join(failures)}")
        return 1
    print("\nAll sources extracted exactly one OpenAPI candidate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
