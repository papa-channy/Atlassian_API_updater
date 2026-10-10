You are creating an evaluation set for an API operation search engine over the Atlassian Jira / Confluence REST catalog.
Below are VERB_METHODS — a JSON object mapping every action verb the engine recognizes to the HTTP methods it may express — and the
catalog: one line per operation with key, source, method, summary, tags (tab-separated).
Produce ONLY one JSON object: {"held_out": [16 records], "negative": [8 records]}.
held_out record: {"id": "h-001".."h-016", "query": "...", "expected_top1_any": ["<key>"], "forbidden_top1": [], "origin": "held_out-r5",
  "failure_classes": [], "ambiguous": false}
negative record: {"id": "n-001".."n-008", "query": "...", "expected_top1_any": [], "forbidden_top1": ["<key>"], "origin": "negative-r5",
  "failure_classes": [], "ambiguous": false}
Rules checked by a program (a violation is sent back to you by rule id):
- words: every query has 3 to 7 words of natural end-user phrasing.
- ascii: a query uses ASCII English letters, digits, spaces, apostrophes and hyphens only — no accents, no other scripts, no other punctuation.
- actionable (held_out): Every held_out query must express a single actionable API intent using at least one action verb whose HTTP
  method matches the expected operation; if several recognized verbs occur, their allowed-method intersection must be non-empty.
  Precisely: the query contains at least one VERB_METHODS key (matched as a lowercase word); the intersection of the method lists of
  all contained keys is non-empty; and the expected operation's method is inside that intersection.
- negative-distribution: Exactly 4 negative queries must be actionable under the frozen verb-method inventory (a recognized action
  verb is present and the allowed-method intersection is non-empty) and exactly 4 must be non-actionable; prefer no recognized verb
  for the non-actionable half — do not manufacture conflicting multi-verb phrasings merely to force abstention.
- negative-method (actionable negatives only): the method of the forbidden_top1 operation must be inside the query's allowed-method
  intersection — a wrong operation that merely has the wrong HTTP method is too easy.
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
fixed priority schema > catalog > words > ascii > actionable > negative-method > operationId > summary/tags > negative-phrase > reuse), respond
ONLY with a JSON array containing exactly one replacement record for each listed id, in the same record schema and with the same id.
A later message may also contain lines "record <id> rejected: reviewer": "reviewer" is a valid semantic-review replacement request (a
human-language review found the expected answer not the single best one, the verb used as a noun, or a negative that has a correct
answer); it is not a machine rule id and takes no part in the priority above; respond with the same JSON array of replacement records.
Do not repeat or modify any other record. If a later message starts with "distribution rejected" and lists all 16 held_out ids, return a
JSON array of 16 replacement held_out records (same ids) that satisfy the distribution rule. If a later message starts with
"negative distribution rejected" and lists all eight negative ids, reply ONLY with a JSON array of exactly eight replacement negative
records, one per listed id, preserving those ids; together they must satisfy exactly 4 actionable / 4 non-actionable. Do not return
held_out records or the outer object.
No commentary.

VERB_METHODS:
<verb methods json>

CATALOG:
<generator catalog lines>
