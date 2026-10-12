/* =====================================================================
 * api.js — 后端接口层（唯一需要对接后端的文件）
 * ---------------------------------------------------------------------
 * 用法：
 *   1. 把 API.BASE 改成你的后端地址，例如 'https://your-host/api'
 *   2. 把 API.MOCK 改成 false
 *   界面逻辑（app.js）无需任何改动。
 *
 * 后端需要实现的接口契约见 README.md。所有方法均返回 Promise。
 * ===================================================================== */

const API = {
  /* ---------- 配置 ---------- */
  BASE: '/api',     // TODO: 改成你的后端地址
  MOCK: true,       // TODO: 对接后端时改成 false
  TOKEN: '',        // 如需鉴权，填入 Bearer Token（可留空）

  /* ---------- 通用请求封装 ---------- */
  _headers() {
    const h = { 'Content-Type': 'application/json' };
    if (this.TOKEN) h['Authorization'] = 'Bearer ' + this.TOKEN;
    return h;
  },
  async _get(path) {
    const res = await fetch(this.BASE + path, { headers: this._headers() });
    if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
    return res.json();
  },
  async _post(path, body) {
    const res = await fetch(this.BASE + path, {
      method: 'POST', headers: this._headers(), body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
    return res.json();
  },

  /* ---------- 评估报告 ---------- */
  // GET /reports -> Report[]
  listReports() {
    return this.MOCK ? Promise.resolve(MOCK.reports) : this._get('/reports');
  },
  // GET /reports/:id -> ReportDetail
  getReport(id) {
    return this.MOCK ? Promise.resolve(MOCK.reportDetail(id)) : this._get(`/reports/${encodeURIComponent(id)}`);
  },

  /* ---------- 评估集 ---------- */
  // GET /datasets -> Dataset[]
  listDatasets() {
    return this.MOCK ? Promise.resolve(MOCK.datasets) : this._get('/datasets');
  },
  // GET /datasets/:name -> DatasetDetail { meta, samples[] }
  getDataset(name) {
    return this.MOCK ? Promise.resolve(MOCK.datasetDetail(name)) : this._get(`/datasets/${encodeURIComponent(name)}`);
  },
  // POST /datasets -> { name, count }
  // body: { name, format: 'csv'|'jsonl', rows: object[] }
  uploadDataset(payload) {
    if (this.MOCK) {
      MOCK.datasets.unshift({ n: payload.name, d: '手动上传 · ' + payload.format.toUpperCase(),
        cnt: payload.count, pass: 0, upd: today(), ico: '⬆', anno: payload.count });
      return Promise.resolve({ name: payload.name, count: payload.count });
    }
    return this._post('/datasets', payload);
  },

  /* ---------- 评分指标 ---------- */
  // GET /metrics -> MetricDef[]
  listMetrics() {
    return this.MOCK ? Promise.resolve(MOCK.metrics) : this._get('/metrics');
  },

  /* ---------- Bad Case ---------- */
  // GET /bad-cases -> BadCase[]
  listBadCases() {
    return this.MOCK ? Promise.resolve(MOCK.badCases()) : this._get('/bad-cases');
  },

  /* ---------- Prompt 版本 ---------- */
  // GET /prompts -> PromptVersion[]
  listPrompts() {
    return this.MOCK ? Promise.resolve(MOCK.prompts) : this._get('/prompts');
  },
  // POST /prompts -> PromptVersion   body: { version, body }
  createPrompt(payload) {
    if (this.MOCK) {
      const pv = { v: payload.version, tag: 'draft', date: today(), run: '—',
        score: null, f: null, c: null, body: escapeHtml(payload.body) };
      MOCK.prompts.unshift(pv);
      return Promise.resolve(pv);
    }
    return this._post('/prompts', payload);
  },

  /* ---------- 新建评估 ---------- */
  // POST /evaluations -> { run_id }
  // body: { name, dataset, model, prompt, retriever, baseline }
  createEvaluation(payload) {
    if (this.MOCK) {
      const nums = MOCK.reports.map(r => parseInt(r.v.replace('#', '')));
      const id = '#' + (Math.max(...nums) + 1);
      MOCK.reports.unshift({ v: id, name: payload.name, ds: payload.dataset, n: payload.count || 200,
        score: 0, prev: 0, bad: 0, model: `${payload.model} · ${payload.prompt} · ${payload.retriever}`,
        st: 'run', time: '运行中 · 0%' });
      MOCK._running[id] = 0;
      return Promise.resolve({ run_id: id });
    }
    return this._post('/evaluations', payload);
  },
  // GET /evaluations/:id/status -> { progress, status, score, prev, bad, time }
  getEvaluationStatus(id) {
    if (this.MOCK) return Promise.resolve(MOCK.tickRunning(id));
    return this._get(`/evaluations/${encodeURIComponent(id)}/status`);
  },
};

/* ===================================================================== *
 *  以下为 MOCK（演示）数据，对接后端后可整段删除。
 * ===================================================================== */
const rand = (a, b) => a + Math.random() * (b - a);
const today = () => '2026-10-12';
const escapeHtml = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function buildCases() {
  const q = [
    { q: '公司的年假政策是多少天？', a: '员工入职满一年享有 10 天带薪年假，满三年后每年递增…', reason: '', type: '' },
    { q: '出差住宿标准是多少？', a: '一线城市每晚上限 600 元，其余城市 450 元…', reason: '', type: '' },
    { q: '报销流程最长多久到账？', a: '模型回答“3 个工作日”，但知识库原文为“5 个工作日”。', reason: '忠实度低：答案与检索上下文冲突，出现数值幻觉。', type: '忠实' },
    { q: '试用期可以提前转正吗？', a: '检索未命中相关条款，模型凭常识作答。', reason: '上下文召回缺失：golden 文档未被检索到，答案无依据。', type: '召回' }
  ];
  return q.map((base, i) => {
    const bad = !!base.reason;
    const f = bad ? rand(.4, .72) : rand(.82, .98);
    const r = bad ? rand(.45, .75) : rand(.78, .95);
    const p = bad ? rand(.4, .7) : rand(.74, .92);
    const c = bad ? rand(.35, .68) : rand(.7, .9);
    return { id: 'C-' + (1042 + i), q: base.q, a: base.a, reason: base.reason, type: base.type,
      f, r, p, c, overall: (f + r + p + c) / 4 * 100, bad };
  });
}

const MOCK = {
  reports: [
    { v: '#142', name: '知识库问答评估', ds: 'faq-golden-200', n: 200, score: 82.4, prev: 4.1, bad: 37, model: 'gpt-4o + bge-reranker', st: 'done', time: '2026-10-12 18:20' },
    { v: '#138', name: '知识库问答评估(基线)', ds: 'faq-golden-200', n: 200, score: 78.3, prev: 0, bad: 48, model: 'gpt-4o-mini', st: 'done', time: '2026-10-09 14:00' }
  ],
  _running: {},

  reportDetail(id) {
    return {
      id, title: '知识库问答评估', ver: id, dataset: 'faq-golden-200', n: 200,
      model: 'gpt-4o + bge-reranker', time: '2026-10-12 18:20',
      score: 82.4, baselineDelta: 4.1, baselineRun: '#138', badCount: 37,
      metrics: [
        { label: '◆ Faithfulness 忠实度', value: 0.89, delta: 0.05, up: true, color: 'var(--green)' },
        { label: '◆ Answer Relevancy 相关性', value: 0.84, delta: 0.02, up: true, color: 'var(--green)' },
        { label: '◆ Context Precision 精确', value: 0.76, delta: -0.03, up: false, color: 'var(--amber)' },
        { label: '◆ Context Recall 召回', value: 0.71, delta: 0.08, up: true, color: 'var(--amber)' }
      ],
      trend: {
        labels: ['#133', '#134', '#135', '#136', '#137', '#138', '#139', '#140', '#141', '#142'],
        composite: [71, 73, 72, 76, 74, 78.3, 79, 80, 81, 82.4],
        faithfulness: [80, 82, 81, 83, 82, 84, 85, 86, 88, 89],
        precision: [70, 72, 74, 75, 77, 79, 78, 77, 78, 76]
      },
      radar: {
        labels: ['忠实度', '答案相关', '上下文精确', '上下文召回', '答案正确性'],
        current: [89, 84, 76, 71, 80], baseline: [84, 82, 79, 63, 77]
      },
      summary: {
        verdict: '本轮综合评分 <b>82.4</b>，较基线 run #138 提升 <b style="color:var(--green)">+4.1 分</b>，达到上线门槛（≥80）。主要收益来自引入 <b>bge-reranker</b> 后 <b>上下文召回</b>从 0.63 提升至 0.71；但 <b>上下文精确度</b>轻微回落（-0.03），200 条中仍有 <b style="color:var(--red)">37 条 bad case</b>，集中在数值类问答与多片段聚合场景。',
        findings: [
          '<b>忠实度冲突（14 条）</b>：答案数值与原文不符，多发生在金额/时限类问题，模型产生数值幻觉。',
          '<b>召回缺失（11 条）</b>：golden 文档未进入 Top-k，常见于长尾与改写表述的问题。',
          '<b>检索噪声（7 条）</b>：Top-k 混入无关片段，污染生成答案。',
          '<b>答案不完整（5 条）</b>：遗漏关键限定条件，相关性评分偏低。'
        ],
        recommendations: [
          '对金额/时限类问题增加<b>强制引用约束</b>，要求答案标注来源 chunk，降低数值幻觉。',
          '召回侧补充 <b>query 改写 / HyDE</b>，并将 Top-k 由 5 提升至 8 做召回兜底。',
          '精确度回落需在 reranker 后加<b>相关性阈值过滤</b>，剔除低分片段。',
          '把本轮 37 条 bad case <b>回流到 policy-hard 集</b>，下轮定向回归。'
        ]
      },
      cases: buildCases()
    };
  },

  datasets: [
    { n: 'faq-golden-200', d: 'FAQ 黄金标准集 · 人工标注', cnt: 200, pass: 163, upd: '2026-10-10', ico: '▤', anno: 200 },
    { n: 'policy-hard-80', d: 'HR 政策疑难问题', cnt: 80, pass: 58, upd: '2026-10-08', ico: '◆', anno: 80 }
  ],
  _samples: [
    ['公司的年假政策是多少天？', '满一年 10 天，满三年起每满一年 +1 天，上限 15 天。'],
    ['报销流程最长多久到账？', '审批通过后 5 个工作日内到账。'],
    ['病假需要提供什么证明？', '连续 3 天以上须提供三甲医院诊断证明。']
  ],
  datasetDetail(name) {
    const d = this.datasets.find(x => x.n === name) || this.datasets[0];
    const show = Math.min(d.cnt, 3);
    const samples = [];
    for (let k = 0; k < show; k++) {
      const q = this._samples[k % this._samples.length];
      const annotated = k < Math.round(show * d.anno / d.cnt);
      samples.push({ idx: k + 1, query: q[0], ground_truth: annotated ? q[1] : null, annotated });
    }
    return {
      meta: { name: d.n, desc: d.d, count: d.cnt, annotated: d.anno,
        passRate: d.pass ? Math.round(d.pass / d.cnt * 100) : null,
        linkedReports: this.reports.filter(r => r.ds === d.n).length, updated: d.upd },
      samples, shown: show
    };
  },

  metrics: [
    { icon: '◆', name: 'Faithfulness 忠实度', weight: 0.30, type: 'LLM-as-judge', desc: '答案中的每个论断是否都能由检索到的上下文支撑，惩罚幻觉与编造。' },
    { icon: '◆', name: 'Answer Relevancy 答案相关性', weight: 0.25, type: 'embedding', desc: '答案是否紧扣用户问题，惩罚答非所问、冗余与跑题。' },
    { icon: '◆', name: 'Context Precision 上下文精确度', weight: 0.20, type: 'rank-aware', desc: '检索返回的 Top-k 中真正相关的 chunk 占比与排序质量。' },
    { icon: '◆', name: 'Context Recall 上下文召回', weight: 0.15, type: 'LLM-as-judge', desc: '回答所需的关键信息是否都被检索召回，惩罚召回缺失。' },
    { icon: '◆', name: 'Answer Correctness 答案正确性', weight: 0.10, type: 'vs ground truth', desc: '与人工参考答案的事实一致性，综合语义与事实比对。' }
  ],

  badCases() {
    const out = [];
    const typed = buildCases().filter(c => c.bad);
    this.reports.filter(r => r.st === 'done').forEach(r => {
      typed.forEach(c => out.push({ id: 'C-' + Math.floor(rand(1000, 1999)), q: c.q,
        reason: c.reason, type: c.type, src: r.v, overall: Math.round(rand(40, 68)) }));
    });
    return out;
  },

  prompts: [
    { v: 'v3', tag: 'live', date: '2026-10-10', run: '#142', score: 82.4, f: 0.89, c: 0.71,
      body: `你是企业知识库问答助手。请<span class="hl">仅依据下方检索到的上下文</span>回答用户问题。\n\n规则：\n1. 若上下文不包含答案，直接回答「知识库中暂无相关信息」，<span class="add">不要编造</span>。\n2. 涉及金额、时限、天数等数值时，<span class="add">必须逐字引用原文</span>并标注来源片段编号。\n3. 回答需完整覆盖问题的所有限定条件。\n\n【上下文】\n{context}\n\n【问题】\n{question}` },
    { v: 'v2', tag: 'old', date: '2026-09-28', run: '#136', score: 73.3, f: 0.84, c: 0.63,
      body: `你是企业知识库问答助手。请根据下方上下文回答用户问题。\n\n规则：\n1. 若上下文不包含答案，回答「知识库中暂无相关信息」。\n2. 回答要简洁准确。\n\n【上下文】\n{context}\n\n【问题】\n{question}` }
  ],

  // 模拟运行中评估的进度轮询
  tickRunning(id) {
    let p = (this._running[id] || 0) + Math.round(8 + Math.random() * 14);
    if (p >= 100) {
      p = 100;
      delete this._running[id];
      const row = this.reports.find(r => r.v === id);
      if (row) { row.st = 'done'; row.score = +(70 + Math.random() * 15).toFixed(1);
        row.prev = +((Math.random() * 8) - 2).toFixed(1); row.bad = Math.round(row.n * 0.15 * Math.random() + 15);
        row.time = '2026-10-12 20:' + String(20 + Math.floor(Math.random() * 39)).padStart(2, '0'); }
      return { progress: 100, status: 'done', score: row ? row.score : null, time: row ? row.time : null };
    }
    this._running[id] = p;
    const row = this.reports.find(r => r.v === id);
    if (row) row.time = '运行中 · ' + p + '%';
    return { progress: p, status: 'running' };
  }
};
