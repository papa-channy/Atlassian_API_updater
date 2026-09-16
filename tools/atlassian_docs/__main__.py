"""CLI entry point. No sync logic here — parses args, calls sync.py,
formats output per spec §25, and returns the exit code from §26.
"""
import argparse
import sys

from . import sources, storage, sync


def _format_result_lines(result: sync.SyncResult):
    name = result.source_name
    if result.status == "ok":
        return [f"[OK] {name}: cache valid ({result.api_version or 'unknown'})"]
    if result.status == "updated":
        return [f"[UPDATED] {name}: specification changed"]
    if result.status == "version_changed":
        return [
            f"[VERSION] {name}: {result.previous_api_version} -> {result.api_version}",
            f"[UPDATED] {name}",
        ]
    if result.status == "warn_fallback":
        return [
            f"[WARN] {name}: {result.message}",
            f"[WARN] {name}: using existing cache",
        ]
    if result.status == "error_unavailable":
        return [f"[ERROR] {name}: {result.message}"]
    raise ValueError(f"unknown sync result status: {result.status!r}")


def _print_results(results) -> None:
    for result in results:
        for line in _format_result_lines(result):
            print(line)


def _display_timestamp(value):
    if not value:
        return "-"
    import datetime

    dt = datetime.datetime.strptime(value, sync._TIMESTAMP_FORMAT)
    return dt.strftime("%Y-%m-%d %H:%M")


def _show_status() -> int:
    metadata = storage.read_metadata()
    for source_name in sources.SOURCES:
        meta = metadata.get(source_name, {})
        print(source_name)
        print(f"  API version: {meta.get('api_version') or '(unknown)'}")
        print(f"  Cached: {'yes' if meta else 'no'}")
        print(f"  Last checked: {_display_timestamp(meta.get('last_checked'))}")
        print(f"  Last updated: {_display_timestamp(meta.get('last_updated'))}")
        print()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.atlassian_docs")
    parser.add_argument("--force", action="store_true", help="ignore TTL and re-extract")
    parser.add_argument("--status", action="store_true", help="show cache status and exit")
    args = parser.parse_args(argv)

    if args.status:
        return _show_status()

    try:
        results = sync.sync_all(force=args.force)
    except sync.MetadataPersistenceError as exc:
        # Every cache file that could be refreshed already was (atomic
        # replace happens per-source before this point) — only the
        # metadata.json bookkeeping failed to save. That's a degraded
        # run, not an unavailable API reference, so it's exit 1, not 2.
        print(f"[WARN] metadata.json could not be saved: {exc}")
        return 1

    _print_results(results)
    return sync.exit_code_for(results)


if __name__ == "__main__":
    sys.exit(main())
