"""Single home for transport/credential header names and redaction (spec §14)."""
from typing import Any

TRANSPORT_HEADERS = frozenset({"content-type", "accept", "content-length", "host", "user-agent", "accept-encoding"})
CREDENTIAL_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token"})
REDACTED = "[REDACTED]"


def credential_header_names(source_registry: Any) -> frozenset:
    """Static list plus every securitySchemes entry of type apiKey located in a header (lower-cased)."""
    names = set(CREDENTIAL_HEADERS)
    schemes = getattr(source_registry, "security_schemes", None) or {}
    for scheme in schemes.values():
        if isinstance(scheme, dict) and scheme.get("type") == "apiKey" and scheme.get("in") == "header" \
                and isinstance(scheme.get("name"), str):
            names.add(scheme["name"].lower())
    return frozenset(names)


def is_transport(name: str) -> bool:
    return name.lower() in TRANSPORT_HEADERS
