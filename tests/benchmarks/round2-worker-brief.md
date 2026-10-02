# Round 2 tuning worker brief (frozen at commit T)

You are the B..C tuning worker. You do not analyse queries, choose constants or choose aliases; the tools do.
Allowed inputs: this file, tests/benchmarks/search_queries.json (seed, regression_negative only), the frozen data files
under tools/atlassian_docs/intelligence/data/, the snapshot at $ATLASSIAN_DOCS_ROUND2_CACHE, and the tuning script.
Forbidden: anything under ~/.atlassian_api_updater/sealed/, any *.enc file, any ChatGPT page, docs/phase3-readiness.md.

Procedure (run from the repo root, exactly once; rerun only after a tool error, never after a valid result):
1. git status --porcelain --untracked-files=no   -> must be empty (otherwise stop and report).
2. python tests/tune_search_ranking.py --cache-dir "$ATLASSIAN_DOCS_ROUND2_CACHE" --note "round2 tuning run"
   (prints a JSON line with run_id and status: "pending" = candidate policy written, "failed" = log only)
3. python -m unittest discover -s tests -t .
4. If step 2 exited 0 and step 3 is OK:
     python tests/tune_search_ranking.py --adopt <run_id>
     git add tools/atlassian_docs/intelligence/data/search_ranking.json tools/atlassian_docs/intelligence/data/search_aliases.json
             tests/benchmarks/search-tuning-round2.jsonl
     git commit -m "round2: tuning run (one-way pipeline, adopted <run_id>)" + the project trailer.
   If step 2 exited 0 but step 3 FAILED (run step 3 as
     python -m unittest discover -s tests -t . > ~/.atlassian_api_updater/round2-work/suite-<run_id>.txt 2>&1
   so the red output is captured BEFORE anything is rolled back):
     python tests/tune_search_ranking.py --reject <run_id> --reason full-suite-failed --evidence ~/.atlassian_api_updater/round2-work/suite-<run_id>.txt
       (stores the failure signature on the log line, then restores the B policy files)
     git add tests/benchmarks/search-tuning-round2.jsonl
     git commit -m "round2: tuning run rejected (full suite failed)" + trailer.
   If step 2 exited 1 (tuning_failed): commit ONLY tests/benchmarks/search-tuning-round2.jsonl with message
     "round2: tuning failed (log only)" + trailer; do not touch the data files.
   If step 2 exited 2: do not commit; report the stderr verbatim.
Report: exit codes, the JSON summary lines printed by step 2, the --adopt/--reject output, the commit sha, and — when rejected — the
evidence file path plus the failing test ids verbatim. Nothing else.
