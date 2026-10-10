"""Round 6 spec §4.3: promotion of the Round 5 hidden set and relabel of the regression records (plan Task 6)."""


def fixture_label_conflicts(bench) -> list:
    """plan review 1 P0-4 (PR-8): r0 records relabeled answerable whose acceptable keys include a historical fixture forbidden key."""
    return sorted(r["id"] for r in bench.get("regression_positive") or [] if r["origin"].endswith("-r0")
                  and set(r["expected_top1_any"]) & (set(r.get("forbidden_top1") or []) | set(r.get("legacy_forbidden_top1") or [])))
