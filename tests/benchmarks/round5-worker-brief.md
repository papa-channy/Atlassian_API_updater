# Round 5 tuning worker brief (frozen at commit T)

You are the B..C tuning worker. You do not analyse queries, choose constants or choose aliases; the tools do.
Allowed inputs: this file, tests/benchmarks/search_queries.json (seed, regression_negative only), tests/benchmarks/round5-counterexample-reference.json, the frozen data files
under tools/atlassian_docs/intelligence/data/, the snapshot at $ATLASSIAN_DOCS_ROUND5_CACHE, and the tuning script.
Forbidden: anything under ~/.atlassian_api_updater/sealed/ or ~/.atlassian_api_updater/archive/, any *.enc file, any ChatGPT page,
docs/phase3-readiness.md.
Acceptance (Round 5 spec §4.2, byte-for-byte): tuning_accept := failed seed ids ⊆ {s-004, s-027, s-039} ∧ regression_effective == 14/14 ∧ fixture_positive == 23/23 ∧ fixture_negative_raw == 6/6 ∧ counterexample ok (no loss, no uncovered proposer key) ∧ no validation errors
regression_raw is recorded only. tuning_accept false -> status "failed" (F). tuning_accept true -> status "pending"; the candidate is
AC-valid (adoptable) only if the canonical full suite then passes (C); a red suite rejects it (X).
Expected wall-clock of step 2: about 18 minutes for the 23,328-point grid (memoized evaluator) plus the proposer trials; do not interrupt it.

Phase 0 (handshake): your first message begins with the marker ROUND5-WORKER-HANDSHAKE and contains the handshake instruction itself
(write {"worker_actor_id": <your agent id>, "session_id": <your session id or "not_available">} to
~/.atlassian_api_updater/round5-work/worker-handshake.json, read NO other file, run NO other command, report the single word HANDSHAKE).
You read this brief only after receiving a message that BEGINS WITH "run the brief procedure"; do not start the procedure below before that message.

Procedure (run from the repo root, exactly once; rerun only after a tool error, never after a valid result):
1. git status --porcelain --untracked-files=no   -> must be empty (otherwise stop and report).
2. python tests/tune_search_ranking.py --cache-dir "$ATLASSIAN_DOCS_ROUND5_CACHE" --note "round5 tuning run"
   (prints a JSON line with run_id, status and tuning_accept: "pending" = candidate policy written, "failed" = log only)
3. python -m unittest discover -s tests -t . > ~/.atlassian_api_updater/round5-work/suite-<run_id>.txt 2>&1; echo "exit_code: $?" >> ~/.atlassian_api_updater/round5-work/suite-<run_id>.txt
4. If step 2 exited 0 and the suite exit code is 0:
     python tests/tune_search_ranking.py --adopt <run_id>
     git add tools/atlassian_docs/intelligence/data/search_ranking.json tools/atlassian_docs/intelligence/data/search_aliases.json
             tests/benchmarks/search-tuning-round5.jsonl
     git commit -m "round5: tuning run (one-way pipeline, adopted <run_id>)" + the project trailer.
   If step 2 exited 0 but the suite exit code is not 0:
     python tests/tune_search_ranking.py --reject <run_id> --reason full-suite-failed --evidence ~/.atlassian_api_updater/round5-work/suite-<run_id>.txt
       (stores the failure signature on the log line, then restores the B policy files)
     git add tests/benchmarks/search-tuning-round5.jsonl
     git commit -m "round5: tuning run rejected (full suite failed)" + trailer.
   If step 2 exited 1 (tuning_accept false): commit ONLY tests/benchmarks/search-tuning-round5.jsonl with message
     "round5: tuning failed (log only)" + trailer; do not touch the data files.
   If step 2 exited 2: do not commit; report the stderr verbatim.
Report: exit codes, the JSON summary lines printed by step 2, the --adopt/--reject output, the commit sha, the suite file path and — when
rejected — the failing test ids verbatim. Nothing else.
