Below is a JSON object mapping a candidate synonym — a single English word or a two-word phrase an end user might type — to one
API concept token of an issue-tracking / wiki product. For each entry answer whether an ordinary user would plausibly use the
synonym to mean that concept (a two-word phrase must mean the concept as a whole, e.g. "time entry" -> worklog is true,
"issue page" -> page is false). Reply ONLY with a JSON object {"<synonym>": true|false, ...} covering every key. Do not add,
rename or re-target any entry.

ENTRIES:
<the "lexicon" object of lexicon_structural.json>
