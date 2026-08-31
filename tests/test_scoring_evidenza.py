#!/usr/bin/env python3
"""
Quanto di un punteggio poggia su un dato vero (src/scoring.py).

Idea presa da OuroborosCouncil, _needs_more_signal: "un solo componente
disponibile E già saturo... è segnale vuoto ad alta rumorosità". Lì serve a
non spendere una chiamata AI su un punteggio gonfio; qui la spesa è già
fatta, quindi serve all'altra metà del problema — non far sembrare misura
una costante.

Misurato sulla dashboard del 31 ago 2026 (54 pubblicati): `experience` era
50 su 50 schede, `source` su 41, `league_fit` su 39. Il 40% del punteggio
era una costante su tre quarti del prodotto.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_scoring_evidenza -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring import OB1Scorer


class TestPesoMisurato(unittest.TestCase):
    def setUp(self):
        self.s = OB1Scorer()

    def test_record_nudo_dichiara_quasi_tutto_ignoto(self):
        r = self.s.score({"player_name": "Tizio Caio"})
        self.assertIn("experience", r["score_senza_dato"])
        self.assertIn("market_value", r["score_senza_dato"])
        self.assertLess(r["peso_misurato"], 0.5)

    def test_record_completo_e_tutto_misurato(self):
        r = self.s.score({
            "player_name": "Tizio Caio", "opportunity_type": "svincolato",
            "reported_date": "2026-08-30", "age": 21, "market_value": 200_000,
            "appearances": 40, "current_club": "Cesena",
            "summary": "Difensore centrale, 40 presenze in Serie C.",
            "source_name": "tuttoc",
        })
        self.assertEqual(r["score_senza_dato"], [])
        self.assertEqual(r["peso_misurato"], 1.0)

    def test_il_punteggio_non_cambia(self):
        # il contatore descrive, non tocca il calcolo: è la garanzia che
        # aggiungerlo non sposta nessuna classifica
        opp = {"player_name": "Tizio Caio", "age": 20, "market_value": 150_000}
        prima = self.s.score(opp)["ob1_score"]
        self.assertEqual(self.s.score(opp)["ob1_score"], prima)

    def test_fonte_sconosciuta_conta_come_ignota(self):
        r = self.s.score({"player_name": "Tizio Caio",
                          "source_name": "Gemini Search"})
        self.assertIn("source", r["score_senza_dato"])

    def test_fonte_nota_non_conta_come_ignota(self):
        r = self.s.score({"player_name": "Tizio Caio", "source_name": "tuttoc"})
        self.assertNotIn("source", r["score_senza_dato"])


if __name__ == "__main__":
    unittest.main()
