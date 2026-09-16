"""Pure-function extraction of the embedded OpenAPI spec from an Atlassian
REST documentation page's HTML. Knows nothing about HTTP.
"""
import json
import re

_MARKER_PATTERN = re.compile(r"window\.__DATA__\s*=\s*")


class ExtractionError(Exception):
    """Raised when the embedded OpenAPI spec cannot be extracted from HTML."""


class AmbiguousExtractionError(ExtractionError):
    """Raised when more than one OpenAPI-shaped candidate is found."""


def extract_embedded_data(html: str) -> object:
    """Find the single `window.__DATA__ = ...` assignment and JSON-decode
    the value that follows it. Raises ExtractionError if there isn't
    exactly one assignment, or if the JSON after it doesn't parse.
    """
    matches = list(_MARKER_PATTERN.finditer(html))
    if len(matches) != 1:
        raise ExtractionError(
            f"expected exactly 1 window.__DATA__ assignment, found {len(matches)}"
        )
    start = matches[0].end()
    try:
        data, _ = json.JSONDecoder().raw_decode(html, start)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"failed to decode JSON after window.__DATA__: {exc}"
        ) from exc
    return data


def is_openapi_candidate(node: object) -> bool:
    return (
        isinstance(node, dict)
        and isinstance(node.get("openapi"), str)
        and isinstance(node.get("info"), dict)
        and isinstance(node.get("paths"), dict)
    )


def find_openapi_candidates(data: object) -> list:
    """Iterative (stack-based, not recursive) DFS over the parsed tree."""
    stack = [data]
    found = []
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if is_openapi_candidate(node):
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def extract_openapi_spec(html: str) -> dict:
    """Extract the single embedded OpenAPI spec from a documentation
    page's HTML. Raises ExtractionError (or its subclass
    AmbiguousExtractionError) on any failure to find exactly one.
    """
    data = extract_embedded_data(html)
    candidates = find_openapi_candidates(data)
    if len(candidates) == 0:
        raise ExtractionError("no OpenAPI candidate found in embedded data")
    if len(candidates) > 1:
        raise AmbiguousExtractionError(
            f"expected exactly 1 OpenAPI candidate, found {len(candidates)}"
        )
    return candidates[0]
