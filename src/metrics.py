#!/usr/bin/env python3
"""
ARCH-002 Fase 1 — costo per fatto nuovo verificato.

Il numero che manca per smettere di discutere di architettura per opinioni:

    costo_per_fatto = (ricerche + chiamate_llm + fetch) / campi_nuovi_verificati

Non è il costo per run (una run che non scopre niente costa comunque) e non è
il costo per giocatore (un giocatore già completo non produce fatti nuovi). È il
prezzo di UNA informazione che prima non avevamo e che è passata dai controlli.

Il contatore vive per l'intero processo, i moduli lo alimentano dove i costi
nascono davvero:

    src/free_stack.py   ricerche (e ricerche risparmiate dalla cache)
    src/llm/gateway.py  chiamate LLM, cache hit, fallimenti, token
    src/enricher_tm.py  fetch pagina, 304 (fetch risparmiati)
    scripts/run_enrichment.py  campi nuovi verificati, scrittura della riga

A fine run una riga in `data/metrics.jsonl` (append, non stato: serve la serie
storica per vedere se una modifica ha migliorato o peggiorato le cose).

Disattivabile con OB1_METRICS=0: i contatori continuano a girare in memoria —
costano nulla — ma non si scrive niente su disco.

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_metrics -v
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

METRICS_FILE = Path("data/metrics.jsonl")

# Costo marginale reale di una ricerca, in dollari. I motori senza chiave
# costano zero: è tutto il senso di free_stack. Serper si paga a consumo,
# Tavily ha crediti gratuiti mensili (quindi 0 finché stiamo nel piano).
SEARCH_UNIT_COST_USD = {
    "duckduckgo": 0.0,
    "searxng": 0.0,
    "tavily": 0.0,
    "serper": 0.001,
    "cache": 0.0,
}

# Quante run indietro guarda il controllo di regressione.
HISTORY_WINDOW = 10
# Oltre questo rapporto rispetto alla mediana storica, il costo per fatto è
# peggiorato abbastanza da meritare un avviso.
REGRESSION_RATIO = 1.5


@dataclass
class RunMetrics:
    """Contatori di una singola run. Nessuna dipendenza, nessuna rete."""

    run_id: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    searches: int = 0
    searches_cached: int = 0
    searches_blocked: int = 0
    search_by_source: Dict[str, int] = field(default_factory=dict)
    llm_calls: int = 0
    llm_cache_hits: int = 0
    llm_failures: int = 0
    llm_tokens: int = 0
    llm_by_route: Dict[str, int] = field(default_factory=dict)
    fetches: int = 0
    fetches_304: int = 0
    fetches_failed: int = 0
    facts: int = 0
    facts_by_field: Dict[str, int] = field(default_factory=dict)
    players_touched: int = 0
    cost_usd: float = 0.0

    # ------------------------------------------------------------ registrazioni
    def search(self, source: str = "duckduckgo") -> None:
        """Una ricerca web davvero eseguita (la cache non passa di qui)."""
        self.searches += 1
        self.search_by_source[source] = self.search_by_source.get(source, 0) + 1
        self.cost_usd += SEARCH_UNIT_COST_USD.get(source, 0.0)

    def search_cached(self) -> None:
        """Una ricerca risparmiata dalla cache: si conta, ma non costa."""
        self.searches_cached += 1

    def search_blocked(self) -> None:
        """Ricerca non eseguita (anti-bot): non è 'nessun risultato'."""
        self.searches_blocked += 1

    def llm_call(self, route: str = "", tokens: int = 0) -> None:
        self.llm_calls += 1
        self.llm_tokens += max(0, int(tokens or 0))
        if route:
            self.llm_by_route[route] = self.llm_by_route.get(route, 0) + 1

    def llm_cache_hit(self) -> None:
        self.llm_cache_hits += 1

    def llm_failure(self) -> None:
        self.llm_failures += 1

    def fetch(self, status: int = 200) -> None:
        """
        Un fetch HTTP. Il 304 si conta a parte: è il fetch che NON è costato
        parsing né inferenza, ed è la misura di successo della Fase 2.
        """
        self.fetches += 1
        if status == 304:
            self.fetches_304 += 1
        elif status != 200:
            self.fetches_failed += 1

    def fact(self, field_name: str = "", n: int = 1) -> None:
        """Un campo nuovo, verificato, che prima non avevamo."""
        self.facts += max(0, int(n))
        if field_name:
            self.facts_by_field[field_name] = self.facts_by_field.get(field_name, 0) + n

    def player_touched(self, n: int = 1) -> None:
        self.players_touched += max(0, int(n))

    # ----------------------------------------------------------------- letture
    @property
    def operations(self) -> int:
        """Le operazioni che costano: ricerche + inferenza + fetch."""
        return self.searches + self.llm_calls + self.fetches

    @property
    def cost_per_fact(self) -> Optional[float]:
        """
        Operazioni per fatto nuovo. None quando i fatti sono zero: una run che
        non ha scoperto niente non ha un costo per fatto *infinito*, ha un costo
        per fatto *indefinito*. Confondere le due cose avvelena le medie.
        """
        if self.facts <= 0:
            return None
        return round(self.operations / self.facts, 3)

    @property
    def usd_per_fact(self) -> Optional[float]:
        if self.facts <= 0:
            return None
        return round(self.cost_usd / self.facts, 6)

    @property
    def fetch_304_ratio(self) -> Optional[float]:
        """Quota di fetch risolti dalla cache condizionale (criterio Fase 2)."""
        if self.fetches <= 0:
            return None
        return round(self.fetches_304 / self.fetches, 3)

    @property
    def llm_cache_hit_ratio(self) -> Optional[float]:
        total = self.llm_calls + self.llm_cache_hits
        if total <= 0:
            return None
        return round(self.llm_cache_hits / total, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": self.run_id or os.getenv("GITHUB_RUN_ID", ""),
            "started_at": self.started_at,
            "searches": self.searches,
            "searches_cached": self.searches_cached,
            "searches_blocked": self.searches_blocked,
            "search_by_source": dict(sorted(self.search_by_source.items())),
            "llm_calls": self.llm_calls,
            "llm_cache_hits": self.llm_cache_hits,
            "llm_failures": self.llm_failures,
            "llm_tokens": self.llm_tokens,
            "llm_by_route": dict(sorted(self.llm_by_route.items())),
            "fetches": self.fetches,
            "fetches_304": self.fetches_304,
            "fetches_failed": self.fetches_failed,
            "facts": self.facts,
            "facts_by_field": dict(sorted(self.facts_by_field.items())),
            "players_touched": self.players_touched,
            "operations": self.operations,
            "cost_per_fact": self.cost_per_fact,
            "cost_usd": round(self.cost_usd, 6),
            "usd_per_fact": self.usd_per_fact,
            "fetch_304_ratio": self.fetch_304_ratio,
            "llm_cache_hit_ratio": self.llm_cache_hit_ratio,
        }

    def summary(self) -> str:
        cpf = self.cost_per_fact
        cpf_s = f"{cpf}" if cpf is not None else "n/d (0 fatti nuovi)"
        ratio = self.fetch_304_ratio
        ratio_s = f"{int(ratio * 100)}%" if ratio is not None else "-"
        return (
            f"[METRICS] fatti_nuovi={self.facts} operazioni={self.operations} "
            f"(ricerche={self.searches} llm={self.llm_calls} fetch={self.fetches}) "
            f"costo_per_fatto={cpf_s} | 304={ratio_s} "
            f"cache_llm={self.llm_cache_hits} risparmi_ricerca={self.searches_cached} "
            f"costo=${round(self.cost_usd, 4)}"
        )

    # -------------------------------------------------------------- persistenza
    def write(self, path: Path = METRICS_FILE) -> bool:
        """
        Appende una riga JSON. Ritorna False se la scrittura è disattivata o
        fallisce: le metriche non devono MAI far fallire una pipeline.
        """
        if os.getenv("OB1_METRICS", "1") == "0":
            return False
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
            return True
        except OSError as e:
            print(f"  [METRICS] riga non scritta ({type(e).__name__}: {e})")
            return False


# --------------------------------------------------------------- serie storica
def load_history(path: Path = METRICS_FILE, limit: int = HISTORY_WINDOW) -> List[Dict[str, Any]]:
    """Ultime `limit` righe valide di metrics.jsonl, dalla più vecchia."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-limit * 3:]:          # margine per le righe corrotte
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out[-limit:]


def _median(values: List[float]) -> Optional[float]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def regression_check(history: List[Dict[str, Any]],
                     ratio: float = REGRESSION_RATIO) -> Optional[str]:
    """
    Il costo per fatto dell'ultima run confrontato con la mediana delle
    precedenti. Ritorna un messaggio se è peggiorato oltre `ratio`, altrimenti
    None. Le run senza fatti nuovi non entrano nel confronto: non sono un
    peggioramento di efficienza, sono assenza di misura.
    """
    rows = [r for r in history if r.get("cost_per_fact") is not None]
    if len(rows) < 3:
        return None
    current = rows[-1]["cost_per_fact"]
    baseline = _median([r["cost_per_fact"] for r in rows[:-1]])
    if not baseline or current <= baseline * ratio:
        return None
    return (f"costo_per_fatto {current} contro mediana storica {baseline} "
            f"({round(current / baseline, 2)}x): la pipeline sta pagando di più "
            f"per la stessa informazione")


# ------------------------------------------------------------------- singleton
_METRICS: Optional[RunMetrics] = None


def get_metrics() -> RunMetrics:
    """Contatore condiviso dal processo. Come get_gateway(), stesso motivo."""
    global _METRICS
    if _METRICS is None:
        _METRICS = RunMetrics()
    return _METRICS


def reset_metrics() -> RunMetrics:
    """Riparte da zero (test, o una seconda pipeline nello stesso processo)."""
    global _METRICS
    _METRICS = RunMetrics()
    return _METRICS


if __name__ == "__main__":
    m = reset_metrics()
    m.search("duckduckgo")
    m.fetch(200)
    m.llm_call("groq:llama-3.3-70b", tokens=1200)
    m.fact("birth_date")
    m.fact("current_club")
    print(m.summary())
    print(json.dumps(m.to_dict(), indent=2, ensure_ascii=False))
