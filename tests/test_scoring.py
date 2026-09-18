#!/usr/bin/env python3
"""SCORE-003: pesi, soglie, appearances 0 vs None."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scoring import OB1Scorer, assess_follow


class TestWeights(unittest.TestCase):
    def test_pesi_sommano_1(self):
        s = sum(OB1Scorer.WEIGHTS.values())
        self.assertAlmostEqual(s, 1.0, places=6)

    def test_niente_completeness(self):
        self.assertNotIn("completeness", OB1Scorer.WEIGHTS)


class TestScore(unittest.TestCase):
    def setUp(self):
        self.scorer = OB1Scorer()

    def _score(self, **kwargs):
        opp = {
            "player_name": "Marco Rossi",
            "opportunity_type": "svincolato",
            "reported_date": "2026-09-17",
            "age": 21,
            "appearances": 25,
            "current_club": "Pescara",
            "source_name": "tuttoc",
            "source_url": "https://www.tuttoc.com/x",
        }
        opp.update(kwargs)
        return self.scorer.score(opp)

    def test_u23_age_max(self):
        bd = self._score(age=20)["score_breakdown"]
        self.assertEqual(bd["age"], 100)

    def test_eta_sconosciuta_neutra(self):
        bd = self._score(age=None)["score_breakdown"]
        self.assertEqual(bd["age"], 60)

    def test_svincolato_type_max(self):
        bd = self._score(opportunity_type="svincolato")["score_breakdown"]
        self.assertEqual(bd["opportunity_type"], 100)

    def test_appearances_zero_uguale_none(self):
        a = self._score(appearances=0)["score_breakdown"]["experience"]
        b = self._score(appearances=None)["score_breakdown"]["experience"]
        self.assertEqual(a, b)

    def test_hot_warm_cold(self):
        r = self._score()
        self.assertIn(r["classification"], ("hot", "warm", "cold"))
        if r["ob1_score"] >= 70:
            self.assertEqual(r["classification"], "hot")
        elif r["ob1_score"] >= 57:
            self.assertEqual(r["classification"], "warm")
        else:
            self.assertEqual(r["classification"], "cold")

    def test_assess_follow_svincolato(self):
        scored = self._score()
        a = assess_follow(
            {
                "opportunity_type": "svincolato",
                "age": 21,
                "appearances": 25,
                "current_club": "Pescara",
            },
            scored,
        )
        self.assertTrue(any("zero" in x.lower() for x in a["yes"]))
        self.assertIn("action", a)


if __name__ == "__main__":
    unittest.main()
