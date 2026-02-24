// OB1 World Scout — Dashboard
(function () {
  let data = null;
  let currentFilter = 'all';

  async function loadData() {
    try {
      const r = await fetch('data.json?t=' + Date.now());
      data = await r.json();
      render();
    } catch (e) {
      document.getElementById('grid').innerHTML =
        '<div class="empty"><h3>No data yet</h3><p>Scraper has not run yet. Data will appear after first run.</p></div>';
    }
  }

  function render() {
    if (!data) return;
    renderUpdate();
    renderBreakdown();
    renderGrid();
  }

  function renderUpdate() {
    const el = document.getElementById('lastUpdate');
    if (data.generated_at_utc) {
      const d = new Date(data.generated_at_utc);
      el.textContent = 'Last update: ' + d.toLocaleString();
    }
  }

  function renderBreakdown() {
    const b = data.region_breakdown || {};
    const el = document.getElementById('breakdown');
    const regions = [
      { key: 'africa', label: 'Africa', cls: 'africa' },
      { key: 'asia', label: 'Asia', cls: 'asia' },
      { key: 'south-america', label: 'S. America', cls: 'south-america' },
      { key: 'international', label: 'International', cls: 'international' },
    ];
    el.innerHTML = regions.map(r =>
      `<div class="region-box ${r.cls}"><div class="count">${b[r.key] || 0}</div><div class="label">${r.label}</div></div>`
    ).join('');
  }

  function getFiltered() {
    let items = data.items || [];
    const q = (document.getElementById('search').value || '').toLowerCase();
    if (q) items = items.filter(it => (it.label || '').toLowerCase().includes(q));
    if (currentFilter === 'all') return items;
    if (currentFilter === 'hot') return items.filter(it => it.score >= 20).sort((a, b) => b.score - a.score).slice(0, 5);
    if (currentFilter === 'PLAYER_BURST' || currentFilter === 'TRANSFER_SIGNAL') return items.filter(it => it.anomaly_type === currentFilter);
    // region filter
    return items.filter(it => (it.why || []).includes(currentFilter));
  }

  function scoreClass(score) {
    if (score >= 20) return 'hot';
    if (score >= 10) return 'warm';
    return 'cold';
  }

  function renderGrid() {
    const items = getFiltered();
    const el = document.getElementById('grid');
    if (!items.length) {
      el.innerHTML = '<div class="empty"><h3>No signals</h3><p>Try a different filter.</p></div>';
      return;
    }
    el.innerHTML = items.map(it => {
      const tags = (it.why || []).map(t => {
        const cls = ['africa', 'asia', 'south-america', 'international', 'youth', 'mercato', 'esordio', 'recente'].includes(t) ? ` ${t}` : '';
        return `<span class="tag${cls}">${t}</span>`;
      }).join('');
      const links = (it.links || []).map(l => `<a class="card-link" href="${l}" target="_blank">View source ↗</a>`).join(' ');
      const sc = scoreClass(it.score);
      return `<div class="card">
        <div class="card-head">
          <div class="card-title">${it.label || 'Unknown'}</div>
          <div class="card-score ${sc}">${it.score}</div>
        </div>
        <div class="card-type">${it.anomaly_type || ''}</div>
        <div class="card-tags">${tags}</div>
        ${links}
      </div>`;
    }).join('');
  }

  // Filters
  document.getElementById('filters').addEventListener('click', e => {
    const btn = e.target.closest('.chip');
    if (!btn) return;
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    renderGrid();
  });

  // Search
  document.getElementById('search').addEventListener('input', () => renderGrid());

  // Boot
  loadData();
})();
