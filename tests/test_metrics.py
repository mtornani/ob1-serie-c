#!/usr/bin/env python3
"""
Test offline delle metriche ARCH-002 Fase 1.

Il punto: `costo_per_fatto` deve essere calcolabile, persistibile e confrontabile
nel tempo — soprattutto nei casi limite (zero fatti, storico corto, file
corrotto), perché è il numero su cui si decideranno le fasi successive.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_metrics -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.metrics import (RunMetrics, get_metrics, load_history, regression_check,
                         reset_metrics)


class CostPerFactTestCase(unittest.TestCase):
    def test_cost_per_fact_counts_searches_llm_and_fetches(self):
        m = RunMetrics()
        for _ in range(4):
            m.search("duckduckgo")
        for _ in range(2):
            m.llm_call("groq:llama-3.3-70b", tokens=1000)
        for _ in range(6):
            m.fetch(200)
        m.fact("birth_date")
        m.fact("current_club")
        m.fact("market_value")
        m.fact("age")

        self.assertEqual(m.operations, 12)
        self.assertEqual(m.facts, 4)
        self.assertEqual(m.cost_per_fact, 3.0)

    def test_zero_facts_is_undefined_not_infinite(self):
        """Una run che non scopre niente non ha costo infinito: indefinito."""
        m = RunMetrics()
        m.search("duckduckgo")
        m.fetch(200)
        self.assertIsNone(m.cost_per_fact)
        self.assertIsNone(m.usd_per_fact)
        self.assertIn("n/d", m.summary())
        self.assertIsNone(m.to_dict()["cost_per_fact"])

    def test_zero_operations_and_zero_facts_do_not_raise(self):
        m = RunMetrics()
        self.assertEqual(m.operations, 0)
        self.assertIsNone(m.cost_per_fact)
        self.assertIsNone(m.fetch_304_ratio)
        self.assertIsNone(m.llm_cache_hit_ratio)
        json.dumps(m.to_dict())  # serializzabile anche vuota

    def test_304_and_cache_do_not_count_as_new_cost(self):
        """
        Un 304 è un fetch (la richiesta parte) ma non produce lavoro a valle;
        una ricerca da cache non è una ricerca. La distinzione è tutto il punto
        della Fase 2, quindi va misurata separatamente.
        """
        m = RunMetrics()
        m.fetch(200)
        for _ in range(9):
            m.fetch(304)
        m.search_cached()
        m.llm_cache_hit()
        m.fact("current_club")

        self.assertEqual(m.fetches, 10)
        self.assertEqual(m.fetches_304, 9)
        self.assertEqual(m.fetch_304_ratio, 0.9)
        self.assertEqual(m.searches, 0)          # la cache non è una ricerca
        self.assertEqual(m.llm_cache_hit_ratio, 1.0)

    def test_failed_fetch_is_counted_apart(self):
        m = RunMetrics()
        m.fetch(403)
        m.fetch(0)          # errore di rete
        m.fetch(200)
        self.assertEqual(m.fetches, 3)
        self.assertEqual(m.fetches_failed, 2)
        self.assertEqual(m.fetches_304, 0)

    def test_only_paid_searches_cost_money(self):
        m = RunMetrics()
        m.search("duckduckgo")
        m.search("searxng")
        self.assertEqual(m.cost_usd, 0.0)
        m.search("serper")
        self.assertAlmostEqual(m.cost_usd, 0.001)
        m.fact("birth_date")
        self.assertAlmostEqual(m.usd_per_fact, 0.001)


class PersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "metrics.jsonl"
        os.environ.pop("OB1_METRICS", None)

    def test_write_appends_one_line_per_run(self):
        for i in range(3):
            m = RunMetrics()
            m.search("duckduckgo")
            m.fact("birth_date", i + 1)
            self.assertTrue(m.write(self.path))
        rows = [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["facts"] for r in rows], [1, 2, 3])

    def test_metrics_can_be_disabled_without_touching_the_pipeline(self):
        os.environ["OB1_METRICS"] = "0"
        self.addCleanup(lambda: os.environ.pop("OB1_METRICS", None))
        m = RunMetrics()
        m.fact("age")
        self.assertFalse(m.write(self.path))
        self.assertFalse(self.path.exists())
        self.assertEqual(m.facts, 1)   # i contatori girano lo stesso

    def test_write_failure_never_raises(self):
        """Le metriche non possono far fallire una pipeline che ha funzionato."""
        m = RunMetrics()
        m.fact("age")
        impossible = Path(self.tmp.name) / "file.txt" / "nested" / "metrics.jsonl"
        Path(self.tmp.name, "file.txt").write_text("non sono una cartella")
        self.assertFalse(m.write(impossible))

    def test_history_survives_corrupted_lines(self):
        self.path.write_text(
            json.dumps({"cost_per_fact": 2.0, "facts": 1}) + "\n"
            + "{ questo non e' json\n"
            + "\n"
            + json.dumps({"cost_per_fact": 3.0, "facts": 2}) + "\n",
            encoding="utf-8")
        rows = load_history(self.path)
        self.assertEqual([r["cost_per_fact"] for r in rows], [2.0, 3.0])

    def test_history_of_missing_file_is_empty(self):
        self.assertEqual(load_history(Path(self.tmp.name) / "assente.jsonl"), [])


class RegressionCheckTestCase(unittest.TestCase):
    def _hist(self, values):
        return [{"cost_per_fact": v, "facts": 1} for v in values]

    def test_no_alarm_when_cost_is_stable(self):
        self.assertIsNone(regression_check(self._hist([3.0, 3.2, 2.9, 3.1])))

    def test_alarm_when_cost_per_fact_doubles(self):
        msg = regression_check(self._hist([3.0, 3.0, 3.0, 6.5]))
        self.assertIsNotNone(msg)
        self.assertIn("6.5", msg)

    def test_no_alarm_without_enough_history(self):
        """Con due run non si sa ancora cosa sia normale: meglio tacere."""
        self.assertIsNone(regression_check(self._hist([1.0, 9.0])))

    def test_runs_without_facts_do_not_poison_the_baseline(self):
        history = [{"cost_per_fact": None, "facts": 0}] * 5 + self._hist([3.0, 3.0, 3.1])
        self.assertIsNone(regression_check(history))

    def test_improvement_is_never_an_alarm(self):
        self.assertIsNone(regression_check(self._hist([10.0, 9.0, 11.0, 2.0])))


class ExitCriterionPhase1TestCase(unittest.TestCase):
    """
    Criterio di uscita ARCH-002 Fase 1, verificato per davvero:
    «una run stampa costo_per_fatto e il valore finisce in data/metrics.jsonl».
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "data" / "opportunities.json").write_text(json.dumps([
            {"id": 1, "player_name": "Cosimo Patierno"},
            {"id": 2, "player_name": "Sergej Levak"},
        ]), encoding="utf-8")
        os.environ.pop("OB1_METRICS", None)
        reset_metrics()

    def test_a_run_prints_the_cost_per_fact_and_persists_it(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        import scripts.run_enrichment as runner

        metrics_file = self.root / "data" / "metrics.jsonl"

        class _FakeEnricher:
            """Due giocatori: uno arricchito (2 fatti), uno no. Zero rete."""
            stalled = False

            def enrich_players_batch(self, names):
                m = get_metrics()
                m.search("duckduckgo")
                m.fetch(200)
                m.llm_call("groq:llama-3.3-70b", tokens=900)
                return {names[0]: {"birth_date": "2006-05-03", "current_club": "Avellino"},
                        names[1]: {}}

        with mock.patch.object(runner, "DATA_FILE", self.root / "data" / "opportunities.json"), \
             mock.patch.object(runner, "DATA_FILE_DOCS", self.root / "docs" / "data.json"), \
             mock.patch.object(runner, "METRICS_FILE", metrics_file), \
             mock.patch.object(runner, "TransfermarktEnricher", _FakeEnricher), \
             mock.patch.object(runner, "DELAY_BETWEEN_BATCHES", 0):
            buf = io.StringIO()
            with redirect_stdout(buf):
                runner.main()
            out = buf.getvalue()

        self.assertIn("costo_per_fatto", out)
        self.assertTrue(metrics_file.exists(), "la riga di metriche non è stata scritta")
        row = json.loads(metrics_file.read_text(encoding="utf-8").splitlines()[-1])
        # 2 fatti nuovi (birth_date + current_club) + age derivata = 3
        self.assertEqual(row["facts"], 3)
        self.assertEqual(row["operations"], 3)     # 1 ricerca + 1 llm + 1 fetch
        self.assertEqual(row["cost_per_fact"], 1.0)
        self.assertEqual(row["players_touched"], 2)

    def test_a_run_with_nothing_to_do_still_leaves_a_row(self):
        """Un buco nella serie storica non si recupera più: si scrive comunque."""
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        import scripts.run_enrichment as runner

        (self.root / "data" / "opportunities.json").write_text(json.dumps([
            {"id": 1, "player_name": "Cosimo Patierno", "tm_enriched": True},
        ]), encoding="utf-8")
        metrics_file = self.root / "data" / "metrics.jsonl"
        with mock.patch.object(runner, "DATA_FILE", self.root / "data" / "opportunities.json"), \
             mock.patch.object(runner, "METRICS_FILE", metrics_file):
            with redirect_stdout(io.StringIO()):
                runner.main()
        row = json.loads(metrics_file.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(row["facts"], 0)
        self.assertIsNone(row["cost_per_fact"])


class SingletonTestCase(unittest.TestCase):
    def test_get_metrics_is_shared_and_resettable(self):
        reset_metrics()
        get_metrics().fact("age")
        self.assertEqual(get_metrics().facts, 1)
        self.assertEqual(reset_metrics().facts, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
