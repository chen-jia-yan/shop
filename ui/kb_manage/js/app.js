/* ============================================================
 * app.js — 知识库管理（列表 → 详情 → 文档管理 / 上传 / 配置）
 * 只依赖 api.js；对接后端无需改动本文件。
 * ============================================================ */
const $ = id => document.getElementById(id);
function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
let toastT; function toast(m) { const t = $('toast'); t.textContent = m; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2200); }
function openModal(id) { $(id).classList.add('show'); }
function closeModal(id) { $(id).classList.remove('show'); }

const stPill = { ok: '<span class="pill p-ok"><span class="d"></span>已索引</span>', idx: '<span class="pill p-idx"><span class="d"></span>索引中</span>', wait: '<span class="pill p-wait"><span class="d"></span>待处理</span>', err: '<span class="pill p-err"><span class="d"></span>失败</span>' };
const stName = { ok: '已索引', idx: '索引中', wait: '待处理', err: '失败' };
function guessType(name) { const e = (name.split('.').pop() || '').toLowerCase(); return ({ pdf: 'PDF', doc: 'Word', docx: 'Word', xls: 'Word', xlsx: 'Word', md: 'Markdown', markdown: 'Markdown', txt: 'Markdown', html: '网页', htm: '网页' })[e] || 'PDF'; }

/* 缓存 */
let KBS = [];
const DOCS = {};              // id -> 文档数组（引用缓存）
let curKb = null, curDocs = [];

/* ================= 路由 ================= */
function go(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('show'));
  $('view-' + view).classList.add('show');
  $('content').scrollTop = 0;
  if (view === 'list') $('crumb').innerHTML = '<b>知识库管理</b>';
  else $('crumb').innerHTML = `<span>知识库管理</span><span class="sep">/</span><b>${esc(curKb ? curKb.name : '')}</b>`;
}

/* ================= 列表 ================= */
function renderKbGrid() {
  $('kbGrid').innerHTML = KBS.map(k => `
    <div class="kb-card" data-kb="${k.id}">
      <div class="kc-top"><div class="kc-ico" style="background:${k.color}">${k.ico}</div>
        <div><h4>${esc(k.name)}</h4><div class="kc-desc">${esc(k.desc)}</div></div></div>
      <div style="display:flex;gap:7px;align-items:center">${k.status === 'idx' ? '<span class="pill p-idx"><span class="d"></span>索引中</span>' : '<span class="pill p-ok"><span class="d"></span>就绪</span>'}
        <span class="ft">${esc(k.model)}</span></div>
      <div class="kc-stats"><div><b>${k.docs.toLocaleString()}</b>文档</div><div><b>${(k.chunks / 1000).toFixed(0)}K</b>向量块</div><div><b style="color:${k.frag < 4 ? 'var(--green)' : k.frag < 6 ? 'var(--amber)' : 'var(--red)'}">${k.frag}%</b>碎片率</div></div>
    </div>`).join('')
    + `<div class="kb-card" data-new="1" style="display:flex;align-items:center;justify-content:center;border-style:dashed;color:var(--navy)"><div style="text-align:center"><div style="font-size:26px">＋</div><div style="font-weight:600;margin-top:4px">新建知识库</div></div></div>`;
  $('kbCount').textContent = KBS.length + ' 个库';
}

/* ================= 详情 ================= */
async function openKb(id) {
  curKb = KBS.find(k => k.id === id);
  if (!DOCS[id]) DOCS[id] = await API.getKbDocs(id);
  curDocs = DOCS[id];
  $('kbMini').innerHTML = `
    <div class="mini"><div class="ml">文档数</div><div class="mv">${curKb.docs.toLocaleString()}</div></div>
    <div class="mini"><div class="ml">向量块</div><div class="mv">${(curKb.chunks / 1000).toFixed(0)}K</div></div>
    <div class="mini"><div class="ml">碎片率</div><div class="mv" style="color:${curKb.frag < 4 ? 'var(--green)' : curKb.frag < 6 ? 'var(--amber)' : 'var(--red)'}">${curKb.frag}%</div></div>
    <div class="mini"><div class="ml">最近更新</div><div class="mv" style="font-size:13px">${curKb.upd.split(' ')[0]}</div></div>`;
  $('chunkCfg').innerHTML = `
    <div class="cfg-row"><span class="k">Embedding 模型</span><span class="v">${esc(curKb.model)}</span></div>
    <div class="cfg-row"><span class="k">向量维度</span><span class="v">${curKb.dim}</span></div>
    <div class="cfg-row"><span class="k">分块大小</span><span class="v">${curKb.chunk} tokens</span></div>
    <div class="cfg-row"><span class="k">重叠 overlap</span><span class="v">${curKb.ov} tokens</span></div>
    <div class="cfg-row"><span class="k">切分策略</span><span class="v">递归字符 + 语义边界</span></div>`;
  $('idxHealth').innerHTML = `
    <div class="cfg-row"><span class="k">索引状态</span><span class="v">${curKb.status === 'idx' ? '<span style="color:var(--blue)">索引中 68%</span>' : '<span style="color:var(--green)">就绪</span>'}</span></div>
    <div class="cfg-row"><span class="k">碎片率</span><span class="v" style="color:${curKb.frag < 4 ? 'var(--green)' : 'var(--amber)'}">${curKb.frag}%</span></div>
    <div class="cfg-row"><span class="k">上次重建</span><span class="v">${curKb.upd}</span></div>
    <div style="display:flex;gap:8px;margin-top:12px"><button class="btn sm" data-act="rebuild">⟳ 重建索引</button>
      <button class="btn sm" data-act="defrag">🧹 碎片整理</button>
      <button class="btn sm danger" data-act="clear">清空重建</button></div>`;
  $('filterRules').innerHTML = `
    <div class="cfg-row"><span class="k">去重策略</span><span class="v">内容哈希（MD5）精确去重</span></div>
    <div class="cfg-row"><span class="k">空白/低质过滤</span><span class="v">文本密度 &lt; 阈值自动剔除</span></div>
    <div class="cfg-row"><span class="k">格式白名单</span><span class="v">PDF / Word / MD / TXT / HTML</span></div>
    <div class="cfg-row"><span class="k">敏感信息脱敏</span><span class="v" style="color:var(--green)">已开启（身份证/银行卡）</span></div>
    <div class="cfg-row"><span class="k">单文件大小上限</span><span class="v">80 MB</span></div>`;
  const klog = [['11:12', '新增文档 理赔常见问题.md 并索引完成'], ['10:20', '重建索引完成'], ['09:40', '删除 2 个重复文档'], ['昨日', '上传 15 个文档，过滤 2 个重复']];
  $('kbLog').innerHTML = klog.map(l => `<div style="display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--line-soft);font-size:12.5px"><span class="mono" style="color:var(--ink-faint);font-size:11px">${l[0]}</span><span>${l[1]}</span></div>`).join('');
  $('docSearch').value = ''; $('docTypeFilter').value = ''; $('docStatusFilter').value = '';
  renderDocs(curDocs);
  go('detail');
}
function renderDocs(list) {
  $('docRows').innerHTML = list.map(d => `<tr data-name="${esc(d.n)}">
    <td class="checkcol"><input type="checkbox" class="docchk"></td>
    <td class="fname">${esc(d.n)} <span class="ft">${d.t}</span></td>
    <td class="num">${d.size}</td><td class="num">${d.chunks || '—'}</td>
    <td>${stPill[d.st] || d.st}</td>
    <td class="mono" style="font-size:11px;color:var(--ink-soft)">${d.upd}</td>
    <td><div class="rowact">
      <span class="ia" data-act="view" title="查看">👁</span>
      <span class="ia" data-act="reindex" title="重新索引">⟳</span>
      <span class="ia del" data-act="del" title="删除">🗑</span>
    </div></td></tr>`).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--ink-faint);padding:24px">暂无文档</td></tr>';
  $('docCap').textContent = `共 ${list.length} 个文档`;
  $('checkAll').checked = false;
}
function filterDocs() {
  const kw = $('docSearch').value.trim().toLowerCase();
  const ty = $('docTypeFilter').value, st = $('docStatusFilter').value;
  renderDocs(curDocs.filter(d => (!kw || d.n.toLowerCase().includes(kw)) && (!ty || d.t === ty) && (!st || stName[d.st] === st)));
}
function toggleAll(cb) { document.querySelectorAll('.docchk').forEach(c => c.checked = cb.checked); }
function batchDelete() {
  const rows = [...document.querySelectorAll('#docRows tr')].filter(tr => tr.querySelector('.docchk')?.checked);
  if (!rows.length) { toast('请先勾选要删除的文档'); return; }
  const names = rows.map(tr => tr.dataset.name);
  if (!confirm(`确认删除选中的 ${names.length} 个文档及其向量？`)) return;
  API.deleteDocs(curKb.id, names).catch(err => toast('后端删除失败：' + err.message));
  const set = new Set(names);
  DOCS[curKb.id] = curDocs = curDocs.filter(d => !set.has(d.n));
  curKb.docs = Math.max(0, curKb.docs - names.length);
  filterDocs(); toast(`已删除 ${names.length} 个文档并移除对应向量`);
}
function delDoc(name) {
  const d = curDocs.find(x => x.n === name); if (!d) return;
  if (!confirm(`删除文档「${name}」？`)) return;
  API.deleteDocs(curKb.id, [name]).catch(err => toast('后端删除失败：' + err.message));
  DOCS[curKb.id] = curDocs = curDocs.filter(x => x.n !== name);
  curKb.docs = Math.max(0, curKb.docs - 1);
  filterDocs(); toast('已删除：' + name);
}
function rebuildIndex() { if (curKb) API.reindex(curKb.id).catch(err => toast('后端失败：' + err.message)); toast('已提交重建索引任务，预计 2 分钟'); }
function openUpload() { if (curKb) $('upKb').value = curKb.id; openModal('uploadMask'); }
function doUpload() {
  const kbId = $('upKb').value || (curKb && curKb.id); if (!kbId) { toast('请选择目标知识库'); return; }
  const file = $('upFile').files[0];
  const name = file ? file.name : '新上传文档.pdf';
  const chunkSize = +$('upChunk').value, overlap = +$('upOverlap').value, index = $('upIndexNow').checked;
  API.uploadDoc(kbId, { name, chunkSize, overlap, index }).catch(err => toast('后端上传失败：' + err.message));
  const doc = { n: name, t: guessType(name), size: file ? (file.size / 1048576).toFixed(1) + ' MB' : '—', chunks: 0, st: index ? 'idx' : 'wait', upd: '刚刚' };
  (DOCS[kbId] = DOCS[kbId] || []).unshift(doc);
  const kb = KBS.find(k => k.id === kbId); if (kb) kb.docs++;
  if (curKb && curKb.id === kbId) { curDocs = DOCS[kbId]; filterDocs(); }
  $('upFile').value = ''; $('upName').textContent = '点击选择或拖拽文件';
  closeModal('uploadMask'); toast('文件已上传，正在建立索引');
}
async function doNewKb() {
  const name = $('nkName').value.trim(); if (!name) { toast('请填写知识库名称'); return; }
  const model = $('nkModel').value, dim = +$('nkDim').value, desc = $('nkDesc').value.trim();
  const res = await API.createKb({ name, desc, model, dim }).catch(err => { toast('后端创建失败：' + err.message); return null; });
  const id = (res && res.id) || ('kb_' + Date.now().toString(36));
  KBS.push({ id, name, desc: desc || '新建知识库', docs: 0, chunks: 0, status: 'ok', ico: '📁', color: '#1f5aa6', model, dim, chunk: 512, ov: 64, frag: 0, upd: new Date().toISOString().slice(0, 16).replace('T', ' ') });
  DOCS[id] = [];
  $('nkName').value = ''; $('nkDesc').value = '';
  refreshUpKb(); renderKbGrid(); closeModal('newKbMask'); toast(`已创建知识库「${name}」`);
}
function refreshUpKb() { $('upKb').innerHTML = KBS.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join(''); }

/* ================= 事件绑定 ================= */
$('kbGrid').addEventListener('click', e => {
  const card = e.target.closest('[data-kb]'); if (card) { openKb(card.dataset.kb); return; }
  if (e.target.closest('[data-new]')) openModal('newKbMask');
});
$('docRows').addEventListener('click', e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const name = b.closest('tr').dataset.name;
  if (b.dataset.act === 'del') delDoc(name);
  else if (b.dataset.act === 'view') toast('打开文档预览（演示）');
  else if (b.dataset.act === 'reindex') toast('已重新索引：' + name);
});
$('view-detail').addEventListener('click', e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  if (b.dataset.act === 'rebuild') rebuildIndex();
  else if (b.dataset.act === 'defrag') toast('已触发碎片整理（演示）');
  else if (b.dataset.act === 'clear') { if (confirm('确认清空并重建该库索引？')) rebuildIndex(); }
});
$('backBtn').onclick = () => go('list');
$('newKbTop').onclick = () => openModal('newKbMask');
$('uploadBtn').onclick = openUpload;
$('batchDelBtn').onclick = batchDelete;
$('rebuildBtn').onclick = rebuildIndex;
$('checkAll').onchange = function () { toggleAll(this); };
$('docSearch').oninput = filterDocs;
$('docTypeFilter').onchange = filterDocs;
$('docStatusFilter').onchange = filterDocs;
$('upFile').onchange = function () { $('upName').textContent = this.files[0] ? ('📄 ' + this.files[0].name) : '点击选择或拖拽文件'; };
document.querySelectorAll('[data-close]').forEach(el => el.onclick = () => closeModal(el.dataset.close));
$('doUploadBtn').onclick = doUpload;
$('doNewKbBtn').onclick = doNewKb;

/* ================= 初始化 ================= */
async function init() {
  try { KBS = await API.listKbs(); }
  catch (err) { toast('加载知识库失败：' + err.message); KBS = []; }
  renderKbGrid(); refreshUpKb(); go('list');
}
init();
