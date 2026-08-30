#!/usr/bin/env python3
"""
Test offline del gateway LLM. Nessuna rete: il trasporto è iniettato.

    PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.cache import ResponseCache
from src.llm.gateway import LLMGateway, _parse_json, _parse_retry_after
from src.llm.ledger import QuotaLedger
from src.llm.registry import Registry

KEY_A = "sk-test-aaaaaaaaaaaaaaaaaaaa"
KEY_B = "sk-test-bbbbbbbbbbbbbbbbbbbb"

CONFIG = {
    "version": 1,
    "defaults": {"timeout_s": 5, "max_tokens": 256, "temperature": 0.0,
                 "cooldown_transient_s": 30, "fail_streak_limit": 2},
    "task_classes": {
        "extract": {"min_tier": "small", "max_input_chars": 500, "cache_ttl_h": 24},
        "reason": {"min_tier": "frontier", "max_input_chars": 500, "cache_ttl_h": 24},
    },
    "providers": [
        {
            "id": "primary", "base_url": "https://primary.test/v1",
            "api_key_env": "TEST_PRIMARY_KEY", "commercial_use": True,
            "trains_on_data": False, "limits": {"rpm": 5, "rpd": 3},
            "models": [{"name": "fast-1", "tier": "mid", "context": 8000,
                        "json_mode": True, "tasks": ["extract"], "priority": 10}],
        },
        {
            "id": "secondary", "base_url": "https://secondary.test/v1",
            "api_key_env": "TEST_SECONDARY_KEY", "commercial_use": True,
            "trains_on_data": True, "limits": {"rpm": 10},
            "models": [{"name": "big-1", "tier": "frontier", "context": 8000,
                        "json_mode": False, "tasks": ["extract", "reason"],
                        "priority": 20}],
        },
        {
            "id": "paidonly", "base_url": "https://paid.test/v1",
            "api_key_env": "TEST_SECONDARY_KEY", "commercial_use": True,
            "paid": True, "limits": {"rpm": 10},
            "models": [{"name": "paid-1", "tier": "frontier", "context": 8000,
                        "tasks": ["extract"], "priority": 999}],
        },
    ],
}


def ok_body(content, tokens=42):
    return {"choices": [{"message": {"content": content}}],
            "usage": {"total_tokens": tokens}}


class FakeTransport:
    """Risponde secondo uno scenario per host, e registra le chiamate."""

    def __init__(self, script):
        self.script = script  # host -> list[(status, body)] oppure (status, body)
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        host = url.split("/")[2]
        self.calls.append({"host": host, "model": payload["model"],
                           "payload": payload, "headers": headers})
        entry = self.script.get(host, (500, "no script"))
        if isinstance(entry, list):
            return entry.pop(0) if entry else (500, "script esaurito")
        return entry


class GatewayTestCase(unittest.TestCase):
    def setUp(self):
        os.environ["TEST_PRIMARY_KEY"] = KEY_A
        os.environ["TEST_SECONDARY_KEY"] = KEY_B
        for var in ("OB1_LLM_ALLOW_PAID", "OB1_LLM_COMMERCIAL_ONLY", "OB1_LLM_ALLOW_TRAINING"):
            os.environ.pop(var, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def build(self, script, **kw):
        gw = LLMGateway(
            registry=Registry(CONFIG),
            ledger=QuotaLedger(self.root / "ledger.json"),
            cache=ResponseCache(self.root / "cache", enabled=kw.pop("cache", True)),
            transport=FakeTransport(script),
            verbose=False,
            **kw,
        )
        return gw


class TestRouting(GatewayTestCase):
    def test_primary_wins_and_parses(self):
        gw = self.build({"primary.test": (200, ok_body('{"nome": "Rossi"}'))})
        res = gw.complete_json("extract", "estrai")
        self.assertTrue(res.ok)
        self.assertEqual(res.data["nome"], "Rossi")
        self.assertEqual(res.route, "primary/fast-1")
        self.assertEqual(res.tokens, 42)

    def test_failover_on_429(self):
        gw = self.build({
            "primary.test": (429, {"error": "rate limit exceeded"}),
            "secondary.test": (200, ok_body('{"ok": true}')),
        })
        res = gw.complete_json("extract", "estrai")
        self.assertTrue(res.ok)
        self.assertEqual(res.route, "secondary/big-1")
        # Il 429 "per minuto" chiude il bucket primary per il minuto corrente
        self.assertIsNotNone(gw.ledger.blocked_reason("primary:fast-1:0", {"rpm": 2}))

    def test_failover_on_broken_json(self):
        gw = self.build({
            "primary.test": (200, ok_body("non è json, mi dispiace")),
            "secondary.test": (200, ok_body('{"ok": 1}')),
        })
        res = gw.complete_json("extract", "estrai")
        self.assertTrue(res.ok)
        self.assertEqual(res.route, "secondary/big-1")

    def test_all_routes_down(self):
        gw = self.build({
            "primary.test": (500, "boom"),
            "secondary.test": (503, "overloaded"),
        })
        res = gw.complete_json("extract", "estrai")
        self.assertFalse(res.ok)
        self.assertFalse(bool(res))
        self.assertEqual(res.attempts, 2)
        self.assertEqual(gw.stats["failures"], 1)

    def test_tier_floor_filters_small_models(self):
        gw = self.build({"secondary.test": (200, ok_body('{"ok": 1}'))})
        # `reason` richiede tier frontier: primary (mid) non è eleggibile
        res = gw.complete_json("reason", "valuta")
        self.assertTrue(res.ok)
        self.assertEqual(res.route, "secondary/big-1")

    def test_paid_route_excluded_by_default(self):
        gw = self.build({
            "primary.test": (500, "boom"),
            "secondary.test": (500, "boom"),
            "paid.test": (200, ok_body('{"ok": 1}')),
        })
        res = gw.complete_json("extract", "estrai")
        self.assertFalse(res.ok)
        self.assertNotIn("paid.test", [c["host"] for c in gw.transport.calls])

    def test_paid_route_used_when_allowed(self):
        gw = self.build({
            "primary.test": (500, "boom"),
            "secondary.test": (500, "boom"),
            "paid.test": (200, ok_body('{"ok": 1}')),
        })
        gw.allow_paid = True
        res = gw.complete_json("extract", "estrai")
        self.assertTrue(res.ok)
        self.assertEqual(res.route, "paidonly/paid-1")

    def test_training_providers_excluded_when_disallowed(self):
        gw = self.build({"primary.test": (500, "boom"), "secondary.test": (200, ok_body("{}"))})
        gw.allow_training = False  # secondary ha trains_on_data: true
        res = gw.complete_json("extract", "estrai")
        self.assertFalse(res.ok)

    def test_json_mode_only_where_supported(self):
        gw = self.build({"primary.test": (200, ok_body("{}"))})
        gw.complete_json("extract", "estrai")
        self.assertIn("response_format", gw.transport.calls[0]["payload"])

    def test_auth_error_disables_bucket_for_a_day(self):
        gw = self.build({
            "primary.test": (401, "invalid api key"),
            "secondary.test": (200, ok_body("{}")),
        })
        gw.complete_json("extract", "estrai")
        reason = gw.ledger.blocked_reason("primary:fast-1:0", {})
        self.assertIn("cooldown", reason or "")

    def test_prompt_clamped_to_task_limit(self):
        gw = self.build({"primary.test": (200, ok_body("{}"))})
        gw.complete_json("extract", "x" * 5000)
        sent = gw.transport.calls[0]["payload"]["messages"][1]["content"]
        self.assertLessEqual(len(sent), 500 + 20)


class TestCache(GatewayTestCase):
    def test_second_identical_call_is_free(self):
        gw = self.build({"primary.test": [(200, ok_body('{"n": 1}'))]})
        first = gw.complete_json("extract", "stesso prompt")
        second = gw.complete_json("extract", "stesso prompt")
        self.assertTrue(first.ok and second.ok)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(len(gw.transport.calls), 1)  # una sola chiamata di rete
        self.assertEqual(second.data["n"], 1)

    def test_different_task_does_not_share_cache(self):
        gw = self.build({
            "primary.test": [(200, ok_body('{"n": 1}'))],
            "secondary.test": [(200, ok_body('{"n": 2}'))],
        })
        gw.complete_json("extract", "p")
        res = gw.complete_json("reason", "p")
        self.assertEqual(res.data["n"], 2)

    def test_expired_entry_is_refetched(self):
        import time as _time
        cache = ResponseCache(self.root / "cache")
        key = ResponseCache.key("extract", "p", "s")
        cache.put(key, {"raw": "{}", "route": "x"})
        entry_path = cache._path(key)
        stale = json.loads(entry_path.read_text(encoding="utf-8"))
        stale["stored_at"] = _time.time() - 7200  # due ore fa
        entry_path.write_text(json.dumps(stale), encoding="utf-8")
        self.assertIsNone(cache.get(key, ttl_h=1))
        self.assertIsNotNone(cache.get(key, ttl_h=24))

    def test_cache_can_be_disabled(self):
        gw = self.build({"primary.test": [(200, ok_body("{}")), (200, ok_body("{}"))]},
                        cache=False)
        gw.complete_json("extract", "p")
        gw.complete_json("extract", "p")
        self.assertEqual(len(gw.transport.calls), 2)


class TestLedger(GatewayTestCase):
    def test_rpd_cap_blocks_before_the_call(self):
        gw = self.build({"primary.test": (200, ok_body("{}")),
                         "secondary.test": (200, ok_body("{}"))})
        # rpd: 3 sul primary — la quarta deve uscire da secondary
        for i in range(4):
            gw.complete_json("extract", f"prompt {i}")
        hosts = [c["host"] for c in gw.transport.calls]
        self.assertEqual(hosts.count("primary.test"), 3)
        self.assertEqual(hosts[-1], "secondary.test")

    def test_counters_survive_process_restart(self):
        path = self.root / "ledger.json"
        led = QuotaLedger(path)
        led.record_success("prov:model:0", tokens=100)
        reloaded = QuotaLedger(path)
        self.assertIsNotNone(reloaded.blocked_reason("prov:model:0", {"rpd": 1}))

    def test_day_rollover_resets_counters(self):
        led = QuotaLedger(self.root / "ledger.json")
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        led.record_success("prov:model:0", tokens=100, now=yesterday)
        self.assertIsNone(led.blocked_reason("prov:model:0", {"rpd": 1}))

    def test_token_budget_respected(self):
        led = QuotaLedger(self.root / "ledger.json")
        led.record_success("prov:model:0", tokens=900)
        self.assertIsNotNone(led.blocked_reason("prov:model:0", {"tpd": 1000}, est_tokens=500))
        self.assertIsNone(led.blocked_reason("prov:model:0", {"tpd": 1000}, est_tokens=50))

    def test_daily_exhaustion_kills_bucket_for_the_day(self):
        led = QuotaLedger(self.root / "ledger.json")
        led.record_failure("prov:model:0", exhausted="day")
        self.assertIsNotNone(led.blocked_reason("prov:model:0", {"rpd": 1000}))

    def test_atomic_save_leaves_valid_json(self):
        path = self.root / "ledger.json"
        led = QuotaLedger(path)
        led.record_success("a:b:0", tokens=1)
        self.assertIn("buckets", json.loads(path.read_text(encoding="utf-8")))


class TestRateLimitHandling(GatewayTestCase):
    """Un 429 va interpretato, non indovinato: il provider dice quanto aspettare."""

    GROQ_TPD = ("Rate limit reached for model `llama-3.3-70b-versatile` in organization "
                "`org_x` service tier `on_demand` on tokens per day (TPD): Limit 100000, "
                "Used 99000, Requested 5000. Please try again in 3m59s.")
    GROQ_TPM = ("Rate limit reached ... on tokens per minute (TPM): Limit 12000, "
                "Used 11000, Requested 5000. Please try again in 24.5s.")

    def test_retry_after_is_parsed_from_the_body(self):
        self.assertEqual(_parse_retry_after(self.GROQ_TPM), 25)
        self.assertEqual(_parse_retry_after(self.GROQ_TPD), 240)
        self.assertEqual(_parse_retry_after("no hint here"), 0)

    def test_retry_after_wins_over_the_day_guess(self):
        """
        Il caso visto in produzione: 'tokens per day' + 'try again in 3m59s'.
        Prima spegneva la rotta fino a mezzanotte UTC — con una sola rotta free
        configurata, l'arricchimento si fermava per il resto della giornata.
        """
        gw = self.build({"primary.test": (429, {"error": {"message": self.GROQ_TPD}}),
                         "secondary.test": (200, ok_body("{}"))})
        gw.complete_json("extract", "p")
        reason = gw.ledger.blocked_reason("primary:fast-1:0", {})
        self.assertIn("cooldown", reason)
        cd = gw.ledger.snapshot()["buckets"]["primary:fast-1:0"]["cooldown_until"]
        delta = datetime.fromisoformat(cd) - datetime.now(timezone.utc)
        self.assertLess(delta.total_seconds(), 300)  # minuti, non ore

    def test_day_exhaustion_without_hint_waits_for_utc_midnight(self):
        gw = self.build({"primary.test": (429, {"error": "quota exceeded, requests per day"}),
                         "secondary.test": (200, ok_body("{}"))})
        gw.complete_json("extract", "p")
        cd = gw.ledger.snapshot()["buckets"]["primary:fast-1:0"]["cooldown_until"]
        midnight = datetime.fromisoformat(cd)
        self.assertEqual((midnight.hour, midnight.minute), (0, 0))

    def test_counters_are_not_inflated_by_a_quota_stop(self):
        """Il vecchio sentinella 10^9 falsava le metriche e i log."""
        led = QuotaLedger(self.root / "ledger.json")
        led.record_failure("prov:model:0", exhausted="day")
        bucket = led.snapshot()["buckets"]["prov:model:0"]
        self.assertLess(bucket["rpd"], 10)
        self.assertIsNotNone(led.blocked_reason("prov:model:0", {"rpd": 900}))


class TestRegistry(GatewayTestCase):
    def test_missing_key_drops_provider(self):
        os.environ.pop("TEST_PRIMARY_KEY")
        reg = Registry(CONFIG)
        self.assertNotIn("primary", [r.provider for r in reg.routes])

    def test_placeholder_key_is_ignored(self):
        os.environ["TEST_PRIMARY_KEY"] = "your_key_here_placeholder"
        reg = Registry(CONFIG)
        self.assertNotIn("primary", [r.provider for r in reg.routes])

    def test_comma_separated_keys_shard_into_buckets(self):
        os.environ["TEST_PRIMARY_KEY"] = f"{KEY_A},{KEY_B}"
        reg = Registry(CONFIG)
        buckets = [r.bucket for r in reg.routes if r.provider == "primary"]
        self.assertEqual(buckets, ["primary:fast-1:0", "primary:fast-1:1"])

    def test_routes_sorted_by_priority(self):
        reg = Registry(CONFIG)
        prios = [r.priority for r in reg.routes]
        self.assertEqual(prios, sorted(prios))

    def test_real_config_file_loads(self):
        """Il YAML in config/ deve restare parsabile e coerente."""
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "llm_providers.yaml"
        reg = Registry.load(cfg_path)
        self.assertIn("extract", reg.task_classes)
        self.assertIn("reason", reg.task_classes)
        # Nessuna chiave in env di test => nessuna rotta, ma il parsing regge
        for prov in reg.config["providers"]:
            self.assertTrue(prov.get("models"), f"{prov['id']} senza modelli")
            # base_url statica (https) oppure presa da env (endpoint locali)
            if not prov.get("base_url_env"):
                self.assertTrue(prov.get("base_url", "").startswith("https://"),
                                f"{prov['id']}: base_url non https")

    def test_nvidia_covers_triage_when_key_is_set(self):
        """
        Aggiunto il 30 ago 2026: con Groq rate-limited (429, verificato su un
        run reale) e Cerebras/Mistral senza chiave in questo repo, NVIDIA era
        l'unico altro provider con un secret già reale ma escluso dal task
        'triage' — la classe di task che stava fallendo. Un modello frontier
        per un compito 'nano' non deve essere escluso dal floor di tier: solo
        chi sta SOTTO il minimo richiesto lo è (vedi TIER_ORDER in registry.py).
        """
        os.environ["NVIDIA_API_KEY"] = "n" * 20
        self.addCleanup(os.environ.pop, "NVIDIA_API_KEY", None)
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "llm_providers.yaml"
        reg = Registry.load(cfg_path)
        triage_providers = {r.provider for r in reg.routes_for("triage")}
        self.assertIn("nvidia_nim", triage_providers, triage_providers)

    def test_compare_endpoint_reachable_via_workflow_env_names(self):
        """
        La route 'compare' (Ollama/LM Studio auto-ospitati) esisteva nello
        yaml da tempo ma .github/workflows/ingest.yml non passava mai
        COMPARE_BASE_URL/COMPARE_API_KEY/COMPARE_MODEL — collegata il 30 ago
        2026. requires_key: false, quindi basta l'URL + il nome modello.
        """
        os.environ["COMPARE_BASE_URL"] = "http://example.invalid:11434/v1"
        os.environ["COMPARE_MODEL"] = "llama3.1"
        self.addCleanup(os.environ.pop, "COMPARE_BASE_URL", None)
        self.addCleanup(os.environ.pop, "COMPARE_MODEL", None)
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "llm_providers.yaml"
        reg = Registry.load(cfg_path)
        providers = {r.provider for r in reg.routes_for("triage")}
        self.assertIn("compare", providers, providers)

    def test_env_driven_provider_needs_its_env_var(self):
        """COMPARE_*: senza COMPARE_BASE_URL il provider non produce rotte."""
        cfg = {"version": 1, "task_classes": {"extract": {"min_tier": "small"}},
               "providers": [{"id": "compare", "base_url_env": "TEST_COMPARE_URL",
                              "api_key_env": "TEST_COMPARE_KEY", "requires_key": False,
                              "limits": {}, "models": [{"name": "local-model",
                                                        "name_env": "TEST_COMPARE_MODEL",
                                                        "tier": "frontier",
                                                        "tasks": ["extract"]}]}]}
        os.environ.pop("TEST_COMPARE_URL", None)
        self.assertEqual(Registry(cfg).routes, [])

        os.environ["TEST_COMPARE_URL"] = "http://localhost:20128/v1"
        os.environ["TEST_COMPARE_MODEL"] = "qwen-local"
        self.addCleanup(lambda: os.environ.pop("TEST_COMPARE_URL", None))
        self.addCleanup(lambda: os.environ.pop("TEST_COMPARE_MODEL", None))
        routes = Registry(cfg).routes
        self.assertEqual(len(routes), 1)  # nessuna chiave richiesta
        self.assertEqual(routes[0].model, "qwen-local")
        self.assertEqual(routes[0].base_url, "http://localhost:20128/v1")

    def test_provider_can_be_excluded_from_routing(self):
        reg = Registry(CONFIG)
        without = reg.routes_for("extract", exclude_providers={"primary"})
        self.assertNotIn("primary", [r.provider for r in without])
        self.assertTrue(without)


class TestJsonParsing(unittest.TestCase):
    def test_fenced_json(self):
        self.assertEqual(_parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_prose_around_json(self):
        self.assertEqual(_parse_json('Ecco il risultato:\n{"a": 1}\nSpero vada bene'), {"a": 1})

    def test_array_response(self):
        self.assertEqual(_parse_json('[{"a": 1}]'), [{"a": 1}])

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_json("non ho trovato nulla"))
        self.assertIsNone(_parse_json(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
