"""
OB1 WORLD - DNA 2.0 Semantic Matching Engine
AI-driven evaluation based on club strategy manifestos.
"""

import os
import yaml
import json
from typing import Dict, Any, List, Optional
from src.models import MarketOpportunity, PlayerProfile

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

class DNAEngine:
    """Matches players to club strategies using semantic similarity."""

    def __init__(self, manifesto_path: str = "config/dna_manifestos.yaml"):
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY missing.")
        
        self.client = genai.Client(api_key=self.api_key)
        
        with open(manifesto_path, 'r', encoding='utf-8') as f:
            self.manifestos = yaml.safe_load(f).get('archetypes', {})

    def calculate_dna_fit(self, opp: MarketOpportunity, profile: Optional[PlayerProfile] = None) -> Dict[str, Dict]:
        """Compares player signal with all club archetypes."""
        results = {}
        
        # Build player context for the AI
        player_text = f"Player: {opp.player_name}\nDescription: {opp.description}\n"
        if profile:
            player_text += f"Age: {profile.birth_year}\nRole: {profile.role}\nValue: {profile.market_value}\n"

        for arch_id, manifesto in self.manifestos.items():
            print(f"  [DNA MATCHING] Evaluating: {manifesto['name']}...")
            import time
            time.sleep(1) # Anti-429
            
            prompt = f"As a Senior Director of Football, evaluate this player for our club strategy:\nCLUB MANIFESTO:\n{manifesto['description']}\nPLAYER REPORT:\n{player_text}\nINSTRUCTION: Give a match score from 0-100 and a 1-sentence 'Scouting Verdict'. Respond only in JSON: {{\"score\": 85, \"verdict\": \"...\"}}"

            try:
                response = self.client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        response_mime_type="application/json"
                    )
                )
                results[arch_id] = json.loads(response.text)
            except Exception as e:
                print(f"  [DNA ERROR] {e}")
                results[arch_id] = {"score": 50, "verdict": "AI Analysis failed."}

        return results
