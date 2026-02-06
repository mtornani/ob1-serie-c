#!/usr/bin/env python3
"""
OB1 Serie C - Date Filter Utility
Extracts real article dates from URLs and filters stale content.
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple


# Maximum age in days for an article to be considered fresh
MAX_ARTICLE_AGE_DAYS = 60


def extract_date_from_url(url: str) -> Optional[datetime]:
    """
    Extract publication date from URL patterns.
    Many news sites embed dates in their URLs.

    Examples:
    - /2022/01/01-... → 2022-01-01
    - /2026/02/05/... → 2026-02-05
    - /news/20260205-... → 2026-02-05
    - /-88425267/ → None (article ID, not date)
    """
    if not url:
        return None

    # Pattern 1: /YYYY/MM/DD/ or /YYYY/MM/DD-
    match = re.search(r'/(\d{4})/(\d{2})/(\d{2})[-/]', url)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # Pattern 2: /YYYY-MM-DD/ or -YYYY-MM-DD-
    match = re.search(r'[/-](\d{4})-(\d{2})-(\d{2})[/-]', url)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # Pattern 3: /YYYYMMDD- or /YYYYMMDD/
    match = re.search(r'/(\d{4})(\d{2})(\d{2})[-/]', url)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # Pattern 4: date in query string ?date=YYYY-MM-DD
    match = re.search(r'[?&]date=(\d{4})-(\d{2})-(\d{2})', url)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    return None


def is_article_fresh(url: str, max_age_days: int = MAX_ARTICLE_AGE_DAYS) -> Tuple[bool, Optional[str]]:
    """
    Check if an article is fresh enough to be included.

    Returns:
        (is_fresh, reason) - reason explains why it was rejected if not fresh
    """
    article_date = extract_date_from_url(url)

    if article_date is None:
        # Can't determine date from URL - allow it but flag
        return True, None

    now = datetime.now()
    age = now - article_date

    if age.days > max_age_days:
        return False, f"Article from {article_date.strftime('%Y-%m-%d')} is {age.days} days old (max {max_age_days})"

    if article_date > now + timedelta(days=1):
        # Future date - probably parsing error
        return False, f"Article date {article_date.strftime('%Y-%m-%d')} is in the future"

    return True, None


def filter_fresh_results(results: list, url_key: str = 'source_url', max_age_days: int = MAX_ARTICLE_AGE_DAYS) -> list:
    """
    Filter a list of results to keep only fresh articles.

    Args:
        results: List of dicts with URL field
        url_key: Key name for the URL field
        max_age_days: Maximum article age

    Returns:
        Filtered list with only fresh articles
    """
    fresh = []
    stale_count = 0

    for item in results:
        url = item.get(url_key, '')
        is_fresh, reason = is_article_fresh(url, max_age_days)

        if is_fresh:
            fresh.append(item)
        else:
            stale_count += 1
            player = item.get('player_name', 'Unknown')
            print(f"  [STALE] {player}: {reason}")

    if stale_count > 0:
        print(f"  Filtered out {stale_count} stale articles")

    return fresh


def clean_opportunities_data(opportunities: list, max_age_days: int = MAX_ARTICLE_AGE_DAYS) -> list:
    """
    Clean existing opportunities data by removing stale entries.
    """
    return filter_fresh_results(opportunities, url_key='source_url', max_age_days=max_age_days)


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    test_urls = [
        "https://www.tuttosport.com/news/calcio/calciomercato/2022/01/01-88425267/test",  # 2022 - STALE
        "https://www.tuttoc.com/news/2026/02/05/mercato-serie-c",  # Recent - OK
        "https://www.transfermarkt.it/serie-c-girone-a/transfers/wettbewerb/IT3A",  # No date
        "https://example.com/20260201-news-title",  # Recent - OK
        "https://example.com/2019/06/15/old-news",  # 2019 - STALE
    ]

    print("Testing date extraction:")
    for url in test_urls:
        date = extract_date_from_url(url)
        is_fresh, reason = is_article_fresh(url)
        status = "FRESH" if is_fresh else "STALE"
        print(f"  [{status}] {url[:60]}...")
        if date:
            print(f"         Date: {date.strftime('%Y-%m-%d')}")
        if reason:
            print(f"         Reason: {reason}")
