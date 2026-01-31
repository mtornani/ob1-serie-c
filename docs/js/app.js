/**
 * OB1 Radar - Dashboard Application
 * Mobile-first PWA for Serie C/D scouting
 */

// =============================================================================
// State Management
// =============================================================================

const state = {
  opportunities: [],
  filteredOpportunities: [],
  savedOpportunities: [],
  currentFilter: 'all',
  currentRoleFilter: '',
  currentTypeFilter: '',
  searchQuery: '',
  isLoading: true,
  theme: 'dark'
};

// =============================================================================
// Demo Data (Replace with real API calls)
// =============================================================================

const demoOpportunities = [
  {
    id: 'opp_001',
    player_name: 'Nicolas Viola',
    age: 28,
    role: 'CC',
    role_name: 'Centrocampista Centrale',
    opportunity_type: 'svincolato',
    reported_date: '2026-01-30',
    source_name: 'TuttoC',
    source_url: 'https://tuttoc.com/news/viola-svincolato',
    previous_clubs: ['Fiorentina', 'Cagliari', 'Benevento'],
    appearances: 185,
    goals: 22,
    ob1_score: 87,
    classification: 'hot'
  },
  {
    id: 'opp_002',
    player_name: 'Marco Bianchi',
    age: 24,
    role: 'DC',
    role_name: 'Difensore Centrale',
    opportunity_type: 'rescissione',
    reported_date: '2026-01-29',
    source_name: 'Calciomercato',
    source_url: 'https://calciomercato.com/news/bianchi',
    previous_clubs: ['Pescara', 'Reggiana'],
    appearances: 78,
    goals: 4,
    ob1_score: 72,
    classification: 'warm'
  },
  {
    id: 'opp_003',
    player_name: 'Luca Verdi',
    age: 26,
    role: 'ES',
    role_name: 'Esterno Sinistro',
    opportunity_type: 'prestito',
    reported_date: '2026-01-28',
    source_name: 'TMW',
    source_url: 'https://tmw.com/news/verdi',
    previous_clubs: ['Milan Primavera', 'Cesena', 'Gubbio'],
    appearances: 95,
    goals: 12,
    ob1_score: 68,
    classification: 'warm'
  },
  {
    id: 'opp_004',
    player_name: 'Giuseppe Rossi',
    age: 31,
    role: 'AT',
    role_name: 'Attaccante',
    opportunity_type: 'scadenza',
    reported_date: '2026-01-25',
    source_name: 'Gazzetta',
    source_url: 'https://gazzetta.it/news/rossi',
    previous_clubs: ['Livorno', 'Trapani', 'Ternana'],
    appearances: 220,
    goals: 65,
    ob1_score: 55,
    classification: 'cold'
  },
  {
    id: 'opp_005',
    player_name: 'Andrea Neri',
    age: 22,
    role: 'TD',
    role_name: 'Terzino Destro',
    opportunity_type: 'svincolato',
    reported_date: '2026-01-30',
    source_name: 'TuttoC',
    source_url: 'https://tuttoc.com/news/neri',
    previous_clubs: ['Juventus U23', 'Pro Vercelli'],
    appearances: 45,
    goals: 1,
    ob1_score: 81,
    classification: 'hot'
  },
  {
    id: 'opp_006',
    player_name: 'Fabio Gialli',
    age: 27,
    role: 'PO',
    role_name: 'Portiere',
    opportunity_type: 'prestito',
    reported_date: '2026-01-27',
    source_name: 'Corriere dello Sport',
    source_url: 'https://corrieredellosport.it/news/gialli',
    previous_clubs: ['Parma', 'Piacenza', 'Mantova'],
    appearances: 110,
    goals: 0,
    ob1_score: 63,
    classification: 'warm'
  }
];

// =============================================================================
// DOM Elements
// =============================================================================

const elements = {
  opportunitiesGrid: document.getElementById('opportunitiesGrid'),
  emptyState: document.getElementById('emptyState'),
  searchInput: document.getElementById('searchInput'),
  filterChips: document.getElementById('filterChips'),
  roleFilter: document.getElementById('roleFilter'),
  typeFilter: document.getElementById('typeFilter'),
  totalCount: document.getElementById('totalCount'),
  hotCount: document.getElementById('hotCount'),
  warmCount: document.getElementById('warmCount'),
  recentCount: document.getElementById('recentCount'),
  lastUpdate: document.getElementById('lastUpdate'),
  themeToggle: document.getElementById('themeToggle'),
  refreshBtn: document.getElementById('refreshBtn'),
  modalOverlay: document.getElementById('modalOverlay'),
  modalTitle: document.getElementById('modalTitle'),
  modalContent: document.getElementById('modalContent'),
  modalClose: document.getElementById('modalClose'),
  pullIndicator: document.getElementById('pullIndicator'),
  toastContainer: document.getElementById('toastContainer')
};

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initEventListeners();
  loadSavedOpportunities();
  loadData();

  // Initialize onboarding tutorial
  onboarding.init();
  addHelpButton();
});

function initTheme() {
  const savedTheme = localStorage.getItem('ob1-theme');
  if (savedTheme) {
    state.theme = savedTheme;
  } else {
    // Check system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    state.theme = prefersDark ? 'dark' : 'light';
  }
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

// =============================================================================
// Event Listeners
// =============================================================================

function initEventListeners() {
  // Theme toggle
  elements.themeToggle.addEventListener('click', toggleTheme);

  // Refresh button
  elements.refreshBtn.addEventListener('click', () => {
    loadData(true);
  });

  // Search input
  elements.searchInput.addEventListener('input', debounce((e) => {
    state.searchQuery = e.target.value.toLowerCase();
    filterOpportunities();
  }, 300));

  // Filter chips
  elements.filterChips.addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip');
    if (chip) {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.currentFilter = chip.dataset.filter;
      filterOpportunities();
    }
  });

  // Role filter
  elements.roleFilter.addEventListener('change', (e) => {
    state.currentRoleFilter = e.target.value;
    filterOpportunities();
  });

  // Type filter
  elements.typeFilter.addEventListener('change', (e) => {
    state.currentTypeFilter = e.target.value;
    filterOpportunities();
  });

  // Modal close
  elements.modalClose.addEventListener('click', closeModal);
  elements.modalOverlay.addEventListener('click', (e) => {
    if (e.target === elements.modalOverlay) {
      closeModal();
    }
  });

  // Bottom navigation
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      const view = item.dataset.view;
      handleNavigation(view);
    });
  });

  // Pull to refresh (mobile)
  initPullToRefresh();

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModal();
    }
    if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      elements.searchInput.focus();
    }
  });
}

// =============================================================================
// Data Loading
// =============================================================================

async function loadData(forceRefresh = false) {
  state.isLoading = true;
  showSkeletons();

  try {
    // Try to fetch from data.json first
    let data = null;

    try {
      const response = await fetch('data.json?t=' + Date.now());
      if (response.ok) {
        data = await response.json();
      }
    } catch (e) {
      console.log('No data.json found, using demo data');
    }

    // Use demo data if no real data
    if (!data || !data.opportunities || data.opportunities.length === 0) {
      data = { opportunities: demoOpportunities, last_update: new Date().toISOString() };
    }

    state.opportunities = data.opportunities;
    state.filteredOpportunities = [...state.opportunities];

    updateStats();
    filterOpportunities();
    updateLastUpdate(data.last_update);

    if (forceRefresh) {
      showToast('Dati aggiornati', 'success');
    }

  } catch (error) {
    console.error('Error loading data:', error);
    showToast('Errore nel caricamento dati', 'error');
  } finally {
    state.isLoading = false;
  }
}

// =============================================================================
// Filtering
// =============================================================================

function filterOpportunities() {
  let filtered = [...state.opportunities];

  // Classification filter
  if (state.currentFilter !== 'all') {
    filtered = filtered.filter(opp => opp.classification === state.currentFilter);
  }

  // Role filter
  if (state.currentRoleFilter) {
    filtered = filtered.filter(opp => opp.role === state.currentRoleFilter);
  }

  // Type filter
  if (state.currentTypeFilter) {
    filtered = filtered.filter(opp => opp.opportunity_type === state.currentTypeFilter);
  }

  // Search query
  if (state.searchQuery) {
    filtered = filtered.filter(opp => {
      const searchable = [
        opp.player_name,
        opp.role_name,
        opp.opportunity_type,
        ...(opp.previous_clubs || [])
      ].join(' ').toLowerCase();
      return searchable.includes(state.searchQuery);
    });
  }

  // Sort by score (highest first)
  filtered.sort((a, b) => b.ob1_score - a.ob1_score);

  state.filteredOpportunities = filtered;
  renderOpportunities();
}

// =============================================================================
// Rendering
// =============================================================================

function renderOpportunities() {
  if (state.filteredOpportunities.length === 0) {
    elements.opportunitiesGrid.innerHTML = '';
    elements.emptyState.style.display = 'block';
    return;
  }

  elements.emptyState.style.display = 'none';
  elements.opportunitiesGrid.innerHTML = state.filteredOpportunities
    .map(opp => createOpportunityCard(opp))
    .join('');

  // Add click listeners
  document.querySelectorAll('.opportunity-card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (!e.target.closest('.btn-card')) {
        const oppId = card.dataset.id;
        const opp = state.opportunities.find(o => o.id === oppId);
        if (opp) showDetail(opp);
      }
    });
  });

  // Add button listeners
  document.querySelectorAll('.btn-save').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const oppId = btn.closest('.opportunity-card').dataset.id;
      toggleSave(oppId);
    });
  });
}

function createOpportunityCard(opp) {
  const isSaved = state.savedOpportunities.includes(opp.id);
  const scoreEmoji = opp.classification === 'hot' ? '🔥' : opp.classification === 'warm' ? '⚡' : '❄️';

  return `
    <article class="opportunity-card ${opp.classification} slide-up" data-id="${opp.id}">
      <div class="card-header">
        <span class="player-name">${opp.player_name}</span>
        <span class="score-badge ${opp.classification}">${scoreEmoji} ${opp.ob1_score}</span>
      </div>

      <div class="card-meta">
        <span>📍 ${opp.role_name || opp.role}</span>
        <span>🎂 ${opp.age} anni</span>
      </div>

      <div class="card-status">
        <span class="type-badge ${opp.opportunity_type}">${opp.opportunity_type.toUpperCase()}</span>
        <span class="card-date">📅 ${formatDate(opp.reported_date)}</span>
      </div>

      ${opp.previous_clubs && opp.previous_clubs.length > 0 ? `
        <div class="card-clubs">
          🏟️ Ex: ${opp.previous_clubs.slice(0, 3).join(', ')}
        </div>
      ` : ''}

      <div class="card-actions">
        <button class="btn-card primary">📊 Dettagli</button>
        <button class="btn-card secondary btn-save" data-saved="${isSaved}">
          ${isSaved ? '💾 Salvato' : '📋 Salva'}
        </button>
      </div>
    </article>
  `;
}

function showSkeletons() {
  elements.opportunitiesGrid.innerHTML = `
    <div class="opportunity-card skeleton">
      <div class="skeleton-line title"></div>
      <div class="skeleton-line meta"></div>
      <div class="skeleton-line status"></div>
    </div>
    <div class="opportunity-card skeleton">
      <div class="skeleton-line title"></div>
      <div class="skeleton-line meta"></div>
      <div class="skeleton-line status"></div>
    </div>
    <div class="opportunity-card skeleton">
      <div class="skeleton-line title"></div>
      <div class="skeleton-line meta"></div>
      <div class="skeleton-line status"></div>
    </div>
  `;
}

// =============================================================================
// Stats
// =============================================================================

function updateStats() {
  const total = state.opportunities.length;
  const hot = state.opportunities.filter(o => o.classification === 'hot').length;
  const warm = state.opportunities.filter(o => o.classification === 'warm').length;
  const today = new Date().toISOString().split('T')[0];
  const recent = state.opportunities.filter(o => o.reported_date === today).length;

  animateNumber(elements.totalCount, total);
  animateNumber(elements.hotCount, hot);
  animateNumber(elements.warmCount, warm);
  animateNumber(elements.recentCount, recent);
}

function animateNumber(element, target) {
  const start = parseInt(element.textContent) || 0;
  const duration = 500;
  const startTime = performance.now();

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const current = Math.floor(start + (target - start) * easeOutQuad(progress));
    element.textContent = current;

    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }

  requestAnimationFrame(update);
}

function easeOutQuad(t) {
  return t * (2 - t);
}

function updateLastUpdate(timestamp) {
  if (timestamp) {
    const date = new Date(timestamp);
    elements.lastUpdate.textContent = `Ultimo aggiornamento: ${formatDateTime(date)}`;
  }
}

// =============================================================================
// Modal
// =============================================================================

function showDetail(opp) {
  elements.modalTitle.textContent = opp.player_name;

  const scoreEmoji = opp.classification === 'hot' ? '🔥' : opp.classification === 'warm' ? '⚡' : '❄️';

  elements.modalContent.innerHTML = `
    <div style="margin-bottom: var(--space-md);">
      <span class="score-badge ${opp.classification}" style="font-size: 1.2rem; padding: var(--space-sm) var(--space-md);">
        ${scoreEmoji} OB1 Score: ${opp.ob1_score}/100
      </span>
    </div>

    <div class="card" style="background: var(--color-bg-secondary); padding: var(--space-md); border-radius: var(--radius-md); margin-bottom: var(--space-md);">
      <h4 style="margin-bottom: var(--space-sm); color: var(--color-text-secondary);">Informazioni</h4>
      <p><strong>Ruolo:</strong> ${opp.role_name || opp.role}</p>
      <p><strong>Eta:</strong> ${opp.age} anni</p>
      <p><strong>Status:</strong> <span class="type-badge ${opp.opportunity_type}">${opp.opportunity_type.toUpperCase()}</span></p>
      <p><strong>Data:</strong> ${formatDate(opp.reported_date)}</p>
    </div>

    ${opp.previous_clubs && opp.previous_clubs.length > 0 ? `
      <div class="card" style="background: var(--color-bg-secondary); padding: var(--space-md); border-radius: var(--radius-md); margin-bottom: var(--space-md);">
        <h4 style="margin-bottom: var(--space-sm); color: var(--color-text-secondary);">Club Precedenti</h4>
        <p>${opp.previous_clubs.join(' → ')}</p>
      </div>
    ` : ''}

    <div class="card" style="background: var(--color-bg-secondary); padding: var(--space-md); border-radius: var(--radius-md); margin-bottom: var(--space-md);">
      <h4 style="margin-bottom: var(--space-sm); color: var(--color-text-secondary);">Statistiche Carriera</h4>
      <p><strong>Presenze:</strong> ${opp.appearances || 'N/A'}</p>
      <p><strong>Gol:</strong> ${opp.goals || 0}</p>
    </div>

    <div class="card" style="background: var(--color-bg-secondary); padding: var(--space-md); border-radius: var(--radius-md);">
      <h4 style="margin-bottom: var(--space-sm); color: var(--color-text-secondary);">Fonte</h4>
      <p>${opp.source_name}</p>
      ${opp.source_url ? `<a href="${opp.source_url}" target="_blank" rel="noopener" style="color: var(--color-primary);">🔗 Leggi articolo</a>` : ''}
    </div>
  `;

  elements.modalOverlay.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  elements.modalOverlay.classList.remove('active');
  document.body.style.overflow = '';
}

// =============================================================================
// Saved Opportunities
// =============================================================================

function loadSavedOpportunities() {
  const saved = localStorage.getItem('ob1-saved');
  state.savedOpportunities = saved ? JSON.parse(saved) : [];
}

function toggleSave(oppId) {
  const index = state.savedOpportunities.indexOf(oppId);
  if (index > -1) {
    state.savedOpportunities.splice(index, 1);
    showToast('Rimosso dai salvati', 'success');
  } else {
    state.savedOpportunities.push(oppId);
    showToast('Salvato!', 'success');
  }
  localStorage.setItem('ob1-saved', JSON.stringify(state.savedOpportunities));
  renderOpportunities();
}

// =============================================================================
// Navigation
// =============================================================================

function handleNavigation(view) {
  switch (view) {
    case 'home':
      state.currentFilter = 'all';
      document.querySelectorAll('.filter-chip').forEach(c => {
        c.classList.toggle('active', c.dataset.filter === 'all');
      });
      filterOpportunities();
      break;
    case 'search':
      elements.searchInput.focus();
      break;
    case 'saved':
      // Filter to show only saved
      state.filteredOpportunities = state.opportunities.filter(
        opp => state.savedOpportunities.includes(opp.id)
      );
      renderOpportunities();
      if (state.filteredOpportunities.length === 0) {
        showToast('Nessun giocatore salvato', 'info');
      }
      break;
    case 'stats':
      showToast('Stats view coming soon!', 'info');
      break;
  }
}

// =============================================================================
// Pull to Refresh
// =============================================================================

function initPullToRefresh() {
  let touchStartY = 0;
  let isPulling = false;

  document.addEventListener('touchstart', (e) => {
    if (window.scrollY === 0) {
      touchStartY = e.touches[0].clientY;
    }
  }, { passive: true });

  document.addEventListener('touchmove', (e) => {
    if (window.scrollY === 0) {
      const touchY = e.touches[0].clientY;
      const diff = touchY - touchStartY;

      if (diff > 80 && !isPulling) {
        isPulling = true;
        elements.pullIndicator.classList.add('active');
      }
    }
  }, { passive: true });

  document.addEventListener('touchend', () => {
    if (isPulling) {
      isPulling = false;
      loadData(true);
      setTimeout(() => {
        elements.pullIndicator.classList.remove('active');
      }, 1000);
    }
  });
}

// =============================================================================
// Toast Notifications
// =============================================================================

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;

  elements.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// =============================================================================
// Utilities
// =============================================================================

function formatDate(dateString) {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('it-IT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  });
}

function formatDateTime(date) {
  return date.toLocaleDateString('it-IT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
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

// =============================================================================
// Onboarding Tutorial
// =============================================================================

const onboarding = {
  overlay: null,
  currentStep: 1,
  totalSteps: 5,

  init() {
    this.overlay = document.getElementById('onboardingOverlay');
    if (!this.overlay) return;

    // Check if user has seen the tutorial
    const hasSeenTutorial = localStorage.getItem('ob1-tutorial-completed');

    if (!hasSeenTutorial) {
      this.show();
    }

    this.bindEvents();
  },

  bindEvents() {
    // Skip button
    const skipBtn = document.getElementById('skipTutorial');
    if (skipBtn) {
      skipBtn.addEventListener('click', () => this.complete());
    }

    // Next button
    const nextBtn = document.getElementById('nextStep');
    if (nextBtn) {
      nextBtn.addEventListener('click', () => this.nextStep());
    }

    // Prev button
    const prevBtn = document.getElementById('prevStep');
    if (prevBtn) {
      prevBtn.addEventListener('click', () => this.prevStep());
    }

    // Finish button
    const finishBtn = document.getElementById('finishTutorial');
    if (finishBtn) {
      finishBtn.addEventListener('click', () => this.complete());
    }

    // Progress dots (click to navigate)
    document.querySelectorAll('.progress-dot').forEach(dot => {
      dot.addEventListener('click', () => {
        const step = parseInt(dot.dataset.step);
        if (step) this.goToStep(step);
      });
    });

    // Close on ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.overlay.classList.contains('active')) {
        this.complete();
      }
    });
  },

  show() {
    if (this.overlay) {
      this.overlay.classList.add('active');
      document.body.style.overflow = 'hidden';
      this.goToStep(1);
    }
  },

  hide() {
    if (this.overlay) {
      this.overlay.classList.remove('active');
      document.body.style.overflow = '';
    }
  },

  goToStep(step) {
    if (step < 1 || step > this.totalSteps) return;

    this.currentStep = step;

    // Update step visibility
    document.querySelectorAll('.onboarding-step').forEach(s => {
      s.classList.remove('active');
    });
    const currentStepEl = document.querySelector(`.onboarding-step[data-step="${step}"]`);
    if (currentStepEl) {
      currentStepEl.classList.add('active');
    }

    // Update progress dots
    document.querySelectorAll('.progress-dot').forEach(dot => {
      const dotStep = parseInt(dot.dataset.step);
      dot.classList.toggle('active', dotStep === step);
      dot.classList.toggle('completed', dotStep < step);
    });

    // Update navigation buttons
    const prevBtn = document.getElementById('prevStep');
    const nextBtn = document.getElementById('nextStep');
    const finishBtn = document.getElementById('finishTutorial');

    if (prevBtn) {
      prevBtn.style.display = step > 1 ? 'inline-flex' : 'none';
    }

    if (nextBtn && finishBtn) {
      if (step === this.totalSteps) {
        nextBtn.style.display = 'none';
        finishBtn.style.display = 'inline-flex';
      } else {
        nextBtn.style.display = 'inline-flex';
        finishBtn.style.display = 'none';
      }
    }
  },

  nextStep() {
    if (this.currentStep < this.totalSteps) {
      this.goToStep(this.currentStep + 1);
    }
  },

  prevStep() {
    if (this.currentStep > 1) {
      this.goToStep(this.currentStep - 1);
    }
  },

  complete() {
    localStorage.setItem('ob1-tutorial-completed', 'true');
    this.hide();
    showToast('Benvenuto in OB1 Radar! 🎯', 'success');
  },

  // Method to reset and show tutorial again (for help button)
  reset() {
    localStorage.removeItem('ob1-tutorial-completed');
    this.show();
  }
};

// Add help button to reopen tutorial
function addHelpButton() {
  const headerActions = document.querySelector('.header-actions');
  if (headerActions) {
    const helpBtn = document.createElement('button');
    helpBtn.className = 'btn-icon';
    helpBtn.id = 'helpBtn';
    helpBtn.setAttribute('aria-label', 'Aiuto');
    helpBtn.innerHTML = '❓';
    helpBtn.addEventListener('click', () => onboarding.reset());
    headerActions.insertBefore(helpBtn, headerActions.firstChild);
  }
}

// =============================================================================
// Service Worker Registration
// =============================================================================

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js')
      .then(registration => {
        console.log('SW registered:', registration);
      })
      .catch(error => {
        console.log('SW registration failed:', error);
      });
  });
}
