'use strict';

// ── состояние ───────────────────────────────────────────────────────────
let META = null;         // /api/meta
let FILE_ID = null;
let SUMMARY = null;      // ответ /api/analyze
let PARAMS = {};         // текущие значения ползунков (display-единицы)
let analyzeTimer = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function fmtNum(v) {
  if (v === null || v === undefined || v === '') return '';
  if (typeof v === 'number') {
    const s = Number.isInteger(v) ? String(v) : v.toFixed(2);
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  }
  return String(v);
}
function fmtInt(v) { return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }

function mdLite(t) {
  return esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
}
function showError(msg) { const e = $('error'); e.textContent = msg; e.hidden = false; }
function clearError() { $('error').hidden = true; }

const PL = {
  paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(20,34,72,0.18)',
  font: { family: 'system-ui, sans-serif', color: '#9fb2d8', size: 11 },
  xaxis: { gridcolor: 'rgba(90,162,255,0.12)', linecolor: 'rgba(90,162,255,0.28)', zerolinecolor: 'rgba(90,162,255,0.2)' },
  yaxis: { gridcolor: 'rgba(90,162,255,0.12)', linecolor: 'rgba(90,162,255,0.28)', zerolinecolor: 'rgba(90,162,255,0.2)' },
  margin: { l: 44, r: 12, t: 10, b: 40 }, showlegend: false,
};
const PLCFG = { displayModeBar: false, responsive: true };
const hasPlotly = () => typeof window.Plotly !== 'undefined';

// ── инициализация ───────────────────────────────────────────────────────
async function init() {
  try {
    META = await (await fetch('/api/meta')).json();
  } catch (e) { showError('Не удалось загрузить конфигурацию: ' + e); return; }
  buildLegend();
  buildParamGroups();
  wireUpload();
  wireTabs();
  $('replace-btn').onclick = () => $('file-input').click();
  $('dl-report').onclick = () => { if (FILE_ID) window.location = `/api/report/${FILE_ID}`; };
  $('dl-selection').onclick = exportSelection;
}

function buildLegend() {
  $('legend').innerHTML = (META.flag_legend || []).map(f =>
    `<div class="flag-row" style="--flag-color:${f.color};">
       <span class="icon">${f.icon}</span>
       <span class="name"><b>${esc(f.title)}</b> — ${esc(f.desc)}</span>
     </div>`).join('');
}

// ── параметры (ползунки) ────────────────────────────────────────────────
function buildParamGroups() {
  const wrap = $('param-groups');
  wrap.innerHTML = '';
  (META.param_groups || []).forEach((g, gi) => {
    const det = document.createElement('details');
    det.className = 'grp';
    if (gi === 0) det.open = true;
    const help = (META.algo_info || {})[g.rule] || '';
    let inner = `<summary>${esc(g.title)}</summary><div class="grp-body">`;
    if (help) inner += `<button class="info-btn" data-help="${gi}">ⓘ как это работает</button>
                        <div class="popover" id="pop-${gi}" hidden>${mdLite(help)}</div>`;
    g.params.forEach(p => {
      PARAMS[p.key] = p.default;
      if (p.type === 'select') {
        inner += `<div class="ctrl"><div class="row"><label>${esc(p.label)}</label></div>
          <select data-key="${p.key}">` +
          p.options.map(o => `<option value="${o}" ${o === p.default ? 'selected' : ''}>${o}</option>`).join('') +
          `</select></div>`;
      } else {
        inner += `<div class="ctrl"><div class="row"><label>${esc(p.label)}</label>
          <span class="val" id="val-${p.key}">${p.default}</span></div>
          <input type="range" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}" value="${p.default}"></div>`;
      }
    });
    inner += `</div>`;
    det.innerHTML = inner;
    wrap.appendChild(det);
  });

  wrap.querySelectorAll('input[type=range]').forEach(inp => {
    inp.addEventListener('input', () => {
      const k = inp.dataset.key;
      PARAMS[k] = parseFloat(inp.value);
      const lbl = $('val-' + k); if (lbl) lbl.textContent = inp.value;
      if (SUMMARY) renderParamsGrid();
      scheduleAnalyze();
    });
  });
  wrap.querySelectorAll('select[data-key]').forEach(sel => {
    sel.addEventListener('change', () => { PARAMS[sel.dataset.key] = parseFloat(sel.value); scheduleAnalyze(); });
  });
  wrap.querySelectorAll('.info-btn').forEach(b => {
    b.addEventListener('click', () => { const p = $('pop-' + b.dataset.help); p.hidden = !p.hidden; });
  });
}

function scheduleAnalyze() {
  if (!FILE_ID) return;
  clearTimeout(analyzeTimer);
  analyzeTimer = setTimeout(runAnalyze, 350);
}

// ── загрузка файла (чанками) ────────────────────────────────────────────
function wireUpload() {
  const dz = $('dropzone'), inp = $('file-input');
  dz.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => { if (inp.files[0]) uploadFile(inp.files[0]); });
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', e => { const f = e.dataTransfer.files[0]; if (f) uploadFile(f); });
}

async function uploadFile(file) {
  clearError();
  const CHUNK = 512 * 1024;                     // мелкие куски → прокси не режет
  const total = Math.max(1, Math.ceil(file.size / CHUNK));
  const uploadId = (crypto.randomUUID ? crypto.randomUUID() : 'u' + Date.now() + Math.random());
  const prog = $('progress'); prog.hidden = false; prog.firstElementChild.style.width = '0%';
  try {
    let done = null;
    for (let i = 0; i < total; i++) {
      const fd = new FormData();
      fd.append('uploadId', uploadId);
      fd.append('index', i);
      fd.append('total', total);
      fd.append('chunk', file.slice(i * CHUNK, (i + 1) * CHUNK), 'chunk');
      const r = await fetch('/api/upload/chunk', { method: 'POST', body: fd });
      if (!r.ok) { throw new Error((await r.json().catch(() => ({}))).detail || ('HTTP ' + r.status)); }
      const j = await r.json();
      prog.firstElementChild.style.width = Math.round((i + 1) / total * 100) + '%';
      if (j.complete) done = j;
    }
    if (!done) throw new Error('загрузка не завершилась');
    FILE_ID = done.file_id;
    $('fname').textContent = file.name;
    $('fmeta').textContent = `${done.rows.toLocaleString('ru-RU')} строк · ${(file.size / 1048576).toFixed(1)} МБ`;
    // Показываем дашборд с настройками СРАЗУ — даже если анализ споткнётся,
    // ползунки видны и анализ можно повторить, подвигав порог.
    $('upload-section').hidden = true;
    $('dashboard').hidden = false;
    await runAnalyze(true);
  } catch (e) {
    showError('Ошибка загрузки: ' + e.message);
  } finally {
    prog.hidden = true;
  }
}

// ── анализ ──────────────────────────────────────────────────────────────
async function runAnalyze(first) {
  if (!FILE_ID) return;
  clearError();
  try {
    const r = await fetch('/api/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: FILE_ID, params: PARAMS }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ('HTTP ' + r.status));
    SUMMARY = await r.json();
  } catch (e) { showError('Ошибка анализа: ' + e.message); return; }

  if (first) {
    buildSeasonFilter();
    buildFlagFilter();
    buildSubscriberSelect();
  }
  renderParamsGrid();
  renderPills();
  renderMetrics(first);
  renderReportLine();
  renderSummaryCharts();
  renderRegistry();
  if (SUMMARY && document.querySelector('.tab.active').dataset.tab === 'subscriber') onSubscriberChange();
}

// SVG-иконки для сетки параметров (как в канвасе).
const PICON = {
  period: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1l2.1-2.1M17 7l2.1-2.1"/><circle cx="12" cy="12" r="4"/></svg>',
  drop: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  clock: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 13.5"/></svg>',
  power: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  bars: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>',
  ml: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/></svg>',
};

function renderParamsGrid() {
  const months = SUMMARY ? SUMMARY.metrics.months_detected + ' мес' : '—';
  const drop = ((PARAMS.theft_drop_pct || 0) / 100).toFixed(2);
  const cells = [
    ['#7fb4ff', PICON.period, 'Период анализа', months, '#eaf1ff'],
    ['#ff8ea0', PICON.drop, 'Порог падения', drop, '#ffb3bf'],
    ['#7fb4ff', PICON.clock, 'Окно молчания', (PARAMS.silence_months || 0) + ' мес', '#eaf1ff'],
    ['#ffca8f', PICON.power, 'Лимит мощности', '×' + (+PARAMS.power_overrun_ratio || 0).toFixed(1), '#ffd9ad'],
    ['#7fb4ff', PICON.bars, 'Порог риск-балла', '5', '#eaf1ff'],
    ['#8ff0cf', PICON.ml, 'Чувствит. ML', (PARAMS.iso_contamination || 0) + '%', '#b6f5df'],
  ];
  $('params-grid').innerHTML = cells.map(([c, ic, lab, val, vc]) =>
    `<div class="param-cell"><span class="icon" style="color:${c};filter:drop-shadow(0 0 5px ${c});">${ic}</span>
     <span class="param-label">${esc(lab)}</span><span class="param-value" style="color:${vc};">${esc(val)}</span></div>`).join('');
}

function renderPills() {
  const found = Object.values((SUMMARY.report.columns_found) || {});
  $('pills').innerHTML = found.length
    ? '<span class="section-label" style="margin:.2rem 0;">Распознано в выгрузке</span><div>' +
      found.map(v => `<span class="pill found">${esc(v)}</span>`).join('') + '</div>'
    : '';
}

function renderMetrics(animate) {
  const m = SUMMARY.metrics;
  const cards = [
    ['Абонентов в файле', m.total_rows, ''],
    ['Месяцев данных', m.months_detected, ''],
    ['С флагами', m.n_with_flags, 'orange'],
    ['Высокий риск (балл ≥ 5)', m.n_high_risk, 'red'],
  ];
  $('metrics').innerHTML = cards.map(([label, val, opt]) => {
    const acc = opt === 'red' ? 'style="--cell-accent:var(--red);"'
              : opt === 'orange' ? 'style="--cell-accent:var(--orange);"' : '';
    const vcls = opt === 'red' ? ' red' : '';
    return `<div class="metric-cell" ${acc}><div class="metric-label">${esc(label)}</div>
      <div class="metric-value${vcls}" data-t="${val}">${animate ? '0' : fmtInt(val)}</div></div>`;
  }).join('');
  $('metrics').querySelectorAll('.metric-cell').forEach(c => c.style.flex = '1 1 180px');
  if (animate) countUp();
}

function countUp() {
  const els = [...$('metrics').querySelectorAll('.metric-value')];
  const t0 = performance.now(), dur = 1100;
  (function tick(now) {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    els.forEach(el => { el.textContent = fmtInt(Math.round((+el.dataset.t) * e)); });
    if (p < 1) requestAnimationFrame(tick);
  })(performance.now());
}

function renderReportLine() {
  const rep = SUMMARY.report;
  const skipped = (rep.flags_skipped || []).map(f => f.name).join(', ');
  let s = `Период: ${esc(rep.period_range || '—')}`;
  if (skipped) s += ` · пропущены флаги: ${esc(skipped)}`;
  $('report-line').innerHTML = s;
}

// ── графики сводки ──────────────────────────────────────────────────────
function renderSummaryCharts() {
  if (!hasPlotly()) { ['chart-flagcount', 'chart-perflag', 'chart-seasons'].forEach(id => $(id).innerHTML = '<div class="spinner">Графики недоступны (не загрузился Plotly)</div>'); return; }
  const ch = SUMMARY.charts;
  const scale = { 0: '#6f83ac', 1: '#5aa2ff', 2: '#7fb4ff', 3: '#ffb066', 4: '#ff5a72' };
  const colors = ch.by_flag_count.labels.map(k => scale[Math.min(4, parseInt(k))] || '#ff5a72');
  Plotly.newPlot('chart-flagcount', [{
    type: 'bar', x: ch.by_flag_count.labels, y: ch.by_flag_count.values,
    text: ch.by_flag_count.values, textposition: 'outside',
    marker: { color: colors }, textfont: { color: '#dbe6f7' },
    hovertemplate: '<b>%{x} флагов</b><br>%{y} абонентов<extra></extra>',
  }], { ...PL, height: 320 }, PLCFG);

  const pf = ch.per_flag;
  Plotly.newPlot('chart-perflag', [{
    type: 'bar', orientation: 'h',
    y: pf.map(f => f.title), x: pf.map(f => f.count), text: pf.map(f => f.count),
    textposition: 'outside', marker: { color: pf.map(f => f.color) }, textfont: { color: '#dbe6f7' },
    hovertemplate: '<b>%{y}</b><br>%{x} абонентов<extra></extra>',
  }], { ...PL, height: 320, margin: { l: 150, r: 20, t: 10, b: 30 } }, PLCFG);

  const se = ch.seasons;
  Plotly.newPlot('chart-seasons', [{
    type: 'bar', x: se.map(s => s.name), y: se.map(s => s.count), text: se.map(s => s.count),
    textposition: 'outside', marker: { color: se.map(s => s.color) }, textfont: { color: '#dbe6f7' },
    hovertemplate: '<b>%{x}</b><br>%{y} абонентов<extra></extra>',
  }], { ...PL, height: 260 }, PLCFG);
}

// ── реестр ──────────────────────────────────────────────────────────────
function buildSeasonFilter() {
  const seasons = ['(все)', ...SUMMARY.charts.seasons.map(s => s.name)];
  $('f-season').innerHTML = seasons.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
  $('f-season').onchange = renderRegistry;
  $('f-minflags').oninput = renderRegistry;
}
function buildFlagFilter() {
  $('f-flags').innerHTML = SUMMARY.flag_cols.map(k =>
    `<label><input type="checkbox" value="${k}"> ${esc((META.flag_titles || {})[k] || k)}</label>`).join('');
  $('f-flags').querySelectorAll('input').forEach(i => i.addEventListener('change', renderRegistry));
}

function currentFilters() {
  return {
    file_id: FILE_ID,
    min_flags: parseInt($('f-minflags').value) || 0,
    season: $('f-season').value,
    flags: [...$('f-flags').querySelectorAll('input:checked')].map(i => i.value),
  };
}

// Таблица реестра тянется порциями с сервера (серверная фильтрация) — на клиент
// не грузим весь реестр, поэтому анализ большого файла не упирается в память/таймаут.
async function renderRegistry() {
  if (!FILE_ID) return;
  let d;
  try {
    d = await (await fetch('/api/registry', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...currentFilters(), limit: 2000 }),
    })).json();
  } catch (e) { return; }
  const cols = SUMMARY.columns.filter(c => c !== '_idx');
  const labels = SUMMARY.labels;
  const flagset = new Set(SUMMARY.flag_cols);
  const head = '<thead><tr>' + cols.map(c => `<th>${esc(labels[c] || c)}</th>`).join('') + '</tr></thead>';
  const body = '<tbody>' + d.rows.map(r => '<tr>' + cols.map(c => {
    let v = r[c];
    if (flagset.has(c)) v = v ? '✓' : '·';
    else if (typeof v === 'number') v = fmtNum(v);
    else if (v === null || v === undefined) v = '';
    return `<td>${esc(v)}</td>`;
  }).join('') + '</tr>').join('') + '</tbody>';
  $('reg-table').innerHTML = head + body;
  $('reg-count').innerHTML = `Показано <b>${d.total.toLocaleString('ru-RU')}</b> из ${d.registry_total.toLocaleString('ru-RU')} абонентов`
    + (d.shown < d.total ? ` · в таблице первые ${d.shown.toLocaleString('ru-RU')}, в Excel — вся выборка` : '');
}

async function exportSelection() {
  if (!FILE_ID) return;
  const r = await fetch('/api/registry/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(currentFilters()),
  });
  if (!r.ok) { showError('Ошибка выгрузки выборки'); return; }
  const blob = await r.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'выборка.xlsx'; a.click();
  URL.revokeObjectURL(a.href);
}

// ── абонент ─────────────────────────────────────────────────────────────
// Список абонентов для селектора — компактный, с сервера (топ по риску).
async function buildSubscriberSelect() {
  if (!FILE_ID) return;
  let d;
  try { d = await (await fetch(`/api/subscribers/${FILE_ID}`)).json(); }
  catch (e) { return; }
  $('sub-select').innerHTML = d.items.map(it => `<option value="${it.idx}">${esc(it.label)}</option>`).join('');
  $('sub-select').onchange = onSubscriberChange;
}

async function onSubscriberChange() {
  const idx = $('sub-select').value;
  if (idx === '' || idx === undefined) return;
  const body = $('sub-body');
  body.innerHTML = '<div class="spinner">Загрузка…</div>';
  let d;
  try { d = await (await fetch(`/api/subscriber/${FILE_ID}/${idx}`)).json(); }
  catch (e) { body.innerHTML = '<div class="err">Ошибка: ' + e + '</div>'; return; }

  const flagsHtml = d.flags.length
    ? d.flags.map(f => `<div class="flag-row" style="--flag-color:${f.color};"><span class="icon">${f.icon}</span><span class="name">${esc(f.title)}</span></div>`).join('')
    : `<div class="flag-empty"><span class="icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span> Без флагов</div>`;
  const kv = (arr) => `<div class="kv-list">` + arr.map(x => `<div class="kv-row"><span class="kv-key">${esc(x.label)}</span><span class="kv-val">${esc(x.value)}</span></div>`).join('') + `</div>`;

  body.innerHTML = `
    <div id="sub-chart" class="chart" style="min-height:360px;"></div>
    <div class="subgrid" style="margin-top:1rem;">
      <div>
        <div class="section-label">Активные флаги</div>${flagsHtml}
        <div class="section-label" style="margin-top:1.4rem;">Ключевые метрики</div>${kv(d.metrics)}
      </div>
      <div>
        <div class="section-label">Метаданные</div>${d.meta.length ? kv(d.meta) : '<div class="spinner">нет метаданных</div>'}
      </div>
    </div>
    <div style="margin-top:1.2rem;"><button class="btn ghost small" id="dl-card">Карточка абонента (Excel)</button></div>`;
  $('dl-card').onclick = () => window.location = `/api/subscriber/${FILE_ID}/${idx}/card`;

  if (hasPlotly()) {
    const xs = d.series.map(p => p.t + '-01'), ys = d.series.map(p => p.v);
    Plotly.newPlot('sub-chart', [{
      type: 'scatter', mode: 'lines+markers', x: xs, y: ys, connectgaps: false,
      line: { color: '#5aa2ff', width: 2 }, marker: { size: 5, color: '#5aa2ff' },
      fill: 'tozeroy', fillcolor: 'rgba(90,162,255,0.14)',
      hovertemplate: '%{x|%b %Y}<br>%{y:,.0f} кВт·ч<extra></extra>',
    }], { ...PL, height: 360, yaxis: { ...PL.yaxis, title: 'кВт·ч' } }, PLCFG);
  }
}

// ── вкладки ─────────────────────────────────────────────────────────────
function wireTabs() {
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const name = t.dataset.tab;
    ['summary', 'registry', 'subscriber'].forEach(n => $('tab-' + n).hidden = (n !== name));
    if (name === 'summary') renderSummaryCharts();
    if (name === 'subscriber' && $('sub-select').value) onSubscriberChange();
  }));
}

init();
