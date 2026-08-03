"""
ARCH-002 — strato di osservazione: lavorare su un segnale di cambiamento
invece che a orologio.

Fase 2 (qui): `seen.py`, la memoria di cosa è già stato visto.
Fase 3 (dopo): `sources.py`, `poller.py`, `queue.py`.

Tutto lo strato è disattivabile con OB1_WATCH=0 (vincolo ARCH-002 §7): senza
di esso la pipeline torna al comportamento attuale, che resta corretto — solo
più caro.
"""

from .seen import SeenStore, content_key, normalize_content, watch_enabled

__all__ = ["SeenStore", "content_key", "normalize_content", "watch_enabled"]
