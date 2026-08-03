#!/usr/bin/env python3
"""
Test offline dello strato watch (ARCH-002 Fase 2) e della cache condizionale.

Due domande, entrambe senza rete:
  1. `seen.py` sa distinguere "contenuto nuovo" da "stessa roba ripubblicata"?
  2. una seconda run consecutiva sugli stessi giocatori fa 304 e zero LLM?
     (è il criterio di uscita della Fase 2)

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_watch -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import enricher_tm
from src.enricher_tm import TransfermarktEnricher
from src.metrics import reset_metrics
from src.watch import SeenStore, content_key, normalize_content, watch_enabled

TM_PAGE = """
<html><body>
Cosimo Patierno - Profilo giocatore
Nato il: 03/05/2006 (20)
Posizione: Attaccante centrale
Squadra attuale: Avellino
Piede: destro
Valore di mercato: 900 mila &euro;
</body></html>
"""

TM_URL = "https://www.transfermarkt.it/cosimo-patierno/profil/spieler/340000"


class SeenStoreTestCase(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OB1_WATCH", None)
        self.store = SeenStore(":memory:")
        self.addCleanup(self.store.close)

    def test_first_sighting_is_an_event_the_second_is_not(self):
        self.assertTrue(self.store.see("https://x.test/a", "testo dell'articolo"))
        self.assertFalse(self.store.see("https://x.test/a", "testo dell'articolo"))
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.info(content_key("https://x.test/a",
                                                     "testo dell'articolo"))["times_seen"], 2)

    def test_republished_identical_article_is_not_an_event(self):
        """Stesso testo, spaziatura e maiuscole diverse: non è una notizia nuova."""
        self.assertTrue(self.store.see("https://x.test/a", "Il  giovane   attaccante ha firmato."))
        self.assertFalse(self.store.see("https://x.test/a", "il giovane attaccante ha firmato."))

    def test_tracking_parameters_do_not_create_a_fake_event(self):
        self.assertTrue(self.store.see("https://x.test/a", "contenuto"))
        self.assertFalse(self.store.see("https://x.test/a?utm_source=twitter", "contenuto"))
        self.assertFalse(self.store.see("https://x.test/a?fbclid=abc123", "contenuto"))

    def test_updated_page_is_an_event(self):
        self.assertTrue(self.store.see(TM_URL, "valore 900 mila"))
        self.assertTrue(self.store.see(TM_URL, "valore 1,2 mln"))
        self.assertEqual(self.store.count(), 2)

    def test_same_content_from_another_url_is_recognised_as_recirculated(self):
        testo = "Il difensore classe 2006 passa in prestito."
        self.store.see("https://tuttoc.test/a", testo)
        self.assertTrue(self.store.seen_content(testo))
        self.assertTrue(self.store.see("https://aggregatore.test/copia", testo))

    def test_see_many_returns_only_the_new_ones(self):
        batch = [("https://x.test/1", "uno"), ("https://x.test/2", "due")]
        self.assertEqual(self.store.see_many(batch), ["https://x.test/1", "https://x.test/2"])
        batch.append(("https://x.test/3", "tre"))
        self.assertEqual(self.store.see_many(batch), ["https://x.test/3"])

    def test_prune_removes_only_old_rows(self):
        self.store.see("https://x.test/a", "contenuto")
        self.assertEqual(self.store.prune(60), 0)
        with self.store.conn:
            self.store.conn.execute("UPDATE seen SET last_seen = '2020-01-01T00:00:00+00:00'")
        self.assertEqual(self.store.prune(60), 1)
        self.assertEqual(self.store.count(), 0)

    def test_watch_can_be_switched_off(self):
        """OB1_WATCH=0: tutto sembra nuovo, come prima di ARCH-002."""
        os.environ["OB1_WATCH"] = "0"
        self.addCleanup(lambda: os.environ.pop("OB1_WATCH", None))
        self.assertFalse(watch_enabled())
        self.assertTrue(self.store.see("https://x.test/a", "contenuto"))
        self.assertTrue(self.store.see("https://x.test/a", "contenuto"))

    def test_normalize_content_is_stable(self):
        self.assertEqual(normalize_content("  Ciao\n\tMondo  "), "ciao mondo")
        self.assertEqual(normalize_content(None), "")


class _FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class _FakeTMServer:
    """
    Un Transfermarkt finto che rispetta le richieste condizionali: risponde 200
    con ETag la prima volta, 304 quando il client rimanda quell'ETag.
    """

    def __init__(self, etag='W/"tm-v1"', body=TM_PAGE):
        self.etag = etag
        self.body = body
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        headers = headers or {}
        self.calls.append({"url": url, "if_none_match": headers.get("If-None-Match")})
        if headers.get("If-None-Match") == self.etag:
            return _FakeResponse(304, "", {"ETag": self.etag})
        return _FakeResponse(200, self.body, {"ETag": self.etag,
                                              "Last-Modified": "Sun, 03 Aug 2026 05:00:00 GMT"})


class ConditionalFetchTestCase(unittest.TestCase):
    def setUp(self):
        for var in ("GEMINI_API_KEY", "SERPER_API_KEY", "TAVILY_API_KEY",
                    "OB1_LLM_MODE", "OB1_ETAG"):
            os.environ.pop(var, None)
        os.environ["GROQ_API_KEY"] = "gsk_" + "x" * 24
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        for name, value in (("TM_URL_CACHE", Path(self.tmp.name) / "tm_urls.json"),
                            ("TM_ETAG_CACHE", Path(self.tmp.name) / "tm_etags.json")):
            p = mock.patch.object(enricher_tm, name, value)
            p.start()
            self.addCleanup(p.stop)

        for name, value in (("has_any_llm", True), ("describe_stack", "test-stack"),
                            ("llm_source_label", "Enrichment:groq")):
            p = mock.patch.object(enricher_tm, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)

        # Nessuna ricerca reale: l'URL TM arriva dalla cache
        p = mock.patch.object(enricher_tm, "free_web_search",
                              return_value=("duckduckgo", [{"url": TM_URL, "content": ""}]))
        p.start()
        self.addCleanup(p.stop)

        self.llm = mock.patch.object(enricher_tm, "llm_complete_json", return_value={})
        self.llm_mock = self.llm.start()
        self.addCleanup(self.llm.stop)

        self.server = _FakeTMServer()
        reset_metrics()

    def _enricher(self):
        e = TransfermarktEnricher()
        e.session = self.server
        return e

    def test_first_fetch_is_200_and_stores_the_validator(self):
        e = self._enricher()
        data = e.enrich_player_free("Cosimo Patierno")
        self.assertEqual(data.get("birth_date"), "2006-05-03")
        self.assertFalse(e.last_unchanged)
        self.assertEqual(e._etags[TM_URL]["etag"], 'W/"tm-v1"')

    def test_second_run_is_304_and_costs_no_llm_call(self):
        """Criterio di uscita ARCH-002 Fase 2, in miniatura."""
        first = self._enricher()
        first.enrich_player_free("Cosimo Patierno")
        self.llm_mock.reset_mock()

        second = self._enricher()          # nuovo processo: rilegge gli ETag da disco
        data = second.enrich_player_free("Cosimo Patierno")

        self.assertEqual(self.server.calls[-1]["if_none_match"], 'W/"tm-v1"')
        self.assertTrue(second.last_unchanged)
        self.assertEqual(data, {})
        self.llm_mock.assert_not_called()

    def test_a_304_never_falls_back_to_the_paid_path(self):
        """Contenuto invariato non deve mai innescare il grounding a consumo."""
        first = self._enricher()
        first.enrich_player_free("Cosimo Patierno")

        second = self._enricher()
        grounded = mock.patch.object(second, "enrich_player_grounded",
                                     return_value={"birth_date": "2006-05-03"})
        grounded_mock = grounded.start()
        self.addCleanup(grounded.stop)
        second.gemini_disabled = False
        second.mode = "free_first"

        self.assertEqual(second.enrich_player("Cosimo Patierno"), {})
        grounded_mock.assert_not_called()

    def test_changed_page_is_fetched_and_parsed_again(self):
        first = self._enricher()
        first.enrich_player_free("Cosimo Patierno")

        self.server.etag = 'W/"tm-v2"'
        self.server.body = TM_PAGE.replace("Avellino", "US Cremonese")
        second = self._enricher()
        data = second.enrich_player_free("Cosimo Patierno")

        self.assertFalse(second.last_unchanged)
        self.assertEqual(data.get("current_club"), "US Cremonese")

    def test_metrics_count_the_304_as_a_saved_fetch(self):
        reset_metrics()
        self._enricher().enrich_player_free("Cosimo Patierno")
        self._enricher().enrich_player_free("Cosimo Patierno")
        from src.metrics import get_metrics
        m = get_metrics()
        self.assertEqual(m.fetches, 2)
        self.assertEqual(m.fetches_304, 1)
        self.assertEqual(m.fetch_304_ratio, 0.5)

    def test_etag_can_be_switched_off(self):
        """OB1_ETAG=0: nessuna richiesta condizionale, comportamento pre-Fase 2."""
        self._enricher().enrich_player_free("Cosimo Patierno")
        os.environ["OB1_ETAG"] = "0"
        self.addCleanup(lambda: os.environ.pop("OB1_ETAG", None))
        e = self._enricher()
        e.enrich_player_free("Cosimo Patierno")
        self.assertIsNone(self.server.calls[-1]["if_none_match"])
        self.assertFalse(e.last_unchanged)

    def test_pages_without_validators_still_work(self):
        """Un server che non manda ETag non deve rompere niente."""
        class _NoValidators(_FakeTMServer):
            def get(self, url, headers=None, timeout=None):
                self.calls.append({"url": url, "if_none_match": (headers or {}).get("If-None-Match")})
                return _FakeResponse(200, self.body, {})

        self.server = _NoValidators()
        e = self._enricher()
        data = e.enrich_player_free("Cosimo Patierno")
        self.assertEqual(data.get("birth_date"), "2006-05-03")
        self.assertNotIn(TM_URL, e._etags)

    def test_http_error_is_not_confused_with_unchanged(self):
        class _Forbidden(_FakeTMServer):
            def get(self, url, headers=None, timeout=None):
                self.calls.append({"url": url, "if_none_match": None})
                return _FakeResponse(403, "", {})

        self.server = _Forbidden()
        e = self._enricher()
        result = e.fetch_page(TM_URL)
        self.assertEqual(result.status, 403)
        self.assertFalse(result.unchanged)
        self.assertEqual(result.text, "")


class ExitCriterionPhase2TestCase(ConditionalFetchTestCase):
    """
    Criterio di uscita ARCH-002 Fase 2, alla lettera:
    «una seconda run consecutiva sugli stessi giocatori fa ≥80% di 304
    e 0 chiamate LLM».
    """

    def test_second_consecutive_run_is_all_304_and_zero_llm(self):
        from src.metrics import get_metrics

        squadra = ["Cosimo Patierno", "Sergej Levak", "Andrea Rossi",
                   "Marco Bianchi", "Luca Verdi"]
        urls = {n: f"https://www.transfermarkt.it/{n.lower().replace(' ', '-')}"
                   f"/profil/spieler/{i}" for i, n in enumerate(squadra, 1)}

        class _MultiPlayerTM(_FakeTMServer):
            """Un ETag per URL, come farebbe il TM vero."""
            def get(self, url, headers=None, timeout=None):
                headers = headers or {}
                etag = f'W/"{url[-3:]}"'
                self.calls.append({"url": url, "if_none_match": headers.get("If-None-Match")})
                if headers.get("If-None-Match") == etag:
                    return _FakeResponse(304, "", {"ETag": etag})
                return _FakeResponse(200, TM_PAGE, {"ETag": etag})

        def _search_for(name, *a, **kw):
            return ("duckduckgo", [{"url": urls[name.split(" profilo")[0]], "content": ""}])

        with mock.patch.object(enricher_tm, "free_web_search",
                               side_effect=lambda q, **kw: _search_for(q)):
            # --- prima run: tutto nuovo, si paga il fetch pieno
            self.server = _MultiPlayerTM()
            reset_metrics()
            first = self._enricher()
            for name in squadra:
                first.enrich_player_free(name)
            run1 = get_metrics()
            self.assertEqual(run1.fetches, len(squadra))
            self.assertEqual(run1.fetches_304, 0)

            # --- seconda run: stesso processo? no. Nuova istanza, ETag da disco.
            reset_metrics()
            second = self._enricher()
            self.llm_mock.reset_mock()
            for name in squadra:
                second.enrich_player_free(name)
            run2 = get_metrics()

        self.assertEqual(run2.fetches, len(squadra))
        self.assertGreaterEqual(run2.fetch_304_ratio, 0.8,
                                f"solo {run2.fetches_304}/{run2.fetches} 304")
        self.assertEqual(run2.llm_calls, 0)
        self.llm_mock.assert_not_called()

    def test_a_page_that_changed_still_gets_re_enriched_in_the_second_run(self):
        """Il 304 non deve diventare cecità: se cambia, si rilegge."""
        self._enricher().enrich_player_free("Cosimo Patierno")
        self.server.etag = 'W/"tm-v2"'
        self.server.body = TM_PAGE.replace("900 mila", "1,20 mln")
        data = self._enricher().enrich_player_free("Cosimo Patierno")
        self.assertEqual(data.get("market_value_eur"), 1_200_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
