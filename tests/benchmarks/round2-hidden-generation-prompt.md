You are creating an evaluation set for an API operation search engine over the Atlassian Jira / Confluence REST catalog.
Below is the catalog: one line per operation with key, source, method, summary, tags (tab-separated).
Produce ONLY one JSON object: {"held_out": [16 records], "negative": [8 records]}.
held_out record: {"id": "h-001".."h-016", "query": "...", "expected_top1_any": ["<key>"], "forbidden_top1": [], "origin": "held_out-r2",
  "failure_classes": [], "ambiguous": false}
negative record: {"id": "n-001".."n-008", "query": "...", "expected_top1_any": [], "forbidden_top1": ["<key>"], "origin": "negative-r2",
  "failure_classes": [], "ambiguous": false}
Rules checked by a program (a violation is sent back to you by rule id):
- words: every query has 3 to 7 words of natural end-user phrasing.
- operationId: the set of words in a query (lowercased, split on non-letters, words shorter than 2 letters dropped, ignoring
  a/an/the/to/of/for/in/on/at/and/or/with/by/from/is/are/be/this/that) must not equal the set of words of any operation's
  operationId (camelCase split into words the same way).
- summary/tags: after removing those same small words, a held_out query must not contain two consecutive words that also
  appear consecutively in the expected operation's summary or in one of its tags.
- distribution (held_out): at least 6 jira-platform, 4 jira-software, 5 confluence expected operations; at least 4 GET,
  4 POST, 2 PUT, 2 DELETE; at least 4 queries contain "jira" or "confluence" and at least 9 contain neither.
- negative-phrase: a negative query's words (same normalization, singularized) must not equal, in order, the words of any
  operation summary or of the last literal segment of any operation path.
- schema / catalog: ids and origins exactly as above; every key must exist in the catalog.
- reuse (checker-only, you cannot see the existing benchmark): queries that repeat an existing benchmark query or its word
  set are rejected; if that happens you will be asked for a replacement with rule id "reuse".
negative: the query must have NO correct operation in the catalog; forbidden_top1 is the tempting wrong operation.
Replacement contract: if a later message consists only of lines "record <id> rejected: <rule-id>" (one rule id per record, chosen by the
fixed priority schema > catalog > words > operationId > summary/tags > negative-phrase > reuse), respond ONLY with a JSON
array containing exactly one replacement record for each listed id, in the same record schema and with the same id.
Do not repeat or modify any other record. If the message says "distribution rejected", it lists all 16 held_out ids:
return 16 replacement held_out records that satisfy the distribution rule.
No commentary.

CATALOG:
<generator catalog lines>
