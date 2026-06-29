"""
Isolated stress run for the grounding discovery phase.

Goal: measure, on the FREE Gemini key, two things the smoke test could not:
  1. Does the full discovery sweep (all queries × all leagues) hit a 429 /
     RESOURCE_EXHAUSTED rate limit? If so, at which call index + elapsed time?
  2. How many DISTINCT players does the run produce (with the dedup-by-name fix)?

It instruments the Gemini client call (timing + structured error capture per
call) and runs the REAL scrape_league() — so the dedup-by-name fix is exercised
exactly as in production. No Telegram, no commit, no DB writes.
"""
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).parent.parent)
sys.path.insert(0, _root)
sys.path.insert(0, str(Path(_root) / 'src'))

from src.scraper_global import GlobalScraper  # noqa: E402

print("=" * 64)
print("GROUNDING STRESS RUN — free key, full discovery sweep")
print("=" * 64)

if not os.getenv('GEMINI_API_KEY'):
    print("FATAL: no GEMINI_API_KEY in environment")
    sys.exit(1)

scraper = GlobalScraper()
if not scraper.gemini_client:
    print("FATAL: gemini client not initialised")
    sys.exit(1)

# --- Instrument the raw Gemini call: timing + structured error per call -------
call_log = []
_real_gen = scraper.gemini_client.models.generate_content


def _wrapped(*args, **kwargs):
    idx = len(call_log) + 1
    t0 = time.time()
    try:
        r = _real_gen(*args, **kwargs)
        call_log.append({'idx': idx, 'ok': True, 'dt': time.time() - t0, 'err': None})
        return r
    except Exception as e:
        call_log.append({'idx': idx, 'ok': False, 'dt': time.time() - t0,
                         'err': f'{type(e).__name__}: {e}'})
        raise


scraper.gemini_client.models.generate_content = _wrapped

# --- Run the real discovery sweep across every configured league --------------
all_players = []
t_start = time.time()
for league_id in scraper.leagues:
    print(f"\n>>> League: {league_id}")
    try:
        opps = scraper.scrape_league(league_id)
        all_players.extend(opps)
    except Exception as e:
        print(f"  [LEAGUE ERROR] {type(e).__name__}: {e}")
t_total = time.time() - t_start

# --- Report -------------------------------------------------------------------
print("\n" + "=" * 64)
print("RESULTS")
print("=" * 64)

n_calls = len(call_log)
failures = [c for c in call_log if not c['ok']]
rate_limited = [c for c in failures if any(
    k in (c['err'] or '').lower()
    for k in ('429', 'resource_exhausted', 'quota', 'rate limit', 'too many requests')
)]

print(f"Gemini grounded calls made: {n_calls}")
print(f"Total wall time: {t_total:.1f}s")
if n_calls:
    avg = sum(c['dt'] for c in call_log) / n_calls
    print(f"Avg call latency: {avg:.1f}s  |  effective rate: {n_calls / max(t_total, 0.1) * 60:.1f} calls/min")

print("\nPer-call:")
for c in call_log:
    flag = 'OK ' if c['ok'] else 'ERR'
    print(f"  #{c['idx']:>2} {flag} {c['dt']:>5.1f}s  {c['err'] or ''}")

if rate_limited:
    first = rate_limited[0]
    print(f"\n>>> FIRST 429/RATE LIMIT at call #{first['idx']} ({first['dt']:.1f}s in)")
    print(f"    {first['err']}")
elif failures:
    print(f"\n>>> {len(failures)} call(s) failed, but NONE were rate limits:")
    for f in failures:
        print(f"    #{f['idx']}: {f['err']}")
else:
    print("\n>>> NO 429 / rate limit hit. Free key handled the full sweep.")

# Distinct players (scrape_league already dedups by name within a league;
# dedup across leagues here too for a clean global count)
seen = set()
distinct = []
for p in all_players:
    k = (p.player_name or '').strip().lower()
    if k and k not in seen:
        seen.add(k)
        distinct.append(p)

print(f"\nTotal players produced (distinct, dedup-by-name): {len(distinct)}")
for p in distinct:
    print(f"  - {p.player_name}  [{p.opportunity_type}]  via {p.source_name}")

print("\n" + "=" * 64)
print("STRESS RUN DONE")
print("=" * 64)
