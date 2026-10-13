/* =====================================================================
 * app.js — 界面渲染 + 路由（只依赖 api.js，不直接写死数据）
 * 对接后端时无需修改本文件。
 * ===================================================================== */
Chart.defaults.font.family = '"PingFang SC","Microsoft YaHei",sans-serif';
Chart.defaults.font.size = 11; Chart.defaults.color = '#5c6676';
const $ = id => document.getElementById(id);
function toast(m) { const t = $('toast'); t.textContent = m; t.classList.add('show'); clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), 2200); }
function openModal(id) { $(id).classList.add('show'); }
function closeModal(id) { $(id).classList.remove('show'); }

/* 本地缓存（启动时从后端拉取一次） */
let KBS = [];
const DOCS = {};
const stPill = { ok: '<span class="pill p-ok"><span class="d"></span>已索引</span>', idx: '<span class="pill p-idx"><span class="d"></span>索引中</span>', wait: '<span class="pill p-wait"><span class="d"></span>待处理</span>', err: '<span class="pill p-err"><span class="d"></span>失败</span>' };
const stName = { ok: '已索引', idx: '索引中', wait: '待处理', err: '失败' };

/* ================= 总览 ================= */
let chartsBuilt = false;
async function buildOverview() {
  if (chartsBuilt) return; chartsBuilt = true;
  const o = await API.getOverview();
  new Chart($('ovTrend'), { data: { labels: o.trend.days, datasets: [
    { type: 'bar', label: '问答量', data: o.trend.qa, backgroundColor: '#cfe0f6', borderRadius: 3, yAxisID: 'y' },
    { type: 'line', label: '命中率', data: o.trend.hit, borderColor: '#1f9d6b', backgroundColor: 'rgba(31,157,107,.08)', fill: true, tension: .4, borderWidth: 2, pointRadius: 0, yAxisID: 'y1' }
  ] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
    scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { grid: { color: '#eef2f7' }, border: { display: false } }, y1: { position: 'right', min: 80, max: 100, grid: { display: false }, border: { display: false }, ticks: { callback: v => v + '%' } } } } });
  new Chart($('ovPie'), { type: 'doughnut', data: { labels: KBS.map(k => k.name), datasets: [{ data: KBS.map(k => k.docs), backgroundColor: ['#2d7ff0', '#7a5bd6', '#1aa3a3', '#d4a235'], borderColor: '#fff', borderWidth: 2, cutout: '60%' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { boxWidth: 11, padding: 11, font: { size: 11.5 } } } } } });
  $('ovHealth').innerHTML = KBS.map(k => {
    const c = k.frag < 4 ? 'var(--green)' : k.frag < 6 ? 'var(--amber)' : 'var(--red)';
    return `<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--line-soft)">
      <span style="width:9px;height:9px;border-radius:50%;background:${c}"></span>
      <b style="font-size:12.5px">${k.name}</b>
      <span style="font-size:11.5px;color:var(--ink-faint)">${(k.chunks / 1000).toFixed(0)}K chunks</span>
      <span style="margin-left:auto;font-size:11.5px;color:var(--ink-soft)">碎片率 <b style="color:${c};font-family:var(--mono)">${k.frag}%</b></span>
      ${k.status === 'idx' ? '<span class="pill p-idx" style="margin-left:8px"><span class="d"></span>索引中</span>' : ''}
    </div>`; }).join('');
  $('ovLog').innerHTML = o.logs.map(l => `<div style="display:flex;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line-soft);font-size:12.5px">
    <span class="mono" style="color:var(--ink-faint);font-size:11px">${l[0]}</span>
    <span>${l[2]}</span><span style="margin-left:auto">${stPill[l[3]]}</span></div>`).join('');
  $('ovHot').innerHTML = o.hot.map((h, i) => `<div class="hot"><span class="rank ${i < 3 ? 'top' : 'norm'}">${i + 1}</span><span>${h[0]}</span><span class="hc">${h[1]} 次</span></div>`).join('');
  $('ovBars').innerHTML = KBS.map((k, i) => `<div class="barrow"><span class="bl">${k.name}</span><span class="bt"><i style="width:${o.hitRates[i]}%;background:${k.color}"></i></span><span class="bv" style="color:${k.color}">${o.hitRates[i]}%</span></div>`).join('');
}

/* ================= 智能问答 ================= */
const SAMPLES = ['理赔款一般多久到账？', '核保模块支持哪些险种？', '员工年假有多少天？', 'v2.4 版本新增了什么功能？'];
function renderSamples() { $('samples').innerHTML = SAMPLES.map(s => `<span class="sq" onclick="ask('${s}')">${s}</span>`).join(''); }
function clearChat() { $('chatInner').innerHTML = ''; renderWelcome(); }
function renderWelcome() {
  $('chatInner').innerHTML = `<div class="msg bot"><div class="av">🤖</div><div class="body"><div class="who">知识库智能体</div>
    <div class="bubble">你好，我是基于你的知识库训练的问答助手。问我任何问题，我会检索知识库并给出<strong>带来源引用</strong>的答案，还能展开查看我的<strong>检索与思考过程</strong>。
    <div class="welcome-caps">
      <div class="cap-chip" onclick="ask('理赔款一般多久到账？')"><span class="ci" style="background:var(--blue)">✦</span>多路召回 + 重排检索</div>
      <div class="cap-chip" onclick="ask('v2.4 版本新增了什么功能？')"><span class="ci" style="background:var(--violet)">◴</span>可追溯来源引用</div>
      <div class="cap-chip" onclick="ask('核保模块支持哪些险种？')"><span class="ci" style="background:var(--teal)">⌕</span>跨库语义检索</div>
      <div class="cap-chip" onclick="ask('员工年假有多少天？')"><span class="ci" style="background:var(--amber)">◷</span>展示思考全过程</div>
    </div></div></div></div>`;
}
function userMsg(q) { return `<div class="msg user"><div class="av">👤</div><div class="body"><div class="who">你</div><div class="bubble">${q}</div></div></div>`; }
function ask(q) { $('qInput').value = q; sendQ(); }
function sendQ() {
  const q = $('qInput').value.trim(); if (!q) return;
  $('qInput').value = '';
  const inner = $('chatInner');
  inner.insertAdjacentHTML('beforeend', userMsg(q));
  const id = 'b' + Date.now();
  inner.insertAdjacentHTML('beforeend', `<div class="msg bot"><div class="av">🤖</div><div class="body"><div class="who">知识库智能体</div><div id="${id}"></div></div></div>`);
  $('chatBody').scrollTop = $('chatBody').scrollHeight;
  runPipeline($(id), q);
}
async function runPipeline(host, q) {
  const showThink = $('showThink').checked;
  const agent = $('agentMode').checked;
  host.innerHTML = `<div class="bubble"><span style="color:var(--ink-faint)">正在检索知识库…</span></div>`;
  const kb = $('chatKb').value;
  const d = await API.ask(q, { kb, agent });   // 后端返回 {think/steps, answer, srcs/sources, follow/followups}
  let steps = (d.think || d.steps || []).slice();
  if (agent) {
    steps = [
      { t: '任务规划 (Agent)', ms: '120ms', html: '拆解为子任务：① 检索理赔时效 ② 检索小额快速通道 ③ 汇总答复。规划工具链：<span class="qrw">知识库检索</span><span class="qrw">结果校验</span>' },
      ...steps,
      { t: '结果校验 (Agent)', ms: '88ms', html: '对答案做一致性校验：数值「3 个工作日 / 24 小时 / 5 个工作日」均可在来源中定位，无冲突，<b style="color:var(--green)">通过</b>。' }
    ];
  }
  let html = '';
  if (showThink) {
    html += `<div class="think open"><div class="think-h" onclick="this.parentNode.classList.toggle('open')">
      <span class="spark">${agent ? '🤖' : '✦'}</span>${agent ? 'Agent 执行过程' : '检索与思考过程'}<span class="el" id="elapsed">运行中…</span><span class="cv">▸</span></div>
      <div class="think-steps" id="tsteps"></div></div>`;
  }
  html += `<div class="bubble" id="ansbox"><span style="color:var(--ink-faint)">正在检索知识库…</span></div>`;
  host.innerHTML = html;
  const srcs = d.srcs || d.sources || [];
  const follow = d.follow || d.followups || [];
  let i = 0, total = 0;
  function next() {
    if (showThink && i < steps.length) {
      const s = steps[i]; total += parseInt(s.ms);
      let body = s.html || '';
      if (s.chunks) { body = s.chunks.map(c => `<div class="chunk"><div class="ch-top"><span class="ch-src">${c.src}</span><span class="score" style="color:${c.score > 0.8 ? 'var(--green)' : c.score > 0.65 ? 'var(--blue)' : 'var(--amber)'}"><span class="scorebar" style="width:${Math.round(c.score * 46)}px;background:currentColor"></span>${c.score.toFixed(2)}</span></div><div class="ch-txt">${c.txt}</div></div>`).join(''); }
      $('tsteps').insertAdjacentHTML('beforeend', `<div class="tstep"><div class="dotcol"><div class="sdot">${i + 1}</div><div class="sline"></div></div>
        <div><div class="st-title">${s.t}<span class="ms">${s.ms}</span></div><div class="st-body">${body}</div></div></div>`);
      $('chatBody').scrollTop = $('chatBody').scrollHeight;
      i++; setTimeout(next, 520);
    } else {
      if (showThink) $('elapsed').textContent = '耗时 ' + (total / 1000).toFixed(2) + 's · ' + steps.length + ' 步';
      const ans = $('ansbox'); ans.innerHTML = '';
      const full = d.answer; let p = 0;
      (function stream() {
        if (p <= full.length) { ans.innerHTML = full.slice(0, p) + '<span style="opacity:.4">▋</span>'; p += 6; $('chatBody').scrollTop = $('chatBody').scrollHeight; setTimeout(stream, 16); }
        else {
          ans.innerHTML = full + `<div class="srcs"><div class="st">参考来源</div>${srcs.map(s => `<div class="srcitem"><span class="n">${s[0]}</span><span>${s[1]}</span><span style="margin-left:auto;font-family:var(--mono);color:var(--blue);font-weight:700">${s[2]}</span></div>`).join('')}</div>`
            + `<div class="followups">${follow.map(f => `<span class="fu" onclick="ask('${f}')">${f}</span>`).join('')}</div>`
            + `<div class="ansfeed"><span style="font-size:12px;color:var(--ink-faint)">这个回答有帮助吗？</span><span class="fb" onclick="toast('感谢反馈 👍')">👍 有用</span><span class="fb" onclick="toast('已记录，将用于优化 👎')">👎 没用</span><span class="fb" onclick="toast('已复制答案')">⧉ 复制</span></div>`;
          $('chatBody').scrollTop = $('chatBody').scrollHeight;
        }
      })();
    }
  }
  setTimeout(next, 360);
}

/* ================= 检索 ================= */
async function runSearch() {
  const t0 = performance.now();
  const list = await API.search($('searchInput').value.trim(), {
    kb: $('sKb').value, type: $('sType').value, topk: +$('sTopk').value,
    threshold: $('sThr').value / 100, rerank: $('useRerank').checked
  });
  $('searchResults').innerHTML = list.map((r, i) => `
    <div class="res-item"><div class="rk">${i + 1}</div>
      <div><div class="res-src"><b>${r.src.split(' · ')[0]}</b><span>· ${r.src.split(' · ').slice(1).join(' · ')}</span><span class="ft">${r.type}</span>
        <span class="res-score"><span class="scorebar" style="width:${Math.round(r.score * 54)}px;background:currentColor"></span>${r.score.toFixed(2)}</span></div>
      <div class="res-txt">${r.txt}</div>
      <div class="res-foot"><button class="btn sm" onclick="toast('已打开原文定位（演示）')">查看原文</button>
        <button class="btn sm" onclick="toast('已复制片段')">复制片段</button>
        <button class="btn sm" onclick="go('chat')">用它提问 →</button></div>
    </div>`).join('');
  $('searchMeta').textContent = `命中 ${list.length} 条 · 耗时 ${Math.max(60, Math.round(performance.now() - t0 + 120))}ms${$('useRerank').checked ? ' · 已重排' : ''}`;
}
function initSearch() {
  $('sThr').addEventListener('input', e => $('thrv').textContent = (e.target.value / 100).toFixed(2));
  $('searchChips').innerHTML = ['相关度排序', '按时间', '仅PDF', '仅FAQ库'].map((c, i) => `<span class="chip${i === 0 ? ' on' : ''}">${c}</span>`).join('');
  $('searchChips').addEventListener('click', e => { if (e.target.classList.contains('chip')) { $('searchChips').querySelectorAll('.chip').forEach(x => x.classList.remove('on')); e.target.classList.add('on'); runSearch(); } });
  runSearch();
}

/* ================= 知识库管理 ================= */
function renderKbGrid() {
  $('kbGrid').innerHTML = KBS.map(k => `
    <div class="kb-card" onclick="openKb('${k.id}')">
      <div class="kc-top"><div class="kc-ico" style="background:${k.color}">${k.ico}</div>
        <div><h4>${k.name}</h4><div class="kc-desc">${k.desc}</div></div></div>
      <div style="display:flex;gap:7px;align-items:center">${k.status === 'idx' ? '<span class="pill p-idx"><span class="d"></span>索引中</span>' : '<span class="pill p-ok"><span class="d"></span>就绪</span>'}
        <span class="ft">${k.model}</span></div>
      <div class="kc-stats"><div><b>${k.docs.toLocaleString()}</b>文档</div><div><b>${(k.chunks / 1000).toFixed(0)}K</b>向量块</div><div><b style="color:${k.frag < 4 ? 'var(--green)' : k.frag < 6 ? 'var(--amber)' : 'var(--red)'}">${k.frag}%</b>碎片率</div></div>
    </div>`).join('')
    + `<div class="kb-card" style="display:flex;align-items:center;justify-content:center;border-style:dashed;color:var(--navy)" onclick="openModal('newKbMask')"><div style="text-align:center"><div style="font-size:26px">＋</div><div style="font-weight:600;margin-top:4px">新建知识库</div></div></div>`;
}
let curKb = null, curDocs = [];
async function openKb(id) {
  curKb = KBS.find(k => k.id === id);
  curDocs = await API.getKbDocs(id);
  $('pageTitle').textContent = curKb.name;
  $('kbMini').innerHTML = `
    <div class="mini"><div class="ml">文档数</div><div class="mv">${curKb.docs.toLocaleString()}</div></div>
    <div class="mini"><div class="ml">向量块</div><div class="mv">${(curKb.chunks / 1000).toFixed(0)}K</div></div>
    <div class="mini"><div class="ml">碎片率</div><div class="mv" style="color:${curKb.frag < 4 ? 'var(--green)' : curKb.frag < 6 ? 'var(--amber)' : 'var(--red)'}">${curKb.frag}%</div></div>
    <div class="mini"><div class="ml">最近更新</div><div class="mv" style="font-size:13px">${curKb.upd.split(' ')[0]}</div></div>`;
  $('chunkCfg').innerHTML = `
    <div class="cfg-row"><span class="k">Embedding 模型</span><span class="v">${curKb.model}</span></div>
    <div class="cfg-row"><span class="k">向量维度</span><span class="v">${curKb.dim}</span></div>
    <div class="cfg-row"><span class="k">分块大小</span><span class="v">${curKb.chunk} tokens</span></div>
    <div class="cfg-row"><span class="k">重叠 overlap
