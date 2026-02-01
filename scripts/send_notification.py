#!/usr/bin/env python3
"""
OB1 Scout - Send Telegram Notifications (NOTIF-001)
Notifiche arricchite con scoring avanzato
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from notifier import TelegramNotifier
from scoring import OB1Scorer


def main():
    print("📢 Sending enhanced Telegram notifications (NOTIF-001)...")

    base_dir = Path(__file__).parent.parent

    # Load opportunities from docs/data.json (already scored by generate_dashboard)
    data_file = base_dir / 'docs' / 'data.json'

    if not data_file.exists():
        # Fallback to raw data
        data_file = base_dir / 'data' / 'opportunities.json'

    if not data_file.exists():
        print("❌ No data file found")
        return

    # Load data
    data = json.loads(data_file.read_text())

    # Handle both formats
    if 'opportunities' in data:
        # From data.json (dashboard format, already scored)
        opportunities = data['opportunities']
        stats = data.get('stats', {})
        print(f"📊 Loaded {len(opportunities)} scored opportunities from dashboard data")
    else:
        # From opportunities.json (raw format, needs scoring)
        opportunities = data
        print(f"📊 Loaded {len(opportunities)} raw opportunities, applying scoring...")

        scorer = OB1Scorer()
        scored_opps = []
        for opp in opportunities:
            score_result = scorer.score(opp)
            scored_opp = {**opp, **score_result}
            scored_opps.append(scored_opp)

        # Sort by score
        scored_opps.sort(key=lambda x: x['ob1_score'], reverse=True)
        opportunities = scored_opps

        # Calculate stats
        stats = {
            'total': len(opportunities),
            'hot': sum(1 for o in opportunities if o.get('classification') == 'hot'),
            'warm': sum(1 for o in opportunities if o.get('classification') == 'warm'),
            'cold': sum(1 for o in opportunities if o.get('classification') == 'cold'),
        }

    if not opportunities:
        print("❌ No opportunities found")
        return

    # Filter for recent (last 6 hours for scheduled runs)
    cutoff = (datetime.now() - timedelta(hours=6)).strftime('%Y-%m-%d')

    recent = [
        o for o in opportunities
        if o.get('reported_date', '') >= cutoff or o.get('discovered_at', '')[:10] >= cutoff
    ]

    # If no recent, check for today's data
    today = datetime.now().strftime('%Y-%m-%d')
    if not recent:
        recent = [
            o for o in opportunities
            if o.get('reported_date', '') == today or o.get('discovered_at', '')[:10] == today
        ]

    # If still no recent, use top opportunities (for initial setup / testing)
    if not recent:
        print("⚠️ No recent opportunities, using top 10 for notification")
        recent = opportunities[:10]

    print(f"📋 Found {len(recent)} opportunities to notify")

    # Classify
    hot = [o for o in recent if o.get('classification') == 'hot']
    warm = [o for o in recent if o.get('classification') == 'warm']
    cold = [o for o in recent if o.get('classification') == 'cold']

    print(f"   🔥 HOT: {len(hot)}")
    print(f"   ⚡ WARM: {len(warm)}")
    print(f"   ❄️ COLD: {len(cold)}")

    # Initialize notifier
    notifier = TelegramNotifier()
    dashboard_url = os.getenv('GITHUB_PAGES_URL', 'https://mirkotornani.github.io/ob1-serie-c-dev/')

    if not notifier.enabled:
        print("⚠️ Notifier not configured (missing TELEGRAM_BOT_TOKEN)")
        print("Notifications would have been:")
        for opp in hot[:3]:
            print(f"  🔥 HOT: {opp.get('player_name')} - {opp.get('ob1_score')}/100")
        return

    # Send notifications
    success = notifier.notify_scored_opportunities(recent, dashboard_url)

    if success:
        print(f"✅ Notifications sent successfully!")
    else:
        print(f"⚠️ Some notifications failed")

    # REPORT-001: Send PDF Report if available
    report_file = base_dir / 'docs' / 'report_latest.pdf'
    if report_file.exists():
        print(f"📄 Found PDF report: {report_file}")
        
        # Only send if recent (modified in last hour)
        mtime = datetime.fromtimestamp(report_file.stat().st_mtime)
        if (datetime.now() - mtime).total_seconds() < 3600:
            print("   Sending PDF report...")
            notifier.send_document(
                str(report_file), 
                caption=f"📄 <b>OB1 Scouting Report</b> - {datetime.now().strftime('%d/%m/%Y')}"
            )
        else:
            print("   Report too old, skipping send.")

if __name__ == "__main__":
    main()
