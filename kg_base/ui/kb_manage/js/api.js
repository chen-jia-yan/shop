/* =====================================================================
 * api.js — 知识库管理 · 后端接口层（唯一需要对接后端的文件）
 * ---------------------------------------------------------------------
 * 对接后端：
 *   1. 把 API.BASE 改成你的后端地址，例如 'https://your-host/api'
 *   2. 把 API.MOCK 改成 false
 *   3. 可选：删除下方 MOCK 演示数据
 * app.js 无需改动。所有方法返回 Promise。
 *
 * 建议后端实现的接口：
 *   GET    /kbs                        -> 知识库列表 [{id,name,desc,docs,chunks,status,ico,color,model,dim,chunk,ov,frag,upd}]
 *   GET    /kbs/:id/docs               -> 文档列表   [{n,t,size,chunks,st,upd}]
 *   POST   /kbs                        -> 新建知识库 body:{name,desc,model,dim}            -> {ok,id}
 *   POST   /kbs/:id/docs               -> 上传文档   body:{name,chunkSize,overlap,index}   -> {ok}
 *          （若要直传文件，见 README：改成 FormData + multipart）
 *   POST   /kbs/:id/docs/delete        -> 删除文档   body:{names:[...]}                     -> {ok}
 *   POST   /kbs/:id/reindex            -> 重建索引                                          -> {ok}
 *
 *   文档状态 st 取值：ok=已索引 / idx=索引中 / wait=待处理 / err=失败
 * ===================================================================== */

const API = {
  BASE: '/api',   // TODO: 改成你的后端地址
  MOCK: true,     // TODO: 对接后端时改成 false
  TOKEN: '',      // 可选 Bearer Token

  _headers() { const h = { 'Content-Type': 'application/json' }; if (this.TOKEN) h. Authorization = 'Bearer ' + this.TOKEN; return h; },
  async _get(p) { const r = await fetch(this.BASE + p, { headers: this._headers() }); if (!r.ok) throw new Error('GET ' + p + ' -> ' + r.status); return r.json(); },
  async _post(p, b) { const r = await fetch(this.BASE + p, { method: 'POST', headers: this._headers(), body: JSON.stringify(b) }); if (!r.ok) throw new Error('POST ' + p + ' -> ' + r.status); return r.json(); },

  listKbs()             { return this.MOCK ? Promise.resolve(MOCK.kbs.map(k => ({ ...k }))) : this._get('/kbs'); },
  getKbDocs(id)         { return this.MOCK ? Promise.resolve((MOCK.docs[id] || []).map(d => ({ ...d }))) : this._get(`/kbs/${id}/docs`); },
  createKb(p)           { return this.MOCK ? Promise.resolve({ ok: true, id: 'kb_' + Date.now().toString(36) }) : this._post('/kbs', p); },
  uploadDoc(id, p)      { return this.MOCK ? Promise.resolve({ ok: true }) : this._post(`/kbs/${id}/docs`, p); },
  deleteDocs(id, names) { return this.MOCK ? Promise.resolve({ ok: true }) : this._post(`/kbs/${id}/docs/delete`, { names }); },
  reindex(id)           { return this.MOCK ? Promise.resolve({ ok: true }) : this._post(`/kbs/${id}/reindex`, {}); },
};

/* ===================================================================== *
 *  以下为 MOCK（演示）数据，对接后端后可整段删除。
 * ===================================================================== */
const MOCK = {
  kbs: [
    { id: 'prod', name: '产品知识库', desc: '产品手册 · 功能说明 · 版本说明', docs: 1280, chunks: 168000, status: 'ok', ico: '📘', color: '#2d7ff0', model: 'bge-large-zh-v1.5', dim: 1024, chunk: 512, ov: 64, frag: 3.2, upd: '2026-10-13 10:20' },
    { id: 'tech', name: '技术文档库', desc: 'API · 架构 · 运维手册', docs: 960, chunks: 142000, status: 'idx', ico: '⚙', color: '#7a5bd6', model: 'text-embedding-3-large', dim: 1536, chunk: 1024, ov: 128, frag: 6.8, upd: '2026-10-13 09:05' },
    { id: 'hr', name: 'HR 制度库', desc: '规章制度 · 福利 · 流程', docs: 742, chunks: 98000, status: 'ok', ico: '👤', color: '#1aa3a3', model: 'bge-large-zh-v1.5', dim: 1024, chunk: 512, ov: 64, frag: 2.1, upd: '2026-10-12 18:40' },
    { id: 'faq', name: '客服 FAQ 库', desc: '常见问题 · 话术 · 理赔指南', docs: 860, chunks: 78000, status: 'ok', ico: '💬', color: '#d4a235', model: 'm3e-base', dim: 768, chunk: 256, ov: 32, frag: 4.5, upd: '2026-10-13 11:12' },
  ],
  docs: {
    prod: [
      { n: '产品白皮书_v2.4.pdf', t: 'PDF', size: '8.2 MB', chunks: 420, st: 'ok', upd: '2026-10-13 10:20' },
      { n: '功能说明_核保模块.docx', t: 'Word', size: '1.9 MB', chunks: 112, st: 'ok', upd: '2026-10-12 16:30' },
      { n: '版本发布说明_2026Q4.md', t: 'Markdown', size: '86 KB', chunks: 34, st: 'idx', upd: '2026-10-13 10:18' },
      { n: '定价规则手册.pdf', t: 'PDF', size: '4.1 MB', chunks: 208, st: 'ok', upd: '2026-10-11 14:00' },
      { n: '产品FAQ导出.html', t: '网页', size: '320 KB', chunks: 76, st: 'wait', upd: '2026-10-13 11:00' },
      { n: '旧版手册_v1.8.pdf', t: 'PDF', size: '7.0 MB', chunks: 0, st: 'err', upd: '2026-10-10 09:30' },
    ],
    tech: [
      { n: 'OpenAPI_规范.yaml', t: 'Markdown', size: '210 KB', chunks: 95, st: 'ok', upd: '2026-10-13 09:05' },
      { n: '系统架构设计.pdf', t: 'PDF', size: '5.6 MB', chunks: 260, st: 'idx', upd: '2026-10-13 09:00' },
      { n: '运维手册.docx', t: 'Word', size: '2.2 MB', chunks: 140, st: 'ok', upd: '2026-10-12 20:10' },
    ],
    hr: [
      { n: '员工手册_2026.pdf', t: 'PDF', size: '3.3 MB', chunks: 180, st: 'ok', upd: '2026-10-12 18:40' },
      { n: '考勤与休假制度.docx', t: 'Word', size: '640 KB', chunks: 48, st: 'ok', upd: '2026-10-11 10:00' },
    ],
    faq: [
      { n: '理赔常见问题.md', t: 'Markdown', size: '120 KB', chunks: 66, st: 'ok', upd: '2026-10-13 11:12' },
      { n: '客服话术库.xlsx', t: 'Word', size: '890 KB', chunks: 220, st: 'ok', upd: '2026-10-12 15:20' },
      { n: '投诉处理指南.pdf', t: 'PDF', size: '2.0 MB', chunks: 90, st: 'wait', upd: '2026-10-13 08:30' },
    ],
  },
};
