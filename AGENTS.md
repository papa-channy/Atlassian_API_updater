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
