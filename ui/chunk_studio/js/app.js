/* ============================================================
 * app.js — 文档切片预览（只依赖 api.js，对接后端无需改动）
 * 核心修复：切片配置「调整」按钮现在会打开可编辑弹窗，
 * 修改分块大小 / 重叠 / 切分策略后即时重新切片。
 * ============================================================ */
const $ = id => document.getElementById(id);
function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
let toastT; function toast(m) { const t = $('toast'); t.textContent = m; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2200); }
function openModal(id) { $(id).classList.add('show'); }
function closeModal(id) { $(id).classList.remove('show'); }

let KBS = [];
const DOCS = {};
// 当前切片配置（打开某库时用其默认值初始化，可在弹窗里改）
let cfg = { chunk: 512, ov: 64, strategy: '递归字符 + 语义边界' };

/* ---- 选择器 ---- */
async function initKbSelect() {
  KBS = await API.listKbs();
  $('slKb').innerHTML = KBS.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('');
  await onKbChange();
}
async function onKbChange() {
  const kb = curKb();
  cfg = { chunk: kb.chunk, ov: kb.ov, strategy: '递归字符 + 语义边界' };
  if (!DOCS[kb.id]) DOCS[kb.id] = await API.getKbDocs(kb.id);
  const docs = (DOCS[kb.id] || []).filter(d => d.chunks > 0);
  $('slDoc').innerHTML = (docs.length ? docs : (DOCS[kb.id] || [])).map(d => `<option>${esc(d.n)}</option>`).join('') || '<option>（无文档）</option>';
  await renderSlice();
}
const curKb = () => KBS.find(k => k.id === $('slKb').value) || KBS[0];

/* ---- 渲染切片 ---- */
async function renderSlice() {
  const kb = curKb(); const docName = $('slDoc').value || '（未选择）';
  const s = await API.getSlice(kb.id, docName, cfg);
  const segs = s.segments || [];
  const base = s.baseTokens || 4096;
  const count = s.count || Math.max(1, Math.round(base / cfg.chunk)); // 分块越小，切片越多
  $('slMini').innerHTML = `
    <div class="mini"><div class="ml">切片数</div><div class="mv">${count}</div></div>
    <div class="mini"><div class="ml">分块大小</div><div class="mv">${cfg.chunk}</div></div>
    <div class="mini"><div class="ml">重叠 overlap</div><div class="mv">${cfg.ov}</div></div>
    <div class="mini"><div class="ml">Embedding</div><div class="mv" style="font-size:12px">${esc(kb.model)}</div></div>`;
  $('slCfg').innerHTML = `
    <div class="cfg-row"><span class="k">切分策略</span><span class="v">${esc(cfg.strategy)}</span></div>
    <div class="cfg-row"><span class="k">分块大小 / 重叠</span><span class="v">${cfg.chunk} / ${cfg.ov} tokens</span></div>
    <div class="cfg-row"><span class="k">当前文档</span><span class="v">${esc(docName)}</span></div>
    <div class="cfg-row"><span class="k">预计切片数</span><span class="v">${count}</span></div>`;
  $('slCount').textContent = count;
  // 重叠占比（overlap / chunk）决定重叠高亮区的视觉长度
  const ovRatio = Math.min(0.9, cfg.ov / cfg.chunk);
  let html = '';
  for (let i = 0; i < count; i++) {
    const baseTxt = segs.length ? segs[i % segs.length] : '（无内容）';
    const ovLen = i > 0 && segs.length ? Math.max(8, Math.round(segs[(i - 1) % segs.length].length * ovRatio)) : 0;
    const prevTail = ovLen ? ('<span class="ov">' + esc(segs[(i - 1) % segs.length].slice(-ovLen)) + '</span> ') : '';
    const tok = Math.round(cfg.chunk * (0.82 + Math.random() * 0.3));
    html += `<div class="slice-chunk"><div class="sc-h"><span class="sc-i">#${i + 1}</span>
      <span>${esc(docName)} · 第 ${i + 1} 块</span><span class="sc-tok">${tok} tokens</span></div>
      <div class="sc-txt">${prevTail}${esc(baseTxt)}</div></div>`;
  }
  $('sliceList').innerHTML = html;
}

/* ---- 切片配置弹窗（修复：真正可打开 + 生效）---- */
function openSliceCfg() {
  $('cfgChunk').value = String(cfg.chunk);
  $('cfgOverlap').value = cfg.ov; $('cfgOvVal').textContent = cfg.ov;
  $('cfgStrategy').value = cfg.strategy;
  openModal('cfgMask');
}
function saveSliceCfg() {
  const chunk = +$('cfgChunk').value;
  const ov = +$('cfgOverlap').value;
  if (ov >= chunk) { toast('重叠需小于分块大小'); return; }
  cfg = { chunk, ov, strategy: $('cfgStrategy').value };
  closeModal('cfgMask'); renderSlice(); toast('已按新参数重新切片');
}

/* ---- 事件 ---- */
$('slKb').onchange = onKbChange;
$('slDoc').onchange = renderSlice;
$('resliceBtn').onclick = () => { renderSlice(); toast('已重新切片'); };
$('cfgBtn').onclick = openSliceCfg;
$('cfgSaveBtn').onclick = saveSliceCfg;
$('cfgOverlap').oninput = e => $('cfgOvVal').textContent = e.target.value;
document.querySelectorAll('[data-close]').forEach(el => el.onclick = () => closeModal(el.dataset.close));

/* ---- 初始化 ---- */
async function init() {
  try { await initKbSelect(); }
  catch (err) { toast('加载失败：' + err.message); }
}
init();
