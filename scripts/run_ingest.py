#!/usr/bin/env python3
"""
OB1 Scout - Ingest Pipeline for GitHub Actions
Uses Tavily + Gemini for advanced scraping
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Check which scraper to use
USE_TAVILY = os.getenv('TAVILY_API_KEY') is not None


def main():
    print("Starting OB1 Scout ingest pipeline...")

    # Run appropriate scraper
    if USE_TAVILY:
        print("Using Tavily scraper (advanced)")
        from scraper_tavily import TavilyScraperOB1
        scraper = TavilyScraperOB1()
        opportunities = scraper.scrape_all()  # Returns list of dicts
    else:
        print("Using Serper scraper (basic)")
        from scraper import OB1Scraper
        scraper = OB1Scraper()
        raw_opportunities = scraper.scrape_all()
        opportunities = [o.model_dump() for o in raw_opportunities]

    # Save results
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)

    # Load existing opportunities
    output_file = output_dir / 'opportunities.json'
    existing = []
    if output_file.exists():
        try:
            existing = json.loads(output_file.read_text())
        except:
            pass

    # Merge and deduplicate
    all_opps = existing + opportunities
    seen = set()
    unique = []
    for o in all_opps:
        key = (o.get('player_name', ''), o.get('source_url', ''))
        if key not in seen:
            seen.add(key)
            unique.append(o)

    # Keep only last 100
    unique = sorted(unique, key=lambda x: x.get('discovered_at', ''), reverse=True)[:100]
    output_file.write_text(json.dumps(unique, indent=2, ensure_ascii=False, default=str))

    # Stats
    new_count = len(opportunities)
    total_count = len(unique)

    print(f"Found {new_count} new opportunities")
    print(f"Total tracked: {total_count}")

    # Save stats
    stats = {
        'last_run': datetime.now().isoformat(),
        'new_opportunities': new_count,
        'total_opportunities': total_count,
        'scraper': 'tavily' if USE_TAVILY else 'serper',
        'by_type': {}
    }
    for o in opportunities:
        t = o.get('opportunity_type', 'altro')
        if hasattr(t, 'value'):
            t = t.value
        stats['by_type'][t] = stats['by_type'].get(t, 0) + 1

    (output_dir / 'stats.json').write_text(json.dumps(stats, indent=2))

    # Output for GitHub Actions
    github_output = os.getenv('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f'new_count={new_count}\n')
            f.write(f'total_count={total_count}\n')

    return new_count


if __name__ == "__main__":
    main()
