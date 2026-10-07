You are given the resource vocabulary of a REST API catalog (Atlassian Jira / Confluence). Each CONCEPTS line is:
token, occurrence count, products, excerpt — the excerpt is the first sentence of one operation's documentation for that resource.
For each concept token, list everyday words an ordinary end user (not a developer) might type instead of the token when
describing what they want: up to 5 SINGLE words and up to 5 TWO-WORD phrases (lowercase ASCII letters only; a phrase is two
words separated by one space). Use product UI vocabulary where you know it (for example "release" for version, "starred" for
favourite, "log work" or "time entry" for worklog, "blog entry" for blogpost, "workspace" for space). Never use a VERBS word as a
synonym or inside a phrase. Do not repeat the token itself. Do not include product names.
Output ONLY one JSON object: {"<word or two-word phrase>": ["<concept token>"], ...} — exactly one concept per key; if a key fits
several concepts, choose the single best one. No commentary.

CONCEPTS:
<one line per concept: "<token>\t<count>\t<products>\t<excerpt>">

VERBS:
<verb keys>
