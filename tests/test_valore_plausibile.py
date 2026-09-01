#!/usr/bin/env python3
"""
Un frammento di schema non è un dato (scripts/run_enrichment.py).

Caso vero, trovato dal vivo il 31 ago 2026 — la prima run dopo il grafo
delle fonti, quella che ha reso il difetto visibile per la prima volta:

    Daniele Cagnazzo -> current_club: ", competizione ecc."

Nessuna occorrenza di quella frase nei nostri prompt (verificato con grep su
src/ e scripts/): non è un template che perde nel testo che mandiamo al
modello, è un'invenzione del modello (Mistral, via free_stack) quando non
sapeva la risposta vera e ha risposto descrivendo lo schema invece di
compilarlo. Prima di questo fix finiva dritto in `current_club` e ci
restava: un fatto falso indistinguibile da uno vero.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_valore_plausibile -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_enrichment import (_valore_di_testo_plausibile, apply_tm_data,
                                    _CAMPI_TESTO_LIBERO)


class TestValoreDiTestoPlausibile(unittest.TestCase):
    def test_il_caso_vero_viene_scartato(self):
        self.assertFalse(_valore_di_testo_plausibile(", competizione ecc."))

    def test_club_vero_passa(self):
        self.assertTrue(_valore_di_testo_plausibile("Virtus Entella"))

    def test_club_che_comincia_con_un_numero_passa(self):
        # ci sono club veri con un anno nel nome — il primo carattere numerico
        # non è di per sé un segnale, a differenza della punteggiatura
        self.assertTrue(_valore_di_testo_plausibile("1913 Seregno"))

    def test_parole_meta_scartate(self):
        for v in ("ecc", "eccetera.", "Esempio", "N/A", "placeholder", "TBD"):
            self.assertFalse(_valore_di_testo_plausibile(v), v)

    def test_comincia_con_punteggiatura_scartato(self):
        for v in (", qualcosa", "; altro", "- lista", ") chiuso"):
            self.assertFalse(_valore_di_testo_plausibile(v), v)

    def test_valori_non_testuali_passano_indisturbati(self):
        # il controllo è SOLO per il testo libero: un numero o un None non
        # sono il problema che questa funzione risolve
        self.assertTrue(_valore_di_testo_plausibile(150000))
        self.assertTrue(_valore_di_testo_plausibile(None))

    def test_stringa_vuota_passa_la_gestisce_chi_chiama(self):
        self.assertTrue(_valore_di_testo_plausibile(""))
        self.assertTrue(_valore_di_testo_plausibile("   "))


class TestApplyTmDataScartaImplausibile(unittest.TestCase):
    """End-to-end: il valore scartato non deve arrivare né al record né al
    grafo delle fonti — deve fermarsi PRIMA di entrambi."""

    def test_current_club_implausibile_non_scrive_nulla(self):
        opp = {"player_name": "Daniele Cagnazzo", "reported_date": "2026-08-31"}
        tm = {"current_club": ", competizione ecc.", "nationality": "Italia"}
        apply_tm_data(opp, tm)
        self.assertIsNone(opp.get("current_club"))
        self.assertEqual(opp.get("nationality"), "Italia")   # il resto passa
        grafo = opp.get("grafo_fonti") or {}
        campi_nel_grafo = (grafo.get("p") or {}).keys()
        self.assertNotIn("club", campi_nel_grafo)

    def test_current_club_plausibile_passa(self):
        opp = {"player_name": "Tizio", "reported_date": "2026-08-31"}
        apply_tm_data(opp, {"current_club": "AC Prato"})
        self.assertEqual(opp["current_club"], "AC Prato")

    def test_ogni_campo_in_testo_libero_e_coperto(self):
        # tutti i campi che questo file dichiara "a rischio" devono davvero
        # passare dal controllo — non solo current_club
        for campo in _CAMPI_TESTO_LIBERO:
            opp = {"player_name": "Tizio"}
            apply_tm_data(opp, {campo: ", competizione ecc."})
            self.assertIsNone(opp.get(campo), campo)


if __name__ == "__main__":
    unittest.main()
