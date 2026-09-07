#!/usr/bin/env python3
"""
ECC-001 — test dello scoring per l'Eccellenza.

Il caso che conta di piu' non e' un punteggio giusto: e' il **rifiuto**. Un
club di Eccellenza non ha un ufficio dati che ricontrolla, quindi un numero su
un record non tracciabile diventa direttamente una telefonata sbagliata.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_scoring_eccellenza -v
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring_eccellenza import EccellenzaScorer, valuta_lista

OGGI = datetime.now(timezone.utc).isoformat()
TM = "https://www.transfermarkt.it/mario-rossi/profil/spieler/123456"


def opp(**kw):
    """Record minimo che PASSA l'ammissione: i test tolgono un pezzo per volta."""
    base = {"player_name": "Mario Rossi", "opportunity_type": "svincolato",
            "tm_url": TM, "tm_verified_at": OGGI, "appearances": 40,
            "age": 22, "market_value": 20000, "discovered_at": OGGI,
            "current_club": "Savignanese", "summary": "svincolato, ex Serie D"}
    base.update(kw)
    return base


class AmmissioneTestCase(unittest.TestCase):
    """Chi non e' verificabile non prende un punteggio basso: non lo prende."""

    def setUp(self):
        self.s = EccellenzaScorer(base="rimini")

    def test_senza_profilo_tm_non_e_valutabile(self):
        r = self.s.score(opp(tm_url=None))
        self.assertFalse(r["valutabile"])
        self.assertIsNone(r["punteggio"])
        self.assertIn("scheda", r["motivo"])

    def test_profilo_mai_aperto_non_basta(self):
        """L'URL c'e' ma nessuno l'ha aperto: tm_verified_at manca."""
        r = self.s.score(opp(tm_verified_at=None))
        self.assertFalse(r["valutabile"])

    def test_redirect_di_ricerca_e_detto_per_nome(self):
        r = self.s.score(opp(tm_url=None, tm_verified_at=None,
                             source_url="https://vertexaisearch.cloud.google.com/"
                                        "grounding-api-redirect/AbC"))
        self.assertFalse(r["valutabile"])
        self.assertIn("scade", r["motivo"])

    def test_una_presenza_non_e_una_carriera(self):
        """Il caso Gagliano: 1 presenza in carriera non regge un giudizio."""
        r = self.s.score(opp(appearances=1))
        self.assertFalse(r["valutabile"])
        self.assertIn("5 partite", r["motivo"])

    def test_segnalazione_vecchia_non_descrive_piu_la_realta(self):
        vecchio = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        r = self.s.score(opp(discovered_at=vecchio))
        self.assertFalse(r["valutabile"])
        # il motivo cita la soglia, non i giorni del singolo: cosi' gli scarti
        # si contano insieme invece di sparpagliarsi in bucket da uno
        self.assertIn("45 giorni", r["motivo"])

    def test_due_record_vecchi_finiscono_nello_stesso_motivo(self):
        v1 = (datetime.now(timezone.utc) - timedelta(days=87)).isoformat()
        v2 = (datetime.now(timezone.utc) - timedelta(days=190)).isoformat()
        r = valuta_lista([opp(discovered_at=v1), opp(discovered_at=v2)], base="rimini")
        self.assertEqual(len(r["scartati_per_motivo"]), 1)

    def test_record_completo_passa(self):
        self.assertTrue(self.s.score(opp())["valutabile"])


class ANotazioneUmanaTestCase(unittest.TestCase):
    """
    Requisito esplicito: chi legge non e' un analista. Ogni uscita deve essere
    una frase che dice la CONSEGUENZA, non la misura. "prossimita 100" non e'
    un risultato utilizzabile; "abita in zona" lo e'.
    """

    def setUp(self):
        self.s = EccellenzaScorer(base="rimini")

    def test_ogni_rifiuto_e_una_frase_comprensibile(self):
        for record in (opp(tm_url=None), opp(appearances=1), opp(age=None)):
            r = self.s.score(record)
            self.assertTrue(r["riassunto"].startswith("Non lo proponiamo:"))
            self.assertTrue(r["riassunto"].endswith("."))

    def test_niente_gergo_nei_motivi(self):
        """Le parole che una persona fuori dal mestiere non deve incontrare."""
        gergo = ("redirect", "transfermarkt", "url", "tm_", "score", "breakdown",
                 "gate", "parser", "record")
        for record in (opp(tm_url=None), opp(appearances=1), opp(age=None),
                       opp(tm_url=None, tm_verified_at=None,
                           source_url="https://vertexaisearch.cloud.google.com/x")):
            motivo = self.s.score(record)["motivo"].lower()
            for parola in gergo:
                self.assertNotIn(parola, motivo, f"gergo '{parola}' in: {motivo}")

    def test_il_promosso_ha_una_riga_da_leggere_al_telefono(self):
        r = self.s.score(opp(current_club="Riccione"))
        self.assertTrue(r["valutabile"])
        self.assertIn("Abita in zona", r["riassunto"])
        self.assertIn("svincolato", r["riassunto"])
        # una frase per ognuna delle cinque componenti
        self.assertGreaterEqual(len(r["spiegazione"]), 4)

    def test_la_frase_cambia_col_dato_non_e_un_testo_fisso(self):
        vicino = self.s.score(opp(current_club="Riccione"))["spiegazione"][0]
        lontano = self.s.score(opp(current_club="Palermo", summary=""))["spiegazione"][0]
        self.assertNotEqual(vicino, lontano)
        self.assertIn("Non risulta un legame", lontano)

    def test_nessun_motivo_contiene_i_due_punti(self):
        """Il chiamante scrive "Non lo proponiamo: {motivo}." — se il motivo
        ne ha gia' uno, la frase esce con due volte i due punti."""
        for record in (opp(tm_url=None), opp(appearances=1), opp(age=None),
                       opp(discovered_at="2026-01-01T00:00:00+00:00")):
            self.assertNotIn(":", self.s.score(record)["motivo"])

    def test_savignanese_e_riconosciuta_come_zona(self):
        """Le societa' si chiamano come il paese ma declinato: cercare
        "savignano" mancava "Savignanese", che e' a mezz'ora da Rimini."""
        r = self.s.score(opp(current_club="Savignanese", summary=""))
        self.assertEqual(r["breakdown"]["prossimita"], 100)

    def test_il_prestito_avvisa_che_serve_il_club(self):
        r = self.s.score(opp(opportunity_type="prestito"))
        self.assertIn("accordo del club", " ".join(r["spiegazione"]))


class SegnoInvertitoTestCase(unittest.TestCase):
    """
    La differenza vera con SCORE-002: in Serie C il valore alto e' un pregio,
    qui e' il segnale che non lo prendi. Se questo test si rompe, qualcuno ha
    riportato ECC-001 alla logica della categoria sbagliata.
    """

    def setUp(self):
        self.s = EccellenzaScorer(base="rimini")

    def test_valore_alto_penalizza(self):
        basso = self.s.score(opp(market_value=20000))["breakdown"]["sostenibilita"]
        alto = self.s.score(opp(market_value=500000))["breakdown"]["sostenibilita"]
        self.assertGreater(basso, alto)

    def test_nessun_valore_non_e_un_difetto(self):
        senza = self.s.score(opp(market_value=None))["breakdown"]["sostenibilita"]
        self.assertGreaterEqual(senza, 70)


class ProssimitaTestCase(unittest.TestCase):

    def setUp(self):
        self.s = EccellenzaScorer(base="rimini")

    def test_bacino_vicino_batte_il_medio_che_batte_il_lontano(self):
        vicino = self.s.score(opp(current_club="Santarcangelo"))["breakdown"]["prossimita"]
        medio = self.s.score(opp(current_club="Ravenna"))["breakdown"]["prossimita"]
        lontano = self.s.score(opp(current_club="Palermo", summary=""))["breakdown"]["prossimita"]
        self.assertGreater(vicino, medio)
        self.assertGreater(medio, lontano)

    def test_il_lontano_non_e_zero(self):
        """Un legame puo' esistere e non essere scritto: si penalizza, non si esclude."""
        self.assertGreater(
            self.s.score(opp(current_club="Palermo", summary=""))["breakdown"]["prossimita"], 0)


class ListaTestCase(unittest.TestCase):

    def test_l_imbuto_dice_perche_ha_scartato(self):
        lista = [opp(), opp(tm_url=None), opp(appearances=1), opp(tm_url=None)]
        r = valuta_lista(lista, base="rimini")
        self.assertEqual(r["totale_esaminati"], 4)
        self.assertEqual(len(r["valutati"]), 1)
        self.assertEqual(sum(r["scartati_per_motivo"].values()), 3)

    def test_ordinati_dal_migliore(self):
        lista = [opp(current_club="Palermo", summary=""), opp(current_club="Riccione")]
        v = valuta_lista(lista, base="rimini")["valutati"]
        self.assertGreaterEqual(v[0]["ecc_score"], v[1]["ecc_score"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
