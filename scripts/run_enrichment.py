#!/usr/bin/env python3
import sys, os, json, time
from datetime import datetime
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from src.enricher_tm import TransfermarktEnricher

_JUNK_TERMS = [
    'transfermarkt', 'calciomercato', 'svincolati', 'la casa di c',
    'rádio', 'fischio finale', 'ultime notizie', 'football club',
    'web radio', 'il portale', 'il piccolo', 'management magazine',
    'next pro wiki', 'chiamarsi bomber', 'spareggi nazionali', 'spareggi',
    'stagione sportiva', 'sport news', 'giornale', 'magazine',
    'notiziario', 'dipartimento', 'interregionale', 'associazione',
    'sky sport', 'rappresentativa', 'juniores cup', 'parametro zero',
    'football italy', 'migliori giovani', 'giovani talenti', 'occasione serie',
    'notizie calcio', 'scuola superiore', 'tutto mercato', 'calciomercato live',
    'accordo collettivo', 'guardian', 'ultimo uomo', 'mediaset',
    'jugadores libres', 'ranking', 'classifica', 'tabella',
    'reserve league', 'liga profesional', 'selección', 'seleccion',
]

def _is_enrichable(name: str) -> bool:
    """Skip names that are clearly not individual players."""
    if not isinstance(name, str) or len(name) < 4 or '|' in name:
        return False
    n = name.lower()
    return not any(t in n for t in _JUNK_TERMS)
DATA_FILE = Path("data/opportunities.json")
DATA_FILE_DOCS = Path("docs/data.json")
MAX_RETRIES = 3
RETRY_DELAY = 3
RATE_LIMIT_DELAY = 5
def save_progress(data, opportunities, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(opportunities if isinstance(data, list) else data, f, ensure_ascii=False, indent=2)
def enrich_with_retry(enricher, player_name):
    for attempt in range(MAX_RETRIES):
        try:
            tm_data = enricher.enrich_player(player_name)
            return tm_data if tm_data else None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  ⚠️ Errore: {e}")
                time.sleep(RETRY_DELAY)
            else:
                raise e
def main():
    if not DATA_FILE.exists():
        print(f"File {DATA_FILE} non trovato!")
        return
    print(f"Loading {DATA_FILE}...")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    opportunities = data if isinstance(data, list) else data.get('opportunities', [])
    print(f"Trovate {len(opportunities)} opportunità.")
    enricher = TransfermarktEnricher()
    updated_count = 0
    errors = 0
    skipped = 0
    for i, opp in enumerate(opportunities):
        player_name = opp.get('player_name')
        if not _is_enrichable(player_name):
            skipped += 1
            continue
        # Skip only fully-enriched entries (tm_enriched=True).
        # Entries with partial data (market_value but no appearances, etc.) are re-enriched
        # so grounding can fill in the missing stats fields.
        if opp.get('tm_enriched') is True:
            skipped += 1
            continue
        print(f"\n[{i+1}/{len(opportunities)}] Arricchimento: {player_name}")
        try:
            tm_data = enrich_with_retry(enricher, player_name)
            if tm_data:
                # Normalize grounding key names → DB key names
                if tm_data.get('market_value_eur') and not tm_data.get('market_value'):
                    tm_data['market_value'] = tm_data['market_value_eur']
                if tm_data.get('market_value_text') and not tm_data.get('market_value_formatted'):
                    tm_data['market_value_formatted'] = tm_data['market_value_text']

                for key in ['nationality', 'second_nationality', 'foot', 'market_value', 'market_value_formatted', 'height_cm', 'birth_date', 'contract_expires', 'tm_url', 'agent', 'appearances', 'goals', 'assists', 'minutes_played']:
                    val = tm_data.get(key)
                    if val is not None:
                        opp[key] = val
                p = opp.setdefault('player_profile', {})
                for key in ['nationality', 'second_nationality', 'market_value', 'market_value_formatted', 'contract_expiry', 'foot', 'height_cm', 'tm_url', 'agent', 'appearances', 'goals', 'assists', 'minutes_played']:
                    val = tm_data.get(key)
                    if val is not None:
                        p[key] = val
                if not opp.get('age') and tm_data.get('birth_date'):
                    try:
                        age = datetime.now().year - int(str(tm_data['birth_date'])[:4])
                        if 10 <= age <= 60:
                            opp['age'] = age
                    except (ValueError, TypeError):
                        pass
                # Only lock as enriched when substantive data is present.
                # Entries with only nationality/agent stay unlocked for retry.
                has_substance = any(tm_data.get(k) for k in ['market_value', 'appearances', 'contract_expires', 'goals'])
                opp['tm_enriched'] = has_substance
                updated_count += 1
                nat_str = tm_data.get('nationality', 'N/A')
                if tm_data.get('second_nationality'):
                    nat_str += f" / {tm_data.get('second_nationality')}"
                mv_str = tm_data.get('market_value_formatted') or tm_data.get('market_value_text', 'N/A')
                print(f"  ✅ {nat_str} | {mv_str} | apps={tm_data.get('appearances','?')}")
                if updated_count % 5 == 0:
                    save_progress(data, opportunities, DATA_FILE)
                    print("  💾 Salvataggio...")
                time.sleep(RATE_LIMIT_DELAY)
            else:
                print("  ⚠️ Nessun dato trovato")
        except Exception as e:
            print(f"  ❌ Errore: {e}")
            errors += 1
    if updated_count > 0:
        print(f"\nSalvataggio finale ({updated_count})...")
        save_progress(data, opportunities, DATA_FILE)
        save_progress(data, opportunities, DATA_FILE_DOCS)
    else:
        print("\nNessun aggiornamento.")
    print(f"\nTotale: {len(opportunities)} | Aggiornati: {updated_count} | Saltati: {skipped} | Errori: {errors}")
if __name__ == "__main__":
    main()
