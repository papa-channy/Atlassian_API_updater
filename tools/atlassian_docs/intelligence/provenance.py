"""Per-source provenance computed from the ACTIVE registry (spec §12) + response helpers (§14.1)."""
import datetime
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .. import sources, sync
from .models import SourceProvenance


@dataclass(frozen=True)
class SourceObservation:
    source: str
    metadata: dict
    observed_cache_sha256: Optional[str]
    served_from_last_good: bool
    rejected: Optional[dict]
    refresh_failed: bool
    extra_warnings: tuple


def _parse_ts(value: Any) -> Optional[datetime.datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value, sync.TIMESTAMP_FORMAT).replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def build_source_provenance(active, obs: SourceObservation, *, now: datetime.datetime,
                            ttl_seconds: int = sync.TTL_SECONDS) -> SourceProvenance:
    md = obs.metadata if isinstance(obs.metadata, dict) else {}
    warnings = list(obs.extra_warnings)
    common = dict(
        source=obs.source, observed_cache_sha256=obs.observed_cache_sha256,
        metadata_sha256=md.get("sha256"), resolved_documentation_url=md.get("resolved_documentation_url"),
        last_checked=md.get("last_checked"), last_updated=md.get("last_updated"),
        candidate=dict(obs.rejected) if obs.rejected else None,
    )
    if active is None:
        reason = obs.rejected["rejected_reason"] if obs.rejected else "no_cache"
        return SourceProvenance(status="unavailable", reason=reason, active_spec_sha256=None,
                                active_openapi_version=None, active_api_version=None,
                                operation_count=0, schema_count=0, warnings=tuple(warnings), **common)
    if active.normalization_partial:
        warnings.append({"kind": "normalization_partial",
                         "skipped": sum(1 for w in active.warnings if w.get("kind") == "operation_skipped")})
    matches_metadata = md.get("sha256") == active.spec_sha256
    checked = _parse_ts(md.get("last_checked"))
    ttl_ok = checked is not None and (now - checked).total_seconds() < ttl_seconds
    if obs.served_from_last_good:          # wins over `rejected`: the candidate stays in `candidate` as diagnostic
        reason = "served_from_last_good"
    elif obs.rejected:
        reason = obs.rejected["rejected_reason"]
    elif obs.refresh_failed:
        reason = "refresh_failed"
    elif not matches_metadata:
        reason = "metadata_mismatch"
    elif not ttl_ok:
        reason = "ttl_expired"
    else:
        reason = None
    return SourceProvenance(
        status="fresh" if reason is None else "stale", reason=reason,
        active_spec_sha256=active.spec_sha256, active_openapi_version=active.openapi_version,
        active_api_version=md.get("api_version") if matches_metadata else None,
        operation_count=len(active.operations), schema_count=len(active.schemas),
        warnings=tuple(warnings), **common)


def build_provenance(reg, observations: Mapping[str, SourceObservation], *, now: datetime.datetime,
                     ttl_seconds: int = sync.TTL_SECONDS) -> Mapping[str, SourceProvenance]:
    out = {}
    for name in sources.SOURCES:
        obs = observations.get(name) or SourceObservation(name, {}, None, False, None, False, ())
        out[name] = build_source_provenance(reg.sources.get(name), obs, now=now, ttl_seconds=ttl_seconds)
    return out


def error_response(code: str, message: str, **extra) -> dict:
    err = {"code": code, "message": message}
    err.update(extra)
    return {"error": err}


def with_provenance(payload: dict, state, source_names) -> dict:
    """Add `provenance` and `registry_fingerprint` to payload IN PLACE and return it."""
    prov = {}
    for name in source_names:
        p = state.provenance.get(name)
        prov[name] = p.to_dict() if p else {"source": name, "status": "unavailable", "reason": "unknown_source"}
    payload["provenance"] = prov
    payload["registry_fingerprint"] = state.registry.fingerprint
    return payload
