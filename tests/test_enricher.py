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

TM_URL = "https://www.transfermarkt.it/cosimo-patierno/profil/spieler/340000"


class EnricherTestCase(unittest.TestCase):
    def setUp(self):
        for var in ("GEMINI_API_KEY", "SERPER_API_KEY", "TAVILY_API_KEY", "OB1_LLM_MODE"):
            os.environ.pop(var, None)
        os.environ["GROQ_API_KEY"] = "gsk_" + "x" * 24  # unica chiave configurata

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

    def build(self, page_text=TM_PAGE, search_url=TM_URL):
        enricher = TransfermarktEnricher()
        enricher.fetch_page = fetched(page_text)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
