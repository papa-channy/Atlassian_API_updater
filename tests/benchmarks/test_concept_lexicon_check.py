import json, unittest
from unittest import mock
from tests.benchmarks import concept_lexicon_check as clc

CONCEPTS = {"issue", "comment", "page", "sprint", "attachment", "version", "space"}
CATALOG = CONCEPTS | {"file", "get", "workspace", "linked"}
VERBS, HINTS, ALIAS_KEYS = {"get", "create"}, {"jira", "confluence"}, {"ticket"}
ARGS = (CONCEPTS, CATALOG, VERBS, HINTS, ALIAS_KEYS)


class TestChecks(unittest.TestCase):
    def test_normalize_lowercases_singularizes_and_merges(self):
        raw = {"Tickets": ["issue"], "ticket": ["issues"], "notes": ["comment"]}
        self.assertEqual(clc.normalize_raw(raw), {"note": ["comment"], "ticket": ["issue"]})

    def test_normalize_keeps_first_seen_phrase_order_and_merges_same_token_set(self):            # spec §6 v1.25 (H10 review I2 + reviewer display)
        raw = {"time entry": ["worklog"], "entry time": ["blogpost"], "Blog Entries": ["blogpost"]}
        self.assertEqual(clc.normalize_raw(raw), {"time entry": ["blogpost", "worklog"], "blog entry": ["blogpost"]})
        kept, rej = clc.structural_check(clc.normalize_raw(raw), CONCEPTS | {"worklog", "blogpost"}, CATALOG, VERBS, HINTS, ALIAS_KEYS)
        self.assertEqual(rej["time entry"]["reason"], "multi_target"); self.assertEqual(kept, {"blog entry": ["blogpost"]})
        self.assertEqual(clc.phrase_set("time entry"), frozenset({"entry", "time"}))

    def test_in_catalog_cross_product_exception(self):                                             # spec §6 v1.25
        sources = {"workspace": {"jira-software"}, "space": {"confluence"}, "page": {"confluence"}, "board": {"jira-software"}}
        lex = {"workspace": ["space"], "board": ["page"], "page": ["space"]}
        kept, rej = clc.structural_check(lex, CONCEPTS | {"board"}, CATALOG | {"workspace", "board"}, VERBS, HINTS, ALIAS_KEYS, token_sources=sources)
        self.assertEqual(kept, {"workspace": ["space"], "board": ["page"]})                          # catalog words of another product may alias
        self.assertEqual(rej["page"]["reason"], "in_catalog")                                        # same product -> still in_catalog
        kept2, rej2 = clc.structural_check({"workspace": ["space"]}, CONCEPTS, CATALOG | {"workspace"}, VERBS, HINTS, ALIAS_KEYS)
        self.assertEqual(rej2["workspace"]["reason"], "in_catalog")                                  # without source data: strict as before
        kept3, rej3 = clc.structural_check({"entry": ["worklog"]}, CONCEPTS | {"worklog"}, CATALOG | {"entry"}, VERBS, HINTS, ALIAS_KEYS, token_sources=sources)
        self.assertEqual(rej3["entry"]["reason"], "in_catalog")                                      # H12 review I1: a summary-only catalog word (no resource sources) stays in_catalog

    def test_plural_synonym_rejected_after_normalization(self):
        kept, rej = clc.prepare_review({"files": ["attachments"], "File": ["attachment"]}, *ARGS)
        self.assertEqual(kept, {}); self.assertEqual({k: v["reason"] for k, v in rej.items()}, {"file": "in_catalog"})

    def test_structural_reasons(self):
        lex = {"note": ["comment"], "my": ["issue"], "get": ["issue"], "jira": ["issue"], "doc": ["page", "space"],
               "card": ["board"], "ticket": ["issue"], "e-mail": ["comment"]}
        kept, rej = clc.structural_check(lex, *ARGS)
        self.assertEqual(kept, {"note": ["comment"]})
        self.assertEqual({k: v["reason"] for k, v in rej.items()},
                         {"my": "function_word", "get": "verb", "jira": "product_hint", "doc": "multi_target",
                          "card": "target_not_concept", "ticket": "alias_conflict", "e-mail": "shape"})

    def test_id_like_rejected_after_shape(self):
        lex = {"404": ["issue"], "key": ["issue"], "w3": ["issue"]}
        kept, rej = clc.structural_check(lex, *ARGS)
        self.assertEqual(rej["404"]["reason"], "id_like")
        self.assertEqual(rej["key"]["reason"], "id_like")
        self.assertNotEqual(rej.get("w3", {}).get("reason"), "id_like")  # has a letter, not in ID_LIKE: id_like does not reject it

    def test_one_letter_synonym_rejected_as_shape(self):
        """Review M-6: tokenize_unigrams drops tokens shorter than 2, so such an alias could never fire."""
        kept, rej = clc.prepare_review({"x": ["issue"], "Q": ["page"], "xy": ["issue"]}, *ARGS)
        self.assertEqual(rej["x"]["reason"], "shape"); self.assertEqual(rej["q"]["reason"], "shape"); self.assertIn("xy", kept)

    def test_prepare_review_does_not_cap(self):
        raw = {f"w{i}": ["issue"] for i in range(8)}
        kept, _ = clc.prepare_review(raw, *ARGS)
        self.assertEqual(len(kept), 8)

    def test_validate_review_exact_keys_and_bools(self):
        keys = ["w0", "w1"]
        self.assertEqual(clc.validate_review({"w0": True, "w1": False}, keys), [])
        self.assertTrue(clc.validate_review({"w0": True}, keys))                       # missing
        self.assertTrue(clc.validate_review({"w0": True, "w1": False, "w9": True}, keys))  # extra
        self.assertTrue(clc.validate_review({"w0": True, "w1": "no"}, keys))           # non-bool
        self.assertTrue(clc.validate_review([True, False], keys))                      # non-object

    def test_validate_review_tolerates_extra_keys_that_are_structurally_rejected(self):
        """Round 3 re-gate (spec §5): the archived Round 2 review also judged words that the current structural stage
        now rejects (alias_conflict: merged as lexicon-r2). Those extra keys are tolerated; unknown extras still fail."""
        keys = ["w0", "w1"]
        review = {"w0": True, "w1": False, "ticket": True}
        self.assertTrue(clc.validate_review(review, keys))                                     # strict by default
        self.assertEqual(clc.validate_review(review, keys, structurally_rejected={"ticket"}), [])
        self.assertTrue(clc.validate_review({**review, "w9": True}, keys, structurally_rejected={"ticket"}))  # unknown extra
        self.assertTrue(clc.validate_review({"w0": True, "ticket": True}, keys, structurally_rejected={"ticket"}))  # still missing w1

    def test_build_regates_prior_round_review_with_structurally_rejected_extras(self):
        raw = {"note": ["comment"], "ticket": ["issue"], "get": ["issue"]}
        review = {"note": True, "ticket": True, "get": False}                                   # judged in a prior round
        lexicon, rej = clc.build(raw, review, *ARGS)
        self.assertEqual(lexicon, {"note": ["comment"]})
        self.assertEqual(rej["ticket"]["reason"], "alias_conflict"); self.assertEqual(rej["get"]["reason"], "verb")

    def test_phrase_keys_become_rule_candidates(self):                                             # Round 3 spec §6 (v1.24)
        lex = {"time entry": ["worklog"], "blog entry": ["blogpost"], "get entry": ["worklog"], "my own entry": ["worklog"], "issue page": ["page"], "jira entry": ["issue"]}
        kept, rej = clc.structural_check(lex, CONCEPTS | {"worklog", "blogpost"}, CATALOG | {"time", "entry", "blog", "worklog", "blogpost"},
                                         VERBS, HINTS, ALIAS_KEYS, rule_sets=frozenset({frozenset({"issue", "page"})}))
        self.assertEqual(kept, {"blog entry": ["blogpost"], "time entry": ["worklog"]})               # catalog words are fine inside a phrase
        self.assertEqual({k: v["reason"] for k, v in rej.items()}, {"get entry": "verb", "my own entry": "shape", "issue page": "rule_conflict", "jira entry": "product_hint"})

    def test_cap_counts_words_and_phrases_separately(self):
        lex = {f"w{i}": ["issue"] for i in range(6)}; lex.update({f"p{i} x": ["issue"] for i in range(6)})
        kept, rej = clc.cap_per_concept(lex)
        self.assertEqual(sum(1 for k in kept if " " in k), 5); self.assertEqual(sum(1 for k in kept if " " not in k), 5)
        self.assertEqual({v["reason"] for v in rej.values()}, {"concept-cap"})

    def test_merge_emits_rules_for_phrases(self):
        aliases = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {}, "rules": [{"when_all": ["issue", "key"], "add": ["getissue"]}],
                   "notes": {"rule:0": {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "x"}}}
        out, skipped = clc.merge(aliases, {"time entry": ["worklog"], "issue key": ["getissue"], "note": ["comment"]}, 3)
        self.assertEqual(out["rules"][1], {"when_all": ["entry", "time"], "add": ["worklog"]}); self.assertEqual(skipped, ["issue key"])
        self.assertEqual(out["notes"]["rule:1"], {"origin": "lexicon-r3", "seed_query_id": None, "failure_classes": [], "evidence": "concept lexicon r3 phrase"})
        self.assertEqual(out["aliases"], {"note": ["comment"]}); self.assertEqual(len(aliases["rules"]), 1)   # input untouched

    def test_union_docs_first_wins(self):
        self.assertEqual(clc.union_docs([{"release": ["build"], "note": ["comment"]}, {"release": ["version"], "starred": ["favourite"]}]),
                         {"release": ["build"], "note": ["comment"], "starred": ["favourite"]})

    def test_render_generation_input_is_deterministic_and_grounded(self):                           # spec §5(b) (v1.24)
        internal = [{"key": "jira-platform:GET:/rest/api/3/issue/{id}/worklog", "source": "jira-platform", "method": "GET", "operation_id": "getIssueWorklog",
                     "summary": "Get issue worklogs", "tags": ["Issue worklogs"], "description": "Returns worklogs for an issue.\tTime tracking must be enabled."},
                    {"key": "jira-platform:POST:/rest/api/3/issue", "source": "jira-platform", "method": "POST", "operation_id": "createIssue", "summary": "Create issue", "tags": ["Issues"], "description": ""}]
        ranking = {"path_noise": ["rest", "api", "3"], "verb_methods": {"get": ["GET"], "create": ["POST"]}}
        tpl = "HEAD\nCONCEPTS:\n<one line per concept: \"<token>\\t<count>\\t<products>\\t<excerpt>\">\nVERBS:\n<verb keys>\n"
        out = clc.render_lexicon_generation_input(tpl, internal, ranking)
        self.assertEqual(out, clc.render_lexicon_generation_input(tpl, internal, ranking))
        self.assertIn("worklog\t1\tjira-platform\tReturns worklogs for an issue.", out)                  # first sentence, tabs collapsed
        self.assertIn("\nissue\t2\tjira-platform\t-\n", out)                                             # smallest-key terminal op has no description -> '-'
        self.assertIn("VERBS:\ncreate, get\n", out); self.assertNotIn("<one line", out); self.assertNotIn("<verb keys>", out)

    def test_review_then_cap_recovers_sixth_synonym(self):
        kept = {f"w{i}": ["issue"] for i in range(7)}
        review = {f"w{i}": i not in (0, 1, 2) for i in range(7)}
        lexicon, rej = clc.finalize(kept, {}, review)
        self.assertEqual(sorted(lexicon), ["w3", "w4", "w5", "w6"])                   # 4 survive the review, all kept (<= 5)
        self.assertEqual(rej["w0"]["reason"], "semantic-reject")
        kept8 = {f"w{i}": ["issue"] for i in range(8)}
        lexicon8, rej8 = clc.finalize(kept8, {}, {k: True for k in kept8})
        self.assertEqual(sorted(lexicon8), ["w0", "w1", "w2", "w3", "w4"]); self.assertEqual(rej8["w7"]["reason"], "concept-cap")
        with self.assertRaises(ValueError):
            clc.finalize(kept, {}, {"w0": True})                                       # invalid review refused

    def test_build_is_deterministic_and_ordered(self):
        raw = {"Notes": ["comment"], "files": ["attachment"], "release": ["version"], "cards": ["board"]}
        review = {"note": True, "release": True}
        a = clc.build(raw, review, *ARGS, df={"file": 3}); b = clc.build(raw, review, *ARGS, df={"file": 3})
        self.assertEqual(a, b); self.assertEqual(a[0], {"note": ["comment"], "release": ["version"]})
        self.assertEqual(a[1]["file"]["catalog_df"], 3); self.assertEqual(a[1]["card"]["reason"], "target_not_concept")

    def test_merge_adds_lexicon_notes_and_skips_conflicts(self):
        aliases = {"version": 1, "alias_damping": 0.5, "rule_damping": 1.0, "aliases": {"ticket": ["issue"]}, "rules": [],
                   "notes": {"ticket": {"origin": "phase2.5", "seed_query_id": None, "failure_classes": [], "evidence": "x"}}}
        out, skipped = clc.merge(aliases, {"note": ["comment"], "ticket": ["issue"]}, 2)
        self.assertEqual(out["aliases"], {"ticket": ["issue"], "note": ["comment"]}); self.assertEqual(skipped, ["ticket"])
        self.assertEqual(out["notes"]["note"], {"origin": "lexicon-r2", "seed_query_id": None, "failure_classes": [], "evidence": "concept lexicon r2"})
        self.assertEqual(aliases["aliases"], {"ticket": ["issue"]})      # input untouched


class TestRound4DocTitles(unittest.TestCase):
    INTERNAL = [{"key": "jira-platform:GET:/rest/api/3/issue/{id}/worklog", "source": "jira-platform", "method": "GET", "operation_id": "getIssueWorklog",
                 "summary": "Get issue worklogs", "tags": ["Issue worklogs"], "description": "Returns worklogs for an issue."},
                {"key": "jira-platform:POST:/rest/api/3/issue", "source": "jira-platform", "method": "POST", "operation_id": "createIssue", "summary": "Create issue", "tags": ["Issues"], "description": ""}]
    RANKING = {"path_noise": ["rest", "api", "3"], "verb_methods": {"get": ["GET"], "create": ["POST"]}}
    TPL = ('C:\n<one line per concept: "<token>\\t<count>\\t<products>\\t<excerpt>">\nT:\n<one line per concept title: "<token>\\t<product>\\t<title words>">\nV:\n<verb keys>\n')
    SNAP = {"titles": [{"product": "jira-software-cloud", "url": "u", "title": "Create an issue", "tokens": ["create", "an", "issue"]}]}

    def test_render_generation_input_with_doc_titles_block_and_attachment(self):
        out = clc.render_lexicon_generation_input(self.TPL, self.INTERNAL, self.RANKING, doc_snapshot=self.SNAP)
        self.assertIn("issue\tjira-software-cloud\tCreate an issue", out); self.assertNotIn("<one line per concept title", out)
        self.assertIn("worklog\t-", out)
        self.assertEqual(clc.render_lexicon_generation_input(self.TPL, self.INTERNAL, self.RANKING, doc_snapshot=self.SNAP), out)

    def test_render_generation_input_never_opens_benchmark(self):
        import builtins, pathlib
        real_open, real_read = builtins.open, pathlib.Path.read_text
        def guard_open(path, *a, **k):
            if "search_queries" in str(path): raise AssertionError("benchmark read")
            return real_open(path, *a, **k)
        def guard_read(self_, *a, **k):
            if "search_queries" in str(self_): raise AssertionError("benchmark read")
            return real_read(self_, *a, **k)
        with mock.patch("builtins.open", guard_open), mock.patch.object(pathlib.Path, "read_text", guard_read):
            clc.render_lexicon_generation_input(self.TPL, self.INTERNAL, self.RANKING, doc_snapshot={"titles": []})
CTX5 = (CONCEPTS | {"build", "favourite", "filter"}, CATALOG | {"build"}, VERBS, HINTS, ALIAS_KEYS, frozenset(), None)


class TestRound5Union(unittest.TestCase):
    """Round 5 spec §6.1/§6.3: source precedence, seed-free eligibility, no fallback, pair-level review reuse."""
    def _src(self, r2=None, r4=None):
        return [{"id": "round2_archive", "raw": r2 or {}}, {"id": "round4_generation", "raw": r4 or {}}]

    def test_lower_rank_ineligible_higher_rank_eligible(self):                       # (a)
        v = {(("release",), ("version",)): True, (("release",), ("build",)): False}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertEqual(out["lexicon"], {"release": ["version"]}); self.assertEqual(out["selected"]["release"]["source"], "round4_generation")

    def test_both_eligible_highest_rank_wins(self):                                   # (b)
        v = {(("release",), ("version",)): True, (("release",), ("build",)): True}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertEqual(out["lexicon"]["release"], ["version"]); self.assertEqual(out["selected"]["release"]["provenance_rank"], 1)

    def test_higher_rank_rejected_lower_rank_used(self):                              # (c)
        v = {(("release",), ("version",)): False, (("release",), ("build",)): True}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertEqual(out["lexicon"]["release"], ["build"])

    def test_all_ineligible_records_every_candidate(self):                             # (d)
        v = {(("release",), ("version",)): False, (("release",), ("build",)): False}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        self.assertNotIn("release", out["lexicon"])
        self.assertEqual([c["source"] for c in out["rejected"]["release"]["candidates"]], ["round2_archive", "round4_generation"])

    def test_input_order_does_not_matter(self):                                        # (e)
        v = {(("release",), ("version",)): True, (("release",), ("build",)): True}
        a = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        b = clc.resolve_sources(list(reversed(self._src({"release": ["build"]}, {"release": ["version"]}))), CTX5, v)
        self.assertEqual(a, b)

    def test_resolution_reads_no_benchmark(self):                                       # (f) seed-independence
        src = self._src({"release": ["build"]}, {"release": ["version"]}); v = {(("release",), ("version",)): True}
        with mock.patch("builtins.open", side_effect=AssertionError("resolution must not read files")), \
             mock.patch("pathlib.Path.read_text", side_effect=AssertionError("resolution must not read files")):
            out = clc.resolve_sources(src, CTX5, v)
        self.assertEqual(out["lexicon"], {"release": ["version"]})

    def test_gate_removal_never_falls_back(self):                                       # (g)
        from tests.benchmarks import alias_candidates_tool as act
        v = {(("release",), ("version",)): True, (("release",), ("build",)): True}
        out = clc.resolve_sources(self._src({"release": ["build"]}, {"release": ["version"]}), CTX5, v)
        doc = {"lexicon": dict(out["lexicon"]), "rejected": dict(out["rejected"])}
        bench = {"seed": [{"id": "s-1", "query": "publish a release", "expected_top1_any": ["p:POST:/build"]}]}
        by_key = {"p:POST:/build": {"key": "p:POST:/build", "operation_id": "build", "summary": "build", "tags": []}}
        ranking = {"verb_methods": {"publish": ["POST"]}, "path_noise": [], "product_hints": {}}
        doc, rejected = act.lexicon_gate(doc, bench, by_key, ranking)
        self.assertEqual(rejected, ["release"]); self.assertNotIn("release", doc["lexicon"])      # removed, not replaced by release→build

    def test_review_pairs_and_conflicts(self):
        text = 'header\nENTRIES:\n{\n "access combination": ["combination"],\n "release": ["build"]\n}\n'
        pairs = clc.review_pairs(text, {"access combination": False, "release": True})
        self.assertEqual(pairs, {(("access", "combination"), ("combination",)): False, (("release",), ("build",)): True})
        agreed, conflicts = clc.merge_verdicts([pairs, {(("release",), ("build",)): False}])
        self.assertEqual(conflicts, [(("release",), ("build",))]); self.assertNotIn((("release",), ("build",)), agreed)

    def test_conflicting_past_verdicts_are_pending(self):
        agreed, conflicts = clc.merge_verdicts([{(("release",), ("version",)): True}, {(("release",), ("version",)): False}])
        out = clc.resolve_sources(self._src(None, {"release": ["version"]}), CTX5, agreed)
        self.assertEqual(out["pending"], [(("release",), ("version",), "release")]); self.assertNotIn("release", out["lexicon"])

    def test_cap_removed_entry_keeps_provenance(self):
        raw4 = {w: ["issue"] for w in ("aaa", "bbb", "ccc", "ddd", "eee", "fff")}           # 6 words on one concept → cap keeps 5
        v = {((w,), ("issue",)): True for w in raw4}
        out = clc.resolve_sources(self._src(None, raw4), (CONCEPTS, CATALOG, VERBS, HINTS, set(), frozenset(), None), v)
        self.assertEqual(out["rejected"]["fff"]["reason"], "concept-cap"); self.assertEqual(out["selected"]["fff"]["source"], "round4_generation")
        self.assertNotIn("fff", out["lexicon"])

    def test_fresh_verdict_resolves_conflict(self):
        past = [{(("release",), ("version",)): True}, {(("release",), ("version",)): False}]
        for fresh_v in (True, False):
            eff, left = clc.resolve_verdicts(past, [{(("release",), ("version",)): fresh_v}])
            self.assertEqual(eff[(("release",), ("version",))], fresh_v); self.assertEqual(left, [])
        eff, left = clc.resolve_verdicts(past, [])
        self.assertNotIn((("release",), ("version",)), eff); self.assertEqual(left, [(("release",), ("version",))])
        eff, _ = clc.resolve_verdicts([{(("ticket",), ("issue",)): True}], [{(("ticket",), ("issue",)): False}])
        self.assertTrue(eff[(("ticket",), ("issue",))])                                   # fresh never overrides an agreed past verdict

    def test_render_pending_review_batches_unique_keys(self):
        tpl = 'Reply ONLY with JSON.\n\nENTRIES:\n<the "lexicon" object of lexicon_structural.json>\n'
        texts = clc.render_pending_review(tpl, [(("release",), ("version",), "release"), (("release",), ("build",), "release")])
        self.assertEqual(len(texts), 2)
        self.assertEqual([json.loads(t.split("ENTRIES:\n", 1)[1]) for t in texts], [{"release": ["build"]}, {"release": ["version"]}])
    def test_cli_resolve_writes_pending_then_lexicon(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td); tpl = d / "tpl.md"; tpl.write_text('ENTRIES:\n<the "lexicon" object of lexicon_structural.json>\n')
            (d / "r2.json").write_text(json.dumps({"release": ["build"]})); (d / "r4.json").write_text(json.dumps({"release": ["version"]}))
            (d / "rv2.json").write_text(json.dumps({"release": False})); (d / "ri2.txt").write_text('ENTRIES:\n{"release": ["build"]}\n')
            (d / "rv4.json").write_text(json.dumps({})); (d / "ri4.txt").write_text('ENTRIES:\n{}\n')
            args = ["resolve", "--cache-dir", "unused", "--round", "5", "--template", str(tpl),
                    "--source", "round2_archive", str(d / "r2.json"), str(d / "rv2.json"), str(d / "ri2.txt"),
                    "--source", "round4_generation", str(d / "r4.json"), str(d / "rv4.json"), str(d / "ri4.txt"),
                    "--pending-out", str(d / "pending"), "--out", str(d / "lex.json")]
            with mock.patch.object(clc, "_context", return_value=(None, "fp", {}, {"verb_methods": {}}, {}, CTX5)):
                self.assertEqual(clc.main(args), 3)                                    # release→version unreviewed
                (d / "rv5.json").write_text(json.dumps({"release": True}))
                self.assertEqual(clc.main(args + ["--review-r5", str(d / "rv5.json"), str(d / "pending" / "review-input-1.txt")]), 0)
            doc = json.loads((d / "lex.json").read_text())
            self.assertEqual(doc["lexicon"], {"release": ["version"]}); self.assertEqual(doc["components"]["union_resolution"], "source-precedence")
