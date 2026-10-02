You review candidate evaluation records against an API catalog. The catalog is given as JSON lines, one operation per
line, with the fields key, source, method, operation_id, summary, tags, description (full text, not truncated).
For each held_out record decide whether the expected operation is the single best answer to the query
(reject if another operation answers it at least as well, or if the query is unanswerable). For each negative record
decide whether the catalog truly has NO correct operation for the query (reject if one exists) and whether forbidden_top1
is really a wrong answer. Reply ONLY with {"<id>": {"accept": true|false, "reason": "<short>"}, ...} for every record.
Never rewrite queries, never propose replacements.

RECORDS:
<plaintext records>
CATALOG (JSON lines):
<internal catalog lines>
