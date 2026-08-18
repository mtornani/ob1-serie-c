#!/usr/bin/env python3
"""
Test del quality gate (src/quality_gate.py). Non esisteva prima una suite per
questo file, nonostante decida da solo cosa arriva in dashboard pubblica —
aggiunto insieme all'hard-gate su `corroborated` (2026-08-17): prima del
cambio `publishable` bastava `identity_complete`, ora richiede anche una
seconda prova (profilo TM o ≥2 domini). Misurato sui dati reali prima di
attivarlo: 119 → 99 publishable (-17%), non uno svuotamento della dashboard.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_quality_gate -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.quality_gate import assess_identity, normalize_age


def opp(**kw):
    base = {
        "player_name": "Mario Rossi",
        "age": 20,
        "current_club": "Cesena",
        "source_url": "https://tuttoc.it/mario-rossi",
    }
    base.update(kw)
    return base


class TestPublishableHardGate(unittest.TestCase):
    """Da qui in poi: publishable = identity_complete AND corroborated."""

    def test_identity_complete_da_sola_non_basta_piu(self):
        # nome + età + club + fonte, ma una sola fonte e nessun profilo TM
        g = assess_identity(opp())
        self.assertTrue(g["identity_complete"])
        self.assertFalse(g["corroborated"])
        self.assertFalse(g["publishable"], "una sola fonte non deve più bastare")
        self.assertIn("fonte_singola", g["review_flags"])

    def test_due_domini_distinti_corroborano(self):
        g = assess_identity(opp(sources=[
            {"url": "https://tuttoc.it/mario-rossi"},
            {"url": "https://tuttomercatoweb.com/mario-rossi"},
        ]))
        self.assertTrue(g["corroborated"])
        self.assertTrue(g["publishable"])

    def test_profilo_tm_giocatore_basta_da_solo(self):
        g = assess_identity(opp(
            tm_url="https://www.transfermarkt.it/mario-rossi/profil/spieler/123456",
        ))
        self.assertTrue(g["tm_player_profile"])
        self.assertTrue(g["corroborated"])
        self.assertTrue(g["publishable"])

    def test_pagina_transfermarkt_non_profilo_non_conta_come_tm_ok(self):
        # una pagina squadra/lega TM non è un profilo giocatore: non basta
        # da sola (a differenza di un vero profilo, vedi test sopra) — qui
        # resta isolata sullo stesso dominio della fonte base, quindi anche
        # n_sources non arriva a 2
        g = assess_identity(opp(
            source_url="https://www.transfermarkt.it/serie-c-girone-b/startseite/wettbewerb/IC3B",
            tm_url="https://www.transfermarkt.it/serie-c-girone-b/startseite/wettbewerb/IC3B",
        ))
        self.assertFalse(g["tm_player_profile"])
        self.assertEqual(g["n_sources"], 1)
        self.assertFalse(g["corroborated"])
        self.assertFalse(g["publishable"])

    def test_tm_url_non_profilo_ma_domini_distinti_corrobora_comunque(self):
        # comportamento esistente di count_distinct_sources, non toccato da
        # questo gate: un secondo dominio (anche una pagina lega TM) conta
        # come seconda fonte indipendente dal fatto che sia un profilo
        # giocatore o meno — è count_distinct_sources, non tm_ok, a decidere
        g = assess_identity(opp(
            tm_url="https://www.transfermarkt.it/serie-c-girone-b/startseite/wettbewerb/IC3B",
        ))
        self.assertFalse(g["tm_player_profile"])
        self.assertEqual(g["n_sources"], 2)
        self.assertTrue(g["corroborated"])
        self.assertTrue(g["publishable"])

    def test_stesso_dominio_ripetuto_non_corrobora(self):
        # due URL della stessa testata non sono due fonti indipendenti
        g = assess_identity(opp(sources=[
            {"url": "https://tuttoc.it/mario-rossi"},
            {"url": "https://tuttoc.it/mercato/mario-rossi-al-cesena"},
        ]))
        self.assertEqual(g["n_sources"], 1)
        self.assertFalse(g["publishable"])

    def test_identity_incompleta_resta_non_pubblicabile_anche_corroborata(self):
        # due fonti ma età mancante: identity_complete deve bloccare comunque
        g = assess_identity(opp(age=None, sources=[
            {"url": "https://tuttoc.it/mario-rossi"},
            {"url": "https://tuttomercatoweb.com/mario-rossi"},
        ]))
        self.assertTrue(g["corroborated"])
        self.assertFalse(g["identity_complete"])
        self.assertFalse(g["publishable"])


class TestNormalizeAge(unittest.TestCase):
    """Bug noto: anno di nascita finito per sbaglio nel campo age."""

    def test_anno_di_nascita_convertito_in_eta(self):
        self.assertEqual(normalize_age(2006), 2026 - 2006)

    def test_eta_plausibile_passa_diretta(self):
        self.assertEqual(normalize_age(20), 20)

    def test_eta_fuori_range_scartata(self):
        self.assertIsNone(normalize_age(7))
        self.assertIsNone(normalize_age(99))

    def test_birth_date_ha_priorita(self):
        self.assertEqual(normalize_age(99, birth_date="2005-03-01"), 2026 - 2005)


if __name__ == "__main__":
    unittest.main()
