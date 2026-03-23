# OB1 Serie C Radar

## Stack
- Python 3.12
- Gemini API (google-genai) per RAG e File Search
- Tavily per web scraping avanzato
- python-telegram-bot per il bot Telegram
- YAML per configurazione

## Struttura
- `src/` - Codice sorgente principale (agent, scraper, scoring, DNA, ecc.)
- `bot/` - Bot Telegram
- `config/` - File di configurazione YAML
- `data/` - Dati locali (CSV, JSON)
- `scripts/` - Script di utilita e automazione
- `workers/` - Worker per task asincroni
- `docs/` - Documentazione

## Convenzioni
- Script Python eseguibili in `src/` con `if __name__ == "__main__"`
- Configurazione tramite `.env` e file YAML in `config/`
- Encoding: usa sempre `PYTHONIOENCODING=utf-8` quando esegui script Python
- Git: branch `main`, commit in italiano o inglese con prefisso semantico

## Comandi utili
```bash
# Test scraper
PYTHONIOENCODING=utf-8 python src/scraper.py

# Ingest dati
PYTHONIOENCODING=utf-8 python src/ingest.py

# Avvia bot
PYTHONIOENCODING=utf-8 python bot/main.py
```
