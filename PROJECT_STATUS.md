# OB1 Scout Lega Pro / Serie D — Project Status

**Ultimo aggiornamento:** 2026-07-17  
**Branch:** `main`  
**Repo:** https://github.com/mtornani/ob1-serie-c  
**Percorso:** `D:\AI\Sferico\OB1_Ecosystem\lega-pro`

> Unico file di stato. Aggiorna dopo cambi significativi.

---

## Promessa prodotto

Radar scouting **Serie C / Serie D / Eccellenza IT**.  
Ogni nome in dashboard pubblica regge una telefonata di verifica  
(**identity_complete**: nome completo + età 15–42 + club + source_url).

Allineamento qualità: **global-scout v2** (gate + prove) · **Karpathy** (semplicità) · **ponytail** (minimo codice).

---

## Snapshot dati (post quality gate)

| Metrica | Valore |
|--------|--------|
| Raw `opportunities.json` | 602 |
| Tracking (post pre-filter) | 304 |
| **Publishable pubblici** | **40** |
| HOT / WARM / COLD | 6 / 27 / 7 |
| Con età (raw) | ~308 |
| `tm_enriched` | ~311 |

Top: Levak 79, Rizzo Pinna 77, Buffon 74, Doumbia 72, Licina 70.

---

## Pipeline

```
cron 6h → ouroboros_run (Gemini budget 4 + Tavily source-first)
       → run_enrichment (batch TM, priorità no-age, max 4 batch)
       → generate_dashboard (gate publishable only)
       → sanity_check
       → notify + commit data
```

| Componente | File | Note |
|-----------|------|------|
| Discovery | `src/scraper_global.py` | Circuit breaker daily quota; Tavily trusted_sources |
| Enrich | `src/enricher_tm.py` + `scripts/run_enrichment.py` | Batch 5; stop on free_tier dead |
| Score | `src/scoring.py` | SCORE-002 |
| Gate | `src/quality_gate.py` | identity_complete → publishable |
| Export | `scripts/generate_dashboard.py` | Solo publishable in `docs/data.json` |
| Sanity | `scripts/sanity_check.py` | + check età pubblica |
| Config | `config/leagues.yaml` | Query estate 2026 + trusted IT sources |

Env knobs:
- `GEMINI_DISCOVERY_BUDGET` (default 4)
- `MAX_ENRICH_BATCHES` (default 4)

---

## P0 root cause (risolto a codice, monitorare in CI)

GHA **verde** ma Gemini free tier **20 RPD** esausto → 0 discovery, 0 enrich.  
Fix: budget discovery, circuit breaker daily quota, Tavily fallback source-first, enrich prioritizza età.

---

## Aperti

1. **Quota Gemini** — se 20 RPD insufficienti: pay-as-you-go o modello alternativo  
2. **264 tracking non publishable** — arricchire età/club (prossima run con budget)  
3. Multi-fonte evidence store (SQLite) — solo se monofonte resta bug  
4. Hard-gate `corroborated` (≥2 fonti) — dopo multi-fonte  

---

## Non toccare senza richiesta

- `src/satarch/` (progetto separato, rimosso da remote core)  
- Rewrite SQLite v2 “per allinearci a global”  
- Feature one-off club (Campobasso/Ravenna scripts)  
