import json, unittest
from tests.benchmarks import concept_lexicon_check as clc

CONCEPTS = {"issue", "comment", "page", "sprint", "attachment", "version", "space"}
CATALOG = CONCEPTS | {"file", "get", "workspace", "linked"}
VERBS, HINTS, ALIAS_KEYS = {"get", "create"}, {"jira", "confluence"}, {"ticket"}
ARGS = (CONCEPTS, CATALOG, VERBS, HINTS, ALIAS_KEYS)


class TestChecks(unittest.TestCase):
    def test_normalize_lowercases_singularizes_and_merges(self):
        raw = {"Tickets": ["issue"], "ticket": ["issues"], "notes": ["comment"]}
        self.assertEqual(clc.normalize_raw(raw), {"note": ["comment"], "ticket": ["issue"]})

    def test_normalize_sorts_phrase_tokens_so_reordered_phrases_collide(self):                        # H10 review I2
        raw = {"entry time": ["blogpost"], "time entry": ["worklog"], "Blog Entries": ["blogpost"]}
        self.assertEqual(clc.normalize_raw(raw), {"blog entry": ["blogpost"], "entry time": ["blogpost", "worklog"]})
        kept, rej = clc.structural_check(clc.normalize_raw(raw), CONCEPTS | {"worklog", "blogpost"}, CATALOG, VERBS, HINTS, ALIAS_KEYS)
        self.assertEqual(rej["entry time"]["reason"], "multi_target"); self.assertEqual(kept, {"blog entry": ["blogpost"]})

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
