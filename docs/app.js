/* OB1 — Scout Lega Pro (app v5) */

const STATE = {
  all: [],
  filtered: [],
  filter: 'all',
  type: '',
  sort: 'score',
  q: '',
  lastUpdate: null,
};

const TIER_LABEL = { hot: 'da chiamare', warm: 'da seguire', cold: 'bassa priorità' };

// Tipo opportunità → etichetta da campo (no gergo interno)
const TYPE_LABEL = {
  svincolato: 'Senza contratto',
  rescissione: 'Ha rescisso',
  prestito: 'Prestito',
  mercato: 'Sul mercato',
  scadenza: 'In scadenza',
  talento: 'Giovane',
};

const el  = (s, r=document) => r.querySelector(s);
const els = (s, r=document) => [...r.querySelectorAll(s)];
const safe = (v, f='—') => (v===null||v===undefined||v===''||v==='null') ? f : v;

document.addEventListener('DOMContentLoaded', init);

async function init(){
  wireKeyShortcuts();
  wireControls();
  wireDrawer();

  // Deep-link from PWA shortcuts: ?filter=hot|free|under|new
  const params = new URLSearchParams(location.search);
  const f = params.get('filter');
  if (f && ['all','hot','free','under','new'].includes(f)) {
    STATE.filter = f;
  }

  el('#grid').innerHTML = '<div class="empty" style="display:block"><div class="big" style="font-size:16px;color:var(--ink-mute)">caricamento…</div></div>';

  try {
    const r = await fetch('data.json?t='+Date.now());
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    STATE.all = (data.opportunities||[]).map(decorate);
    STATE.lastUpdate = data.last_update;
  } catch(err) {
    el('#grid').innerHTML = `
      <div class="empty" style="display:block">
        <div class="big">⚠</div>
        <div>Impossibile caricare i dati.<br>Ricarica la pagina o riprova tra qualche minuto.</div>
      </div>`;
    console.error('[OB1] fetch failed:', err);
    return;
  }

  updateCycle();
  checkStale();
  setInterval(updateCycle, 30000);
  trackSession();
  paintCounters();
  // Sync chip UI with deep-link filter
  els('.chip').forEach((c) => {
    c.classList.toggle('on', c.dataset.f === STATE.filter);
  });
  applyFilter();
}

/* ============ DECORATE ============ */

function decorate(o){
  const exp = o.contract_expires ? new Date(o.contract_expires) : null;
  const today = new Date();
  let days = null;
  if (exp && !isNaN(exp.getTime())) {
    days = Math.round((exp - today) / 86400000);
  }
  const typeLower = (o.opportunity_type||'').toLowerCase();
  const isFree = typeLower.includes('svincol');
  let urgency;
  if (isFree) {
    const dwc = o.days_without_contract || 0;
    if (dwc === 0) urgency = 'critical';
    else if (dwc <= 14) urgency = 'high';
    else if (dwc <= 45) urgency = 'warm';
    else urgency = 'cold';
  } else if (days === null) {
    urgency = 'cold';
  } else if (days < 0) urgency = 'cold';
  else if (days <= 90)  urgency = 'critical';
  else if (days <= 180) urgency = 'high';
  else if (days <= 365) urgency = 'warm';
  else urgency = 'cold';

  const s = o.ob1_score || 0;
  let tier = 'cold';
  if (s >= 70) tier = 'hot';
  else if (s >= 57) tier = 'warm';

  let barPct = 0;
  if (isFree) {
    barPct = Math.max(5, Math.min(100, 100 - (o.days_without_contract||0) * 2));
  } else if (days !== null) {
    barPct = Math.max(4, Math.min(100, 100 - ((days/730)*100)));
  }

  return { ...o, _days: days, _urgency: urgency, _tier: tier, _isFree: isFree, _barPct: barPct };
}

/* ============ FILTER + SORT ============ */

function applyFilter(){
  let list = [...STATE.all];

  if (STATE.filter === 'hot')    list = list.filter(o=>o.ob1_score>=70);
  else if (STATE.filter === 'under')  list = list.filter(o=>o.age!=null && o.age<=22);
  else if (STATE.filter === 'free')   list = list.filter(o=>o._isFree);
  else if (STATE.filter === 'new'){
    const cutoff = Date.now() - 14 * 86400000; // ultimi 14 giorni
    list = list.filter(o => o.discovered_at && new Date(o.discovered_at).getTime() >= cutoff);
    list.sort((a,b)=>(b.discovered_at||'').localeCompare(a.discovered_at||''));
  }

  if (STATE.type) list = list.filter(o=>(o.opportunity_type||'').toLowerCase()===STATE.type);

  if (STATE.q) {
    const q = STATE.q;
    list = list.filter(o =>
      (o.player_name||'').toLowerCase().includes(q) ||
      (o.role_name||o.role||'').toLowerCase().includes(q) ||
      (o.current_club||'').toLowerCase().includes(q) ||
      (o.nationality||'').toLowerCase().includes(q)
    );
  }

  if (STATE.sort==='score')        list.sort((a,b)=>b.ob1_score-a.ob1_score);
  else if (STATE.sort==='name')    list.sort((a,b)=>a.player_name.localeCompare(b.player_name));
  else if (STATE.sort==='date')    list.sort((a,b)=>(b.discovered_at||'').localeCompare(a.discovered_at||''));
  else if (STATE.sort==='urgency'){
    const rank = { critical:0, high:1, warm:2, cold:3 };
    list.sort((a,b)=> (rank[a._urgency]-rank[b._urgency]) || (b.ob1_score-a.ob1_score));
  }

  STATE.filtered = list;
  paintGrid();
  paintResultCount();
}

/* ============ COUNTERS ============ */

function paintCounters(){
  const all = STATE.all;
  const hot    = all.filter(o=>o.ob1_score>=70).length;
  const free   = all.filter(o=>o._isFree).length;
  const u21    = all.filter(o=>o.age!=null && o.age<=22).length;
  const cutoff14 = Date.now() - 14 * 86400000;
  const newCt  = all.filter(o => o.discovered_at && new Date(o.discovered_at).getTime() >= cutoff14).length;

  el('#ctHot').textContent  = hot;
  el('#ctFree').textContent = free;
  el('#ctU21').textContent  = u21;
  el('#ctAll').textContent  = all.length;

  const map = { all:all.length, hot, free, under:u21, new:newCt };
  els('.chip .num').forEach(n=>{
    const k = n.dataset.ct;
    n.textContent = map[k] ?? 0;
  });
  el('#rtotal').textContent = all.length;
}

function paintResultCount(){
  el('#rcount').textContent = STATE.filtered.length;
}

/* ============ GRID ============ */

function paintGrid(){
  const g     = el('#grid');
  const empty = el('#empty');
  if (STATE.filtered.length === 0){
    g.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  g.innerHTML = STATE.filtered.map(card).join('');
  els('.card', g).forEach(c=>{
    c.addEventListener('click',  ()=>{ const o=STATE.all.find(x=>x.id===c.dataset.id); if(o) openDrawer(o); });
    c.addEventListener('keydown', e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); const o=STATE.all.find(x=>x.id===c.dataset.id); if(o) openDrawer(o); }});
  });
}

function cardLine(o){
  // One plain line under the name — no timer, no bar, no tag pile
  const type = (o.opportunity_type||'').toLowerCase();
  const sit = TYPE_LABEL[type] || '';
  if (o._isFree) {
    const dwc = o.days_without_contract || 0;
    const free = dwc === 0 ? 'appena libero' : `${dwc} gg senza club`;
    return sit ? `${sit} · ${free}` : free;
  }
  if (o._days != null && o._days >= 0 && o._days <= 180) {
    return sit ? `${sit} · scade tra ${o._days} gg` : `scade tra ${o._days} gg`;
  }
  return sit || '—';
}

function card(o){
  const roleRaw = o.role_name || o.role || '';
  const role  = /^(n\/d|n\/a|none|—|-)?$/i.test(roleRaw.trim()) ? '' : roleRaw;
  const club  = safe(o.current_club, 'Senza club');
  const age   = o.age!=null ? `${o.age} anni` : '';
  const daysOld = o.discovered_at ? Math.round((Date.now() - new Date(o.discovered_at)) / 86400000) : null;
  const isNew = daysOld !== null && daysOld <= 3;

  return `
<article class="card" data-id="${o.id}" data-urgency="${o._urgency}" data-tier="${o._tier}" tabindex="0" role="button" aria-label="${esc(o.player_name)}, ${o.ob1_score}">
  <span class="urgency"></span>
  <div class="card-head">
    <div class="name-block">
      <div class="name">${esc(o.player_name)}${isNew ? ' <span class="tag new-signal">Nuovo</span>' : ''}</div>
      <div class="meta">
        ${[role && `<span class="role">${esc(role)}</span>`, age && `<span class="age">${age}</span>`, `<span class="club">${esc(club)}</span>`].filter(Boolean).join('<span class="sep">·</span>')}
      </div>
      <div class="meta card-line">${esc(cardLine(o))}</div>
    </div>
    <div class="score">${o.ob1_score}<span class="dlabel">${TIER_LABEL[o._tier]||''}</span></div>
  </div>
</article>`;
}

function esc(s){ return String(s ?? '').replace(/[<>&"']/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":"&#39;"}[c])); }

/* ============ DRAWER: assessment from backend (no LLM) ============ */

function openDrawer(o){
  trackDrawerOpen(o.player_name);

  const brief = el('#brief');
  const type  = (o.opportunity_type||'').toLowerCase();
  const roleRaw = o.role_name || o.role || '';
  const role  = /^(n\/d|n\/a|none|—|-)?$/i.test(roleRaw.trim()) ? '' : roleRaw;
  const club  = safe(o.current_club, 'Senza club');
  const sit   = TYPE_LABEL[type] || type || '—';

  el('#breadName').textContent = o.player_name || '';

  // Prefer server-side assessment (code from scoring.assess_follow)
  const a = o.assessment || {};
  const yes = a.yes || [];
  const no  = a.no || [];
  const action = a.action
    || (o.ob1_score >= 70 ? 'Da chiamare ora'
       : o.ob1_score >= 57 ? "Da tenere d'occhio"
       : 'Bassa priorità');

  const nums = [
    o.appearances != null && o.appearances > 0 && { v: o.appearances, l: 'Presenze' },
    o.goals != null && o.goals > 0 && { v: o.goals, l: 'Gol' },
    o.assists != null && o.assists > 0 && { v: o.assists, l: 'Assist' },
    o.market_value_formatted && { v: shortMoney(o.market_value_formatted), l: 'Valore' },
  ].filter(Boolean);

  const stripHtml = nums.length
    ? `<div class="strip">${nums.map(s=>`<div class="cell"><span class="v">${s.v}</span><span class="l">${s.l}</span></div>`).join('')}</div>`
    : '';

  const facts = [
    ['Situazione', sit],
    ['Club', club],
    o.age!=null && ['Età', `${o.age} anni`],
    role && ['Ruolo', role],
    o.nationality && ['Nazionalità', o.nationality + (o.second_nationality ? ` / ${o.second_nationality}` : '')],
    o.foot && ['Piede', o.foot],
    o.agent && ['Agente', o.agent],
  ].filter(Boolean);

  const yesHtml = yes.length
    ? `<div class="assess yes"><div class="assess-h">Perché sì</div><ul class="why-list">${yes.map(b=>`<li>${esc(b)}</li>`).join('')}</ul></div>`
    : '';
  const noHtml = no.length
    ? `<div class="assess no"><div class="assess-h">Perché no / attenzione</div><ul class="why-list">${no.map(b=>`<li>${esc(b)}</li>`).join('')}</ul></div>`
    : '';

  brief.innerHTML = `
    <div class="brief-head">
      <div>
        <div class="name">${esc(o.player_name)}</div>
        <div class="sub">
          ${[role && esc(role), o.age!=null && `${o.age} anni`, esc(club)].filter(Boolean).join(' · ')}
        </div>
      </div>
      <div class="big-score ${o._tier}">${o.ob1_score}<div class="pct">/100</div></div>
    </div>

    <div class="verdict-note" style="margin:12px 0 10px">
      <strong>${esc(action)}</strong>
    </div>
    ${yesHtml}
    ${noHtml}

    ${stripHtml}

    <div class="sect">
      <div class="sect-title">SCHEDA</div>
      <div class="meta-grid">
        ${facts.map(([k,v])=>`<div class="cell"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join('')}
      </div>
    </div>
  `;

  const srcLink = el('#sourceLink');
  const isGrounding = o.source_url && (o.source_url.includes('vertexaisearch') || o.source_url.includes('grounding-api'));
  if (o.source_url && !isGrounding){
    srcLink.href = o.source_url;
    srcLink.textContent = `Leggi la notizia ↗`;
    srcLink.style.display = '';
  } else {
    srcLink.href = `https://www.google.com/search?q=${encodeURIComponent((o.player_name||'') + ' Serie C')}`;
    srcLink.textContent = 'Cerca su Google ↗';
    srcLink.style.display = '';
  }

  const tmLink = el('#tmLink');
  tmLink.href = o.tm_url
    ? o.tm_url
    : `https://www.transfermarkt.it/schnellsuche/ergebnis/schnellsuche?query=${encodeURIComponent(o.player_name||'')}`;
  tmLink.textContent = 'Transfermarkt ↗';

  el('#ov').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeDrawer(){
  el('#ov').classList.remove('open');
  document.body.style.overflow = '';
}

function shortMoney(s){
  if (!s) return '—';
  s = s.replace('€','').trim();
  if (s.includes('mln'))  return s.replace('mln','M').replace(',','.').replace(/\s+/g,'');
  if (s.includes('mila')) return s.replace('mila','K').replace(',','.').replace(/\s+/g,'');
  return s;
}

/* ============ CYCLE STATUS ============ */

function updateCycle(){
  if (!STATE.lastUpdate) return;
  const last  = new Date(STATE.lastUpdate);
  if (isNaN(last.getTime())) return;
  const now   = new Date();
  const diffMs = Math.max(0, now - last);
  const diffH  = Math.floor(diffMs / 3600000);
  const diffM  = Math.floor((diffMs % 3600000) / 60000);
  const nextMs = Math.max(0, (6 * 3600000) - diffMs);
  const nH = Math.floor(nextMs/3600000), nM = Math.floor((nextMs%3600000)/60000);
  const hh = String(last.getHours()).padStart(2,'0');
  const mm = String(last.getMinutes()).padStart(2,'0');
  const ago  = diffH > 0 ? `${diffH} h fa` : `${diffM} min fa`;
  const next = nextMs > 0 ? `prossimo tra ${nH > 0 ? nH + ' h' : nM + ' min'}` : 'aggiornamento in corso…';
  el('#cycleStatus').textContent = `Aggiornato ${ago} · ${next}`;
}

/* ============ STALE WARNING ============ */

function checkStale(){
  if (!STATE.lastUpdate) return;
  const ageH  = (Date.now() - new Date(STATE.lastUpdate)) / 3600000;
  const banner = el('#staleBanner');
  if (!banner) return;
  if (ageH > 12) {
    const h = Math.round(ageH);
    banner.textContent = `⚠ Dati di ${h} ore fa — aggiornamento in corso, ricarica tra poco.`;
    banner.style.display = 'block';
  }
}

/* ============ SESSION TRACKING (K-Sport engagement) ============ */

function trackSession(){
  const today = new Date().toISOString().slice(0, 10);
  try {
    let sessions = JSON.parse(localStorage.getItem('ob1_sessions') || '[]');
    if (!Array.isArray(sessions)) sessions = [];
    if (!sessions.includes(today)) {
      sessions.push(today);
      localStorage.setItem('ob1_sessions', JSON.stringify(sessions.slice(-90)));
    }
    localStorage.setItem('ob1_last_visit', new Date().toISOString());
  } catch(_){}
}

function trackDrawerOpen(playerName){
  try {
    const views = JSON.parse(localStorage.getItem('ob1_views') || '{}');
    views[playerName] = (views[playerName] || 0) + 1;
    localStorage.setItem('ob1_views', JSON.stringify(views));
    localStorage.setItem('ob1_last_view', JSON.stringify({ player: playerName, at: new Date().toISOString() }));
  } catch(_){}
}

/* ============ CONTROLS ============ */

function wireControls(){
  el('#q').addEventListener('input', debounce(e=>{
    STATE.q = e.target.value.toLowerCase();
    applyFilter();
  }, 180));
  el('#filters').addEventListener('click', e=>{
    const c = e.target.closest('.chip');
    if (!c) return;
    els('.chip').forEach(x=>x.classList.remove('on'));
    c.classList.add('on');
    STATE.filter = c.dataset.f;
    applyFilter();
  });
  el('#typeF').addEventListener('change',  e=>{ STATE.type = e.target.value; applyFilter(); });
  el('#sortBy').addEventListener('change', e=>{ STATE.sort = e.target.value; applyFilter(); });
}

function wireDrawer(){
  el('#closeBtn').addEventListener('click', closeDrawer);
  el('#ov').addEventListener('click', e=>{ if (e.target.id === 'ov') closeDrawer(); });
  document.addEventListener('keydown', e=>{ if (e.key === 'Escape') closeDrawer(); });
}

function wireKeyShortcuts(){
  document.addEventListener('keydown', e=>{
    // '/' → focus search
    if (e.key === '/' && document.activeElement !== el('#q')){
      e.preventDefault();
      el('#q').focus();
      return;
    }
    // Arrow keys → navigate cards
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !el('#ov').classList.contains('open')){
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
      const cards = els('.card');
      if (!cards.length) return;
      const idx = cards.indexOf(document.activeElement);
      const next = e.key === 'ArrowDown'
        ? (cards[idx + 1] || cards[0])
        : (cards[idx - 1] || cards[cards.length - 1]);
      next.focus();
      e.preventDefault();
    }
  });
}

function debounce(fn, ms){ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }

