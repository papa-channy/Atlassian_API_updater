"""RegistryManager: cache-first startup, lazy TTL refresh with failure-only backoff,
gate-before-swap, durable last-known-good, single ActiveState snapshot (spec §11)."""
import datetime
import threading
import time
from typing import Callable, Optional

from .. import sources, storage, sync
from . import gate, lastgood, provenance, registry
from .models import RefreshStatus

MIN_RETRY_INTERVAL = 900
_FAILED_STATUSES = ("warn_fallback", "error_unavailable")


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class RegistryManager:
    def __init__(self, *, sync_all: Callable = sync.sync_all,
                 read_cache_spec: Callable = storage.read_cache_spec,
                 read_metadata: Callable = storage.read_metadata,
                 read_last_good: Callable = lastgood.read_last_good,
                 write_last_good: Callable = lastgood.write_last_good,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime.datetime] = _utc_now,
                 ttl_seconds: int = sync.TTL_SECONDS,
                 min_retry_interval: int = MIN_RETRY_INTERVAL):
        self._sync_all, self._read_cache_spec, self._read_metadata = sync_all, read_cache_spec, read_metadata
        self._read_last_good, self._write_last_good = read_last_good, write_last_good
        self._clock, self._now = clock, now
        self._ttl, self._min_retry = ttl_seconds, min_retry_interval
        self._lock = threading.Lock()
        self._active: Optional[registry.ActiveState] = None
        self._last_failed_mono: Optional[float] = None
        self._last_attempt_at: Optional[str] = None
        self._last_result: Optional[dict] = None
        self._served_from_last_good: set = set()
        self._rejected: dict = {}
        self._extra_warnings: dict = {}
        self._failed_sources: frozenset = frozenset()

    # ---- public -----------------------------------------------------------------
    @property
    def active(self) -> registry.ActiveState:
        if self._active is None:
            raise registry.RegistryUnavailableError("manager not started")
        return self._active

    @property
    def backoff_active(self) -> bool:
        return self._last_failed_mono is not None and (self._clock() - self._last_failed_mono) < self._min_retry

    @property
    def refresh_in_progress(self) -> bool:
        return self._lock.locked()

    def start(self) -> None:
        self._rebuild(previous=None, failed_sources=frozenset())
        if not self._active.registry.sources:
            self._run_sync()
            self._rebuild(previous=None, failed_sources=self._failed_sources)
            if not self._active.registry.sources:
                raise registry.RegistryUnavailableError("no usable OpenAPI cache for any source")

    def needs_refresh(self, source: str) -> bool:
        active = self._active
        if source not in active.registry.sources:
            return True
        md = self._safe_metadata().get(source, {})
        if not isinstance(md, dict):
            md = {}
        prov = active.provenance[source]
        if prov.observed_cache_sha256 != md.get("sha256"):
            return True
        checked = provenance._parse_ts(md.get("last_checked"))
        return checked is None or (self._now() - checked).total_seconds() >= self._ttl

    def ensure_fresh(self) -> None:
        """Never raises (spec §11.5): a failure keeps the current snapshot and starts backoff."""
        try:
            if not any(self.needs_refresh(s) for s in sources.SOURCES):
                return
        except Exception as exc:  # noqa: BLE001
            self._record_failure(exc)
            return
        if self.backoff_active:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._refresh_locked()
        except Exception as exc:  # noqa: BLE001 - lookups must keep serving the old snapshot
            self._record_failure(exc)
        finally:
            self._lock.release()

    def refresh(self) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"status": "refresh_in_progress"}
        try:
            before = self._active.registry.fingerprint
            try:
                self._refresh_locked()
            except Exception as exc:  # noqa: BLE001
                self._record_failure(exc)
                return {"status": "failed", "error": self._last_result["error"]}
            after = self._active.registry.fingerprint
            return {"status": "completed", "registry_rebuilt": before != after,
                    "fingerprint_before": before, "fingerprint_after": after,
                    "sources": dict(self._last_result or {})}
        finally:
            self._lock.release()

    # ---- internals ---------------------------------------------------------------
    def _record_failure(self, exc: BaseException) -> None:
        self._last_failed_mono = self._clock()
        self._last_result = {"error": f"{type(exc).__name__}: {exc}"}

    def _safe_metadata(self) -> dict:
        try:
            metadata = self._read_metadata()
        except (OSError, ValueError):
            return {}
        return metadata if isinstance(metadata, dict) else {}

    def _safe_read(self, reader: Callable, source: str, warnings: list):
        try:
            return reader(source)
        except (OSError, ValueError) as exc:
            warnings.append({"kind": "cache_read_failed", "message": str(exc)})
            return None

    def _run_sync(self) -> None:
        self._last_attempt_at = self._now().strftime(sync.TIMESTAMP_FORMAT)
        failed, results, all_failed = False, [], False
        try:
            results = self._sync_all(force=False)
        except sync.MetadataPersistenceError as exc:
            failed, results, all_failed = True, exc.results, True
        except Exception as exc:  # noqa: BLE001 - any sync failure is a failed refresh
            failed, results, all_failed = True, [], True
            self._last_result = {"error": str(exc)}
        failed_now = {r.source_name for r in results if r.status in _FAILED_STATUSES}
        if failed_now:
            failed = True
        self._failed_sources = frozenset(sources.SOURCES) if all_failed else frozenset(failed_now)
        if results:
            self._last_result = {r.source_name: r.status for r in results}
        if failed:
            self._last_failed_mono = self._clock()
        else:
            self._last_failed_mono = None

    def _refresh_locked(self) -> None:
        previous = self._active
        self._run_sync()
        self._rebuild(previous=previous, failed_sources=self._failed_sources)

    def _candidate_from(self, source: str, spec: dict, previous_sr):
        sha = storage.sha256_of_spec(spec)
        if previous_sr is not None and sha == previous_sr.spec_sha256:
            return previous_sr, sha, None
        rec = self._rejected.get(source)
        if rec and rec["sha256"] == sha:
            return None, sha, rec
        sr, result = gate.build_candidate(source, spec)
        if sr is None:
            return None, sha, {"sha256": sha, "rejected_reason": result.code, "message": result.message}
        return sr, sha, None

    def _rebuild(self, *, previous: Optional[registry.ActiveState], failed_sources: frozenset) -> None:
        metadata = self._safe_metadata()
        new_sources, observations = {}, {}
        for source in sources.SOURCES:
            prev_sr = previous.registry.sources.get(source) if previous else None
            warnings: list = []
            rejected = None
            served_last_good = False
            spec = self._safe_read(self._read_cache_spec, source, warnings)
            observed_sha = storage.sha256_of_spec(spec) if spec is not None else None
            chosen = None
            if spec is not None:
                chosen, _, rejected = self._candidate_from(source, spec, prev_sr)
                if chosen is not None and chosen is not prev_sr:
                    lg = self._safe_read(self._read_last_good, source, warnings)
                    lg_sha = storage.sha256_of_spec(lg) if lg is not None else None
                    if lg_sha != observed_sha:
                        try:
                            self._write_last_good(source, spec)
                        except OSError as exc:
                            warnings.append({"kind": "last_good_write_failed", "message": str(exc)})
            if chosen is None and prev_sr is not None:
                chosen = prev_sr
                served_last_good = source in self._served_from_last_good
            if chosen is None:
                lg = self._safe_read(self._read_last_good, source, warnings)
                if lg is not None:
                    sr, result = gate.build_candidate(source, lg)
                    if sr is not None:
                        chosen, served_last_good = sr, True
            if served_last_good:
                self._served_from_last_good.add(source)
            else:
                self._served_from_last_good.discard(source)
            if rejected:
                self._rejected[source] = rejected
            elif chosen is not None and not served_last_good:
                self._rejected.pop(source, None)
            if chosen is not None:
                new_sources[source] = chosen
            src_md = metadata.get(source, {})
            if not isinstance(src_md, dict):
                src_md = {}
            observations[source] = provenance.SourceObservation(
                source=source, metadata=src_md, observed_cache_sha256=observed_sha,
                served_from_last_good=served_last_good, rejected=self._rejected.get(source),
                refresh_failed=source in failed_sources, extra_warnings=tuple(warnings))
        now = self._now()
        reg = registry.build_registry(new_sources, now.strftime(sync.TIMESTAMP_FORMAT))
        prov = provenance.build_provenance(reg, observations, now=now, ttl_seconds=self._ttl)
        status = RefreshStatus(self._ttl, self._min_retry, self.backoff_active, self._last_attempt_at,
                               self._last_result, self._lock.locked())
        self._active = registry.ActiveState(reg, prov, status)   # single assignment = atomic swap
