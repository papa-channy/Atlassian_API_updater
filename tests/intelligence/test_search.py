import unittest

from tests.intelligence.helpers import load_fixture, make_state
from tools.atlassian_docs.intelligence import normalizer, search


class TestTokenize(unittest.TestCase):
    def test_camel_case_and_path(self):
        self.assertEqual(search.tokenize("issueIdOrKey"), frozenset({"issue", "id", "key"}))  # "or" is a stopword
        self.assertTrue({"rest", "api", "issue", "id", "key", "attachments", "attachment"}
                        <= search.tokenize("/rest/api/3/issue/{issueIdOrKey}/attachments"))

    def test_acronyms_and_digits(self):
        self.assertEqual(search.tokenize("OAuth2"), frozenset({"oauth2"}))
        self.assertEqual(search.tokenize("JQLQuery"), frozenset({"jql", "query"}))
        self.assertEqual(search.tokenize("IssueCreateMetadata"), frozenset({"issue", "create", "metadata"}))

    def test_plural_variants(self):
        self.assertEqual(search.tokenize("statuses"), frozenset({"statuses", "status"}))
        self.assertEqual(search.tokenize("status"), frozenset({"status"}))
        self.assertEqual(search.tokenize("process"), frozenset({"process"}))
        self.assertEqual(search.tokenize("analysis"), frozenset({"analysis"}))
        self.assertEqual(search.tokenize("issues"), frozenset({"issues", "issue"}))

    def test_singular_contract(self):
        cases = {"properties": "property", "queries": "query", "statuses": "status", "status": "status", "access": "access",
                 "issues": "issue", "databases": "database", "schemes": "scheme", "boards": "board", "classes": "class",
                 "series": "series", "news": "news", "jsis": "jsis", "id": "id"}
        for word, want in cases.items():
            self.assertEqual(search.singular(word), want, word)

    def test_unigrams_forms_and_joined(self):
        self.assertEqual(search.tokenize_unigrams("Get the issueIdOrKey properties"), ("get", "issue", "id", "key", "properties"))
        self.assertEqual(search.token_forms("properties"), frozenset({"properties", "property"}))
        self.assertEqual(search.expand_token_forms(("issues", "get")), frozenset({"issues", "issue", "get"}))
        self.assertEqual(search.joined_query_forms("IssueCreateMetadata get"), frozenset({"issuecreatemetadata"}))
        self.assertEqual(search.joined_query_forms("issue attachment"), frozenset())
        self.assertEqual(search._query_tokens("IssueCreateMetadata"), search.tokenize("IssueCreateMetadata") | {"issuecreatemetadata"})

    def test_expansion_never_contains_joined_forms(self):
        exp = search.expand_query("IssueCreateMetadata getIssue", policy.aliases())
        self.assertNotIn("issuecreatemetadata", exp.all); self.assertNotIn("getissue", exp.all)
        self.assertEqual(exp.base, frozenset({"issue", "create", "metadata", "get"}))

    def test_stopwords_short_tokens_and_dedupe(self):
        self.assertEqual(search.tokenize("a to the x issue issue"), frozenset({"issue"}))
        self.assertEqual(search.tokenize(""), frozenset())
        self.assertEqual(search.tokenize(None), frozenset())

    def test_snake_and_kebab(self):
        self.assertEqual(search.tokenize("create_issue"), frozenset({"create", "issue"}))
        self.assertEqual(search.tokenize("jira-platform"), frozenset({"jira", "platform"}))


class TestBuildIndex(unittest.TestCase):
    def test_index_fields_for_attachment_operation(self):
        ns = normalizer.normalize_openapi("jira-platform", load_fixture("jira-platform"))
        index = search.build_index(ns.operations)
        entry = next(e for e in index.entries if e.key.endswith("/attachments"))
        self.assertIn("attachment", entry.fields["operation_id"])
        self.assertIn("multipartfile", entry.fields["schema_names"])
        self.assertEqual(entry.fields["method"], frozenset({"post"}))
        self.assertIn("issue", entry.fields["path"])

    def test_nested_schema_names_indexed(self):
        ns = normalizer.normalize_openapi("edge", load_fixture("edge-cases"))
        index = search.build_index(ns.operations)
        entry = next(e for e in index.entries if e.key == "edge:POST:/things/{thingId}")
        self.assertIn("strict", entry.fields["schema_names"])
        merge = next(e for e in index.entries if e.key == "edge:POST:/merge")
        self.assertIn("merged", merge.fields["schema_names"])  # body is a bare $ref; no resolution (spec §13.2)


class TestSearchOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "jira-software", "confluence")

    def _keys(self, **kw):
        return [r["key"] for r in search.search_operations(self.state, **kw)["results"]]

    def test_attachment_query_top1(self):
        self.assertEqual(self._keys(query="upload attachment to issue")[0],
                         "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")

    def test_plural_and_singular_agree(self):
        self.assertEqual(self._keys(query="issue attachments")[0], self._keys(query="issue attachment")[0])

    def test_sprint_query_prefers_jira_software(self):
        top3 = self._keys(query="sprint board backlog")[:3]
        self.assertEqual(len(top3), 3)
        self.assertTrue(all(k.startswith("jira-software:") for k in top3), top3)

    def test_create_confluence_page(self):
        self.assertEqual(self._keys(query="create confluence page")[0], "confluence:POST:/pages")

    def test_exact_schema_name(self):
        self.assertEqual(self._keys(query="MultipartFile")[0], "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments")
        # getCreateIssueMeta is deprecated in the real spec (x0.7); since v1.4 §6.5b the three /issue ops whose terminal
        # segment "issue" is in the query gain resource_match_bonus and outrank it (25.9 vs 43/27/26), so top-4 is pinned.
        # Fixed constants (2/2/1/3/3/10) so this assertion does not depend on the adopted tuning result (spec v1.4 §6.5b).
        import dataclasses
        from types import MappingProxyType
        from unittest import mock
        fixed = dataclasses.replace(policy.load_ranking(), constants=MappingProxyType(
            {"method_match_bonus": 2.0, "method_mismatch_penalty": 2.0, "path_unmatched_penalty": 1.0,
             "path_unmatched_cap": 3, "product_hint_bonus": 3.0, "resource_match_bonus": 10.0}), sha256="fixed-for-test")
        with mock.patch.object(policy, "ranking", return_value=fixed):
            self.assertIn("jira-platform:GET:/rest/api/3/issue/createmeta", self._keys(query="IssueCreateMetadata")[:4])

    def test_query_tokens_includes_joined_word_and_empty_for_stopwords(self):
        self.assertIn("issuecreatemetadata", search._query_tokens("IssueCreateMetadata"))
        self.assertEqual(search._query_tokens("a to"), frozenset())

    def test_joined_token_only_for_multi_token_words(self):
        self.assertEqual(search._query_tokens("with"), frozenset())
        self.assertEqual(search._query_tokens("attachment"), frozenset({"attachment"}))
        self.assertNotIn("issueattachment", search._query_tokens("issue attachment"))

    def test_all_match_bonus_ignores_joined_forms(self):
        import types
        fields = {f: frozenset() for f in search.FIELD_WEIGHTS}
        first = next(iter(search.FIELD_WEIGHTS))
        fields[first] = frozenset({"issue", "attachment"})
        entry = types.SimpleNamespace(fields=fields)
        q = "issue attachment"
        pol = policy.AliasPolicy(0.5, 1.0, {}, (), "x")
        score = lambda text: search._score(entry, search._query_tokens(text), frozenset(), frozenset(),
                                           search.tokenize_unigrams(text), pol)[0]
        with_bonus = score(q)
        self.assertEqual(with_bonus, 2 * search.FIELD_WEIGHTS[first] + search.ALL_MATCH_BONUS)
        q2 = "IssueAttachment"   # joined token absent from the entry must not cancel the bonus
        self.assertIn("issueattachment", search._query_tokens(q2))
        self.assertEqual(score(q2), with_bonus)

    def test_source_filter(self):
        self.assertTrue(all(k.startswith("confluence:") for k in self._keys(query="issue page", source="confluence")))

    def test_method_tag_and_deprecated_filters(self):
        self.assertTrue(all(":GET:" in k for k in self._keys(query="issue", method="get")))
        out = search.search_operations(self.state, "issue", include_deprecated=False)
        self.assertTrue(all(not r["deprecated"] for r in out["results"]))
        tag = self.state.registry.sources["jira-platform"].operations[0].tags[0]
        self.assertTrue(all(tag in r["tags"] for r in search.search_operations(self.state, "issue", tag=tag)["results"]))

    def test_deterministic_order(self):
        self.assertEqual(self._keys(query="issue"), self._keys(query="issue"))

    def test_limit_bounds_and_provenance_scope(self):
        out = search.search_operations(self.state, "issue", limit=2)
        self.assertEqual(len(out["results"]), 2)
        self.assertEqual(set(out["provenance"]), {"jira-platform", "jira-software", "confluence"})
        self.assertEqual(set(search.search_operations(self.state, "issue", source="confluence")["provenance"]), {"confluence"})
        self.assertEqual(search.search_operations(self.state, "issue", limit=51)["error"]["code"], "invalid_argument")
        self.assertEqual(search.search_operations(self.state, "issue", source="github")["error"]["code"], "invalid_argument")

    def test_stopword_only_query_is_empty_query_error(self):
        self.assertEqual(search.search_operations(self.state, "a to")["error"]["code"], "empty_query")
        self.assertEqual(search.search_operations(self.state, "")["error"]["code"], "empty_query")

    def test_unavailable_source_filter_returns_empty_not_error(self):
        state = make_state("confluence")
        out = search.search_operations(state, "issue", source="jira-platform")
        self.assertEqual(out["results"], [])
        self.assertEqual(out["provenance"]["jira-platform"]["status"], "unavailable")


import json, pathlib
from tests.benchmarks.evaluator import evaluate
from tools.atlassian_docs.intelligence import policy

BENCH = json.loads((pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "search_queries.json").read_text(encoding="utf-8"))


class TestExpansion(unittest.TestCase):
    def test_direction_and_order(self):
        e = search.expand_query("fetch page", policy.aliases())
        self.assertIn("fetch", e.base); self.assertIn("get", e.direct); self.assertEqual(e.cond, frozenset())

    def test_rule_sees_direct_but_no_cascade(self):
        p = policy.AliasPolicy(0.5, 1.0, {"edit": ("update",)}, (policy.AliasRule(frozenset({"update", "page"}), ("updatepage",)),
                               policy.AliasRule(frozenset({"updatepage"}), ("cascade",))), "x")
        e = search.expand_query("edit page", p)
        self.assertIn("updatepage", e.cond); self.assertNotIn("cascade", e.cond)

    def test_no_cascade_through_alias_values(self):
        p = policy.AliasPolicy(0.5, 1.0, {"read": ("get",), "get": ("obtain",)}, (), "x")
        e = search.expand_query("read", p)
        self.assertEqual(e.direct, frozenset({"get"}))          # "obtain" must not appear


class TestExactMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("jira-platform", "jira-software", "confluence")

    def test_identifier_pinned_case_sensitive_first(self):
        out = search.search_operations(self.state, "createIssue")
        self.assertTrue(out["exact_match"]); self.assertEqual(out["results"][0]["match"], "exact_operation_id")
        self.assertEqual(out["results"][0]["key"], "jira-platform:POST:/rest/api/3/issue")
        ci = search.search_operations(self.state, "createissue")
        self.assertEqual(ci["results"][0]["match"], "exact_operation_id_ci")

    def test_duplicate_operation_ids_pinned_in_key_order(self):
        keys = [r["key"] for r in search.search_operations(self.state, "getIssue")["results"][:2]]
        self.assertEqual(keys, sorted(keys)); self.assertTrue(all(k.split(":")[2].endswith("issue/{issueIdOrKey}") for k in keys))

    def test_whitespace_query_is_not_pinned(self):
        out = search.search_operations(self.state, "get issue")
        self.assertFalse(out["exact_match"]); self.assertNotIn("match", out["results"][0])

    def test_exact_score_is_lexical_max_plus_one(self):
        out = search.search_operations(self.state, "createIssue")
        rest = [r["score"] for r in out["results"] if "match" not in r]
        self.assertAlmostEqual(out["results"][0]["score"], (max(rest) if rest else 0) + 1.0, places=3)

    def test_exact_key_and_filters(self):
        out = search.search_operations(self.state, "jira-platform:POST:/rest/api/3/issue")
        self.assertEqual(out["results"][0]["match"], "exact_key")
        conf = search.search_operations(self.state, "createIssue", source="confluence")
        self.assertFalse(conf["exact_match"]); self.assertTrue(all("match" not in r for r in conf["results"]))


class TestSeedBenchmark(unittest.TestCase):
    def test_seed_passes_on_fixtures(self):
        state = make_state("jira-platform", "jira-software", "confluence")
        fn = lambda q: [r["key"] for r in search.search_operations(state, q, limit=5)["results"]]
        res = evaluate(BENCH["seed"], fn)
        self.assertEqual(res["failed"], [], res)
        res_neg = evaluate(BENCH["regression_negative"], fn)
        self.assertEqual(res_neg["failed"], [], res_neg)

    def test_fields_and_fingerprint(self):
        state = make_state("jira-platform")
        out = search.search_operations(state, "fetch issue")
        self.assertIn("get", out["alias_tokens"]); self.assertIn("fetch", out["query_tokens"])
        self.assertEqual(set(out["expanded_tokens"]), set(out["query_tokens"]) | set(out["alias_tokens"]))
        self.assertEqual(len(out["intelligence_fingerprint"]), 64); self.assertEqual(out["intelligence_policy"]["versions"]["search"], 3)

    def test_alias_damped_and_bonus_on_base_only(self):
        state = make_state("jira-platform")
        with_alias = search.search_operations(state, "fetch issue")["results"][0]["score"]
        plain = search.search_operations(state, "get issue")["results"][0]["score"]
        self.assertLess(with_alias, plain)   # damped alias contributes less than the real token


class TestStructuralSignals(unittest.TestCase):
    def setUp(self):
        self.rp = policy.ranking()

    def test_path_tokens_model(self):
        toks = search.path_tokens_for("/rest/api/3/issue/{issueIdOrKey}/properties", self.rp.path_noise)
        self.assertEqual([t.origin for t in toks], ["issue", "properties"])
        self.assertEqual(toks[1].forms, frozenset({"properties", "property"}))
        self.assertEqual(search.path_tokens_for("/rest/api/3", self.rp.path_noise), ())          # review focus 2
        dup = search.path_tokens_for("/issue/{id}/issue", self.rp.path_noise)
        self.assertEqual([t.origin for t in dup], ["issue"])                                       # duplicate segment once
        camel = search.path_tokens_for("/issueTypeScheme", self.rp.path_noise)
        self.assertEqual([t.origin for t in camel], ["issue", "type", "scheme"])                  # unigrams, no joined form

    def _entry(self, path, method="GET", source="jira-platform"):
        return search.IndexEntry(f"{source}:{method}:{path}", {f: frozenset() for f in search.FIELD_WEIGHTS},
                                 search.path_tokens_for(path, self.rp.path_noise), source, method, search.terminal_tokens_for(path))

    def test_terminal_tokens_for(self):
        self.assertEqual(search.terminal_tokens_for("/widget/{id}/history"), ("history",))
        self.assertEqual(search.terminal_tokens_for("/issue/{k}"), ("issue",))
        self.assertEqual(search.terminal_tokens_for("/rest/api/3"), ())                          # last literal segment "3" is all digits -> dropped
        self.assertEqual(search.terminal_tokens_for("/issueTypeScheme/{id}"), ("issue", "type", "scheme"))

    def test_resource_match(self):
        bonus = self.rp.constants["resource_match_bonus"]
        q = ("get", "issue", "key"); ex = frozenset(q)
        rm = lambda path, uq, e: search._structural_signals(self._entry(path), uq, e, self.rp)[1]["resource_match"]
        self.assertEqual(rm("/rest/api/3/issue/{k}", q, ex), {"value": bonus, "tokens": ["issue"]})
        self.assertEqual(rm("/rest/api/3/issue/{k}/properties", q, ex), {"value": 0.0, "tokens": ["properties"]})
        pq = ("get", "project", "key")
        self.assertEqual(rm("/rest/api/3/projectvalidate/validProjectKey", pq, frozenset(pq)), {"value": 0.0, "tokens": ["valid", "project", "key"]})
        uq = ("update", "page", "content")
        self.assertEqual(rm("/pages/{id}", uq, frozenset(uq)), {"value": bonus, "tokens": ["pages"]})   # plural via forms
        self.assertEqual(rm("/rest/api/3", q, ex), {"value": 0.0, "tokens": []})

    def test_path_penalty_origin_once_and_cap(self):
        c = self.rp.constants
        e = self._entry("/rest/api/3/issue/{k}/properties")
        val, sig = search._structural_signals(e, ("get", "issue"), frozenset({"get", "issue"}), self.rp)
        self.assertEqual(sig["path_unmatched"], {"value": -c["path_unmatched_penalty"], "tokens": ["properties"]})
        # brief had ("get", "property"): origin "issue" is then unmatched (-1.0); "issue" added so only the plural case is tested
        val2, sig2 = search._structural_signals(e, ("get", "issue", "property"), frozenset({"get", "issue", "property"}), self.rp)
        self.assertEqual(sig2["path_unmatched"], {"value": 0.0, "tokens": []})                  # plural matched via forms
        deep = self._entry("/alpha/beta/gamma/delta/epsilon")                                     # 5 real origins (>= 2 chars)
        self.assertEqual(len(deep.path_tokens), 5)
        _, sig3 = search._structural_signals(deep, ("zzz",), frozenset({"zzz"}), self.rp)
        self.assertEqual(sig3["path_unmatched"]["value"], -c["path_unmatched_cap"] * c["path_unmatched_penalty"])
        self.assertEqual(len(sig3["path_unmatched"]["tokens"]), 5)                                # tokens list is not capped, only the value

    def test_method_intent(self):
        c = self.rp.constants
        e = self._entry("/x", method="POST")
        self.assertEqual(search._structural_signals(e, ("add", "x"), frozenset({"add", "x"}), self.rp)[1]["method_intent"], {"value": c["method_match_bonus"], "allowed": ["POST"]})
        self.assertEqual(search._structural_signals(e, ("get", "x"), frozenset({"get", "x"}), self.rp)[1]["method_intent"], {"value": -c["method_mismatch_penalty"], "allowed": ["GET"]})
        self.assertEqual(search._structural_signals(e, ("x",), frozenset({"x"}), self.rp)[1]["method_intent"], {"value": 0.0, "allowed": []})
        self.assertEqual(search._structural_signals(e, ("get", "delete", "x"), frozenset(), self.rp)[1]["method_intent"]["value"], 0.0)   # conflict
        self.assertEqual(search._structural_signals(e, ("move", "x"), frozenset(), self.rp)[1]["method_intent"]["allowed"], ["POST", "PUT"])
        patch = self._entry("/x", method="PATCH")
        self.assertEqual(search._structural_signals(patch, ("update", "x"), frozenset(), self.rp)[1]["method_intent"]["value"], -c["method_mismatch_penalty"])  # review focus 1

    def test_product_hint(self):
        j = self._entry("/x", source="jira-software"); c = self._entry("/x", source="confluence")
        self.assertEqual(search._structural_signals(j, ("jira", "x"), frozenset(), self.rp)[1]["product_hint"], {"value": self.rp.constants["product_hint_bonus"], "sources": ["jira-platform", "jira-software"]})
        self.assertEqual(search._structural_signals(c, ("jira", "x"), frozenset(), self.rp)[1]["product_hint"]["value"], 0.0)
        self.assertEqual(search._structural_signals(c, ("x",), frozenset(), self.rp)[1]["product_hint"], {"value": 0.0, "sources": []})


class TestScoringAlgorithm(unittest.TestCase):
    """End-to-end numbers on a synthetic state (spec §6.6, AC-07)."""
    @classmethod
    def setUpClass(cls):
        cls.state = make_state("edge-cases", source_map={"edge-cases": "edge"})   # small, deterministic

    def test_hint_only_query_has_no_candidates(self):                                            # review focus 3
        out = search.search_operations(self.state, "jira")
        self.assertTrue(out.get("error") == "empty_query" or out["results"] == [])

    def test_limit_truncates_pinned_and_keeps_exact_flag(self):                                    # review focus 4
        state = make_state("jira-platform", "jira-software")
        full = search.search_operations(state, "getIssue", limit=10)
        self.assertEqual(sum(1 for r in full["results"] if "match" in r), 2)                       # two pinned ops really exist
        out = search.search_operations(state, "getIssue", limit=1)
        self.assertEqual(len(out["results"]), 1); self.assertTrue(out["exact_match"]); self.assertIn("match", out["results"][0])
        self.assertEqual(out["results"][0]["key"], full["results"][0]["key"])                      # key order: jira-platform first

    def test_signals_shape_and_exact_zero(self):
        state = make_state("jira-platform")
        out = search.search_operations(state, "createIssue")
        pinned = out["results"][0]
        self.assertEqual(pinned["signals"], {"method_intent": {"value": 0.0, "allowed": []}, "path_unmatched": {"value": 0.0, "tokens": []}, "product_hint": {"value": 0.0, "sources": []}, "resource_match": {"value": 0.0, "tokens": []}})
        other = out["results"][1]
        self.assertEqual(set(other["signals"]), {"method_intent", "path_unmatched", "product_hint", "resource_match"})
        self.assertLessEqual({"ranking_sha256", "ranking_structure_sha256"}, set(out["intelligence_policy"]))


class TestScoringNumbers(unittest.TestCase):
    """spec §6.6 end to end with hand-computed numbers. FIELD_WEIGHTS: operation_id 5, summary 4, tags 3, path 3,
    schema_names 2, method 1, description 1; ALL_MATCH_BONUS 2; DEPRECATED_FACTOR 0.7. Fixed policy 2/2/1/3/3/10, no aliases."""
    SPEC = {"openapi": "3.0.1", "info": {"title": "num", "version": "1"}, "paths": {
        "/widget": {"get": {"operationId": "listWidget", "summary": "List widget", "tags": ["Widget"], "responses": {"200": {"description": "ok"}}}},
        "/widget/{id}/history": {"get": {"operationId": "getWidgetHistory", "summary": "Widget history", "tags": ["Widget"],
                                         "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                                         "responses": {"200": {"description": "ok"}}}},
        "/widget/legacy": {"get": {"operationId": "listWidgetLegacy", "summary": "List widget", "tags": ["Widget"], "deprecated": True,
                                   "responses": {"200": {"description": "ok"}}}},
        "/alpha/beta/gamma/delta/epsilon": {"get": {"operationId": "nothingHere", "summary": "Nothing here", "description": "zzz",
                                                    "responses": {"200": {"description": "ok"}}}}}}

    @classmethod
    def setUpClass(cls):
        import os, pathlib, tempfile
        from unittest import mock
        from tests.intelligence.helpers import state_from_source_registries
        from tools.atlassian_docs.intelligence import normalizer, registry
        raw = json.loads((policy.DATA_DIR / "search_ranking.json").read_text(encoding="utf-8"))
        raw["constants"] = {"method_match_bonus": 2.0, "method_mismatch_penalty": 2.0, "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0, "resource_match_bonus": 10.0}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(raw, fh)
        try:
            fixed = policy.load_ranking(pathlib.Path(fh.name))
        finally:
            os.unlink(fh.name)
        cls._p1 = mock.patch.object(policy, "ranking", return_value=fixed); cls._p1.start(); cls.addClassCleanup(cls._p1.stop)
        cls._p2 = mock.patch.object(policy, "aliases", return_value=policy.AliasPolicy(0.5, 1.0, {}, (), "x")); cls._p2.start()
        cls.addClassCleanup(cls._p2.stop)
        ns = normalizer.normalize_openapi("jira-platform", cls.SPEC)
        cls.state = state_from_source_registries({"jira-platform": registry.build_source_registry(ns, "0" * 64)})

    def test_list_widget_numbers(self):
        out = search.search_operations(self.state, "list widget")
        scores = {r["operation_id"]: r["score"] for r in out["results"]}
        # A listWidget:       opid 5*2 + summary 4*2 + tags 3*1 + path 3*1 = 24, all-match +2 = 26; +2 GET, path unmatched 0 -> 28.0; terminal "widget" matched +10 -> 38.0
        # C listWidgetLegacy: opid 5*2 + summary 8 + tags 3 + path 3 ({widget, legacy}) = 24, +2 = 26; +2 GET, -1 (legacy) = 27 * 0.7 = 18.9 (terminal "legacy" unmatched)
        # B getWidgetHistory: opid 5*1 + summary 4*1 + tags 3 + path 3 = 15, no all-match ("list" unmatched); +2 GET, -1 (history) = 16.0 (terminal "history" unmatched)
        self.assertEqual(scores, {"listWidget": 38.0, "listWidgetLegacy": 18.9, "getWidgetHistory": 16.0})
        self.assertEqual([r["operation_id"] for r in out["results"]], ["listWidget", "listWidgetLegacy", "getWidgetHistory"])
        self.assertEqual(out["total_matches"], 3)
        b = out["results"][2]["signals"]
        self.assertEqual(b, {"method_intent": {"value": 2.0, "allowed": ["GET"]}, "path_unmatched": {"value": -1.0, "tokens": ["history"]}, "product_hint": {"value": 0.0, "sources": []},
                             "resource_match": {"value": 0.0, "tokens": ["history"]}})

    def test_negative_subtotal_is_clamped_and_excluded(self):
        out = search.search_operations(self.state, "zzz")
        # nothingHere: description 1*1 = 1, all-match +2 = 3; no verb -> 0; 5 unmatched origins capped 3 * 1.0 = -3 -> clamp 0 -> excluded (terminal "epsilon" unmatched)
        self.assertEqual(out["results"], []); self.assertEqual(out["total_matches"], 0); self.assertNotIn("error", out)
