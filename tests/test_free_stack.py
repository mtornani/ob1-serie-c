#!/usr/bin/env python3
"""
Test offline della catena free (ricerca + LLM). Nessuna rete: i provider
sono sostituiti da fake.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_free_stack -v
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import free_stack

DDG_HTML = """
<div class="result">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.transfermarkt.it%2Fcosimo-patierno%2Fprofil%2Fspieler%2F340000">
    Cosimo Patierno - Profilo giocatore
  </a>
  <a class="result__snippet">Attaccante, Avellino, valore di mercato 900 mila &euro;</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://www.tuttoc.com/articolo">Serie C mercato</a>
  <a class="result__snippet">Le ultime dal mercato di Lega Pro</a>
</div>
"""


class FreeStackTestCase(unittest.TestCase):
    def setUp(self):
        for var in ("OB1_SEARCH_MODE", "OB1_LLM_MODE", "SERPER_API_KEY",
                    "TAVILY_API_KEY", "GEMINI_API_KEY", "SEARXNG_INSTANCES"):
            os.environ.pop(var, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(free_stack, "SEARCH_CACHE_DIR",
                                    Path(self.tmp.name) / "search_cache")
        patcher.start()
        self.addCleanup(patcher.stop)


class TestSearchChain(FreeStackTestCase):
    def test_duckduckgo_needs_no_key(self):
        resp = mock.Mock(status_code=200, text=DDG_HTML)
        with mock.patch.object(free_stack.requests, "post", return_value=resp):
            results = free_stack.search_duckduckgo("Patierno transfermarkt")
        self.assertEqual(len(results), 2)
        # il link DDG /l/?uddg= va srotolato nell'URL vero
        self.assertTrue(results[0]["url"].startswith("https://www.transfermarkt.it/"))
        self.assertIn("Patierno", results[0]["title"])
        self.assertIn("Avellino", results[0]["content"])
        self.assertEqual(results[0]["source"], "duckduckgo")

    def test_free_search_uses_ddg_first_without_any_key(self):
        with mock.patch.object(free_stack, "search_duckduckgo",
                               return_value=[{"title": "t", "url": "https://x.it",
                                              "content": "c", "source": "duckduckgo"}]) as ddg:
            source, results = free_stack.free_web_search("query")
        self.assertEqual(source, "duckduckgo")
        self.assertEqual(len(results), 1)
        ddg.assert_called_once()

    def test_falls_through_to_searxng_when_ddg_empty(self):
        with mock.patch.object(free_stack, "search_duckduckgo", return_value=[]), \
             mock.patch.object(free_stack, "search_searxng",
                               return_value=[{"title": "t", "url": "https://x.it",
                                              "content": "", "source": "searxng"}]):
            source, results = free_stack.free_web_search("query")
        self.assertEqual(source, "searxng")

    def test_serper_is_last_and_optional(self):
        """Senza SERPER_API_KEY la catena funziona lo stesso."""
        with mock.patch.object(free_stack, "search_duckduckgo", return_value=[]), \
             mock.patch.object(free_stack, "search_searxng", return_value=[]):
            source, results = free_stack.free_web_search("query")
        self.assertEqual(source, "none")
        self.assertEqual(results, [])

    def test_search_mode_serper_puts_serper_first(self):
        os.environ["OB1_SEARCH_MODE"] = "serper"
        os.environ["SERPER_API_KEY"] = "k" * 20
        with mock.patch.object(free_stack, "search_serper",
                               return_value=[{"title": "t", "url": "https://x.it",
                                              "content": "", "source": "serper"}]) as serper, \
             mock.patch.object(free_stack, "search_duckduckgo") as ddg:
            source, _ = free_stack.free_web_search("query")
        self.assertEqual(source, "serper")
        serper.assert_called_once()
        ddg.assert_not_called()

    def test_second_search_hits_the_cache(self):
        payload = [{"title": "t", "url": "https://x.it", "content": "", "source": "duckduckgo"}]
        with mock.patch.object(free_stack, "search_duckduckgo", return_value=payload) as ddg:
            free_stack.free_web_search("stessa query")
            source, results = free_stack.free_web_search("stessa query")
        self.assertEqual(ddg.call_count, 1)
        self.assertTrue(source.startswith("cache:"))
        self.assertEqual(results, payload)

    def test_broken_provider_does_not_break_the_chain(self):
        with mock.patch.object(free_stack, "search_duckduckgo", side_effect=RuntimeError("boom")), \
             mock.patch.object(free_stack, "search_searxng",
                               return_value=[{"title": "t", "url": "https://x.it",
                                              "content": "", "source": "searxng"}]):
            source, _ = free_stack.free_web_search("query")
        self.assertEqual(source, "searxng")

    def test_domain_bias_becomes_site_operator(self):
        self.assertEqual(free_stack._with_domains("q", ["transfermarkt.it"]),
                         "site:transfermarkt.it q")
        self.assertIn(" OR ", free_stack._with_domains("q", ["a.it", "b.it"]))

    def test_tavily_non_200_is_logged_not_silent(self):
        """
        DEV_LOG: 'Fallback enrichment Tavily -> 432 Client Error', aperto
        mai indagato. Causa: un non-200 tornava [] senza loggare nulla, e
        free_web_search logga solo sulle eccezioni (che qui non scattano
        mai) — l'errore era strutturalmente invisibile. Non riproduce il 432
        (serve la chiave vera), ma garantisce che il prossimo non lo sia.
        """
        os.environ["TAVILY_API_KEY"] = "k" * 20
        resp = mock.Mock(status_code=432, text="quota esaurita o chiave scaduta")
        buf = io.StringIO()
        with mock.patch.object(free_stack.requests, "post", return_value=resp), \
             redirect_stdout(buf):
            results = free_stack.search_tavily("query")
        self.assertEqual(results, [])
        self.assertIn("432", buf.getvalue())
        self.assertIn("tavily", buf.getvalue())

    def test_serper_non_200_is_logged_not_silent(self):
        os.environ["SERPER_API_KEY"] = "k" * 20
        resp = mock.Mock(status_code=403, text="forbidden")
        buf = io.StringIO()
        with mock.patch.object(free_stack.requests, "post", return_value=resp), \
             redirect_stdout(buf):
            results = free_stack.search_serper("query")
        self.assertEqual(results, [])
        self.assertIn("403", buf.getvalue())


class TestDDGBlocking(FreeStackTestCase):
    """DDG risponde 202 + pagina anti-bot sotto carico: non è "zero risultati"."""

    def setUp(self):
        super().setUp()
        free_stack._ddg_state.update({"last_call": 0.0, "blocked_until": 0.0})
        free_stack._searxng_dead.clear()
        p = mock.patch.object(free_stack, "_DDG_MIN_INTERVAL_S", 0)
        p.start()
        self.addCleanup(p.stop)

    def test_202_anomaly_is_recognised_as_a_block(self):
        resp = mock.Mock(status_code=202, text="<html>anomaly detected</html>")
        with mock.patch.object(free_stack.requests, "post", return_value=resp):
            self.assertEqual(free_stack.search_duckduckgo("q"), [])
        self.assertTrue(free_stack.ddg_blocked())

    def test_blocked_ddg_is_not_called_again(self):
        resp = mock.Mock(status_code=202, text="anomaly")
        with mock.patch.object(free_stack.requests, "post", return_value=resp) as post:
            free_stack.search_duckduckgo("q1")
            free_stack.search_duckduckgo("q2")
        self.assertEqual(post.call_count, 1)  # niente martellamento su un blocco noto

    def test_block_is_reported_as_blocked_not_as_empty(self):
        resp = mock.Mock(status_code=202, text="anomaly")
        with mock.patch.object(free_stack.requests, "post", return_value=resp), \
             mock.patch.object(free_stack, "search_searxng", return_value=[]):
            source, results = free_stack.free_web_search("q")
        self.assertEqual(source, "blocked")  # non "none": la ricerca non è avvenuta
        self.assertEqual(results, [])

    def test_block_falls_through_to_the_next_provider(self):
        resp = mock.Mock(status_code=202, text="anomaly")
        with mock.patch.object(free_stack.requests, "post", return_value=resp), \
             mock.patch.object(free_stack, "search_searxng",
                               return_value=[{"title": "t", "url": "https://x.it",
                                              "content": "", "source": "searxng"}]):
            source, _ = free_stack.free_web_search("q")
        self.assertEqual(source, "searxng")

    def test_dead_searxng_instance_is_dropped_for_the_run(self):
        resp = mock.Mock(status_code=403, headers={"content-type": "text/html"})
        os.environ["SEARXNG_INSTANCES"] = "https://a.test,https://b.test"
        with mock.patch.object(free_stack.requests, "get", return_value=resp) as get:
            free_stack.search_searxng("q1")
            free_stack.search_searxng("q2")
        self.assertEqual(get.call_count, 2)  # 2 istanze provate una volta, poi escluse


class TestLLMChain(FreeStackTestCase):
    def test_has_any_llm_true_with_groq_only(self):
        """Il caso del memo: solo GROQ_API_KEY, niente Gemini, niente Serper."""
        with mock.patch.object(free_stack, "free_llm_routes", return_value=["groq/llama"]):
            self.assertTrue(free_stack.has_any_llm())
            self.assertTrue(free_stack.has_any_llm(free_only=True))

    def test_has_any_llm_false_when_nothing_configured(self):
        with mock.patch.object(free_stack, "free_llm_routes", return_value=[]):
            self.assertFalse(free_stack.has_any_llm())

    def test_gemini_alone_is_enough_unless_free_only(self):
        os.environ["GEMINI_API_KEY"] = "g" * 20
        with mock.patch.object(free_stack, "free_llm_routes", return_value=[]):
            self.assertTrue(free_stack.has_any_llm())
            self.assertFalse(free_stack.has_any_llm(free_only=True))

    def test_free_route_used_before_gemini(self):
        gw = mock.Mock()
        gw.complete_json.return_value = mock.Mock(ok=True, data={"n": 1}, raw='{"n": 1}')
        with mock.patch.object(free_stack, "_gateway", return_value=gw), \
             mock.patch.object(free_stack, "_gemini_complete") as gem:
            out = free_stack.llm_complete_json("sys", "user")
        self.assertEqual(out, {"n": 1})
        gem.assert_not_called()
        # la rotta gemini è esclusa dal gateway: la gestisce il client nativo
        self.assertEqual(gw.complete_json.call_args.kwargs["exclude_providers"], {"gemini"})

    def test_gemini_used_when_free_routes_fail(self):
        gw = mock.Mock()
        gw.complete_json.return_value = mock.Mock(ok=False, data=None, raw="", errors=["ko"])
        os.environ["GEMINI_API_KEY"] = "g" * 20
        with mock.patch.object(free_stack, "_gateway", return_value=gw), \
             mock.patch.object(free_stack, "_gemini_complete", return_value='{"n": 2}'):
            out = free_stack.llm_complete_json("sys", "user")
        self.assertEqual(out, {"n": 2})

    def test_free_only_never_calls_gemini(self):
        os.environ["OB1_LLM_MODE"] = "free_only"
        os.environ["GEMINI_API_KEY"] = "g" * 20
        gw = mock.Mock()
        gw.complete_json.return_value = mock.Mock(ok=False, data=None, raw="", errors=["ko"])
        with mock.patch.object(free_stack, "_gateway", return_value=gw), \
             mock.patch.object(free_stack, "_gemini_complete") as gem:
            out = free_stack.llm_complete_json("sys", "user")
        self.assertIsNone(out)
        gem.assert_not_called()

    def test_gemini_first_inverts_the_order(self):
        os.environ["OB1_LLM_MODE"] = "gemini_first"
        os.environ["GEMINI_API_KEY"] = "g" * 20
        gw = mock.Mock()
        with mock.patch.object(free_stack, "_gateway", return_value=gw), \
             mock.patch.object(free_stack, "_gemini_complete", return_value='{"n": 3}'):
            out = free_stack.llm_complete_json("sys", "user")
        self.assertEqual(out, {"n": 3})
        gw.complete_json.assert_not_called()

    def test_gemini_model_default_is_not_the_deprecated_one(self):
        os.environ["GEMINI_API_KEY"] = "g" * 20
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(text="{}")
        free_stack._gemini_complete("sys", "user", gemini_client=client)
        self.assertEqual(client.models.generate_content.call_args.kwargs["model"],
                         "gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main(verbosity=2)
