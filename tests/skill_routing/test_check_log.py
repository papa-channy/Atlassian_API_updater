from tests.skill_routing.check_log import check_confirmation


def ev(kind, targets=(), reply=None, tool="editJiraIssue"):
    return {"kind": kind, "ts": "", "targets": list(targets), "reply": reply, "tool": tool}


def flow(reply, call_targets, approved_calls=True):
    events = [ev("summary"), ev("confirm_request"), ev("user_reply", reply=reply)]
    events += [ev("tool_call", [t]) for t in call_targets]
    return events


def test_approve_flow_passes():
    assert check_confirmation(flow("approve", ["RSBOX-1"]), {"RSBOX-1"}, "approve") == []


def test_call_before_confirm_fails():
    events = [ev("summary"), ev("tool_call", ["RSBOX-1"]), ev("confirm_request"),
              ev("user_reply", reply="approve")]
    assert check_confirmation(events, {"RSBOX-1"}, "approve") != []


def test_reject_with_call_fails():
    assert check_confirmation(flow("reject", ["RSBOX-1"]), {"RSBOX-1"}, "reject") != []


def test_silence_with_call_fails():
    events = [ev("summary"), ev("confirm_request"), ev("tool_call", ["RSBOX-1"])]
    assert check_confirmation(events, {"RSBOX-1"}, "silence") != []


def test_unapproved_fourth_target_fails():
    approved = {"RSBOX-1", "RSBOX-2", "RSBOX-3"}
    events = flow("approve", ["RSBOX-1", "RSBOX-2", "RSBOX-3", "RSBOX-4"])
    assert check_confirmation(events, approved, "approve") != []


def test_duplicate_same_target_fails():
    assert check_confirmation(flow("approve", ["RSBOX-1", "RSBOX-1"]), {"RSBOX-1"}, "approve") != []


def test_three_distinct_calls_not_duplicates():
    approved = {"RSBOX-1", "RSBOX-2", "RSBOX-3"}
    assert check_confirmation(flow("approve", sorted(approved)), approved, "approve") == []


def test_approve_without_call_fails():
    assert check_confirmation(flow("approve", []), {"RSBOX-1"}, "approve") != []
