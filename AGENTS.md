## Atlassian APIs

Before implementing or modifying Jira or Confluence integrations, run:

    python -m tools.atlassian_docs

Use the OpenAPI specifications under .atlassian-docs/ as the primary
API reference. The cached files always represent the latest
successfully extracted official API specifications.

Do not assume API major versions from memory. Do not rely on
memorized Jira or Confluence endpoints when the local OpenAPI
specification provides the relevant information.

- jira-platform.json  → Jira Platform APIs
- jira-software.json  → Jira Software / Agile APIs
- confluence.json     → Confluence APIs

API versions may change over time without changing these local file
names. jira-software's api_version may legitimately be null/unknown —
this does not mean the cache is invalid.

## Exit codes and flags

- `python -m tools.atlassian_docs` must be run from the repository root — the cache path is resolved relative to the current working directory.
- `--force` ignores the 24h TTL and re-extracts immediately.
- `--status` shows cached state without extracting anything; always exits 0.
- Exit code from a normal run: `0` = every source usable, `1` = degraded (some source fell back to an existing cache after a failed refresh), `2` = unavailable (some source has no usable cache at all). Treat exit 2 as a signal that Jira/Confluence work should not proceed until this is investigated.

## Atlassian OpenAPI Intelligence MCP (Phase 2)

Prefer the MCP server over reading `.atlassian-docs/*.json` directly. Start it from the
repository root: `python -m tools.atlassian_docs.mcp` (needs `pip install -r requirements-mcp.txt`).
In Claude Code it is registered by the project `.mcp.json` at the repository root (or run
`claude mcp add atlassian-openapi -- python -m tools.atlassian_docs.mcp` from the repository root);
Claude Code starts project-scoped servers with the project root as the working directory, which the cache path needs.

Tools: `search_operations` → `get_operation` → `get_schema` → `build_request_template` → `check_request`;
`get_api_status` and `refresh_api_docs` for freshness. Every result carries `provenance`: if a source
is `stale`, the answer comes from the last good spec (`active_*` fields say which). `check_request.compatible`
only means the fixed rule set found no error. The server never calls Jira/Confluence APIs and never
produces server URLs or credentials. Without the MCP SDK, fall back to the Phase 1 CLI and the cached files.

- Prefer the `key` from an exact identifier search (operationId or canonical key, no spaces) — that result is pinned first.
- Each `search_operations` result's `signals` explains why it ranked; add a product word (`jira`/`confluence`) to the query to disambiguate between products.
- If `check_request` returns `body_check: "structural"`, the body was not fully validated (see `body_check_reason`); template headers with `effective_required: true` (including spec-external quirk headers) must be sent.

## Search quality tooling freeze (Round 2)

The files listed in `tests.benchmarks.evaluator.TOOLING_FILES` (the benchmark evaluator, the diagnostic script,
the tuning pipeline, the seal/alias-candidates/concept-lexicon tools, and their integrity tests) are immutable
from each round's `housekeeping_commit` through that round's terminal commit (D on success, F on a failed tuning
run, or X on an aborted one). Do not edit any of them in that window, even for an apparently unrelated fix — a
tool defect found before T must be corrected in an H′ commit instead, and one found after T ends the round.
