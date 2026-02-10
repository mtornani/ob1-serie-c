#!/usr/bin/env python3
"""
DNA-001: Generate DNA Matches v2.0

Genera match player-club e salva risultati per dashboard e bot.
Usa il nuovo scoring realistico con filtri bloccanti.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from dna import DNAMatcher


def main():
    print("🧬 Generating DNA Matches v2.0 (scoring realistico)...")
    print("=" * 60)

    # Inizializza matcher
    data_dir = Path(__file__).parent.parent / 'data'
    matcher = DNAMatcher(data_dir)

    stats = matcher.get_stats()
    print(f"📊 Database: {stats['total_players']} giocatori, {stats['total_clubs']} club")
    print(f"🏟️ Parent clubs: {', '.join(stats['parent_clubs'])}")
    print(f"⚠️ Underused players: {stats['underused_players']}")

    # Genera match per ogni club
    all_matches = []
    clubs_with_matches = 0
    clubs_without_matches = 0

    for club_id, club in matcher.clubs.items():
        print(f"\n🎯 Matching per {club.name} ({club.category})...")
        print(f"   Budget: {club.max_loan_cost}k€ | Stili: {', '.join(club.playing_styles)}")
        print(f"   Esigenze: {', '.join(n.position + ' (' + n.priority + ')' for n in club.needs)}")

        matches = matcher.get_matches_for_club(
            club_id,
            min_score=55,   # Alzata da 50 a 55
            limit=8         # Max 8 per club (era 10) — qualità > quantità
        )

        if matches:
            clubs_with_matches += 1
            print(f"   ✅ Trovati {len(matches)} match realistici")
        else:
            clubs_without_matches += 1
            print(f"   ⚠️ Nessun match realistico trovato")

        for m in matches[:5]:
            emoji = "🔥" if m.score >= 80 else "⚡" if m.score >= 65 else "📊"
            budget_info = f"mv:{m.player.market_value}k€" if m.player.market_value > 0 else "mv:?"
            avail_info = m.player.transfer_status
            print(f"   {emoji} {m.player.name} ({m.player.current_team}) - "
                  f"{m.score}% [{budget_info}, {avail_info}]")
            print(f"      Breakdown: pos={m.breakdown.get('position',0)} "
                  f"age={m.breakdown.get('age',0)} "
                  f"style={m.breakdown.get('style',0)} "
                  f"avail={m.breakdown.get('availability',0)} "
                  f"budget={m.breakdown.get('budget',0)} "
                  f"level={m.breakdown.get('level',0)}")

        all_matches.extend([m.to_dict() for m in matches])

    # Prepara profili club per la dashboard client-side
    clubs_data = [club.to_dict() for club in matcher.clubs.values()]
    print(f"\n🏟️ Inclusi {len(clubs_data)} profili club nell'output")

    # Salva risultati
    output = {
        'matches': all_matches,
        'clubs': clubs_data,
        'stats': stats,
        'generated_at': datetime.now().isoformat(),
        'version': '2.1',
    }

    output_file = data_dir / 'dna_matches.json'
    output_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n{'=' * 60}")
    print(f"✅ Saved {len(all_matches)} matches to {output_file}")

    # Copia in docs per la dashboard
    docs_file = Path(__file__).parent.parent / 'docs' / 'dna_matches.json'
    docs_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"✅ Copied to {docs_file}")

    # Statistiche finali
    print(f"\n📈 RIEPILOGO:")
    print(f"   Club con match: {clubs_with_matches}/{clubs_with_matches + clubs_without_matches}")
    print(f"   Club senza match: {clubs_without_matches}")
    print(f"   Match totali: {len(all_matches)}")

    if all_matches:
        scores = [m['score'] for m in all_matches]
        print(f"   Score medio: {sum(scores)/len(scores):.1f}")
        print(f"   Score min/max: {min(scores)}/{max(scores)}")
        hot = sum(1 for s in scores if s >= 80)
        warm = sum(1 for s in scores if 65 <= s < 80)
        cold = sum(1 for s in scores if s < 65)
        print(f"   🔥 Hot (80+): {hot} | ⚡ Warm (65-79): {warm} | 📊 Cold (<65): {cold}")

    # Top matches globali
    print(f"\n🏆 TOP 10 MATCHES GLOBALI:")
    top = matcher.get_top_matches(min_score=65, limit=10)
    for i, m in enumerate(top, 1):
        print(f"   {i}. {m.player.name} → {m.club.name}: {m.score}%")
        print(f"      {m.recommendation}")


if __name__ == "__main__":
    main()
