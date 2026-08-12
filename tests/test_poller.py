#!/usr/bin/env python3
"""
Test del poller feed (ARCH-002 Fase 3). Nessuna rete: sessione HTTP finta.

Il criterio di uscita della fase è qui sotto come comportamento, non come
promessa: un giro senza notizie nuove non produce eventi e non costa chiamate.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_poller -v
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.watch.poller import (FeedPoller, Item, Source, load_sources,
                              parse_feed, poll_new_items)
from src.watch.seen import SeenStore

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>TuttoC</title>
  <item>
    <title>Avellino, preso Patierno a parametro zero</title>
    <link>https://www.tuttoc.com/avellino-patierno</link>
    <description>L'attaccante firma dopo la rescissione</description>
    <pubDate>{recent}</pubDate>
  </item>
  <item>
    <title>Cremonese, si muove Tosi</title>
    <link>https://www.tuttoc.com/cremonese-tosi</link>
    <description>Il giovane difensore piace in Serie C</description>
    <pubDate>{recent}</pubDate>
  </item>
  <item>
    <title>Articolo vecchissimo</title>
    <link>https://www.tuttoc.com/vecchio</link>
    <description>Roba dell'anno scorso</description>
    <pubDate>{old}</pubDate>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Un titolo Atom</title>
    <link href="https://esempio.it/atom-1"/>
    <summary>Sommario</summary>
    <updated>{recent_iso}</updated>
  </entry>
</feed>"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.tuttomercatoweb.com/serie-c/mercato-avellino-colpo</loc>
    <lastmod>{recent_iso}</lastmod>
  </url>
</urlset>"""


def _rfc822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


NOW = datetime.now(timezone.utc)
RSS_BODY = RSS.format(recent=_rfc822(NOW - timedelta(hours=3)),
                      old=_rfc822(NOW - timedelta(days=90)))
ATOM_BODY = ATOM.format(recent_iso=(NOW - timedelta(hours=2)).isoformat())
SITEMAP_BODY = SITEMAP.format(recent_iso=(NOW - timedelta(hours=1)).isoformat())


class FakeResponse:
    def __init__(self, status=200, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


class FakeSession:
    """Registra gli header ricevuti: è lì che si vede la richiesta condizionale."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}})
        return self.script.pop(0) if self.script else FakeResponse(500)


class PollerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = Source(id="tuttoc", url="https://www.tuttoc.com/rss",
                             league_id="italy_serie_c_d")

    def poller(self, script):
        return FeedPoller(etag_path=self.root / "etags.json",
                          session=FakeSession(script))


class TestParsing(unittest.TestCase):
    def test_rss_items(self):
        items = parse_feed(RSS_BODY, "tuttoc")
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].url, "https://www.tuttoc.com/avellino-patierno")
        self.assertIn("Patierno", items[0].title)
        self.assertIn("rescissione", items[0].summary)
        self.assertEqual(items[0].source_id, "tuttoc")

    def test_atom_link_is_an_attribute_not_text(self):
        items = parse_feed(ATOM_BODY, "x")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://esempio.it/atom-1")

    def test_sitemap_urls_and_slug_title(self):
        items = parse_feed(SITEMAP_BODY, "tmw")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].url.endswith("mercato-avellino-colpo"))
        self.assertEqual(items[0].title, "Mercato avellino colpo")

    def test_malformed_xml_returns_nothing(self):
        self.assertEqual(parse_feed("<rss><item><title>rotto"), [])
        self.assertEqual(parse_feed(""), [])
        self.assertEqual(parse_feed("non è xml"), [])

    def test_item_content_excludes_the_url(self):
        """L'hash deve cambiare col contenuto, non con un ?utm_source diverso."""
        a = Item(url="https://x.it/a?utm_source=fb", title="T", summary="S")
        b = Item(url="https://x.it/a", title="T", summary="S")
        self.assertEqual(a.content, b.content)


class TestConditionalRequests(PollerTestCase):
    def test_first_poll_stores_the_validators(self):
        p = self.poller([FakeResponse(200, RSS_BODY, {"ETag": 'W/"abc"',
                                                      "Last-Modified": "Mon, 03 Aug 2026 10:00:00 GMT"})])
        result = p.poll(self.source)
        self.assertEqual(result.status, 200)
        self.assertFalse(result.unchanged)
        p.save()
        self.assertIn("abc", (self.root / "etags.json").read_text(encoding="utf-8"))

    def test_second_poll_sends_if_none_match(self):
        session = FakeSession([
            FakeResponse(200, RSS_BODY, {"ETag": 'W/"abc"'}),
            FakeResponse(304),
        ])
        p = FeedPoller(etag_path=self.root / "etags.json", session=session)
        p.poll(self.source)
        result = p.poll(self.source)
        self.assertEqual(session.calls[1]["headers"].get("If-None-Match"), 'W/"abc"')
        self.assertTrue(result.unchanged)
        self.assertEqual(result.items, [])

    def test_validators_survive_a_new_process(self):
        """
        La CI è stateless: se i validatori non sopravvivono al processo, ogni
        run riscarica tutto e il 304 non arriva mai.
        """
        p1 = self.poller([FakeResponse(200, RSS_BODY, {"ETag": 'W/"abc"'})])
        p1.poll(self.source)
        p1.save()

        session2 = FakeSession([FakeResponse(304)])
        p2 = FeedPoller(etag_path=self.root / "etags.json", session=session2)
        result = p2.poll(self.source)
        self.assertEqual(session2.calls[0]["headers"].get("If-None-Match"), 'W/"abc"')
        self.assertTrue(result.unchanged)

    def test_stale_items_are_dropped(self):
        p = self.poller([FakeResponse(200, RSS_BODY)])
        result = p.poll(self.source)
        urls = [i.url for i in result.items]
        self.assertNotIn("https://www.tuttoc.com/vecchio", urls)
        self.assertEqual(len(result.items), 2)

    def test_network_error_is_not_fatal(self):
        import requests

        class Boom:
            def get(self, *a, **kw):
                raise requests.RequestException("dns")

        p = FeedPoller(etag_path=self.root / "etags.json", session=Boom())
        result = p.poll(self.source)
        self.assertFalse(result.ok)
        self.assertIn("RequestException", result.error)

    def test_http_error_is_reported_not_raised(self):
        p = self.poller([FakeResponse(503, "")])
        result = p.poll(self.source)
        self.assertEqual(result.status, 503)
        self.assertFalse(result.ok)


class TestNewItemsOnly(PollerTestCase):
    def store(self):
        s = SeenStore(self.root / "seen.db")
        self.addCleanup(s.close)
        return s

    def test_first_run_returns_items_second_returns_none(self):
        """
        Il criterio della Fase 3: due giri consecutivi sullo stesso contenuto
        producono eventi solo la prima volta.
        """
        seen = self.store()
        p1 = self.poller([FakeResponse(200, RSS_BODY)])
        first = poll_new_items([self.source], seen=seen, poller=p1, verbose=False)
        self.assertEqual(len(first), 2)

        p2 = self.poller([FakeResponse(200, RSS_BODY)])
        second = poll_new_items([self.source], seen=seen, poller=p2, verbose=False)
        self.assertEqual(second, [])

    def test_304_produces_no_events(self):
        seen = self.store()
        p = self.poller([FakeResponse(304)])
        self.assertEqual(poll_new_items([self.source], seen=seen, poller=p, verbose=False), [])

    def test_republished_article_with_tracking_param_is_not_an_event(self):
        seen = self.store()
        p1 = self.poller([FakeResponse(200, RSS_BODY)])
        poll_new_items([self.source], seen=seen, poller=p1, verbose=False)

        tracked = RSS_BODY.replace("https://www.tuttoc.com/avellino-patierno",
                                   "https://www.tuttoc.com/avellino-patierno?utm_source=twitter")
        p2 = self.poller([FakeResponse(200, tracked)])
        again = poll_new_items([self.source], seen=seen, poller=p2, verbose=False)
        self.assertEqual(again, [])

    def test_a_genuinely_new_article_comes_through(self):
        seen = self.store()
        p1 = self.poller([FakeResponse(200, RSS_BODY)])
        poll_new_items([self.source], seen=seen, poller=p1, verbose=False)

        extra = RSS_BODY.replace("</channel>", """<item>
            <title>Nuovo colpo per il Cesena</title>
            <link>https://www.tuttoc.com/cesena-nuovo</link>
            <description>Arriva un centrocampista</description>
            <pubDate>%s</pubDate></item></channel>""" % _rfc822(NOW))
        p2 = self.poller([FakeResponse(200, extra)])
        fresh = poll_new_items([self.source], seen=seen, poller=p2, verbose=False)
        self.assertEqual([i.url for i in fresh], ["https://www.tuttoc.com/cesena-nuovo"])

    def test_no_sources_means_no_work(self):
        self.assertEqual(poll_new_items([], verbose=False), [])


class TestConfig(unittest.TestCase):
    def test_real_feeds_config_is_loadable(self):
        sources = load_sources(Path(__file__).resolve().parent.parent / "config" / "feeds.yaml",
                               league_id="italy_serie_c_d")
        self.assertGreaterEqual(len(sources), 5)
        for s in sources:
            self.assertTrue(s.url.startswith("https://"), s.url)
            self.assertIn(s.kind, ("rss", "atom", "sitemap"))

    def test_missing_config_is_not_an_error(self):
        self.assertEqual(load_sources(Path("/non/esiste.yaml")), [])

    def test_league_filter(self):
        cfg = Path(__file__).resolve().parent.parent / "config" / "feeds.yaml"
        self.assertEqual(load_sources(cfg, league_id="lega_inesistente"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
