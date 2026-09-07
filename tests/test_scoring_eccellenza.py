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
        # anche la PROVA dev'essere vecchia: un profilo aperto oggi rende
        # fresco il record anche se la notizia e' di marzo, ed e' voluto
        r = self.s.score(opp(discovered_at=vecchio, tm_verified_at=vecchio))
        self.assertFalse(r["valutabile"])
        # il motivo cita la soglia, non i giorni del singolo: cosi' gli scarti
        # si contano insieme invece di sparpagliarsi in bucket da uno
        self.assertIn("45 giorni", r["motivo"])

    def test_due_record_vecchi_finiscono_nello_stesso_motivo(self):
        v1 = (datetime.now(timezone.utc) - timedelta(days=87)).isoformat()
        v2 = (datetime.now(timezone.utc) - timedelta(days=190)).isoformat()
        r = valuta_lista([opp(discovered_at=v1, tm_verified_at=v1),
                          opp(discovered_at=v2, tm_verified_at=v2)], base="rimini")
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
                       opp(discovered_at="2026-01-01T00:00:00+00:00",
                           tm_verified_at="2026-01-01T00:00:00+00:00")):
            self.assertNotIn(":", self.s.score(record)["motivo"])

    def test_savignanese_e_riconosciuta_come_zona(self):
        """Le societa' si chiamano come il paese ma declinato: cercare
        "savignano" mancava "Savignanese", che e' a mezz'ora da Rimini."""
        r = self.s.score(opp(current_club="Savignanese", summary=""))
        self.assertEqual(r["breakdown"]["prossimita"], 100)

    def test_il_prestito_avvisa_che_serve_il_club(self):
        r = self.s.score(opp(opportunity_type="prestito"))
        self.assertIn("accordo del club", " ".join(r["spiegazione"]))


class RicontrolloTestCase(unittest.TestCase):
    """
    Il ri-controllo (scripts/refresh_verificati.py) deve poter cambiare il
    verdetto, altrimenti non serve a niente: il gate continuerebbe a scartare
    sulla data della notizia invece che su quella della verifica.
    """

    def setUp(self):
        self.s = EccellenzaScorer(base="rimini")
        self.vecchio = "2026-03-02T00:00:00+00:00"

    def test_una_prova_di_oggi_riabilita_una_segnalazione_di_marzo(self):
        scaduto = opp(discovered_at=self.vecchio, tm_verified_at=self.vecchio)
        self.assertFalse(self.s.score(scaduto)["valutabile"])
        ricontrollato = opp(discovered_at=self.vecchio, tm_verified_at=OGGI,
                            club_attuale_verificato="")
        self.assertTrue(self.s.score(ricontrollato)["valutabile"])

    def test_bussare_senza_risposta_non_e_una_prova(self):
        """
        Il bug del primo giro: 39 giocatori su 39 dati "senza squadra" a
        settembre, perche' l'assenza di un club nel parse veniva scritta come
        assenza di club nella realta'. Se la pagina non dice dove gioca,
        `tm_verified_at` non si rinnova e il record resta vecchio.
        """
        bussato = opp(discovered_at=self.vecchio, tm_verified_at=self.vecchio,
                      refreshed_at=OGGI, club_attuale_verificato=None)
        r = self.s.score(bussato)
        self.assertFalse(r["valutabile"])
        self.assertIn("45 giorni", r["motivo"])

    def test_chi_ha_firmato_altrove_non_e_piu_un_opportunita(self):
        r = self.s.score(opp(tm_verified_at=OGGI, opportunity_type="svincolato",
                             club_attuale_verificato="SS Maceratese 1922"))
        self.assertFalse(r["valutabile"])
        self.assertIn("Maceratese", r["motivo"])

    def test_per_un_prestito_avere_un_club_e_normale(self):
        """Il rifiuto vale per chi si dichiarava libero, non per chi e' in prestito."""
        r = self.s.score(opp(tm_verified_at=OGGI, opportunity_type="prestito",
                             club_attuale_verificato="SS Maceratese 1922",
                             current_club="Riccione"))
        self.assertTrue(r["valutabile"])
        self.assertEqual(r["fascia"], "da seguire")
        self.assertIn("Maceratese", r["riassunto"])


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


class DaSeguireTestCase(unittest.TestCase):
    """
    La quarta uscita. Senza, un giocatore buono ma legato a un contratto
    finiva in "fuori profilo" insieme a chi non va bene — e sono due
    decisioni diverse: una si archivia, l'altra si mette in agenda.
    """

    def setUp(self):
        self.s = EccellenzaScorer(base="rimini")

    def test_buono_ma_in_prestito_e_da_seguire(self):
        r = self.s.score(opp(opportunity_type="prestito", current_club="Riccione"))
        self.assertEqual(r["fascia"], "da seguire")
        self.assertEqual(r["rivedere_a"], "gennaio")
        self.assertIn("gennaio", r["riassunto"])

    def test_buono_ma_troppo_caro_oggi_e_da_seguire(self):
        """Dopo mesi da fermo la stessa persona risponde in un altro modo."""
        r = self.s.score(opp(market_value=600000, current_club="Riccione"))
        self.assertEqual(r["fascia"], "da seguire")
        self.assertIn("categoria superiore", r["riassunto"])

    def test_la_frase_del_freno_non_ripete_oggi(self):
        """Il chiamante scrive gia' "Oggi non e' disponibile perche' {freno}"."""
        r = self.s.score(opp(market_value=600000, current_club="Riccione"))
        frase = [f for f in r["spiegazione"] if f.startswith("Oggi non")][0]
        self.assertEqual(frase.lower().count("oggi"), 1)

    def test_scadenza_di_contratto_e_da_seguire(self):
        r = self.s.score(opp(opportunity_type="scadenza", current_club="Riccione"))
        self.assertEqual(r["fascia"], "da seguire")

    def test_bloccato_ma_senza_merito_resta_fuori_profilo(self):
        """Il freno temporaneo non promuove chi non andrebbe bene comunque:
        lontano, categoria sbagliata ed eta' alta restano un no."""
        r = self.s.score(opp(opportunity_type="prestito", current_club="Palermo",
                             summary="Serie A", age=36))
        self.assertEqual(r["fascia"], "fuori profilo")
        self.assertIsNone(r["rivedere_a"])

    def test_lo_svincolato_alla_portata_resta_da_chiamare(self):
        """Chi e' disponibile adesso non deve finire in agenda: si chiama."""
        r = self.s.score(opp(current_club="Riccione"))
        self.assertEqual(r["fascia"], "da chiamare")
        self.assertIsNone(r["rivedere_a"])

    def test_il_merito_stabile_ignora_cio_che_scade(self):
        """Contratto e prezzo cambiano, dove abita e quanti anni ha no."""
        libero = self.s.score(opp(current_club="Riccione"))
        legato = self.s.score(opp(current_club="Riccione", opportunity_type="prestito",
                                  market_value=600000))
        self.assertEqual(libero["merito_stabile"], legato["merito_stabile"])
        self.assertGreater(libero["punteggio"], legato["punteggio"])

    def test_la_finestra_e_configurabile(self):
        s = EccellenzaScorer(base="rimini", finestra="dicembre")
        r = s.score(opp(opportunity_type="prestito", current_club="Riccione"))
        self.assertEqual(r["rivedere_a"], "dicembre")
        self.assertIn("dicembre", r["riassunto"])

    def test_la_lista_separa_chi_e_in_agenda(self):
        lista = [opp(current_club="Riccione"),
                 opp(current_club="Riccione", opportunity_type="prestito")]
        r = valuta_lista(lista, base="rimini")
        self.assertEqual(len(r["valutati"]), 2)
        self.assertEqual(len(r["da_seguire"]), 1)
        self.assertEqual(r["da_seguire"][0]["ecc_rivedere_a"], "gennaio")


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
