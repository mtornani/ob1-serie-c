#!/usr/bin/env python3
"""
OB1 Scout - Send Telegram Notifications
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from notifier import TelegramNotifier


def main():
    print("📢 Sending Telegram notifications...")

    # Load opportunities
    data_file = Path(__file__).parent.parent / 'data' / 'opportunities.json'
    if not data_file.exists():
        print("No data file found")
        return

    opportunities = json.loads(data_file.read_text())

    # Get recent (last 6 hours)
    cutoff = (datetime.now() - timedelta(hours=6)).isoformat()
    recent = [o for o in opportunities if o.get('discovered_at', '') > cutoff]

    if not recent:
        print("No new opportunities to notify")
        return

    print(f"Found {len(recent)} recent opportunities")

    # Send notification
    notifier = TelegramNotifier()
    dashboard_url = os.getenv('GITHUB_PAGES_URL', '')

    if notifier.enabled:
        success = notifier.notify_new_opportunities(recent, dashboard_url)
        print(f"Notification sent: {success}")
    else:
        print("Notifier not configured, skipping")


if __name__ == "__main__":
    main()
