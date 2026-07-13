#!/usr/bin/env python3
"""
Transfermarkt direct parser — free, no LLM, no daily cap.

Reads the real Transfermarkt profile page and extracts structured, authoritative
data (market value, birth date, position, nationality, foot, agent, club,
contract). This replaces Gemini-grounded enrichment: the data is read straight
from the source, so it's genuinely verified — and it costs nothing.
"""
import re
import time
import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
}
_BASE = 'https://www.transfermarkt.it'
_TIMEOUT = 20


def _get(url: str, retries: int = 2) -> Optional[str]:
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                if r.status != 200:
                    return None
                return r.read().decode('utf-8', 'ignore')
        except Exception as e:
            # Retry transient server/network hiccups (timeouts, 5xx) once or twice.
            transient = any(t in str(e).lower() for t in ('timed out', 'timeout', '504', '503', '502', 'reset'))
            if transient and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f"  [TM FETCH ERROR] {url[:60]}: {e}")
            return None


def _clean(s: str) -> str:
    s = re.sub(r'<[^>]+>', ' ', s)
    s = s.replace('\xa0', ' ').replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def _date_it_to_iso(s: str) -> Optional[str]:
    m = re.search(r'(\d{2})/(\d{2})/(\d{4})', s)
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{y}-{mo}-{d}"


def search_profile_url(name: str) -> Optional[str]:
    """Find a player's Transfermarkt profile URL via TM's own search (free)."""
    q = urllib.parse.quote(name)
    html = _get(f"{_BASE}/schnellsuche/ergebnis/schnellsuche?query={q}")
    if not html:
        return None
    m = re.search(r'href="(/[^"]+/profil/spieler/\d+)"', html)
    return _BASE + m.group(1) if m else None


def parse_profile(html: str, tm_url: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {'tm_url': tm_url}

    # Market value: "2,80 mln €" / "150 mila €"
    mv = re.search(r'data-header__market-value-wrapper[^>]*>(.*?)</a>', html, re.DOTALL)
    if mv:
        txt = _clean(mv.group(1))
        num = re.search(r'([\d.,]+)\s*(mln|mila)?\s*€', txt)
        if num:
            raw, unit = num.group(1), num.group(2)
            data['market_value_text'] = f"{raw} {unit} €".replace('  ', ' ').strip()
            try:
                val = float(raw.replace('.', '').replace(',', '.'))
                if unit == 'mln':
                    val *= 1_000_000
                elif unit == 'mila':
                    val *= 1_000
                data['market_value_eur'] = int(val)
            except ValueError:
                pass

    # Personal-data table: label/value pairs
    pairs = re.findall(
        r'info-table__content--regular">(.*?)</span>\s*'
        r'<span class="info-table__content info-table__content--bold">(.*?)</span>',
        html, re.DOTALL)
    kv = {_clean(k).rstrip(':').lower(): _clean(v) for k, v in pairs}

    if 'nato il' in kv:
        bd = _date_it_to_iso(kv['nato il'])
        if bd:
            data['birth_date'] = bd
    if 'nazionalità' in kv:
        data['nationality'] = kv['nazionalità'].split('  ')[0].strip() or None
    if 'altezza' in kv:
        h = re.search(r'(\d)[,.](\d{2})', kv['altezza'])
        if h:
            data['height_cm'] = int(h.group(1) + h.group(2))
    if 'piede' in kv:
        data['foot'] = kv['piede'] or None
    if 'posizione' in kv:
        # "Centrocampo - Centrocampista" -> take specific role
        data['main_position'] = kv['posizione'].split(' - ')[-1].strip() or None
    if 'procuratore' in kv:
        data['agent'] = kv['procuratore'] or None
    if 'squadra attuale' in kv:
        data['current_club'] = kv['squadra attuale'] or None
    if 'scadenza' in kv:
        exp = _date_it_to_iso(kv['scadenza'])
        if exp:
            data['contract_expires'] = exp

    # drop empty/placeholder values
    return {k: v for k, v in data.items() if v not in (None, '', '-')}


def enrich(name: str, tm_url: Optional[str] = None) -> Dict[str, Any]:
    """Enrich one player from Transfermarkt. Uses the known profile URL if we
    have it, otherwise searches by name. Returns {} if not found."""
    url = tm_url if (isinstance(tm_url, str) and 'transfermarkt' in tm_url) else None
    if url:
        html = _get(url)
        if html and 'info-table__content' in html:
            data = parse_profile(html, url)
            if data.get('birth_date') or data.get('market_value_text'):
                return data
        # Stored URL was wrong/stale/empty — fall through to a fresh search.

    found = search_profile_url(name)
    if not found:
        return {}
    html = _get(found)
    if not html or 'info-table__content' not in html:
        return {}
    return parse_profile(html, found)


if __name__ == "__main__":
    import sys
    tests = [
        ("Sergej Levak", "https://www.transfermarkt.it/sergej-levak/profil/spieler/892165"),
        ("Marco Capuano", None),  # via search
    ]
    for nm, u in tests:
        print(f"\n=== {nm} ===")
        print(json.dumps(enrich(nm, u), indent=2, ensure_ascii=False))
        time.sleep(1)
