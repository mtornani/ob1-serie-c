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

const TIER_LABEL = { hot: 'occasione', warm: 'da seguire', cold: 'archivio' };

const el  = (s, r=document) => r.querySelector(s);
const els = (s, r=document) => [...r.querySelectorAll(s)];
const safe = (v, f='—') => (v===null||v===undefined||v===''||v==='null') ? f : v;

document.addEventListener('DOMContentLoaded', init);

async function init(){
  wireKeyShortcuts();
  wireControls();
  wireDrawer();

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

  applyUrlFilter();
  updateCycle();
  checkStale();
  setInterval(updateCycle, 30000);
  trackSession();
  paintCounters();
  applyFilter();
}

/* Deep-link / PWA shortcut: ?filter=hot|free|under|verified|new */
function applyUrlFilter(){
  const f = new URLSearchParams(location.search).get('filter');
  const valid = ['all','hot','under','free','verified','new'];
  if (!f || !valid.includes(f)) return;
  STATE.filter = f;
  const chip = el(`.chip[data-f="${f}"]`);
  if (chip){ els('.chip').forEach(x=>x.classList.remove('on')); chip.classList.add('on'); }
}

/* Register the service worker so the app is installable + works offline */
if ('serviceWorker' in navigator){
  window.addEventListener('load', ()=>{
    navigator.serviceWorker.register('sw.js').catch(err=>console.warn('[OB1] SW registration failed', err));
  });
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
  else if (STATE.filter === 'verified') list = list.filter(o => o.market_value != null || o.appearances != null);
  else if (STATE.filter === 'urgent') list = list.filter(o=>o._urgency==='critical'||o._urgency==='high');
  else if (STATE.filter === 'new'){
    const cutoff = Date.now() - 30 * 86400000;
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
  const urgent   = all.filter(o=>o._urgency==='critical'||o._urgency==='high').length;
  const verified = all.filter(o => o.market_value != null || o.appearances != null).length;
  const cutoff30 = Date.now() - 30 * 86400000;
  const newCt  = all.filter(o => o.discovered_at && new Date(o.discovered_at).getTime() >= cutoff30).length;

  el('#ctHot').textContent  = hot;
  el('#ctFree').textContent = free;
  el('#ctU21').textContent  = u21;
  el('#ctAll').textContent  = all.length;

  const map = { all:all.length, hot, free, under:u21, verified, urgent, new:newCt };
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

function card(o){
  const type  = (o.opportunity_type||'').toLowerCase();
  const roleRaw = o.role_name || o.role || '';
  const role  = /^(n\/d|n\/a|none|—|-)?$/i.test(roleRaw.trim()) ? '' : roleRaw;
  const club  = safe(o.current_club, 'Svincolato');
  const age   = o.age!=null ? `${o.age} anni` : '';
  const typeTag = type ? `<span class="tag type-${type}">${type.toUpperCase()}</span>` : '';
  const daysOld = o.discovered_at ? Math.round((Date.now() - new Date(o.discovered_at)) / 86400000) : null;
  const newTag  = (daysOld !== null && daysOld <= 3) ? `<span class="tag new-signal">NUOVO</span>` : '';
  const tmTag   = o.tm_enriched === true ? `<span class="tag tm-ok">Verificato</span>` : '';

  let daysText, daysUnit;
  if (o._isFree){
    const dwc = o.days_without_contract || 0;
    daysText = dwc === 0 ? 'oggi' : dwc;
    daysUnit = dwc === 0 ? 'appena svincolato' : (dwc === 1 ? 'giorno da svincolato' : 'giorni da svincolato');
  } else if (o._days == null){
    daysText = '—';
    daysUnit = '';
  } else if (o._days < 0){
    daysText = '—';
    daysUnit = 'contratto scaduto';
  } else {
    if (o._days > 730) { daysText = Math.round(o._days/30); daysUnit = 'mesi alla scadenza'; }
    else               { daysText = o._days;                 daysUnit = o._days === 1 ? 'giorno alla scadenza' : 'giorni alla scadenza'; }
  }

  return `
<article class="card" data-id="${o.id}" data-urgency="${o._urgency}" data-tier="${o._tier}" tabindex="0" role="button" aria-label="${esc(o.player_name)}, punteggio ${o.ob1_score}">
  <span class="urgency"></span>
  <div class="card-head">
    <div class="name-block">
      <div class="name">${esc(o.player_name)}</div>
      <div class="meta">
        ${[role && `<span class="role">${esc(role)}</span>`, age && `<span class="age">${age}</span>`, `<span class="club">${esc(club)}</span>`].filter(Boolean).join('<span class="sep">·</span>')}
      </div>
    </div>
    <div class="score">${o.ob1_score}<span class="dlabel">${TIER_LABEL[o._tier]||''}</span></div>
  </div>
  <div class="card-body">
    <div class="tag-row">${typeTag}${tmTag}${newTag}</div>
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

const SCORE_WEIGHTS = { freshness:15, opportunity_type:10, experience:20, age:15, market_value:15, league_fit:15, source:5, completeness:5 };

function scoreReason(k, v, o) {
  switch (k) {
    case 'freshness':
      return v >= 90 ? 'Segnalato oggi o ieri'
           : v >= 70 ? 'Notizia di questa settimana'
           : v >= 40 ? 'Notizia recente (meno di 30 giorni)'
           : 'Notizia datata — verificare disponibilità';
    case 'opportunity_type': {
      const t = (o.opportunity_type||'').toLowerCase();
      if (t === 'svincolato')  return 'Svincolato — zero costi di cartellino';
      if (t === 'rescissione') return 'Rescissione — in uscita dal club';
      if (t === 'prestito')    return 'Prestito — investimento contenuto';
      if (t === 'scadenza')    return 'Contratto in scadenza — da muovere subito';
      return 'Opportunità generica di mercato';
    }
    case 'experience':
      if (o.appearances != null) {
        const a = o.appearances;
        return a >= 150 ? `${a} presenze — veterano di categoria`
             : a >= 80  ? `${a} presenze — esperienza solida`
             : a >= 30  ? `${a} presenze — profilo emergente`
             : `${a} presenze — ancora poca esperienza`;
      }
      return 'Presenze non ancora verificate su Transfermarkt';
    case 'age':
      if (o.age != null) {
        const a = o.age;
        return a <= 22 ? `${a} anni — profilo U23, ideale per minutaggio FIGC`
             : a <= 26 ? `${a} anni — picco della carriera`
             : a <= 29 ? `${a} anni — esperienza matura`
             : a <= 32 ? `${a} anni — esperienza ma futuribilità limitata`
             : `${a} anni — profilo senior`;
      }
      return 'Età non disponibile';
    case 'market_value':
      if (o.market_value_formatted) return `Valore TM: ${o.market_value_formatted}`;
      if (o.market_value) return `Valore stimato: ${Math.round(o.market_value/1000)}k€`;
      return 'Valore di mercato non ancora verificato su TM';
    case 'league_fit':
      return v >= 80 ? 'Profilo nella fascia giusta per la Lega Pro'
           : v >= 50 ? 'Pertinenza Lega Pro da confermare'
           : 'Profilo fuori categoria target';
    case 'source':
      return v >= 80 ? `Fonte specializzata: ${o.source_name||''}`
           : v >= 60 ? `Fonte verificata: ${o.source_name||''}`
           : 'Trovato dalla ricerca automatica — da confermare su fonte diretta';
    case 'completeness': {
      const have = ['nationality','foot','agent','appearances','market_value'].filter(f=>o[f]!=null).length;
      return have >= 4 ? `Profilo completo — ${have}/5 dati verificati su TM`
           : have >= 2 ? `Profilo parziale — ${have}/5 dati verificati (arricchimento in corso)`
           : `Profilo quasi vuoto — ${have}/5 campi, arricchimento necessario`;
    }
    default: return '';
  }
}

function scoreVerdict(o) {
  const bd = o.score_breakdown || {};
  const s  = o.ob1_score || 0;

  const plusFn = {
    opportunity_type: () => { const t=(o.opportunity_type||'').toLowerCase(); return t==='svincolato'?'parametro zero':t==='rescissione'?'in uscita dal club':t==='prestito'?'disponibile in prestito':null; },
    age:              () => o.age ? (o.age<=22?`U23 (${o.age}a)`:`${o.age} anni`) : null,
    experience:       () => o.appearances!=null ? `${o.appearances} presenze` : null,
    freshness:        () => 'notizia fresca',
    market_value:     () => o.market_value_formatted || null,
  };
  const minusLabel = { experience:'presenze da verificare', market_value:'valore non confermato', league_fit:'categoria da confermare', source:'fonte non specializzata', completeness:'profilo incompleto' };

  const strong = Object.entries(bd).filter(([k,v])=>v>=75&&plusFn[k]).map(([k])=>plusFn[k]?.()).filter(Boolean).slice(0,3);
  const weak   = Object.entries(bd).filter(([k,v])=>v<50&&minusLabel[k]).map(([k])=>minusLabel[k]).filter(Boolean).slice(0,2);
  const action = s>=70 ? 'Contattare subito.' : s>=57 ? 'Tenere d\'occhio.' : 'Bassa priorità.';

  const parts = [];
  if (strong.length) parts.push(strong.join(' + '));
  if (weak.length)   parts.push(`Penalizza: ${weak.join(', ')}`);
  parts.push(action);
  return parts.join(' — ');
}

function openDrawer(o){
  trackDrawerOpen(o.player_name);

  const brief = el('#brief');
  const type  = (o.opportunity_type||'').toLowerCase();
  const roleRaw = o.role_name || o.role || '';
  const role  = /^(n\/d|n\/a|none|—|-)?$/i.test(roleRaw.trim()) ? '' : roleRaw;
  const club  = safe(o.current_club, 'Svincolato');

  el('#breadName').textContent = o.player_name || '';

  let urgencyLine = '', urgencyDate = '', urgencyBadge = 'Contratto';
  if (o._isFree){
    const dwc = o.days_without_contract||0;
    urgencyLine  = dwc === 0 ? 'Appena svincolato' : 'Attualmente svincolato';
    urgencyDate  = o._stale_free_agent ? 'da verificare' : 'disponibile subito';
    urgencyBadge = 'Svincolato';
  } else if (o._days != null){
    const exp = new Date(o.contract_expires);
    urgencyDate = exp.toLocaleDateString('it-IT', { day:'2-digit', month:'short', year:'numeric' });
    if (o._days < 0)       urgencyLine = 'Contratto scaduto';
    else if (o._days === 0) urgencyLine = 'Scade oggi';
    else if (o._days <= 30) urgencyLine = `Scade tra meno di ${o._days} giorni`;
    else if (o._days <= 365) urgencyLine = `Scade tra circa ${Math.round(o._days/30)} mesi`;
    else urgencyLine = `Scade tra ${Math.round(o._days/365*10)/10} anni`;
  } else {
    urgencyLine = 'Scadenza non disponibile';
    urgencyDate = '—';
  }

  const daysHeadline = o._isFree
    ? ((o.days_without_contract||0) === 0 ? 'oggi' : `${o.days_without_contract} gg`)
    : (o._days == null ? '—' : (o._days < 0 ? 'scaduto' : (o._days > 999 ? `${Math.round(o._days/30)} mesi` : `${o._days} gg`)));

  const stats = [
    { v: safe(o.appearances, '—'), l: 'PRESENZE' },
    { v: safe(o.goals, '—'),       l: 'GOL' },
    { v: safe(o.assists, '—'),     l: 'ASSIST' },
    { v: o.market_value_formatted ? shortMoney(o.market_value_formatted) : (o.age!=null?o.age:'—'),
      l: o.market_value_formatted ? 'VALORE' : 'ETÀ' },
  ];

  const mvCell        = o.market_value_formatted ? `<div class="cell"><span class="k">VALORE</span><span class="v">${esc(o.market_value_formatted)}</span></div>`:'';
  const natCell       = o.nationality ? `<div class="cell"><span class="k">NAZIONALITÀ</span><span class="v">${esc(o.nationality)}${o.second_nationality?` / ${esc(o.second_nationality)}`:''}</span></div>`:'';
  const footCell      = o.foot ? `<div class="cell"><span class="k">PIEDE</span><span class="v">${esc(o.foot)}</span></div>`:'';
  const ageCell       = o.age!=null ? `<div class="cell"><span class="k">ETÀ</span><span class="v">${o.age} anni</span></div>`:'';
  const agentCell     = o.agent ? `<div class="cell"><span class="k">AGENTE</span><span class="v">${esc(o.agent)}</span></div>`:'';
  const clubCell      = `<div class="cell"><span class="k">CLUB ATTUALE</span><span class="v">${esc(club)}</span></div>`;
  const typeCell      = `<div class="cell"><span class="k">TIPO</span><span class="v" style="text-transform:uppercase;">${esc(type||'—')}</span></div>`;
  const discoveredCell = o.discovered_at ? (()=>{
    const d = new Date(o.discovered_at);
    if (isNaN(d.getTime())) return '';
    return `<div class="cell"><span class="k">SEGNALATO IL</span><span class="v">${d.toLocaleDateString('it-IT')}</span></div>`;
  })() : '';

  const metaCells = [clubCell, typeCell, ageCell, natCell, footCell, mvCell, agentCell, discoveredCell].filter(Boolean);
  if (metaCells.length % 2) metaCells.push('<div class="cell"></div>');

  const bdLabels = {
    freshness:       'Notizia recente',
    opportunity_type:'Tipo opportunità',
    experience:      'Esperienza in carriera',
    age:             'Fascia d\'età ideale',
    market_value:    'Valore di mercato',
    league_fit:      'Adatto alla categoria',
    source:          'Fonte affidabile',
    completeness:    'Dati disponibili',
  };
  const bd = o.score_breakdown || {};
  const bdHtml = Object.entries(bd).map(([k,v])=>{
    const icon = v>=75?'✅':v>=45?'⚡':'❌';
    const cls  = v>=75?'good':v>=45?'mid':'low';
    const lbl  = bdLabels[k]||k;
    const wt   = SCORE_WEIGHTS[k] ? `<span class="reason-weight"> ${SCORE_WEIGHTS[k]}%</span>` : '';
    const why  = esc(scoreReason(k, v, o));
    return `<div class="reason-row"><span class="reason-icon">${icon}</span><div class="reason-body"><span class="reason-label">${lbl}${wt}</span><span class="reason-text">${why}</span></div><span class="reason-score ${cls}">${v}</span></div>`;
  }).join('');
  const verdict = scoreVerdict(o);

  const summaryText = o.recommendation || o.summary || '';
  const prevClubs   = Array.isArray(o.previous_clubs) && o.previous_clubs.length ? o.previous_clubs.join(' → ') : '';
  const intel       = o.intel || {};

  // Stats strip: only render if at least one stat has real data
  const hasStats = o.appearances != null || o.goals != null || o.assists != null || o.market_value_formatted;
  const seasonNote = o.season ? `<div style="font-size:10px;color:var(--ink-mute);letter-spacing:.08em;margin-top:4px">stagione ${esc(o.season)}</div>` : '';
  const stripHtml = hasStats
    ? `<div class="strip">${stats.map(s=>`<div class="cell"><span class="v">${s.v}</span><span class="l">${s.l}</span></div>`).join('')}</div>${seasonNote}`
    : `<div class="strip-empty">Statistiche in arrivo — verifica su Transfermarkt in corso</div>`;

  // Minutaggio FIGC — una sola riga in linguaggio piano. I dettagli
  // (moltiplicatori, proiezioni) restano nei report privati, non qui.
  let minutaggioHtml = '';
  if (intel.traffic_light === 'green') {
    const bonus = ['elite','high','medium'].includes(intel.roi_class)
      ? ' e porta contributi minutaggio giovani' : '';
    minutaggioHtml = `<div class="intel-note" style="border-left:3px solid var(--acc);padding-left:10px;">✓ Under per le liste FIGC${bonus}</div>`;
  } else if (intel.traffic_light === 'red') {
    minutaggioHtml = `<div class="intel-note" style="border-left:3px solid var(--ink-mute);padding-left:10px;">Occupa un posto Over in lista</div>`;
  }

  // Segnali contrattuali
  const signalsHtml = (intel.signals && intel.signals.length) ? `
    <div class="sect">
      <div class="sect-title">SEGNALI</div>
      <div class="signals">
        ${intel.signals.map(s=>`<div class="signal ${s.severity}"><div class="sl">${esc(s.label)}</div><div class="sd">${esc(s.detail)}</div></div>`).join('')}
      </div>
    </div>` : '';

  brief.innerHTML = `
    <div class="brief-head">
      <div>
        <div class="name">${esc(o.player_name)}</div>
        <div class="sub">
          ${[role && `<span class="role">${esc(role)}</span>`, o.age!=null && `<span>${o.age} anni</span>`, `<span>${esc(club)}</span>`, o.nationality && `<span>${esc(o.nationality)}</span>`].filter(Boolean).join('<span class="sep">·</span>')}
        </div>
      </div>
      <div class="big-score ${o._tier}">${o.ob1_score}<div class="pct">/100</div></div>
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

    ${stripHtml}

    <div class="sect">
      <div class="sect-title">SCHEDA</div>
      <div class="meta-grid">${metaCells.join('')}</div>
      ${prevClubs ? `<div class="intel-note"><span style="color:var(--ink-mute);letter-spacing:.12em;font-size:10px;">STORICO CLUB </span>${esc(prevClubs)}</div>` : ''}
    </div>

    ${minutaggioHtml}
    ${signalsHtml}

    <details class="score-details sect">
      <summary>Perché questo punteggio<span class="dim">${TIER_LABEL[o._tier]||''}</span></summary>
      <div class="score-body">
        <div class="verdict-note">${esc(verdict)}</div>
        <div>${bdHtml}</div>
      </div>
    </details>
  `;

  // Links that ALWAYS resolve. A direct URL is used only when it's a real,
  // durable link; otherwise we fall back to a Google search, which never 404s.
  const google = (terms) => `https://www.google.com/search?q=${encodeURIComponent(terms)}`;
  const isRealUrl = (u) => typeof u === 'string' && u.startsWith('http')
    && !u.includes('vertexaisearch') && !u.includes('grounding-api');

  const srcLink = el('#sourceLink');
  if (isRealUrl(o.source_url)){
    srcLink.href = o.source_url;
    srcLink.textContent = 'Leggi la notizia ↗';
  } else {
    srcLink.href = google(`${o.player_name||''} ${o.current_club||'Serie C'} calcio`);
    srcLink.textContent = 'Cerca notizie ↗';
  }

  const tmLink = el('#tmLink');
  tmLink.href = isRealUrl(o.tm_url) ? o.tm_url : google(`${o.player_name||''} transfermarkt`);
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

