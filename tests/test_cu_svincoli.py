#!/usr/bin/env python3
"""
Gli svincolati dai CU: il parser che produce i nomi che il radar non trovava.

Testi ricopiati dai comunicati veri del Comitato Emilia-Romagna (CU 71 del
3/12/2025 e CU 20 del settembre 2026), comprese le sporcizie di estrazione.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_cu_svincoli -v
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cu_svincoli import nome_incerto, parse_svincoli, solo_maggiorenni

# Dal CU 71: intestazione, righe, e la frase che chiude la tabella.
REALE = """SVINCOLI EX ART. 117bis NOIF
vista la documentazione depositata al Comitato Regionale Emilia Romagna, si dichiarano
svincolati i seguenti calciatori:
Matricola Calciatore Nascita Matricola Società
4630785 CARBONI FILIPPO 25/03/1998 70392 OSTERIA GRANDE
6893545 TORTORA KEVIN 01/05/2004 6740 BOBBIESE
3.937.990 DRAGHI LUCA 15/01/1990 70718 CADEO
2527805 GOLFARELLI NICOLO' 22/02/2003 940778 VIRTUS LIBERTAS
È possibile effettuare il nuovo tesseramento dilettantistico entro il termine stabilito
PROVVEDIMENTI DISCIPLINARI
ROSSI MARIO (BOBBIESE) I AMMONIZIONE DIFFIDA
"""


class ParseTestCase(unittest.TestCase):

    def setUp(self):
        self.r = parse_svincoli(REALE, cu_number=71, cu_date="2025-12-03")

    def test_prende_tutte_le_righe(self):
        self.assertEqual(len(self.r), 4)

    def test_matricola_puntata_diventa_liscia(self):
        """Il comitato scrive sia 3937990 sia 3.937.990: e' la stessa chiave."""
        draghi = next(x for x in self.r if x["nome"].startswith("Draghi"))
        self.assertEqual(draghi["matricola"], "3937990")

    def test_data_di_nascita_ed_eta(self):
        c = next(x for x in self.r if x["matricola"] == "4630785")
        self.assertEqual(c["nascita"], "1998-03-25")
        self.assertEqual(c["nome"], "Carboni Filippo")
        self.assertEqual(c["societa"], "OSTERIA GRANDE")

    def test_apostrofo_nel_nome_non_rompe_la_riga(self):
        g = next(x for x in self.r if x["matricola"] == "2527805")
        self.assertEqual(g["societa"], "VIRTUS LIBERTAS")

    def test_la_tabella_finisce_dove_lo_dice_il_comitato(self):
        """Senza il confine il regex prosegue nei provvedimenti disciplinari,
        e "ROSSI MARIO (BOBBIESE)" diventerebbe uno svincolato."""
        self.assertNotIn("Rossi Mario", [x["nome"] for x in self.r])

    def test_il_comunicato_senza_tabella_non_e_un_errore(self):
        self.assertEqual(parse_svincoli("PROVVEDIMENTI DISCIPLINARI\nnulla"), [])

    def test_porta_con_se_il_comunicato_di_provenienza(self):
        """Ogni nome deve poter essere citato: CU numero e data."""
        for s in self.r:
            self.assertEqual((s["cu_number"], s["cu_date"]), (71, "2025-12-03"))


class NomeSporcoTestCase(unittest.TestCase):
    """
    "CAVALLIN I EDOARDO" nel CU vero era "CAVALLINI EDOARDO": pypdf spezza.
    Non si indovina — un'iniziale puntata esiste davvero — quindi si marca.
    """

    def test_riconosce_la_lettera_isolata(self):
        self.assertTrue(nome_incerto("CAVALLIN I EDOARDO"))
        self.assertFalse(nome_incerto("CARBONI FILIPPO"))

    def test_il_record_porta_la_marcatura(self):
        t = REALE.replace("CARBONI FILIPPO", "CAVALLIN I EDOARDO")
        r = parse_svincoli(t)
        sporco = next(x for x in r if "Cavallin" in x["nome"])
        self.assertTrue(sporco["nome_incerto"])
        pulito = next(x for x in r if x["nome"].startswith("Tortora"))
        self.assertFalse(pulito["nome_incerto"])


class MinorenniTestCase(unittest.TestCase):
    """
    I CU pubblicano anche tesserati minorenni. Leggerli e' legittimo — sono
    atti pubblici — ma il nome di un minore non finisce su una scheda che gira
    su WhatsApp. Il vincolo sta in una funzione, non nella memoria di chi
    scrivera' il prossimo script.
    """

    def test_esclude_gli_under_18(self):
        lista = [{"nascita": "2010-05-01"}, {"nascita": "1998-03-25"}]
        r = solo_maggiorenni(lista, al=date(2026, 9, 8))
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["nascita"], "1998-03-25")

    def test_chi_compie_18_anni_oggi_passa(self):
        r = solo_maggiorenni([{"nascita": "2008-09-08"}], al=date(2026, 9, 8))
        self.assertEqual(len(r), 1)

    def test_data_mancante_non_passa(self):
        """Senza data non si puo' dimostrare la maggiore eta': si esclude."""
        self.assertEqual(solo_maggiorenni([{"nascita": ""}]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
