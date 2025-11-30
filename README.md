# 🎯 OB1 Serie C Radar v2

**Scout AI per Serie C e Serie D italiana** - Powered by Gemini File Search RAG

A differenza di un semplice aggregatore di notizie, OB1 v2 è un **agente conversazionale** che:
- Accumula conoscenza nel tempo (RAG su Gemini File Search)
- Risponde in linguaggio naturale
- Impara dai tuoi criteri di ricerca
- Costa quasi nulla (~$5/mese)

## 🚀 Quick Start

### 1. Clona e configura

```bash
git clone https://github.com/tuousername/ob1-serie-c.git
cd ob1-serie-c
cp .env.example .env
```

### 2. Ottieni le API keys

| Servizio | Link | Costo |
|----------|------|-------|
| Serper.dev | [serper.dev](https://serper.dev) | 2500 query gratis, poi $50/50k |
| Gemini API | [aistudio.google.com](https://aistudio.google.com/apikey) | Gratis (limiti generosi) |
| Telegram Bot | [@BotFather](https://t.me/BotFather) | Gratis |

Inserisci le key nel file `.env`

### 3. Installa e testa

```bash
pip install -r requirements.txt

# Test scraper
cd src
python scraper.py

# Prima ingest (popola il database)
python ingest.py

# Test agent interattivo
python agent.py
```

### 4. Avvia Telegram Bot (opzionale)

```bash
cd bot
python telegram_bot.py
```

## 📱 Come usarlo

### Via Terminale

```
Tu: Chi sono i centrocampisti svincolati under 25?

🤖 OB1: Ecco i centrocampisti svincolati under 25 disponibili:

1. **Marco Rossi** (23 anni)
   - Ruolo: Centrocampista centrale
   - Ex club: Pescara
   - Presenze 2024/25: 12
   - Note: Rescissione consensuale il 15/01
   - Fonte: Calciomercato.com

2. **Luca Bianchi** (24 anni)
   ...
```

### Via Telegram

```
/svincolati centrocampista
/player Nicolas Viola
/cerca difensore mancino under 28
/summary
```

Oppure scrivi liberamente:
> "Ci sono esterni sinistri con esperienza Serie B?"

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────────┐
│                    SCRAPER (ogni 6h)                    │
│  • Serper API → notizie mercato                         │
│  • Parsing strutturato → MarketOpportunity             │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                 GEMINI FILE SEARCH                       │
│  • Auto-chunking dei documenti                          │
│  • Embedding semantici                                   │
│  • Storage persistente (~$0.15/MB una tantum)           │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                      AGENT                               │
│  • Query in linguaggio naturale                         │
│  • Retrieval semantico dal knowledge base               │
│  • Risposte con citazioni                               │
│  • Memoria conversazionale                               │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                    INTERFACES                            │
│  • CLI interattiva                                       │
│  • Telegram Bot                                          │
│  • (futuro) Web UI                                       │
└─────────────────────────────────────────────────────────┘
```

## 💰 Costi reali

| Componente | Costo mensile stimato |
|------------|----------------------|
| Serper (search) | ~$0-5 (2500 gratis) |
| Gemini File Search (storage) | $0 |
| Gemini File Search (indexing) | ~$0.50 una tantum |
| Gemini Flash (query) | ~$1-3 |
| **Totale** | **~$5/mese** |

Confronto: un setup RAG tradizionale (Pinecone + OpenAI) costa $50-100+/mese.

## 📂 Struttura progetto

```
ob1-serie-c/
├── .github/workflows/
│   ├── ingest.yml       # Cron ogni 6h
│   └── cleanup.yml      # Pulizia settimanale
├── src/
│   ├── models.py        # Data structures
│   ├── scraper.py       # News collection
│   ├── ingest.py        # Upload to Gemini
│   └── agent.py         # Query interface
├── bot/
│   └── telegram_bot.py  # Mobile interface
├── requirements.txt
├── .env.example
└── README.md
```

## 🔧 Configurazione avanzata

### Aggiungere fonti di scraping

Modifica `QUERIES` in `src/scraper.py`:

```python
QUERIES = {
    OpportunityType.SVINCOLATO: [
        '"Serie C" "parametro zero"',
        # Aggiungi nuove query qui
    ],
}
```

### Personalizzare il comportamento dell'agent

Modifica `SYSTEM_PROMPT` in `src/agent.py`:

```python
SYSTEM_PROMPT = """Sei OB1, assistente scouting...
# Aggiungi istruzioni specifiche per il tuo club
"""
```

### Limitare accesso Telegram

Nel `.env`:
```
ALLOWED_TELEGRAM_USERS=123456789,987654321
```

## 🚧 Roadmap

- [ ] Integrazione Transfermarkt per valutazioni
- [ ] Export PDF report settimanale  
- [ ] Web UI con React
- [ ] Notifiche push per opportunità top
- [ ] Tracking storico giocatori
- [ ] Comparazione profili

## 📄 License

MIT - Usa come vuoi, citami se ti va.

---

Made with ⚽ for Serie C scouting by [Mirko]
