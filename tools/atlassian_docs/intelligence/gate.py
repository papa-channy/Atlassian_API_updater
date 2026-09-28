"""Compatibility gate (before normalize) and integrity check (after) — spec §10."""
from dataclasses import dataclass
from typing import Any, Optional

from .. import extractor, storage
from . import normalizer, registry

SUPPORTED_DIALECT_PREFIXES = ("3.0.", "3.1.")


@dataclass(frozen=True)
class GateResult:
    ok: bool
    code: Optional[str]
    message: str


_OK = GateResult(True, None, "ok")


def check_compatibility(spec: Any) -> GateResult:
    if not extractor.is_openapi_candidate(spec):
        return GateResult(False, "invalid_structure", "not an OpenAPI document (openapi/info/paths)")
    if not spec["openapi"].startswith(SUPPORTED_DIALECT_PREFIXES):
        return GateResult(False, "incompatible_dialect", f"unsupported OpenAPI dialect {spec['openapi']!r}")
    has_op = any(isinstance(item, dict) and any(m in item for m in normalizer.HTTP_METHODS)
                 for item in spec["paths"].values())
    if not has_op:
        return GateResult(False, "no_operations", "spec declares no operations")
    return _OK


def check_integrity(sr: registry.SourceRegistry) -> GateResult:
    if not sr.operations:
        return GateResult(False, "empty_registry", "normalized registry has no operations")
    keys = [op.key for op in sr.operations]
    if len(keys) != len(set(keys)):
        return GateResult(False, "duplicate_keys", "duplicate canonical keys")
    return _OK


def build_candidate(source_name: str, spec: Any) -> "tuple[Optional[registry.SourceRegistry], GateResult]":
    result = check_compatibility(spec)
    if not result.ok:
        return None, result
    comps = spec.get("components")
    if comps is not None and (not isinstance(comps, dict) or
                              ("schemas" in comps and not isinstance(comps["schemas"], dict))):
        return None, GateResult(False, "invalid_components", "components.schemas is not an object")
    try:
        normalized = normalizer.normalize_openapi(source_name, spec)
    except normalizer.NormalizationError as exc:
        return None, GateResult(False, "normalization_failed", str(exc))
    sr = registry.build_source_registry(normalized, storage.sha256_of_spec(spec))
    result = check_integrity(sr)
    return (sr, result) if result.ok else (None, result)
