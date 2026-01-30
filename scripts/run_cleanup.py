#!/usr/bin/env python3
"""
OB1 Scout - Weekly Cleanup
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from ingest import OB1Ingest


def main():
    print("🧹 Running weekly cleanup...")

    try:
        ingest = OB1Ingest()
        ingest.cleanup_old_files(days_to_keep=7)
        print("✅ Cleanup completato")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")


if __name__ == "__main__":
    main()
