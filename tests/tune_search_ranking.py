"""One-way, deterministic Round-N tuning (Round 2 spec §5.5/§7.2):

    python tests/tune_search_ranking.py --cache-dir S [--dry-run] [--note TEXT]     # pipeline, exit 0 pending / 1 failed / 2 error
    python tests/tune_search_ranking.py --adopt RUN_ID                               # after the full suite passed: marks the
                                                                                     # log line adopted only (the worker commits)
    python tests/tune_search_ranking.py --verify --cache-dir S                       # replay the adopted run

tune_round(b_aliases, b_ranking, snapshot, frozen_candidates, seed, regression) -> (final_constants, alias_patch, log):
  0. baseline_checked: working tree == B baseline (alias/ranking canonical hashes == alias_candidates.generated_from.inputs)
     and verify_freeze(S) ok; otherwise exit 2 - restore B first (git checkout <B> -- <files>).
  1. constants_selected: select_candidate over the whole grid, evaluated with the B aliases (exactly once).
  2. aliases_proposed: propose_aliases at those constants (exactly once; frozen candidates only, 1 target each).
  3. final_check: seed+regression perfect -> policy files written, log status "pending" (adoption needs --adopt after the
     canonical full test suite passed); else status "failed" (tuning_failed), nothing written but the log.
No constant reselection after aliases, no second proposal. --dry-run writes nothing and prints the would-be log line.
Fixture hard constraint (spec v1.14, AC-06a): every candidate - each constants grid point (with the B aliases) and each
alias/rule trial of the proposer - must pass the r0 fixture suite (the 23 seed / 6 negative r0 records on
make_state("jira-platform", "jira-software", "confluence"), as in tests/intelligence/test_search.py). A failing candidate
is excluded from selection and logged under `fixture_fail`; it is a constraint, never an objective.
"""
import argparse, copy, dataclasses, datetime, hashlib, itertools, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time, uuid
from types import MappingProxyType
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.benchmarks import evaluator as ev  # noqa: E402
from tests.benchmarks import round_seal as rs  # noqa: E402
from tests.benchmarks.evaluator import evaluate  # noqa: E402
from tools.atlassian_docs import storage, sync  # noqa: E402
from tools.atlassian_docs.intelligence import RegistryManager, policy, search_operations  # noqa: E402

ROUND = ev.current_round()["round"]
BENCH_PATH = ROOT / "tests" / "benchmarks" / "search_queries.json"
LOG_REL = f"tests/benchmarks/search-tuning-round{ROUND}.jsonl"
LOG_PATH = ROOT / LOG_REL
RANKING_PATH = policy.DATA_DIR / "search_ranking.json"
ALIASES_PATH = policy.DATA_DIR / "search_aliases.json"
CANDIDATES_PATH = policy.DATA_DIR / "alias_candidates.json"
CONSTANT_KEYS = policy.CONSTANT_KEYS
MAGNITUDE_KEYS = tuple(k for k in CONSTANT_KEYS if k != "path_unmatched_cap")
_BENCH = json.loads(BENCH_PATH.read_text(encoding="utf-8"))
SEED_TOTAL, REGRESSION_TOTAL = len(_BENCH["seed"]), len(_BENCH["regression_negative"])
SOURCES = ("jira-platform", "jira-software", "confluence")
BUDGET, PER_SEED = 15, 2
BONUS_KEYS = ("path_coverage_bonus", "method_order_bonus")      # spec §3.4: conservative tie-break, in this order
FIXTURE_COUNTS = (23, 6)
EVENTS = ("baseline_checked", "constants_selected", "aliases_proposed", "final_check")


# ---- pure helpers (unit-tested in tests/test_tune_search_ranking.py) ----

def grid_points(grid) -> list:
    """Cartesian product of the grid in CONSTANT_KEYS order; ascending values -> lexicographic order."""
    axes = [sorted(grid[k]) for k in CONSTANT_KEYS]
    return [dict(zip(CONSTANT_KEYS, combo)) for combo in itertools.product(*axes)]


def l1_index_distance(point, baseline, grid) -> int:
    return sum(abs(list(grid[k]).index(point[k]) - list(grid[k]).index(baseline[k])) for k in CONSTANT_KEYS)


def select_candidate(results, baseline, grid, seed_total=SEED_TOTAL, regression_total=REGRESSION_TOTAL) -> dict:
    """spec §3.4: results = (point, seed_passed, regression_EFFECTIVE_passed). (1) perfect points only, else max seed then max
    regression; (2) smaller (path_coverage_bonus, method_order_bonus); (3) min L1 grid-index distance to the baseline; (4) min
    magnitude sum; (5) lexicographic 8-tuple."""
    if not results:
        raise ValueError("no results to select from")
    pool = [p for p, s, r in results if s == seed_total and r == regression_total]
    if not pool:
        best = max((s, r) for _, s, r in results)
        pool = [p for p, s, r in results if (s, r) == best]
    return dict(min(pool, key=lambda p: (tuple(p[k] for k in BONUS_KEYS), l1_index_distance(p, baseline, grid),
                                          sum(p[k] for k in MAGNITUDE_KEYS), tuple(p[k] for k in CONSTANT_KEYS))))


def cross_check_mismatch(slow_s, slow_r, fast_s, fast_r) -> list:
    """Round 3 H' (I2): identity check for the memoized/production cross-check at the selected point, not just
    pass counts. Compares the sorted failing-record ids for seed and for regression between the two paths and
    returns the sorted ids where they disagree (ids only, never queries); empty when the two paths agree."""
    def ids(res):
        return sorted(f["id"] for f in res["failed"])
    mismatched = set()
    if ids(slow_s) != ids(fast_s):
        mismatched |= set(ids(slow_s)) ^ set(ids(fast_s))
    if ids(slow_r) != ids(fast_r):
        mismatched |= set(ids(slow_r)) ^ set(ids(fast_r))
    return sorted(mismatched)


def plan_effects(dry_run: bool, perfect: bool) -> dict:
    """--dry-run has no side effects; a normal run always logs, but writes constants only for a perfect pick."""
    return {"write_constants": perfect and not dry_run, "append_log": not dry_run}


def dirty_paths(porcelain: str) -> list:
    """Tracked paths with uncommitted changes (git status --porcelain), excluding untracked files and the log."""
    out = set()
    for row in porcelain.splitlines():
        if len(row) < 4 or row.startswith("??"):
            continue
        path = row[3:].split(" -> ")[-1].strip().strip('"')
        if path != LOG_REL:
            out.add(path)
    return sorted(out)


# ---- evaluation against the snapshot ----

def _search_fn(state):
    """(top-5 keys, actionable) - the Round 3 evaluator contract."""
    def fn(q):
        out = search_operations(state, q, limit=5)
        return [r["key"] for r in out.get("results", [])], bool(out.get("actionable", True))
    return fn


def ranking_with(rp, point):
    return dataclasses.replace(rp, constants=MappingProxyType(dict(point)),
                               sha256=policy.canonical_sha256({"tuning_point": dict(point)}))


def evaluate_point(state, rp, point, bench, alias_policy):
    """Production path: seed raw top-1, regression_negative raw + effective (spec §4)."""
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), \
            mock.patch.object(policy, "aliases", return_value=alias_policy):
        fn = _search_fn(state)
        return evaluate(bench["seed"], fn, section="seed"), evaluate(bench["regression_negative"], fn, section="regression_negative")


def fixture_negative_diagnostic(state, rp, point, bench_r0, alias_policy) -> dict:
    """AC-R3-11a `fixture_negative.effective_diagnostic`: the 6 r0 negatives judged like regression_negative (raw + effective) -
    recorded on the log line only; acceptance uses fixture_failures (raw)."""
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), \
            mock.patch.object(policy, "aliases", return_value=alias_policy):
        return evaluate(bench_r0["regression_negative"], _search_fn(state), section="regression_negative")


def top5(state, rp, point, query, alias_policy):
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), \
            mock.patch.object(policy, "aliases", return_value=alias_policy):
        return [(r["key"], r["score"], r.get("signals")) for r in search_operations(state, query, limit=5).get("results", [])]


def fixture_bench(bench) -> dict:
    """The r0 fixture suite (spec v1.14 AC-06a): seed / regression_negative records with an -r0 origin."""
    out = {"seed": [r for r in bench["seed"] if r["origin"].endswith("-r0")],
           "regression_negative": [r for r in bench["regression_negative"] if r["origin"].endswith("-r0")]}
    if (len(out["seed"]), len(out["regression_negative"])) != FIXTURE_COUNTS:
        raise SystemExit(f"error: r0 fixture suite must have {FIXTURE_COUNTS} records, got "
                         f"{(len(out['seed']), len(out['regression_negative']))}")
    return out


def fixture_state():
    """The same fixture registry tests/intelligence/test_search.py::test_seed_passes_on_fixtures uses."""
    from tests.intelligence.helpers import make_state
    return make_state(*SOURCES)


def fixture_failures(state, rp, point, bench_r0, alias_policy) -> list:
    """Sorted ids of r0 fixture records failing at `point` - RAW judgement for both sets (spec §3.4 fixture hard constraint)."""
    with mock.patch.object(policy, "ranking", return_value=ranking_with(rp, point)), \
            mock.patch.object(policy, "aliases", return_value=alias_policy):
        fn = _search_fn(state)
        s, r = evaluate(bench_r0["seed"], fn), evaluate(bench_r0["regression_negative"], fn)
    return sorted(f["id"] for f in s["failed"] + r["failed"])


class GridEvaluator:
    """Memoized grid-stage evaluation (spec §3.4 v1.22). Per query the lexical rows (entry, op, lexical) are computed ONCE per alias
    state with the production `_score` (terminal_full fixed at construction, spec §3.8); every grid point re-runs only the
    production `_structural_signals` and reproduces search_operations' ordering: `_order_key` (tier, -final, tiebreak,
    deprecated, key), DEPRECATED_FACTOR, zero clamp, limit. Bench queries contain whitespace, so exact-key pinning and the
    identifier-query exemption never apply; a whitespace-free query falls back to search_operations."""
    def __init__(self, state, queries, alias_policy, terminal_full=False):
        from tools.atlassian_docs.intelligence import search as S
        self.S, self.state, self.ap, self.rows, self.meta, self.terminal_full = S, state, alias_policy, {}, {}, terminal_full
        for q in dict.fromkeys(queries):
            unigrams, exp = S.tokenize_unigrams(q), S.expand_query(q, alias_policy)
            lexical_base, rows = exp.base | S.joined_query_forms(q), []
            for name in sorted(state.registry.sources):
                sr = state.registry.sources[name]
                for entry in sr.search_index.entries:
                    lexical, _ = S._score(entry, lexical_base, exp.direct, exp.cond, unigrams, alias_policy, terminal_full)
                    if lexical > 0:
                        rows.append((entry, sr.operations_by_key[entry.key], lexical))
            self.rows[q], self.meta[q] = rows, (unigrams, exp.all, S.joined_query_forms(q))

    def ranked(self, query, rp, limit=5):
        if query not in self.rows or not any(ch.isspace() for ch in query.strip()):
            with mock.patch.object(policy, "ranking", return_value=rp), mock.patch.object(policy, "aliases", return_value=self.ap):
                return _search_fn(self.state)(query)
        unigrams, exp_all, joined = self.meta[query]
        assert rp.ordering_rules["terminal_alias_full_weight"] == self.terminal_full, "GridEvaluator built for a different terminal_alias_full_weight"
        intent = self.S.method_intent(unigrams, rp.verb_methods)
        rules = self.S.ordering_rules_for(rp.ordering_rules, False)                                  # whitespace query: never an identifier query
        verbs, allowed = intent
        preferred = rp.verb_method_order[verbs[0]][0] if verbs else None
        cands = []
        for entry, op, lexical in self.rows[query]:
            structural, _ = self.S._structural_signals(entry, unigrams, exp_all, rp, intent)
            final = max(lexical + structural, 0.0) * (self.S.DEPRECATED_FACTOR if op.deprecated else 1.0)
            if final == 0.0:
                continue
            cands.append((final, op.deprecated, op.key, entry.method))
        cands.sort(key=lambda c: self.S._order_key(rules, allowed, preferred, c[0], c[3], c[1], c[2]))
        return [c[2] for c in cands[:limit]], bool(intent[1])


def evaluate_point_fast(ge, rp, point, bench):
    rpp = ranking_with(rp, point); fn = lambda q: ge.ranked(q, rpp)
    return evaluate(bench["seed"], fn, section="seed"), evaluate(bench["regression_negative"], fn, section="regression_negative")


def fixture_failures_fast(ge, rp, point, bench_r0) -> list:
    rpp = ranking_with(rp, point); fn = lambda q: ge.ranked(q, rpp)
    s, r = evaluate(bench_r0["seed"], fn), evaluate(bench_r0["regression_negative"], fn)
    return sorted(f["id"] for f in s["failed"] + r["failed"])


def write_constants(point, path=RANKING_PATH) -> None:
    """Rewrite ONLY the `constants` object; verify the frozen structure hash is unchanged, else restore."""
    original = path.read_text(encoding="utf-8")
    before = policy.load_ranking(path)
    rows = (CONSTANT_KEYS[:2], CONSTANT_KEYS[2:5], CONSTANT_KEYS[5:6], CONSTANT_KEYS[6:])          # the frozen file's layout
    body = ",\n    ".join(", ".join(f'"{k}": {json.dumps(point[k])}' for k in row) for row in rows if row)
    text, n = re.subn(r'"constants": \{[^}]*\}', lambda _m: '"constants": {\n    ' + body + "\n  }", original)
    if n != 1:
        raise SystemExit("could not locate a single 'constants' object in search_ranking.json")
    path.write_text(text, encoding="utf-8")
    after = policy.load_ranking(path)
    if after.structure_sha256 != before.structure_sha256 or dict(after.constants) != dict(point):
        path.write_text(original, encoding="utf-8")
        raise SystemExit("constants rewrite changed the frozen structure; restored the original file")


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def build_state(cache_copy: pathlib.Path):
    """Same construction as tests/diag_search_queries.py; caller patches storage.CACHE_DIR to cache_copy."""
    mgr = RegistryManager(sync_all=lambda force=False: [sync.SyncResult(s, "ok") for s in SOURCES])
    mgr.start()
    return mgr.active


# ---- proposer, validator, replay, hashes ----

def _norm_tokens(text):
    from tests.benchmarks.alias_candidates_tool import norm_tokens
    return norm_tokens(text)


def round_note(word, sid, target) -> dict:
    return {"origin": f"round{ROUND}", "seed_query_id": sid, "candidate_word": word, "failure_classes": ["R6"],
            "evidence": f"alias {word} -> {target} for {sid} (frozen candidate, deterministic atomic-action proposer)"}


def alias_patch(base_raw, working_raw) -> dict:
    return {"aliases": {w: v for w, v in working_raw["aliases"].items() if w not in base_raw["aliases"]},
            "rules": working_raw["rules"][len(base_raw["rules"]):],
            "notes": {k: n for k, n in working_raw["notes"].items() if k not in base_raw["notes"]}}


def strip_round_entries(raw, round) -> dict:
    """Reconstruct the B state: drop every alias/rule whose note has origin round{N} (rules are a suffix)."""
    origin, out = f"round{round}", copy.deepcopy(raw)
    for key, n in list(out["notes"].items()):
        if n.get("origin") == origin:
            del out["notes"][key]
            if not key.startswith("rule:"):
                out["aliases"].pop(key, None)
    keep = [i for i in range(len(out["rules"])) if raw["notes"].get(f"rule:{i}", {}).get("origin") != origin]
    out["rules"] = [out["rules"][i] for i in keep]
    return out


def atomic_actions(cands, sid, working) -> list:
    """spec §6: this seed's (candidate_word, target) pairs in tuple order; words already aliased in the working state excluded."""
    return sorted((w, t) for w, c in cands.items() if sid in c["seed_ids"] and w not in working["aliases"] for t in c["targets_by_seed"][sid])


def trial_order(actions) -> list:
    """size-1 actions in tuple order, then size-2 combinations with DISTINCT candidate words in tuple order."""
    return [(a,) for a in actions] + [(a, b) for a, b in itertools.combinations(actions, 2) if a[0] != b[0]]


def apply_actions(working, actions, sid):
    trial = copy.deepcopy(working)
    for word, target in actions:
        trial["aliases"][word] = [target]; trial["notes"][word] = round_note(word, sid, target)
    return trial


def propose_aliases(eval_fn, bench, base_raw, cands, budget=BUDGET, per_seed=PER_SEED, fixture_fn=None):
    """spec §6 atomic-action contract: seeds in id order; each seed re-evaluated against the working state first
    (resolved_by_prior_change); seeds without R6 skipped; trials in trial_order(); every trial starts from the current working
    snapshot (failed trials are not accumulated); the first trial that fixes the seed without breaking a passing seed, a
    regression record (effective) or the fixture suite is committed. <= per_seed actions per seed, <= budget in total. Direct
    aliases only (no rules, spec §2)."""
    working = copy.deepcopy(base_raw)
    seed_fail, _ = eval_fn(working)
    patch = {"resolved_by_prior_change": [], "not_r6": [], "unresolved": [], "fixture_fail": [], "trials": 0, "actions_by_seed": {}}
    accepted_n, by_id = 0, {r["id"]: r for r in bench["seed"]}

    def ok(trial, sid, cur_fail, cur_reg, desc):
        patch["trials"] += 1
        f, r = eval_fn(trial)
        if not (sid not in f and f <= (cur_fail - {sid}) and r <= cur_reg):
            return False
        bad = list(fixture_fn(trial)) if fixture_fn is not None else []
        if bad:
            patch["fixture_fail"].append({**desc, "seed_query_id": sid, "failing": bad})
        return not bad

    for sid in sorted(seed_fail):
        cur_fail, cur_reg = eval_fn(working)
        if sid not in cur_fail:
            patch["resolved_by_prior_change"].append(sid); continue
        if "R6" not in (by_id[sid].get("failure_classes") or ()):
            patch["not_r6"].append(sid); continue
        found = None
        for combo in trial_order(atomic_actions(cands, sid, working)):
            if len(combo) > per_seed or accepted_n + len(combo) > budget:
                continue
            trial = apply_actions(working, combo, sid)
            if ok(trial, sid, cur_fail, cur_reg, {"kind": "alias", "actions": [list(a) for a in combo]}):
                found = (trial, combo); break
        if found is None:
            patch["unresolved"].append(sid); continue
        working, accepted_n = found[0], accepted_n + len(found[1])
        patch["actions_by_seed"][sid] = [list(a) for a in found[1]]
    patch.update(alias_patch(base_raw, working))
    return working, patch


def validate_alias_change(before_raw, after_raw, cands, queries, classes, budget=BUDGET, per_seed=PER_SEED) -> list:
    """Pure shape check (spec §7.2); replay equality is verify_replay. classes: {seed_id: bench failure_classes};
    every added note and its seed must carry R6."""
    out = [f"top-level {k!r} changed" for k in ("version", "alias_damping", "rule_damping") if before_raw.get(k) != after_raw.get(k)]
    out += [f"unexpected top-level key {k!r}" for k in after_raw if k not in before_raw]
    for w, v in before_raw["aliases"].items():
        if after_raw["aliases"].get(w) != v:
            out.append(f"alias {w!r} removed or changed")
    if after_raw["rules"][:len(before_raw["rules"])] != before_raw["rules"]:
        out.append("existing rules removed or reordered")
    for k, n in before_raw["notes"].items():
        if after_raw["notes"].get(k) != n:
            out.append(f"note {k!r} removed or changed")
    added = alias_patch(before_raw, after_raw)
    if added["rules"]:
        out.append("rules are not proposed in Round 3 (direct aliases only)")
    per_seed_counts, n_new = {}, len(added["aliases"]) + len(added["rules"])
    if n_new > budget:
        out.append(f"budget exceeded: {n_new} > {budget}")
    for key, note in added["notes"].items():
        cw, sid = note.get("candidate_word"), note.get("seed_query_id")
        if cw not in cands:
            out.append(f"{key}: candidate_word {cw!r} not in frozen candidates"); continue
        per_seed_counts[sid] = per_seed_counts.get(sid, 0) + 1
        if "R6" not in (note.get("failure_classes") or ()) or "R6" not in (classes.get(sid) or ()):
            out.append(f"{key}: seed {sid!r} is not R6 (note and bench failure_classes must contain R6)")
        if sid not in cands[cw]["seed_ids"]:
            out.append(f"{key}: seed {sid!r} is not a seed of candidate {cw!r}"); continue
        if key.startswith("rule:"):
            rule = after_raw["rules"][int(key[5:])]
            ctx = [t for t in rule["when_all"] if t != cw]
            if cw not in rule["when_all"] or len(rule["when_all"]) > 2:
                out.append(f"{key}: rule must be candidate_word plus at most one context token")
            elif ctx and ctx[0] not in _norm_tokens(queries.get(sid, "")):
                out.append(f"{key}: context token {ctx[0]!r} is not a unigram of seed {sid}")
            targets = rule["add"]
        else:
            if key != cw:
                out.append(f"{key}: alias word must equal candidate_word {cw!r}")
            targets = after_raw["aliases"].get(key, [])
        if len(targets) != 1:
            out.append(f"{key}: exactly 1 target required")
        elif targets[0] not in cands[cw]["targets_by_seed"].get(sid, []):
            out.append(f"{key}: target {targets[0]!r} is not a target of {cw!r} for seed {sid}")
    for w in added["aliases"]:
        if w not in added["notes"]:
            out.append(f"alias {w!r} added without a note")
    for i in range(len(before_raw["rules"]), len(after_raw["rules"])):
        if f"rule:{i}" not in added["notes"]:
            out.append(f"rule:{i} added without a note")
    out += [f"more than two atomic actions for seed {sid}: {n}" for sid, n in sorted(per_seed_counts.items()) if n > per_seed]
    return out


def baseline_mismatch(aliases_raw, ranking_raw, cands_doc) -> list:
    inputs = cands_doc["generated_from"]["inputs"]
    return [name for name, raw in (("aliases", aliases_raw), ("ranking", ranking_raw)) if policy.canonical_sha256(raw) != inputs[name]]


def baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench, root=ROOT) -> str:
    """spec §5.5 v1.22: the whole input of tune_round3 - B aliases/ranking, S, frozen candidates, seed/regression benches, the r0
    fixture bench, the evaluation code and the final grid."""
    fx = fixture_bench(bench)
    return policy.canonical_sha256({"b_aliases_sha256": policy.canonical_sha256(aliases_raw), "b_ranking_sha256": policy.canonical_sha256(ranking_raw),
                                    "snapshot_registry_fingerprint": fp, "alias_candidates_sha256": policy.canonical_sha256(cands_doc),
                                    "seed_benchmark_sha256": policy.canonical_sha256(bench["seed"]),
                                    "regression_benchmark_sha256": policy.canonical_sha256(bench["regression_negative"]),
                                    "fixture_benchmark_sha256": policy.canonical_sha256(fx),
                                    "evaluation_code_sha256": ev.evaluation_code_sha256(root), "tuning_grid_sha256": ev.tuning_grid_sha256(ranking_raw)})


def tuning_accept(seed_res, reg_res, fixture_final) -> bool:
    """spec §5.5 v1.22: seed 39/39 ∧ regression_effective 14/14 ∧ fixture positive 23/23 ∧ fixture negative raw 6/6."""
    return seed_res["passed"] == SEED_TOTAL and reg_res["effective_passed"] == REGRESSION_TOTAL and not fixture_final


LOG_MUTABLE_KEYS = ("run_log_sha256", "status", "adopted", "reject_reason", "reject_evidence")


def log_core(line: dict) -> dict:
    """The hashed projection of a tuning log line: everything except the fields that --adopt/--reject may set."""
    return {k: v for k, v in line.items() if k not in LOG_MUTABLE_KEYS}


def result_sha256(final_constants, patch) -> str:
    return policy.canonical_sha256({"final_constants": dict(final_constants),
                                    "alias_patch": {k: patch[k] for k in ("aliases", "rules", "notes")}})


def verify_replay(eval_fn, bench, base_raw, cands, constants, expected_result_sha256, fixture_fn=None) -> list:
    """AC-19: the committed alias additions must equal a fresh proposer run from the B state at the adopted constants
    (with the same fixture constraint as the pipeline)."""
    _, patch = propose_aliases(eval_fn, bench, base_raw, cands, fixture_fn=fixture_fn)
    got = result_sha256(constants, patch)
    return [] if got == expected_result_sha256 else [f"replay result_sha256 {got} != adopted {expected_result_sha256}"]


# ---- pipeline, adoption, verification CLI ----

def _alias_policy(raw):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "a.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        return policy.load_aliases(p)


def run_pipeline(evaluate_fn, bench, aliases_raw, cands_doc, grid, baseline, fixture_fn):
    """Pure orchestration (tested with a fake evaluate_fn(point, raw_aliases) -> (seed_res, reg_res) and a fake
    fixture_fn(point, raw_aliases) -> failing r0 fixture ids): constants exactly once with the B aliases over the
    fixture-admissible grid points, then the proposer exactly once at those constants under the same fixture constraint.
    Returns (results, selected, working, patch, seed_res, reg_res, fixture_fail) where fixture_fail =
    {"constants": [grid_points indices excluded], "final": [ids failing with the final config]}."""
    results, excluded = [], []
    for i, point in enumerate(grid_points(grid)):
        if fixture_fn(point, aliases_raw):
            excluded.append(i); continue
        s, r = evaluate_fn(point, aliases_raw)
        results.append((point, s["passed"], r["passed"]))
    if not results:
        raise SystemExit("error: every constants grid point fails the r0 fixture suite (fixture_fail)")
    selected = select_candidate(results, baseline, grid)

    def eval_fn(raw):
        s, r = evaluate_fn(selected, raw)
        return frozenset(f["id"] for f in s["failed"]), frozenset(f["id"] for f in r["failed"])
    working, patch = propose_aliases(eval_fn, bench, aliases_raw, cands_doc["candidates"],
                                     fixture_fn=lambda raw: fixture_fn(selected, raw))
    seed_res, reg_res = evaluate_fn(selected, working)
    return results, selected, working, patch, seed_res, reg_res, {"constants": excluded, "final": list(fixture_fn(selected, working))}


def _parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--note", default="")
    ap.add_argument("--adopt", default=None, metavar="RUN_ID")
    ap.add_argument("--reject", default=None, metavar="RUN_ID"); ap.add_argument("--reason", default="full-suite-failed")
    ap.add_argument("--evidence", default=None, metavar="PATH"); ap.add_argument("--materialize", default=None, metavar="RUN_ID"); ap.add_argument("--out", default=None)
    ap.add_argument("--verify", action="store_true")
    return ap.parse_args(argv)


def _read_log():
    return [json.loads(x) for x in LOG_PATH.read_text(encoding="utf-8").splitlines() if x.strip()] if LOG_PATH.exists() else []


def _write_log(lines):
    LOG_PATH.write_text("\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in lines) + "\n", encoding="utf-8")


def _with_state(cache, fn):
    """Build the registry from a temporary copy of the snapshot and call fn(state)."""
    with tempfile.TemporaryDirectory() as td:
        copy_dir = pathlib.Path(td) / "cache"
        shutil.copytree(cache, copy_dir)
        with mock.patch.object(storage, "CACHE_DIR", copy_dir):
            return fn(build_state(copy_dir))


def require_round(min_round=3) -> None:
    """Refuse to run before round_freeze.json has a round >= min_round entry (checked fresh, not from the
    module-level ROUND computed at import time): every subcommand does file/log I/O keyed by ROUND/LOG_PATH,
    and until the Round-N freeze entry exists those resolve to an earlier round's (frozen) paths."""
    current = ev.current_round()["round"]
    if current < min_round:
        raise SystemExit(f"error: tuning CLI requires round_freeze.json to have a round >= {min_round} entry "
                          f"(currently round {current}); freeze round {min_round} first")


def main(argv=None) -> int:
    args = _parse(argv)
    try:
        require_round()
    except SystemExit as e:
        print(e, file=sys.stderr); return 2
    if args.adopt:
        return _adopt(args.adopt)
    if args.reject:
        if not args.evidence:
            print("error: --reject needs --evidence PATH (the captured red-suite output)", file=sys.stderr); return 2
        return _reject(args.reject, args.reason, args.evidence)
    if args.materialize:
        return _materialize(args.materialize, args.out or "candidate-policy")
    cache = (args.cache_dir or pathlib.Path("")).expanduser()
    if not all((cache / f"{s}.json").is_file() for s in SOURCES):
        print(f"error: {cache} is not a cache snapshot (missing <source>.json)", file=sys.stderr); return 2
    problems = rs.verify_freeze(ROUND, cache)
    if problems:
        print("error: snapshot S differs from round_freeze: " + "; ".join(problems), file=sys.stderr); return 2
    os.environ.pop("ATLASSIAN_DOCS_SEARCH_LOG", None)
    bench, rp = _BENCH, policy.load_ranking(RANKING_PATH)
    aliases_raw, ranking_raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8")), json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    cands_doc = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    if args.verify:
        return _verify(cache, bench, rp, aliases_raw, ranking_raw, cands_doc)
    decided = [l["run_id"] for l in _read_log() if l.get("status") in ("pending", "rejected", "adopted")]
    if decided and not args.dry_run:
        print(f"error: {LOG_REL} already holds a pending/rejected/adopted run {decided}; the first AC-valid output is "
              f"final and a rejected run ends the round - no new pipeline run", file=sys.stderr); return 2
    bad = baseline_mismatch(aliases_raw, ranking_raw, cands_doc)
    if bad:
        print(f"error: dirty round state: {bad} differ from the B baseline recorded in alias_candidates.json; "
              f"restore the B commit's files first (git checkout <B> -- {ALIASES_PATH.name} {RANKING_PATH.name})", file=sys.stderr); return 2
    seal = bench.get(f"round{ROUND}_seal") or {}

    def body(state):
        fp = state.registry.fingerprint
        if fp != seal.get("registry_fingerprint") or fp != cands_doc["generated_from"]["registry_fingerprint"]:
            raise SystemExit(f"error: registry fingerprint {fp} != round{ROUND}_seal / alias_candidates provenance; wrong snapshot?")
        b_sha = policy.canonical_sha256(aliases_raw)
        queries = [r["query"] for r in bench["seed"] + bench["regression_negative"]]
        fx_state, fx_bench = fixture_state(), fixture_bench(bench)
        tf = rp.ordering_rules["terminal_alias_full_weight"]                                          # v1.24 spec §3.8 parity
        ge = GridEvaluator(state, queries, _alias_policy(aliases_raw), tf)
        ge_fx = GridEvaluator(fx_state, [r["query"] for r in fx_bench["seed"] + fx_bench["regression_negative"]], _alias_policy(aliases_raw), tf)

        _raw_sha_cache = {}

        def raw_sha(raw):                        # memoized per distinct alias-state object (grid stage reuses one object many times)
            key = id(raw)
            if key not in _raw_sha_cache:
                _raw_sha_cache[key] = policy.canonical_sha256(raw)
            return _raw_sha_cache[key]

        def evaluate_fn(point, raw):             # grid stage (B aliases): memoized; proposer trials / final: production path
            return evaluate_point_fast(ge, rp, point, bench) if raw_sha(raw) == b_sha else evaluate_point(state, rp, point, bench, _alias_policy(raw))

        def fixture_fn(point, raw):
            return fixture_failures_fast(ge_fx, rp, point, fx_bench) if raw_sha(raw) == b_sha else fixture_failures(fx_state, rp, point, fx_bench, _alias_policy(raw))
        t0 = time.perf_counter()
        results, selected, working, patch, seed_res, reg_res, fixture_fail = run_pipeline(
            evaluate_fn, bench, aliases_raw, cands_doc, rp.tuning_grid, dict(rp.baseline), fixture_fn)
        grid_runtime = time.perf_counter() - t0
        fixture_diag = fixture_negative_diagnostic(fx_state, rp, selected, fx_bench, _alias_policy(working))   # AC-R3-11a diagnostic, final config
        slow_s, slow_r = evaluate_point(state, rp, selected, bench, _alias_policy(aliases_raw))        # cross-check the memoized path once
        fast_s, fast_r = evaluate_point_fast(ge, rp, selected, bench)
        counts_differ = (slow_s["passed"], slow_r["passed"], slow_r["raw_passed"]) != (fast_s["passed"], fast_r["passed"], fast_r["raw_passed"])
        id_mismatch = cross_check_mismatch(slow_s, slow_r, fast_s, fast_r)
        if counts_differ or id_mismatch:
            raise SystemExit("error: memoized grid evaluator disagrees with search_operations at the selected point"
                              f" (differing ids: {id_mismatch})")
        violations = validate_alias_change(aliases_raw, working, cands_doc["candidates"], {r["id"]: r["query"] for r in bench["seed"]},
                                           {r["id"]: r["failure_classes"] for r in bench["seed"]})
        if violations:
            raise SystemExit("\n".join(f"VIOLATION {v}" for v in violations))
        for f in seed_res["failed"] + reg_res["failed"]:
            print(f"  FAIL {f['id']} {f['query']!r}")
            for key, score, sig in top5(state, rp, selected, f["query"], _alias_policy(working)):
                print(f"      {score:8.3f}  {key}  {json.dumps(sig, sort_keys=True)}")
        return fp, results, selected, working, patch, seed_res, reg_res, fixture_fail, grid_runtime, fixture_diag
    try:
        fp, results, selected, working, patch, seed_res, reg_res, fixture_fail, grid_runtime, fixture_diag = _with_state(cache, body)
    except SystemExit as e:
        print(e, file=sys.stderr); return 2
    return _finish(args, rp, fp, results, selected, patch, working, seed_res, reg_res,
                   baseline_sha256(aliases_raw, ranking_raw, fp, cands_doc, bench), fixture_fail, grid_runtime, fixture_diag)


def _finish(args, rp, fp, results, selected, patch, working, seed_res, reg_res, base_sha, fixture_fail, grid_runtime, fixture_diag) -> int:
    accept = tuning_accept(seed_res, reg_res, fixture_fail["final"])
    effects = plan_effects(args.dry_run, accept)
    pos_fail = [i for i in fixture_fail["final"] if i.startswith("s-")]
    neg_fail = [i for i in fixture_fail["final"] if i.startswith("rn-")]
    line = {"run_id": str(uuid.uuid4()), "run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": _git("rev-parse", "HEAD").strip(), "round": ROUND, "registry_fingerprint": fp,
            "baseline_sha256": base_sha, "events": list(EVENTS), "constants_selected": selected,
            "grid_size": len(results) + len(fixture_fail["constants"]), "grid_runtime_s": round(grid_runtime, 1),
            "fixture_fail": fixture_fail,
            "passing_combos": sum(1 for _, s, r in results if s == SEED_TOTAL and r == REGRESSION_TOTAL),
            "aliases_proposed": patch, "seed": f"{seed_res['passed']}/{SEED_TOTAL}",
            "regression_negative": f"{reg_res['effective_passed']}/{REGRESSION_TOTAL}",
            "regression_raw": f"{reg_res['raw_passed']}/{REGRESSION_TOTAL}",
            "fixture_positive": f"{FIXTURE_COUNTS[0] - len(pos_fail)}/{FIXTURE_COUNTS[0]}",
            "fixture_negative_raw": f"{FIXTURE_COUNTS[1] - len(neg_fail)}/{FIXTURE_COUNTS[1]}",
            "fixture_negative_effective_diagnostic": f"{fixture_diag['effective_passed']}/{FIXTURE_COUNTS[1]}",
            "tuning_accept": accept, "tuning_failed": not accept,
            "result_sha256": result_sha256(selected, patch),
            "dirty": dirty_paths(_git("status", "--porcelain", "--untracked-files=no")), "note": args.note,
            "ranking_structure_sha256": rp.structure_sha256, "baseline": dict(rp.baseline)}
    line["run_log_sha256"] = policy.canonical_sha256(log_core(line))   # status/adopted/reject_reason are outside the hash
    line["status"], line["adopted"] = ("pending" if accept else "failed"), False
    if effects["write_constants"]:                                   # candidate policy, adoption pending --adopt
        write_constants(selected)
        ALIASES_PATH.write_text(json.dumps(working, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        policy.load_aliases(ALIASES_PATH)
    if effects["append_log"]:
        _write_log(_read_log() + [line])
    else:
        print("dry run: nothing written; would-be log line:"); print(json.dumps(line, ensure_ascii=False, sort_keys=True))
    print(json.dumps({k: line[k] for k in ("run_id", "constants_selected", "seed", "regression_negative", "passing_combos",
                                           "tuning_failed", "status", "result_sha256")}, ensure_ascii=False))
    print(json.dumps({"aliases": patch["aliases"], "rules": patch["rules"], "unresolved": patch["unresolved"],
                      "resolved_by_prior_change": patch["resolved_by_prior_change"]}, ensure_ascii=False))
    return 0 if accept else 1


def _current_result_sha256() -> str:
    """result_sha256 recomputed from the policy files on disk (constants + round-N alias additions)."""
    raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    base = strip_round_entries(raw, ROUND)
    return result_sha256(policy.load_ranking(RANKING_PATH).constants, alias_patch(base, raw))


def _adopt(run_id) -> int:
    """Second stage (AC-19/20): called by the frozen worker brief only after the canonical full suite passed."""
    lines = _read_log()
    mine = [l for l in lines if l["run_id"] == run_id]
    if len(mine) != 1 or mine[0]["status"] != "pending":
        print(f"error: run {run_id} is not a pending run", file=sys.stderr); return 2
    if any(l["adopted"] for l in lines):
        print("error: a run is already adopted", file=sys.stderr); return 2
    first = next((l for l in lines if l["status"] != "failed"), None)
    if first is None or first["run_id"] != run_id:
        print(f"error: run {run_id} is not the first non-failed run of the log (AC-20b)", file=sys.stderr); return 2
    if _current_result_sha256() != mine[0]["result_sha256"]:
        print("error: policy files no longer reproduce this run's result_sha256", file=sys.stderr); return 2
    mine[0]["status"], mine[0]["adopted"] = "adopted", True
    _write_log(lines)
    print(json.dumps({"run_id": run_id, "adopted": True}))
    return 0


FAILING_TEST = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)
EXIT_CODE_LINE = re.compile(r"^(?:exit[_ ]code|EXIT_CODE)\s*[:=]\s*(\d+)\s*$", re.M | re.I)
UNITTEST_FAILED = re.compile(r"^FAILED \(", re.M)


def _test_id(name: str, qual: str) -> str:
    """Python prints `FAIL: test_x (pkg.mod.Class)` (3.11-) or `FAIL: test_x (pkg.mod.Class.test_x)` (3.12+)."""
    return qual if qual.endswith("." + name) else f"{qual}.{name}"


def suite_evidence(text: str) -> dict:
    """Failure signature of a captured unittest run: exit code, canonical failing test ids (sorted, deduped) and the
    sha of the output. exit_code comes from the evidence: an explicit `exit_code: N` / `EXIT_CODE=N` line (the last
    one) when the capture recorded it, else unittest's own summary (`FAILED (` -> 1, otherwise 0)."""
    ids = sorted({_test_id(name, qual) for name, qual in FAILING_TEST.findall(text)})
    explicit = EXIT_CODE_LINE.findall(text)
    code = int(explicit[-1]) if explicit else (1 if UNITTEST_FAILED.search(text) else 0)
    return {"exit_code": code, "failing_tests": ids, "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def materialize_candidate(line: dict, b_aliases_raw: dict, b_ranking_raw: dict) -> tuple:
    """The policy files a run produced: B ranking with constants_selected, B aliases + aliases_proposed."""
    ranking = json.loads(json.dumps(b_ranking_raw)); ranking["constants"] = dict(line["constants_selected"])
    aliases, patch = json.loads(json.dumps(b_aliases_raw)), line["aliases_proposed"]
    aliases["aliases"].update(patch["aliases"]); aliases["rules"] += patch["rules"]; aliases["notes"].update(patch["notes"])
    return ranking, aliases


def _materialize(run_id, out_dir) -> int:
    lines = [l for l in _read_log() if l["run_id"] == run_id]
    if len(lines) != 1:
        print(f"error: unknown run {run_id}", file=sys.stderr); return 2
    raw_a, raw_r = json.loads(ALIASES_PATH.read_text(encoding="utf-8")), json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    ranking, aliases = materialize_candidate(lines[0], strip_round_entries(raw_a, ROUND), raw_r)
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "search_ranking.json").write_text(json.dumps(ranking, indent=2) + "\n", encoding="utf-8")
    (out / "search_aliases.json").write_text(json.dumps(aliases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written_r, written_a = json.loads((out / "search_ranking.json").read_text(encoding="utf-8")), json.loads((out / "search_aliases.json").read_text(encoding="utf-8"))
    actual = result_sha256(written_r["constants"], alias_patch(strip_round_entries(raw_a, ROUND), written_a))   # recomputed from the files
    if actual != lines[0]["result_sha256"]:
        print(f"error: materialized files give {actual}, run recorded {lines[0]['result_sha256']}", file=sys.stderr); return 2
    print(json.dumps({"run_id": run_id, "result_sha256_from_files": actual}))
    return 0


def _reject(run_id, reason, evidence_path) -> int:
    """pending -> rejected (the canonical full suite failed on the candidate policy): the red-suite output captured BEFORE
    the rollback is summarized onto the log line, then the B policy files are restored. A rejected run is a round abort
    (spec v1.13 AC-22), distinct from tuning_failed."""
    lines = _read_log()
    mine = [l for l in lines if l["run_id"] == run_id]
    if len(mine) != 1 or mine[0]["status"] != "pending":
        print(f"error: run {run_id} is not a pending run", file=sys.stderr); return 2
    text = pathlib.Path(evidence_path).expanduser().read_text(encoding="utf-8", errors="replace")
    ev_sig = suite_evidence(text)
    if not ev_sig["failing_tests"] or ev_sig["exit_code"] == 0:
        print("error: evidence shows no FAIL/ERROR lines or a zero exit code; refusing to reject a green run", file=sys.stderr); return 2
    if _current_result_sha256() != mine[0]["result_sha256"]:
        print("error: policy files no longer reproduce this run's result_sha256; evidence would not belong to this candidate", file=sys.stderr); return 2
    subprocess.run(["git", "checkout", "--", str(ALIASES_PATH.relative_to(ROOT)), str(RANKING_PATH.relative_to(ROOT))], cwd=ROOT, check=True)
    cands_doc = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    bad = baseline_mismatch(json.loads(ALIASES_PATH.read_text(encoding="utf-8")), json.loads(RANKING_PATH.read_text(encoding="utf-8")), cands_doc)
    if bad:
        print(f"error: B baseline not restored: {bad}", file=sys.stderr); return 2
    mine[0]["status"], mine[0]["reject_reason"] = "rejected", reason
    mine[0]["reject_evidence"] = {**ev_sig, "evidence_path": str(evidence_path)}
    _write_log(lines)
    print(json.dumps({"run_id": run_id, "status": "rejected", "reason": reason, "failing_tests": ev_sig["failing_tests"], "output_sha256": ev_sig["output_sha256"]}))
    return 0


def _verify(cache, bench, rp, aliases_raw, ranking_raw, cands_doc) -> int:
    """AC-19 per branch (spec v1.13): success -> replay == adopted run and files carry its delta; abort -> replay == the
    rejected candidate while the applied delta is 0 (policy == B)."""
    log = _read_log()
    adopted, rejected = [l for l in log if l["adopted"]], [l for l in log if l["status"] == "rejected"]
    failed = [l for l in log if l["status"] == "failed"]
    base = strip_round_entries(aliases_raw, ROUND)
    if len(adopted) + len(rejected) == 1:
        target = (adopted or rejected)[0]
        consts = dict(rp.constants) if adopted else dict(target["constants_selected"])
        if rejected:                                                # AC-19d / AC-01d: BOTH policy files at B
            bad = baseline_mismatch(aliases_raw, ranking_raw, cands_doc)
            delta = alias_patch(base, aliases_raw)
            if bad or delta["aliases"] or delta["rules"] or delta["notes"]:
                print(f"MISMATCH abort branch: policy files are not at B: {bad or 'round2 alias delta present'}", file=sys.stderr); return 1
    elif not adopted and not rejected and failed:                   # no decided run yet: all candidates must agree (replayable failure)
        if len({l["result_sha256"] for l in failed}) != 1:
            print("error: failed runs in the log disagree on result_sha256", file=sys.stderr); return 2
        target = failed[0]
        consts = dict(target["constants_selected"])
        bad = baseline_mismatch(aliases_raw, ranking_raw, cands_doc)
        delta = alias_patch(base, aliases_raw)
        if bad or delta["aliases"] or delta["rules"] or delta["notes"]:
            print(f"MISMATCH failure branch: policy files are not at B: {bad or 'round delta present'}", file=sys.stderr); return 1
    else:
        print("error: exactly one adopted run (success), one rejected run (abort), or only failed runs required", file=sys.stderr); return 2

    def body(state):
        def eval_fn(raw):
            s, r = evaluate_point(state, rp, consts, bench, _alias_policy(raw))
            return frozenset(f["id"] for f in s["failed"]), frozenset(f["id"] for f in r["failed"])
        fx_state, fx_bench = fixture_state(), fixture_bench(bench)
        fixture_fn = lambda raw: fixture_failures(fx_state, rp, consts, fx_bench, _alias_policy(raw))
        return verify_replay(eval_fn, bench, base, cands_doc["candidates"], consts, target["result_sha256"], fixture_fn)
    problems = _with_state(cache, body)
    if policy.canonical_sha256(base) != cands_doc["generated_from"]["inputs"]["aliases"]:
        problems.append("stripped alias file differs from the B baseline recorded in alias_candidates.json")
    if adopted and consts != adopted[0]["constants_selected"]:
        problems.append("constants on disk differ from the adopted run")
    if adopted and _current_result_sha256() != target["result_sha256"]:     # AC-19b: the files carry exactly the adopted delta
        problems.append("policy files on disk do not reproduce the adopted run's result_sha256")
    print("replay ok" if not problems else "\n".join(f"MISMATCH {m}" for m in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
