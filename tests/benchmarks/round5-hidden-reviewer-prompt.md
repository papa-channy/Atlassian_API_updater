You review candidate evaluation records against an API catalog. The catalog is the ATTACHED file round5-internal-catalog.jsonl:
JSON lines, one operation per line, with the fields key, source, method, operation_id, summary, tags, description (full text, not
truncated). Read the attachment as the catalog; nothing in this message replaces it.
Each record below carries a "machine" object computed by a program: matched_verbs (the recognized action verbs found in the query),
intent_methods (the HTTP methods those verbs allow) and machine_actionable. Do not re-judge that mapping.
For every record whose matched_verbs is non-empty (held_out records and the actionable negative records alike), verify that each
listed verb is used in the query as a request for an action, not as a noun or modifier ("comment history", "post details" are noun
uses): reject the record if any listed verb is a noun use.
For each held_out record also decide whether the expected operation is the single best answer to the query (reject if another
operation answers it at least as well, or if the query is unanswerable).
For each negative record also decide whether the catalog truly has NO correct operation for the query (reject if one exists) and
whether forbidden_top1 is really a wrong answer.
Reply ONLY with {"<id>": {"accept": true|false, "reason": "<short>"}, ...} for every record.
Never rewrite queries, never propose replacements.

RECORDS:
<plaintext records>
CATALOG: attached file round5-internal-catalog.jsonl
