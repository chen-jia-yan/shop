/* =====================================================================
 * app.js — 界面渲染 + 路由（只依赖 api.js，不直接碰数据源）
 * 对接后端时无需修改本文件。
 * ===================================================================== */

/* ---------- 小工具 ---------- */
const $ = id => document.getElementById(id);
const clsOf = v => v >= 0.8 ? 's-hi' : v >= 0.65 ? 's-mid' : 's-lo';
const rColor = v => v >= 78 ? 'var(--green)' : v >= 65 ? 'var(--amber)' : 'var(--red)';
const scoreTag = v => `<span class="sdot ${clsOf(v)}">${v.toFixed(2).slice(1)}</span>`;
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2400);
}

/* ---------- 全局状态 ---------- */
const state = {
  detail: null,        // 当前报告详情
  badList: [],         // 当前 bad case 列表（含筛选）
  badAll: [],          // 全部 bad case
  badGroup: 'type',    // 'type' | 'src'
  uploadFmt: 'csv',
  uploadRows: null,
  uploadCount: 0,
};
let gaugeChart, trendChart, radarChart;

/* ===================================================================== *
 *  评估报告列表
 * ===================================================================== */
async function loadReports() {
  const reports = await API.listReports();
  $('navReports').textContent = reports.length;
  $('rptCount').textContent = reports.length + ' 条';
  $('rptRows').innerHTML = reports.map(r => {
    const trend = r.prev > 0 ? `<span class="trend-up">▲ ${r.prev.toFixed(1)}</span>`
      : r.prev < 0 ? `<span class="trend-dn">▼ ${Math.abs(r.prev).toFixed(1)}</span>`
      : '<span style="color:var(--ink-faint)">基线</span>';
    const st = r.st === 'done' ? '<span class="st-done">● 已完成</span>' : '<span class="st-run">● 运行中</span>';
    return `<tr data-id="${r.v}" data-done="${r.st === 'done'}">
      <td class="rpt-row-name"><b><span class="ver">run ${r.v}</span></b><span>${r.name}</span></td>
      <td><span class="mtag">${r.ds}</span><div style="font-size:11px;color:var(--ink-faint);margin-top:3px">${r.n} 条</div></td>
      <td class="score-cell">${r.st === 'done' ? `<span class="big-score" style="color:${rColor(r.score)}">${r.score.toFixed(1)}</span>` : '<span style="color:var(--ink-faint)">—</span>'}</td>
      <td class="score-cell">${r.st === 'done' ? trend : '—'}</td>
      <td class="score-cell">${r.st === 'done' ? `<span class="sdot s-lo">${r.bad}</span>` : '—'}</td>
      <td style="font-size:12px;color:var(--ink-soft)">${r.model}</td>
      <td>${st}</td>
      <td style="font-size:12px;color:var(--ink-soft);font-family:var(--mono)">${r.time}</td>
    </tr>`;
  }).join('');
}
$('rptRows').addEventListener('click', e => {
  const tr = e.target.closest('tr'); if (!tr) return;
  if (tr.dataset.done === 'true') openReport(tr.dataset.id);
  else toast('该评估仍在运行中');
});

/* ===================================================================== *
 *  单个报告详情
 * ===================================================================== */
async function openReport(id) {
  const d = await API.getReport(id);
  state.detail = d;
  $('rptTitle').innerHTML = `${d.title} <span class="ver">run ${d.ver}</span>`;
  $('rptSub').innerHTML = `评估集 <b style="color:var(--ink)">${d.dataset}</b> · ${d.n} 条 · ${d.model} · ${d.time} 完成`;

  // 结论摘要
  $('summaryVerdict').innerHTML = d.summary.verdict;
  $('summaryFindings').innerHTML = d.summary.findings.map(x => `<li>${x}</li>`).join('');
  $('summaryRec').innerHTML = d.summary.recommendations.map(x => `<li>${x}</li>`).join('');

  // 评分盘 + 说明
  $('gVal').textContent = d.score.toFixed(1);
  const dir = d.baselineDelta >= 0 ? '▲' : '▼';
  $('gCaption').innerHTML = `较基线 run ${d.baselineRun} <b>${dir} ${Math.abs(d.baselineDelta).toFixed(1)} 分</b><br>${d.n} 条中 <b style="color:var(--red)">${d.badCount} 条</b> 为 bad case`;

  // 指标卡
  $('metricsRow').innerHTML = d.metrics.map(m => {
    const dd = m.up ? `<span class="m-delta up">▲ ${Math.abs(m.delta).toFixed(2)}</span>` : `<span class="m-delta down">▼ ${Math.abs(m.delta).toFixed(2)}</span>`;
    return `<div class="metric"><div class="m-label">${m.label}</div>
      <div class="m-val">${m.value.toFixed(2)}</div>
      <div class="m-bar"><i style="width:${Math.round(m.value * 100)}%;background:${m.color}"></i></div>
      ${dd}</div>`;
  }).join('');

  buildCharts(d);
  renderCases(d.cases);
  const badN = d.cases.filter(c => c.bad).length;
  $('tabAll').textContent = d.cases.length;
  $('tabBad').textContent = badN;
  $('caseCount').textContent = d.cases.length + ' 条';
  $('caseTitle').textContent = '评估明细（示例）';
  document.querySelectorAll('#view-report .tabs button').forEach((b, i) => b.classList.toggle('on', i === 0));
  document.querySelectorAll('#view-report .filters .chip').forEach((c, i) => c.classList.toggle('on', i === 0));
  go('report');
  // 图表需在视图可见后再 resize，避免在 display:none 时尺寸为 0
  requestAnimationFrame(() => { if (gaugeChart) gaugeChart.resize(); if (trendChart) trendChart.resize(); if (radarChart) radarChart.resize(); });
}

function renderCases(list) {
  $('rows').innerHTML = list.map((x, i) => `
    <tr class="${x.bad ? 'bad' : ''}${i === 0 ? ' sel' : ''}">
      <td class="q-cell"><span class="sid">${x.id}</span><b>${x.q}</b><p>${x.a}</p>${x.bad && x.reason ? `<div class="reason">⚠ ${x.reason}</div>` : ''}</td>
      <td class="score-cell"><span class="sdot ${clsOf(x.overall / 100)}">${Math.round(x.overall)}</span></td>
      <td class="score-cell">${scoreTag(x.f)}</td><td class="score-cell">${scoreTag(x.r)}</td>
      <td class="score-cell">${scoreTag(x.p)}</td><td class="score-cell">${scoreTag(x.c)}</td>
      <td>${x.bad ? '<span class="badpill">● Bad</span>' : '<span class="goodpill">● Pass</span>'}</td>
    </tr>`).join('');
}
$('rows').addEventListener('click', e => {
  const tr = e.target.closest('tr'); if (!tr) return;
  document.querySelectorAll('#rows tr').forEach(x => x.classList.remove('sel')); tr.classList.add('sel');
});
document.querySelectorAll('#view-report .tabs button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#view-report .tabs button').forEach(x => x.classList.remove('on')); b.classList.add('on');
  const cases = state.detail.cases;
  if (b.dataset.tab === 'bad') { const bad = cases.filter(c => c.bad); renderCases(bad); $('caseTitle').textContent = 'Bad Case 明细'; $('caseCount').textContent = bad.length + ' 条'; }
  else { renderCases(cases); $('caseTitle').textContent = '评估明细'; $('caseCount').textContent = cases.length + ' 条'; }
}));
document.querySelectorAll('#view-report .filters .chip').forEach(c => c.addEventListener('click', () => {
  document.querySelectorAll('#view-report .filters .chip').forEach(x => x.classList.remove('on')); c.classList.add('on');
  const cases = state.detail.cases, f = c.dataset.f;
  if (f === 'bad') renderCases(cases.filter(x => x.bad));
  else if (f === 'faith') renderCases(cases.filter(x => x.f < 0.75));
  else if (f === 'recall') renderCases(cases.filter(x => x.c < 0.7));
  else renderCases(cases);
}));

/* ---------- 图表 ---------- */
function buildCharts(d) {
  Chart.defaults.font.family = 'ui-monospace, Menlo, monospace';
  Chart.defaults.font.size = 11; Chart.defaults.color = '#9a9a90';
  const grid = '#efede8';
  if (gaugeChart) gaugeChart.destroy();
  if (trendChart) trendChart.destroy();
  if (radarChart) radarChart.destroy();

  gaugeChart = new Chart($('gauge'), { type: 'doughnut',
    data: { datasets: [{ data: [d.score, 100 - d.score], backgroundColor: ['#1f6feb', '#eceae4'], borderWidth: 0, cutout: '78%' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { enabled: false } } } });

  trendChart = new Chart($('trend'), { type: 'line',
    data: { labels: d.trend.labels, datasets: [
      { data: d.trend.composite, borderColor: '#1f6feb', backgroundColor: 'rgba(31,111,235,.07)', fill: true, tension: .35, borderWidth: 2.5, pointRadius: 3, pointBackgroundColor: '#1f6feb' },
      { data: d.trend.faithfulness, borderColor: '#1a7f52', tension: .35, borderWidth: 2, pointRadius: 0 },
      { data: d.trend.precision, borderColor: '#b8860b', tension: .35, borderWidth: 2, pointRadius: 0, borderDash: [4, 3] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
      scales: { x: { grid: { display: false } }, y: { min: 60, max: 95, grid: { color: grid }, border: { display: false } } } } });

  radarChart = new Chart($('radar'), { type: 'radar',
    data: { labels: d.radar.labels, datasets: [
      { data: d.radar.current, borderColor: '#1f6feb', backgroundColor: 'rgba(31,111,235,.14)', borderWidth: 2, pointRadius: 2, pointBackgroundColor: '#1f6feb' },
      { data: d.radar.baseline, borderColor: '#9a9a90', backgroundColor: 'rgba(154,154,144,.1)', borderWidth: 1.5, pointRadius: 0, borderDash: [4, 3] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { r: { min: 40, max: 100, grid: { color: grid }, angleLines: { color: grid }, pointLabels: { font: { size: 11 }, color: '#6b6b63' }, ticks: { display: false, stepSize: 20 } } } } });
}

/* ===================================================================== *
 *  评估集
 * ===================================================================== */
async function loadDatasets() {
  const datasets = await API.listDatasets();
  $('navDatasets').textContent = datasets.length;
  $('dsSubCount').textContent = `${datasets.length} 个数据集 · 点击查看样本明细`;
  $('dsGrid').innerHTML = datasets.map(d => {
    const rate = d.pass ? Math.round(d.pass / d.cnt * 100) : null;
    const col = rate === null ? 'var(--ink-faint)' : rate >= 75 ? 'var(--green)' : rate >= 60 ? 'var(--amber)' : 'var(--red)';
    return `<div class="ds-card" data-name="${d.n}">
      <div class="ds-ico">${d.ico}</div><h4>${d.n}</h4><div class="ds-meta">${d.d}</div>
      <div class="ds-stats"><div><b>${d.cnt}</b>样本数</div><div><b style="color:${col}">${rate === null ? '未评估' : rate + '%'}</b>最近通过率</div><div><b style="font-size:13px;color:var(--ink-soft)">${d.upd}</b>更新</div></div>
    </div>`;
  }).join('');
}
$('dsGrid').addEventListener('click', e => {
  const card = e.target.closest('.ds-card'); if (card) openDataset(card.dataset.name);
});
async function openDataset(name) {
  const { meta, samples, shown } = await API.getDataset(name);
  $('dsTitle').textContent = meta.name;
  $('dsSub').innerHTML = `${meta.desc} · 共 ${meta.count} 条样本 · 更新于 ${meta.updated}`;
  const rc = meta.passRate === null ? 'var(--ink-faint)' : meta.passRate >= 75 ? 'var(--green)' : meta.passRate >= 60 ? 'var(--amber)' : 'var(--red)';
  $('dsKv').innerHTML = `
    <div class="metric"><div class="m-label">样本总数</div><div class="m-val">${meta.count}</div></div>
    <div class="metric"><div class="m-label">已标注</div><div class="m-val">${meta.annotated}<small style="font-size:12px;color:var(--ink-faint)"> / ${meta.count}</small></div></div>
    <div class="metric"><div class="m-label">最近通过率</div><div class="m-val" style="color:${rc}">${meta.passRate === null ? '未评估' : meta.passRate + '%'}</div></div>
    <div class="metric"><div class="m-label">关联报告</div><div class="m-val">${meta.linkedReports}</div></div>`;
  $('dsCount').textContent = `显示 ${shown} / ${meta.count} 条`;
  $('dsRows').innerHTML = samples.map(s => `<tr>
    <td class="sid">${String(s.idx).padStart(3, '0')}</td>
    <td style="max-width:280px"><b style="font-weight:600">${s.query}</b></td>
    <td style="max-width:340px;color:var(--ink-soft);font-size:12.5px">${s.annotated ? s.ground_truth : '<span style="color:var(--ink-faint)">— 待补充 —</span>'}</td>
    <td>${s.annotated ? '<span class="goodpill">● 已标注</span>' : '<span class="badpill" style="background:var(--amber-soft);color:var(--amber)">● 待标注</span>'}</td></tr>`).join('');
  go('dataset');
}

/* ===================================================================== *
 *  评分指标
 * ===================================================================== */
async function loadMetrics() {
  const metrics = await API.listMetrics();
  $('metricCards').innerHTML = metrics.map(m => `
    <div class="mcard"><div class="mi">${m.icon}</div>
      <div><h4>${m.name} <span class="mtag">${m.type}</span></h4><p>${m.desc}</p></div>
      <div class="wt"><b>${(m.weight * 100).toFixed(0)}%</b><span>权重</span></div>
    </div>`).join('');
}

/* ===================================================================== *
 *  Bad Case 汇总
 * ===================================================================== */
const typeLabel = { 忠实: '忠实度冲突', 召回: '召回缺失', 精确: '检索噪声', 相关: '答案不完整' };
async function loadBadCases() {
  state.badAll = await API.listBadCases();
  state.badList = state.badAll;
  $('navBad').textContent = state.badAll.length;
  const counts = {}; state.badAll.forEach(b => counts[b.type] = (counts[b.type] || 0) + 1);
  $('badKv').innerHTML = Object.keys(typeLabel).map(t => `
    <div class="metric"><div class="m-label">${typeLabel[t]}</div><div class="m-val" style="color:var(--red)">${counts[t] || 0}</div></div>`).join('');
  renderBad(state.badList);
}
function badRow(x) {
  return `<tr class="bad"><td class="q-cell"><span class="sid">${x.id}</span><b>${x.q}</b><div class="reason">⚠ ${x.reason}</div></td>
    <td><span class="ver" style="font-family:var(--mono);font-size:11px;background:var(--accent-soft);color:var(--accent);padding:1px 7px;border-radius:5px">run ${x.src}</span></td>
    <td class="score-cell"><span class="sdot s-lo">${x.overall}</span></td>
    <td><span class="badpill">${typeLabel[x.type]}</span></td></tr>`;
}
function renderBad(list) {
  $('badCount').textContent = list.length + ' 条';
  const groups = {};
  list.forEach(x => { const k = state.badGroup === 'type' ? typeLabel[x.type] : ('run ' + x.src); (groups[k] = groups[k] || []).push(x); });
  const keys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
  $('badRows').innerHTML = keys.map(k => {
    const gc = state.badGroup === 'type' ? 'gc' : 'gc blue';
    return `<tr style="background:transparent;cursor:default"><td colspan="4" style="padding:0">
      <div class="grp-head">${state.badGroup === 'type' ? '⚠' : '◷'} ${k} <span class="${gc}">${groups[k].length} 条</span></div></td></tr>`
      + groups[k].map(badRow).join('');
  }).join('');
}
document.querySelectorAll('#view-badcase .filters .chip').forEach(c => c.addEventListener('click', () => {
  document.querySelectorAll('#view-badcase .filters .chip').forEach(x => x.classList.remove('on')); c.classList.add('on');
  const bf = c.dataset.bf;
  state.badList = bf === 'all' ? state.badAll : state.badAll.filter(x => x.type === bf);
  renderBad(state.badList);
}));
document.querySelectorAll('#badSeg button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#badSeg button').forEach(x => x.classList.remove('on')); b.classList.add('on');
  state.badGroup = b.dataset.grp; renderBad(state.badList);
}));

/* ===================================================================== *
 *  Prompt 版本
 * ===================================================================== */
async function loadPrompts() {
  const prompts = await API.listPrompts();
  $('pvList').innerHTML = prompts.map((p, i) => {
    const prev = prompts[i + 1];
    const canDiff = prev && p.score != null && prev.score != null;
    const diff = canDiff ? (p.score - prev.score) : null;
    const diffHtml = p.score == null ? '<span style="color:var(--amber);font-weight:600">草稿 · 待评估</span>'
      : canDiff ? (diff >= 0 ? `<span class="trend-up">▲ ${diff.toFixed(1)} vs ${prev.v}</span>` : `<span class="trend-dn">▼ ${Math.abs(diff).toFixed(1)} vs ${prev.v}</span>`)
      : '<span style="color:var(--ink-faint)">初始版本</span>';
    const tagLabel = p.tag === 'live' ? '● 当前使用' : p.tag === 'draft' ? '● 草稿' : '历史版本';
    const scoreBlock = p.score == null
      ? `<div><div class="sl">综合评分</div><div class="big" style="color:var(--ink-faint)">—</div></div>
         <div class="mini"><span>忠实度</span><b>—</b></div>
         <div class="mini"><span>上下文召回</span><b>—</b></div>
         <div class="mini" style="color:var(--ink-faint)"><span>状态</span><span>未评估</span></div>
         <button class="btn primary" style="margin-top:4px;justify-content:center" data-neweval>▶ 跑评估</button>`
      : `<div><div class="sl">综合评分</div><div class="big" style="color:${rColor(p.score)}">${p.score.toFixed(1)}</div></div>
         <div class="mini"><span>忠实度</span><b>${p.f.toFixed(2)}</b></div>
         <div class="mini"><span>上下文召回</span><b>${p.c.toFixed(2)}</b></div>
         <div class="mini" style="color:var(--ink-faint)"><span>关联</span><span>run ${p.run}</span></div>`;
    return `<div class="pvc ${p.tag === 'live' ? 'cur' : ''}">
      <div class="pvc-head"><span class="pvv">${p.v}</span><span class="pvtag ${p.tag}">${tagLabel}</span>${diffHtml}
        <span class="pvmeta">更新 ${p.date} · 评估 run ${p.run}</span></div>
      <div class="pvc-body"><div class="pvc-prompt">${p.body}</div><div class="pvc-score">${scoreBlock}</div></div>
    </div>`;
  }).join('');
}

/* ===================================================================== *
 *  路由
 * ===================================================================== */
const titles = { reports: '评估报告', datasets: '评估集', metrics: '评分指标', badcase: 'Bad Case', prompts: 'Prompt 版本', report: '评估报告', dataset: '评估集' };
function setCrumb(v) {
  const c = $('crumbs');
  if (v === 'report') c.innerHTML = `<span class="lnk" onclick="go('reports')">评估报告</span><span class="sep">/</span><span class="proj-pill"><span class="dot"></span>run ${state.detail ? state.detail.ver : ''}</span>`;
  else if (v === 'dataset') c.innerHTML = `<span class="lnk" onclick="go('datasets')">评估集</span><span class="sep">/</span><span class="proj-pill"><span class="dot"></span>${$('dsTitle').textContent}</span>`;
  else c.innerHTML = `<span>${titles[v]}</span>`;
}
function go(v) {
  document.querySelectorAll('.view').forEach(x => x.classList.remove('show'));
  $('view-' + v).classList.add('show');
  document.querySelector('.content').scrollTop = 0;
  const navKey = v === 'report' ? 'reports' : v === 'dataset' ? 'datasets' : v;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.nav === navKey));
  $('exportWrap').style.display = v === 'report' ? 'block' : 'none';
  setCrumb(v);
  // 列表类视图每次进入都从后端拉取最新
  if (v === 'reports') loadReports();
  else if (v === 'datasets') loadDatasets();
  else if (v === 'metrics') loadMetrics();
  else if (v === 'badcase') loadBadCases();
  else if (v === 'prompts') loadPrompts();
}
document.querySelectorAll('.nav-item').forEach(n => n.addEventListener('click', () => go(n.dataset.nav)));

/* ===================================================================== *
 *  导出
 * ===================================================================== */
const exportBtn = $('exportBtn'), exportMenu = $('exportMenu');
exportBtn.addEventListener('click', e => { e.stopPropagation(); exportMenu.classList.toggle('show'); });
document.addEventListener('click', () => exportMenu.classList.remove('show'));
exportMenu.addEventListener('click', e => e.stopPropagation());
exportMenu.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
  exportMenu.classList.remove('show');
  const kind = b.dataset.exp;
  if (kind === 'pdf') { toast('正在生成 PDF，请在打印窗口选择「保存为 PDF」'); setTimeout(() => window.print(), 400); }
  else exportCSV(kind === 'bad' ? 'bad' : 'all');
}));
function exportCSV(kind) {
  if (!state.detail) return;
  const list = kind === 'bad' ? state.detail.cases.filter(c => c.bad) : state.detail.cases;
  const head = ['case_id', 'question', 'answer', 'faithfulness', 'relevancy', 'context_precision', 'context_recall', 'overall', 'verdict', 'fail_reason'];
  const esc = s => '"' + String(s).replace(/"/g, '""') + '"';
  const lines = [head.join(',')].concat(list.map(x => [
    x.id, esc(x.q), esc(x.a), x.f.toFixed(3), x.r.toFixed(3), x.p.toFixed(3), x.c.toFixed(3),
    (x.overall / 100).toFixed(3), x.bad ? 'bad' : 'pass', esc(x.reason || '')
  ].join(',')));
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `rageval_${state.detail.ver.replace('#', '')}_${kind === 'bad' ? 'badcase' : 'cases'}.csv`;
  a.click(); URL.revokeObjectURL(a.href);
  toast(`已导出 ${list.length} 条明细 CSV`);
}

/* ===================================================================== *
 *  弹窗通用
 * ===================================================================== */
document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => $(b.dataset.close).classList.remove('show')));
function openMask(id) { $(id).classList.add('show'); }

/* ---------- 新建评估 ---------- */
$('newEvalBtn').addEventListener('click', openNewEval);
document.addEventListener('click', e => { if (e.target.closest('[data-neweval]')) openNewEval(); });
async function openNewEval() {
  const datasets = await API.listDatasets();
  $('neDs').innerHTML = datasets.map(d => `<option>${d.n} (${d.cnt} 条)</option>`).join('');
  $('neName').value = '';
  openMask('newEvalMask');
}
$('startEval').addEventListener('click', async () => {
  const name = $('neName').value.trim() || '知识库问答评估';
  const dsLabel = $('neDs').value, dsName = dsLabel.replace(/\s*\(.*$/, '');
  const cntMatch = dsLabel.match(/\((\d+)/); const count = cntMatch ? +cntMatch[1] : 200;
  const payload = {
    name, dataset: dsName, count,
    model: $('neModel').value,
    prompt: $('nePrompt').value.replace(/\s*\(current\)/, ''),
    retriever: $('neRetr').value.split(' · ')[0],
    baseline: $('neBase').value
  };
  const { run_id } = await API.createEvaluation(payload);
  $('newEvalMask').classList.remove('show');
  go('reports');
  toast(`已启动评估 run ${run_id}`);
  pollEvaluation(run_id);
});
// 轮询评估进度（后端模式下调用 GET /evaluations/:id/status）
function pollEvaluation(id) {
  const timer = setInterval(async () => {
    const s = await API.getEvaluationStatus(id);
    if ($('view-reports').classList.contains('show')) loadReports();
    if (s.status === 'done') { clearInterval(timer); toast(`run ${id} 评估完成${s.score != null ? ' · 综合分 ' + s.score : ''}`); }
  }, 900);
}

/* ---------- 上传评估集 ---------- */
$('uploadBtn').addEventListener('click', () => { openMask('uploadMask'); setFmt('csv'); resetUpload(); });
const specs = {
  csv: `<span class="k">query</span><span class="req">*</span>,<span class="k">ground_truth</span><span class="req">*</span>,contexts,metadata\n如何申请年假？,满一年享10天年假…,"doc_12;doc_34",{"cat":"hr"}`,
  jsonl: `{<span class="k">"query"</span><span class="req">*</span>: "如何申请年假？",\n <span class="k">"ground_truth"</span><span class="req">*</span>: "满一年享10天年假…",\n "contexts": ["doc_12","doc_34"]}`
};
function resetUpload() { state.uploadRows = null; state.uploadCount = 0; $('preview').classList.remove('show'); $('dsName').value = ''; $('fileInput').value = ''; document.querySelector('#dropzone .dz-main').textContent = '点击选择文件，或拖拽到此处'; }
function setFmt(f) {
  state.uploadFmt = f;
  document.querySelectorAll('.fmt-tabs button').forEach(b => b.classList.toggle('on', b.dataset.fmt === f));
  $('spec').innerHTML = specs[f];
  $('dzSub').textContent = `支持 .${f === 'csv' ? 'csv' : 'jsonl'} · 必填列标 * · 最大 20MB`;
  $('fileInput').accept = f === 'csv' ? '.csv,.tsv' : '.jsonl,.json';
}
document.querySelectorAll('.fmt-tabs button').forEach(b => b.addEventListener('click', () => setFmt(b.dataset.fmt)));
const dz = $('dropzone'), fileInput = $('fileInput');
dz.addEventListener('click', () => fileInput.click());
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('drag'); if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]); });
fileInput.addEventListener('change', e => { if (e.target.files[0]) handleFile(e.target.files[0]); });
function splitCSV(line) { const out = []; let cur = '', q = false; for (let i = 0; i < line.length; i++) { const ch = line[i]; if (ch === '"') { if (q && line[i + 1] === '"') { cur += '"'; i++; } else q = !q; } else if (ch === ',' && !q) { out.push(cur); cur = ''; } else cur += ch; } out.push(cur); return out; }
function handleFile(file) {
  document.querySelector('#dropzone .dz-main').textContent = '📄 ' + file.name;
  const reader = new FileReader();
  reader.onload = ev => {
    const text = ev.target.result; let header = [], rows = [], all = [];
    try {
      if (state.uploadFmt === 'csv') {
        const ls = text.split(/\r?\n/).filter(l => l.trim());
        header = splitCSV(ls[0]);
        all = ls.slice(1).map(splitCSV).map(cells => Object.fromEntries(header.map((h, i) => [h, cells[i]])));
        rows = ls.slice(1, 6).map(splitCSV);
      } else {
        const ls = text.split(/\r?\n/).filter(l => l.trim());
        all = ls.map(l => JSON.parse(l)); header = Object.keys(all[0]);
        rows = all.slice(0, 5).map(o => header.map(h => Array.isArray(o[h]) ? o[h].join(';') : (typeof o[h] === 'object' ? JSON.stringify(o[h]) : o[h])));
      }
    } catch (err) {
      $('pvHead').innerHTML = '⚠ 解析失败：请检查格式是否符合规范';
      $('pvHead').style.cssText = 'background:var(--red-soft);color:var(--red)';
      $('preview').classList.add('show'); state.uploadRows = null; return;
    }
    state.uploadRows = all; state.uploadCount = all.length;
    $('pvHead').innerHTML = `✓ 已解析 ${all.length} 行 · 预览前 ${rows.length} 条`; $('pvHead').style.cssText = '';
    $('pvThead').innerHTML = '<tr>' + header.map(h => `<th>${h}</th>`).join('') + '</tr>';
    $('pvBody').innerHTML = rows.map(r => '<tr>' + r.map(c => `<td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c || ''}</td>`).join('') + '</tr>').join('');
    $('preview').classList.add('show');
    if (!$('dsName').value) $('dsName').value = file.name.replace(/\.(csv|tsv|jsonl|json)$/i, '');
  };
  reader.readAsText(file);
}
$('confirmUpload').addEventListener('click', async () => {
  const name = $('dsName').value.trim();
  if (!name) { toast('请填写评估集名称'); return; }
  if (!state.uploadRows) { toast('请先选择并解析文件'); return; }
  await API.uploadDataset({ name, format: state.uploadFmt, count: state.uploadCount, rows: state.uploadRows });
  $('uploadMask').classList.remove('show');
  loadDatasets();
  toast(`已导入评估集「${name}」· ${state.uploadCount} 条样本`);
});

/* ---------- 新建 Prompt 版本 ---------- */
$('newPromptBtn').addEventListener('click', async () => {
  const prompts = await API.listPrompts();
  const cur = prompts.find(p => p.tag === 'live') || prompts[0];
  const n = Math.max(...prompts.map(p => parseInt(p.v.replace(/\D/g, '')) || 0)) + 1;
  $('npVer').value = 'v' + n;
  $('npBody').value = (cur ? cur.body : '').replace(/<[^>]+>/g, '');
  openMask('newPromptMask');
});
$('savePrompt').addEventListener('click', async () => {
  const ver = $('npVer').value.trim(), body = $('npBody').value;
  if (!ver) { toast('请填写版本号'); return; }
  if (!body.trim()) { toast('提示词内容不能为空'); return; }
  await API.createPrompt({ version: ver, body });
  $('newPromptMask').classList.remove('show');
  loadPrompts();
  toast(`已创建 ${ver}（草稿 · 未评估）`);
});

/* ---------- seg 通用高亮 ---------- */
document.querySelectorAll('.seg').forEach(s => s.addEventListener('click', e => {
  if (e.target.tagName === 'BUTTON') { s.querySelectorAll('button').forEach(x => x.classList.remove('on')); e.target.classList.add('on'); }
}));

/* ---------- 启动 ---------- */
go('reports');
// 预取侧边栏徽标计数
(async () => {
  try {
    const [ds, bad] = await Promise.all([API.listDatasets(), API.listBadCases()]);
    $('navDatasets').textContent = ds.length;
    $('navBad').textContent = bad.length;
  } catch (e) { /* 后端未就绪时忽略 */ }
})();
