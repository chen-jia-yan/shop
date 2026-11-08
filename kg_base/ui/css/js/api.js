/* =====================================================================
 * api.js — 后端接口层（唯一需要对接后端的文件）
 * ---------------------------------------------------------------------
 * 对接后端：
 *   1. 把 API.BASE 改成你的后端地址，例如 'https://your-host/api'
 *   2. 把 API.MOCK 改成 false
 *   3. 可选：删除下方 MOCK 演示数据
 * app.js 无需改动。所有方法返回 Promise。
 *
 * 建议后端实现的接口：
 *   GET  /overview                      -> 总览数据
 *   GET  /kbs                           -> 知识库列表
 *   GET  /kbs/:id/docs                  -> 某知识库的文档列表
 *   POST /kbs                           -> 新建知识库   body:{name,desc,model,dim}
 *   POST /kbs/:id/docs                  -> 上传文档     body:{name,chunkSize,overlap}
 *   POST /kbs/:id/docs/delete           -> 批量删除     body:{names:[]}
 *   POST /kbs/:id/reindex               -> 重建索引
 *   POST /chat                          -> 问答         body:{question,kb,agent}
 *                                          返回 {steps,answer,sources,followups}
 *   POST /search                        -> 检索         body:{query,kb,type,topk,threshold,rerank}
 *   GET  /kbs/:id/slice?doc=xxx         -> 文档切片预览
 *   GET  /eval                          -> 评估报告数据
 *   GET  /batch                         -> 批处理报告数据
 * ===================================================================== */

const API = {
  BASE: '/api',   // TODO: 改成你的后端地址
  MOCK: true,     // TODO: 对接后端时改成 false
  TOKEN: '',      // 可选 Bearer Token

  _headers() { const h = { 'Content-Type': 'application/json' }; if (this.TOKEN) h.Authorization = 'Bearer ' + this.TOKEN; return h; },
  async _get(p) { const r = await fetch(this.BASE + p, { headers: this._headers() }); if (!r.ok) throw new Error('GET ' + p + ' -> ' + r.status); return r.json(); },
  async _post(p, b) { const r = await fetch(this.BASE + p, { method: 'POST', headers: this._headers(), body: JSON.stringify(b) }); if (!r.ok) throw new Error('POST ' + p + ' -> ' + r.status); return r.json(); },

  getOverview()        { return this.MOCK ? Promise.resolve(MOCK.overview) : this._get('/overview'); },
  listKbs()            { return this.MOCK ? Promise.resolve(MOCK.kbs) : this._get('/kbs'); },
  getKbDocs(id)        { return this.MOCK ? Promise.resolve((MOCK.docs[id] || []).slice()) : this._get(`/kbs/${id}/docs`); },
  createKb(p)          { return this.MOCK ? Promise.resolve({ ok: true }) : this._post('/kbs', p); },
  uploadDoc(id, p)     { return this.MOCK ? Promise.resolve({ ok: true }) : this._post(`/kbs/${id}/docs`, p); },
  deleteDocs(id, names){ return this. MOCK ? Promise.resolve({ ok: true }) : this._post(`/kbs/${id}/docs/delete`, { names }); },
  reindex(id)          { return this.MOCK ? Promise.resolve({ ok: true }) : this._post(`/kbs/${id}/reindex`, {}); },
  ask(q, opts)         { return this.MOCK ? Promise.resolve(MOCK.answer) : this._post('/chat', { question: q, ...opts }); },
  search(q, opts)      { return this.MOCK ? Promise.resolve(MOCK.search) : this._post('/search', { query: q, ...opts }); },
  getSlice(id, doc)    { return this.MOCK ? Promise.resolve(MOCK.slice) : this._get(`/kbs/${id}/slice?doc=${encodeURIComponent(doc)}`); },
  getEval()            { return this.MOCK ? Promise.resolve(MOCK.eval) : this._get('/eval'); },
  getBatch()           { return this.MOCK ? Promise.resolve(MOCK.batch) : this._get('/batch'); },
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
  overview: {
    trend: {
      days: Array.from({ length: 14 }, (_, i) => `10/${i + 1}`),
      qa: [820, 760, 900, 1040, 980, 1120, 1180, 1050, 1210, 1160, 1240, 1190, 1300, 1274],
      hit: [88, 87, 89, 90, 89, 91, 90, 91, 92, 91, 92, 92, 93, 92.6],
    },
    logs: [
      ['11:12', 'faq', '客服 FAQ 库 新增 1 个文档并完成索引', 'ok'],
      ['10:20', 'prod', '产品知识库 重建索引完成，486K → 486K chunks', 'ok'],
      ['10:18', 'prod', '版本发布说明_2026Q4.md 正在索引', 'idx'],
      ['09:05', 'tech', '技术文档库 架构设计.pdf 索引中', 'idx'],
      ['08:30', 'faq', '投诉处理指南.pdf 等待处理', 'wait'],
    ],
    hot: [['理赔款多久到账？', 312], ['如何申请退保？', 248], ['年假有多少天？', 196], ['v2.4 新增功能', 154], ['发票如何报销', 131]],
    hitRates: [94, 88, 95, 91], // 顺序对应 kbs
  },
  answer: {
    q: '理赔款一般多久到账？',
    think: [
      { t: '问题理解', ms: '82ms', html: '识别意图：<b>理赔时效查询</b>；关键实体：<span class="qrw">理赔款</span><span class="qrw">到账时间</span>；判定需检索「客服 FAQ 库 / 产品知识库」。' },
      { t: 'Query 改写与扩展', ms: '140ms', html: '生成多路召回 query：<span class="qrw">理赔款到账时间</span><span class="qrw">赔款多久支付</span><span class="qrw">理赔打款周期</span>' },
      { t: '向量检索 (Top-10)', ms: '96ms', chunks: [
        { src: '客服 FAQ 库 · 理赔常见问题.md', score: 0.91, txt: '…资料齐全并审核通过后，赔款将在 3 个工作日内支付至您提供的银行账户…' },
        { src: '产品知识库 · 定价规则手册.pdf', score: 0.74, txt: '…小额案件（1 万元以下）支持快速通道，最快 24 小时内完成支付…' },
        { src: '客服 FAQ 库 · 投诉处理指南.pdf', score: 0.63, txt: '…如超过 5 个工作日仍未到账，可通过客服热线发起查询…' },
      ] },
      { t: '重排序 (rerank)', ms: '54ms', html: '交叉编码器重排后，<b>理赔常见问题.md</b> 置信度升至 <b style="color:var(--blue)">0.94</b>，列为主依据；过滤掉相似度低于 0.6 的 7 条噪声片段。' },
      { t: '答案组织与引用', ms: '310ms', html: '基于 Top-3 片段组织答案，标注来源编号，确保每个结论可溯源。' },
    ],
    answer: '一般情况下，在您提交的理赔资料<b>齐全并审核通过</b>后，赔款会在 <b>3 个工作日</b>内支付到您指定的银行账户 <cite>1</cite>。<br><br>如果是 1 万元以下的小额案件，可走<b>快速通道</b>，最快 <b>24 小时</b>内完成支付 <cite>2</cite>。若超过 <b>5 个工作日</b>仍未到账，建议通过客服热线发起查询 <cite>3</cite>。',
    srcs: [['1', '客服 FAQ 库 · 理赔常见问题.md', '0.94'], ['2', '产品知识库 · 定价规则手册.pdf', '0.74'], ['3', '客服 FAQ 库 · 投诉处理指南.pdf', '0.63']],
    follow: ['大额案件审核要多久？', '理赔需要准备哪些材料？', '赔款可以改到其他账户吗？'],
  },
  search: [
    { src: '客服 FAQ 库 · 理赔常见问题.md · 第 2 节', type: 'Markdown', score: 0.94, txt: '资料齐全并审核通过后，<mark>赔款</mark>将在 3 个工作日内<mark>支付</mark>至您提供的银行账户；大额案件可能需要额外复核。' },
    { src: '产品知识库 · 定价规则手册.pdf · p.41', type: 'PDF', score: 0.74, txt: '小额案件（1 万元以下）支持快速通道，最快 24 小时内完成<mark>赔款支付</mark>，无需人工复核。' },
    { src: '客服 FAQ 库 · 投诉处理指南.pdf · p.8', type: 'PDF', score: 0.63, txt: '如<mark>赔款</mark>超过 5 个工作日仍未<mark>到账</mark>，客户可通过客服热线发起查询工单。' },
    { src: '产品知识库 · 产品白皮书_v2.4.pdf · p.112', type: 'PDF', score: 0.58, txt: '理赔流程包含报案、定损、审核、<mark>支付</mark>四个阶段，系统全程留痕可追溯。' },
  ],
  slice: {
    count: 8,
    segments: [
      '保险理赔是指在保险标的发生保险责任范围内的损失或事故后，被保险人向保险公司提出索赔申请，保险公司依据保险合同约定进行审核并支付赔款的过程。',
      '理赔流程通常包括报案、提交资料、定损核价、审核、支付赔款五个主要环节。被保险人应在事故发生后及时报案，并按要求提交完整的索赔材料。',
      '在资料齐全并通过审核后，赔款一般会在 3 个工作日内支付至被保险人指定的银行账户。对于 1 万元以下的小额案件，系统支持快速通道，最快可在 24 小时内完成支付。',
      '若赔款超过 5 个工作日仍未到账，被保险人可通过客服热线发起查询工单，客服将协助核实支付状态并跟进处理进度，确保理赔体验顺畅。',
    ],
  },
  eval: {
    bars: [['忠实度 Faithfulness', 0.89, 'var(--green)'], ['答案相关性 Relevancy', 0.84, 'var(--blue)'], ['上下文精确 Precision', 0.76, 'var(--amber)'], ['上下文召回 Recall', 0.71, 'var(--amber)'], ['答案正确性 Correctness', 0.80, 'var(--violet)']],
    trend: { labels: ['#135', '#136', '#137', '#138', '#139', '#140', '#141', '#142'], data: [72, 76, 74, 78.3, 79, 80, 81, 82.4] },
    runs: [['#142', 'faq-golden-200', 82.4, 37, 'gpt-4o+rerank', '10-13 18:20'], ['#138', 'faq-golden-200', 78.3, 48, 'gpt-4o-mini', '10-09 14:00']],
    bad: [['报销流程最长多久到账？', '忠实度低：答案数值与原文冲突（3天 vs 5天）'], ['试用期可以提前转正吗？', '召回缺失：golden 文档未进入 Top-k'], ['竞业协议的补偿标准？', '检索噪声：Top-k 混入无关片段']],
  },
  batch: {
    reasons: [['扫描件清晰度不足', 68], ['加密/权限 PDF', 41], ['关键字段缺失', 34], ['重复文档', 33], ['空白/格式不符', 29], ['文件损坏/截断', 22]],
    donut: [1236, 182, 62],
    rows: [['BATCH-20261013-07', 1480, 1236, 182, 83.5, 'done', '10-13 21:40'], ['BATCH-20261012-05', 960, 902, 41, 94.0, 'done', '10-12 16:10'], ['BATCH-20261013-09', 520, 0, 0, 0, 'run', '进行中']],
  },
};
