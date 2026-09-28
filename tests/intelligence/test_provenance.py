import datetime
import unittest

from tests.intelligence.helpers import build_source_registry_from_fixture, make_state
from tools.atlassian_docs import sync
from tools.atlassian_docs.intelligence import provenance, registry

NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=datetime.timezone.utc)


def _obs(sr, **over):
    base = dict(source=sr.source, observed_cache_sha256=sr.spec_sha256, served_from_last_good=False,
                rejected=None, refresh_failed=False, extra_warnings=(),
                metadata={"sha256": sr.spec_sha256, "api_version": "v3",
                          "last_checked": (NOW - datetime.timedelta(hours=1)).strftime(sync.TIMESTAMP_FORMAT),
                          "last_updated": "2026-09-27T00:00:00Z", "resolved_documentation_url": "https://d/"})
    base.update(over)
    return provenance.SourceObservation(**base)


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.sr = build_source_registry_from_fixture("confluence")

    def test_fresh(self):
        p = provenance.build_source_provenance(self.sr, _obs(self.sr), now=NOW)
        self.assertEqual((p.status, p.reason), ("fresh", None))
        self.assertEqual(p.active_spec_sha256, self.sr.spec_sha256)
        self.assertEqual(p.active_api_version, "v3")
        self.assertEqual(p.operation_count, len(self.sr.operations))

    def test_ttl_expired(self):
        old = {"last_checked": (NOW - datetime.timedelta(hours=25)).strftime(sync.TIMESTAMP_FORMAT)}
        obs = _obs(self.sr); obs = provenance.SourceObservation(**{**obs.__dict__, "metadata": {**obs.metadata, **old}})
        p = provenance.build_source_provenance(self.sr, obs, now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "ttl_expired"))

    def test_refresh_failed(self):
        p = provenance.build_source_provenance(self.sr, _obs(self.sr, refresh_failed=True), now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "refresh_failed"))

    def test_metadata_mismatch_hides_api_version(self):
        obs = _obs(self.sr); obs = provenance.SourceObservation(**{**obs.__dict__, "metadata": {**obs.metadata, "sha256": "other"}})
        p = provenance.build_source_provenance(self.sr, obs, now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "metadata_mismatch"))
        self.assertIsNone(p.active_api_version)

    def test_rejected_candidate_is_diagnostic_only(self):
        obs = _obs(self.sr, observed_cache_sha256="newsha", rejected={"sha256": "newsha", "rejected_reason": "incompatible_dialect"})
        p = provenance.build_source_provenance(self.sr, obs, now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "incompatible_dialect"))
        self.assertEqual(p.active_spec_sha256, self.sr.spec_sha256)
        self.assertEqual(p.observed_cache_sha256, "newsha")
        self.assertEqual(p.candidate["rejected_reason"], "incompatible_dialect")

    def test_served_from_last_good(self):
        p = provenance.build_source_provenance(self.sr, _obs(self.sr, served_from_last_good=True), now=NOW)
        self.assertEqual((p.status, p.reason), ("stale", "served_from_last_good"))

    def test_unavailable(self):
        p = provenance.build_source_provenance(None, _obs(self.sr, observed_cache_sha256=None, metadata={}), now=NOW)
        self.assertEqual((p.status, p.reason), ("unavailable", "no_cache"))
        self.assertEqual(p.operation_count, 0)

    def test_partial_normalization_warning(self):
        sr = build_source_registry_from_fixture("edge-cases", source="edge")
        p = provenance.build_source_provenance(sr, _obs(sr), now=NOW)
        self.assertFalse(any(w["kind"] == "normalization_partial" for w in p.warnings))  # fixture is complete


class TestBuildProvenanceAndHelpers(unittest.TestCase):
    def test_all_configured_sources_present(self):
        state = make_state("confluence")
        self.assertEqual(set(state.provenance), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(state.provenance["jira-platform"].status, "unavailable")

    def test_with_provenance_and_error(self):
        state = make_state("confluence")
        out = provenance.with_provenance({"x": 1}, state, ["confluence", "jira-platform"])
        self.assertEqual(set(out["provenance"]), {"confluence", "jira-platform"})
        self.assertEqual(out["registry_fingerprint"], state.registry.fingerprint)
        err = provenance.error_response("operation_not_found", "nope", candidates=["a"])
        self.assertEqual(err["error"]["code"], "operation_not_found"); self.assertEqual(err["error"]["candidates"], ["a"])
