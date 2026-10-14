/* ============================================================
 * app.js — 知识图谱 UI + 手写力导向布局（只依赖 api.js）
 * 数据读取走 API.getStats/getSeed/getNeighbors/search，
 * 增删改走 API.createNode / createEdge / updateNode / deleteNode / deleteEdge，
 * 节点内容走 API.getNodeContent，增量同步走 API.pullDelta。
 * ============================================================ */
const $ = id => document.getElementById(id);
const svg = $('graph'), vp = $('viewport'), edgeLayer = $('edgeLayer'), nodeLayer = $('nodeLayer');

/* ---- 节点类型配置（可自行增减）---- */
const TYPES = {
  product:  { name: '产品', color: '#1f5aa6' },
  clause:   { name: '条款', color: '#2d7ff0' },
  risk:     { name: '风险', color: '#e05548' },
  claim:    { name: '理赔', color: '#1aa3a3' },
  customer: { name: '客户', color: '#7a5bd6' },
  channel:  { name: '渠道', color: '#d4a235' },
  doc:      { name: '文档', color: '#8a94a6' },
};
const TKEYS = Object.keys(TYPES);
let curType = 'product';

/* ---- 大规模配置 ---- */
const CFG = { MAX_NODES: 700, EXPAND_LIMIT: 24 };   // 可见上限 + 单次展开邻居数
let addSeq = 0;                                      // 节点加入顺序（超限回收最旧）

/* ---- 状态 ---- */
let nodes = [], edges = [], selected = null, history = [], changeSeq = 0;
let syncVersion = 0;              // 增量同步游标
const hidden = new Set();          // 被过滤隐藏的类型
let W = 800, H = 600;
const T = { k: 1, x: 0, y: 0 };    // 画布缩放/平移
const byId = id => nodes.find(n => n.id === id);

/* ============================================================
 * 力导向布局
 * ============================================================ */
let alpha = 0;
function reheat(a = 0.45) { alpha = Math.max(alpha, a); }
function tick() {
  alpha *= 0.92; if (alpha < 0.04) alpha = 0;
  const K_REP = 5200, L = 118, K_SPR = 0.035, GRAV = 0.025, DAMP = 0.8;
  for (const n of nodes) { n.vx = n.vx || 0; n.vy = n.vy || 0; }
  for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
    const a = nodes[i], b = nodes[j];
    let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy || 0.01, d = Math.sqrt(d2);
    const f = K_REP / d2, fx = dx / d * f, fy = dy / d * f;
    a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
  }
  for (const e of edges) {
    const a = byId(e.source), b = byId(e.target); if (!a || !b) continue;
    let dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
    const f = (d - L) * K_SPR, fx = dx / d * f, fy = dy / d * f;
    a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
  }
  for (const n of nodes) { n.vx += (W / 2 - n.x) * GRAV * alpha; n.vy += (H / 2 - n.y) * GRAV * alpha; }
  for (const n of nodes) {
    if (n.fixed) { n.vx = 0; n.vy = 0; continue; }
    n.vx *= DAMP; n.vy *= DAMP;
    n.x += n.vx * alpha; n.y += n.vy * alpha;
    n.x = Math.max(40, Math.min(W - 40, n.x)); n.y = Math.max(40, Math.min(H - 40, n.y));
  }
  positionDom();
  requestAnimationFrame(tick);
}

/* ============================================================
 * 渲染（增量：只创建/更新/移除变化的 DOM）
 * ============================================================ */
function render() {
  const eIds = new Set(edges.map(e => e.id));
  [...edgeLayer.children].forEach(g => { if (!eIds.has(g.dataset.id)) g.remove(); });
  for (const e of edges) {
    let g = edgeLayer.querySelector(`[data-id="${e.id}"]`);
    if (!g) {
      g = mk('g', { 'data-id': e.id });
      const line = mk('line', { class: 'edge spawn' });
      const lbl = mk('text', { class: 'edge-label' }); lbl.textContent = e.label || '';
      g.append(line, lbl); edgeLayer.appendChild(g);
      setTimeout(() => line.classList.remove('spawn'), 500);
    } else { g.querySelector('text').textContent = e.label || ''; }
  }
  const nIds = new Set(nodes.map(n => n.id));
  [...nodeLayer.children].forEach(g => { if (!nIds.has(g.dataset.id)) g.remove(); });
  for (const n of nodes) {
    let g = nodeLayer.querySelector(`[data-id="${n.id}"]`);
    if (!g) {
      g = mk('g', { class: 'node spawn', 'data-id': n.id });
      const c = mk('circle', { r: nodeR(n) });
      const t = mk('text', { dy: nodeR(n) + 15 });
      g.append(c, t);
      bindNode(g, n); nodeLayer.appendChild(g);
      setTimeout(() => g.classList.remove('spawn'), 520);
    }
    const c = g.querySelector('circle'), t = g.querySelector('text');
    c.setAttribute('r', nodeR(n)); c.setAttribute('fill', TYPES[n.type] ? TYPES[n.type].color : '#8894a5');
    t.setAttribute('dy', nodeR(n) + 15); t.textContent = n.label;
  }
  applyFilterDim(); updateStats(); refreshEdgeSelects();
}
function nodeR(n) { const deg = (n.deg != null && n.deg > 0) ? n.deg : edges.filter(e => e.source === n.id || e.target === n.id).length; return 11 + Math.min(Math.sqrt(deg || 1) * 1.6, 13); }
function mk(tag, attrs) { const el = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const k in attrs) el.setAttribute(k, attrs[k]); return el; }

function positionDom() {
  for (const g of nodeLayer.children) { const n = byId(g.dataset.id); if (n) g.setAttribute('transform', `translate(${n.x},${n.y})`); }
  for (const g of edgeLayer.children) {
    const e = edges.find(x => x.id === g.dataset.id); if (!e) continue;
    const a = byId(e.source), b = byId(e.target); if (!a || !b) continue;
    const line = g.querySelector('line'), lbl = g.querySelector('text');
    line.setAttribute('x1', a.x); line.setAttribute('y1', a.y); line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
    lbl.setAttribute('x', (a.x + b.x) / 2); lbl.setAttribute('y', (a.y + b.y) / 2 - 3);
  }
}

/* ============================================================
 * 交互：选中 / 拖拽 / 缩放 / 平移 / 高亮
 * ============================================================ */
function bindNode(g, n) {
  let dragging = false, moved = false;
  g.addEventListener('pointerdown', ev => { ev.stopPropagation(); dragging = true; moved = false; g.setPointerCapture(ev.pointerId); n.fixed = true; });
  g.addEventListener('pointermove', ev => { if (!dragging) return; moved = true; const p = toGraph(ev.clientX, ev.clientY); n.x = p.x; n.y = p.y; positionDom(); });
  g.addEventListener('pointerup', () => { dragging = false; n.fixed = false; reheat(0.18); if (!moved) selectNode(n.id); });
  g.addEventListener('dblclick', ev => { ev.stopPropagation(); expand(n.id, n.loaded || 0); });
  g.addEventListener('pointerenter', () => highlight(n.id));
  g.addEventListener('pointerleave', () => { if (!selected) highlight(null); });
}
function toGraph(cx, cy) { const r = svg.getBoundingClientRect(); return { x: (cx - r.left - T.x) / T.k, y: (cy - r.top - T.y) / T.k }; }

function highlight(id) {
  if (id == null) { [...nodeLayer.children].forEach(g => g.classList.remove('dim')); [...edgeLayer.children].forEach(g => { g.querySelector('line').classList.remove('hl', 'dim'); g.querySelector('text').classList.remove('dim'); }); return; }
  const nb = new Set([id]); edges.forEach(e => { if (e.source === id) nb.add(e.target); if (e.target === id) nb.add(e.source); });
  [...nodeLayer.children].forEach(g => g.classList.toggle('dim', !nb.has(g.dataset.id)));
  [...edgeLayer.children].forEach(g => { const e = edges.find(x => x.id === g.dataset.id); const on = e && (e.source === id || e.target === id);
    g.querySelector('line').classList.toggle('hl', on); g.querySelector('line').classList.toggle('dim', !on); g.querySelector('text').classList.toggle('dim', !on); });
}

function applyTransform() { vp.setAttribute('transform', `translate(${T.x},${T.y}) scale(${T.k})`); }
svg.addEventListener('wheel', ev => {
  ev.preventDefault(); const r = svg.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const f = ev.deltaY < 0 ? 1.12 : 0.89, nk = Math.max(0.3, Math.min(2.6, T.k * f));
  T.x = mx - (mx - T.x) * (nk / T.k); T.y = my - (my - T.y) * (nk / T.k); T.k = nk; applyTransform();
}, { passive: false });
let panning = false, ps = {};
svg.addEventListener('pointerdown', ev => { if (ev.target.closest('.node')) return; panning = true; ps = { x: ev.clientX - T.x, y: ev.clientY - T.y }; svg.classList.add('panning'); if (selected) { selected = null; renderDetail(); highlight(null); [...nodeLayer.children].forEach(g => g.classList.remove('sel')); } });
svg.addEventListener('pointermove', ev => { if (!panning) return; T.x = ev.clientX - ps.x; T.y = ev.clientY - ps.y; applyTransform(); });
window.addEventListener('pointerup', () => { panning = false; svg.classList.remove('panning'); });
$('zoomIn').onclick = () => zoomBy(1.2); $('zoomOut').onclick = () => zoomBy(0.83);
$('zoomReset').onclick = () => { T.k = 1; T.x = 0; T.y = 0; applyTransform(); };
function zoomBy(f) { const nk = Math.max(0.3, Math.min(2.6, T.k * f)); T.x = W / 2 - (W / 2 - T.x) * (nk / T.k); T.y = H / 2 - (H / 2 - T.y) * (nk / T.k); T.k = nk; applyTransform(); }

/* ============================================================
 * 选中详情
 * ============================================================ */
function selectNode(id) { selected = id; [...nodeLayer.children].forEach(g => g.classList.toggle('sel', g.dataset.id === id)); highlight(id); renderDetail(); }
function renderDetail() {
  const d = $('detail');
  if (!selected || !byId(selected)) { d.innerHTML = '<div class="detail-empty">点击任意节点查看详情<br>并进行编辑 / 删除</div>'; return; }
  const n = byId(selected), col = TYPES[n.type] ? TYPES[n.type].color : '#8894a5', tyName = TYPES[n.type] ? TYPES[n.type].name : n.type;
  const nbrs = edges.filter(e => e.source === n.id || e.target === n.id).map(e => { const oid = e.source === n.id ? e.target : e.source; const o = byId(oid); return { o, eid: e.id, rel: e.label, dir: e.source === n.id ? '→' : '←' }; }).filter(x => x.o);
  d.innerHTML = `
    <div class="d-head"><div class="d-ico" style="background:${col}">${tyName[0]}</div>
      <div><h4>${esc(n.label)}</h4><div class="ty">${tyName} · ${nbrs.length} 个关系</div></div></div>
    <div class="d-row"><span class="k">ID</span><span class="v" style="font-family:var(--mono);font-size:11px">${n.id}</span></div>
    <div class="d-row"><span class="k">类型</span><span class="v" style="color:${col}">${tyName}</span></div>
    ${n._total != null ? `<div class="d-row"><span class="k">后端总关系</span><span class="v">${n._total}</span></div>` : ''}
    <div class="d-acts"><button class="btn sm" data-act="expand" style="flex:1">⊕ 展开邻居${(n._total != null && n._total > (n.loaded || nbrs.length)) ? `（还有 ${n._total - (n.loaded || nbrs.length)}）` : ''}</button></div>
    <div class="sec-sub">相邻节点 <span style="color:var(--ink-faint);font-weight:400">（✕ 删除该关系）</span></div>
    ${nbrs.length ? nbrs.map(x => `<div class="nbr"><span class="dot" style="background:${TYPES[x.o.type] ? TYPES[x.o.type].color : '#8894a5'}"></span><span class="nbr-go" data-go="${x.o.id}">${esc(x.o.label)}</span><span class="rel">${x.dir} ${esc(x.rel || '')}</span><span class="ex" data-deledge="${x.eid}" title="删除该关系">✕</span></div>`).join('') : '<div style="font-size:12px;color:var(--ink-faint)">无相邻节点</div>'}
    <div class="sec-sub">关联内容 / 来源切片</div>
    <div class="ncontent" id="nodeContent"><div class="nc-tip">加载中…</div></div>
    <div class="d-acts"><button class="btn sm" data-act="edit">✎ 重命名/改类型</button><button class="btn sm danger" data-act="del">🗑 删除节点</button></div>`;
  d.querySelectorAll('[data-go]').forEach(el => el.onclick = () => selectNode(el.dataset.go));
  d.querySelectorAll('[data-deledge]').forEach(el => el.onclick = e => { e.stopPropagation(); deleteEdge(el.dataset.deledge); });
  d.querySelector('[data-act="expand"]').onclick = () => expand(n.id, n.loaded || 0);
  d.querySelector('[data-act="edit"]').onclick = () => editNode(n.id);
  d.querySelector('[data-act="del"]').onclick = () => deleteNode(n.id);
  loadNodeContent(n.id, n.label);
}
/* 点节点 → 加载它关联的来源文件与切片（RAG 内容） */
async function loadNodeContent(id, label) {
  const box = $('nodeContent'); if (!box) return;
  try {
    const d = await API.getNodeContent(id, label);
    if (selected !== id) return;                       // 期间已切换节点
    const files = d.files || [];
    box.innerHTML = files.length ? files.map((f, fi) => `
      <div class="nc-file${fi === 0 ? ' open' : ''}">
        <div class="nc-fh"><span class="nc-ic">${f.type === 'PDF' ? '📕' : f.type === 'Word' ? '📘' : '📄'}</span><span class="nc-nm">${esc(f.name)}</span><span class="nc-ct">${f.chunks.length} 片</span><span class="nc-cv">▸</span></div>
        <div class="nc-chunks">${f.chunks.map(c => `<div class="nc-chunk"><div class="nc-ch-h"><span>切片 #${c.idx}</span><span class="nc-score">相似度 ${c.score}</span></div><div class="nc-ch-tx">${esc(c.text)}</div></div>`).join('')}</div>
      </div>`).join('') : '<div class="nc-tip">暂无关联文件</div>';
    box.querySelectorAll('.nc-fh').forEach(h => h.onclick = () => h.parentNode.classList.toggle('open'));
  } catch (e) { box.innerHTML = `<div class="nc-tip">内容加载失败：${esc(e.message)}</div>`; }
}

/* ============================================================
 * 按需子图：合入服务端节点/边 + 可见上限回收 + 双击展开邻居
 * ============================================================ */
function mergeNode(n, near) {
  if (byId(n.id)) return byId(n.id);
  const node = { id: n.id, label: n.label, type: n.type, deg: n.deg || 0,
    x: (near ? near.x : W / 2) + (Math.random() - .5) * 90, y: (near ? near.y : H / 2) + (Math.random() - .5) * 90, vx: 0, vy: 0, seq: addSeq++ };
  nodes.push(node); enforceCap(); return node;
}
function mergeEdge(e) {
  if (!e) return; const id = e.id || ('e_' + e.source + '_' + e.target);
  if (edges.some(x => x.id === id) || !byId(e.source) || !byId(e.target)) return;
  edges.push({ id, source: e.source, target: e.target, label: e.label || '关联' });
}
// 超过可见上限：回收“最旧且非当前选中/其邻居”的节点，保证 SVG 不卡
function enforceCap() {
  if (nodes.length <= CFG.MAX_NODES) return;
  const keep = new Set([selected]); edges.forEach(e => { if (e.source === selected) keep.add(e.target); if (e.target === selected) keep.add(e.source); });
  const removable = nodes.filter(n => !keep.has(n.id)).sort((a, b) => (a.seq || 0) - (b.seq || 0));
  const kill = new Set(removable.slice(0, nodes.length - CFG.MAX_NODES).map(n => n.id));
  if (!kill.size) return;
  nodes = nodes.filter(n => !kill.has(n.id));
  edges = edges.filter(e => !kill.has(e.source) && !kill.has(e.target));
}
async function expand(id, offset = 0) {
  const node = byId(id); if (!node) return;
  try {
    const res = await API.getNeighbors(id, offset, CFG.EXPAND_LIMIT);
    let added = 0;
    for (const n of res.nodes) { if (!byId(n.id)) added++; mergeNode(n, node); }
    for (const e of res.edges) mergeEdge(e);
    node.loaded = offset + res.nodes.length; node._total = res.total;
    render(); reheat(0.4); spawnPulse(node); if (selected === id) renderDetail();
    toast(added ? `展开 ${added} 个邻居` + (res.total > node.loaded ? `，还有 ${res.total - node.loaded} 个` : '') : '邻居已全部加载');
  } catch (e) { toast('展开失败：' + e.message); }
}

/* ============================================================
 * 增量操作（本地乐观更新 + 调用后端 + 记录可撤销）
 * ============================================================ */
function logChange(kind, html, inverse) {
  changeSeq++; history.push({ id: changeSeq, kind, html, inverse, undone: false, time: nowStr() });
  renderLog(); updateStats(); $('undoBtn').disabled = false;
}
function addNode(label, type, opt = {}) {
  label = (label || '').trim(); if (!label) { toast('请输入节点名称'); return null; }
  const id = opt.id || ('n' + Date.now().toString(36) + Math.floor(Math.random() * 99));
  const n = { id, label, type, x: opt.x ?? (W / 2 + (Math.random() - .5) * 80), y: opt.y ?? (H / 2 + (Math.random() - .5) * 80), vx: 0, vy: 0, seq: addSeq++ };
  nodes.push(n); enforceCap(); render(); reheat(0.5); spawnPulse(n);
  if (!opt.fromServer) API.createNode({ id, label, type }).catch(err => toast('后端写入失败：' + err.message));
  if (!opt.silent) logChange('add', `新增节点 <b>${esc(label)}</b> <span style="color:var(--ink-faint)">(${TYPES[type] ? TYPES[type].name : type})</span>`, { op: 'delNode', id });
  if (!opt.silent) toast('已新增节点：' + label);
  return n;
}
function addEdge(s, t, label, opt = {}) {
  if (!s || !t || s === t) { toast('请选择两个不同的节点'); return null; }
  const id = opt.id || ('e' + s + '_' + t + '_' + Math.floor(Math.random() * 999));
  if (edges.some(e => e.source === s && e.target === t && e.label === label)) { toast('该关系已存在'); return null; }
  const e = { id, source: s, target: t, label: (label || '关联').trim() };
  edges.push(e); render(); reheat(0.35);
  if (!opt.fromServer) API.createEdge({ ...e }).catch(err => toast('后端写入失败：' + err.message));
  if (!opt.silent) logChange('add', `新增关系 <b>${esc(byId(s).label)}</b> ─${esc(e.label)}→ <b>${esc(byId(t).label)}</b>`, { op: 'delEdge', id });
  if (!opt.silent) toast('已新增关系');
  return e;
}
function editNode(id) {
  const n = byId(id); if (!n) return;
  const nl = prompt('重命名节点：', n.label); if (nl === null) return;
  const tkey = prompt('类型（' + TKEYS.map(k => k + '=' + TYPES[k].name).join(' / ') + '）：', n.type);
  const old = { label: n.label, type: n.type };
  n.label = (nl || '').trim() || n.label; if (tkey && TYPES[tkey]) n.type = tkey;
  render(); renderDetail();
  API.updateNode(id, { label: n.label, type: n.type }).catch(err => toast('后端写入失败：' + err.message));
  logChange('edit', `修改节点 <b>${esc(old.label)}</b> → <b>${esc(n.label)}</b>`, { op: 'restoreNode', id, old });
  toast('已更新节点');
}
function deleteNode(id, opt = {}) {
  const n = byId(id); if (!n) return;
  if (!opt.silent && !confirm(`删除节点「${n.label}」及其所有关系？`)) return;
  const removedEdges = edges.filter(e => e.source === id || e.target === id).map(e => ({ ...e }));
  const removedNode = { ...n };
  edges = edges.filter(e => e.source !== id && e.target !== id); nodes = nodes.filter(x => x.id !== id);
  if (selected === id) { selected = null; renderDetail(); }
  render(); reheat(0.5);
  if (!opt.fromServer) API.deleteNode(id).catch(err => toast('后端写入失败：' + err.message));
  logChange('del', `删除节点 <b>${esc(n.label)}</b> <span style="color:var(--ink-faint)">(连带 ${removedEdges.length} 条关系)</span>`, { op: 'restoreNodeFull', node: removedNode, edges: removedEdges });
  if (!opt.silent) toast('已删除节点');
}
function deleteEdge(id) {
  const e = edges.find(x => x.id === id); if (!e) return;
  edges = edges.filter(x => x.id !== id); render(); reheat(0.4);
  API.deleteEdge(id).catch(err => toast('后端写入失败：' + err.message));
  logChange('del', `删除关系 <b>${esc(byId(e.source)?.label || '')}</b> ─${esc(e.label)}→ <b>${esc(byId(e.target)?.label || '')}</b>`, { op: 'restoreEdge', edge: { ...e } });
}
function spawnPulse(n) { const p = mk('circle', { class: 'pulse', cx: 0, cy: 0 }); const g = nodeLayer.querySelector(`[data-id="${n.id}"]`); if (g) { g.insertBefore(p, g.firstChild); setTimeout(() => p.remove(), 700); } }

/* ---- 撤销 ---- */
function undo() {
  for (let i = history.length - 1; i >= 0; i--) { if (!history[i].undone) { applyInverse(history[i].inverse); history[i].undone = true; break; } }
  renderLog(); updateStats(); if (!history.some(h => !h.undone)) $('undoBtn').disabled = true;
}
function applyInverse(inv) {
  if (!inv) return;
  switch (inv.op) {
    case 'delNode': nodes = nodes.filter(n => n.id !== inv.id); edges = edges.filter(e => e.source !== inv.id && e.target !== inv.id); if (selected === inv.id) { selected = null; renderDetail(); } API.deleteNode(inv.id).catch(() => {}); break;
    case 'delEdge': edges = edges.filter(e => e.id !== inv.id); API.deleteEdge(inv.id).catch(() => {}); break;
    case 'restoreNode': { const n = byId(inv.id); if (n) { n.label = inv.old.label; n.type = inv.old.type; } renderDetail(); API.updateNode(inv.id, { ...inv.old }).catch(() => {}); break; }
    case 'restoreEdge': if (!edges.some(e => e.id === inv.edge.id)) { edges.push({ ...inv.edge }); API.createEdge({ ...inv.edge }).catch(() => {}); } break;
    case 'restoreNodeFull':
      if (!byId(inv.node.id)) { nodes.push({ ...inv.node, vx: 0, vy: 0 }); API.createNode({ id: inv.node.id, label: inv.node.label, type: inv.node.type }).catch(() => {}); }
      inv.edges.forEach(e => { if (!edges.some(x => x.id === e.id)) { edges.push({ ...e }); API.createEdge({ ...e }).catch(() => {}); } }); break;
  }
  render(); reheat(0.6); toast('已撤销上一步');
}

/* ============================================================
 * 增量同步：从后端拉取 delta 并合并到当前图谱
 * ============================================================ */
async function syncDelta() {
  $('syncBtn').disabled = true;
  try {
    const d = await API.pullDelta(syncVersion);
    syncVersion = d.version || Date.now();
    let added = 0, removed = 0, updated = 0;
    (d.removed?.edgeIds || []).forEach(id => { if (edges.some(e => e.id === id)) { edges = edges.filter(e => e.id !== id); removed++; } });
    (d.removed?.nodeIds || []).forEach(id => { if (byId(id)) { edges = edges.filter(e => e.source !== id && e.target !== id); nodes = nodes.filter(n => n.id !== id); removed++; } });
    (d.added?.nodes || []).forEach(n => { if (!byId(n.id)) { addNode(n.label, n.type, { id: n.id, silent: true, fromServer: true }); added++; } });
    (d.added?.edges || []).forEach(e => { if (!edges.some(x => x.id === e.id)) { addEdge(e.source, e.target, e.label, { id: e.id, silent: true, fromServer: true }); added++; } });
    (d.updated?.nodes || []).forEach(u => { const n = byId(u.id); if (n) { n.label = u.label ?? n.label; n.type = u.type ?? n.type; updated++; } });
    render(); reheat(0.5); renderDetail();
    if (added || removed || updated) {
      logChange('sync', `增量同步：<b>+${added}</b> 新增 · <b>~${updated}</b> 变更 · <b>−${removed}</b> 删除`, null);
      toast(`已同步增量：+${added} / ~${updated} / −${removed}`);
    } else { toast('已是最新，无增量变更'); }
  } catch (err) { toast('同步失败：' + err.message); }
  $('syncBtn').disabled = false;
}

/* ============================================================
 * 面板 / 日志 / 过滤 / 统计
 * ============================================================ */
function renderLog() {
  const el = $('log'); const items = [...history].reverse();
  if (!items.length) { el.innerHTML = '<div class="log-empty">暂无变更。试试左侧的增量操作，<br>或点顶部「演示增量更新」。</div>'; return; }
  const sym = { add: '+', del: '−', edit: '~', sync: '⟳', undo: '↶' };
  el.innerHTML = items.map(h => `<div class="log-item ${h.undone ? 'undone' : ''}"><span class="lk ${h.kind}">${sym[h.kind] || '~'}</span><span class="log-tx">${h.html}</span><span class="log-tm">${h.time}</span></div>`).join('');
}
function renderLegend() {
  const counts = {}; TKEYS.forEach(k => counts[k] = 0); nodes.forEach(n => { if (counts[n.type] != null) counts[n.type]++; });
  $('legend').innerHTML = TKEYS.map(k => `<div class="lg ${hidden.has(k) ? 'off' : ''}" data-k="${k}"><span class="dot" style="background:${TYPES[k].color}"></span>${TYPES[k].name}<span class="c">${counts[k]}</span></div>`).join('');
  $('legend').querySelectorAll('.lg').forEach(el => el.onclick = () => { const k = el.dataset.k; hidden.has(k) ? hidden.delete(k) : hidden.add(k); renderLegend(); applyFilterDim(); });
  $('legendTotal').textContent = nodes.length + ' 节点';
}
function applyFilterDim() {
  [...nodeLayer.children].forEach(g => { const n = byId(g.dataset.id); g.style.display = (n && hidden.has(n.type)) ? 'none' : ''; });
  [...edgeLayer.children].forEach(g => { const e = edges.find(x => x.id === g.dataset.id); const hide = e && (hidden.has(byId(e.source)?.type) || hidden.has(byId(e.target)?.type)); g.style.display = hide ? 'none' : ''; });
}
function refreshEdgeSelects() {
  const opts = '<option value="">选择节点…</option>' + nodes.map(n => `<option value="${n.id}">${esc(n.label)}</option>`).join('');
  const f = $('eFrom'), t = $('eTo'), fv = f.value, tv = t.value; f.innerHTML = opts; t.innerHTML = opts; f.value = fv; t.value = tv;
}
function updateStats() { $('stNodes').textContent = nodes.length; $('stEdges').textContent = edges.length; $('stChanges').textContent = history.filter(h => !h.undone).length; renderLegend(); }

/* ---- 搜索（命中百万级后端，自动加载该节点的局部网络）---- */
let searchT;
$('search').addEventListener('input', e => {
  clearTimeout(searchT); const q = e.target.value.trim();
  [...nodeLayer.children].forEach(g => { const n = byId(g.dataset.id); const on = !q || (n && n.label.toLowerCase().includes(q.toLowerCase())); g.classList.toggle('dim', !on && !!q); });
  if (!q) return;
  searchT = setTimeout(async () => {
    try {
      const r = await API.search(q, 8); if (!r.nodes.length) { toast('后端无匹配节点'); return; }
      const top = r.nodes[0];
      if (!byId(top.id)) { const ego = await API.getNeighbors(top.id, 0, CFG.EXPAND_LIMIT); const s = mergeNode(top); for (const n of ego.nodes) mergeNode(n, s); for (const e2 of ego.edges) mergeEdge(e2); s._total = ego.total; s.loaded = ego.nodes.length; render(); reheat(0.45); }
      selectNode(top.id); const hit = byId(top.id); if (hit) { T.k = Math.max(T.k, 1); T.x = W / 2 - hit.x * T.k; T.y = H / 2 - hit.y * T.k; applyTransform(); }
    } catch (err) { toast('搜索失败：' + err.message); }
  }, 300);
});

/* ---- 类型选择器 ---- */
function renderTypePick() {
  $('typePick').innerHTML = TKEYS.map(k => `<span class="tp ${k === curType ? 'on' : ''}" data-k="${k}" style="color:${TYPES[k].color}"><span class="dot" style="background:${TYPES[k].color}"></span>${TYPES[k].name}</span>`).join('');
  $('typePick').querySelectorAll('.tp').forEach(el => el.onclick = () => { curType = el.dataset.k; renderTypePick(); });
}

/* ---- 按钮 ---- */
$('addNodeBtn').onclick = () => { const n = addNode($('nName').value, curType); if (n) $('nName').value = ''; };
$('nName').addEventListener('keydown', e => { if (e.key === 'Enter') $('addNodeBtn').click(); });
$('addEdgeBtn').onclick = () => { const e = addEdge($('eFrom').value, $('eTo').value, $('eLabel').value); if (e) $('eLabel').value = ''; };
$('undoBtn').onclick = undo;
$('syncBtn').onclick = syncDelta;
$('resetBtn').onclick = () => { if (confirm('重置为初始图谱？所有本地变更将清空。')) boot(); };
$('exportBtn').onclick = () => {
  const data = JSON.stringify({ nodes: nodes.map(({ id, label, type, x, y }) => ({ id, label, type, x, y })), edges: edges.map(({ id, source, target, label }) => ({ id, source, target, label })) }, null, 2);
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([data], { type: 'application/json' })); a.download = 'knowledge-graph.json'; a.click(); toast('已导出 JSON');
};
$('importBtn').onclick = () => $('importFile').click();
$('importFile').onchange = e => { const f = e.target.files[0]; if (!f) return; const rd = new FileReader(); rd.onload = () => { try { loadData(JSON.parse(rd.result)); toast('已导入图谱'); } catch (err) { toast('导入失败：JSON 格式错误'); } }; rd.readAsText(f); e.target.value = ''; };

/* ---- 演示增量更新 ---- */
let playing = false;
$('playBtn').onclick = async () => {
  if (playing) return; playing = true; $('playingTag').classList.add('show'); $('playBtn').disabled = true;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const n1 = addNode('航意险', 'product'); await wait(900);
  const n2 = addNode('航班延误风险', 'risk'); await wait(900);
  if (n1 && n2) { addEdge(n1.id, n2.id, '承保'); await wait(900); }
  if (n1) { selectNode(n1.id); await wait(700); const old = { label: n1.label, type: n1.type }; n1.label = '航空意外险'; render(); renderDetail();
    API.updateNode(n1.id, { label: n1.label, type: n1.type }).catch(() => {});
    logChange('edit', '修改节点 <b>航意险</b> → <b>航空意外险</b>', { op: 'restoreNode', id: n1.id, old }); await wait(900); }
  if (n2) { await wait(300); deleteNode(n2.id, { silent: true }); await wait(400); }
  $('playingTag').classList.remove('show'); $('playBtn').disabled = false; playing = false; toast('演示完成，可点右侧「撤销」逐步回退');
};

/* ---- 工具 ---- */
function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function nowStr() { const d = new Date(); const p = x => String(x).padStart(2, '0'); return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; }
let toastT; function toast(m) { const t = $('toast'); t.textContent = m; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2200); }

/* ---- 载入数据 ---- */
function loadData(d) {
  nodes = (d.nodes || []).map(n => ({ ...n, x: n.x ?? W / 2 + (Math.random() - .5) * 300, y: n.y ?? H / 2 + (Math.random() - .5) * 300, vx: 0, vy: 0, seq: addSeq++ }));
  edges = (d.edges || []).map(e => ({ ...e, id: e.id || ('e_' + e.source + '_' + e.target) }));
  selected = null; history = []; changeSeq = 0; syncVersion = d.version || 0; hidden.clear();
  render(); renderDetail(); renderLog(); reheat(0.6); $('undoBtn').disabled = true;
}
async function boot() {
  resize();
  nodes = []; edges = []; selected = null; history = []; changeSeq = 0; hidden.clear(); addSeq = 0;
  nodeLayer.innerHTML = ''; edgeLayer.innerHTML = '';
  try {
    const st = await API.getStats(); if ($('stDocTotal')) $('stDocTotal').textContent = st.docTotal.toLocaleString();
    const seed = await API.getSeed(42);
    for (const n of seed.nodes) mergeNode(n);
    for (const e of seed.edges) mergeEdge(e);
    toast('已加载种子子图，双击节点展开、单击看切片');
  } catch (err) { toast('加载失败：' + err.message); }
  // 初始放射状布点
  nodes.forEach((n, i) => { const a = i / Math.max(1, nodes.length) * Math.PI * 2; n.x = W / 2 + Math.cos(a) * Math.min(W, H) * 0.3; n.y = H / 2 + Math.sin(a) * Math.min(W, H) * 0.3; });
  render(); renderDetail(); renderLog(); reheat(0.6); $('undoBtn').disabled = true;
}
function resize() { const r = svg.getBoundingClientRect(); W = r.width || 800; H = r.height || 600; }
new ResizeObserver(() => { resize(); reheat(0.3); }).observe(svg);

renderTypePick(); boot(); requestAnimationFrame(tick);
