/* =====================================================================
 * api.js — 文档切片 · 后端接口层（唯一需要对接后端的文件）
 * ---------------------------------------------------------------------
 * 对接后端：
 *   1. 把 API.BASE 改成你的后端地址，例如 'https://your-host/api'
 *   2. 把 API.MOCK 改成 false
 *   3. 可选：删除下方 MOCK 演示数据
 * app.js 无需改动。所有方法返回 Promise。
 *
 * 建议后端实现的接口：
 *   GET  /kbs                                   -> 知识库列表 [{id,name,model,chunk,ov}]
 *   GET  /kbs/:id/docs                          -> 文档列表   [{n,t,chunks}]
 *   GET  /kbs/:id/slice?doc=&chunk=&overlap=&strategy=
 *        -> 切片预览：{ count?, baseTokens?, segments:[文本...] }
 *           · 若后端直接返回 count，则前端用它；否则按 baseTokens/chunk 估算
 *   POST /kbs/:id/reslice   body:{doc,chunk,overlap,strategy}
 *        -> 按新参数重新切片：返回同 slice 结构
 * ===================================================================== */

const API = {
  BASE: '/api',   // TODO: 改成你的后端地址
  MOCK: true,     // TODO: 对接后端时改成 false
  TOKEN: '',      // 可选 Bearer Token

  _headers() { const h = { 'Content-Type': 'application/json' }; if (this.TOKEN) h.Authorization = 'Bearer ' + this.TOKEN; return h; },
  async _get(p) { const r = await fetch(this.BASE + p, { headers: this._headers() }); if (!r.ok) throw new Error('GET ' + p + ' -> ' + r.status); return r.json(); },
  async _post(p, b) { const r = await fetch(this.BASE + p, { method: 'POST', headers: this._headers(), body: JSON.stringify(b) }); if (!r.ok) throw new Error('POST ' + p + ' -> ' + r.status); return r.json(); },

  listKbs()         { return this.MOCK ? Promise.resolve(MOCK.kbs.map(k => ({ ...k }))) : this._get('/kbs'); },
  getKbDocs(id)     { return this.MOCK ? Promise.resolve((MOCK.docs[id] || []).map(d => ({ ...d }))) : this._get(`/kbs/${id}/docs`); },
  getSlice(id, doc, o = {}) {
    if (this.MOCK) return Promise.resolve({ ...MOCK.slice });
    const q = `?doc=${encodeURIComponent(doc)}&chunk=${o.chunk || ''}&overlap=${o.overlap || ''}&strategy=${encodeURIComponent(o.strategy || '')}`;
    return this._get(`/kbs/${id}/slice${q}`);
  },
  reslice(id, body) { return this.MOCK ? Promise.resolve({ ...MOCK.slice }) : this._post(`/kbs/${id}/reslice`, body); },
};

/* ===================================================================== *
 *  以下为 MOCK（演示）数据，对接后端后可整段删除。
 * ===================================================================== */
const MOCK = {
  kbs: [
    { id: 'prod', name: '产品知识库', model: 'bge-large-zh-v1.5', chunk: 512, ov: 64 },
    { id: 'tech', name: '技术文档库', model: 'text-embedding-3-large', chunk: 1024, ov: 128 },
    { id: 'hr', name: 'HR 制度库', model: 'bge-large-zh-v1.5', chunk: 512, ov: 64 },
    { id: 'faq', name: '客服 FAQ 库', model: 'm3e-base', chunk: 256, ov: 32 },
  ],
  docs: {
    prod: [
      { n: '产品白皮书_v2.4.pdf', t: 'PDF', chunks: 420 },
      { n: '功能说明_核保模块.docx', t: 'Word', chunks: 112 },
      { n: '定价规则手册.pdf', t: 'PDF', chunks: 208 },
    ],
    tech: [
      { n: 'OpenAPI_规范.yaml', t: 'Markdown', chunks: 95 },
      { n: '系统架构设计.pdf', t: 'PDF', chunks: 260 },
      { n: '运维手册.docx', t: 'Word', chunks: 140 },
    ],
    hr: [
      { n: '员工手册_2026.pdf', t: 'PDF', chunks: 180 },
      { n: '考勤与休假制度.docx', t: 'Word', chunks: 48 },
    ],
    faq: [
      { n: '理赔常见问题.md', t: 'Markdown', chunks: 66 },
      { n: '投诉处理指南.pdf', t: 'PDF', chunks: 90 },
    ],
  },
  // baseTokens 用于按分块大小估算切片数：count ≈ baseTokens / chunk
  slice: {
    baseTokens: 4096,
    segments: [
      '保险理赔是指在保险标的发生保险责任范围内的损失或事故后，被保险人向保险公司提出索赔申请，保险公司依据保险合同约定进行审核并支付赔款的过程。',
      '理赔流程通常包括报案、提交资料、定损核价、审核、支付赔款五个主要环节。被保险人应在事故发生后及时报案，并按要求提交完整的索赔材料。',
      '在资料齐全并通过审核后，赔款一般会在 3 个工作日内支付至被保险人指定的银行账户。对于 1 万元以下的小额案件，系统支持快速通道，最快可在 24 小时内完成支付。',
      '若赔款超过 5 个工作日仍未到账，被保险人可通过客服热线发起查询工单，客服将协助核实支付状态并跟进处理进度，确保理赔体验顺畅。',
    ],
  },
};
