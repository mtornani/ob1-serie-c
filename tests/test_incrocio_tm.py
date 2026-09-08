#!/usr/bin/env python3
"""
Fact check: l'identità si verifica sulla DATA DI NASCITA, non sul nome.

E' la regola che il database vecchio non aveva, ed e' il motivo per cui
conteneva "CHIOETTO JHONATAN DAVID" accoppiato al profilo di Jonathan David
(30 milioni, Juventus). Dai Comunicati la data arriva esatta: se non combacia,
non e' lui — anche quando il nome e' identico.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_incrocio_tm -v
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.incrocia_svincoli_tm as ic

SV = {"nome": "Varoli Fabio", "nascita": "1999-01-14", "societa": "FIORENZUOLA"}


class NomeTestCase(unittest.TestCase):
    """I CU scrivono COGNOME NOME, Transfermarkt cerca per Nome Cognome."""

    def test_inverte_due_parole(self):
        self.assertEqual(ic._nome_invertito("Varoli Fabio"), "Fabio Varoli")

    def test_lascia_stare_i_nomi_composti(self):
        """Con tre parole non si sa dove finisce il cognome: non si indovina."""
        self.assertEqual(ic._nome_invertito("Ngom Mouhamadou Lami"),
                         "Ngom Mouhamadou Lami")


class IdentitaTestCase(unittest.TestCase):

    def _con(self, profili, dati_per_url):
        return (mock.patch.object(ic, "cerca_profili", return_value=profili),
                mock.patch.object(ic, "_get", return_value=object()),
                mock.patch.object(ic, "_testo", return_value="x"),
                mock.patch.object(ic, "parse_tm_text",
                                  side_effect=lambda t, u: dati_per_url[u]))

    def test_data_coincidente_conferma(self):
        u = "https://x/1"
        p = self._con([u], {u: {"birth_date": "1999-01-14", "current_club": "Fiorenzuola"}})
        with p[0], p[1], p[2], p[3]:
            r = ic.verifica(SV, pausa=0)
        self.assertEqual(r["fact_check"]["stato"], "confermato")
        self.assertEqual(r["fact_check"]["tm_url"], u)

    def test_omonimo_con_altra_data_viene_scartato(self):
        """Il caso Chioetto: stesso nome, persona diversa."""
        u = "https://x/2"
        p = self._con([u], {u: {"birth_date": "1990-05-03"}})
        with p[0], p[1], p[2], p[3]:
            r = ic.verifica(SV, pausa=0)
        self.assertEqual(r["fact_check"]["stato"], "scartato")
        self.assertIn("1990-05-03", r["fact_check"]["motivo"])

    def test_nessun_profilo_non_e_un_difetto(self):
        """Nei dilettanti la maggioranza non ha una scheda: e' normale."""
        with mock.patch.object(ic, "cerca_profili", return_value=[]):
            r = ic.verifica(SV, pausa=0)
        self.assertEqual(r["fact_check"]["stato"], "assente")
        self.assertIsNone(r["fact_check"]["tm_url"])

    def test_il_profilo_senza_data_non_conferma_niente(self):
        u = "https://x/3"
        p = self._con([u], {u: {"current_club": "Fiorenzuola"}})
        with p[0], p[1], p[2], p[3]:
            r = ic.verifica(SV, pausa=0)
        self.assertEqual(r["fact_check"]["stato"], "assente")

    def test_il_record_originale_non_viene_perso(self):
        with mock.patch.object(ic, "cerca_profili", return_value=[]):
            r = ic.verifica(SV, pausa=0)
        self.assertEqual(r["nome"], SV["nome"])
        self.assertEqual(r["societa"], SV["societa"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
