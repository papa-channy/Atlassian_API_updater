You are given the resource vocabulary of a REST API catalog (Atlassian Jira / Confluence). Each CONCEPTS line is:
token, occurrence count, products, excerpt — the excerpt is the first sentence of one operation's documentation for that resource.
For each concept token, list everyday words an ordinary end user (not a developer) might type instead of the token when
describing what they want: up to 5 SINGLE words and up to 5 TWO-WORD phrases (lowercase ASCII letters only; a phrase is two
words separated by one space). Prefer the product's own user-interface vocabulary — the words shown on menus, tabs, buttons and
screens — over developer or API terms, and use the excerpt to understand what the resource is. Never use a VERBS word as a
synonym or inside a phrase. Do not repeat the token itself. Do not include product names.
DOCUMENTATION TITLES lists the current titles of the product's official help pages that mention each resource, and the attached
file doc-titles.txt lists all of them. These titles show the words the product's user interface and its users use for each
resource. Propose those words as synonyms. Include such a word even when it is itself a catalog term of a different product,
if users of this product call this resource by it.
Output ONLY one JSON object: {"<word or two-word phrase>": ["<concept token>"], ...} — exactly one concept per key; if a key fits
several concepts, choose the single best one. No commentary.

CONCEPTS:
<one line per concept: "<token>\t<count>\t<products>\t<excerpt>">

DOCUMENTATION TITLES:
<one line per concept title: "<token>\t<product>\t<title words>">

VERBS:
<verb keys>
