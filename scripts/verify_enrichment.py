"""
Controlled verification: does post-enrichment scoring rank real players ABOVE
roster-dump names? Tests the assumption that capped dump-names self-clean
post-enrichment (no TM profile -> stay at base score) while real free agents
rise (TM data -> age/apps/value lift their score).

Fixed 10-player input (deterministic): 5 real players + 5 dump names that the
cap let through. Enriches each via the production TransfermarktEnricher, merges
fields exactly like run_enrichment.py, scores post-enrichment with OB1Scorer,
and prints the final ranking. No Telegram, no commit, no DB writes.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

_root = str(Path(__file__).parent.parent)
sys.path.insert(0, _root)

from src.enricher_tm import TransfermarktEnricher  # noqa: E402
from src.scoring import OB1Scorer  # noqa: E402

# Real, recognisable Serie B/C free agents seen in discovery
REAL = ["Mattia Aramu", "Marco Capuano", "Marco Olivieri", "Enrico Brignola", "Shady Oukhadda"]
# Roster-dump names the cap let through (surname-first table style)
DUMP = ["Berardini Alessandro", "Brolli Fransisco Roberto", "Canetto Stefano",
        "Capriotti Stefano", "Cecarini Leonardo"]

if not os.getenv('GEMINI_API_KEY'):
    print("FATAL: no GEMINI_API_KEY")
    sys.exit(1)

enricher = TransfermarktEnricher()
scorer = OB1Scorer()

ENRICH_KEYS = ['nationality', 'second_nationality', 'foot', 'market_value',
               'market_value_formatted', 'height_cm', 'birth_date', 'contract_expires',
               'tm_url', 'agent', 'appearances', 'goals', 'assists', 'minutes_played']


def build_and_enrich(name, kind):
    opp = {
        'player_name': name,
        'opportunity_type': 'svincolato',
        'discovered_at': datetime.now().isoformat(),
        'source_name': 'Gemini Search',
        'source_url': 'https://example.test/article',
        'summary': 'Svincolato Serie C/D estate 2026',
        '_kind': kind,
    }
    try:
        tm = enricher.enrich_player(name)
    except Exception as e:
        print(f"  [ENRICH ERR] {name}: {e}")
        tm = None
    if tm:
        if tm.get('market_value_eur') and not tm.get('market_value'):
            tm['market_value'] = tm['market_value_eur']
        for k in ENRICH_KEYS:
            v = tm.get(k)
            if v is not None:
                opp[k] = v
        if not opp.get('age') and tm.get('birth_date'):
            try:
                age = datetime.now().year - int(str(tm['birth_date'])[:4])
                if 10 <= age <= 60:
                    opp['age'] = age
            except (ValueError, TypeError):
                pass
        opp['tm_enriched'] = any(tm.get(k) for k in ['market_value', 'appearances', 'contract_expires', 'goals'])
    return opp


print("=" * 70)
print("ENRICHMENT VERIFICATION — real players vs roster-dump names")
print("=" * 70)

rows = []
for name in REAL:
    print(f"\n[REAL] {name}")
    opp = build_and_enrich(name, 'REAL')
    rows.append(opp)
for name in DUMP:
    print(f"\n[DUMP] {name}")
    opp = build_and_enrich(name, 'DUMP')
    rows.append(opp)

# Score post-enrichment
for opp in rows:
    res = scorer.score(opp)
    opp['_score'] = res['ob1_score']
    opp['_tier'] = res['classification']

rows.sort(key=lambda o: -o['_score'])

print("\n" + "=" * 70)
print("FINAL RANKING (post-enrichment)")
print("=" * 70)
print(f"{'#':>2}  {'score':>5}  {'tier':<5} {'kind':<5} {'enriched':<9} {'age':>4} {'apps':>5} {'value':>10}  name")
for i, o in enumerate(rows, 1):
    enr = 'TM✓' if o.get('tm_enriched') else '—'
    age = o.get('age', '')
    apps = o.get('appearances', '')
    val = o.get('market_value_formatted') or (o.get('market_value') or '')
    print(f"{i:>2}  {o['_score']:>5}  {o['_tier']:<5} {o['_kind']:<5} {enr:<9} "
          f"{str(age):>4} {str(apps):>5} {str(val):>10}  {o['player_name']}")

# Verdict
real_scores = [o['_score'] for o in rows if o['_kind'] == 'REAL']
dump_scores = [o['_score'] for o in rows if o['_kind'] == 'DUMP']
worst_real = min(real_scores)
best_dump = max(dump_scores)
print("\n" + "-" * 70)
print(f"Worst REAL score: {worst_real}   |   Best DUMP score: {best_dump}")
if worst_real > best_dump:
    print(">>> CONFIRMED: every real player ranks ABOVE every dump name.")
else:
    print(">>> NOT CLEAN: at least one dump name scored >= a real player. Inspect above.")
print("=" * 70)
