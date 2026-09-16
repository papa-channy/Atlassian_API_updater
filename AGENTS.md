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
