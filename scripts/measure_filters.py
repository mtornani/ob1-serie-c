"""
Diagnostic: measure how the guard-rails (cap-per-source + score floor) shape
the discovery output. Runs the REAL scrape_league (cap active), scores each
player with the SAME gate scorer used by ouroboros_run, and reports the score
distribution + how many clear the floor.

Answers: of everything discovered, how many survive, and is the floor tuned
right? No Telegram, no commit, no DB writes.
"""
import os
import sys
from pathlib import Path

_root = str(Path(__file__).parent.parent)
sys.path.insert(0, _root)
sys.path.insert(0, str(Path(_root) / 'src'))

sys.path.insert(0, str(Path(_root) / 'scripts'))

from src.scraper_global import GlobalScraper, MAX_PLAYERS_PER_SOURCE  # noqa: E402
from src.scoring import OB1Scorer  # noqa: E402
from ouroboros_run import is_valid_player_name  # noqa: E402  (same gate as prod)

SCORE_FLOOR = 55  # mirrors ouroboros_run.SCORE_FLOOR

print("=" * 64)
print("FILTER MEASUREMENT — cap-per-source + score floor")
print(f"MAX_PLAYERS_PER_SOURCE={MAX_PLAYERS_PER_SOURCE}  SCORE_FLOOR={SCORE_FLOOR}")
print("=" * 64)

if not os.getenv('GEMINI_API_KEY'):
    print("FATAL: no GEMINI_API_KEY")
    sys.exit(1)

scraper = GlobalScraper()
scorer = OB1Scorer()

# --- Discovery (cap-per-source active inside scrape_league) -------------------
discovered = []
for league_id in scraper.leagues:
    print(f"\n>>> League: {league_id}")
    try:
        discovered.extend(scraper.scrape_league(league_id))
    except Exception as e:
        print(f"  [LEAGUE ERROR] {type(e).__name__}: {e}")

# --- Score each player with the production gate scorer ------------------------
scored = []
for opp in discovered:
    # Mirror production: junk names are skipped before scoring (ouroboros_run).
    if not is_valid_player_name(opp.player_name):
        continue
    raw_dict = {
        'player_name': opp.player_name,
        'opportunity_type': opp.opportunity_type.value,
        'discovered_at': opp.reported_date,
        'source_name': opp.source_name,
        'source_url': opp.source_url,
        'summary': opp.description,
    }
    try:
        s = scorer.score(raw_dict)['ob1_score']
    except Exception as e:
        print(f"  [SCORE ERROR] {opp.player_name}: {e}")
        s = 0
    scored.append((opp.player_name, s))

# --- Report ------------------------------------------------------------------
print("\n" + "=" * 64)
print("RESULTS")
print("=" * 64)

total = len(scored)
buckets = {'<40': 0, '40-54': 0, '55-69 (WARM)': 0, '70+ (HOT)': 0}
for _, s in scored:
    if s < 40:
        buckets['<40'] += 1
    elif s < 55:
        buckets['40-54'] += 1
    elif s < 70:
        buckets['55-69 (WARM)'] += 1
    else:
        buckets['70+ (HOT)'] += 1

survivors = [(n, s) for n, s in scored if s >= SCORE_FLOOR]

print(f"Discovered (post cap/dedup/freshness): {total}")
print(f"Survivors (score >= {SCORE_FLOOR}):       {len(survivors)}")
print(f"Cut by score floor:                    {total - len(survivors)}")

print("\nScore distribution:")
for k, v in buckets.items():
    bar = '#' * v
    print(f"  {k:>14}: {v:>3}  {bar}")

# Per-source density (proves the cap held — no source should exceed the cap)
from collections import Counter  # noqa: E402
# Count by source_url, not source_name: grounding maps every redirect to the
# label "Gemini Search", so only the URL reveals whether the cap held.
src_counts = Counter(opp.source_url for opp in discovered if opp.source_url)
print("\nPlayers per source URL (cap check):")
for src, c in src_counts.most_common(8):
    flag = '  <-- OVER CAP' if c > MAX_PLAYERS_PER_SOURCE else ''
    print(f"  {c:>3}  {src[:60]}{flag}")

print(f"\nSurvivors (>= {SCORE_FLOOR}), sorted by score:")
for n, s in sorted(survivors, key=lambda x: -x[1]):
    print(f"  {s:>3}  {n}")

print("\n" + "=" * 64)
print("MEASUREMENT DONE")
print("=" * 64)
