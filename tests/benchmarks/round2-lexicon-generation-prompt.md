You are given a list of concept tokens from a REST API catalog (Jira / Confluence). Each line is: token, occurrence count, products.
For each concept token, list up to 5 single English words (lowercase, letters only, one word each, no verbs) that an ordinary
end user might type instead of that token when describing what they want (for example a colloquial or business synonym).
Do not repeat the token itself. Do not invent multi-word phrases. Do not include product names.
Output ONLY one JSON object: {"<synonym>": ["<concept token>"], ...} — one concept per synonym; if a synonym fits several
concepts, choose the single best one. No commentary.

CONCEPT TOKENS:
<one line per token: "<token>\t<count>\t<products>">
