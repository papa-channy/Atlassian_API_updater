"""Immutable per-source and composite registries plus the ActiveState snapshot (spec §9, §11.1)."""
import copy
import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from .. import sources
from . import search
from .models import Operation, RefreshStatus, SourceProvenance
from .normalizer import NormalizedSpec


class RegistryUnavailableError(Exception):
    """No source could be loaded at startup (spec §11.2)."""


@dataclass(frozen=True)
class SourceRegistry:
    source: str
    openapi_version: str
    title: Optional[str]
    operations: tuple
    operations_by_key: Mapping[str, Operation]
    keys_by_operation_id: Mapping[str, tuple]
    schemas: Mapping[str, dict]
    parameters: Mapping[str, dict]
    request_bodies: Mapping[str, dict]
    responses: Mapping[str, dict]
    security_schemes: Mapping[str, dict]
    tags: tuple
    spec_sha256: str
    warnings: tuple
    normalization_partial: bool
    search_index: search.SearchIndex


def build_source_registry(normalized: NormalizedSpec, spec_sha256: str) -> SourceRegistry:
    by_key = {}
    by_op_id: dict = {}
    for op in normalized.operations:
        by_key[op.key] = op
        if op.operation_id:
            by_op_id.setdefault(op.operation_id, []).append(op.key)
    return SourceRegistry(
        source=normalized.source, openapi_version=normalized.openapi_version, title=normalized.title,
        operations=normalized.operations,
        operations_by_key=MappingProxyType(by_key),
        keys_by_operation_id=MappingProxyType({k: tuple(v) for k, v in by_op_id.items()}),
        schemas=MappingProxyType(normalized.schemas), parameters=MappingProxyType(normalized.parameters),
        request_bodies=MappingProxyType(normalized.request_bodies), responses=MappingProxyType(normalized.responses),
        security_schemes=MappingProxyType(normalized.security_schemes),
        tags=normalized.tags, spec_sha256=spec_sha256, warnings=normalized.warnings,
        normalization_partial=normalized.normalization_partial,
        search_index=search.build_index(normalized.operations),
    )


def compute_fingerprint(shas: Mapping[str, Optional[str]]) -> str:
    lines = [f"{name}:{shas.get(name) or '-'}" for name in sorted(sources.SOURCES)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Registry:
    sources: Mapping[str, SourceRegistry]
    fingerprint: str
    built_at: str

    def components(self, source: str) -> Optional[SourceRegistry]:
        """Internal read-only surface; callers must never mutate the returned mappings — use
        get_schema/to_dict copies."""
        return self.sources.get(source)

    def get_operation(self, key: str) -> Optional[Operation]:
        source = key.split(":", 1)[0]
        sr = self.sources.get(source)
        return sr.operations_by_key.get(key) if sr else None

    def find_by_operation_id(self, source: Optional[str], operation_id: str) -> tuple:
        names = [source] if source else sorted(self.sources)
        keys: list = []
        for name in names:
            sr = self.sources.get(name)
            if sr:
                keys.extend(sr.keys_by_operation_id.get(operation_id, ()))
        return tuple(keys)

    def list_operations(self, source=None, method=None, tag=None, include_deprecated=True) -> tuple:
        out = []
        for name in sorted(self.sources):
            if source and name != source:
                continue
            for op in self.sources[name].operations:
                if method and op.method != method.upper():
                    continue
                if tag and tag not in op.tags:
                    continue
                if not include_deprecated and op.deprecated:
                    continue
                out.append(op)
        return tuple(out)

    def list_sources(self) -> tuple:
        return tuple(sorted(self.sources))

    def list_tags(self, source: str) -> tuple:
        sr = self.sources.get(source)
        return sr.tags if sr else ()

    def get_schema(self, source: str, name: str) -> Optional[dict]:
        sr = self.sources.get(source)
        node = sr.schemas.get(name) if sr else None
        return copy.deepcopy(node) if isinstance(node, dict) else None


def build_registry(source_registries: Mapping[str, SourceRegistry], built_at: str) -> Registry:
    frozen = MappingProxyType(dict(source_registries))
    return Registry(sources=frozen,
                    fingerprint=compute_fingerprint({n: sr.spec_sha256 for n, sr in frozen.items()}),
                    built_at=built_at)


@dataclass(frozen=True)
class ActiveState:
    registry: Registry
    provenance: Mapping[str, SourceProvenance]
    refresh: RefreshStatus
