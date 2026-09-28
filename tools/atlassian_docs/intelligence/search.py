"""Weighted lexical operation search: tokenizer + prebuilt index (spec §13)."""
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from . import schemas

STOPWORDS = frozenset("a an the to of for in on at and or with by from is are be this that".split())
FIELD_WEIGHTS = {"operation_id": 5, "summary": 4, "tags": 3, "path": 3,
                 "schema_names": 2, "method": 1, "description": 1}
DESCRIPTION_INDEX_CHARS = 1000
_CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])")        # fooBar -> foo Bar
_CAMEL_2 = re.compile(r"([A-Z]{2,})([A-Z][a-z])")  # JQLQuery -> JQL Query
_SPLIT = re.compile(r"[^a-z0-9]+")


def tokenize(text: Optional[str]) -> frozenset:
    if not text:
        return frozenset()
    text = _CAMEL_2.sub(r"\1 \2", _CAMEL_1.sub(r"\1 \2", text)).lower()
    out = set()
    for tok in _SPLIT.split(text):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        out.add(tok)
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
            out.add(tok[:-1])
    return frozenset(out)


@dataclass(frozen=True)
class IndexEntry:
    key: str
    fields: Mapping[str, frozenset]


@dataclass(frozen=True)
class SearchIndex:
    entries: tuple


def _schema_names(op: Any, component_schemas: dict = None) -> frozenset:
    names: set = set()
    if op.request_body:
        for media in op.request_body.content:
            names.update(schemas.collect_local_ref_names(media.schema))
            # Resolve references to find nested schemas
            if component_schemas and media.schema and media.schema.get("$ref"):
                ref = media.schema.get("$ref")
                schema_name = ref.split("/")[-1] if "/" in ref else None
                if schema_name and schema_name in component_schemas:
                    resolved = component_schemas[schema_name]
                    names.update(schemas.collect_local_ref_names(resolved))
    for resp in op.responses:
        for media in resp.content:
            names.update(schemas.collect_local_ref_names(media.schema))
            # Resolve references to find nested schemas
            if component_schemas and media.schema and media.schema.get("$ref"):
                ref = media.schema.get("$ref")
                schema_name = ref.split("/")[-1] if "/" in ref else None
                if schema_name and schema_name in component_schemas:
                    resolved = component_schemas[schema_name]
                    names.update(schemas.collect_local_ref_names(resolved))
    for p in op.parameters:
        names.update(schemas.collect_local_ref_names(p.schema))
    toks: set = set()
    for n in names:
        toks.add(n.lower())          # exact type name, e.g. "issuecreatemetadata"
        toks |= tokenize(n)          # split parts, e.g. "issue", "create", "metadata"
    return frozenset(toks)


def build_index(operations: tuple, component_schemas: dict = None) -> SearchIndex:
    entries = []
    for op in operations:
        fields = {
            "operation_id": tokenize(op.operation_id),
            "summary": tokenize(op.summary),
            "tags": frozenset().union(*(tokenize(t) for t in op.tags)) if op.tags else frozenset(),
            "path": tokenize(op.path),
            "schema_names": _schema_names(op, component_schemas),
            "method": frozenset({op.method.lower()}),
            "description": tokenize((op.description or "")[:DESCRIPTION_INDEX_CHARS]),
        }
        entries.append(IndexEntry(op.key, fields))
    return SearchIndex(tuple(entries))
