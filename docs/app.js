/* OB1 :: LEGA PRO — Redesign */

const STATE = {
  all: [],
  filtered: [],
  filter: 'all',
  type: '',
  sort: 'score',
  q: '',
  lastUpdate: null,
};

const el = (s, r=document) => r.querySelector(s);
const els = (s, r=document) => [...r.querySelectorAll(s)];
const safe = (v, f='—') => (v===null||v===undefined||v===''||v==='null') ? f : v;

document.addEventListener('DOMContentLoaded', init);

async function init(){
  applyTweaksFromDefaults();
  wireTweaks();
  wireKeyShortcuts();
  wireControls();
  wireDrawer();

  const r = await fetch('data.json?t='+Date.now());
  const data = await r.json();
  STATE.all = (data.opportunities||[]).map(decorate);
  STATE.lastUpdate = data.last_update;

  updateCycle();
  setInterval(updateCycle, 30000);
  paintCounters();
  paintTicker();
  applyFilter();
}

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
  else if (days <= 90) urgency = 'critical';
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

  if (STATE.filter === 'hot') list = list.filter(o=>o.ob1_score>=70).sort((a,b)=>b.ob1_score-a.ob1_score).slice(0,10);
  else if (STATE.filter === 'under') list = list.filter(o=>o.age!=null && o.age<=21);
  else if (STATE.filter === 'free')  list = list.filter(o=>o._isFree);
  else if (STATE.filter === 'roi')   list = list.filter(o=>{
    const rc=(o.intel||{}).roi_class; return rc==='elite'||rc==='high';
  }).sort((a,b)=>((b.intel||{}).moltiplicatore||0)-((a.intel||{}).moltiplicatore||0));
  else if (STATE.filter === 'urgent') list = list.filter(o=>o._urgency==='critical'||o._urgency==='high');

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

  if (STATE.sort==='score') list.sort((a,b)=>b.ob1_score-a.ob1_score);
  else if (STATE.sort==='name') list.sort((a,b)=>a.player_name.localeCompare(b.player_name));
  else if (STATE.sort==='date') list.sort((a,b)=>(b.discovered_at||'').localeCompare(a.discovered_at||''));
  else if (STATE.sort==='urgency'){
    const rank = { critical:0, high:1, warm:2, cold:3 };
    list.sort((a,b)=> (rank[a._urgency]-rank[b._urgency]) || (b.ob1_score-a.ob1_score));
  }

  STATE.filtered = list;
  paintGrid();
  paintResultCount();
}

/* ============ PAINT: COUNTERS ============ */

function paintCounters(){
  const all = STATE.all;
  const hot = all.filter(o=>o.ob1_score>=70).length;
  const free = all.filter(o=>o._isFree).length;
  const u21 = all.filter(o=>o.age!=null && o.age<=21).length;
  const urgent = all.filter(o=>o._urgency==='critical'||o._urgency==='high').length;
  const roi = all.filter(o=>{ const rc=(o.intel||{}).roi_class; return rc==='elite'||rc==='high'; }).length;

  el('#ctHot').textContent = hot;
  el('#ctFree').textContent = free;
  el('#ctU21').textContent = u21;
  el('#ctAll').textContent = all.length;

  const map = { all:all.length, hot, free, under:u21, roi, urgent };
  els('.chip .num').forEach(n=>{
    const k = n.dataset.ct;
    n.textContent = map[k] ?? 0;
  });

  el('#rtotal').textContent = all.length;
}

function paintResultCount(){
  el('#rcount').textContent = STATE.filtered.length;
}

/* ============ PAINT: TICKER ============ */

function paintTicker(){
  const track = el('#ticker');
  const top = [...STATE.all].sort((a,b)=>b.ob1_score-a.ob1_score).slice(0, 20);
  const items = top.map(o=>{
    const arrow = o.ob1_score >= 70 ? '▲' : '●';
    const cls = o.ob1_score >= 70 ? 'up' : '';
    return `<span class="t-item"><span class="tag">${(o.opportunity_type||'—').toUpperCase().slice(0,4)}</span> <span>${o.player_name}</span> <span class="n ${cls}">${arrow} ${o.ob1_score}</span></span>`;
  });
  track.innerHTML = (items.join('<span class="dot">/</span>') + '<span class="dot">/</span>').repeat(2);
}

/* ============ PAINT: GRID ============ */

function paintGrid(){
  const g = el('#grid');
  const empty = el('#empty');
  if (STATE.filtered.length === 0){
    g.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  g.innerHTML = STATE.filtered.map(card).join('');
  els('.card', g).forEach(c=>{
    c.addEventListener('click', ()=>{
      const o = STATE.all.find(x=>x.id===c.dataset.id);
      if (o) openDrawer(o);
    });
  });
}

function card(o){
  const type = (o.opportunity_type||'').toLowerCase();
  const role = safe(o.role_name, o.role || '—');
  const club = safe(o.current_club, 'Svincolato');
  const age = o.age!=null ? `${o.age}a` : '';
  const intel = o.intel || {};
  const roiClass = intel.roi_class || '';
  const roiTag = (roiClass && roiClass!=='none' && roiClass!=='unknown')
    ? `<span class="tag roi-${roiClass}">ROI x${intel.moltiplicatore||0}</span>` : '';
  const u21Tag = (o.age!=null && o.age<=21) ? `<span class="tag u21">U21</span>` : '';
  const typeTag = type ? `<span class="tag type-${type}">${type.toUpperCase()}</span>` : '';

  let days = o._days;
  let daysText;
  let daysUnit;
  if (o._isFree){
    const dwc = o.days_without_contract || 0;
    daysText = dwc === 0 ? 'FREE' : dwc;
    daysUnit = dwc === 0 ? 'JUST AVAIL.' : 'GG FREE';
  } else if (days == null){
    daysText = '∞';
    daysUnit = 'N/A';
  } else if (days < 0){
    daysText = '—';
    daysUnit = 'SCADUTO';
  } else {
    if (days > 999) { daysText = Math.round(days/30); daysUnit = 'MESI'; }
    else { daysText = days; daysUnit = 'GG CTR'; }
  }

  return `
<article class="card" data-id="${o.id}" data-urgency="${o._urgency}" data-tier="${o._tier}">
  <span class="urgency"></span>
  <div class="card-head">
    <div class="name-block">
      <div class="name">${esc(o.player_name)}</div>
      <div class="meta">
        <span class="role">${esc(role)}</span>
        ${age?`<span class="sep">·</span><span class="age">${age}</span>`:''}
        <span class="sep">·</span>
        <span>${esc(club)}</span>
      </div>
    </div>
    <div class="score">${o.ob1_score}<span class="dlabel">OB1</span></div>
  </div>
  <div class="card-body">
    <div class="tag-row">
      ${typeTag}${u21Tag}${roiTag}
    </div>
    <div class="timer">
      <div class="days">${daysText}</div>
      <span class="unit">${daysUnit}</span>
    </div>
  </div>
  <div class="card-bar"><div class="fill" style="width:${o._barPct}%"></div></div>
</article>`;
}

function esc(s){ return String(s ?? '').replace(/[<>&"']/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":"&#39;"}[c])); }

/* ============ DRAWER ============ */

function openDrawer(o){
  const brief = el('#brief');
  const type = (o.opportunity_type||'').toLowerCase();
  const role = safe(o.role_name, o.role || '—');
  const club = safe(o.current_club, 'Svincolato');
  const intel = o.intel || {};

  el('#breadName').textContent = (o.player_name||'').toUpperCase();

  let urgencyLine = '';
  let urgencyDate = '';
  let urgencyBadge = 'CONTRATTO';
  if (o._isFree){
    const dwc = o.days_without_contract||0;
    urgencyLine = dwc === 0 ? 'Appena svincolato' : `${dwc} giorni senza squadra`;
    urgencyDate = o._stale_free_agent ? 'stale' : 'fresh';
    urgencyBadge = 'SVINCOLATO';
  } else if (o._days != null){
    const exp = new Date(o.contract_expires);
    urgencyDate = exp.toLocaleDateString('it-IT', { day:'2-digit', month:'short', year:'numeric' });
    if (o._days < 0) urgencyLine = 'Contratto scaduto';
    else if (o._days === 0) urgencyLine = 'Scade oggi';
    else if (o._days <= 30) urgencyLine = `Scade in <${o._days} giorni`;
    else if (o._days <= 365) urgencyLine = `Scade tra ~${Math.round(o._days/30)} mesi`;
    else urgencyLine = `Scade tra ${Math.round(o._days/365*10)/10} anni`;
  } else {
    urgencyLine = 'Contratto non noto';
    urgencyDate = '—';
  }

  const daysHeadline = o._isFree
    ? ((o.days_without_contract||0) === 0 ? 'FREE' : `${o.days_without_contract}gg`)
    : (o._days == null ? '—' : (o._days < 0 ? 'SCAD.' : (o._days > 999 ? `${Math.round(o._days/30)}m` : `${o._days}gg`)));

  const stats = [
    { v: safe(o.appearances, 0), l: 'PRES' },
    { v: safe(o.goals, 0),       l: 'GOAL' },
    { v: safe(o.assists, 0),     l: 'ASS' },
    { v: o.market_value_formatted ? shortMoney(o.market_value_formatted) : (o.age!=null?o.age:'—'), l: o.market_value_formatted ? 'VALORE' : 'ETÀ' },
  ];

  const mvCell = o.market_value_formatted ? `<div class="cell"><span class="k">VALORE</span><span class="v">${esc(o.market_value_formatted)}</span></div>`:'';
  const natCell = o.nationality ? `<div class="cell"><span class="k">NAZ.</span><span class="v">${esc(o.nationality)}${o.second_nationality?` / ${esc(o.second_nationality)}`:''}</span></div>`:'';
  const footCell = o.foot ? `<div class="cell"><span class="k">PIEDE</span><span class="v">${esc(o.foot)}</span></div>`:'';
  const ageCell = o.age!=null ? `<div class="cell"><span class="k">ETÀ</span><span class="v">${o.age} anni</span></div>`:'';
  const agentCell = o.agent ? `<div class="cell"><span class="k">AGENTE</span><span class="v">${esc(o.agent)}</span></div>`:'';
  const clubCell = `<div class="cell"><span class="k">CLUB</span><span class="v">${esc(club)}</span></div>`;
  const typeCell = `<div class="cell"><span class="k">TIPO</span><span class="v" style="text-transform:uppercase;">${esc(type||'—')}</span></div>`;
  const discoveredCell = o.discovered_at ? `<div class="cell"><span class="k">SCOPERTO</span><span class="v">${new Date(o.discovered_at).toLocaleDateString('it-IT')}</span></div>`:'';

  const metaCells = [clubCell, typeCell, ageCell, natCell, footCell, mvCell, agentCell, discoveredCell].filter(Boolean);
  if (metaCells.length % 2) metaCells.push('<div class="cell"></div>');

  const bd = o.score_breakdown || {};
  const bdLabels = {
    freshness:'FRESCHEZZA', opportunity_type:'TIPO', experience:'ESPERIENZA',
    age:'ETÀ', market_value:'VALORE', league_fit:'LEGA', source:'FONTE', completeness:'DATI'
  };
  const bdHtml = Object.entries(bd).map(([k,v])=>{
    const cls = v>=70?'good':v>=40?'mid':'low';
    return `<div class="bd-row"><span class="bk">${bdLabels[k]||k}</span><div class="bt"><div class="bf ${cls}" style="width:${v}%"></div></div><span class="bv">${v}</span></div>`;
  }).join('');

  let intelHtml = '';
  if (intel.roi_class && intel.roi_class !== 'unknown'){
    const accClass = intel.roi_class==='elite'||intel.roi_class==='high' ? 'acc' : (intel.roi_class==='medium' ? 'blue' : '');
    intelHtml = `
      <div class="sect">
        <div class="sect-title">INTEL_MINUTAGGIO<span class="dim">${intel.roi_label||''}</span></div>
        <div class="intel-grid">
          <div class="intel-cell ${accClass}"><div class="k">ROI</div><div class="v">${esc(intel.roi_label||'—')}</div></div>
          <div class="intel-cell"><div class="k">MOLTIPLICATORE</div><div class="v">×${intel.moltiplicatore||0}</div></div>
          <div class="intel-cell"><div class="k">COEFF. ETÀ</div><div class="v">×${intel.coefficiente_eta||0}</div></div>
          <div class="intel-cell"><div class="k">PROIEZIONE</div><div class="v">${intel.proiezione_stagionale||0}<span style="font-size:11px;color:var(--ink-mute);font-weight:400"> min</span></div></div>
        </div>
        ${intel.roi_dettaglio?`<div class="intel-note">${esc(intel.roi_dettaglio)}</div>`:''}
        ${intel.traffic_light?`<div class="lista ${intel.traffic_light}"><span class="light"></span><div><div class="lista-main">LISTA FIGC :: ${esc(intel.traffic_label||'—')}</div><div class="lista-sub">${esc(intel.lista_dettaglio||'')}</div></div></div>`:''}
      </div>`;
  }

  const signalsHtml = (intel.signals && intel.signals.length) ? `
    <div class="sect">
      <div class="sect-title">SEGNALI</div>
      <div class="signals">
        ${intel.signals.map(s=>`<div class="signal ${s.severity}"><div class="sl">${esc(s.label)}</div><div class="sd">${esc(s.detail)}</div></div>`).join('')}
      </div>
    </div>` : '';

  const summaryText = o.recommendation || o.summary || '';
  const prevClubs = Array.isArray(o.previous_clubs) && o.previous_clubs.length ? o.previous_clubs.join(' → ') : '';

  brief.innerHTML = `
    <div class="brief-head">
      <div>
        <div class="name">${esc(o.player_name)}</div>
        <div class="sub">
          <span class="role">${esc(role)}</span>
          ${o.age!=null?`<span class="sep">·</span><span>${o.age} anni</span>`:''}
          <span class="sep">·</span><span>${esc(club)}</span>
          ${o.nationality?`<span class="sep">·</span><span>${esc(o.nationality)}</span>`:''}
        </div>
      </div>
      <div class="big-score ${o._tier}">${o.ob1_score}<div class="pct">/100 OB1</div></div>
    </div>

    <div class="urgency-bloc" data-urgency="${o._urgency}">
      <span class="badge">${urgencyBadge}</span>
      <div class="line">
        <span class="strong">${esc(urgencyLine)}</span>
        <span>${esc(urgencyDate)}</span>
      </div>
      <div class="countdown">${daysHeadline}</div>
    </div>

    ${summaryText ? `<div class="summary">${esc(summaryText)}</div>` : ''}

    <div class="strip">
      ${stats.map(s=>`<div class="cell"><span class="v">${s.v}</span><span class="l">${s.l}</span></div>`).join('')}
    </div>

    <div class="sect">
      <div class="sect-title">META<span class="dim">${o.id||''}</span></div>
      <div class="meta-grid">${metaCells.join('')}</div>
      ${prevClubs ? `<div class="intel-note"><span style="color:var(--ink-mute);letter-spacing:.12em;font-size:10px;">PASSATO </span>${esc(prevClubs)}</div>` : ''}
    </div>

    ${intelHtml}
    ${signalsHtml}

    <div class="sect">
      <div class="sect-title">SCORE_BREAKDOWN<span class="dim">ob1: ${o.ob1_score}</span></div>
      <div>${bdHtml}</div>
    </div>
  `;

  const srcLink = el('#sourceLink');
  if (o.source_url){
    srcLink.href = o.source_url;
    srcLink.textContent = `APRI FONTE :: ${(o.source_name||'link').toUpperCase()} ↗`;
    srcLink.style.display = '';
  } else {
    srcLink.style.display = 'none';
  }

  const tmLink = el('#tmLink');
  const tmQuery = encodeURIComponent(o.player_name || '');
  tmLink.href = `https://www.transfermarkt.it/schnellsuche/ergebnis/schnellsuche?query=${tmQuery}`;

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
  if (s.includes('mln')) return s.replace('mln','M').replace(',','.').replace(/\s+/g,'');
  if (s.includes('mila')) return s.replace('mila','K').replace(',','.').replace(/\s+/g,'');
  return s;
}

/* ============ CYCLE STATUS ============ */

function updateCycle(){
  if (!STATE.lastUpdate) return;
  const last = new Date(STATE.lastUpdate);
  const now = new Date();
  const diffMs = Math.max(0, now - last);
  const diffH = Math.floor(diffMs / 3600000);
  const diffM = Math.floor((diffMs % 3600000) / 60000);
  const nextMs = Math.max(0, (6 * 3600000) - diffMs);
  const nH = Math.floor(nextMs/3600000), nM = Math.floor((nextMs%3600000)/60000);
  const hh = String(last.getHours()).padStart(2,'0');
  const mm = String(last.getMinutes()).padStart(2,'0');
  const ago = diffH > 0 ? `${diffH}h${diffM}m ago` : `${diffM}m ago`;
  const next = nextMs > 0 ? `next ${nH}h${nM}m` : 'cycling…';
  el('#cycleStatus').textContent = `OUROBOROS :: ${hh}:${mm} (${ago}) // ${next}`;
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
  el('#typeF').addEventListener('change', e=>{ STATE.type = e.target.value; applyFilter(); });
  el('#sortBy').addEventListener('change', e=>{ STATE.sort = e.target.value; applyFilter(); });
}

function wireDrawer(){
  el('#closeBtn').addEventListener('click', closeDrawer);
  el('#ov').addEventListener('click', e=>{ if (e.target.id === 'ov') closeDrawer(); });
  document.addEventListener('keydown', e=>{ if (e.key === 'Escape') closeDrawer(); });
}

function wireKeyShortcuts(){
  document.addEventListener('keydown', e=>{
    if (e.key === '/' && document.activeElement !== el('#q')){
      e.preventDefault();
      el('#q').focus();
    }
  });
}

function debounce(fn, ms){ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }

/* ============ TWEAKS ============ */

function applyTweaksFromDefaults(){
  const t = (window.TWEAK_DEFAULTS || {});
  setAccent(t.accent || '#00ff66');
  document.documentElement.setAttribute('data-density', t.density || 'comfortable');
  document.documentElement.setAttribute('data-card-style', t.cardStyle || 'brief');
  document.documentElement.setAttribute('data-score-weight', t.scoreWeight || 'heavy');
  document.documentElement.setAttribute('data-urgency-mode', t.urgencyMode || 'bar');
  window.__tweaks = {...t};
}

function setAccent(c){
  document.documentElement.style.setProperty('--acc', c);
  document.documentElement.style.setProperty('--acc-dim', c);
  document.documentElement.style.setProperty('--acc-bg', hexWithAlpha(c, .1));
}
function hexWithAlpha(hex, a){
  if (!hex.startsWith('#') || hex.length<7) return `rgba(0,255,102,${a})`;
  const r = parseInt(hex.slice(1,3),16), g=parseInt(hex.slice(3,5),16), b=parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${a})`;
}

function persistTweak(k, v){
  window.__tweaks = {...(window.__tweaks||{}), [k]: v};
  try { window.parent.postMessage({type:'__edit_mode_set_keys', edits:{[k]: v}}, '*'); } catch(_){}
}

function wireTweaks(){
  const panel = el('#tweaks');
  window.addEventListener('message', e=>{
    if (!e.data) return;
    if (e.data.type === '__activate_edit_mode'){ panel.classList.add('open'); refreshTweakUI(); }
    if (e.data.type === '__deactivate_edit_mode'){ panel.classList.remove('open'); }
  });
  try { window.parent.postMessage({type:'__edit_mode_available'}, '*'); } catch(_){}

  el('#tweakClose').addEventListener('click', ()=>panel.classList.remove('open'));

  el('#swatches').addEventListener('click', e=>{
    const sw = e.target.closest('.sw'); if (!sw) return;
    const c = sw.dataset.c;
    setAccent(c);
    persistTweak('accent', c);
    refreshTweakUI();
  });

  els('.opts').forEach(g=>{
    g.addEventListener('click', e=>{
      const b = e.target.closest('button'); if (!b) return;
      const key = g.dataset.tw;
      const v = b.dataset.v;
      if (key === 'density') document.documentElement.setAttribute('data-density', v);
      if (key === 'cardStyle') document.documentElement.setAttribute('data-card-style', v);
      if (key === 'scoreWeight') document.documentElement.setAttribute('data-score-weight', v);
      if (key === 'urgencyMode') document.documentElement.setAttribute('data-urgency-mode', v);
      persistTweak(key, v);
      refreshTweakUI();
    });
  });

  refreshTweakUI();
}

function refreshTweakUI(){
  const t = window.__tweaks || {};
  els('#swatches .sw').forEach(s => s.classList.toggle('on', s.dataset.c === t.accent));
  els('.opts').forEach(g=>{
    const key = g.dataset.tw;
    els('button', g).forEach(b=> b.classList.toggle('on', b.dataset.v === t[key]));
  });
}
