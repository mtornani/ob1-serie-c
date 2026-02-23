#!/usr/bin/env python3
"""
OUROBOROS - Ingest to Gemini File Search Store
Simplified version for stable google-genai integration.
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from src.models import MarketOpportunity, PlayerProfile

class OB1Ingest:
    """Handles data ingestion to Gemini File Search."""
    
    STORE_PREFIX = "ouroboros-world-"
    
    def __init__(self):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY missing.")
        self.client = genai.Client(api_key=api_key)

    def get_or_create_store(self, league_id: str):
        store_display_name = f"{self.STORE_PREFIX}{league_id}"
        try:
            # Note: list() triggers the iterator
            stores = list(self.client.file_search_stores.list())
            for s in stores:
                if store_display_name in s.display_name: return s
        except: pass
        return self.client.file_search_stores.create(config={'display_name': store_display_name})

    def ingest_opportunities(self, league_id: str, opportunities: List[MarketOpportunity]):
        """Consolidates and uploads opportunities for a league."""
        store = self.get_or_create_store(league_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Generate Markdown content
        lines = [f"# OUROBOROS LEAGUE: {league_id.upper()}", f"Update: {today}", "", "---", ""]
        for opp in opportunities:
            lines.append(opp.to_document())
            lines.append("\n---")
        
        content = "\n".join(lines)
        temp_dir = os.path.join(os.getcwd(), 'data')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = Path(temp_dir) / f"ingest_{league_id}.md"
        temp_path.write_text(content, encoding='utf-8')
        
        try:
            print(f"  [INGEST] Uploading {league_id} knowledge...")
            # Simplified upload without mime_type (let the library detect it)
            operation = self.client.file_search_stores.upload_to_file_search_store(
                file=str(temp_path),
                file_search_store_name=store.name
            )
            while not operation.done:
                time.sleep(2)
                operation = self.client.operations.get(operation)
            print(f"  [INGEST] Success! {len(opportunities)} items indexed.")
        except Exception as e:
            print(f"  [INGEST ERROR] {e}")
        finally:
            if temp_path.exists(): temp_path.unlink()
