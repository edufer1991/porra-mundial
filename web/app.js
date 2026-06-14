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
  calendario: null,
  calIdx: {},          // match_id → partido (built on load)
  sectionOpen: {},     // section ID → bool (open/closed state)
  selectedNick: null,
  activeTab: 'clasificacion',
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
  const [standings, detalle, proximos, snapshots, resultados, calendario] = await Promise.all([
    fetchJSON(`${DATA_BASE}${p}/standings.json`),
    fetchJSON(`${DATA_BASE}${p}/detalle.json`),
    fetchJSON(`${DATA_BASE}${p}/proximos.json`),
    fetchJSON(`${DATA_BASE}${p}/snapshots.json`),
    fetchJSON(`${DATA_BASE}resultados.json`),
    fetchJSON(`${DATA_BASE}calendario.json`),
  ]);
  state.prevStandings = state.standings;
  state.standings  = standings;
  state.detalle    = detalle;
  state.proximos   = proximos;
  state.snapshots  = snapshots;
  state.resultados = resultados;
  state.calendario = calendario;
  state.calIdx     = Object.fromEntries((calendario?.partidos || []).map(p => [p.id, p]));
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
    row.addEventListener('click', () => {
      // Cambiar a Mi Porra y cargar el nick
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
      document.querySelector('[data-tab="mi-porra"]')?.classList.add('active');
      $('view-mi-porra')?.classList.add('active');
      state.activeTab = 'mi-porra';
      selectNick(p.nickname);
      renderMiPorra();
    });
    heroEl.appendChild(row);
  });
  container.innerHTML = '';
  container.appendChild(heroEl);
}

// ── Scoring helpers (v2 logic in JS) ─────────────────────────────────────────
function signoReal(gl, gv) { return gl > gv ? '1' : gl < gv ? '2' : 'X'; }

function normStr(s) {
  if (!s) return '';
  return String(s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().trim();
}

function v2Score(pred, gl, gv) {
  const pgl = pred?.gl ?? pred?.goles_local;
  const pgv = pred?.gv ?? pred?.goles_visitante;
  if (!pred || gl == null || gv == null) return { signo:false, diferencia:false, exacto:false, pts:0 };
  const s = pred.signo === signoReal(gl, gv);
  const d = s && (pgl - pgv) === (gl - gv);
  const e = d && pgl === gl && pgv === gv;
  return { signo:s, diferencia:d, exacto:e, pts: (s?5:0)+(d?2:0)+(e?8:0) };
}

function indsHtml(sc) {
  return `<span class="ind ${sc.signo?'ok':'no'}">G</span>`
       + `<span class="ind ${sc.diferencia?'ok':'no'}">D</span>`
       + `<span class="ind ${sc.exacto?'ok':'no'}">E</span>`;
}

function matchRowV2(idx, local, visitante, pred, resultado, honorCls='') {
  const pgl = pred?.gl ?? pred?.goles_local;
  const pgv = pred?.gv ?? pred?.goles_visitante;
  const predStr = pred ? `${pred.signo}|${pgl}-${pgv}` : '—';

  if (!resultado) {
    return `<div class="match-row pending ${honorCls}">
      <div class="match-row-idx">${idx}</div>
      <div class="match-row-teams">
        <div class="match-teams-main">${escHtml(local)} - ${escHtml(visitante)}</div>
        <div class="match-subtext">Pred: ${predStr}</div>
      </div>
    </div>`;
  }
  const { goles_local: gl, goles_visitante: gv } = resultado;
  const sc = v2Score(pred, gl, gv);
  const sr = signoReal(gl, gv);
  return `<div class="match-row ${sc.pts>0?'correct':'wrong'} ${honorCls}">
    <div class="match-row-idx">${idx}</div>
    <div class="match-row-teams">
      <div class="match-teams-main">${escHtml(local)} - ${escHtml(visitante)}</div>
      <div class="match-subtext">Pred: ${predStr} · Real: ${sr}|${gl}-${gv} ${indsHtml(sc)}</div>
    </div>
    <div></div>
    <div class="match-row-pts ${sc.pts>0?'pos':'zero'}">${sc.pts}</div>
  </div>`;
}

function findElimResult(local, visitante, marcadores) {
  const nl = normStr(local), nv = normStr(visitante);
  for (const m of (marcadores||[])) {
    if (m.estado !== 'finalizado' || !m.local) continue;
    const ml = normStr(m.local), mv = normStr(m.visitante);
    if (ml===nl && mv===nv) return { goles_local:m.goles_local, goles_visitante:m.goles_visitante };
    if (ml===nv && mv===nl) return { goles_local:m.goles_visitante, goles_visitante:m.goles_local };
  }
  return null;
}

// ── Mi Porra helpers ──────────────────────────────────────────────────────────
function fmtCEST(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('es-ES', {
    timeZone: 'Europe/Madrid', weekday: 'short',
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

const RONDAS_PTS  = { '1/16': 10, '1/8': 12, '1/4': 14, 'semis': 16, 'final': 20 };
const NEXT_ROUND  = { '1/16': '1/8', '1/8': '1/4', '1/4': 'semis', 'semis': 'final' };
const ROUND_LABEL = { '1/16': 'Dieciseisavos', '1/8': 'Octavos', '1/4': 'Cuartos',
                      'semis': 'Semifinales', '3-4': '3.er y 4.º puesto', 'final': 'Final' };
const RONDA_ORDER = { '1/16': 0, '1/8': 1, '1/4': 2, 'semis': 3, '3-4': 4, 'final': 5 };

function elimClassifBadges(local, visitante, ronda, predClasifs, realClasifs) {
  const nextRound = NEXT_ROUND[ronda];
  if (!nextRound) return [];
  const predSet = new Set((predClasifs?.[nextRound] || []).map(normStr));
  const realSet = new Set((realClasifs?.[nextRound] || []).map(normStr));
  const hasReal = realSet.size > 0;
  const pts     = RONDAS_PTS[nextRound] || 0;
  const label   = ROUND_LABEL[nextRound] || nextRound;
  return [local, visitante].filter(t => t && predSet.has(normStr(t))).map(team => ({
    team, pts, label,
    hit: hasReal ? realSet.has(normStr(team)) : null,
  }));
}

function mcpCard(fase, fechaStr, local, visitante, pred, resultado, classifBadges) {
  const pgl = pred?.gl ?? pred?.goles_local;
  const pgv = pred?.gv ?? pred?.goles_visitante;
  const predStr = pred ? `${pred.signo}|${pgl}-${pgv}` : '—';

  let scoreHtml, indHtml = '', cardMod = '';

  if (resultado) {
    const { goles_local: gl, goles_visitante: gv } = resultado;
    const sc = v2Score(pred, gl, gv);
    cardMod = sc.pts > 0 ? ' mcp-ok' : ' mcp-ko';
    const scoreCls = sc.exacto ? 'exact' : sc.signo ? 'partial' : 'miss';
    scoreHtml = `
      <div class="mcp-score-row">
        <span class="mcp-home-name">${escHtml(local)}</span>
        <span class="mcp-score-big ${scoreCls}">${gl} – ${gv}</span>
        <span class="mcp-away-name">${escHtml(visitante)}</span>
      </div>
      <div class="mcp-pred-row">Pronóstico: <strong>${escHtml(predStr)}</strong></div>`;
    indHtml = `
      <div class="mcp-indicators">
        <span class="mcp-ind ${sc.signo?'ok':'no'}">${sc.signo?'✓':'✗'} Ganador${sc.signo?' +5':''}</span>
        <span class="mcp-ind ${sc.diferencia?'ok':'no'}">${sc.diferencia?'✓':'✗'} Diferencia${sc.diferencia?' +2':''}</span>
        <span class="mcp-ind ${sc.exacto?'ok':'no'}">${sc.exacto?'✓':'✗'} Exacto${sc.exacto?' +8':''}</span>
        <span class="mcp-total ${sc.pts>0?'pos':'zero'}">+${sc.pts} pts</span>
      </div>`;
  } else {
    scoreHtml = `
      <div class="mcp-score-row">
        <span class="mcp-home-name">${escHtml(local)}</span>
        <span class="mcp-score-big pending">Pendiente</span>
        <span class="mcp-away-name">${escHtml(visitante)}</span>
      </div>
      <div class="mcp-pred-row">Pronóstico: <strong>${escHtml(predStr)}</strong></div>`;
  }

  const badgesHtml = (classifBadges || []).map(b => {
    if (b.hit === null) return `<div class="mcp-badge neutral">⏳ ${escHtml(b.team)} clasif. a ${escHtml(b.label)} +${b.pts}pts</div>`;
    return b.hit
      ? `<div class="mcp-badge hit">✓ ${escHtml(b.team)} clasif. a ${escHtml(b.label)} +${b.pts}pts</div>`
      : `<div class="mcp-badge miss">✗ ${escHtml(b.team)} no clasif. a ${escHtml(b.label)}</div>`;
  }).join('');

  return `<div class="mcp-card${cardMod}">
    <div class="mcp-head">
      <span class="mcp-fase">${escHtml(fase)}</span>
      ${fechaStr ? `<span class="mcp-date">${escHtml(fechaStr)}</span>` : ''}
    </div>
    ${scoreHtml}
    ${indHtml}
    ${badgesHtml}
  </div>`;
}

function sectionPts(sectionId, standP) {
  const d = standP?.desglose;
  if (!d) return 0;
  if (sectionId === 'grupos') {
    return (d.grupos?.total || 0)
         + (d.posiciones_grupo?.total || 0)
         + (d.clasificado_1_16_desde_grupos?.total || 0);
  }
  return (d.elim_marcadores?.detalle || [])
    .filter(e => e.ronda === sectionId)
    .reduce((s, e) => s + (e.pts || 0), 0);
}

function defaultOpenSection(detalleP, marcadores) {
  // Latest elim round with a played match takes priority
  let latestElim = null;
  for (const p of (detalleP.elim_marcadores || [])) {
    const r = findElimResult(p.local, p.visitante, marcadores);
    if (r) {
      const ord = RONDA_ORDER[p.ronda] ?? 0;
      if (latestElim === null || ord > (RONDA_ORDER[latestElim] ?? 0)) latestElim = p.ronda;
    }
  }
  if (latestElim) return latestElim;
  if ((detalleP.grupos || []).some(g => g.resultado)) return 'grupos';
  return 'grupos';
}

function sectionBlock(id, title, matchCount, pts, cardsHtml) {
  const isOpen = state.sectionOpen[id] ?? false;
  const chevron = '▶';
  const metaPts = pts > 0 ? ` · <span class="sec-pts">+${pts} pts</span>` : '';
  return `<div class="sec-block${isOpen ? ' open' : ''}" data-sec="${id}">
    <button class="sec-header" type="button">
      <span class="sec-chevron">${chevron}</span>
      <span class="sec-title">${escHtml(title)}</span>
      <span class="sec-meta">${matchCount} partidos${metaPts}</span>
    </button>
    <div class="sec-body"><div class="sec-inner">${cardsHtml}</div></div>
  </div>`;
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
  state.sectionOpen = {};   // reset so defaultOpenSection runs again
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

  const marcadores  = state.resultados?.marcadores  || [];
  const realClasifs = state.resultados?.clasificados || {};
  const realHonor   = state.resultados?.honor        || {};
  const realPremios = state.resultados?.premios      || {};

  // Inicializar estados de sección (primera vez que se abre Mi Porra para este nick)
  if (Object.keys(state.sectionOpen).length === 0) {
    const defSec = defaultOpenSection(detalleP, marcadores);
    ['grupos','1/16','1/8','1/4','semis','3-4','final','honor','premios'].forEach(id => {
      state.sectionOpen[id] = (id === defSec);
    });
  }

  let html = '';

  // ── Resumen de puntos ──────────────────────────────────────────────────────
  const standP = state.standings?.clasificacion?.find(p => p.nickname === nick);
  if (standP) {
    const d = standP.desglose || {};
    const fN = n => (n == null ? '—' : n);
    html += `<div class="score-breakdown">
      <div class="score-card total">
        <div class="score-card-label">Total</div>
        <div class="score-card-pts">${fN(standP.puntos_total)}</div>
        <div class="score-card-sub">Pos. ${standP.posicion}${standP.empate?' (empate)':''}</div>
      </div>
      <div class="score-card"><div class="score-card-label">Marc. grupos</div><div class="score-card-pts">${fN(d.grupos?.total)}</div></div>
      <div class="score-card"><div class="score-card-label">Pos. grupo</div><div class="score-card-pts">${fN(d.posiciones_grupo?.total)}</div></div>
      <div class="score-card"><div class="score-card-label">Clas. 1/16</div><div class="score-card-pts">${fN(d.clasificado_1_16_desde_grupos?.total)}</div></div>
      <div class="score-card"><div class="score-card-label">Marc. elim.</div><div class="score-card-pts">${fN(d.elim_marcadores?.total)}</div></div>
      <div class="score-card"><div class="score-card-label">Clasificados</div><div class="score-card-pts">${fN(d.clasificados?.total)}</div></div>
      <div class="score-card"><div class="score-card-label">Honor</div><div class="score-card-pts">${fN(d.honor?.total)}</div></div>
      <div class="score-card"><div class="score-card-label">Premios</div><div class="score-card-pts">${fN(d.premios?.total)}</div></div>
    </div>`;
  }

  // ── Sección: Fase de grupos ────────────────────────────────────────────────
  {
    const grupos = (detalleP.grupos || []).slice().sort((a, b) => {
      const fa = state.calIdx[a.match_id]?.fecha_hora_utc || '';
      const fb = state.calIdx[b.match_id]?.fecha_hora_utc || '';
      return fa < fb ? -1 : fa > fb ? 1 : 0;
    });
    const cardsHtml = grupos.map(g => {
      const cal  = state.calIdx[g.match_id];
      const fase = cal ? `Grupo ${cal.grupo} · ${cal.jornada}` : '';
      const res  = g.resultado
        ? { goles_local: g.resultado.goles_local, goles_visitante: g.resultado.goles_visitante }
        : null;
      return mcpCard(fase, fmtCEST(cal?.fecha_hora_utc), g.local, g.visitante, g.prediccion, res, null);
    }).join('');
    html += sectionBlock('grupos', 'Fase de grupos', grupos.length, sectionPts('grupos', standP), cardsHtml);
  }

  // ── Secciones: Eliminatorias ───────────────────────────────────────────────
  const elimPreds = detalleP.elim_marcadores || [];
  const byRonda = {};
  elimPreds.forEach(p => { (byRonda[p.ronda] = byRonda[p.ronda] || []).push(p); });

  ['1/16','1/8','1/4','semis','3-4','final'].forEach(r => {
    const partidos = byRonda[r];
    if (!partidos?.length) return;
    const cardsHtml = partidos.map(p => {
      const res    = findElimResult(p.local, p.visitante, marcadores);
      const pred   = { signo: p.signo, goles_local: p.gl, goles_visitante: p.gv };
      const badges = r !== '3-4' && r !== 'final'
        ? elimClassifBadges(p.local, p.visitante, p.ronda, detalleP.clasificados, realClasifs)
        : [];
      return mcpCard(ROUND_LABEL[r], '', p.local, p.visitante, pred, res, badges);
    }).join('');
    html += sectionBlock(r, ROUND_LABEL[r], partidos.length, sectionPts(r, standP), cardsHtml);
  });

  // ── Sección: Honor y premios ───────────────────────────────────────────────
  {
    const honorRows = [{k:'campeon',label:'Campeón',pts:25},{k:'subcampeon',label:'Subcampeón',pts:20},
                       {k:'tercero',label:'3.º',pts:15},{k:'cuarto',label:'4.º',pts:10}];
    const honorHtml = honorRows.map(({k,label,pts}) => {
      const predVal = detalleP.honor?.[k];
      const realVal = realHonor[k];
      const played  = !!realVal;
      const hit     = played && normStr(predVal) === normStr(realVal);
      const rowCls  = !played ? 'pending' : (hit ? 'correct' : 'wrong');
      const subHtml = played
        ? `<div class="match-subtext">Real: ${escHtml(realVal)} <span class="ind ${hit?'ok':'no'}">${hit?'✓':'✗'}</span></div>` : '';
      const ptsHtml = played
        ? `<div></div><div class="match-row-pts ${hit?'pos':'zero'}">${hit?pts:0}</div>` : '';
      return `<div class="match-row match-row--honor ${rowCls}">
        <div class="match-row-idx">${label}</div>
        <div class="match-row-teams"><div class="match-teams-main">${escHtml(predVal||'—')}</div>${subHtml}</div>
        ${ptsHtml}
      </div>`;
    }).join('');
    const honorPts = standP?.desglose?.honor?.total || 0;
    html += sectionBlock('honor', 'Cuadro de honor', 4, honorPts,
      `<div class="match-table" style="margin-top:4px">${honorHtml}</div>`);
  }
  {
    const premiosRows = [{k:'goleador',label:'Goleador',pts:15},{k:'mvp',label:'MVP',pts:15},{k:'portero',label:'Portero',pts:15}];
    const premiosHtml = premiosRows.map(({k,label,pts}) => {
      const predVal = detalleP.premios?.[k];
      const realVal = realPremios[k];
      const played  = !!realVal;
      const hit     = played && normStr(predVal) === normStr(realVal);
      const rowCls  = !played ? 'pending' : (hit ? 'correct' : 'wrong');
      const subHtml = played
        ? `<div class="match-subtext">Real: ${escHtml(realVal)} <span class="ind ${hit?'ok':'no'}">${hit?'✓':'✗'}</span></div>` : '';
      const ptsHtml = played
        ? `<div></div><div class="match-row-pts ${hit?'pos':'zero'}">${hit?pts:0}</div>` : '';
      return `<div class="match-row match-row--honor ${rowCls}">
        <div class="match-row-idx">${label}</div>
        <div class="match-row-teams"><div class="match-teams-main">${escHtml(predVal||'—')}</div>${subHtml}</div>
        ${ptsHtml}
      </div>`;
    }).join('');
    const premiosPts = standP?.desglose?.premios?.total || 0;
    html += sectionBlock('premios', 'Premios individuales', 3, premiosPts,
      `<div class="match-table" style="margin-top:4px">${premiosHtml}</div>`);
  }

  detailEl.className = 'mi-porra-detail show';
  detailEl.innerHTML = html;

  // Eventos de toggle en las secciones
  detailEl.querySelectorAll('.sec-header').forEach(btn => {
    btn.addEventListener('click', () => {
      const secId = btn.closest('.sec-block').dataset.sec;
      state.sectionOpen[secId] = !state.sectionOpen[secId];
      renderNickDetail(nick);
    });
  });
}

// ── EVOLUCIÓN ─────────────────────────────────────────────────────────────────
function renderEvolucion() {
  const chartArea = $('view-evolucion');
  const chartCont = chartArea.querySelector('.chart-container');
  const ptsCont   = chartArea.querySelector('.pts-chart-container');

  // Reset state on every call: clear previous content and any empty-state message
  chartArea.querySelector('.evolucion-empty')?.remove();
  $('pos-chart').innerHTML  = '';
  $('pts-chart').innerHTML  = '';
  $('pos-legend').innerHTML = '';

  const snaps     = state.snapshots?.snapshots || [];
  const nicknames = state.snapshots?.nicknames || [];

  if (snaps.length < 2) {
    chartCont.style.display = 'none';
    ptsCont.style.display   = 'none';
    const div = document.createElement('div');
    div.className = 'empty-state evolucion-empty';
    div.innerHTML = '<div class="icon">📈</div>El gráfico de evolución estará disponible cuando haya más partidos jugados';
    chartArea.insertBefore(div, chartCont);
    return;
  }

  chartCont.style.display = '';
  ptsCont.style.display   = '';

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

// ── PRÓXIMOS + JUGADOS ────────────────────────────────────────────────────────
function renderProximos() {
  renderJugados();

  const container = $('proximos-container');
  if (!state.proximos?.length) {
    container.innerHTML = '<div class="empty-state"><div class="icon">📅</div>No hay próximos partidos cargados</div>';
  } else {
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
}

// Returns CSS class for the score value in a played-match cell.
// hit-exact · hit-diff · hit-sign · hit-wrong
function _predValClass(pr, resultado) {
  if (!pr.acierto_signo) return 'hit-wrong';
  if (pr.acierto_local && pr.acierto_visitante) return 'hit-exact';
  if (resultado) {
    const pd = (pr.prediccion?.goles_local ?? 0) - (pr.prediccion?.goles_visitante ?? 0);
    const rd = (resultado.goles_local ?? 0) - (resultado.goles_visitante ?? 0);
    if (pd === rd) return 'hit-diff';
  }
  return 'hit-sign';
}

// Returns inner HTML for the badges row (G / D / E), empty string when no badges.
function _predBadgesHtml(cls) {
  if (cls === 'hit-wrong') return '';
  let html = '<span class="pred-badge">G</span>';
  if (cls === 'hit-diff' || cls === 'hit-exact') html += '<span class="pred-badge">D</span>';
  if (cls === 'hit-exact') html += '<span class="pred-badge">E</span>';
  return html;
}

// Builds the list of played matches from detalle.json, sorted most-recent first.
function _buildJugadosIndex() {
  if (!state.detalle) return [];
  const matchMap = new Map();
  for (const [nick, participant] of Object.entries(state.detalle)) {
    for (const g of (participant.grupos || [])) {
      if (!g.resultado || g.acierto_signo === null || g.acierto_signo === undefined) continue;
      if (!matchMap.has(g.match_id)) {
        const cal = state.calIdx[g.match_id] || {};
        matchMap.set(g.match_id, {
          match_id:      g.match_id,
          local:         g.local,
          visitante:     g.visitante,
          grupo:         g.grupo,
          jornada:       g.jornada,
          fase:          cal.fase || 'grupos',
          fecha_hora_utc: cal.fecha_hora_utc || '',
          resultado:     g.resultado,
          predicciones:  [],
        });
      }
      matchMap.get(g.match_id).predicciones.push({
        nickname:        nick,
        prediccion:      g.prediccion,
        acierto_signo:   g.acierto_signo,
        acierto_local:   g.acierto_local,
        acierto_visitante: g.acierto_visitante,
      });
    }
  }
  return [...matchMap.values()].sort((a, b) =>
    (b.fecha_hora_utc || '').localeCompare(a.fecha_hora_utc || ''));
}

function renderJugados() {
  const wrap = $('jugados-wrap');
  // Preserve open/closed state across re-renders
  const wasOpen = wrap.querySelector('.sec-block')?.classList.contains('open') ?? false;
  const jugados = _buildJugadosIndex();

  // Reuse the same sec-block structure and CSS as Mi Porra sections
  const secBlock = el('div', `sec-block${wasOpen ? ' open' : ''}`);
  secBlock.innerHTML = `
    <button class="sec-header" type="button">
      <span class="sec-chevron">▶</span>
      <span class="sec-title">Partidos jugados</span>
      <span class="sec-meta">${jugados.length} partidos</span>
    </button>
    <div class="sec-body"><div class="sec-inner"></div></div>
  `;

  const secInner = secBlock.querySelector('.sec-inner');

  if (!jugados.length) {
    secInner.innerHTML = '<div class="empty-state"><div class="icon">🏁</div>Aún no hay partidos jugados</div>';
  } else {
    jugados.forEach(m => {
      const card  = el('div', 'match-card');
      const jLabel = m.grupo ? `Grupo ${m.grupo} · ${m.jornada}` : (m.jornada || m.fase || '');
      const r = m.resultado;

      card.innerHTML = `
        <div class="match-card-head">
          <span class="match-meta">${escHtml(jLabel)}</span>
          <span class="match-date-str">${fmtDate(m.fecha_hora_utc)}</span>
        </div>
        <div class="match-teams-row">
          <div class="match-team home">${escHtml(m.local)}</div>
          <span class="match-final-score">${r.goles_local ?? '?'} – ${r.goles_visitante ?? '?'}</span>
          <div class="match-team away">${escHtml(m.visitante)}</div>
        </div>
      `;

      if (m.predicciones?.length) {
        const sorted = [...m.predicciones].sort((a, b) => a.nickname.localeCompare(b.nickname));
        const grid = el('div', 'preds-grid');
        sorted.forEach(pr => {
          const cell = el('div', 'pred-cell');
          const p = pr.prediccion;
          const valStr = p ? `${p.goles_local}-${p.goles_visitante}` : '—';
          const valCls = _predValClass(pr, m.resultado);
          const badges = _predBadgesHtml(valCls);
          cell.innerHTML = `
            <div class="pred-cell-nick">${escHtml(pr.nickname)}</div>
            <div class="pred-cell-val ${valCls}">${valStr}</div>
            <div class="pred-badges">${badges}</div>
          `;
          grid.appendChild(cell);
        });
        card.appendChild(grid);
      }

      secInner.appendChild(card);
    });
  }

  secBlock.querySelector('.sec-header').addEventListener('click', () => {
    secBlock.classList.toggle('open');
  });

  wrap.innerHTML = '';
  wrap.appendChild(secBlock);
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
