#!/usr/bin/env python3
"""
OB1 Serie C - Ingest to Gemini File Search
Alimenta il File Search Store con documenti strutturati
"""

import os
import time
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

# Gemini imports
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ google-genai non installato. Esegui: pip install google-genai")

from models import MarketOpportunity, PlayerProfile
from scraper import OB1Scraper


class OB1Ingest:
    """Gestisce upload e indicizzazione su Gemini File Search"""

    STORE_NAME = "ob1-serie-c-knowledge"

    def __init__(self):
        if not GEMINI_AVAILABLE:
            raise ImportError("google-genai richiesto")

        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante nel .env")

        self.client = genai.Client(api_key=api_key)
        self.store = None

    # =========================================================================
    # STORE MANAGEMENT
    # =========================================================================

    def get_or_create_store(self) -> str:
        """Recupera o crea il File Search Store"""

        # Try to find existing store
        try:
            stores = list(self.client.file_search_stores.list())
            for store in stores:
                if self.STORE_NAME in store.display_name:
                    print(f"✅ Store esistente trovato: {store.name}")
                    self.store = store
                    return store.name
        except Exception as e:
            print(f"⚠️ Errore listing stores: {e}")

        # Create new store
        print(f"📦 Creazione nuovo store: {self.STORE_NAME}")
        self.store = self.client.file_search_stores.create(
            config={'display_name': self.STORE_NAME}
        )
        print(f"✅ Store creato: {self.store.name}")
        return self.store.name

    def list_store_files(self) -> List[str]:
        """Lista file nello store"""

        if not self.store:
            self.get_or_create_store()

        try:
            files = list(self.client.file_search_stores.list_files(
                file_search_store_name=self.store.name
            ))
            return [f.name for f in files]
        except Exception as e:
            print(f"⚠️ Errore listing files: {e}")
            return []

    # =========================================================================
    # DOCUMENT INGESTION
    # =========================================================================

    def ingest_opportunities(self, opportunities: List[MarketOpportunity]) -> int:
        """Carica opportunità nel File Search Store"""

        store_name = self.get_or_create_store()
        uploaded = 0

        # Group by date for batch documents
        today = datetime.now().strftime("%Y-%m-%d")

        # Create consolidated document
        doc_content = self._create_opportunities_document(opportunities)

        # Save temp file
        temp_path = Path(f"/tmp/ob1_opportunities_{today}.md")
        temp_path.write_text(doc_content, encoding='utf-8')

        print(f"📄 Uploading: {temp_path.name} ({len(doc_content)} chars)")

        try:
            # Upload to store
            operation = self.client.file_search_stores.upload_to_file_search_store(
                file=str(temp_path),
                file_search_store_name=store_name,
                config={'display_name': f'opportunities_{today}'}
            )

            # Wait for indexing
            print("⏳ Indicizzazione in corso...")
            while not operation.done:
                time.sleep(3)
                operation = self.client.operations.get(operation)

            print(f"✅ Documento indicizzato")
            uploaded = len(opportunities)

        except Exception as e:
            print(f"❌ Errore upload: {e}")

        finally:
            # Cleanup
            if temp_path.exists():
                temp_path.unlink()

        return uploaded

    def ingest_player_profiles(self, profiles: List[PlayerProfile]) -> int:
        """Carica profili giocatori nel File Search Store"""

        store_name = self.get_or_create_store()
        uploaded = 0

        # Create consolidated document
        doc_content = self._create_profiles_document(profiles)

        # Save temp file
        today = datetime.now().strftime("%Y-%m-%d")
        temp_path = Path(f"/tmp/ob1_profiles_{today}.md")
        temp_path.write_text(doc_content, encoding='utf-8')

        print(f"📄 Uploading profiles: {temp_path.name}")

        try:
            operation = self.client.file_search_stores.upload_to_file_search_store(
                file=str(temp_path),
                file_search_store_name=store_name,
                config={'display_name': f'profiles_{today}'}
            )

            print("⏳ Indicizzazione profili...")
            while not operation.done:
                time.sleep(3)
                operation = self.client.operations.get(operation)

            print(f"✅ Profili indicizzati")
            uploaded = len(profiles)

        except Exception as e:
            print(f"❌ Errore upload profili: {e}")

        finally:
            if temp_path.exists():
                temp_path.unlink()

        return uploaded

    # =========================================================================
    # DOCUMENT FORMATTING
    # =========================================================================

    def _create_opportunities_document(self, opportunities: List[MarketOpportunity]) -> str:
        """Crea documento markdown con tutte le opportunità"""

        lines = [
            "# OB1 SERIE C - OPPORTUNITÀ DI MERCATO",
            f"Aggiornamento: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Totale opportunità: {len(opportunities)}",
            "",
            "---",
            ""
        ]

        # Group by type
        by_type = {}
        for opp in opportunities:
            type_key = opp.opportunity_type.value
            if type_key not in by_type:
                by_type[type_key] = []
            by_type[type_key].append(opp)

        # Write each section
        for type_name, opps in by_type.items():
            lines.append(f"## {type_name.upper()} ({len(opps)} opportunità)")
            lines.append("")

            for opp in opps:
                lines.append(opp.to_document())
                lines.append("")
                lines.append("---")
                lines.append("")

        return "\n".join(lines)

    def _create_profiles_document(self, profiles: List[PlayerProfile]) -> str:
        """Crea documento markdown con profili giocatori"""

        lines = [
            "# OB1 SERIE C - DATABASE GIOCATORI",
            f"Aggiornamento: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Totale profili: {len(profiles)}",
            "",
            "---",
            ""
        ]

        for profile in profiles:
            lines.append(profile.to_document())
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # CLEANUP
    # =========================================================================

    def cleanup_old_files(self, days_to_keep: int = 7):
        """Rimuove file più vecchi di N giorni"""

        if not self.store:
            self.get_or_create_store()

        cutoff = datetime.now().timestamp() - (days_to_keep * 86400)
        removed = 0

        try:
            files = self.client.file_search_stores.list_files(
                file_search_store_name=self.store.name
            )

            for f in files:
                # Check file age from name (opportunities_2025-01-15.md)
                try:
                    date_str = f.display_name.split('_')[-1].replace('.md', '')
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")

                    if file_date.timestamp() < cutoff:
                        self.client.file_search_stores.delete_file(
                            file_search_store_name=self.store.name,
                            file_name=f.name
                        )
                        print(f"🗑️ Rimosso: {f.display_name}")
                        removed += 1
                except:
                    continue

            print(f"✅ Cleanup completato: {removed} file rimossi")

        except Exception as e:
            print(f"⚠️ Errore cleanup: {e}")

        return removed


# =============================================================================
# PIPELINE
# =============================================================================

def run_ingest_pipeline():
    """Pipeline completa: scrape → ingest"""

    print("=" * 60)
    print("🎯 OB1 INGEST PIPELINE")
    print("=" * 60)

    # 1. Scrape
    print("\n📡 FASE 1: Scraping...")
    scraper = OB1Scraper()
    opportunities = scraper.scrape_all()

    if not opportunities:
        print("⚠️ Nessuna opportunità trovata")
        return

    # 2. Ingest
    print("\n📦 FASE 2: Ingest to Gemini File Search...")
    ingest = OB1Ingest()
    uploaded = ingest.ingest_opportunities(opportunities)

    # 3. Cleanup old data
    print("\n🧹 FASE 3: Cleanup...")
    ingest.cleanup_old_files(days_to_keep=7)

    print("\n" + "=" * 60)
    print(f"✅ PIPELINE COMPLETATA")
    print(f"   Opportunità trovate: {len(opportunities)}")
    print(f"   Documenti caricati: {uploaded}")
    print("=" * 60)


if __name__ == "__main__":
    run_ingest_pipeline()
