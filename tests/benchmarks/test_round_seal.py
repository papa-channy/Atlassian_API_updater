import hashlib, json, pathlib, subprocess, tempfile, unittest
from unittest import mock
from tests.benchmarks import evaluator as ev
from tests.benchmarks import round_seal as rs

CAT = [  # A..H: 8 synthetic ops covering jira-platform / jira-software / confluence and GET/POST/PUT/DELETE
    {"key": "jira-platform:GET:/rest/api/3/issue/{issueIdOrKey}", "source": "jira-platform", "method": "GET",
     "operation_id": "getIssue", "summary": "Get issue", "tags": ["Issues"], "description": "Returns the details for an issue."},
    {"key": "confluence:POST:/pages", "source": "confluence", "method": "POST",
     "operation_id": "createPage", "summary": "Create page", "tags": ["Page"], "description": "Creates a page in the space."},
    {"key": "jira-platform:DELETE:/rest/api/3/issue/{issueIdOrKey}", "source": "jira-platform", "method": "DELETE",
     "operation_id": "deleteIssue", "summary": "Delete issue", "tags": ["Issues"], "description": "Deletes an issue."},
    {"key": "jira-software:GET:/rest/agile/1.0/board", "source": "jira-software", "method": "GET",
     "operation_id": "getAllBoards", "summary": "Get all boards", "tags": ["Board"], "description": "Returns all boards."},
    {"key": "jira-software:PUT:/rest/agile/1.0/sprint/{sprintId}", "source": "jira-software", "method": "PUT",
     "operation_id": "updateSprint", "summary": "Update sprint", "tags": ["Sprint"], "description": "Performs a full update of a sprint."},
    {"key": "jira-platform:PUT:/rest/api/3/issue/{issueIdOrKey}/assignee", "source": "jira-platform", "method": "PUT",
     "operation_id": "assignIssue", "summary": "Assign issue", "tags": ["Issues"], "description": "Assigns an issue to a user."},
    {"key": "confluence:GET:/pages/{id}", "source": "confluence", "method": "GET",
     "operation_id": "getPageById", "summary": "Get page by id", "tags": ["Page"], "description": "Returns a specific page."},
    {"key": "jira-software:POST:/rest/agile/1.0/sprint", "source": "jira-software", "method": "POST",
     "operation_id": "createSprint", "summary": "Create sprint", "tags": ["Sprint"], "description": "Creates a future sprint."},
]
A, B, C, D, E, F, G, H = (c["key"] for c in CAT)
BENCH = {"seed": [{"id": "s-001", "query": "get issue by key", "expected_top1_any": [A], "forbidden_top1": [],
                   "origin": "seed-r0", "failure_classes": [], "ambiguous": False}], "regression_negative": []}


def rec(i, q, key, **kw):
    return {"id": f"h-{i:03d}", "query": q, "expected_top1_any": [key], "forbidden_top1": [], "origin": "held_out-r1",
            "failure_classes": [], "ambiguous": False, **kw}


def neg(i, q, key):
    return {"id": f"n-{i:03d}", "query": q, "expected_top1_any": [], "forbidden_top1": [key], "origin": "negative-r1",
            "failure_classes": [], "ambiguous": False}


def valid_plain():
    """16 held_out + 8 negative satisfying every machine rule against CAT.
    Sources: jira-platform 6 (h1,3,6,9,11,16), jira-software 5 (h4,5,8,12,14), confluence 5 (h2,7,10,13,15).
    Methods: GET 7, POST 5, PUT 2 (h5,h6), DELETE 2 (h3,h11). Product-named: h4,h5,h7,h16 (4); unnamed 12.
    Every query is 3-7 words, never equals an operationId unigram set, never copies 2 consecutive summary/tag tokens."""
    held = [rec(1, "show me the ticket details", A), rec(2, "publish a brand new document", B), rec(3, "throw away the ticket", C),
            rec(4, "list every jira board", D), rec(5, "rename the current jira sprint", E), rec(6, "hand the ticket to someone", F),
            rec(7, "open the confluence document", G), rec(8, "kick off a fresh sprint", H), rec(9, "bring up my ticket", A),
            rec(10, "write a fresh wiki entry", B), rec(11, "erase the ticket record", C), rec(12, "which agile boards exist", D),
            rec(13, "author a document today", B), rec(14, "start another sprint now", H), rec(15, "read one wiki document", G),
            rec(16, "see a jira ticket", A)]
    negs = [neg(1, "ticket status field values", A), neg(2, "issue type scheme entries", C), neg(3, "document space overview", G),
            neg(4, "jira ticket owner list", F), neg(5, "confluence document tree", B), neg(6, "sprint board settings", D),
            neg(7, "ticket record archive", C), neg(8, "page tree layout", G)]
    return {"held_out": held, "negative": negs}


class TestMachineCheck(unittest.TestCase):
    """One failing test per machine rule of spec §5.4 (review finding P0-8)."""
    def _msgs(self, mutate):
        plain = valid_plain(); mutate(plain)
        return rs.machine_check(plain, BENCH, CAT)

    def test_valid_plaintext_has_no_violations(self):
        self.assertEqual(rs.machine_check(valid_plain(), BENCH, CAT), [])

    def test_word_count_bounds(self):
        self.assertTrue(any("h-001" in m and "words" in m for m in self._msgs(lambda p: p["held_out"][0].__setitem__("query", "ticket now"))))
        self.assertTrue(any("h-001" in m and "words" in m for m in self._msgs(lambda p: p["held_out"][0].__setitem__("query", "a b c d e f g h ticket"))))
        self.assertTrue(any("n-001" in m and "words" in m for m in self._msgs(lambda p: p["negative"][0].__setitem__("query", "ticket"))))

    def test_operation_id_unigram_set_rejected(self):
        self.assertTrue(any("h-001" in m and "operationId" in m for m in self._msgs(lambda p: p["held_out"][0].__setitem__("query", "get the issue"))))

    def test_summary_two_consecutive_tokens_rejected(self):
        self.assertTrue(any("h-002" in m and "summary" in m for m in self._msgs(lambda p: p["held_out"][1].__setitem__("query", "please create page today"))))
        self.assertTrue(any("h-004" in m and "summary" in m for m in self._msgs(lambda p: p["held_out"][3].__setitem__("query", "get all boards please"))))

    def test_reuse_against_seed_and_within_hidden(self):
        self.assertTrue(any("h-001" in m and "reuse" in m for m in self._msgs(lambda p: p["held_out"][0].__setitem__("query", "get issue by key"))))
        self.assertTrue(any("reuse" in m for m in self._msgs(lambda p: p["held_out"][1].__setitem__("query", p["held_out"][0]["query"]))))
        self.assertTrue(any("reuse" in m for m in self._msgs(lambda p: p["negative"][0].__setitem__("query", "details the ticket show me"))))  # same unigram set as h-001

    def test_counts_and_distributions(self):
        self.assertTrue(any("held_out" in m and "16" in m for m in self._msgs(lambda p: p["held_out"].pop())))
        self.assertTrue(any("negative" in m and "8" in m for m in self._msgs(lambda p: p["negative"].pop())))
        def all_confluence(p):
            for r in p["held_out"]: r["expected_top1_any"] = [B]
        self.assertTrue(any("source" in m for m in self._msgs(all_confluence)))
        def no_put(p):
            p["held_out"][4]["expected_top1_any"] = [H]; p["held_out"][5]["expected_top1_any"] = [A]
        self.assertTrue(any("method" in m for m in self._msgs(no_put)))
        def no_product(p):
            for r in p["held_out"]: r["query"] = r["query"].replace("jira ", "big ").replace("confluence ", "team ")
        self.assertTrue(any("product_named" in m for m in self._msgs(no_product)))

    def test_negative_schema_and_unknown_keys(self):
        self.assertTrue(any("n-001" in m for m in self._msgs(lambda p: p["negative"][0].__setitem__("expected_top1_any", [A]))))
        self.assertTrue(any("n-002" in m and "forbidden" in m for m in self._msgs(lambda p: p["negative"][1].__setitem__("forbidden_top1", []))))
        self.assertTrue(any("h-003" in m and "catalog" in m for m in self._msgs(lambda p: p["held_out"][2].__setitem__("expected_top1_any", ["jira-platform:POST:/nope"]))))
        self.assertTrue(any("n-003" in m and "catalog" in m for m in self._msgs(lambda p: p["negative"][2].__setitem__("forbidden_top1", ["confluence:GET:/nope"]))))

    def test_ambiguous_distribution_uses_first_expected_key(self):
        d = rs.distribution([rec(1, "show me the ticket", A), rec(2, "start new page", B, ambiguous=True, expected_top1_any=[B, A])], "held_out")
        self.assertEqual(d["source"], {"jira-platform": 1, "confluence": 1}); self.assertEqual(d["method"], {"GET": 1, "POST": 1}); self.assertEqual(d["product_named"], 0)
        dn = rs.distribution([neg(1, "ticket record archive", C)], "negative")
        self.assertEqual(dn["source"], {"jira-platform": 1}); self.assertEqual(dn["method"], {"DELETE": 1})

    def test_seal_metadata_contract(self):
        recs = valid_plain()["held_out"]
        meta = rs.seal_metadata(recs, 1, "held_out")
        self.assertEqual(meta["count"], 16); self.assertEqual(meta["sha256"], rs.canonical_sha256(recs)); self.assertTrue(meta["sealed"]); self.assertEqual(meta["round"], 1)
        self.assertEqual(meta["distribution"], rs.distribution(recs, "held_out"))

    def test_generator_view_hides_operation_id_and_description(self):
        for r in rs.generator_view(CAT):
            self.assertEqual(set(r), {"key", "source", "method", "summary", "tags"})


class TestHiddenOriginAndIds(unittest.TestCase):
    """Fix round 1: origin/id-prefix per section and cross-section duplicate ids."""
    def _msgs(self, mutate):
        plain = valid_plain(); mutate(plain)
        return rs.machine_check(plain, BENCH, CAT)

    def test_held_out_bad_origin_rejected(self):
        msgs = self._msgs(lambda p: p["held_out"][0].__setitem__("origin", "held_out-r0"))
        self.assertTrue(any(m.startswith("h-001") and "origin" in m for m in msgs))

    def test_negative_bad_origin_rejected(self):
        msgs = self._msgs(lambda p: p["negative"][0].__setitem__("origin", "held_out-r1"))
        self.assertTrue(any(m.startswith("n-001") and "origin" in m for m in msgs))

    def test_n_id_inside_held_out_rejected(self):
        msgs = self._msgs(lambda p: p["held_out"][0].__setitem__("id", "n-099"))
        self.assertTrue(any(m.startswith("n-099") and "id" in m and "held_out" in m for m in msgs))

    def test_h_id_inside_negative_rejected(self):
        msgs = self._msgs(lambda p: p["negative"][0].__setitem__("id", "h-099"))
        self.assertTrue(any(m.startswith("h-099") and "id" in m and "negative" in m for m in msgs))

    def test_duplicate_id_across_sections_rejected(self):
        msgs = self._msgs(lambda p: p["negative"][0].__setitem__("id", "h-001"))
        self.assertTrue(any(m.startswith("h-001") and "duplicate id" in m for m in msgs))


class TestRoundParameter(unittest.TestCase):
    def test_origin_and_seal_key_follow_round(self):
        self.assertEqual(rs.section_origin(2), {"held_out": "held_out-r2", "negative": "negative-r2"})
        self.assertEqual(rs.seal_key(2), "round2_seal")
        plain = valid_plain()
        self.assertEqual(rs.machine_check(plain, BENCH, CAT, round=1), [])
        msgs = rs.machine_check(plain, BENCH, CAT, round=2)
        self.assertTrue(all("origin" in m for m in msgs) and len(msgs) == 24)

    def test_seal_key_is_per_round(self):
        import json, pathlib, tempfile
        from unittest import mock
        plain = valid_plain()
        for r in plain["held_out"] + plain["negative"]:
            r["origin"] = r["origin"].replace("-r1", "-r2")
        bench = {**BENCH, "held_out": [], "negative": [], "round1_seal": {"held_out_sha256": "0" * 64}}
        with tempfile.TemporaryDirectory() as td:
            bp, pp = pathlib.Path(td) / "b.json", pathlib.Path(td) / "p.json"
            bp.write_text(json.dumps(bench)); pp.write_text(json.dumps(plain))
            fake = lambda cache_dir, round=1: (rs.generator_view(CAT), CAT, "f" * 64, {"jira-platform": "a" * 64})
            argv = ["seal", "--round", "2", "--plain", str(pp), "--bench", str(bp), "--cache-dir", td]
            entry = {"round": 2, "source_registry_fingerprint": "f" * 64, "source_spec_sha256": {"jira-platform": "a" * 64}}
            with mock.patch.object(rs, "load_catalogs_from_cache", fake), mock.patch("builtins.print"):
                # M-9: no round 2 freeze entry -> refused; a snapshot that differs from the freeze -> refused
                with mock.patch.object(rs.ev, "freeze_for", side_effect=KeyError("round 2")):
                    self.assertEqual(rs.main(argv), 1)
                with mock.patch.object(rs.ev, "freeze_for", return_value={**entry, "source_registry_fingerprint": "0" * 64}):
                    self.assertEqual(rs.main(argv), 1)
                self.assertNotIn("round2_seal", json.loads(bp.read_text()))
            with mock.patch.object(rs, "load_catalogs_from_cache", fake), mock.patch("builtins.print"), \
                 mock.patch.object(rs.ev, "freeze_for", return_value=entry):
                self.assertEqual(rs.main(argv), 0)
                out = json.loads(bp.read_text())
                self.assertIn("round2_seal", out); self.assertIn("round1_seal", out)
                self.assertEqual(out["round2_seal"]["machine_check"], "passed")
                self.assertEqual(out["round2_seal"]["origins"], rs.section_origin(2))
                self.assertEqual(out["held_out"]["round"], 2)
                self.assertEqual(rs.main(["seal", "--round", "2", "--plain", str(pp), "--bench", str(bp), "--cache-dir", td]), 1)


I = {"key": "jira-software:GET:/rest/agile/1.0/board/list", "source": "jira-software", "method": "GET",
     "operation_id": "listBoards", "summary": "Show all boards", "tags": ["Board"], "description": "Lists boards."}
CAT_R2 = CAT + [I]


class TestRound2NegativePhraseRule(unittest.TestCase):
    def _plain(self):
        plain = valid_plain()
        for r in plain["held_out"] + plain["negative"]:
            r["origin"] = r["origin"].replace("-r1", "-r2")
        return plain

    def test_phrase_tokens(self):
        self.assertEqual(rs.phrase_tokens("Show all the Boards"), ("show", "all", "board"))
        self.assertEqual(rs.phrase_tokens("Board"), ("board",)); self.assertEqual(rs._last_literal_segment(D), "board")
        self.assertEqual(rs.phrase_tokens("1.0"), ("1", "0"))                           # digits are tokens; only the LAST segment is compared

    def test_negative_equal_to_summary_phrase_rejected(self):
        # I: summary phrase ("show","all","board") but operationId words {list, boards}: the Round 1 operationId rule does
        # NOT fire for "show all boards", so Round 1 = 0 violations and Round 2 = exactly the new negative-phrase rule.
        plain = self._plain(); plain["negative"][0]["query"] = "show all boards"
        msgs = rs.machine_check(plain, BENCH, CAT_R2, round=2)
        self.assertTrue(any(m.startswith("n-001") and "summary phrase" in m for m in msgs), msgs)
        plain1 = valid_plain(); plain1["negative"][0]["query"] = "show all boards"
        self.assertEqual(rs.machine_check(plain1, BENCH, CAT_R2, round=1), [])          # Round 1 rule set unchanged

    def test_negative_equal_to_last_path_segment_rejected(self):
        plain = self._plain(); plain["negative"][1]["query"] = "assignee of this"       # 3 words; of/this are STOPWORDS
        self.assertEqual(rs.phrase_tokens(plain["negative"][1]["query"]), rs.phrase_tokens(rs._last_literal_segment(F)))
        msgs = rs.machine_check(plain, BENCH, CAT, round=2)
        self.assertTrue(any(m.startswith("n-002") and "path phrase" in m for m in msgs), msgs)

    def test_valid_round2_plain_has_no_violations(self):
        self.assertEqual(rs.machine_check(self._plain(), BENCH, CAT, round=2), [])


class TestReviewerOutputValidator(unittest.TestCase):
    def test_exact_keys_and_schema(self):
        ids = ["h-001", "n-001"]
        good = {"h-001": {"accept": True, "reason": "ok"}, "n-001": {"accept": False, "reason": "answerable"}}
        self.assertEqual(rs.validate_reviewer_output(good, ids), [])
        self.assertTrue(rs.validate_reviewer_output({"h-001": good["h-001"]}, ids))                         # missing
        self.assertTrue(rs.validate_reviewer_output({**good, "h-999": good["h-001"]}, ids))                 # extra
        self.assertTrue(rs.validate_reviewer_output({**good, "n-001": {"accept": "no", "reason": "x"}}, ids))  # non-bool
        self.assertTrue(rs.validate_reviewer_output({**good, "n-001": "reject"}, ids))                       # non-object
        self.assertTrue(rs.validate_reviewer_output(["h-001"], ids))


class TestVerifyFreeze(unittest.TestCase):
    def test_verify_freeze_compares_fingerprint_and_spec_shas(self):
        from unittest import mock
        shas = {"jira-platform": "a" * 64, "jira-software": "b" * 64, "confluence": "c" * 64}
        entry = {"round": 2, "source_registry_fingerprint": "f" * 64, "source_spec_sha256": dict(shas)}
        fake = lambda cache_dir, round=1: ([], CAT, "f" * 64, dict(shas))
        with mock.patch.object(rs, "load_catalogs_from_cache", fake), mock.patch.object(rs.ev, "freeze_for", lambda r: entry):
            self.assertEqual(rs.verify_freeze(2, "x"), [])
        bad = lambda cache_dir, round=1: ([], CAT, "f" * 64, {**shas, "confluence": "d" * 64})
        with mock.patch.object(rs, "load_catalogs_from_cache", bad), mock.patch.object(rs.ev, "freeze_for", lambda r: entry):
            self.assertEqual(rs.verify_freeze(2, "x"), ["spec_sha256[confluence] differs from round_freeze"])

class TestReplacementHelpers(unittest.TestCase):
    def test_validate_and_merge_replacements(self):
        plain = valid_plain()
        new = [{**plain["held_out"][2], "query": "wipe out the whole ticket"}]
        self.assertEqual(rs.validate_replacement_output(new, ["h-003"]), [])
        self.assertTrue(rs.validate_replacement_output(new, ["h-003", "h-004"]))                 # missing
        self.assertTrue(rs.validate_replacement_output(new + [plain["held_out"][0]], ["h-003"]))  # unexpected
        self.assertTrue(rs.validate_replacement_output({"h-003": new[0]}, ["h-003"]))            # not a list
        merged = rs.merge_replacements(plain, new)
        self.assertEqual(merged["held_out"][2]["query"], "wipe out the whole ticket")
        self.assertEqual([r["id"] for r in merged["held_out"]], [r["id"] for r in plain["held_out"]])
        self.assertEqual(merged["negative"], plain["negative"])
        manifest = rs.coverage_manifest(merged, {r["id"]: 1 for s in ("held_out", "negative") for r in merged[s]})
        self.assertEqual(len(manifest), 24); self.assertEqual(manifest["h-003"]["record_sha256"], rs.canonical_sha256(new[0]))
        ids = [r["id"] for s in ("held_out", "negative") for r in merged[s]]
        shas = {r["id"]: rs.canonical_sha256(r) for s in ("held_out", "negative") for r in merged[s]}
        attempts = [{"attempt_no": 1, "stage": "review", "status": "valid", "reviewed_record_shas": shas, "accepted_ids": ids}]
        self.assertEqual(rs.verify_coverage(manifest, merged, attempts), [])
        self.assertTrue(rs.verify_coverage(manifest, merged, [{**attempts[0], "status": "invalid"}]))
        self.assertTrue(rs.verify_coverage(manifest, merged, [{**attempts[0], "accepted_ids": [i for i in ids if i != "h-003"]}]))   # reviewed but rejected
        old = {**shas, "h-003": rs.canonical_sha256(plain["held_out"][2])}
        self.assertTrue(rs.verify_coverage(manifest, merged, [{**attempts[0], "reviewed_record_shas": old}]))                  # reviewed the OLD h-003
        self.assertTrue(rs.verify_coverage(manifest, plain, attempts))                                                        # stale manifest sha


VERBS = {"get": ["GET"], "show": ["GET"], "list": ["GET"], "create": ["POST"], "publish": ["POST"], "start": ["POST"],
         "delete": ["DELETE"], "erase": ["DELETE"], "remove": ["DELETE"], "update": ["PUT"], "rename": ["PUT", "POST"], "assign": ["PUT", "POST"]}


def rec3(i, q, key):
    return {**rec(i, q, key), "origin": "held_out-r3"}


def neg3(i, q, key):
    return {**neg(i, q, key), "origin": "negative-r3"}


def valid_plain_r3():
    """Round 3 shape of valid_plain(): same expected keys/distribution; every held_out query carries a verb whose method matches
    its expected op; negatives: n1-n4 actionable with the forbidden op's method inside the intent, n5-n8 verb-less."""
    held = [rec3(1, "show me the ticket details", A), rec3(2, "publish a brand new document", B), rec3(3, "erase the whole ticket", C),
            rec3(4, "list every jira board", D), rec3(5, "rename the current jira sprint", E), rec3(6, "assign the ticket to someone", F),
            rec3(7, "show the confluence document", G), rec3(8, "start a fresh sprint", H), rec3(9, "get my ticket now", A),
            rec3(10, "publish a fresh wiki entry", B), rec3(11, "remove the ticket record", C), rec3(12, "list which agile boards exist", D),
            rec3(13, "create a document today", B), rec3(14, "start another sprint now", H), rec3(15, "show one wiki document", G),
            rec3(16, "get a jira ticket", A)]
    negs = [neg3(1, "delete the ticket status field", C), neg3(2, "update the issue type scheme", E), neg3(3, "show the document space overview", G),
            neg3(4, "assign jira ticket owner", F), neg3(5, "confluence document tree", B), neg3(6, "sprint board settings", D),
            neg3(7, "ticket record archive", C), neg3(8, "page tree layout", G)]
    return {"held_out": held, "negative": negs}


class TestRound3ActionabilityRules(unittest.TestCase):
    def check(self, plain):
        return rs.machine_check(plain, BENCH, CAT, round=3, verb_methods=VERBS)

    def test_valid_round3_plain_has_no_violations(self):
        self.assertEqual(self.check(valid_plain_r3()), [])
        self.assertEqual(rs.negative_distribution(valid_plain_r3()["negative"], VERBS), (4, 4))
        with self.assertRaises(ValueError):
            rs.machine_check(valid_plain_r3(), BENCH, CAT, round=3)                                  # round >= 3 needs the inventory
        self.assertEqual(rs.machine_check(valid_plain(), BENCH, CAT), [])                            # round 1 unchanged

    def test_actionable_rule_three_branches(self):                                                     # review focus 1
        p = valid_plain_r3(); p["held_out"][0]["expected_top1_any"] = [C]                              # show (GET) vs DELETE op: intent non-empty, expected outside
        msgs = self.check(p); self.assertEqual([rs.rule_id(m) for m in msgs], ["actionable"]); self.assertTrue(msgs[0].startswith("h-001: actionable:"))
        p = valid_plain_r3(); p["held_out"][0]["query"] = "create and delete the ticket"              # empty intersection
        self.assertEqual([rs.rule_id(m) for m in self.check(p)], ["actionable"])
        p = valid_plain_r3(); p["held_out"][0]["query"] = "the ticket details please"                 # no verb
        self.assertEqual([rs.rule_id(m) for m in self.check(p)], ["actionable"])
        self.assertEqual(self.check(valid_plain_r3()), [])                                           # non-empty + expected inside -> pass

    def test_negative_method_rule_applies_to_actionable_negatives_only(self):
        p = valid_plain_r3(); p["negative"][0]["forbidden_top1"] = [A]                                  # delete (DELETE) vs GET op
        msgs = self.check(p); self.assertEqual([rs.rule_id(m) for m in msgs], ["negative-method"]); self.assertTrue(msgs[0].startswith("n-001: negative-method:"))
        p = valid_plain_r3(); p["negative"][4]["forbidden_top1"] = [A]                                  # abstained n-005: rule does not apply
        self.assertEqual(self.check(p), [])

    def test_negative_distribution_must_be_exactly_four_four(self):
        # NOTE (task-6 concern): brief's literal query "show the document tree" makes n-005 actionable via "show" (GET),
        # but forbidden_top1 is still B (confluence:POST:/pages) -> that also trips negative-method (GET vs POST), which
        # this test does not expect. "publish" (POST) keeps the intent inside the forbidden method, isolating the
        # negative-distribution violation this test targets; see task-6-report.md for the computation.
        p = valid_plain_r3(); p["negative"][4]["query"] = "publish the document tree"                  # 5 actionable / 3 abstained
        msgs = self.check(p); self.assertEqual([rs.rule_id(m) for m in msgs], ["negative-distribution"])
        self.assertIn("5 actionable / 3 abstained", msgs[0])
        p = valid_plain_r3(); p["negative"][0]["query"] = "ticket status field values"                # 3 / 5
        self.assertEqual([rs.rule_id(m) for m in self.check(p)], ["negative-distribution"])

    def test_rule_id_covers_every_checker_message(self):
        mutations = [lambda p: p["held_out"][0].update(query="two words"), lambda p: p["held_out"][0].update(expected_top1_any=["nope:GET:/x"]),
                     lambda p: p["held_out"][0].update(query="get issue"), lambda p: p["held_out"][1].update(query="publish a create page now"),
                     lambda p: p["negative"][6].update(query="delete issue"), lambda p: p["held_out"][1].update(query="get issue by key"),
                     lambda p: p["held_out"][0].update(origin="held_out-r2"), lambda p: p["negative"][0].update(expected_top1_any=[A]),
                     lambda p: p["held_out"].__setitem__(3, rec3(4, "get my ticket now", A)), lambda p: p["negative"][4].update(query="show the document tree")]
        for mutate in mutations:
            p = valid_plain_r3(); mutate(p)
            msgs = self.check(p); self.assertTrue(msgs)
            for m in msgs:
                self.assertIn(rs.rule_id(m), rs.HIDDEN_RULES_R3, m)
        self.assertEqual(rs.HIDDEN_RULES_R3, ("schema", "catalog", "words", "ascii", "actionable", "negative-method", "operationId", "summary/tags",
                                              "negative-phrase", "reuse", "distribution", "negative-distribution"))
        p = valid_plain_r3(); p["held_out"][0]["query"] = "show me the tïcket details"                                      # non-ASCII letter
        self.assertEqual([rs.rule_id(m) for m in self.check(p)], ["ascii"])
        p = valid_plain_r3(); p["held_out"][0]["query"] = "show me the ticket's details"                                     # apostrophe allowed
        self.assertEqual(self.check(p), [])


class TestReplacementStateMachine(unittest.TestCase):
    def test_record_lines_by_priority_then_sections_in_frozen_order(self):
        p = valid_plain_r3()
        v = ["h-002: query has 2 words (must be 3-7)", "h-002: copies consecutive tokens 'create page' from expected op summary (summary/tags rule)",
             "held_out: method DELETE=1 (need >= 2)", "negative: negative-distribution: 5 actionable / 3 abstained (need 4/4)", "n-003: negative-method: forbidden methods ['GET'] outside intent ['POST']"]
        self.assertEqual(rs.record_rejections(v), ["record h-002 rejected: words", "record n-003 rejected: negative-method"])     # words beats summary/tags
        self.assertEqual(rs.section_rejections(v), ["distribution", "negative-distribution"])
        self.assertEqual(rs.next_request(v, p, {})[0], "records")
        only_sections = v[2:4]
        kind, section, text = rs.next_request(only_sections, p, {})
        self.assertEqual((kind, section), ("section", "held_out")); self.assertEqual(text.split("\n"), ["distribution rejected"] + [r["id"] for r in p["held_out"]])
        kind, section, text = rs.next_request(only_sections[1:], p, {"negative_section_replacements": 0})
        self.assertEqual((kind, section), ("section", "negative")); self.assertEqual(text.split("\n"), ["negative distribution rejected"] + [r["id"] for r in p["negative"]])
        self.assertEqual(rs.next_request(only_sections[1:], p, {"negative_section_replacements": 1})[0], "invalid")           # second section replacement forbidden
        self.assertEqual(rs.next_request([], p, {}), ("ok", None))

    def test_render_generation_input_is_deterministic_and_pins_the_inventory(self):
        tpl = "RULES\nVERB_METHODS:\n<verb methods json>\nCATALOG:\n<generator catalog lines>\n"
        gen = rs.generator_view(CAT)
        a, b = rs.render_generation_input(tpl, gen, VERBS), rs.render_generation_input(tpl, gen, VERBS)
        self.assertEqual(a, b)
        block = a.split("VERB_METHODS:\n")[1].split("\nCATALOG:")[0]
        self.assertEqual(json.loads(block), VERBS); self.assertEqual(rs.canonical_sha256(json.loads(block)), rs.canonical_sha256(VERBS))
        self.assertIn(f"{CAT[0]['key']}\t{CAT[0]['source']}\t{CAT[0]['method']}\t{CAT[0]['summary']}\tIssues", a)
        with self.assertRaises(ValueError):
            rs.render_generation_input("no placeholders", gen, VERBS)

    def test_annotate_for_review_adds_machine_fields(self):
        ann = rs.annotate_for_review(valid_plain_r3(), VERBS)
        h1, n5 = ann["held_out"][0], ann["negative"][4]
        self.assertEqual(h1["machine"], {"matched_verbs": ["show"], "intent_methods": ["GET"], "machine_actionable": True})
        self.assertEqual(n5["machine"], {"matched_verbs": [], "intent_methods": [], "machine_actionable": False})
        self.assertEqual({k: v for k, v in h1.items() if k != "machine"}, valid_plain_r3()["held_out"][0])          # records untouched
        self.assertEqual(sum(r["machine"]["machine_actionable"] for r in ann["negative"]), 4)

    def test_needle_manifest_and_scan(self):
        import tempfile, pathlib, json
        queries = ["show me the ticket details", "Delete the ticket status field"]
        m = rs.needle_manifest(queries)
        self.assertEqual([e["words"] for e in m], [5, 5]); self.assertTrue(all(len(e["sha256"]) == 64 for e in m))
        self.assertNotIn("ticket", json.dumps(m))                                                           # no plaintext in the manifest
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); (root / "a.txt").write_text("notes: Show   me the\nticket details!", encoding="utf-8")     # whitespace / case variant
            (root / "b.json").write_text(json.dumps({"q": "delete the ticket status field"}), encoding="utf-8")
            (root / "c.md").write_text("ticket details are shown here", encoding="utf-8")                   # partial: no hit
            (root / "esc.json").write_text('{"q": "Delete the\\\\nticket status \\\\u0066ield"}', encoding="utf-8")       # escaped newline + \\u0066 ('f'): still a hit
            self.assertEqual(m[0]["sha256"], __import__("hashlib").sha256(b"show me the ticket details").hexdigest())   # spec byte contract
            (root / "allowed.json").write_text(json.dumps({"q": "show me the ticket details"}), encoding="utf-8")
            hits = rs.scan_for_needles([root], m)
            self.assertEqual(sorted(pathlib.Path(h).name for h in hits), ["a.txt", "allowed.json", "b.json", "esc.json"])
            self.assertEqual(sorted(pathlib.Path(h).name for h in rs.scan_for_needles([root], m, allow=[root / "allowed.json"])), ["a.txt", "b.json", "esc.json"])
            # I3 (H' final-review fix): an --allow entry naming a DIRECTORY allows every needle-containing file under it.
            sub = root / "allowed_dir"; sub.mkdir()
            (sub / "inside.json").write_text(json.dumps({"q": "show me the ticket details"}), encoding="utf-8")
            hits_dir_allowed = sorted(pathlib.Path(h).name for h in rs.scan_for_needles([root], m, allow=[sub]))
            self.assertNotIn("inside.json", hits_dir_allowed)                                                # inside the allowed directory: not reported
            self.assertIn("a.txt", hits_dir_allowed)                                                          # outside it: still reported
            hits_dir_not_allowed = sorted(pathlib.Path(h).name for h in rs.scan_for_needles([root], m))
            self.assertIn("inside.json", hits_dir_not_allowed)                                                # with no allow at all: reported
            mp = root / "m.json"; mp.write_text(json.dumps(m), encoding="utf-8"); good = rs.ev.file_sha256(mp)
            from unittest import mock
            with mock.patch("builtins.print"):
                self.assertEqual(rs.main(["scan", "--manifest", str(mp), "--root", str(root), "--expect-sha256", good]), 1)             # hits present
                mp.write_text(json.dumps(rs.needle_manifest(["nothing"])), encoding="utf-8")                                      # tampered manifest
                self.assertEqual(rs.main(["scan", "--manifest", str(mp), "--root", str(root), "--expect-sha256", good]), 2)             # refused
            self.assertEqual(rs.scan_for_needles([root], rs.needle_manifest(["totally absent phrase here"])), [])

    def test_seal_verifies_manifest_against_sealed_queries(self):
        """spec §5 v1.22: round >= 3 seal binds needle_manifest_sha256 only when the manifest equals needle_manifest(sealed queries)."""
        import tempfile, pathlib, json
        from unittest import mock
        plain = valid_plain_r3(); queries = [r["query"] for r in plain["held_out"] + plain["negative"]]
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); pl = root / "plain.json"; pl.write_text(json.dumps(plain), encoding="utf-8")
            bench = {"version": 2, "seed": BENCH["seed"], "regression_negative": [], "held_out": [], "negative": []}
            good, bad = root / "good.json", root / "bad.json"
            good.write_text(json.dumps(rs.needle_manifest(queries)), encoding="utf-8"); bad.write_text(json.dumps(rs.needle_manifest(queries[:-1] + ["something else entirely"])), encoding="utf-8")
            def run(manifest):
                b = root / "bench.json"; b.write_text(json.dumps(bench), encoding="utf-8")
                argv = ["seal", "--round", "3", "--plain", str(pl), "--bench", str(b), "--cache-dir", "x"] + (["--needle-manifest", str(manifest)] if manifest else [])
                with mock.patch.object(rs, "load_catalogs_from_cache", lambda cache_dir, round=1: ([], CAT, "f" * 64, {})), mock.patch.object(rs, "verify_freeze", lambda r, c: []), \
                     mock.patch.object(rs.ev, "freeze_for", lambda r: {"round": 3}), mock.patch.object(rs, "RANKING_PATH", root / "ranking.json"), mock.patch("builtins.print") as mock_print:
                    (root / "ranking.json").write_text(json.dumps({"verb_methods": VERBS}), encoding="utf-8")
                    code = rs.main(argv)
                printed = [c.args[0] for c in mock_print.call_args_list]
                return code, json.loads(b.read_text(encoding="utf-8")), printed
            code, out, printed = run(good); self.assertEqual(code, 0); self.assertEqual(out["round3_seal"]["needle_manifest_sha256"], rs.ev.file_sha256(good))
            # Minor fix (H' final-review): a successful round >= 3 seal prints the negative actionable/abstained split.
            actionable, abstained = rs.negative_distribution(plain["negative"], VERBS)
            self.assertIn(f"negative_actionable_split: {actionable}/{abstained}", printed)
            self.assertEqual(run(bad)[0], 1)                                                              # wrong queries -> refused
            self.assertEqual(run(None)[0], 1)                                                             # missing manifest -> refused

    def test_verify_reference_ciphertext(self):
        import tempfile, pathlib
        from unittest import mock
        from tests.benchmarks import evaluator as ev
        with tempfile.TemporaryDirectory() as td:
            enc = pathlib.Path(td) / "round2-sealed.json.enc"; enc.write_bytes(b"ciphertext")
            entry = {"round": 3, "reference_set": {"enc_sha256": ev.file_sha256(enc)}}
            with mock.patch.object(rs.ev, "freeze_for", lambda r: entry):
                self.assertEqual(rs.verify_reference_ciphertext(enc, 3), [])
                enc.write_bytes(b"tampered")
                self.assertEqual(len(rs.verify_reference_ciphertext(enc, 3)), 1)


class TestRound3FreezeEntry(unittest.TestCase):
    def test_round3_entry_has_the_canonical_key_set(self):
        import tempfile, pathlib
        from unittest import mock
        from tests.benchmarks import evaluator as ev
        shas = {"jira-platform": "a" * 64, "jira-software": "b" * 64, "confluence": "c" * 64}
        hashes = {k: "0" * 64 for k in ("concept_lexicon_sha256", "lexicon_aliases_sha256", "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256",
                                         "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T", "regression_reference_sha256", "tuning_grid_sha256")}
        # NOTE (task-6 concern): brief's indentation closes the TemporaryDirectory before the `ev.file_sha256(enc)`
        # assertion below, which would raise FileNotFoundError; widened to keep `enc` alive through the read. See
        # task-6-report.md for the computation.
        with tempfile.TemporaryDirectory() as td:
            enc = pathlib.Path(td) / "round2-sealed.json.enc"; enc.write_bytes(b"ciphertext")
            with mock.patch.object(rs, "load_catalogs_from_cache", lambda cache_dir, round=1: ([], CAT, "f" * 64, dict(shas))), \
                 mock.patch.object(rs.ev, "round_freeze_hashes", lambda r: dict(hashes)):
                e = rs.freeze_entry(3, "x", reference_enc=enc)
            self.assertEqual(set(e), ev.freeze_key_set(3)); self.assertNotIn("commit_T", e)
            self.assertEqual(e["reference_set"]["origin"], "round2"); self.assertEqual(e["reference_set"]["enc_sha256"], ev.file_sha256(enc))
        b = json.loads(rs.BENCH_PATH.read_text(encoding="utf-8"))["round2_seal"]
        self.assertEqual((e["reference_set"]["held_out_sha256"], e["reference_set"]["negative_sha256"]), (b["held_out_sha256"], b["negative_sha256"]))
        self.assertEqual(e["hidden_generation_rules"], list(rs.HIDDEN_RULES_R3)); self.assertEqual(e["hidden_set_origin"], "round3")
        with self.assertRaises(SystemExit):
            with mock.patch.object(rs, "load_catalogs_from_cache", lambda cache_dir, round=1: ([], CAT, "f" * 64, dict(shas))), \
                 mock.patch.object(rs.ev, "round_freeze_hashes", lambda r: dict(hashes)):
                rs.freeze_entry(3, "x")                                                               # round >= 3 needs --reference-enc


# ---------------------------------------------------------------- Round 4 spec §9.1 / §9.5: freeze guard, recovery verifier
ALIASES_REL = "tools/atlassian_docs/intelligence/data/search_aliases.json"
CANON = "python -m unittest discover -s tests -t ."


def _mk_recovery_repo(root, tamper=None):
    """H -> T -> X -> R (rollback) -> A (attestation) with real shas; `tamper` breaks exactly one contract (spec §9.5)."""
    root = pathlib.Path(root); run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout.strip()
    run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
    w = lambda rel, obj: ((root / rel).parent.mkdir(parents=True, exist_ok=True), (root / rel).write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8"))
    sha = lambda c, rel: hashlib.sha256(subprocess.run(["git", "-C", str(root), "show", f"{c}:{rel}"], check=True, capture_output=True).stdout).hexdigest()
    good = {"version": 1, "aliases": {"ticket": ["issue"]}, "rules": [], "notes": {"ticket": {"origin": "seed"}}}
    w(ALIASES_REL, good); w("tests/benchmarks/round_outcomes.json", [{"round": 3, "outcome": "pre-T not reached"}]); w("tests/benchmarks/round_recoveries.json", [])
    (root / "docs").mkdir(); (root / "docs/phase3-readiness.md").write_text("# readiness\n", encoding="utf-8")
    run("add", "-A"); run("commit", "-q", "-m", "H"); H = run("rev-parse", "HEAD")
    bad = {**good, "aliases": {**good["aliases"], "release": ["version"]}, "notes": {**good["notes"], "release": {"origin": "lexicon-r4"}}}
    w(ALIASES_REL, bad)
    w("tests/benchmarks/round_freeze.json", [{"round": 1}, {"round": 2}, {"round": 4, "t_policy_files": [ALIASES_REL],
                                              "round_outcomes_sha256": ev.file_sha256(root / "tests/benchmarks/round_outcomes.json"),
                                              "round_recoveries_sha256": ev.file_sha256(root / "tests/benchmarks/round_recoveries.json")}])
    run("add", "-A"); run("commit", "-q", "-m", "T"); T = run("rev-parse", "HEAD")
    w("tests/benchmarks/round_outcomes.json", [{"round": 3, "outcome": "pre-T not reached"},
                                               {"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": True, "reject_reason": "t", "t_commit": T}])
    (root / "docs/phase3-readiness.md").write_text(f"# readiness\n\n## Search Quality Round 4 — aborted before B\nhousekeeping_commit: {H}\n", encoding="utf-8")
    run("add", "-A"); run("commit", "-q", "-m", "X"); X = run("rev-parse", "HEAD")
    w(ALIASES_REL, {**good, "aliases": {"ticket": ["issue"], "zz": ["issue"]}} if tamper == "r_not_hk_bytes" else good)
    run("add", "-A"); run("commit", "-q", "-m", "R"); R = run("rev-parse", "HEAD")
    rec = {"round": 4, "t_commit": T, "xpreb_terminal_commit": X, "recovery_commit": R, "recovery_mode": "rollback", "reviewed_base": X, "reviewed_head": R,
           "reviewed_by": "test-reviewer", "review_findings": 0, "review_output_sha256": "00" * 32, "suite_commit": R, "suite_command": CANON,
           "suite_exit_code": 0, "suite_output_sha256": "11" * 32,
           "files": [{"path": ALIASES_REL, "before_sha256": sha(T, ALIASES_REL), "after_sha256": sha(R, ALIASES_REL), "known_good_sha256": sha(H, ALIASES_REL)}],
           "removed_aliases": ["release"]}
    if tamper == "before_sha_wrong": rec["files"][0]["before_sha256"] = "ab" * 32
    if tamper == "removed_aliases_wrong": rec["removed_aliases"] = []
    if tamper == "evidence_missing": del rec["review_output_sha256"]
    if tamper == "bad_suite_command": rec["suite_command"] = "pytest"
    w("tests/benchmarks/round_recoveries.json", [rec]); run("add", "-A"); run("commit", "-q", "-m", "A"); A = run("rev-parse", "HEAD")
    if tamper == "attestation_edited_after_A":
        rec["reviewed_by"] = "someone-else"; w("tests/benchmarks/round_recoveries.json", [rec]); run("add", "-A"); run("commit", "-q", "-m", "edit")
    if tamper == "edited_after_A":
        w("tests/benchmarks/round_recoveries.json", [{**rec, "review_findings": 0, "reviewed_by": "rewritten"}]); run("add", "-A"); run("commit", "-q", "-m", "rewrite")
    (root / "scratch.txt").write_text("x"); run("add", "-A"); run("commit", "-q", "-m", "bad-r-candidate"); bad_r = run("rev-parse", "HEAD")
    return {"path": root, "H": H, "T": T, "X": X, "R": R, "A": A, "bad_r": bad_r}


class TestFreezeGuardAndRecovery(unittest.TestCase):
    F = [{"round": 1}, {"round": 2}]; O3 = [{"round": 3, "outcome": "pre-T not reached"}]

    def test_freeze_guard_round4_needs_closed_round3(self):
        with mock.patch.dict(ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256, {3: "a", 4: "b"}, clear=True):
            self.assertEqual(rs.freeze_guard_problems(4, self.F, self.O3, repo=None), [])
            self.assertIn("pending_round", rs.freeze_guard_problems(4, self.F, [], repo=None)[0])
            self.assertIn("pending_round", rs.freeze_guard_problems(5, self.F, self.O3, repo=None)[0])

    def test_freeze_guard_requires_recovery_attestation(self):
        f = self.F + [{"round": 4, "t_policy_files": [ALIASES_REL]}]
        ab = lambda inv: self.O3 + [{"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB", "invalidates_policy": inv}]
        with mock.patch.dict(ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256, {3: "a", 4: "b", 5: "c"}, clear=True):
            self.assertEqual(rs.freeze_guard_problems(5, f, ab(False), repo=None), [])
            with mock.patch.object(ev, "load_round_recoveries", return_value=[]):
                self.assertIn("recovery", rs.freeze_guard_problems(5, f, ab(True), repo=None)[0])

    def test_verify_recovery_exact_chain(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_recovery_repo(pathlib.Path(td))
            self.assertEqual(rs.verify_recovery(4, repo["path"]), [])
            self.assertTrue(any("parent(R)" in p for p in rs.verify_recovery(4, repo["path"], r_commit=repo["bad_r"])))

    def test_verify_recovery_tamper_cases(self):
        for tamper, needle in (("r_not_hk_bytes", "sha(HK:path)"), ("attestation_edited_after_A", "append-only"), ("before_sha_wrong", "sha(git show T:path)"),
                               ("removed_aliases_wrong", "removed_aliases"), ("evidence_missing", "review_output_sha256"), ("bad_suite_command", "suite_command"),
                               ("edited_after_A", "append-only")):
            with tempfile.TemporaryDirectory() as td:
                repo = _mk_recovery_repo(pathlib.Path(td), tamper=tamper)
                self.assertTrue(any(needle in p for p in rs.verify_recovery(4, repo["path"])), tamper)

    def test_verify_recovery_allows_later_round_appends(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_recovery_repo(pathlib.Path(td)); path = repo["path"] / "tests/benchmarks/round_recoveries.json"
            cur = json.loads(path.read_text()); path.write_text(json.dumps(cur + [{**cur[0], "round": 5}], indent=1) + "\n")
            subprocess.run(["git", "-C", str(repo["path"]), "commit", "-qam", "A5"], check=True)
            self.assertEqual(rs.verify_recovery(4, repo["path"]), [])

    def test_round_start_guard_refuses_head_not_descendant_of_A(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_recovery_repo(pathlib.Path(td))
            with mock.patch.object(ev, "load_round_freeze", return_value=json.loads(subprocess.run(["git", "-C", str(repo["path"]), "show", "HEAD:tests/benchmarks/round_freeze.json"], capture_output=True, text=True).stdout)), \
                 mock.patch.object(ev, "load_round_outcomes", return_value=json.loads((repo["path"] / "tests/benchmarks/round_outcomes.json").read_text())), \
                 mock.patch.object(ev, "load_round_recoveries", return_value=json.loads((repo["path"] / "tests/benchmarks/round_recoveries.json").read_text())), \
                 mock.patch.dict(ev.PRE_FREEZE_NONVERB_STRUCTURE_SHA256, {3: "a", 4: "b", 5: "c"}, clear=True):
                self.assertEqual(rs.round_start_guard_problems(5, repo["path"]), [])
                subprocess.run(["git", "-C", str(repo["path"]), "checkout", "-q", "-b", "side", repo["X"]], check=True)
                self.assertTrue(any("descendant" in p for p in rs.round_start_guard_problems(5, repo["path"])))


class TestCleanupNeedles(unittest.TestCase):
    """Round 4 spec §9.4: hash-only cleanup needles over every hidden-attempt artifact; deletion guard; canonical authority union."""
    def test_json_query_fields_exact_and_nonjson_windows(self):
        with tempfile.TemporaryDirectory() as td:
            j = pathlib.Path(td, "a.json"); j.write_text(json.dumps({"held_out": [{"query": "show my starred searches"}], "x": {"query": "list open bugs now"}}))
            m = rs.cleanup_needle_manifest_from_artifacts([j])
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("show my starred searches")}, m)
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("list open bugs now")}, m)

    def test_cleanup_needles_span_line_breaks(self):
        with tempfile.TemporaryDirectory() as td:
            raw = pathlib.Path(td, "attempt.txt"); raw.write_text("candidate answer is: show my starred\nsearches because ...\n")
            m = rs.cleanup_needle_manifest_from_artifacts([raw])
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("show my starred searches")}, m)
            leak = pathlib.Path(td, "leak.md"); leak.write_text("note: show my starred searches\n")
            self.assertEqual(rs.scan_for_needles([td], m, allow=[raw]), [str(leak)])

    def test_attempt_ledger_union_equals_recomputation(self):
        with tempfile.TemporaryDirectory() as td:
            a = pathlib.Path(td, "a.txt"); a.write_text("alpha beta gamma delta\n"); b = pathlib.Path(td, "b.json"); b.write_text('{"query": "one two three"}')
            led = pathlib.Path(td, "hidden_attempt_needles.jsonl")
            rs.append_attempt_needles(led, [a]); rs.append_attempt_needles(led, [b])
            self.assertEqual(sorted(map(json.dumps, rs.cleanup_authority(led, None, []))), sorted(map(json.dumps, rs.cleanup_needle_manifest_from_artifacts([a, b]))))
            std = pathlib.Path(td, "std.json"); std.write_text(json.dumps(rs.needle_manifest(["final set query here"])))
            self.assertIn({"words": 4, "sha256": rs._ngram_sha256("final set query here")}, rs.cleanup_authority(led, std, [a]))

    def test_delete_guard_requires_sha_and_needle_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            a = pathlib.Path(td, "a.txt"); a.write_text("alpha beta gamma\n"); led = pathlib.Path(td, "l.jsonl")
            self.assertFalse(rs.artifact_is_ledgered(led, a)); rs.append_attempt_needles(led, [a]); self.assertTrue(rs.artifact_is_ledgered(led, a))
            rows = [json.loads(l) for l in led.read_text().splitlines()]; rows[0]["needles"] = rows[0]["needles"][:-1]       # a row that under-covers its artifact
            led.write_text("".join(json.dumps(r) + "\n" for r in rows)); self.assertFalse(rs.artifact_is_ledgered(led, a))


class TestUnchangedSinceAllow(unittest.TestCase):
    def test_unchanged_files_are_allowed_and_new_files_are_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td).resolve(); run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)
            run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
            (repo / "old.md").write_text("candidate answer is here\n"); run("add", "-A"); run("commit", "-q", "-m", "T")
            T = run("rev-parse", "HEAD").stdout.strip()
            (repo / "new.md").write_text("candidate answer is leaked\n"); (repo / "old2.md").write_text("x\n"); run("add", "old2.md"); run("commit", "-q", "-m", "later")
            m = rs.cleanup_needle_manifest_from_artifacts([repo / "new.md"])
            allow = rs.t_baseline_identical_files(repo, T) + [str(repo / ".git")]
            self.assertIn(str(repo / "old.md"), allow)
            self.assertEqual(rs.scan_for_needles([str(repo)], m, allow=allow + [str(repo / "new.md")]), [])        # old.md shares the 3-gram but predates T
            self.assertEqual(rs.scan_for_needles([str(repo)], m, allow=allow), [str(repo / "new.md")])             # a post-T untracked file with the same 3-gram is a hit
            (repo / "tracked-new.md").write_text("candidate answer is tracked\n"); run("add", "tracked-new.md"); run("commit", "-q", "-m", "new tracked")
            (repo / ".gitignore").write_text("ignored.md\n"); (repo / "ignored.md").write_text("candidate answer is ignored\n")
            (repo / "old.md").write_text("candidate answer is here!\n")                                             # 1-byte change to a T path
            allow = rs.t_baseline_identical_files(repo, T) + [str(repo / ".git")]
            hits = rs.scan_for_needles([str(repo)], m, allow=allow)
            for leaked in ("new.md", "tracked-new.md", "ignored.md", "old.md"):
                self.assertIn(str(repo / leaked), hits, leaked)
