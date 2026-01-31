# SCRAPER-002: Tavily-Powered Scraper

## Metadata
- **ID**: SCRAPER-002
- **Priority**: CRITICAL
- **Status**: In Progress
- **Replaces**: Current Serper-based scraper

## Obiettivo
Sostituire lo scraper basato su Serper con Tavily per ottenere:
- Contenuto completo degli articoli (non solo snippet)
- Migliore estrazione di nomi giocatori
- Output AI-ready per Gemini
- Free tier generoso (1000 ricerche/mese)

## Tavily vs Serper

| Feature | Serper | Tavily |
|---------|--------|--------|
| Output | Link + snippet 160 char | Full content extracted |
| AI-ready | No | Yes, optimized for LLMs |
| Free tier | No | 1000/month |
| Depth | Surface only | Can extract full articles |

## Architettura

```
Tavily Search API
       |
       v
  Extract content + metadata
       |
       v
  Gemini 2.0 Flash (parsing)
       |
       v
  Structured opportunities JSON
       |
       v
  data/opportunities.json
```

## Query Strategy

### Primary Queries (High Signal)
```python
QUERIES = [
    # Svincolati e rescissioni
    "Serie C calciatore svincolato 2026",
    "Lega Pro rescissione contratto giocatore",
    "Serie C parametro zero disponibile",

    # Prestiti
    "Serie C prestito gennaio 2026",
    "Serie B esubero disponibile prestito Serie C",

    # Talenti
    "Serie D talento interesse Serie C",
    "Primavera svincolato Serie C",

    # News mercato
    "calciomercato Serie C ultime notizie",
    "TuttoC mercato giocatori",
]
```

### News Sources (Whitelist)
- tuttoc.com
- tuttolegapro.com
- calciomercato.com
- tuttomercatoweb.com
- transfermarkt.it
- gazzetta.it (sezione Lega Pro)

## Tavily API Usage

```python
from tavily import TavilyClient

client = TavilyClient(api_key=TAVILY_API_KEY)

response = client.search(
    query="Serie C svincolato centrocampista",
    search_depth="advanced",  # Deep extraction
    include_domains=["tuttoc.com", "calciomercato.com"],
    max_results=10,
    include_raw_content=True  # Full article text
)
```

## Gemini Parsing

Use Gemini 2.0 Flash to extract structured data:

```python
EXTRACTION_PROMPT = '''
Analizza questo articolo di calciomercato e estrai informazioni sui giocatori menzionati.

Per ogni giocatore trovato, estrai:
- nome_completo: Nome e cognome
- eta: Eta del giocatore (se menzionata)
- ruolo: Ruolo (portiere, difensore, centrocampista, attaccante, etc)
- tipo_opportunita: svincolato | rescissione | prestito | scadenza | mercato
- club_attuale: Club attuale o ultimo club
- club_precedenti: Lista club precedenti
- dettagli: Breve descrizione della situazione

Rispondi in JSON array. Se non ci sono giocatori rilevanti, rispondi [].

ARTICOLO:
{content}
'''
```

## Output Schema

```json
{
  "id": "opp_abc123",
  "player_name": "Marco Rossi",
  "age": 26,
  "role": "CC",
  "role_name": "Centrocampista Centrale",
  "opportunity_type": "svincolato",
  "current_club": "Ex Pescara",
  "previous_clubs": ["Pescara", "Reggiana", "Modena"],
  "description": "Centrocampista esperto, svincolato dopo la rescissione con il Pescara",
  "source_url": "https://tuttoc.com/...",
  "source_name": "TuttoC",
  "discovered_at": "2026-01-31T22:00:00",
  "raw_content": "..."
}
```

## Rate Limiting

- Tavily free: 1000 req/month
- Strategy: 10 queries x 10 results = 100 articles/run
- Run frequency: Every 6 hours = 4 runs/day = ~120 runs/month
- Budget: ~8-10 queries per run to stay within limits

## Implementation Steps

1. [x] Create spec
2. [ ] Add TAVILY_API_KEY to GitHub secrets
3. [ ] Create new scraper_tavily.py
4. [ ] Integrate Gemini for parsing
5. [ ] Update run_ingest.py
6. [ ] Test locally
7. [ ] Deploy to GitHub Actions

## Success Metrics

| Metric | Current (Serper) | Target (Tavily) |
|--------|------------------|-----------------|
| Opportunities/run | 0-5 | 15-30 |
| Player name accuracy | ~30% | 90%+ |
| Content quality | Snippet only | Full article |
| False positives | High | Low (Gemini filter) |
