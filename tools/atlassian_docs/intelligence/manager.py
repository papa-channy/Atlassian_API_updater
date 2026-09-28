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

    # ---- public -----------------------------------------------------------------
    @property
    def active(self) -> registry.ActiveState:
        if self._active is None:
            raise registry.RegistryUnavailableError("manager not started")
        return self._active

    @property
    def backoff_active(self) -> bool:
        return self._last_failed_mono is not None and (self._clock() - self._last_failed_mono) < self._min_retry

    def start(self) -> None:
        self._rebuild(previous=None, refresh_failed=False)
        if not self._active.registry.sources:
            self._run_sync()
            self._rebuild(previous=None, refresh_failed=self._last_failed_mono is not None)
            if not self._active.registry.sources:
                raise registry.RegistryUnavailableError("no usable OpenAPI cache for any source")

    def needs_refresh(self, source: str) -> bool:
        active = self._active
        if source not in active.registry.sources:
            return True
        md = self._read_metadata().get(source, {})
        prov = active.provenance[source]
        if prov.observed_cache_sha256 != md.get("sha256"):
            return True
        checked = provenance._parse_ts(md.get("last_checked"))
        return checked is None or (self._now() - checked).total_seconds() >= self._ttl

    def ensure_fresh(self) -> None:
        if not any(self.needs_refresh(s) for s in sources.SOURCES):
            return
        if self.backoff_active:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._refresh_locked()
        finally:
            self._lock.release()

    def refresh(self) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"status": "refresh_in_progress"}
        try:
            before = self._active.registry.fingerprint
            self._refresh_locked()
            after = self._active.registry.fingerprint
            return {"status": "completed", "registry_rebuilt": before != after,
                    "fingerprint_before": before, "fingerprint_after": after,
                    "sources": dict(self._last_result or {})}
        finally:
            self._lock.release()

    # ---- internals ---------------------------------------------------------------
    def _run_sync(self) -> None:
        self._last_attempt_at = self._now().strftime(sync.TIMESTAMP_FORMAT)
        failed, results = False, []
        try:
            results = self._sync_all(force=False)
        except sync.MetadataPersistenceError as exc:
            failed, results = True, exc.results
        except Exception as exc:  # noqa: BLE001 - any sync failure is a failed refresh
            failed, results = True, []
            self._last_result = {"error": str(exc)}
        if any(r.status in _FAILED_STATUSES for r in results):
            failed = True
        if results:
            self._last_result = {r.source_name: r.status for r in results}
        if failed:
            self._last_failed_mono = self._clock()
        else:
            self._last_failed_mono = None

    def _refresh_locked(self) -> None:
        previous = self._active
        self._run_sync()
        self._rebuild(previous=previous, refresh_failed=self._last_failed_mono is not None)

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

    def _rebuild(self, *, previous: Optional[registry.ActiveState], refresh_failed: bool) -> None:
        metadata = self._read_metadata()
        new_sources, observations = {}, {}
        for source in sources.SOURCES:
            prev_sr = previous.registry.sources.get(source) if previous else None
            warnings: list = []
            rejected = None
            served_last_good = False
            spec = self._read_cache_spec(source)
            observed_sha = storage.sha256_of_spec(spec) if spec is not None else None
            chosen = None
            if spec is not None:
                chosen, _, rejected = self._candidate_from(source, spec, prev_sr)
                if chosen is not None and chosen is not prev_sr:
                    lg = self._read_last_good(source)
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
                lg = self._read_last_good(source)
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
            observations[source] = provenance.SourceObservation(
                source=source, metadata=metadata.get(source, {}), observed_cache_sha256=observed_sha,
                served_from_last_good=served_last_good, rejected=self._rejected.get(source),
                refresh_failed=refresh_failed, extra_warnings=tuple(warnings))
        now = self._now()
        reg = registry.build_registry(new_sources, now.strftime(sync.TIMESTAMP_FORMAT))
        prov = provenance.build_provenance(reg, observations, now=now, ttl_seconds=self._ttl)
        status = RefreshStatus(self._ttl, self._min_retry, self.backoff_active, self._last_attempt_at,
                               self._last_result, False)
        self._active = registry.ActiveState(reg, prov, status)   # single assignment = atomic swap
