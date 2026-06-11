/* ── Porra Mundial 2026 — app.js ─────────────────────────────────────────── */
'use strict';

// ── Config ───────────────────────────────────────────────────────────────────
// Cambiar estas contraseñas antes de publicar.
const PASSWORDS = {
  amigos:  'maristada',
  trabajo: 'cosmeticallyyours',
};

const DATA_BASE = 'data/';
const REFRESH_MS = 45_000;
const LIVE_CHECK_MS = 20_000;

const SESSION_KEY    = 'porra_session';
const WC_START       = new Date('2026-06-11T19:00:00Z'); // 11 jun 21:00 CEST
const PREVIEW_TOKEN  = 'preview2026';                    // ?preview=preview2026 bypasses gate

// ── State ────────────────────────────────────────────────────────────────────
let state = {
  porra: null,
  standings: null,
  detalle: null,
  proximos: null,
  snapshots: null,
  resultados: null,
  selectedNick: null,
  activeTab: 'mi-porra',
  prevStandings: null,
  refreshTimer: null,
  lastUpdate: null,
  showAllPending: false,
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('es-ES', { weekday:'short', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'Europe/Madrid' });
}
function fmtTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString('es-ES', { hour:'2-digit', minute:'2-digit', timeZone:'Europe/Madrid' });
}
function fmtPts(n) { return n === null || n === undefined ? '—' : String(n); }

// Paleta de colores para gráficos (por índice)
const PALETTE = ['#c9921a','#5b9cf6','#4ade80','#fb923c','#a78bfa','#38bdf8','#f472b6','#facc15'];

function nickColor(idx) { return PALETTE[idx % PALETTE.length]; }

// ── Password Screen ───────────────────────────────────────────────────────────
$('pw-toggle').addEventListener('click', () => {
  const inp = $('pw-input');
  inp.type = inp.type === 'password' ? 'text' : 'password';
});

$('pw-input').addEventListener('keydown', e => { if (e.key === 'Enter') tryLogin(); });
$('pw-submit').addEventListener('click', tryLogin);

function tryLogin() {
  const pw = $('pw-input').value.trim();
  // Detecta la porra por la contraseña introducida
  const porra = Object.entries(PASSWORDS).find(([, secret]) => pw === secret)?.[0];
  if (!porra) {
    $('pw-error').textContent = 'Contraseña incorrecta';
    $('pw-input').value = '';
    $('pw-input').focus();
    return;
  }
  $('pw-error').textContent = '';
  enterApp(porra);
}

async function enterApp(porra) {
  state.porra = porra;
  sessionStorage.setItem(SESSION_KEY, porra);
  $('password-screen').style.display = 'none';
  $('app').style.display = 'flex';
  $('salir-btn').title = `Porra: ${porra}`;

  // Logo: solo visible en porra trabajo
  $('trabajo-logo').classList.toggle('hidden', porra !== 'trabajo');

  await loadAll();
  renderActiveTab();
  startRefreshLoop();
  startLiveCheck();
}

$('salir-btn').addEventListener('click', () => {
  clearRefreshLoop();
  state.porra = null;
  sessionStorage.removeItem(SESSION_KEY);
  $('trabajo-logo').classList.add('hidden');
  $('app').style.display = 'none';
  $('password-screen').style.display = 'flex';
  $('pw-input').value = '';
  $('pw-error').textContent = '';
  $('pw-input').focus();
});

// ── Data Loading ─────────────────────────────────────────────────────────────
async function fetchJSON(url) {
  try {
    const r = await fetch(url + '?_=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch(e) {
    console.warn('fetch failed:', url, e);
    return null;
  }
}

async function loadAll() {
  const p = state.porra;
  const [standings, detalle, proximos, snapshots, resultados] = await Promise.all([
    fetchJSON(`${DATA_BASE}${p}/standings.json`),
    fetchJSON(`${DATA_BASE}${p}/detalle.json`),
    fetchJSON(`${DATA_BASE}${p}/proximos.json`),
    fetchJSON(`${DATA_BASE}${p}/snapshots.json`),
    fetchJSON(`${DATA_BASE}resultados.json`),
  ]);
  state.prevStandings = state.standings;
  state.standings  = standings;
  state.detalle    = detalle;
  state.proximos   = proximos;
  state.snapshots  = snapshots;
  state.resultados = resultados;
  state.lastUpdate = new Date();
  updateRefreshBar();
  checkLive();
}

// ── Refresh Loop ──────────────────────────────────────────────────────────────
function startRefreshLoop() {
  clearRefreshLoop();
  state.refreshTimer = setInterval(async () => {
    await loadAll();
    renderActiveTab();
  }, REFRESH_MS);
}
function clearRefreshLoop() {
  if (state.refreshTimer) { clearInterval(state.refreshTimer); state.refreshTimer = null; }
}

// ── Live Check ────────────────────────────────────────────────────────────────
function startLiveCheck() {
  setInterval(checkLive, LIVE_CHECK_MS);
}
function checkLive() {
  if (!state.resultados) return;
  const live = state.resultados.marcadores?.some(m => m.estado === 'en_juego');
  $('live-badge').classList.toggle('show', !!live);
}

// ── Refresh Bar ────────────────────────────────────────────────────────────────
function updateRefreshBar() {
  if (!state.lastUpdate) return;
  const d = state.lastUpdate;
  $('refresh-time').textContent = d.toLocaleTimeString('es-ES', { hour:'2-digit', minute:'2-digit' });
  $('refresh-label').textContent = 'Actualizado';
  $('refresh-dot').classList.remove('stale');
}

// ── Tab Navigation ────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    $(`view-${tab}`)?.classList.add('active');
    state.activeTab = tab;
    renderActiveTab();
  });
});

function renderActiveTab() {
  switch (state.activeTab) {
    case 'clasificacion': renderClasificacion(); break;
    case 'mi-porra':      renderMiPorra();       break;
    case 'evolucion':     renderEvolucion();     break;
    case 'proximos':      renderProximos();      break;
    // 'reglas' is static HTML
  }
}

// ── CLASIFICACIÓN ─────────────────────────────────────────────────────────────
const MEDALS = { 1:'🥇', 2:'🥈', 3:'🥉' };

function posArrow(nick, prev) {
  if (!prev) return '<span class="pos-arrow same">—</span>';
  const prevPos = prev.find(p => p.nickname === nick)?.posicion;
  if (prevPos == null) return '<span class="pos-arrow same">—</span>';
  const curr = state.standings?.clasificacion?.find(p => p.nickname === nick)?.posicion;
  if (curr < prevPos) return '<span class="pos-arrow up">▲</span>';
  if (curr > prevPos) return '<span class="pos-arrow down">▼</span>';
  return '<span class="pos-arrow same">—</span>';
}

function renderClasificacion() {
  const container = $('standings-container');
  if (!state.standings) {
    container.innerHTML = '<div class="empty-state"><div class="icon">📊</div>Cargando clasificación…</div>';
    return;
  }
  const clas = state.standings.clasificacion || [];
  const prev = state.prevStandings?.clasificacion;

  const heroEl = el('div', 'standings-hero');
  heroEl.innerHTML = `
    <div class="standings-header">
      <div class="sh-pos">#</div>
      <div class="sh-nick">Jugador</div>
      <div class="sh-pts">Total</div>
      <div class="sh-grp">Grp</div>
      <div class="sh-elim">Elim</div>
    </div>
  `;

  clas.forEach(p => {
    const row = el('div', `standings-row${p.posicion === 1 ? ' top-row' : ''}`);
    const medal = MEDALS[p.posicion] || '';
    const arrow = posArrow(p.nickname, prev);
    row.innerHTML = `
      <div class="col-pos">
        <span class="pos-num">${medal || p.posicion}</span>
        ${arrow}
      </div>
      <div class="col-nick">
        ${escHtml(p.nickname)}
        ${p.empate ? '<span class="nick-empate">=</span>' : ''}
      </div>
      <div class="col-pts">${fmtPts(p.puntos_total)}</div>
      <div class="col-grp">${fmtPts(p.puntos_grupos)}</div>
      <div class="col-elim">${fmtPts(p.puntos_fase_eliminatoria)}</div>
    `;
    heroEl.appendChild(row);
  });
  container.innerHTML = '';
  container.appendChild(heroEl);
}

// ── MI PORRA ──────────────────────────────────────────────────────────────────
function renderMiPorra() {
  if (!state.standings) return;
  const clas = state.standings.clasificacion || [];

  // Chips
  const chipsEl = $('nick-chips');
  chipsEl.innerHTML = '';
  clas.forEach(p => {
    const chip = el('button', `nick-chip${state.selectedNick === p.nickname ? ' active' : ''}`);
    chip.textContent = p.nickname;
    chip.addEventListener('click', () => selectNick(p.nickname));
    chipsEl.appendChild(chip);
  });

  if (state.selectedNick) renderNickDetail(state.selectedNick);
}

$('nick-search').addEventListener('input', function() {
  const q = this.value.toLowerCase();
  document.querySelectorAll('.nick-chip').forEach(c => {
    c.style.display = c.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
});

function selectNick(nick) {
  state.selectedNick = nick;
  state.showAllPending = false;
  document.querySelectorAll('.nick-chip').forEach(c => c.classList.toggle('active', c.textContent === nick));
  renderNickDetail(nick);
}

function renderNickDetail(nick) {
  const detailEl = $('mi-porra-detail');
  const detalleP = state.detalle?.[nick];

  if (!state.standings?.clasificacion?.find(p => p.nickname === nick)) {
    detailEl.className = 'mi-porra-detail show';
    detailEl.innerHTML = '<div class="empty-state"><div class="icon">🔍</div>Nickname no encontrado</div>';
    return;
  }

  if (!detalleP) {
    detailEl.className = 'mi-porra-detail show';
    detailEl.innerHTML = '<div class="empty-state"><div class="icon">📋</div>Sin datos de pronóstico</div>';
    return;
  }

  let html = '';

  // Grupos — todos en lista neutra, sin coloreado ni puntos
  const todosGrupos = detalleP.grupos || [];
  if (todosGrupos.length) {
    const showAll = state.showAllPending;
    const visible = showAll ? todosGrupos : todosGrupos.slice(0, 8);
    html += `<div class="section-title mt16">Partidos de grupos</div><div class="match-table">`;
    visible.forEach(g => {
      const pStr = g.prediccion ? `${g.prediccion.goles_local}-${g.prediccion.goles_visitante} (${g.prediccion.signo})` : '—';
      html += `<div class="match-row pending">
        <div class="match-row-idx">${g.match_id}</div>
        <div class="match-row-teams">
          <div class="match-teams-main">${escHtml(g.local)} - ${escHtml(g.visitante)}</div>
          <div class="match-subtext">Pred: ${pStr}</div>
        </div>
      </div>`;
    });
    if (todosGrupos.length > 8) {
      const more = todosGrupos.length - 8;
      html += `<div class="match-row pending-toggle-row" id="pending-toggle">
        <div class="match-row-idx">${showAll ? '▲' : '▼'}</div>
        <div class="match-row-teams">${showAll ? 'Mostrar menos' : `Ver ${more} pronósticos más`}</div>
        <div></div><div></div>
      </div>`;
    }
    html += '</div>';
  }

  // Eliminatorias — equipos sin hit/miss ni puntos
  if (detalleP.clasificados) {
    html += `<div class="section-title mt16">Eliminatorias</div>`;
    ['1/16','1/8','1/4','semis','final'].forEach(r => {
      const pred = detalleP.clasificados[r] || [];
      const teamsHtml = pred.map(t => `<span class="elim-team">${escHtml(t)}</span>`).join('');
      html += `<div class="elim-round">
        <span class="elim-round-label">${r}</span>
        <div class="elim-teams">${teamsHtml || '<span style="color:var(--text3);font-size:.75rem">—</span>'}</div>
      </div>`;
    });
  }

  // Posiciones de honor — solo predicción
  if (detalleP.honor) {
    html += `<div class="section-title mt16">Posiciones de honor</div><div class="match-table">`;
    [
      {k:'campeon',    label:'Campeón'},
      {k:'subcampeon', label:'Subcampeón'},
      {k:'tercero',    label:'3.º'},
      {k:'cuarto',     label:'4.º'},
    ].forEach(({k, label}) => {
      html += `<div class="match-row pending">
        <div class="match-row-idx">${label}</div>
        <div class="match-row-teams">
          <div class="match-teams-main">${escHtml(detalleP.honor[k] || '—')}</div>
        </div>
      </div>`;
    });
    html += '</div>';
  }

  // Premios individuales — solo predicción
  if (detalleP.premios) {
    html += `<div class="section-title mt16">Premios individuales</div><div class="match-table">`;
    [
      {k:'goleador', label:'Goleador'},
      {k:'mvp',      label:'MVP'},
      {k:'portero',  label:'Portero'},
    ].forEach(({k, label}) => {
      html += `<div class="match-row pending">
        <div class="match-row-idx">${label}</div>
        <div class="match-row-teams">
          <div class="match-teams-main">${escHtml(detalleP.premios[k] || '—')}</div>
        </div>
      </div>`;
    });
    html += '</div>';
  }

  detailEl.className = 'mi-porra-detail show';
  detailEl.innerHTML = html;

  const toggleRow = detailEl.querySelector('#pending-toggle');
  if (toggleRow) {
    toggleRow.addEventListener('click', () => {
      state.showAllPending = !state.showAllPending;
      renderNickDetail(state.selectedNick);
    });
  }
}

// ── EVOLUCIÓN ─────────────────────────────────────────────────────────────────
function renderEvolucion() {
  if (!state.snapshots) return;
  const snaps = state.snapshots.snapshots || [];
  const nicknames = state.snapshots.nicknames || [];
  if (!snaps.length) return;

  const svgPos  = $('pos-chart');
  const svgPts  = $('pts-chart');
  const legend  = $('pos-legend');

  const W = 440, PH = 240, PTH = 200;
  const PAD = { top: 20, right: 20, bottom: 30, left: 30 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = PH - PAD.top - PAD.bottom;
  const ptsH   = PTH - PAD.top - PAD.bottom;

  const dates = snaps.map(s => s.fecha);
  const nCols = dates.length - 1;
  const maxPos = nicknames.length;

  function xPos(i) { return PAD.left + (i / Math.max(nCols,1)) * chartW; }
  function yPos(pos) { return PAD.top + ((pos - 1) / Math.max(maxPos - 1, 1)) * chartH; }

  // Build points series
  const nickMaxPts = {};
  nicknames.forEach(nick => {
    snaps.forEach(s => {
      const p = s.clasificacion.find(c => c.nickname === nick);
      if (p) nickMaxPts[nick] = Math.max(nickMaxPts[nick] || 0, p.puntos_total || 0);
    });
  });
  const allMaxPts = Math.max(...Object.values(nickMaxPts), 1);
  function yPts(pts) { return PAD.top + ptsH - (pts / allMaxPts) * ptsH; }

  // Position chart
  let posHtml = `<defs>
    ${nicknames.map((_, i) => `<filter id="glow${i}"><feGaussianBlur stdDeviation="2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`).join('')}
  </defs>`;

  // Grid lines (one per position)
  for (let pos = 1; pos <= maxPos; pos++) {
    const y = yPos(pos);
    posHtml += `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left + chartW}" y2="${y}" stroke="rgba(255,255,255,.04)" stroke-width="1"/>
    <text x="${PAD.left - 4}" y="${y + 4}" font-size="9" fill="rgba(255,255,255,.3)" text-anchor="end">${pos}</text>`;
  }

  // Date labels
  dates.forEach((d, i) => {
    const x = xPos(i);
    const label = new Date(d).toLocaleDateString('es-ES', { month:'numeric', day:'numeric' });
    posHtml += `<text x="${x}" y="${PH - 6}" font-size="8" fill="rgba(255,255,255,.35)" text-anchor="middle">${label}</text>`;
  });

  // Lines and dots per nickname
  nicknames.forEach((nick, ni) => {
    const color = nickColor(ni);
    const points = snaps.map((s, i) => {
      const p = s.clasificacion.find(c => c.nickname === nick);
      return p ? { x: xPos(i), y: yPos(p.posicion) } : null;
    }).filter(Boolean);

    if (points.length < 2) return;

    // Line
    const d = points.map((p, i) => `${i===0?'M':'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    posHtml += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" opacity=".85"/>`;

    // Dots
    points.forEach((p, i) => {
      posHtml += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="${color}" stroke="var(--bg2)" stroke-width="2"/>`;
    });

    // Last point label
    const last = points[points.length - 1];
    const lastSnap = snaps[snaps.length - 1].clasificacion.find(c => c.nickname === nick);
    if (lastSnap) {
      posHtml += `<text x="${(last.x + 5).toFixed(1)}" y="${(last.y + 4).toFixed(1)}" font-size="9" fill="${color}" font-weight="600">${escHtml(nick.substring(0,8))}</text>`;
    }
  });

  svgPos.innerHTML = posHtml;

  // Points chart
  let ptsHtml = '';

  // Grid
  [0, 0.25, 0.5, 0.75, 1].forEach(frac => {
    const y = PAD.top + ptsH * (1 - frac);
    const val = Math.round(allMaxPts * frac);
    ptsHtml += `<line x1="${PAD.left}" y1="${y.toFixed(1)}" x2="${PAD.left + chartW}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,.04)" stroke-width="1"/>
    <text x="${PAD.left - 4}" y="${(y + 3).toFixed(1)}" font-size="8" fill="rgba(255,255,255,.3)" text-anchor="end">${val}</text>`;
  });

  nicknames.forEach((nick, ni) => {
    const color = nickColor(ni);
    const points = snaps.map((s, i) => {
      const p = s.clasificacion.find(c => c.nickname === nick);
      return p ? { x: xPos(i), y: yPts(p.puntos_total || 0) } : null;
    }).filter(Boolean);

    if (points.length < 2) return;
    const d = points.map((p, i) => `${i===0?'M':'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    ptsHtml += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" opacity=".8"/>`;
    points.forEach(p => {
      ptsHtml += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="${color}" stroke="var(--bg2)" stroke-width="1.5"/>`;
    });
  });

  svgPts.innerHTML = ptsHtml;

  // Legend
  legend.innerHTML = nicknames.map((nick, ni) => `
    <div class="legend-item">
      <div class="legend-dot" style="background:${nickColor(ni)}"></div>
      <span>${escHtml(nick)}</span>
    </div>
  `).join('');
}

// ── PRÓXIMOS ──────────────────────────────────────────────────────────────────
function renderProximos() {
  const container = $('proximos-container');
  if (!state.proximos?.length) {
    container.innerHTML = '<div class="empty-state"><div class="icon">📅</div>No hay próximos partidos cargados</div>';
    return;
  }

  container.innerHTML = '';
  state.proximos.forEach(m => {
    const card = el('div', 'match-card');
    const liveEntry = state.resultados?.marcadores?.find(e => e.match_id === m.match_id);
    const isLive = liveEntry?.estado === 'en_juego';
    const isDone = liveEntry?.estado === 'finalizado';
    const jLabel = m.jornada ? `${m.grupo ? 'Grupo '+m.grupo+' · ' : ''}${m.jornada}` : (m.fase || '');

    let scoreHtml = '';
    if (isLive || isDone) {
      scoreHtml = `<span class="match-live-score">${liveEntry.goles_local ?? '?'} – ${liveEntry.goles_visitante ?? '?'}</span>`;
    } else {
      scoreHtml = `<span class="match-vs">vs</span>`;
    }

    card.innerHTML = `
      <div class="match-card-head">
        <span class="match-meta">${escHtml(jLabel)}</span>
        <span class="match-date-str">${fmtDate(m.fecha_hora_utc)}</span>
      </div>
      <div class="match-teams-row">
        <div class="match-team home">${escHtml(m.local)}</div>
        ${scoreHtml}
        <div class="match-team away">${escHtml(m.visitante)}</div>
      </div>
    `;

    // Predicciones grid
    if (m.predicciones?.length) {
      const grid = el('div', 'preds-grid');
      m.predicciones.forEach(pr => {
        const cell = el('div', 'pred-cell');
        const p = pr.prediccion;
        const valStr = p ? `${p.goles_local}-${p.goles_visitante}` : '—';
        cell.innerHTML = `
          <div class="pred-cell-nick">${escHtml(pr.nickname)}</div>
          <div class="pred-cell-val">${valStr}</div>
        `;
        grid.appendChild(cell);
      });
      card.appendChild(grid);
    }

    container.appendChild(card);
  });
}

// ── XSS safety ────────────────────────────────────────────────────────────────
function escHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}

// ── Puerta de cuenta atrás (bloquea el acceso antes del Mundial) ──────────────
let _gateInterval = null;

function _updateGateTimer() {
  const diff = WC_START - Date.now();
  if (diff <= 0) {
    clearInterval(_gateInterval);
    _liftGate();
    return;
  }
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  const m = Math.floor((diff % 3600000)  / 60000);
  const s = Math.floor((diff % 60000)    / 1000);
  $('gate-days').textContent  = String(d).padStart(2, '0');
  $('gate-hours').textContent = String(h).padStart(2, '0');
  $('gate-mins').textContent  = String(m).padStart(2, '0');
  $('gate-secs').textContent  = String(s).padStart(2, '0');
}

function _liftGate() {
  const gate = $('countdown-gate');
  gate.classList.remove('active');
  gate.style.display = 'none';
  _restoreOrShowPassword();
}

function _restoreOrShowPassword() {
  const saved = sessionStorage.getItem(SESSION_KEY);
  if (saved && PASSWORDS[saved]) {
    enterApp(saved);
  }
  // else: password screen stays visible (already shown by default)
}

(function initGate() {
  const params = new URLSearchParams(location.search);
  const bypass = params.get('preview') === PREVIEW_TOKEN;
  const before = WC_START - Date.now() > 0;

  if (!bypass && before) {
    $('countdown-gate').classList.add('active');
    _updateGateTimer();
    _gateInterval = setInterval(_updateGateTimer, 1000);
  } else {
    _restoreOrShowPassword();
  }
})();
