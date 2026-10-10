You are labelling search queries against an API catalog. The attached file is the complete operation catalog (one operation per
line: key, method, path, operationId, summary, tags). For each record below decide only from the catalog whether some operation
answers the query as an action a developer would call.

Rules:
- Use only the attached catalog. Do not guess operations that are not in it.
- answerable = true when one or more catalog operations directly perform what the query asks; list every such key in
  acceptable_keys (exact catalog keys, sorted ascending, no duplicates).
- answerable = false when no catalog operation performs it; acceptable_keys = [].
- Reply with exactly one JSON object and nothing else:
  {"labels": {"<id>": {"answerable": true|false, "acceptable_keys": ["..."]}, ...}} covering every id below.

Records:
{RECORDS}
