#!/usr/bin/env python3
"""
OB1 Serie C - Telegram Bot
Interfaccia mobile per direttori sportivi
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from io import TextIOWrapper

# Force UTF-8 output
sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

load_dotenv()

# Telegram imports
try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️ python-telegram-bot non installato")
    print("   pip install python-telegram-bot")

# Import agent
import sys
from pathlib import Path

# Aggiungi la cartella src al path
bot_dir = Path(__file__).parent.resolve()
src_dir = bot_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from agent import OB1Agent

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class OB1TelegramBot:
    """Bot Telegram per OB1"""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN mancante nel .env")

        # Agent per utente (semplificato - in prod usare db)
        self.agents: dict[int, OB1Agent] = {}

        # Whitelist utenti autorizzati (opzionale)
        self.allowed_users = self._load_allowed_users()

    def _load_allowed_users(self) -> set:
        """Carica lista utenti autorizzati"""
        users_str = os.getenv("ALLOWED_TELEGRAM_USERS", "")
        if users_str:
            return set(int(u.strip()) for u in users_str.split(",") if u.strip())
        return set()  # Empty = tutti autorizzati

    def _get_agent(self, user_id: int) -> OB1Agent:
        """Recupera o crea agent per utente"""
        if user_id not in self.agents:
            self.agents[user_id] = OB1Agent()
        return self.agents[user_id]

    def _is_authorized(self, user_id: int) -> bool:
        """Verifica autorizzazione utente"""
        if not self.allowed_users:
            return True  # No whitelist = tutti OK
        return user_id in self.allowed_users

    # =========================================================================
    # HANDLERS
    # =========================================================================

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /start"""

        user = update.effective_user

        if not self._is_authorized(user.id):
            await update.message.reply_text(
                f"⛔ Non sei autorizzato ad usare questo bot.\nIl tuo ID: {user.id}"
            )
            return

        welcome = f"""
🎯 *OB1 Serie C Radar*

Ciao {user.first_name}! Sono il tuo assistente per lo scouting in Serie C e Serie D.

*Cosa posso fare:*
• Trovare giocatori svincolati
• Analizzare profili con agente e statistiche
• Cercare per agenzia o stats stagionali
• Ricerca avanzata per criteri multipli

*Comandi rapidi:*
/svincolati - Lista svincolati disponibili
/player <nome> - Analisi giocatore (con agente e stats)
/agent <agenzia> - Trova giocatori di un'agenzia
/stats <min_presenze> - Filtra per statistiche stagionali
/summary - Riepilogo mercato
/cerca <criteri> - Ricerca avanzata
/help - Guida completa

Oppure scrivimi direttamente cosa cerchi! 💬
        """

        await update.message.reply_text(welcome, parse_mode="Markdown")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /help"""

        help_text = """
📖 *Guida OB1 - Comandi Aggiornati*

*Ricerche base:*
• `/svincolati` - tutti gli svincolati
• `/svincolati difensore` - svincolati per ruolo
• `/player Rossi` - info completa su un giocatore (con agente e stats)

*Nuovi filtri (DATA-003):*
• `/agent Esse Sports` - giocatori di un'agenzia specifica
• `/stats 15` - giocatori con almeno 15 presenze
• `/stats 10 centrocampista` - filtra per stats e ruolo

*Ricerca avanzata:*
`/cerca centrocampista under 25 con 20+ presenze`

*Domande libere:*
Puoi chiedermi qualsiasi cosa, ad esempio:
- "Chi sono i migliori svincolati under 23?"
- "Trova giocatori dell'agenzia CAA Base Ltd"
- "Chi ha fatto almeno 20 presenze quest'anno?"

*Tip:* I dati includono ora agente, presenze, gol, assist e minuti giocati!
        """

        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def svincolati(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /svincolati"""

        if not self._is_authorized(update.effective_user.id):
            return

        role = " ".join(context.args) if context.args else None

        await update.message.reply_text("🔍 Cerco svincolati...")

        agent = self._get_agent(update.effective_user.id)
        response = agent.find_svincolati(role=role)

        await self._send_long_message(update, response)

    async def player(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /player <nome>"""

        if not self._is_authorized(update.effective_user.id):
            return

        if not context.args:
            await update.message.reply_text(
                "❓ Specifica il nome del giocatore\nEs: `/player Nicolas Viola`",
                parse_mode="Markdown",
            )
            return

        player_name = " ".join(context.args)

        await update.message.reply_text(f"🔍 Cerco info su {player_name}...")

        agent = self._get_agent(update.effective_user.id)
        response = agent.analyze_player(player_name)

        await self._send_long_message(update, response)

    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /summary"""

        if not self._is_authorized(update.effective_user.id):
            return

        await update.message.reply_text("📊 Genero riepilogo mercato...")

        agent = self._get_agent(update.effective_user.id)
        response = agent.market_summary()

        await self._send_long_message(update, response)

    async def cerca(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /cerca <criteri>"""

        if not self._is_authorized(update.effective_user.id):
            return

        if not context.args:
            await update.message.reply_text(
                "❓ Specifica i criteri di ricerca\n"
                "Es: `/cerca difensore centrale under 25`",
                parse_mode="Markdown",
            )
            return

        criteria = " ".join(context.args)

        await update.message.reply_text(f"🔍 Cerco: {criteria}...")

        agent = self._get_agent(update.effective_user.id)
        response = agent.query(f"Cerca giocatori con questi criteri: {criteria}")

        await self._send_long_message(update, response)

    async def agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /agent <nome_agenzia>"""

        if not self._is_authorized(update.effective_user.id):
            return

        if not context.args:
            await update.message.reply_text(
                "❓ Specifica il nome dell'agenzia\nEs: `/agent Esse Sports`",
                parse_mode="Markdown",
            )
            return

        agent_name = " ".join(context.args)

        await update.message.reply_text(
            f"🔍 Cerco giocatori dell'agenzia: {agent_name}..."
        )

        agent = self._get_agent(update.effective_user.id)
        response = agent.query(
            f"Trova tutti i giocatori rappresentati dall'agenzia '{agent_name}'. Mostra ruolo, età, valore di mercato e situazione contrattuale."
        )

        await self._send_long_message(update, response)

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /stats <min_presenze> [ruolo]"""

        if not self._is_authorized(update.effective_user.id):
            return

        if not context.args:
            await update.message.reply_text(
                "❓ Specifica il numero minimo di presenze\n"
                "Es: `/stats 15` o `/stats 10 centrocampista`",
                parse_mode="Markdown",
            )
            return

        try:
            min_appearances = int(context.args[0])
        except ValueError:
            await update.message.reply_text(
                "❌ Il primo parametro deve essere un numero (presenze minime)"
            )
            return

        role = " ".join(context.args[1:]) if len(context.args) > 1 else None

        role_text = f" nel ruolo di {role}" if role else ""
        await update.message.reply_text(
            f"🔍 Cerco giocatori con almeno {min_appearances} presenze{role_text}..."
        )

        agent = self._get_agent(update.effective_user.id)

        query = f"Trova giocatori con almeno {min_appearances} presenze stagionali"
        if role:
            query += f" nel ruolo di {role}"
        query += ". Mostra presenze, gol, assist e minuti giocati."

        response = agent.query(query)

        await self._send_long_message(update, response)

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler messaggi liberi"""

        if not self._is_authorized(update.effective_user.id):
            return

        user_message = update.message.text

        # Typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )

        agent = self._get_agent(update.effective_user.id)
        response = agent.query(user_message)

        await self._send_long_message(update, response)

    async def _send_long_message(self, update: Update, text: str):
        """Invia messaggio, splitta se troppo lungo"""

        MAX_LENGTH = 4000

        if len(text) <= MAX_LENGTH:
            await update.message.reply_text(text)
            return

        # Split by paragraphs
        parts = []
        current = ""

        for line in text.split("\n"):
            if len(current) + len(line) + 1 > MAX_LENGTH:
                parts.append(current)
                current = line
            else:
                current += "\n" + line if current else line

        if current:
            parts.append(current)

        for i, part in enumerate(parts):
            await update.message.reply_text(
                f"{part}\n\n_({i + 1}/{len(parts)})_", parse_mode="Markdown"
            )

    # =========================================================================
    # RUN
    # =========================================================================

    def run(self):
        """Avvia il bot"""

        print("🤖 Avvio OB1 Telegram Bot...")

        app = Application.builder().token(self.token).build()

        # Commands
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("svincolati", self.svincolati))
        app.add_handler(CommandHandler("player", self.player))
        app.add_handler(CommandHandler("agent", self.agent))
        app.add_handler(CommandHandler("stats", self.stats))
        app.add_handler(CommandHandler("summary", self.summary))
        app.add_handler(CommandHandler("cerca", self.cerca))

        # Free text
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler)
        )

        # Set commands menu
        async def set_commands(app):
            await app.bot.set_my_commands(
                [
                    BotCommand("start", "Inizia"),
                    BotCommand("svincolati", "Lista svincolati"),
                    BotCommand("player", "Info giocatore"),
                    BotCommand("agent", "Cerca per agenzia"),
                    BotCommand("stats", "Filtra per statistiche"),
                    BotCommand("summary", "Riepilogo mercato"),
                    BotCommand("cerca", "Ricerca avanzata"),
                    BotCommand("help", "Guida"),
                ]
            )

        app.post_init = set_commands

        print("✅ Bot pronto!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    if not TELEGRAM_AVAILABLE:
        print("❌ Installa python-telegram-bot:")
        print("   pip install python-telegram-bot")
        exit(1)

    bot = OB1TelegramBot()
    bot.run()
