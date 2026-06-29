"""
Isolated Gemini free-tier smoke test.

Verifies, using only GEMINI_API_KEY, whether a billing-free key can:
  1. Authenticate and call gemini-2.5-flash (plain generation)
  2. Use Google Search grounding (the feature the real pipeline depends on)

Prints clear PASS/FAIL per stage and the raw data produced, so we can see
exactly what a free key returns (or which limit it hits: 429 rate, 403 billing).

No Telegram, no commits, no DB writes — safe to run standalone.
"""
import os
import sys
import json
import re

KEY = os.getenv('GEMINI_API_KEY', '')

print("=" * 60)
print("GEMINI FREE-TIER SMOKE TEST")
print("=" * 60)
print(f"GEMINI_API_KEY present: {bool(KEY)} (len={len(KEY)})")
if not KEY:
    print("FATAL: no GEMINI_API_KEY in environment")
    sys.exit(1)

try:
    from google import genai
except Exception as e:
    print(f"FATAL: cannot import google.genai — {e}")
    sys.exit(1)

client = genai.Client(api_key=KEY)
MODEL = "gemini-2.5-flash"

# ---------------------------------------------------------------------------
# Stage 1 — plain generation (auth + model access)
# ---------------------------------------------------------------------------
print("\n--- STAGE 1: plain generation ---")
try:
    r = client.models.generate_content(
        model=MODEL,
        contents="Rispondi solo con la parola: OK",
    )
    print(f"PASS — model reachable. Response: {(r.text or '').strip()[:80]!r}")
except Exception as e:
    print(f"FAIL — {type(e).__name__}: {e}")
    print("\n>>> Free key cannot even do plain generation. Stopping.")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Stage 2 — Google Search grounding (the real pipeline feature)
# ---------------------------------------------------------------------------
print("\n--- STAGE 2: Google Search grounding ---")
prompt = (
    "Cerca su Google notizie recenti (2026) su: svincolati Serie C Lega Pro centrocampisti\n\n"
    "Identifica SOLO nomi di calciatori INDIVIDUALI.\n"
    "Rispondi ESCLUSIVAMENTE con un JSON array:\n"
    '[{"player_name": "Nome Cognome", "source_url": "url", '
    '"opportunity_type": "svincolato|prestito|rescissione|mercato", '
    '"description": "max 80 caratteri"}]\n'
    "Se non trovi nulla, rispondi: []"
)
try:
    r = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
            temperature=0.0,
        ),
    )
    text = r.text or ""
    print(f"PASS — grounding call returned. Raw text length: {len(text)}")
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            items = json.loads(m.group(0))
            print(f"Parsed {len(items)} players:")
            print(json.dumps(items, indent=2, ensure_ascii=False))
        except Exception as pe:
            print(f"JSON parse failed: {pe}")
            print(f"Raw: {text[:500]}")
    else:
        print(f"No JSON array in response. Raw: {text[:500]}")

    # Show whether grounding metadata is actually attached (proves search ran)
    try:
        cand = r.candidates[0]
        gm = getattr(cand, 'grounding_metadata', None)
        if gm and getattr(gm, 'grounding_chunks', None):
            print(f"\nGrounding active: {len(gm.grounding_chunks)} source chunks")
        else:
            print("\nWARNING: no grounding metadata — search may not have run")
    except Exception:
        pass

except Exception as e:
    print(f"FAIL — {type(e).__name__}: {e}")
    msg = str(e).lower()
    if '429' in msg or 'quota' in msg or 'rate' in msg:
        print(">>> Free-tier RATE/QUOTA limit hit on grounding.")
    elif '403' in msg or 'billing' in msg or 'permission' in msg:
        print(">>> Grounding likely requires BILLING (not available on free key).")
    sys.exit(3)

print("\n" + "=" * 60)
print("DONE — free key works for plain + grounded generation.")
print("=" * 60)
