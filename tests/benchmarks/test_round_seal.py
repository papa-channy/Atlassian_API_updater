import json, unittest
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
