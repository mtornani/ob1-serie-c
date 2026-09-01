#!/usr/bin/env python3
"""
Test offline dell'enricher free-first.

Il punto del memo: l'arricchimento deve funzionare con la sola GROQ_API_KEY —
senza Serper e senza Gemini. I mock sono su free_web_search / llm_complete_json,
non su requests.post.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_enricher -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import enricher_tm
from src.enricher_tm import FetchResult, TransfermarktEnricher, parse_tm_text


def fetched(text: str = "", status: int = 200, unchanged: bool = False) -> mock.Mock:
    """
    Il fetch ora dice anche COM'È andata (200 / 304 / errore), perché un 304 non
    è un fetch vuoto: è contenuto invariato. I test mockano quel livello.
    """
    return mock.Mock(return_value=FetchResult(text, status, unchanged))

TM_PAGE = """
Cosimo Patierno - Profilo giocatore
Nato il: 03/05/2006 (20)
Posizione: Attaccante centrale
Club attuale: Avellino
Piede: destro
Valore di mercato: 900 mila €
Contratto fino a: 30.06.2027
"""

TM_URL = "https://www.transfermarkt.it/cosimo-patierno/profil/spieler/283352"


class EnricherTestCase(unittest.TestCase):
    def setUp(self):
        for var in ("GEMINI_API_KEY", "SERPER_API_KEY", "TAVILY_API_KEY", "OB1_LLM_MODE"):
            os.environ.pop(var, None)
        os.environ["GROQ_API_KEY"] = "gsk_" + "x" * 24  # unica chiave configurata
        # La ricerca interna di TM è l'unico percorso che apre una connessione
        # vera. Spenta qui con l'interruttore di produzione: senza, ogni test
        # che costruisce l'enricher da sé pagherebbe un timeout di rete.
        os.environ["OB1_TM_SITE_SEARCH"] = "0"
        self.addCleanup(os.environ.pop, "OB1_TM_SITE_SEARCH", None)
        # Stesso motivo: sports-skills parla con un backend vero. Spento di
        # default, chi lo testa lo riaccende e mocka sports_skills_football.
        os.environ["OB1_SPORTS_SKILLS"] = "0"
        self.addCleanup(os.environ.pop, "OB1_SPORTS_SKILLS", None)
        # Stessa ragione per la verifica d'identita': apre il profilo VERO su
        # Transfermarkt via Jina Reader. Senza spegnerla questi test farebbero
        # una richiesta di rete reale per ogni URL (misurato: suite da 0,4s a
        # 8s) e fallirebbero quando la rete non c'e'. Cio' che la verifica fa
        # e' testato in src/tm_verify.py con una pagina reale salvata.
        os.environ["OB1_TM_VERIFY"] = "0"
        self.addCleanup(os.environ.pop, "OB1_TM_VERIFY", None)

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Nessun test deve poter scrivere dentro data/ del repo.
        for _name, _file in (("TM_URL_CACHE", "tm_urls.json"),
                             ("TM_ETAG_CACHE", "tm_etags.json")):
            p = mock.patch.object(enricher_tm, _name, Path(self.tmp.name) / _file)
            p.start()
            self.addCleanup(p.stop)

        # Il gateway reale non deve essere interrogato nei test
        p2 = mock.patch.object(enricher_tm, "has_any_llm", return_value=True)
        p2.start()
        self.addCleanup(p2.stop)
        p3 = mock.patch.object(enricher_tm, "describe_stack", return_value="test-stack")
        p3.start()
        self.addCleanup(p3.stop)
        p4 = mock.patch.object(enricher_tm, "llm_source_label", return_value="Enrichment:groq")
        p4.start()
        self.addCleanup(p4.stop)
        # Default: nessuna chiamata LLM reale esce dai test (i singoli test
        # ripatchano dove il comportamento dell'LLM conta).
        p5 = mock.patch.object(enricher_tm, "llm_complete_json", return_value=None)
        p5.start()
        self.addCleanup(p5.stop)

    def build(self, page_text=TM_PAGE, search_url=TM_URL, site_search=""):
        enricher = TransfermarktEnricher()
        enricher.fetch_page = fetched(page_text)
        # La ricerca interna di TM parla con la rete vera: spenta di default,
        # così i test restano offline e quello che si esercita qui resta il
        # percorso del motore di ricerca. Chi la testa la riaccende da sé.
        enricher._tm_url_from_site_search = mock.Mock(return_value=site_search)
        self.search = mock.Mock(return_value=("duckduckgo", [
            {"title": "Patierno", "url": search_url, "content": "snippet", "source": "duckduckgo"},
        ]))
        enricher_tm.free_web_search = self.search
        return enricher


class TestConstruction(EnricherTestCase):
    def test_works_with_groq_only(self):
        """Niente GEMINI_API_KEY, niente SERPER_API_KEY: deve costruire lo stesso."""
        enricher = TransfermarktEnricher()
        self.assertIsNone(enricher.gemini_client)
        self.assertTrue(enricher.gemini_disabled)

    def test_raises_only_when_no_llm_at_all(self):
        with mock.patch.object(enricher_tm, "has_any_llm", return_value=False):
            with self.assertRaises(ValueError) as ctx:
                TransfermarktEnricher()
        self.assertIn("GROQ_API_KEY", str(ctx.exception))

    def test_stalled_is_false_while_free_routes_exist(self):
        enricher = TransfermarktEnricher()
        with mock.patch.object(enricher_tm, "has_any_llm", return_value=True):
            self.assertFalse(enricher.stalled)
        with mock.patch.object(enricher_tm, "has_any_llm", return_value=False):
            self.assertTrue(enricher.stalled)


class TestFreeEnrichment(EnricherTestCase):
    def test_regex_only_when_page_is_complete(self):
        enricher = self.build()
        with mock.patch.object(enricher_tm, "llm_complete_json") as llm:
            data = enricher.enrich_player_free("Cosimo Patierno")
        llm.assert_not_called()  # dati completi: nessuna chiamata LLM
        self.assertEqual(data["birth_date"], "2006-05-03")
        self.assertEqual(data["current_club"], "Avellino")
        self.assertEqual(data["tm_url"], TM_URL)
        self.assertEqual(data["enrichment_source"], "Enrichment:regex")

    def test_llm_fills_only_the_gaps(self):
        enricher = self.build(page_text="Pagina povera, nessun dato utile.")
        with mock.patch.object(enricher_tm, "llm_complete_json",
                               return_value={"birth_date": "2005-01-02",
                                             "current_club": "Ascoli",
                                             "appearances": 12}) as llm:
            data = enricher.enrich_player_free("Tizio Caio")
        llm.assert_called_once()
        self.assertEqual(data["current_club"], "Ascoli")
        self.assertEqual(data["appearances"], 12)
        self.assertEqual(data["enrichment_source"], "Enrichment:groq")

    def test_deterministic_data_is_never_overwritten_by_the_llm(self):
        """Regex vince: l'LLM riempie i buchi, non corregge ciò che è certo."""
        page = "Nato il: 03/05/2006 (20)\nAltro testo senza club."
        enricher = self.build(page_text=page)
        with mock.patch.object(enricher_tm, "llm_complete_json",
                               return_value={"birth_date": "1999-12-31",
                                             "current_club": "Avellino"}):
            data = enricher.enrich_player_free("Cosimo Patierno")
        self.assertEqual(data["birth_date"], "2006-05-03")  # dal regex, non dall'LLM
        self.assertEqual(data["current_club"], "Avellino")  # buco riempito dall'LLM

    def test_tm_url_is_cached_after_first_lookup(self):
        enricher = self.build()
        enricher.enrich_player_free("Cosimo Patierno")
        enricher.enrich_player_free("Cosimo Patierno")
        self.assertEqual(self.search.call_count, 1)  # la ricerca si paga una volta
        self.assertIn("cosimo patierno", enricher._tm_urls)

    def test_no_results_returns_empty_without_crashing(self):
        enricher = TransfermarktEnricher()
        enricher.fetch_page = fetched("", status=403)
        enricher_tm.free_web_search = mock.Mock(return_value=("none", []))
        self.assertEqual(enricher.enrich_player_free("Ignoto"), {})

    def test_snippet_used_when_page_fetch_is_blocked(self):
        """TM risponde 403: si ripiega sullo snippet della ricerca."""
        enricher = TransfermarktEnricher()
        enricher.fetch_page = fetched("", status=403)
        enricher_tm.free_web_search = mock.Mock(return_value=("duckduckgo", [
            {"title": "Patierno", "url": TM_URL, "content": TM_PAGE, "source": "duckduckgo"},
        ]))
        with mock.patch.object(enricher_tm, "llm_complete_json", return_value=None):
            data = enricher.enrich_player_free("Cosimo Patierno")
        self.assertEqual(data["current_club"], "Avellino")


class TestConditionalFetch(EnricherTestCase):
    def test_304_skips_both_parsing_and_the_llm(self):
        """
        Contenuto invariato: niente regex, niente inferenza, niente scrittura.
        È il risparmio della Fase 2 espresso come comportamento, non come numero.
        """
        enricher = self.build()
        enricher.fetch_page = fetched("", status=304, unchanged=True)
        with mock.patch.object(enricher_tm, "parse_tm_text") as parse, \
             mock.patch.object(enricher_tm, "llm_complete_json") as llm:
            data = enricher.enrich_player_free("Cosimo Patierno")
        self.assertEqual(data, {})
        self.assertTrue(enricher.last_unchanged)
        parse.assert_not_called()
        llm.assert_not_called()


class TestBatch(EnricherTestCase):
    def test_batch_uses_the_free_path_without_gemini(self):
        enricher = self.build()
        with mock.patch.object(enricher_tm, "llm_complete_json", return_value=None):
            out = enricher.enrich_players_batch(["Cosimo Patierno", "Cosimo Patierno"])
        self.assertEqual(len(out), 1)  # dedup per nome nel dict di ritorno
        self.assertEqual(out["Cosimo Patierno"]["current_club"], "Avellino")

    def test_grounded_batch_not_attempted_without_client(self):
        enricher = self.build()
        enricher._enrich_batch_grounded = mock.Mock(return_value={})
        with mock.patch.object(enricher_tm, "llm_complete_json", return_value=None):
            enricher.enrich_players_batch(["Cosimo Patierno"])
        enricher._enrich_batch_grounded.assert_not_called()

    def test_empty_names_is_a_noop(self):
        self.assertEqual(TransfermarktEnricher().enrich_players_batch([]), {})


class TestParseTmText(unittest.TestCase):
    # Layout reale della pagina TM ripulita dai tag: label e valore su righe
    # diverse. Prima di questo caso il club non veniva mai estratto.
    TM_STRIPPED = """Cosimo Patierno
 Piede:
 destro
 Procuratore:
 Gio'sport
 Squadra attuale:


 US Avellino 1912

 In rosa da:
 10/07/2023
 Scadenza:
 30/06/2027
"""

    def test_club_on_a_following_line(self):
        data = parse_tm_text(self.TM_STRIPPED)
        self.assertEqual(data["current_club"], "US Avellino 1912")

    def test_club_label_is_not_mistaken_for_a_value(self):
        data = parse_tm_text("Squadra attuale:\n\nIn rosa da:\n10/07/2023")
        self.assertIsNone(data.get("current_club"))

    def test_markdown_club_still_works(self):
        """Il formato raw markdown di Tavily non deve regredire."""
        md = "[Atalanta U23](/atalanta-u23/startseite/verein/54365) Nato il: 03/05/2006"
        self.assertEqual(parse_tm_text(md)["current_club"], "Atalanta U23")

    def test_italian_page(self):
        data = parse_tm_text(TM_PAGE, TM_URL)
        self.assertEqual(data["birth_date"], "2006-05-03")
        self.assertEqual(data["current_club"], "Avellino")
        self.assertEqual(data["tm_url"], TM_URL)

    def test_empty_input(self):
        self.assertEqual(parse_tm_text(""), {})


class SiteSearchTestCase(EnricherTestCase):
    """
    Ricerca interna di Transfermarkt: toglie di mezzo il motore terzo, che è il
    punto della catena che si fa bloccare. Due comportamenti non ovvi da fissare.
    """

    def _enricher(self, response):
        os.environ.pop("OB1_TM_SITE_SEARCH", None)   # rotta accesa
        enricher = TransfermarktEnricher()
        enricher.session = mock.Mock()
        enricher.session.get = mock.Mock(return_value=response)
        return enricher

    @staticmethod
    def _resp(status=200, text="", content_type="text/html"):
        return mock.Mock(status_code=status, text=text,
                         headers={"content-type": content_type})

    def test_usa_il_canonical_quando_tm_reindirizza_al_profilo(self):
        """
        Con un solo risultato esatto TM salta l'elenco e serve il profilo. La
        pagina contiene i link ai compagni di squadra: prendere il primo href
        arricchirebbe in silenzio il giocatore sbagliato — il caso peggiore,
        perché il dato sembra buono.
        """
        page = (f'<link rel="canonical" href="{TM_URL}">'
                '<div class="info-table__content">Nato il: 03/05/2006</div>'
                '<a href="/altro-giocatore/profil/spieler/999999">compagno</a>')
        enricher = self._enricher(self._resp(text=page))
        self.assertEqual(enricher._tm_url_from_site_search("Cosimo Patierno"), TM_URL)

    def test_usa_il_primo_risultato_quando_e_un_elenco(self):
        page = ('<table class="items">'
                f'<a href="/cosimo-patierno/profil/spieler/283352">Patierno</a>'
                '<a href="/altro/profil/spieler/999999">Altro</a></table>')
        self.assertEqual(
            self._enricher(self._resp(text=page))._tm_url_from_site_search("Patierno"),
            TM_URL)

    def test_200_senza_profilo_lo_dice_invece_di_tornare_muto(self):
        """
        Il bug reale: in produzione questo caso tornava '' senza una riga di
        log, indistinguibile da "provato e non trovato per davvero" — 20
        giocatori su 20, zero traccia. Ora almeno si vede.
        """
        page = '<html><body>pagina di consenso cookie, nessun risultato</body></html>'
        with mock.patch("builtins.print") as p:
            result = self._enricher(self._resp(text=page))._tm_url_from_site_search("Tizio")
        self.assertEqual(result, "")
        self.assertTrue(any("[TM SEARCH]" in str(c) for c in p.call_args_list))

    def test_200_con_corpo_vuoto_lo_dice_anche_lui(self):
        """
        Il ramo che il primo giro di diagnostica aveva dimenticato: 'if not
        page: return \"\"' restituiva muto ESATTAMENTE come il caso sopra, e
        in produzione — verificato su un run reale dopo aver mergiato il
        primo fix — è rimasto silenzioso lo stesso. Un 200 con corpo vuoto è
        la forma più leggera di blocco anti-bot: rispondere presto e non dare
        niente, verosimile verso un IP di datacenter come quello dei runner.
        """
        with mock.patch("builtins.print") as p:
            result = self._enricher(self._resp(text=""))._tm_url_from_site_search("Tizio")
        self.assertEqual(result, "")
        self.assertTrue(any("[TM SEARCH]" in str(c) and "VUOTO" in str(c)
                            for c in p.call_args_list))

    def test_un_blocco_spegne_la_rotta_per_tutta_la_run(self):
        """Se TM blocca l'IP li blocca tutti: insistere costa un timeout a testa."""
        enricher = self._enricher(self._resp(status=403))
        self.assertEqual(enricher._tm_url_from_site_search("Tizio"), "")
        self.assertTrue(enricher._tm_search_dead)
        self.assertEqual(enricher._tm_url_from_site_search("Caio"), "")
        self.assertEqual(enricher.session.get.call_count, 1)   # non ha riprovato

    def test_qualunque_status_non_200_spegne_il_circuito(self):
        """
        Il bug reale, in produzione: una tupla chiusa (403, 429, 503) lasciava
        passare in silenzio qualunque altro status — un 500, un 520 di
        Cloudflare, un rate-limit non standard. Tre run reali hanno mostrato
        "dead=False" su tutti e 20 i giocatori e nessun'altra riga: il codice
        veniva raggiunto, uno status sconosciuto usciva senza stampare e
        senza fermare niente, 20 volte su 20. Ora qualunque non-200 ferma
        il circuito, non solo i tre codici che avevo previsto io.
        """
        with mock.patch("builtins.print") as p:
            enricher = self._enricher(self._resp(status=520))
            result = enricher._tm_url_from_site_search("Tizio")
        self.assertEqual(result, "")
        self.assertTrue(enricher._tm_search_dead)
        self.assertTrue(any("HTTP 520" in str(c) for c in p.call_args_list))

    def test_un_errore_di_rete_spegne_la_rotta_ma_non_esplode(self):
        enricher = self._enricher(None)
        enricher.session.get = mock.Mock(side_effect=OSError("timed out"))
        self.assertEqual(enricher._tm_url_from_site_search("Tizio"), "")
        self.assertTrue(enricher._tm_search_dead)

    def test_linterruttore_di_produzione_la_tiene_spenta(self):
        os.environ["OB1_TM_SITE_SEARCH"] = "0"
        enricher = TransfermarktEnricher()
        enricher.session = mock.Mock()
        self.assertEqual(enricher._tm_url_from_site_search("Tizio"), "")
        enricher.session.get.assert_not_called()

    def test_il_motore_di_ricerca_resta_il_ripiego(self):
        """Se TM non risolve, il percorso vecchio deve ancora provarci."""
        enricher = self.build(site_search="")
        enricher.enrich_player_free("Cosimo Patierno")
        self.assertEqual(self.search.call_count, 1)

    def test_se_tm_risolve_il_motore_di_ricerca_non_si_chiama(self):
        enricher = self.build(site_search=TM_URL)
        with mock.patch.object(enricher_tm, "llm_complete_json", return_value=None):
            enricher.enrich_player_free("Cosimo Patierno")
        self.search.assert_not_called()
        self.assertEqual(enricher._tm_urls["cosimo patierno"], TM_URL)


class SportsSkillsTestCase(EnricherTestCase):
    """
    Percorso via il pacchetto community sports-skills — riempi-buchi
    facoltativo, non deve mai far fallire l'arricchimento se manca, se non
    trova il giocatore, o se il cognome non combacia.
    """

    def _enricher_with(self, search_result=None, profile_result=None):
        # Il patch di sports_skills_football deve partire PRIMA di costruire
        # l'enricher: __init__ legge `sports_skills_football is None` una
        # volta sola e la congela in self._sports_skills_dead. Costruendo
        # prima e patchando dopo (l'ordine di prima), quel controllo vedeva
        # il modulo VERO, non il finto — e se il pacchetto reale non e'
        # installato (successo il 1 set 2026, container senza
        # `pip install -r requirements.txt`: sports_skills_football e' None
        # a livello di modulo) l'enricher nasceva gia' "morto" e ogni test
        # di questa classe falliva per un motivo che non aveva niente a che
        # fare col comportamento sotto test. In produzione il pacchetto e'
        # sempre installato (requirements.txt + CI), quindi il difetto era
        # latente: mascherato ogni volta che il pacchetto vero capitava di
        # esserci.
        os.environ.pop("OB1_SPORTS_SKILLS", None)  # rotta accesa
        fake = mock.Mock()
        fake.search_player = mock.Mock(return_value=search_result or {
            "status": True, "data": {"results": []}, "message": "",
        })
        fake.get_player_profile = mock.Mock(return_value=profile_result or {})
        self.patched = mock.patch.object(enricher_tm, "sports_skills_football", fake)
        self.patched.start()
        self.addCleanup(self.patched.stop)
        enricher = TransfermarktEnricher()
        return enricher

    def test_traccia_dingresso_incondizionata(self):
        """
        La lezione della saga TM_SEARCH (PR #38-41): un ramo silenzioso è
        indistinguibile da un ramo mai raggiunto. Verificato in produzione
        il 2026-08-17 - zero righe [SPORTS-SKILLS] nel log di un run reale,
        nessun modo di sapere se la funzione girava e non trovava nulla o
        se non veniva proprio chiamata. Ora stampa sempre, anche a vuoto.
        """
        with mock.patch("builtins.print") as p:
            enricher = self._enricher_with()
            enricher.enrich_player_sports_skills("Chiunque")
        self.assertTrue(any("[SPORTS-SKILLS] tentativo per" in str(c)
                            for c in p.call_args_list))
        self.assertTrue(any("nessun risultato" in str(c) for c in p.call_args_list))

    def test_pacchetto_non_installato_non_rompe_niente(self):
        """Import fallito -> sports_skills_football è None -> ramo spento."""
        with mock.patch.object(enricher_tm, "sports_skills_football", None):
            enricher = TransfermarktEnricher()
            self.assertTrue(enricher._sports_skills_dead)
            self.assertEqual(enricher.enrich_player_sports_skills("Cosimo Patierno"), {})

    def test_linterruttore_di_produzione_la_tiene_spenta(self):
        enricher = TransfermarktEnricher()  # OB1_SPORTS_SKILLS=0 da setUp
        self.assertTrue(enricher._sports_skills_dead)

    def test_nessun_risultato_torna_vuoto(self):
        enricher = self._enricher_with()
        self.assertEqual(enricher.enrich_player_sports_skills("Cosimo Patierno"), {})

    def test_cognome_diverso_viene_scartato(self):
        """
        Stesso principio del fix in ob1-scout/corroborate_v2.py: un nome di
        battesimo condiviso non basta a confermare la persona.
        """
        enricher = self._enricher_with(search_result={
            "status": True, "message": "",
            "data": {"results": [
                {"name": "Cosimo Bianchi", "tm_player_id": "1"},
            ]},
        })
        self.assertEqual(enricher.enrich_player_sports_skills("Cosimo Patierno"), {})

    def test_match_buono_restituisce_valore_di_mercato_e_club(self):
        enricher = self._enricher_with(
            search_result={"status": True, "message": "", "data": {"results": [
                {"name": "Sergej Levak", "tm_player_id": "892165"},
            ]}},
            profile_result={"status": True, "message": "", "data": {"player": {
                "market_value": {"value": 2800000, "formatted": "€2.80m",
                                  "club": "Atalanta U23"},
            }}},
        )
        data = enricher.enrich_player_sports_skills("Sergej Levak")
        self.assertEqual(data["market_value_eur"], 2800000)
        self.assertEqual(data["current_club"], "Atalanta U23")
        self.assertEqual(data["tm_player_id"], "892165")
        self.assertEqual(data["enrichment_source"], "Enrichment:sports-skills")
        self.assertIn("892165", data["tm_url"])

    def test_eccezione_spegne_la_rotta_ma_non_esplode(self):
        os.environ.pop("OB1_SPORTS_SKILLS", None)
        enricher = TransfermarktEnricher()
        fake = mock.Mock()
        fake.search_player = mock.Mock(side_effect=OSError("timed out"))
        with mock.patch.object(enricher_tm, "sports_skills_football", fake):
            self.assertEqual(enricher.enrich_player_sports_skills("Tizio"), {})
        self.assertTrue(enricher._sports_skills_dead)

    def test_riempie_i_buchi_ma_non_sovrascrive_il_regex(self):
        """Il dato dalla pagina TM vera vince sempre su quello di terzi."""
        enricher = self.build(site_search="")  # rotta TM diretta trova la pagina vera
        enricher.enrich_player_sports_skills = mock.Mock(return_value={
            "market_value_eur": 999, "current_club": "Club Sbagliato",
            "enrichment_source": "Enrichment:sports-skills",
        })
        with mock.patch.object(enricher_tm, "llm_complete_json", return_value=None):
            data = enricher.enrich_player_free("Cosimo Patierno")
        # TM_PAGE ha "Club attuale: Avellino" — il regex deve vincere
        self.assertEqual(data.get("current_club"), "Avellino")

    def test_riempie_quando_la_pagina_tm_non_ha_niente(self):
        enricher = self.build(site_search="", page_text="")
        enricher._tm_url_from_site_search = mock.Mock(return_value="")
        enricher_tm.free_web_search = mock.Mock(return_value=("duckduckgo", []))
        enricher.enrich_player_sports_skills = mock.Mock(return_value={
            "market_value_eur": 2800000, "current_club": "Atalanta U23",
            "tm_url": "https://www.transfermarkt.it/x/profil/spieler/892165",
            "enrichment_source": "Enrichment:sports-skills",
        })
        data = enricher.enrich_player_free("Sergej Levak")
        self.assertEqual(data.get("market_value_eur"), 2800000)
        self.assertEqual(data.get("enrichment_source"), "Enrichment:sports-skills")


if __name__ == "__main__":
    unittest.main(verbosity=2)
