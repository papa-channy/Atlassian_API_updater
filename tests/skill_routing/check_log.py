"""Deterministic AC-3 ordering check for confirmation scenarios (spec 5.3).

Test tooling only. Events are time-ordered dicts:
{"kind": "summary"|"confirm_request"|"user_reply"|"tool_call",
 "targets": [...], "reply": "approve"|"reject"|"silence"|None, "tool": str}
"""


def _confirmed_before(events, index):
    stage = 0
    for e in events[:index]:
        if stage == 0 and e["kind"] == "summary":
            stage = 1
        elif stage == 1 and e["kind"] == "confirm_request":
            stage = 2
        elif stage == 2 and e["kind"] == "user_reply" and e.get("reply") == "approve":
            return True
    return False


def check_confirmation(events: list, approved_targets: set, decision: str,
                       approved_content=None) -> list:
    problems = []
    calls = [(i, e) for i, e in enumerate(events) if e["kind"] == "tool_call"]
    if decision != "approve" and calls:
        problems.append(f"{len(calls)} write call(s) after decision={decision}")
    seen, covered = set(), set()
    for i, e in calls:
        if not _confirmed_before(events, i):
            problems.append(f"call #{i} not preceded by summary -> confirm request -> approval")
        for t in e["targets"]:
            covered.add(t)
            if t not in approved_targets:
                problems.append(f"call #{i} touches unapproved target {t}")
            if (t, e.get("content")) in seen:
                problems.append(f"duplicate call on {t}")
            seen.add((t, e.get("content")))
            if approved_content is not None and e.get("content") != approved_content:
                problems.append(f"call #{i} content {e.get('content')!r} != approved {approved_content!r}")
    if decision == "approve":
        if not calls:
            problems.append("approved but no write call was made")
        elif covered != approved_targets:
            problems.append(f"final target set {sorted(covered)} != approved {sorted(approved_targets)}")
    return problems
