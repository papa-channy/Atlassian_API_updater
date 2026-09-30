import unittest
from tests import tune_search_ranking as tune

GRID = {"method_match_bonus": [1.0, 2.0, 3.0], "method_mismatch_penalty": [0.0, 1.0, 2.0, 3.0], "path_unmatched_penalty": [0.5, 1.0, 1.5, 2.0],
        "path_unmatched_cap": [2, 3, 4], "product_hint_bonus": [2.0, 3.0, 4.0],
        "resource_match_bonus": [6.0, 8.0, 10.0, 12.0]}
BASE = {"method_match_bonus": 2.0, "method_mismatch_penalty": 2.0, "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0, "resource_match_bonus": 10.0}
S, R = tune.SEED_TOTAL, tune.REGRESSION_TOTAL   # 23 seed, 6 regression_negative


def pt(**over):
    return {**BASE, **over}


class TestSelector(unittest.TestCase):
    def test_totals_match_benchmark(self):
        self.assertEqual((S, R), (23, 6))

    def test_grid_cardinality_and_order(self):
        pts = tune.grid_points(GRID)
        self.assertEqual(len(pts), 1728); self.assertEqual(pts, sorted(pts, key=lambda p: tuple(p[k] for k in tune.CONSTANT_KEYS)))

    def test_l1_index_distance(self):
        self.assertEqual(tune.l1_index_distance(BASE, BASE, GRID), 0)
        self.assertEqual(tune.l1_index_distance(pt(method_mismatch_penalty=0.0, path_unmatched_cap=4), BASE, GRID), 3)

    def test_perfect_beats_non_perfect(self):
        res = [(pt(method_match_bonus=3.0), S, R), (BASE, S - 1, R)]
        self.assertEqual(tune.select_candidate(res, BASE, GRID), pt(method_match_bonus=3.0))

    def test_l1_then_magnitude_then_lexicographic(self):
        near, far = pt(product_hint_bonus=4.0), pt(method_match_bonus=1.0, path_unmatched_cap=4)
        self.assertEqual(tune.select_candidate([(far, S, R), (near, S, R)], BASE, GRID), near)          # L1 1 < 2
        a, b = pt(method_match_bonus=1.0), pt(method_match_bonus=3.0)                                   # both L1 = 1
        self.assertEqual(tune.select_candidate([(b, S, R), (a, S, R)], BASE, GRID), a)                  # smaller magnitude sum
        c, d = pt(method_mismatch_penalty=1.0), pt(path_unmatched_penalty=0.5)                          # L1 1, sums 7.0 vs 7.5
        self.assertEqual(tune.select_candidate([(d, S, R), (c, S, R)], BASE, GRID), c)
        e, f = pt(method_match_bonus=1.0, method_mismatch_penalty=3.0), pt(method_match_bonus=3.0, method_mismatch_penalty=1.0)
        self.assertEqual(tune.select_candidate([(f, S, R), (e, S, R)], BASE, GRID), e)                  # 6-tuple lexicographic
        g, h = pt(resource_match_bonus=8.0), pt(resource_match_bonus=12.0)                              # only the new axis differs, L1 1
        self.assertEqual(tune.select_candidate([(h, S, R), (g, S, R)], BASE, GRID), g)                  # magnitude sum includes it
        x, y = pt(method_match_bonus=1.0, resource_match_bonus=12.0), pt(method_match_bonus=3.0, resource_match_bonus=8.0)
        self.assertEqual(tune.select_candidate([(x, S, R), (y, S, R)], BASE, GRID), y)                  # L1 2 each; sums 19 vs 17 beat lexicographic

    def test_fallback_when_no_perfect(self):
        res = [(pt(product_hint_bonus=4.0), S - 2, R - 1), (BASE, S - 2, R), (pt(method_match_bonus=1.0), S - 3, R)]
        self.assertEqual(tune.select_candidate(res, BASE, GRID), BASE)                                 # seed max, then regression max
