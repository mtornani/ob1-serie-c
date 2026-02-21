/**
 * OB1 Radar - Dashboard Application
 * DS-Proof Redesign - 2026
 */

const state = {
  opportunities: [],
  filteredOpportunities: [],
  currentView: 'landing', 
  currentFilter: 'all',
  searchQuery: '',
  isLoading: true,
  theme: 'dark'
};

const elements = {
  opportunitiesGrid: document.getElementById('opportunitiesGrid'),
  emptyState: document.getElementById('emptyState'),
  searchInput: document.getElementById('searchInput'),
  filterChips: document.getElementById('filterChips'),
  lastUpdate: document.getElementById('lastUpdate'),
  themeToggle: document.getElementById('themeToggle'),
  modalOverlay: document.getElementById('modalOverlay'),
  modalTitle: document.getElementById('modalTitle'),
  modalContent: document.getElementById('modalContent'),
  modalClose: document.getElementById('modalClose'),
  toastContainer: document.getElementById('toastContainer')
};

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initEventListeners();
  loadData();
  showView('landing');
});

function initTheme() {
  const savedTheme = localStorage.getItem('ob1-theme') || 'dark';
  state.theme = savedTheme;
  applyTheme();
}

function applyTheme() {
  if (state.theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}

function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('ob1-theme', state.theme);
  applyTheme();
}

function initEventListeners() {
  elements.themeToggle.addEventListener('click', toggleTheme);

  elements.searchInput.addEventListener('input', debounce((e) => {
    state.searchQuery = e.target.value.toLowerCase();
    filterOpportunities();
  }, 300));

  elements.filterChips.addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip');
    if (chip) {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.currentFilter = chip.dataset.filter;
      filterOpportunities();
    }
  });

  elements.modalClose.addEventListener('click', closeModal);
  elements.modalOverlay.addEventListener('click', (e) => {
    if (e.target === elements.modalOverlay) closeModal();
  });

  const btnExploreAll = document.getElementById('btnExploreAll');
  if (btnExploreAll) {
    btnExploreAll.addEventListener('click', () => {
      showView('explore');
      filterOpportunities();
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
    updateLastUpdate(data.last_update);
    filterOpportunities();
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

function filterOpportunities() {
  let filtered = [...state.opportunities];

  // Quick Filters logic
  if (state.currentFilter === 'hot') {
    filtered = filtered.filter(o => o.ob1_score >= 70).sort((a,b) => b.ob1_score - a.ob1_score).slice(0, 10);
  } else if (state.currentFilter === 'under') {
    filtered = filtered.filter(o => o.age <= 21);
  } else if (state.currentFilter === 'free') {
    filtered = filtered.filter(o => o.opportunity_type.toLowerCase().includes('svincol'));
  }

  if (state.searchQuery) {
    filtered = filtered.filter(o => 
      o.player_name.toLowerCase().includes(state.searchQuery) || 
      (o.role_name || o.role).toLowerCase().includes(state.searchQuery)
    );
  }

  // Default sorting
  filtered.sort((a, b) => b.ob1_score - a.ob1_score);

  state.filteredOpportunities = filtered;
  renderOpportunities();
}

function renderOpportunities() {
  const grid = elements.opportunitiesGrid;
  const empty = elements.emptyState;

  if (state.filteredOpportunities.length === 0) {
    grid.innerHTML = '';
    if (empty) empty.style.display = 'block';
    return;
  }

  if (empty) empty.style.display = 'none';
  grid.innerHTML = state.filteredOpportunities.map(opp => createOpportunityCard(opp)).join('');

  grid.querySelectorAll('.opportunity-card').forEach(card => {
    card.addEventListener('click', () => {
      const opp = state.opportunities.find(o => o.id === card.dataset.id);
      if (opp) showDetail(opp);
    });
  });
}

function createOpportunityCard(opp) {
  const score = opp.ob1_score;
  let verdict = 'VALUTARE';
  let verdictClass = 'cold';
  let stars = '⭐';

  if (score >= 70) {
    verdict = 'TOP';
    verdictClass = 'hot';
    stars = '⭐⭐⭐';
  } else if (score >= 57) {
    verdict = 'OCCASIONE';
    verdictClass = 'warm';
    stars = '⭐⭐';
  }

  const currentClub = opp.current_club || 'Svincolato';
  const role = opp.role_name || opp.role;
  
  let valueInfo = '';
  if (opp.market_value > 0) {
    valueInfo = opp.market_value >= 1000 ? `${Math.round(opp.market_value/1000)}k€` : `${opp.market_value}€`;
  }

  return `
    <article class="opportunity-card ${verdictClass}" data-id="${opp.id}">
      <div class="card-report-header">
        <div class="player-main">
          <span class="report-stars">${stars}</span>
          <h3 class="player-name">${opp.player_name}</h3>
          <span class="player-sub">${role} • ${currentClub}</span>
        </div>
        <div class="verdict-badge ${verdictClass}">${verdict}</div>
      </div>
      <div class="card-report-body">
        <div class="report-item">
          <span class="label">Età</span>
          <span class="value">${opp.age}</span>
        </div>
        <div class="report-item">
          <span class="label">Valore</span>
          <span class="value">${valueInfo || '--'}</span>
        </div>
        <div class="report-item">
          <span class="label">Contratto</span>
          <span class="value">${opp.opportunity_type}</span>
        </div>
      </div>
      ${opp.recommendation ? `
        <div class="report-note">
          <strong>Nota OB1:</strong> ${opp.recommendation}
        </div>
      ` : ''}
    </article>
  `;
}

function showDetail(opp) {
  elements.modalTitle.textContent = "Scouting Report: " + opp.player_name;
  
  elements.modalContent.innerHTML = `
    <div class="detail-header">
      <div class="detail-main">
        <h2>${opp.player_name}</h2>
        <p>${opp.role_name || opp.role} • ${opp.age} anni</p>
      </div>
      <div class="detail-score">${opp.ob1_score}</div>
    </div>
    
    <div class="detail-grid">
      <div class="detail-box">
        <h4>Situazione</h4>
        <p>${opp.opportunity_type}</p>
        <p>Club: ${opp.current_club || 'Svincolato'}</p>
      </div>
      <div class="detail-box">
        <h4>Analisi Tecnica</h4>
        <p>${opp.recommendation || opp.summary || 'Profilo monitorato dal sistema OB1.'}</p>
      </div>
    </div>
    
    <div class="detail-actions">
      ${opp.tm_url ? `<a href="${opp.tm_url}" target="_blank" class="btn-primary">Vedi su Transfermarkt</a>` : ''}
    </div>
  `;

  elements.modalOverlay.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  elements.modalOverlay.classList.remove('active');
  document.body.style.overflow = '';
}

function updateLastUpdate(timestamp) {
  if (timestamp) {
    const date = new Date(timestamp);
    elements.lastUpdate.textContent = `Aggiornato: ${date.toLocaleDateString()} ${date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
  }
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

function formatDate(dateString) {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('it-IT');
}
