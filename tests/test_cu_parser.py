#!/usr/bin/env python3
"""
Test offline del parser dei Comunicati Ufficiali LND (ARCH-003).

Le fixture NON sono un formato ideale: sono righe copiate dal CU 146 del CRER
(13/04/2026), spazi interni nelle date e artefatti di impaginazione compresi.
Un parser che passa su un formato pulito e cade su quello vero non serve.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_cu_parser -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cu_parser import CUStore, parse_cu_text

# Blocco reale (CU 146 CRER, Fasi Finali Under 19 Élite), verbatim.
CU_REALE = """COMUNICATO UFFICIALE N. 146 DEL 13/4/2026

FASI FINALI UNDER 19 ELITE

GARE DEL 11/ 4/2026

PROVVEDIMENTI DISCIPLINARI
In base alle risultanze degli atti ufficiali sono state deliberate le seguenti sanzioni disciplinari.

DIRIGENTI
I AMMONIZIONE DIFFIDA
VIGHI ALESSIO (NOCETO)    VIGHI MATTEO (NOCETO)
GIRONE A - 12 Giornata - R
SORAGNA 1921 - PONTENURESE - D

GIRONE X - 1 Giornata - A
CASTENASO CALCIO - NOCETO 5 - 6 dcr
FIORENZUOLA 1922 SSD ARL - REAL FORMIGINE 3 - 1
TERRE DI CASTELLI 1907 - SAVIGNANESE 4 - 3  dcr

 5036 5036

ALLENATORI
SQUALIFICA FINO AL 18/ 5/2026
RANIERI RICCARDO (NOCETO)
Per gravi proteste nei confronti dell'Arbitro Per aver rivolto gravi proteste e frasi offensive nei confronti
dell'arbitro.

I AMMONIZIONE DIFFIDA
CANOVA GIANMARCO (CASTENASO CALCIO)

CALCIATORI ESPULSI
SQUALIFICA PER DUE GARE EFFETTIVE
PELLEGRI FILIPPO (VIANESE CALCIO SSDARL)

I AMMONIZIONE DIFFIDA
BARATTINI LORENZO (CASTENASO CALCIO)    DASCIA TOMMASO (CASTENASO CALCIO)
SPADONI LUCA (MEDICINA FOSSATONE S.S.D.)    ALINOVI SEBASTIANO (NOCETO)
"""


def _sanction(parsed, person):
    return next(s for s in parsed["sanctions"] if s["person"] == person)


class ParseMetaTestCase(unittest.TestCase):
    def test_numero_e_data_del_comunicato(self):
        meta = parse_cu_text(CU_REALE)["meta"]
        self.assertEqual(meta["cu_number"], 146)
        self.assertEqual(meta["cu_date"], "2026-04-13")

    def test_data_gare_con_spazi_interni(self):
        """'GARE DEL 11/ 4/2026' -> 2026-04-11. Lo spazio c'e' nel PDF vero."""
        s = _sanction(parse_cu_text(CU_REALE), "VIGHI ALESSIO")
        self.assertEqual(s["match_date"], "2026-04-11")

    def test_testo_vuoto_non_esplode(self):
        parsed = parse_cu_text("")
        self.assertIsNone(parsed["meta"]["cu_number"])
        self.assertEqual(parsed["results"], [])
        self.assertEqual(parsed["sanctions"], [])


class ParseResultsTestCase(unittest.TestCase):
    def setUp(self):
        self.results = parse_cu_text(CU_REALE)["results"]

    def test_estrae_solo_le_righe_con_punteggio(self):
        """'SORAGNA 1921 - PONTENURESE - D' non ha punteggio: non e' un risultato."""
        self.assertEqual(len(self.results), 3)
        self.assertNotIn("SORAGNA 1921", [r["home"] for r in self.results])

    def test_punteggio_girone_e_giornata(self):
        r = self.results[0]
        self.assertEqual((r["home"], r["away"]), ("CASTENASO CALCIO", "NOCETO"))
        self.assertEqual((r["home_goals"], r["away_goals"]), (5, 6))
        self.assertEqual(r["note"], "dcr")
        self.assertEqual((r["girone"], r["giornata"]), ("X", 1))

    def test_nomi_societa_con_numeri_non_finiscono_nel_punteggio(self):
        r = self.results[1]
        self.assertEqual(r["home"], "FIORENZUOLA 1922 SSD ARL")
        self.assertEqual((r["home_goals"], r["away_goals"]), (3, 1))


class ParseSanctionsTestCase(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_cu_text(CU_REALE)

    def test_due_tesserati_sulla_stessa_riga(self):
        noceto = [s for s in self.parsed["sanctions"]
                  if s["person"].startswith("VIGHI")]
        self.assertEqual({s["person"] for s in noceto},
                         {"VIGHI ALESSIO", "VIGHI MATTEO"})
        self.assertTrue(all(s["club"] == "NOCETO" for s in noceto))

    def test_squalifica_a_termine_porta_la_data_di_fine(self):
        s = _sanction(self.parsed, "RANIERI RICCARDO")
        self.assertEqual(s["kind"], "SQUALIFICA_FINO_AL")
        self.assertEqual(s["detail"], "2026-05-18")
        self.assertEqual(s["role"], "ALLENATORI")

    def test_squalifica_a_giornate(self):
        s = _sanction(self.parsed, "PELLEGRI FILIPPO")
        self.assertEqual(s["kind"], "SQUALIFICA_GARE")
        self.assertEqual(s["detail"], "DUE")

    def test_ammonizione_con_diffida(self):
        s = _sanction(self.parsed, "CANOVA GIANMARCO")
        self.assertEqual(s["kind"], "AMMONIZIONE")
        self.assertEqual(s["detail"], "I_DIFFIDA")

    def test_la_motivazione_si_attacca_alla_squalifica_precedente(self):
        s = _sanction(self.parsed, "RANIERI RICCARDO")
        self.assertIn("gravi proteste", s["reason"])

    def test_larbitro_della_motivazione_non_diventa_un_tesserato(self):
        """'nei confronti dell'Arbitro (art. 36)' non e' un giocatore."""
        people = {s["person"] for s in self.parsed["sanctions"]}
        self.assertFalse(any("ARBITRO" in p.upper() for p in people))

    def test_artefatti_di_impaginazione_ignorati(self):
        self.assertFalse(any("5036" in s["person"]
                             for s in self.parsed["sanctions"]))


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.store = CUStore(":memory:")
        self.parsed = parse_cu_text(CU_REALE)

    def tearDown(self):
        self.store.close()

    def test_reingerire_lo_stesso_cu_non_duplica(self):
        """Requisito: rilanciare l'ingestion deve essere sicuro."""
        first = self.store.ingest(self.parsed)
        self.assertGreater(first["new_sanctions"], 0)
        self.assertEqual(self.store.ingest(self.parsed),
                         {"new_sanctions": 0, "new_results": 0})

    def test_squalificati_alla_data_del_brief(self):
        self.store.ingest(self.parsed)
        nomi = {r["person"] for r in self.store.squalificati("2026-04-16")}
        self.assertIn("RANIERI RICCARDO", nomi)   # squalificato fino al 18/5
        self.assertIn("PELLEGRI FILIPPO", nomi)   # due giornate
        self.assertNotIn("VIGHI ALESSIO", nomi)   # solo diffidato

    def test_squalifica_scaduta_esce_dalla_lista(self):
        self.store.ingest(self.parsed)
        nomi = {r["person"] for r in self.store.squalificati("2026-06-01")}
        self.assertNotIn("RANIERI RICCARDO", nomi)

    def test_indice_di_presenza_conta_solo_i_calciatori(self):
        """Un dirigente ammonito non era in campo: fuori dall'indice."""
        self.store.ingest(self.parsed)
        nomi = {r["person"] for r in self.store.presence_index()}
        self.assertIn("PELLEGRI FILIPPO", nomi)
        self.assertNotIn("VIGHI ALESSIO", nomi)      # DIRIGENTI
        self.assertNotIn("RANIERI RICCARDO", nomi)   # ALLENATORI

    def test_indice_di_presenza_filtrato_per_societa(self):
        self.store.ingest(self.parsed)
        rows = self.store.presence_index(club="CASTENASO CALCIO")
        self.assertTrue(rows)
        self.assertTrue(all(r["club"] == "CASTENASO CALCIO" for r in rows))

    def test_due_cu_diversi_accumulano_giornate_distinte(self):
        self.store.ingest(self.parsed)
        secondo = parse_cu_text(
            CU_REALE.replace("N. 146 DEL 13/4/2026", "N. 152 DEL 20/4/2026")
                    .replace("GARE DEL 11/ 4/2026", "GARE DEL 18/ 4/2026"))
        self.assertGreater(self.store.ingest(secondo)["new_sanctions"], 0)
        row = next(r for r in self.store.presence_index()
                   if r["person"] == "PELLEGRI FILIPPO")
        self.assertEqual(row["giornate_distinte"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
