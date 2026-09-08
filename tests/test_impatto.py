#!/usr/bin/env python3
"""
IMPATTO: il potenziale di categoria, tenuto separato dalla fattibilità.

Il test che conta di piu' non e' su un punteggio: e' che l'uscita **dichiari
cio' che non sa**. Una scheda che tace sui minuti non giocati è una scheda che
si spaccia per valutazione tecnica.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_impatto -v
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.impatto import DISCLAIMER, ordina, valuta_impatto

MAPPA = {"fiorenzuola 1922": "serie_d", "sanpaimola": "eccellenza",
         "reno molinella 1911": "promozione", "gambettola": "prima_categoria"}
OGGI = date(2026, 9, 8)


def sv(**kw):
    base = {"nome": "Rossi Mario", "eta": 26, "societa": "SANPAIMOLA",
            "cu_date": "2026-09-04", "nome_incerto": False}
    base.update(kw)
    return base


class DichiarazioneTestCase(unittest.TestCase):
    """Il patto con chi legge: qui c'è una ricerca, il giudizio è suo."""

    def test_ogni_risultato_porta_i_limiti(self):
        r = valuta_impatto(sv(), MAPPA, al=OGGI)
        testo = " ".join(r["limiti"]).lower()
        self.assertIn("quante partite", testo)
        self.assertIn("non è nostro", testo)

    def test_ogni_risultato_porta_il_disclaimer(self):
        self.assertEqual(valuta_impatto(sv(), MAPPA, al=OGGI)["disclaimer"], DISCLAIMER)

    def test_il_disclaimer_nega_la_valutazione_tecnica(self):
        d = DISCLAIMER.lower()
        self.assertIn("non una valutazione tecnica", d)

    def test_il_nome_sporco_diventa_un_limite_dichiarato(self):
        r = valuta_impatto(sv(nome_incerto=True), MAPPA, al=OGGI)
        self.assertTrue(any("comitato" in l for l in r["limiti"]))


class SaltoTestCase(unittest.TestCase):
    """La sola cosa misurabile: da che categoria arriva."""

    def test_chi_scende_dalla_serie_d_pesa_di_piu(self):
        alto = valuta_impatto(sv(societa="FIORENZUOLA 1922 SSD ARL"), MAPPA, al=OGGI)
        pari = valuta_impatto(sv(societa="SANPAIMOLA"), MAPPA, al=OGGI)
        basso = valuta_impatto(sv(societa="GAMBETTOLA"), MAPPA, al=OGGI)
        self.assertGreater(alto["punteggio"], pari["punteggio"])
        self.assertGreater(pari["punteggio"], basso["punteggio"])
        self.assertEqual(alto["salto"], 1)

    def test_la_frase_dice_la_categoria_per_nome(self):
        r = valuta_impatto(sv(societa="FIORENZUOLA 1922 SSD ARL"), MAPPA, al=OGGI)
        self.assertIn("Serie D", r["riassunto"])

    def test_categoria_ignota_non_premia(self):
        """Non sapere non è un merito: si dichiara e si resta bassi."""
        r = valuta_impatto(sv(societa="SOCIETA MAI VISTA"), MAPPA, al=OGGI)
        self.assertIsNone(r["categoria_provenienza"])
        self.assertLess(r["breakdown"]["salto"], 65)
        self.assertIn("non è nei calendari", r["riassunto"])


class EtaEFreschezzaTestCase(unittest.TestCase):

    def test_la_fascia_centrale_batte_il_veterano(self):
        giovane = valuta_impatto(sv(eta=26), MAPPA, al=OGGI)["breakdown"]["eta"]
        vecchio = valuta_impatto(sv(eta=37), MAPPA, al=OGGI)["breakdown"]["eta"]
        self.assertGreater(giovane, vecchio)

    def test_svincolato_da_poco_vale_di_piu(self):
        fresco = valuta_impatto(sv(cu_date="2026-09-04"), MAPPA, al=OGGI)
        vecchio = valuta_impatto(sv(cu_date="2026-07-06"), MAPPA, al=OGGI)
        self.assertGreater(fresco["punteggio"], vecchio["punteggio"])
        self.assertIn("può aver già firmato", vecchio["riassunto"])


class OrdinamentoTestCase(unittest.TestCase):

    def test_ordina_dal_potenziale_piu_alto(self):
        lista = [sv(nome="Basso", societa="GAMBETTOLA"),
                 sv(nome="Alto", societa="FIORENZUOLA 1922 SSD ARL")]
        r = ordina(lista, MAPPA, al=OGGI)
        self.assertEqual(r[0]["nome"], "Alto")
        self.assertIn("impatto", r[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
