import unittest
from types import MappingProxyType, SimpleNamespace

from tests.intelligence.helpers import build_source_registry_from_fixture, make_state
from tools.atlassian_docs.intelligence import headers, request_check, request_template


class TestConstants(unittest.TestCase):
    def test_lists(self):
        self.assertIn("proxy-authorization", headers.CREDENTIAL_HEADERS)
        self.assertIn("x-api-key", headers.CREDENTIAL_HEADERS)
        self.assertNotIn("x-atlassian-token", headers.CREDENTIAL_HEADERS)
        self.assertIn("accept-encoding", headers.TRANSPORT_HEADERS)
        self.assertEqual(headers.REDACTED, "[REDACTED]")

    def test_dynamic_api_key_scheme(self):
        sr = SimpleNamespace(security_schemes=MappingProxyType({
            "k": {"type": "apiKey", "in": "header", "name": "X-Custom-Key"},
            "q": {"type": "apiKey", "in": "query", "name": "token"},
            "b": {"type": "http", "scheme": "basic"}}))
        names = headers.credential_header_names(sr)
        self.assertIn("x-custom-key", names); self.assertNotIn("token", names); self.assertIn("authorization", names)

    def test_real_fixture_has_no_api_key_header_scheme(self):
        sr = build_source_registry_from_fixture("jira-platform")
        self.assertEqual(headers.credential_header_names(sr), headers.CREDENTIAL_HEADERS)


class TestRedaction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform")
        cls.key = "jira-platform:POST:/rest/api/3/issue"

    def test_values_never_echoed(self):
        secret = "SECRET-VALUE-9f2a"
        hdrs = {"Proxy-Authorization": secret, "X-Api-Key": secret, "Cookie": secret}
        t = request_template.build_request_template(self.state, self.key, {"headers": hdrs, "body": {}})
        c = request_check.check_request(self.state, self.key, headers=hdrs, body={"fields": {}}, content_type="application/json")
        for out in (t, c):
            self.assertNotIn(secret, repr(out))
        self.assertEqual(sum(1 for w in c["warnings"] if w["rule"] == "credential_header_ignored"), 3)
        self.assertIn("credential_header_dropped", t["notes"])
