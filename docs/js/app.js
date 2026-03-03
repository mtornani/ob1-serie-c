/**
 * OB1 Radar - Serie C Scout
 * Ouroboros Protocol — 2026
 */

const state = {
  opportunities: [],
  filteredOpportunities: [],
  stats: null,
  lastUpdate: null,
  currentView: 'landing',
  currentFilter: 'all',
  currentType: '',
  currentSort: 'score',
  searchQuery: ''
};

const elements = {};

document.addEventListener('DOMContentLoaded', () => {
  // Cache DOM elements safely
  ['opportunitiesGrid', 'emptyState', 'searchInput', 'filterChips',
   'modalOverlay', 'modalTitle', 'modalContent', 'modalClose',
   'cycleStatus', 'resultCount', 'typeFilter', 'sortBy',
   'toastContainer'].forEach(id => {
    elements[id] = document.getElementById(id);
  });

  initEventListeners();
  loadData();
  showView('landing');
});

function initEventListeners() {
  elements.searchInput.addEventListener('input', debounce((e) => {
    state.searchQuery = e.target.value.toLowerCase();
    filterAndRender();
  }, 250));

  elements.filterChips.addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip');
    if (chip) {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.currentFilter = chip.dataset.filter;
      filterAndRender();
    }
  });

  if (elements.typeFilter) {
    elements.typeFilter.addEventListener('change', (e) => {
      state.currentType = e.target.value;
      filterAndRender();
    });
  }

  if (elements.sortBy) {
    elements.sortBy.addEventListener('change', (e) => {
      state.currentSort = e.target.value;
      filterAndRender();
    });
  }

  elements.modalClose.addEventListener('click', closeModal);
  elements.modalOverlay.addEventListener('click', (e) => {
    if (e.target === elements.modalOverlay) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  const btnExploreAll = document.getElementById('btnExploreAll');
  if (btnExploreAll) {
    btnExploreAll.addEventListener('click', () => {
      showView('explore');
      filterAndRender();
    });
  }

  const btnBackFromExplore = document.getElementById('btnBackFromExplore');
  if (btnBackFromExplore) {
    btnBackFromExplore.addEventListener('click', () => showView('landing'));
  }
}

async function loadData() {
  try {
    const response = await fetch('data.json?t=' + Date.now());
    const data = await response.json();
    state.opportunities = data.opportunities || [];
    state.stats = data.stats || {};
    state.lastUpdate = data.last_update;
    updateCycleStatus(data.last_update);
    updateHeroStats();
    renderTopPreview();
    filterAndRender();
  } catch (error) {
    console.error('Error loading data:', error);
  }
}

function showView(viewName) {
  state.currentView = viewName;
  document.getElementById('landingView').style.display = viewName === 'landing' ? 'block' : 'none';
  document.getElementById('exploreView').style.display = viewName === 'explore' ? 'block' : 'none';
  window.scrollTo(0, 0);
}

// ── Hero Stats ──

function updateHeroStats() {
  const opps = state.opportunities;
  const hot = opps.filter(o => o.ob1_score >= 70).length;
  const free = opps.filter(o => (o.opportunity_type || '').toLowerCase().includes('svincol')).length;

  setHeroStat('heroStatProfiles', opps.length);
  setHeroStat('heroStatHot', hot);
  setHeroStat('heroStatFree', free);
}

function setHeroStat(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

// ── Top 3 Preview on Landing ──

function renderTopPreview() {
  const container = document.getElementById('topPreview');
  if (!container) return;
  const top3 = [...state.opportunities].sort((a,b) => b.ob1_score - a.ob1_score).slice(0, 3);
  if (top3.length === 0) return;

  container.innerHTML = top3.map(opp => {
    const role = safe(opp.role_name, opp.role || '');
    const type = safe(opp.opportunity_type, '');
    return `<div class="top-preview-item">
      <span class="tp-score">${opp.ob1_score}</span>
      <div class="tp-info">
        <span class="tp-name">${opp.player_name}</span>
        <span class="tp-meta">${role} // ${type}</span>
      </div>
    </div>`;
  }).join('');
}

// ── Cycle Status ──

function updateCycleStatus(timestamp) {
  if (!timestamp || !elements.cycleStatus) return;
  const last = new Date(timestamp);
  const now = new Date();
  const diffMs = now - last;
  const diffH = Math.floor(diffMs / 3600000);
  const diffM = Math.floor((diffMs % 3600000) / 60000);

  const CYCLE_HOURS = 6;
  const nextMs = Math.max(0, (CYCLE_HOURS * 3600000) - diffMs);
  const nextH = Math.floor(nextMs / 3600000);
  const nextM = Math.floor((nextMs % 3600000) / 60000);

  const lastStr = `${String(last.getHours()).padStart(2,'0')}:${String(last.getMinutes()).padStart(2,'0')}`;
  const agoStr = diffH > 0 ? `${diffH}h ${diffM}m ago` : `${diffM}m ago`;
  const nextStr = nextMs > 0 ? `next: ${nextH}h ${nextM}m` : 'cycling...';

  elements.cycleStatus.innerHTML = `<span class="cycle-label">OUROBOROS</span> ${lastStr} (${agoStr}) // ${nextStr}`;
}

// ── Filter + Sort ──

function filterAndRender() {
  let filtered = [...state.opportunities];

  // Primary filter
  if (state.currentFilter === 'hot') {
    filtered = filtered.filter(o => o.ob1_score >= 70).sort((a,b) => b.ob1_score - a.ob1_score).slice(0, 10);
  } else if (state.currentFilter === 'under') {
    filtered = filtered.filter(o => o.age != null && o.age <= 21);
  } else if (state.currentFilter === 'free') {
    filtered = filtered.filter(o => (o.opportunity_type || '').toLowerCase().includes('svincol'));
  }

  // Type filter
  if (state.currentType) {
    filtered = filtered.filter(o => (o.opportunity_type || '').toLowerCase() === state.currentType);
  }

  // Search
  if (state.searchQuery) {
    filtered = filtered.filter(o =>
      o.player_name.toLowerCase().includes(state.searchQuery) ||
      (o.role_name || o.role || '').toLowerCase().includes(state.searchQuery) ||
      (o.current_club || '').toLowerCase().includes(state.searchQuery)
    );
  }

  // Sort
  if (state.currentSort === 'score') {
    filtered.sort((a, b) => b.ob1_score - a.ob1_score);
  } else if (state.currentSort === 'name') {
    filtered.sort((a, b) => a.player_name.localeCompare(b.player_name));
  } else if (state.currentSort === 'date') {
    filtered.sort((a, b) => {
      const da = a.discovered_at || a.reported_date || '';
      const db = b.discovered_at || b.reported_date || '';
      return db.localeCompare(da);
    });
  }

  state.filteredOpportunities = filtered;

  if (elements.resultCount) {
    elements.resultCount.textContent = filtered.length;
  }

  renderOpportunities();
}

// ── Render Cards ──

function renderOpportunities() {
  const grid = elements.opportunitiesGrid;
  const empty = elements.emptyState;

  if (state.filteredOpportunities.length === 0) {
    grid.innerHTML = '';
    if (empty) empty.style.display = 'block';
    return;
  }

  if (empty) empty.style.display = 'none';

  // Use DocumentFragment for performance
  grid.innerHTML = state.filteredOpportunities.map(opp => createCard(opp)).join('');

  grid.querySelectorAll('.opp-card').forEach(card => {
    card.addEventListener('click', () => {
      const opp = state.opportunities.find(o => o.id === card.dataset.id);
      if (opp) showDetail(opp);
    });
  });
}

function safe(val, fallback) {
  if (val === null || val === undefined || val === '' || val === 'null') return fallback;
  return val;
}

function createCard(opp) {
  const score = opp.ob1_score;
  let tier = 'cold';
  if (score >= 70) tier = 'hot';
  else if (score >= 57) tier = 'warm';

  const name = opp.player_name;
  const role = safe(opp.role_name, opp.role || '—');
  const club = safe(opp.current_club, 'Svincolato');
  const type = safe(opp.opportunity_type, '—');
  const age = safe(opp.age, null);

  let tags = `<span class="opp-tag type-${type}">${type}</span>`;
  if (age !== null) tags += `<span class="opp-tag">${age} anni</span>`;

  return `<article class="opp-card ${tier}" data-id="${opp.id}">
    <div class="opp-top">
      <div class="opp-info">
        <h3 class="opp-name">${name}</h3>
        <span class="opp-meta">${role} // ${club}</span>
      </div>
      <span class="opp-score ${tier}">${score}</span>
    </div>
    <div class="opp-tags">${tags}</div>
  </article>`;
}

// ── Detail Modal ──

function showDetail(opp) {
  const score = opp.ob1_score;
  let tier = 'cold';
  if (score >= 70) tier = 'hot';
  else if (score >= 57) tier = 'warm';

  const age = safe(opp.age, '—');
  const club = safe(opp.current_club, 'Svincolato');
  const role = safe(opp.role_name, opp.role || '—');
  const type = safe(opp.opportunity_type, '—');
  const nationality = safe(opp.nationality, null);
  const foot = safe(opp.foot, null);
  const apps = safe(opp.appearances, null);
  const goals = safe(opp.goals, null);
  const assists = safe(opp.assists, null);
  const recommendation = safe(opp.recommendation, null);
  const summary = safe(opp.summary, null);
  const prevClubs = safe(opp.previous_clubs, null);
  const discovered = safe(opp.discovered_at, null);

  let metaRows = '';
  metaRows += `<tr><td>Ruolo</td><td>${role}</td></tr>`;
  metaRows += `<tr><td>Eta</td><td>${age === '—' ? '—' : age + ' anni'}</td></tr>`;
  metaRows += `<tr><td>Club</td><td>${club}</td></tr>`;
  metaRows += `<tr><td>Contratto</td><td>${type}</td></tr>`;
  if (nationality) metaRows += `<tr><td>Nazionalita</td><td>${nationality}</td></tr>`;
  if (foot) metaRows += `<tr><td>Piede</td><td>${foot}</td></tr>`;
  if (prevClubs) metaRows += `<tr><td>Passato</td><td>${Array.isArray(prevClubs) ? prevClubs.join(', ') : prevClubs}</td></tr>`;
  if (discovered) metaRows += `<tr><td>Scoperto</td><td>${new Date(discovered).toLocaleDateString('it-IT')}</td></tr>`;

  let statsRow = '';
  if (apps !== null || goals !== null || assists !== null) {
    statsRow = `<div class="detail-stats">`;
    if (apps !== null) statsRow += `<div class="detail-stat"><span class="ds-val">${apps}</span><span class="ds-lbl">APP</span></div>`;
    if (goals !== null) statsRow += `<div class="detail-stat"><span class="ds-val">${goals}</span><span class="ds-lbl">GOL</span></div>`;
    if (assists !== null) statsRow += `<div class="detail-stat"><span class="ds-val">${assists}</span><span class="ds-lbl">ASS</span></div>`;
    statsRow += `</div>`;
  }

  const breakdown = opp.score_breakdown;
  let breakdownHtml = '';
  if (breakdown) {
    breakdownHtml = `<div class="detail-breakdown"><h4>> SCORE_BREAKDOWN</h4><div class="bd-bars">`;
    const labels = {
      freshness: 'FRESCHEZZA', opportunity_type: 'TIPO', experience: 'ESPERIENZA',
      age: 'ETA', market_value: 'VALORE', league_fit: 'LEGA', source: 'FONTE', completeness: 'DATI'
    };
    for (const [key, val] of Object.entries(breakdown)) {
      const label = labels[key] || key.toUpperCase();
      const barClass = val >= 70 ? 'bar-good' : val >= 40 ? 'bar-mid' : 'bar-low';
      breakdownHtml += `<div class="bd-row"><span class="bd-lbl">${label}</span><div class="bd-track"><div class="bd-fill ${barClass}" style="width:${val}%"></div></div><span class="bd-val">${val}</span></div>`;
    }
    breakdownHtml += `</div></div>`;
  }

  const analysisText = recommendation || summary || 'Profilo monitorato dal sistema OB1.';

  elements.modalTitle.textContent = opp.player_name;
  elements.modalContent.innerHTML = `
    <div class="detail-header">
      <div class="detail-main"><h2>${opp.player_name}</h2></div>
      <div class="detail-score ${tier}">${score}</div>
    </div>
    <table class="detail-table">${metaRows}</table>
    ${statsRow}
    <div class="detail-box">
      <h4>> OB1_ANALISI</h4>
      <p>${analysisText}</p>
    </div>
    ${breakdownHtml}
    ${opp.tm_url ? `<a href="${opp.tm_url}" target="_blank" class="btn-primary" onclick="event.stopPropagation()">Transfermarkt &#8599;</a>` : ''}
    ${opp.source_url ? `<a href="${opp.source_url}" target="_blank" class="btn-source" onclick="event.stopPropagation()">Fonte originale &#8599;</a>` : ''}
  `;

  elements.modalOverlay.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  elements.modalOverlay.classList.remove('active');
  document.body.style.overflow = '';
}

// ── Utils ──

function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}
