#!/usr/bin/env python3
"""
Il grafo delle fonti registra le due bocche PRIMA che una cancelli l'altra
(scripts/run_enrichment.py -> _registra_nel_grafo).

Perché: in `apply_tm_data` c'è `opp[key] = tm[key]`, cioè Transfermarkt
sovrascrive sempre — anche il club, che è un fatto veloce e su cui una
scheda senza data non dovrebbe battere una notizia datata. E per l'età
succede l'opposto: `if not opp.get('age')`, vince il primo arrivato e la
data di nascita che TM porta viene buttata. Due campi, due errori in
direzioni opposte: il sintomo di una piramide letta in un verso solo.

Questi test bloccano il fatto che il disaccordo venga REGISTRATO. Chi vince
non cambia ancora: si misura prima.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_piramide_enrichment -v
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_enrichment import _registra_nel_grafo
from src.piramide import risolvi


class TestGrafoDuranteEnrichment(unittest.TestCase):
    def test_club_conserva_entrambe_le_voci_e_vince_la_notizia_datata(self):
        opp = {"player_name": "Tizio", "current_club": "Virtus Entella",
               "reported_date": "2026-08-28", "source_url": "https://tuttoc.com/x"}
        _registra_nel_grafo(opp, {"current_club": "Cesena FC"})
        r = risolvi(opp["grafo_fonti"], "p", "club")
        self.assertEqual(r["valore"], "Virtus Entella")
        self.assertTrue(r["conflitto"])
        self.assertEqual(r["alternativa"], "Cesena FC")

    def test_eta_da_data_di_nascita_entra_e_vince(self):
        anno = datetime.now().year
        opp = {"player_name": "Tizio", "age": 22, "reported_date": "2026-08-28"}
        _registra_nel_grafo(opp, {"birth_date": f"{anno - 24}-03-15"})
        r = risolvi(opp["grafo_fonti"], "p", "eta")
        self.assertEqual(r["valore"], "24")          # l'anagrafica batte la notizia
        self.assertTrue(r["conflitto"])
        self.assertEqual(r["alternativa"], "22")

    def test_accordo_non_produce_conflitto(self):
        opp = {"player_name": "Tizio", "current_club": "AC Prato",
               "reported_date": "2026-08-28"}
        _registra_nel_grafo(opp, {"current_club": "AC Prato"})
        self.assertFalse(risolvi(opp["grafo_fonti"], "p", "club")["conflitto"])

    def test_record_senza_dati_non_crea_grafo_vuoto(self):
        opp = {"player_name": "Tizio"}
        _registra_nel_grafo(opp, {})
        self.assertNotIn("grafo_fonti", opp)

    def test_data_di_nascita_illeggibile_non_esplode(self):
        opp = {"player_name": "Tizio", "age": 20}
        _registra_nel_grafo(opp, {"birth_date": "chissà"})
        self.assertEqual(risolvi(opp["grafo_fonti"], "p", "eta")["valore"], "20")

    def test_il_grafo_si_accumula_fra_due_giri(self):
        opp = {"player_name": "Tizio", "current_club": "AC Prato",
               "reported_date": "2026-08-28"}
        _registra_nel_grafo(opp, {"current_club": "AC Prato"})
        opp["current_club"] = "US Triestina"      # la discovery cambia idea
        _registra_nel_grafo(opp, {"current_club": "AC Prato"})
        voci = opp["grafo_fonti"]["p"]["club"]
        self.assertEqual(len(voci), 3)   # 2 news (il cambio è il dato) + 1 TM


if __name__ == "__main__":
    unittest.main()
