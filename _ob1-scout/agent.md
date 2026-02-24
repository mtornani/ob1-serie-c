OB1 World Scout - Agent Context

Project: Global U20 football talent radar
Bot: @Ob1WorldBot (Telegram)
Dashboard: https://mtornani.github.io/ob1-scout/
Repo: https://github.com/mtornani/ob1-scout

Architecture:
  run.py → scrapes 50+ sources (Africa, Asia, S. America)
  docs/ → PWA dashboard (GitHub Pages)
  workers/telegram-bot/ → Cloudflare Workers bot
  .github/workflows/ → Automation (every 6h scrape + deploy)

Data flow:
  run.py → docs/data.json → Dashboard + Bot reads it

Secrets (never commit):
  ANYCRAWL_API_KEY → for run.py scraper
  TELEGRAM_BOT_TOKEN → for @Ob1WorldBot

Development Rules:
  1. Keep files under 100 lines
  2. No frameworks, no databases
  3. GitHub Pages only (free hosting)
  4. Revenue > code quality
  5. Manual processes are fine initially
