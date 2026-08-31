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

from src.quality_gate import (apply_gate, assess_identity, count_distinct_sources,
                              e_redirect_di_ricerca, normalize_age,
                              reconcile_opportunity_type, _parsa_contract_expires)


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


class TestRedirectDiRicercaNonSonoFonti(unittest.TestCase):
    """
    Un redirect di grounding Gemini è il nostro motore di ricerca che dice
    dove ha guardato, e scade. Misurato il 31 ago 2026: 41 delle 54 schede
    pubbliche lo avevano come fonte, otto provati rispondevano tutti 404, e
    ognuna dichiarava "2 fonti" — il redirect faceva da seconda accanto a
    Transfermarkt. Il verdetto del gate era giusto lo stesso (il profilo TM
    corrobora da solo), ma il CONTEGGIO era gonfiato.
    """

    REDIRECT = ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
                "AUZIYQHrLv5bj1wpkK5cAolSjgBvxX2id6riBmDeUG9F")

    def test_riconosce_il_redirect(self):
        self.assertTrue(e_redirect_di_ricerca(self.REDIRECT))
        self.assertTrue(e_redirect_di_ricerca("https://vertexaisearch.google.com/x"))
        self.assertFalse(e_redirect_di_ricerca("https://tuttoc.com/notizia"))
        self.assertFalse(e_redirect_di_ricerca(""))
        self.assertFalse(e_redirect_di_ricerca(None))

    def test_redirect_non_conta_come_fonte(self):
        o = opp(source_url=self.REDIRECT,
                tm_url="https://www.transfermarkt.it/tizio/profil/spieler/1")
        self.assertEqual(count_distinct_sources(o), 1)   # solo Transfermarkt

    def test_redirect_dentro_la_lista_sources(self):
        o = opp(source_url="https://tuttoc.com/notizia",
                sources=[{"url": self.REDIRECT}, {"url": "https://tuttoc.com/notizia"}])
        self.assertEqual(count_distinct_sources(o), 1)

    def test_il_profilo_tm_corrobora_lo_stesso(self):
        # è il punto: il gate non perde nessuno, cambia solo cosa dichiara
        g = assess_identity(opp(source_url=self.REDIRECT,
                                tm_url="https://www.transfermarkt.it/tizio/profil/spieler/1"))
        self.assertEqual(g["n_sources"], 1)
        self.assertTrue(g["corroborated"])
        self.assertTrue(g["publishable"])

    def test_due_fonti_vere_contano_ancora_due(self):
        o = opp(source_url="https://tuttoc.com/x",
                sources=[{"url": "https://tuttomercatoweb.com/y"}])
        self.assertEqual(count_distinct_sources(o), 2)


class TestReconcileOpportunityType(unittest.TestCase):
    """
    Caso vero, trovato dall'utente su Transfermarkt: Sergej Levak segnato
    'svincolato' (da un thread di forum) ma con contract_expires 2030-06-30
    arrivato dopo dall'enrichment TM, mai riconciliato prima di questo fix.
    """

    def test_svincolato_con_contratto_futuro_riclassificato_a_mercato(self):
        o = opp(opportunity_type="svincolato", contract_expires="2030-06-30",
                 current_club="Atalanta U23")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "mercato")
        self.assertEqual(out["type_reconciled_from"], "svincolato")

    def test_rescissione_con_contratto_futuro_riclassificata_anche_lei(self):
        o = opp(opportunity_type="rescissione", contract_expires="2027-06-30")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "mercato")

    def test_svincolato_senza_contratto_non_tocco(self):
        o = opp(opportunity_type="svincolato")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "svincolato")
        self.assertNotIn("type_reconciled_from", out)

    def test_svincolato_con_contratto_gia_scaduto_resta_svincolato(self):
        o = opp(opportunity_type="svincolato", contract_expires="2020-06-30")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "svincolato")

    def test_prestito_non_e_toccato_dalla_riconciliazione(self):
        # la riconciliazione riguarda solo affermazioni di "libero" — un
        # prestito con contratto futuro col club di prestito non è una
        # contraddizione, è normale
        o = opp(opportunity_type="prestito", contract_expires="2027-06-30")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "prestito")

    def test_data_non_valida_non_esplode(self):
        o = opp(opportunity_type="svincolato", contract_expires="chissà")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "svincolato")

    def test_contratto_formato_italiano_riconosciuto(self):
        """
        Caso vero, trovato il 31 ago 2026: Donnarumma in cima alla dashboard
        pubblica come 'svincolato' con contract_expires='30/06/2030' — un
        contratto fino al 2030 non riconciliato perché scritto in GG/MM/AAAA
        (il formato che src/tm_verify.py scrive davvero, non l'ISO che questa
        funzione si aspettava). La riconciliazione lo leggeva come data non
        valida e lasciava passare la contraddizione intatta.
        """
        o = opp(opportunity_type="svincolato", contract_expires="30/06/2030",
                 current_club="Manchester City")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "mercato")
        self.assertEqual(out["type_reconciled_from"], "svincolato")

    def test_contratto_italiano_gia_scaduto_resta_svincolato(self):
        o = opp(opportunity_type="svincolato", contract_expires="30/06/2020")
        out = reconcile_opportunity_type(o)
        self.assertEqual(out["opportunity_type"], "svincolato")

    def test_parsa_contract_expires_entrambi_i_formati(self):
        self.assertEqual(_parsa_contract_expires("2030-06-30"),
                         _parsa_contract_expires("30/06/2030"))
        self.assertIsNone(_parsa_contract_expires("chissà"))

    def test_apply_gate_usa_il_tipo_riconciliato(self):
        o = opp(opportunity_type="svincolato", contract_expires="2030-06-30",
                 current_club="Atalanta U23", tm_url=
                 "https://www.transfermarkt.it/sergej-levak/profil/spieler/892165")
        out = apply_gate(o)
        self.assertEqual(out["opportunity_type"], "mercato")
        self.assertTrue(out["publishable"])  # il fix non deve rompere il gate


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
