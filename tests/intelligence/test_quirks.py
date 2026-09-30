import json
import pathlib
import unittest
from types import MappingProxyType, SimpleNamespace

from tests.intelligence.helpers import make_state
from tools.atlassian_docs.intelligence import policy, quirks

FIX = json.loads((pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "quirks" / "descriptions.json").read_text(encoding="utf-8"))


def _op(key, description=""):
    return SimpleNamespace(key=key, description=description, parameters=())


class TestMining(unittest.TestCase):
    def test_all_four_real_descriptions_mine_as_advisory(self):
        for key, entry in FIX["operations"].items():
            hq = quirks.mine(_op(key, entry["description"]))
            self.assertEqual(len(hq), 1, key)
            self.assertEqual((hq[0].name, hq[0].value, hq[0].enforcement, hq[0].value_policy, hq[0].origin),
                             ("X-Atlassian-Token", "no-check", "advisory", "observed", "quirk:description"))

    def test_value_less_mention_is_not_mined(self):
        self.assertEqual(quirks.mine(_op("x:GET:/a", "set X-Atlassian-Token when uploading")), ())

    def test_mining_is_case_insensitive_with_canonical_name(self):
        hq = quirks.mine(_op("x:POST:/a", "send `x-atlassian-token: no-check` and X-ATLASSIAN-TOKEN: nocheck"))
        self.assertEqual([(h.name, h.value) for h in hq], [("X-Atlassian-Token", "no-check")])

    def test_candidates_exclude_mined_header_case_insensitively(self):
        op = _op("x:POST:/a", "uses x-atlassian-token and X-Other-Thing")
        reg = SimpleNamespace(list_sources=lambda: ["s"], sources={"s": SimpleNamespace(operations=[op])})
        self.assertEqual([c["header"] for c in quirks.header_candidates(reg)], ["X-Other-Thing"])

    def test_candidates_scan(self):
        state = make_state("jira-platform")
        cands = quirks.header_candidates(state.registry)
        self.assertTrue(all(c["header"] != "X-Atlassian-Token" for c in cands))


class TestOverrides(unittest.TestCase):
    def _ov(self, headers, hints=None):
        entry = policy.OverrideEntry(tuple(policy.HeaderOverride(**h) for h in headers), hints or {}, ())
        return policy.QuirkOverrides(MappingProxyType({"x:POST:/a": entry}), "sha")

    def test_set_replaces_mined_and_becomes_required_literal(self):
        ov = self._ov([{"name": "x-atlassian-token", "action": "set", "value": "no-check", "enforcement": "required", "value_policy": "literal", "note": None}])
        q = quirks.for_operation(_op("x:POST:/a", "use `X-Atlassian-Token: no-check`"), ov)
        self.assertEqual(len(q.headers), 1)
        self.assertEqual((q.headers[0].enforcement, q.headers[0].value_policy, q.headers[0].origin), ("required", "literal", "quirk:override"))

    def test_suppress_removes_mined(self):
        ov = self._ov([{"name": "X-ATLASSIAN-TOKEN", "action": "suppress", "value": None, "enforcement": "advisory", "value_policy": "observed", "note": None}])
        q = quirks.for_operation(_op("x:POST:/a", "use `X-Atlassian-Token: no-check`"), ov)
        self.assertEqual(q.headers, ()); self.assertEqual(q.suppressed, ("X-Atlassian-Token",))

    def test_real_overrides_apply_to_attachments(self):
        state = make_state("jira-platform")
        op = state.registry.get_operation("jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")
        q = quirks.for_operation(op)
        self.assertEqual(q.headers[0].origin, "quirk:override"); self.assertEqual(q.request_hints["multipart_fields"][0]["name"], "file")

    def test_orphaned_keys(self):
        state = make_state("confluence")   # none of the 4 override keys exist here
        self.assertEqual(len(quirks.orphaned_override_keys(state.registry)), 4)
        self.assertEqual(quirks.orphaned_override_keys(make_state("jira-platform").registry), ("jira-platform:POST:/rest/api/3/issuetype/{id}/avatar2", "jira-platform:POST:/rest/api/3/project/{projectIdOrKey}/avatar2", "jira-platform:POST:/rest/api/3/universal_avatar/type/{type}/owner/{entityId}"))


class TestOutcomeTable(unittest.TestCase):
    def _q(self, enf, vp):
        return quirks.HeaderQuirk("X", "v", enf, vp, "quirk:override", None)

    def test_table(self):
        self.assertEqual(quirks.outcome(self._q("advisory", "observed"), False, None), (None, "advisory_header_missing"))
        self.assertEqual(quirks.outcome(self._q("advisory", "observed"), True, False), (None, "quirk_value_mismatch"))
        self.assertEqual(quirks.outcome(self._q("required", "observed"), False, None), ("required", None))
        self.assertEqual(quirks.outcome(self._q("required", "observed"), True, False), (None, "quirk_value_mismatch"))
        self.assertEqual(quirks.outcome(self._q("advisory", "literal"), True, False), ("quirk_value_mismatch", None))
        self.assertEqual(quirks.outcome(self._q("required", "literal"), False, None), ("required", None))
        self.assertEqual(quirks.outcome(self._q("required", "literal"), True, False), ("quirk_value_mismatch", None))
        self.assertEqual(quirks.outcome(self._q("required", "literal"), True, True), (None, None))
