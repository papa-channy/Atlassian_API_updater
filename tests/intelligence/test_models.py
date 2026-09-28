import copy
import json
import unittest

from tools.atlassian_docs.intelligence import models


def _op(**overrides):
    base = dict(
        source="jira-platform",
        key="jira-platform:POST:/rest/api/3/issue",
        operation_id="createIssue",
        method="POST",
        path="/rest/api/3/issue",
        summary="Create issue",
        description="desc",
        tags=("Issues",),
        parameters=(models.Parameter("x", "query", False, None, {"type": "string"}, False),),
        request_body=models.RequestBody(True, None, (models.MediaType("application/json", {"$ref": "#/components/schemas/A"}),)),
        responses=(models.Response("201", "created", ()),),
        security=(models.SecurityAlternative((models.SecurityRequirement("OAuth2", ("write:jira-work",)),)),),
        deprecated=False,
        experimental=False,
        oauth2_scopes=("write:jira-work",),
    )
    base.update(overrides)
    return models.Operation(**base)


class TestOperation(unittest.TestCase):
    def test_is_frozen(self):
        op = _op()
        with self.assertRaises(Exception):
            op.summary = "changed"  # type: ignore[misc]

    def test_to_dict_is_json_serialisable_and_uses_lists(self):
        d = _op().to_dict()
        json.dumps(d)
        self.assertEqual(d["tags"], ["Issues"])
        self.assertEqual(d["security"], [[{"scheme": "OAuth2", "scopes": ["write:jira-work"]}]])
        self.assertEqual(d["parameters"][0]["in"], "query")
        self.assertEqual(d["request_body"]["content"][0]["content_type"], "application/json")

    def test_to_dict_returns_copies_of_raw_schema(self):
        op = _op()
        d = op.to_dict()
        d["request_body"]["content"][0]["schema"]["$ref"] = "mutated"
        self.assertEqual(op.request_body.content[0].schema["$ref"], "#/components/schemas/A")

    def test_empty_security_alternative_serialises_to_empty_list(self):
        d = _op(security=(models.SecurityAlternative(()),)).to_dict()
        self.assertEqual(d["security"], [[]])


class TestProvenanceAndRefresh(unittest.TestCase):
    def test_provenance_to_dict_round_trip(self):
        p = models.SourceProvenance(
            source="confluence", status="fresh", reason=None,
            active_spec_sha256="abc", active_openapi_version="3.0.3", active_api_version="v2",
            operation_count=3, schema_count=2,
            observed_cache_sha256="abc", metadata_sha256="abc",
            resolved_documentation_url="https://developer.atlassian.com/cloud/confluence/rest/v2/",
            last_checked="2026-09-28T00:00:00Z", last_updated="2026-09-28T00:00:00Z",
            candidate=None, warnings=({"kind": "x"},),
        )
        d = p.to_dict()
        self.assertEqual(d["status"], "fresh")
        self.assertEqual(d["warnings"], [{"kind": "x"}])
        d["warnings"][0]["kind"] = "mutated"
        self.assertEqual(p.warnings[0]["kind"], "x")

    def test_refresh_status_to_dict(self):
        r = models.RefreshStatus(86400, 900, False, None, None, False)
        self.assertEqual(r.to_dict()["ttl_seconds"], 86400)
