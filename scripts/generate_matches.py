#!/usr/bin/env python3
"""
DNA-001: Generate DNA Matches

Genera match player-club e salva risultati per dashboard e bot.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from dna import DNAMatcher


def main():
    print("🧬 Generating DNA Matches...")

    # Inizializza matcher
    data_dir = Path(__file__).parent.parent / 'data'
    matcher = DNAMatcher(data_dir)

    stats = matcher.get_stats()
    print(f"📊 Database: {stats['total_players']} giocatori, {stats['total_clubs']} club")
    print(f"🏟️ Parent clubs: {', '.join(stats['parent_clubs'])}")
    print(f"⚠️ Underused players: {stats['underused_players']}")

    # Genera match per ogni club
    all_matches = []

    for club_id, club in matcher.clubs.items():
        print(f"\n🎯 Matching per {club.name}...")

        matches = matcher.get_matches_for_club(
            club_id,
            min_score=50,
            limit=10
        )

        print(f"   Trovati {len(matches)} match")

        for m in matches[:5]:
            emoji = "🔥" if m.score >= 80 else "⚡" if m.score >= 65 else "📊"
            print(f"   {emoji} {m.player.name} ({m.player.current_team}) - {m.score}%")

        all_matches.extend([m.to_dict() for m in matches])

    # Salva risultati
    output = {
        'matches': all_matches,
        'stats': stats,
        'generated_at': datetime.now().isoformat(),
    }

    output_file = data_dir / 'dna_matches.json'
    output_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n✅ Saved {len(all_matches)} matches to {output_file}")

    # Copia in docs per la dashboard
    docs_file = Path(__file__).parent.parent / 'docs' / 'dna_matches.json'
    docs_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"✅ Copied to {docs_file}")

    # Top matches globali
    print("\n🏆 TOP 10 MATCHES GLOBALI:")
    top = matcher.get_top_matches(min_score=70, limit=10)
    for i, m in enumerate(top, 1):
        print(f"   {i}. {m.player.name} → {m.club.name}: {m.score}%")
        print(f"      {m.recommendation}")


if __name__ == "__main__":
    main()
