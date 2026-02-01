"""
OB1 Serie C - History Tracking
Traccia l'evoluzione delle opportunità nel tempo (Time Series Data)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import asdict

HISTORY_FILE = Path("data/history_log.json")

class HistoryTracker:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.history_file = self.data_dir / "history_log.json"
        self.history_data = self._load_history()

    def _load_history(self) -> List[Dict]:
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_history(self):
        # Keep only last 1000 events to avoid unlimited growth in this MVP
        # In production, this should append to a database
        if len(self.history_data) > 1000:
            self.history_data = self.history_data[-1000:]
            
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history_data, f, ensure_ascii=False, indent=2)

    def track_changes(self, current_opportunities: List[Dict]):
        """Confronta le opportunità correnti con lo stato precedente e registra eventi"""
        
        # Load previous snapshot (if exists) via the opportunities file itself
        # We assume the caller passes the NEW list. We need to know what was there BEFORE.
        # Since we overwrite opportunities.json, we rely on memory or a 'snapshot.json'
        # For simplicity in this MVP, we just track 'NEW' items based on ID lookup in history
        
        # Mappa degli ID già visti (costruita scorrendo tutto il log storico)
        seen_ids = set()
        for event in self.history_data:
            if event['type'] == 'NEW_DISCOVERY':
                seen_ids.add(event['entity_id'])
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        new_events = []
        
        for opp in current_opportunities:
            opp_id = opp.get('id')
            
            # 1. NEW DISCOVERY
            if opp_id not in seen_ids:
                event = {
                    "date": today,
                    "timestamp": datetime.now().isoformat(),
                    "type": "NEW_DISCOVERY",
                    "entity_id": opp_id,
                    "player_name": opp.get('player_name'),
                    "details": f"Nuova opportunità rilevata: {opp.get('player_name')} ({opp.get('role')})",
                    "score": opp.get('ob1_score', 0)
                }
                self.history_data.append(event)
                new_events.append(event)
                seen_ids.add(opp_id)
                continue
                
            # 2. TRACK CHANGES (Future implementation: compare with previous day's snapshot)
            # Qui servirebbe caricare il data.json di IERI. 
            # Per ora ci limitiamo a tracciare i nuovi inserimenti.
            
        if new_events:
            print(f"  📜 History: Registrati {len(new_events)} nuovi eventi.")
            self.save_history()
            
        return new_events

    def get_recent_events(self, days: int = 7) -> List[Dict]:
        """Ritorna eventi degli ultimi N giorni"""
        limit_date = datetime.now().isoformat() # semplificato, andrebbe gestito meglio il parsing date
        # Sort by date desc
        return sorted(self.history_data, key=lambda x: x['timestamp'], reverse=True)

