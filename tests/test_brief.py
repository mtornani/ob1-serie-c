#!/usr/bin/env python3
"""
Test offline del brief del giovedì (ARCH-003).

Un alert automatico vive o muore sui falsi positivi: il caso che guida questi
test è il giocatore diffidato e poi squalificato, che NON deve continuare a
comparire tra i diffidati. Alla seconda segnalazione sbagliata il DS smette
di leggere, e lo strumento è morto.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_brief -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.brief import build_brief, format_telegram
from src.cu_parser import CUStore


def _cu(number, cu_date, match_date, sanctions):
    return {"meta": {"cu_number": number, "cu_date": cu_date},
            "results": [],
            "sanctions": [{"category": "ECCELLENZA", "match_date": match_date,
                           "role": "CALCIATORI", "reason": None, **s}
                          for s in sanctions]}


AMM = {"kind": "AMMONIZIONE", "detail": "I_DIFFIDA"}
SQ2 = {"kind": "SQUALIFICA_GARE", "detail": "DUE"}


class DiffidatiTestCase(unittest.TestCase):
    def setUp(self):
        self.store = CUStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_diffidato_semplice_compare(self):
        self.store.ingest(_cu(10, "2026-04-13", "2026-04-11",
                              [{**AMM, "person": "ROSSI MARIO", "club": "RIMINI"}]))
        self.assertEqual([r["person"] for r in self.store.diffidati()],
                         ["ROSSI MARIO"])

    def test_diffidato_poi_squalificato_non_e_piu_in_diffida(self):
        """Il falso positivo che ucciderebbe la fiducia nell'alert."""
        self.store.ingest(_cu(10, "2026-04-13", "2026-04-11",
                              [{**AMM, "person": "ROSSI MARIO", "club": "RIMINI"}]))
        self.store.ingest(_cu(11, "2026-04-20", "2026-04-18",
                              [{**SQ2, "person": "ROSSI MARIO", "club": "RIMINI"}]))
        self.assertEqual(self.store.diffidati(), [])

    def test_squalificato_e_poi_di_nuovo_diffidato_torna_in_lista(self):
        """Scontata la squalifica, la diffida successiva vale di nuovo."""
        self.store.ingest(_cu(11, "2026-04-20", "2026-04-18",
                              [{**SQ2, "person": "ROSSI MARIO", "club": "RIMINI"}]))
        self.store.ingest(_cu(12, "2026-04-27", "2026-04-25",
                              [{**AMM, "person": "ROSSI MARIO", "club": "RIMINI"}]))
        self.assertEqual([r["person"] for r in self.store.diffidati()],
                         ["ROSSI MARIO"])

    def test_filtro_per_societa(self):
        self.store.ingest(_cu(10, "2026-04-13", "2026-04-11", [
            {**AMM, "person": "ROSSI MARIO", "club": "RIMINI"},
            {**AMM, "person": "BIANCHI LUCA", "club": "CESENA"}]))
        self.assertEqual([r["person"] for r in self.store.diffidati(club="RIMINI")],
                         ["ROSSI MARIO"])

    def test_i_dirigenti_non_sono_diffidati_utili(self):
        cu = _cu(10, "2026-04-13", "2026-04-11",
                 [{**AMM, "person": "VERDI ANNA", "club": "RIMINI"}])
        cu["sanctions"][0]["role"] = "DIRIGENTI"
        self.store.ingest(cu)
        self.assertEqual(self.store.diffidati(), [])


class SqualificatiTestCase(unittest.TestCase):
    def setUp(self):
        self.store = CUStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_squalifica_a_data_e_certa_finche_non_scade(self):
        self.store.ingest(_cu(10, "2026-04-13", "2026-04-11",
                              [{"kind": "SQUALIFICA_FINO_AL", "detail": "2026-05-18",
                                "person": "ROSSI MARIO", "club": "RIMINI"}]))
        rows = self.store.squalificati("2026-04-16")
        self.assertEqual(rows[0]["certezza"], "certa")
        self.assertEqual(self.store.squalificati("2026-05-20"), [])

    def test_squalifica_a_giornate_e_stimata(self):
        self.store.ingest(_cu(10, "2026-04-13", "2026-04-11",
                              [{**SQ2, "person": "ROSSI MARIO", "club": "RIMINI"}]))
        self.assertEqual(self.store.squalificati("2026-04-16")[0]["certezza"], "stimata")

    def test_squalifica_a_giornate_vecchia_si_considera_scontata(self):
        """Oltre la finestra, tenerla in lista produrrebbe rumore."""
        self.store.ingest(_cu(10, "2026-01-13", "2026-01-11",
                              [{**SQ2, "person": "ROSSI MARIO", "club": "RIMINI"}]))
        self.assertEqual(self.store.squalificati("2026-04-16"), [])


class FormatTestCase(unittest.TestCase):
    def setUp(self):
        self.store = CUStore(":memory:")
        self.store.ingest(_cu(146, "2026-04-13", "2026-04-11", [
            {**AMM, "person": "ROSSI MARIO", "club": "RIMINI"},
            {**SQ2, "person": "BIANCHI LUCA", "club": "RIMINI"},
        ]))

    def tearDown(self):
        self.store.close()

    def _msg(self, **kw):
        return format_telegram(build_brief(self.store, "2026-04-16", "RIMINI", **kw))

    def test_il_messaggio_porta_squalificati_diffidati_e_fonte(self):
        msg = self._msg()
        self.assertIn("Bianchi Luca", msg)
        self.assertIn("due giornate", msg)
        self.assertIn("Rossi Mario", msg)
        self.assertIn("Comunicato Ufficiale n.146", msg)

    def test_la_legenda_segue_sempre_il_marcatore_di_stima(self):
        self.assertIn("verifica se già scontata", self._msg())

    def test_nessuna_legenda_se_tutto_e_certo(self):
        store = CUStore(":memory:")
        store.ingest(_cu(10, "2026-04-13", "2026-04-11",
                         [{"kind": "SQUALIFICA_FINO_AL", "detail": "2026-05-18",
                           "person": "ROSSI MARIO", "club": "RIMINI"}]))
        msg = format_telegram(build_brief(store, "2026-04-16", "RIMINI"))
        self.assertNotIn("verifica se già scontata", msg)
        store.close()

    def test_la_legenda_compare_anche_se_la_stima_e_solo_sullavversario(self):
        store = CUStore(":memory:")
        store.ingest(_cu(10, "2026-04-13", "2026-04-11", [
            {"kind": "SQUALIFICA_FINO_AL", "detail": "2026-05-18",
             "person": "ROSSI MARIO", "club": "RIMINI"},
            {**SQ2, "person": "NERI PAOLO", "club": "CESENA"}]))
        msg = format_telegram(
            build_brief(store, "2026-04-16", "RIMINI", opponent="CESENA"))
        self.assertIn("verifica se già scontata", msg)
        store.close()

    def test_i_ruoli_non_giocatori_sono_marcati(self):
        store = CUStore(":memory:")
        cu = _cu(10, "2026-04-13", "2026-04-11",
                 [{"kind": "SQUALIFICA_FINO_AL", "detail": "2026-05-18",
                   "person": "RANIERI RICCARDO", "club": "RIMINI"}])
        cu["sanctions"][0]["role"] = "ALLENATORI"
        store.ingest(cu)
        self.assertIn("Ranieri Riccardo (all.)",
                      format_telegram(build_brief(store, "2026-04-16", "RIMINI")))
        store.close()

    def test_niente_da_dire_non_produce_contenuto(self):
        brief = build_brief(self.store, "2026-04-16", "SOCIETA INESISTENTE")
        self.assertFalse(brief["has_content"])
        self.assertIn("Nessuna squalifica", format_telegram(brief))

    def test_il_messaggio_sta_in_un_solo_invio_telegram(self):
        self.assertLess(len(self._msg()), 4096)


if __name__ == "__main__":
    unittest.main(verbosity=2)
