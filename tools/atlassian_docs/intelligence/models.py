"""Frozen domain model for normalised OpenAPI operations (spec §6, §12).

Raw JSON-schema fragments are kept as plain dicts owned by the registry;
``to_dict`` always deep-copies them so callers can never mutate registry
state through a returned value (spec §9.5).
"""
import copy
import dataclasses
from dataclasses import dataclass
from typing import Any, Mapping, Optional


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


@dataclass(frozen=True)
class Parameter:
    name: str
    location: str  # "path" | "query" | "header" | "cookie"
    required: bool
    description: Optional[str]
    schema: Optional[dict]
    deprecated: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name, "in": self.location, "required": self.required,
            "description": self.description, "schema": _copy(self.schema),
            "deprecated": self.deprecated,
        }


@dataclass(frozen=True)
class MediaType:
    content_type: str
    schema: Optional[dict]

    def to_dict(self) -> dict:
        return {"content_type": self.content_type, "schema": _copy(self.schema)}


@dataclass(frozen=True)
class RequestBody:
    required: bool
    description: Optional[str]
    content: tuple  # tuple[MediaType, ...]

    def to_dict(self) -> dict:
        return {"required": self.required, "description": self.description,
                "content": [m.to_dict() for m in self.content]}


@dataclass(frozen=True)
class Response:
    status: str
    description: Optional[str]
    content: tuple  # tuple[MediaType, ...]

    def to_dict(self) -> dict:
        return {"status": self.status, "description": self.description,
                "content": [m.to_dict() for m in self.content]}


@dataclass(frozen=True)
class SecurityRequirement:
    scheme: str
    scopes: tuple  # tuple[str, ...]

    def to_dict(self) -> dict:
        return {"scheme": self.scheme, "scopes": list(self.scopes)}


@dataclass(frozen=True)
class SecurityAlternative:
    requirements: tuple  # tuple[SecurityRequirement, ...]  (AND)

    def to_dict(self) -> list:
        return [r.to_dict() for r in self.requirements]


@dataclass(frozen=True)
class Operation:
    source: str
    key: str
    operation_id: Optional[str]
    method: str
    path: str
    summary: Optional[str]
    description: Optional[str]
    tags: tuple
    parameters: tuple
    request_body: Optional[RequestBody]
    responses: tuple
    security: tuple  # tuple[SecurityAlternative, ...]  (OR)
    deprecated: bool
    experimental: bool
    oauth2_scopes: tuple

    def to_dict(self) -> dict:
        return {
            "source": self.source, "key": self.key, "operation_id": self.operation_id,
            "method": self.method, "path": self.path, "summary": self.summary,
            "description": self.description, "tags": list(self.tags),
            "parameters": [p.to_dict() for p in self.parameters],
            "request_body": self.request_body.to_dict() if self.request_body else None,
            "responses": [r.to_dict() for r in self.responses],
            "security": [alt.to_dict() for alt in self.security],
            "deprecated": self.deprecated, "experimental": self.experimental,
            "oauth2_scopes": list(self.oauth2_scopes),
        }


@dataclass(frozen=True)
class SourceProvenance:
    source: str
    status: str  # "fresh" | "stale" | "unavailable"
    reason: Optional[str]
    active_spec_sha256: Optional[str]
    active_openapi_version: Optional[str]
    active_api_version: Optional[str]
    operation_count: int
    schema_count: int
    observed_cache_sha256: Optional[str]
    metadata_sha256: Optional[str]
    resolved_documentation_url: Optional[str]
    last_checked: Optional[str]
    last_updated: Optional[str]
    candidate: Optional[dict]
    warnings: tuple

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["warnings"] = [_copy(w) for w in self.warnings]
        d["candidate"] = _copy(self.candidate)
        return d


@dataclass(frozen=True)
class RefreshStatus:
    ttl_seconds: int
    min_retry_interval_seconds: int
    backoff_active: bool
    last_refresh_attempt_at: Optional[str]
    last_refresh_result: Optional[dict]
    in_progress: bool

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["last_refresh_result"] = _copy(self.last_refresh_result)
        return d
