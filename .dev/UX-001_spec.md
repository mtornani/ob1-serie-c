# UX-001: Dashboard Responsive Design

## Overview

Redesign completo della dashboard PWA per uso mobile-first.
Target: DS che controlla opportunita dal telefono durante viaggi/partite.

## Problem Statement

Dashboard attuale:
- Layout basic non ottimizzato per mobile
- Nessun filtro interattivo
- Score non visualizzato
- Non "sente" come app nativa

## Solution

### Mobile-First Layout

```
┌─────────────────────────────┐
│  🎯 OB1 Serie C Radar       │  <- Header fisso
│  ━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  🔍 [Cerca giocatore...]    │  <- Search bar
├─────────────────────────────┤
│  ⬜ HOT  ⬜ WARM  ⬜ COLD    │  <- Filter chips
│  📍 Ruolo ▼  📅 Periodo ▼   │  <- Dropdowns
├─────────────────────────────┤
│                             │
│  ┌─────────────────────┐   │
│  │ 🔥 87  Nicolas Viola │   │  <- Card opportunita
│  │ CC • 28 anni        │   │
│  │ SVINCOLATO          │   │
│  │ Ex: Fiorentina      │   │
│  │ [Dettagli] [Salva]  │   │
│  └─────────────────────┘   │
│                             │
│  ┌─────────────────────┐   │
│  │ ⚡ 72  Marco Bianchi │   │
│  │ DC • 24 anni        │   │
│  │ RESCISSIONE         │   │
│  │ Da: Pescara         │   │
│  │ [Dettagli] [Salva]  │   │
│  └─────────────────────┘   │
│                             │
│  ... scroll ...            │
│                             │
├─────────────────────────────┤
│  🏠    🔍    📊    ⚙️     │  <- Bottom nav
└─────────────────────────────┘
```

### Desktop Layout (>768px)

```
┌────────────────────────────────────────────────────────────┐
│  🎯 OB1 Serie C Radar              🔍 Search    👤 Profile │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────┐  ┌────────────────────────────────────────┐ │
│  │ FILTRI   │  │                                        │ │
│  │          │  │  ┌──────────┐  ┌──────────┐  ┌──────┐ │ │
│  │ □ HOT    │  │  │ 🔥 87    │  │ ⚡ 72    │  │ ⚡ 68 │ │ │
│  │ □ WARM   │  │  │ Viola    │  │ Bianchi  │  │ Rossi│ │ │
│  │ □ COLD   │  │  │ CC, 28   │  │ DC, 24   │  │ AT,26│ │ │
│  │          │  │  └──────────┘  └──────────┘  └──────┘ │ │
│  │ RUOLO    │  │                                        │ │
│  │ ▼ Tutti  │  │  ┌──────────┐  ┌──────────┐  ┌──────┐ │ │
│  │          │  │  │ ❄️ 45    │  │ ❄️ 42    │  │ ...  │ │ │
│  │ ETA      │  │  │ ...      │  │ ...      │  │      │ │ │
│  │ [18][35] │  │  └──────────┘  └──────────┘  └──────┘ │ │
│  │          │  │                                        │ │
│  │ PERIODO  │  └────────────────────────────────────────┘ │
│  │ ▼ 7 gg   │                                            │
│  └──────────┘                                            │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Opportunity Card Component

```html
<div class="opportunity-card hot" data-score="87">
  <div class="card-header">
    <span class="score-badge hot">🔥 87</span>
    <span class="player-name">Nicolas Viola</span>
  </div>

  <div class="card-meta">
    <span class="role">📍 Centrocampista</span>
    <span class="age">28 anni</span>
  </div>

  <div class="card-status">
    <span class="opportunity-type svincolato">SVINCOLATO</span>
    <span class="date">📅 28/01/2026</span>
  </div>

  <div class="card-clubs">
    <span class="ex-clubs">Ex: Fiorentina, Cagliari</span>
  </div>

  <div class="card-actions">
    <button class="btn-details" onclick="showDetails('opp_123')">
      📊 Dettagli
    </button>
    <button class="btn-save" onclick="saveToWatchlist('opp_123')">
      💾 Salva
    </button>
  </div>
</div>
```

### CSS Variables (Theme)

```css
:root {
  /* Colors */
  --color-hot: #ef4444;
  --color-warm: #f97316;
  --color-cold: #6b7280;
  --color-primary: #2563eb;
  --color-bg: #0f172a;
  --color-card: #1e293b;
  --color-text: #f1f5f9;
  --color-text-muted: #94a3b8;

  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* Typography */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* Border radius */
  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 16px;

  /* Shadows */
  --shadow-card: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
}

/* Light mode */
@media (prefers-color-scheme: light) {
  :root {
    --color-bg: #f8fafc;
    --color-card: #ffffff;
    --color-text: #0f172a;
    --color-text-muted: #64748b;
  }
}
```

### Score Badge Styles

```css
.score-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-sm);
  font-weight: 700;
  font-size: 14px;
}

.score-badge.hot {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: white;
  animation: pulse 2s infinite;
}

.score-badge.warm {
  background: linear-gradient(135deg, #f97316, #ea580c);
  color: white;
}

.score-badge.cold {
  background: var(--color-card);
  color: var(--color-text-muted);
  border: 1px solid var(--color-text-muted);
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
```

### Filter Chips

```css
.filter-chips {
  display: flex;
  gap: var(--space-sm);
  overflow-x: auto;
  padding: var(--space-sm) 0;
  -webkit-overflow-scrolling: touch;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  background: var(--color-card);
  border-radius: var(--radius-lg);
  border: 1px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.filter-chip.active {
  background: var(--color-primary);
  color: white;
}

.filter-chip:hover {
  border-color: var(--color-primary);
}
```

### Responsive Breakpoints

```css
/* Mobile first */
.opportunity-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
  padding: var(--space-md);
}

/* Tablet */
@media (min-width: 640px) {
  .opportunity-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .opportunity-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .sidebar-filters {
    display: block;
    width: 280px;
  }
}

/* Large desktop */
@media (min-width: 1280px) {
  .opportunity-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
```

### Bottom Navigation (Mobile)

```html
<nav class="bottom-nav">
  <a href="#home" class="nav-item active">
    <span class="nav-icon">🏠</span>
    <span class="nav-label">Home</span>
  </a>
  <a href="#search" class="nav-item">
    <span class="nav-icon">🔍</span>
    <span class="nav-label">Cerca</span>
  </a>
  <a href="#stats" class="nav-item">
    <span class="nav-icon">📊</span>
    <span class="nav-label">Stats</span>
  </a>
  <a href="#settings" class="nav-item">
    <span class="nav-icon">⚙️</span>
    <span class="nav-label">Opzioni</span>
  </a>
</nav>
```

```css
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-around;
  background: var(--color-card);
  padding: var(--space-sm) 0;
  border-top: 1px solid rgba(255,255,255,0.1);
  z-index: 100;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-decoration: none;
  color: var(--color-text-muted);
  font-size: 12px;
}

.nav-item.active {
  color: var(--color-primary);
}

.nav-icon {
  font-size: 24px;
}

/* Hide on desktop */
@media (min-width: 1024px) {
  .bottom-nav {
    display: none;
  }
}
```

### PWA Enhancements

```json
// manifest.json updates
{
  "name": "OB1 Serie C Radar",
  "short_name": "OB1 Radar",
  "description": "Scout AI per Serie C e Serie D",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#2563eb",
  "icons": [
    {
      "src": "icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

### Pull-to-Refresh

```javascript
let touchStartY = 0;

document.addEventListener('touchstart', (e) => {
  touchStartY = e.touches[0].clientY;
});

document.addEventListener('touchmove', (e) => {
  const touchY = e.touches[0].clientY;
  const scrollTop = document.documentElement.scrollTop;

  if (scrollTop === 0 && touchY > touchStartY + 100) {
    showRefreshIndicator();
  }
});

document.addEventListener('touchend', () => {
  if (isRefreshing) {
    refreshData();
  }
});
```

### Skeleton Loading

```html
<div class="opportunity-card skeleton">
  <div class="skeleton-line title"></div>
  <div class="skeleton-line meta"></div>
  <div class="skeleton-line status"></div>
</div>
```

```css
.skeleton .skeleton-line {
  background: linear-gradient(
    90deg,
    var(--color-card) 25%,
    rgba(255,255,255,0.1) 50%,
    var(--color-card) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--radius-sm);
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

## File Structure

```
docs/
├── index.html          # Main dashboard
├── manifest.json       # PWA manifest
├── sw.js              # Service worker
├── css/
│   ├── variables.css  # CSS custom properties
│   ├── base.css       # Reset + typography
│   ├── components.css # Cards, buttons, chips
│   ├── layout.css     # Grid, nav, responsive
│   └── animations.css # Transitions, loading
├── js/
│   ├── app.js         # Main app logic
│   ├── filters.js     # Filter handling
│   ├── storage.js     # LocalStorage watchlist
│   └── pwa.js         # Service worker reg
└── icons/
    ├── icon-192.png
    └── icon-512.png
```

## Acceptance Criteria

- [ ] Mobile-first layout (< 640px ottimizzato)
- [ ] Tablet layout (640-1024px)
- [ ] Desktop layout (> 1024px)
- [ ] Score badges con colori appropriati
- [ ] Filter chips funzionanti
- [ ] Bottom nav su mobile
- [ ] Pull-to-refresh
- [ ] Skeleton loading
- [ ] Dark/light mode auto
- [ ] PWA installabile
- [ ] Lighthouse score > 90

## Dependencies

- SCORE-001 (per visualizzare scores)
- GitHub Pages deployment

## Estimate

**3-4 giorni**
- Day 1: HTML structure + CSS variables + base layout
- Day 2: Card component + filters + responsive
- Day 3: Mobile nav + PWA + animations
- Day 4: Polish + testing cross-device

---

**Status:** READY FOR IMPLEMENTATION
**Assigned:** TBD
**Created:** 2026-01-30
