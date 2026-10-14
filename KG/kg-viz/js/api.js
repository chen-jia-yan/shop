/* =====================================================================
 * api.js — 知识图谱（百万级）· 后端接口层（唯一需要对接后端的文件）
 * ---------------------------------------------------------------------
 * 关键思想：百万级图谱全量存后端（真实用图数据库 Neo4j / NebulaGraph）。
 * 前端永远只按需拉“子图”：种子子图、k 跳邻居、搜索。前端内存里始终只有
 * 几百个节点，所以 SVG 的动态手感不变、却不崩不卡。本文件用浏览器内生成的
 * 2 万节点“模拟后端”，对外代表百万级文档量（docTotal）。
 *
 * 对接真实后端：
 *   1. API. BASE 改成你的地址，API.MOCK 改成 false
 *   2. 删除下方 buildStore / MOCK 生成逻辑
 *
 * 建议后端实现：
 *   GET  /graph/stats                            -> {docTotal, nodes, edges}
 *   GET  /graph/seed?limit=                      -> {nodes:[{id,label,type,deg}], edges:[{id,source,target,label}]}
 *   GET  /graph/neighbors?id=&offset=&limit=     -> {nodes, edges, total, offset, limit}
 *   GET  /graph/search?q=&limit=                 -> {nodes:[{id,label,type,deg}]}
 *   GET  /nodes/:id/content                      -> {files:[{name,type,status,chunks:[{idx,text,score}]}]}
 *   POST   /nodes      {id,label,type}           -> {ok}
 *   PATCH  /nodes/:id  {label?,type?}            -> {ok}
 *   DELETE /nodes/:id                            -> {ok}
 *   POST   /edges      {id,source,target,label}  -> {ok}
 *   DELETE /edges/:id                            -> {ok}
 *   GET    /graph/delta?since=                   -> {version,added,updated,removed}
 * ===================================================================== */

const API = {
  BASE: '/api',   // TODO: 改成你的后端地址
  MOCK: true,     // TODO: 对接后端时改成 false
  TOKEN: '',

  _headers() { const h = { 'Content-Type': 'application/json' }; if (this.TOKEN) h.Authorization = 'Bearer ' + this.TOKEN; return h; },
  async _req(method, p, body) { const opt = { method, headers: this._headers() }; if (body !== undefined) opt.body = JSON.stringify(body); const r = await fetch(this.BASE + p, opt); if (!r.ok) throw new Error(method + ' ' + p + ' -> ' + r.status); return r.status === 204 ? {} : r.json(); },

  getStats()                               { return this. MOCK ? Promise.resolve(STORE.stats()) : this._req('GET', '/graph/stats'); },
  getSeed(limit = 42)                      { return this.MOCK ? Promise.resolve(STORE.seed(limit)) : this._req('GET', `/graph/seed?limit=${limit}`); },
  getNeighbors(id, offset = 0, limit = 24) { return this.MOCK ? Promise.resolve(STORE.neighbors(id, offset, limit)) : this._req('GET', `/graph/neighbors?id=${encodeURIComponent(id)}&offset=${offset}&limit=${limit}`); },
  search(q, limit = 8)                     { return this.MOCK ? Promise.resolve(STORE.search(q, limit)) : this._req('GET', `/graph/search?q=${encodeURIComponent(q)}&limit=${limit}`); },
  getNodeContent(id, label)                { return this.MOCK ? Promise.resolve(STORE.content(id, label)) : this._req('GET', `/nodes/${id}/content`); },

  createNode(node)      { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('POST', '/nodes', node); },
  updateNode(id, patch) { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('PATCH', `/nodes/${id}`, patch); },
  deleteNode(id)        { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('DELETE', `/nodes/${id}`); },
  createEdge(edge)      { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('POST', '/edges', edge); },
  deleteEdge(id)        { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('DELETE', `/edges/${id}`); },
  pullDelta(since)      { return this.MOCK ? Promise.resolve(STORE.delta()) : this._req('GET', `/graph/delta?since=${encodeURIComponent(since || '')}`); },
};

/* ===================================================================== *
 *  浏览器内“模拟后端”——对接真实后端后整段删除。
 * ===================================================================== */
const STORE = (() => {
  const DOC_TOTAL = 1000000, GEN = 20000;
  let seed = 20260115; const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const pick = a => a[Math.floor(rnd() * a.length)];
  const nodes = new Map(), adj = new Map();          // adj: id -> Map(nid -> label)
  const add = (id, label, type) => { nodes.set(id, { id, label, type }); adj.set(id, new Map()); };
  const link = (a, b, label) => { if (a === b || !adj.has(a) || !adj.has(b)) return; if (!adj.get(a).has(b)) adj.get(a).set(b, label); if (!adj.get(b).has(a)) adj.get(b).set(a, label); };

  const POOL = {
    product: ['重疾险', '医疗险', '意外险', '寿险', '年金险', '防癌险', '少儿重疾', '高端医疗'],
    clause: ['等待期条款', '免赔额条款', '保额给付条款', '续保条款', '现金价值条款', '责任免除条款'],
    risk: ['既往症风险', '职业等级风险', '高危运动风险', '年龄风险'],
    claim: ['理赔申请', '资料审核', '赔款支付', '拒赔复核'],
    channel: ['代理人渠道', '线上渠道', '经纪渠道', '银保渠道'],
  };
  const ids = { product: [], clause: [], risk: [], claim: [], channel: [], customer: [] };
  const name = (type, i) => { const p = POOL[type]; const base = p[(i - 1) % p.length]; const g = Math.floor((i - 1) / p.length); return g ? base + '·' + (g + 1) : base; };
  const mk = (type, pre, n) => { for (let i = 1; i <= n; i++) { const id = pre + i; add(id, type === 'customer' ? '客户#' + i : name(type, i), type); ids[type].push(id); } };
  mk('product', 'P', 40); mk('clause', 'C', 200); mk('risk', 'R', 80); mk('claim', 'L', 60); mk('channel', 'H', 20); mk('customer', 'U', 1500);

  ids.clause.forEach(c => link(c, pick(ids.product), '所属'));
  ids.risk.forEach(r => { link(r, pick(ids.product), '承保'); if (rnd() < .5) link(r, pick(ids.clause), '受约束'); });
  ids.claim.forEach(l => { link(l, pick(ids.product), '触发'); if (rnd() < .5) link(l, pick(ids.claim), '流转'); });
  ids.customer.forEach(u => { link(u, pick(ids.product), '投保'); link(u, pick(ids.channel), '服务'); });
  const docHubs = ids.product.concat(ids.clause, ids.risk, ids.claim);
  for (let i = 1; nodes.size < GEN; i++) { const id = 'D' + i; add(id, '文档#' + i, 'doc'); const k = 1 + Math.floor(rnd() * 3); for (let j = 0; j < k; j++) link(id, pick(docHubs), '来源'); }

  const deg = id => (adj.get(id) ? adj.get(id).size : 0);
  const toNode = id => { const n = nodes.get(id); return { id: n.id, label: n.label, type: n.type, deg: deg(id) }; };
  const eid = (a, b) => 'e_' + (a < b ? a + '_' + b : b + '_' + a);
  const topHubs = ids.product.concat(ids.clause).sort((a, b) => deg(b) - deg(a)).slice(0, 8);
  let edgeCount = 0; adj.forEach(m => edgeCount += m.size); edgeCount = Math.round(edgeCount / 2);

  return {
    stats: () => ({ docTotal: DOC_TOTAL, nodes: nodes.size, edges: edgeCount }),
    seed(limit) {
      const outN = new Map(), outE = []; const put = id => { if (!outN.has(id)) outN.set(id, toNode(id)); };
      for (const h of topHubs) { put(h); let c = 0; for (const [nb, lb] of adj.get(h)) { if (c++ >= 6) break; put(nb); outE.push({ id: eid(h, nb), source: h, target: nb, label: lb }); if (outN.size >= limit) break; } if (outN.size >= limit) break; }
      return { nodes: [...outN.values()], edges: outE };
    },
    neighbors(id, offset, limit) {
      if (!adj.has(id)) return { nodes: [], edges: [], total: 0, offset, limit };
      const all = [...adj.get(id)]; const slice = all.slice(offset, offset + limit);
      return { nodes: slice.map(([nid]) => toNode(nid)), edges: slice.map(([nid, lb]) => ({ id: eid(id, nid), source: id, target: nid, label: lb })), total: all.length, offset, limit };
    },
    search(q, limit) {
      q = (q || '').trim().toLowerCase(); if (!q) return { nodes: [] };
      const out = []; for (const n of nodes.values()) { if (n.label.toLowerCase().includes(q)) { out.push(toNode(n.id)); if (out.length >= limit * 4) break; } }
      out.sort((a, b) => b.deg - a.deg); return { nodes: out.slice(0, limit) };
    },
    content(id) {
      const n = nodes.get(id); if (!n) return { files: [] };
      const chunkTxt = (lbl) => [
        `本节说明「${lbl}」的定义、适用范围与除外责任。被保险人在保险期间内发生约定事故的，依条款约定承担给付责任。`,
        `关于「${lbl}」的给付条件：资料齐全并通过审核后，赔款在 3 个工作日内支付；小额案件支持 24 小时快速通道。`,
        `「${lbl}」常见争议：若对认定有异议，可在收到通知后 15 日内申请复核并提交补充材料。`,
      ];
      if (n.type === 'doc') {
        const t = chunkTxt(n.label);
        return { files: [{ name: n.label + '.pdf', type: 'PDF', status: 'ok', chunks: t.map((x, i) => ({ idx: i + 1, text: x, score: +(0.9 - i * 0.07).toFixed(2) })) }] };
      }
      const docs = [...adj.get(id)].filter(([nid]) => nodes.get(nid) && nodes.get(nid).type === 'doc').slice(0, 3);
      const files = (docs.length ? docs : [[null]]).map(([nid], fi) => {
        const docName = nid ? nodes.get(nid).label : '条款汇编';
        const t = chunkTxt(n.label);
        return { name: docName + '.pdf', type: fi % 2 ? 'Word' : 'PDF', status: 'ok', chunks: t.slice(0, 2).map((x, i) => ({ idx: i + 1, text: x, score: +(0.88 - fi * 0.05 - i * 0.06).toFixed(2) })) };
      });
      return { files };
    },
    delta() { // 演示：往已存在的枢纽 P1 挂一个新文档
      const did = 'DELTA' + Date.now().toString(36).slice(-4);
      return { version: Date.now(), added: { nodes: [{ id: did, label: '新入库文档·' + did.slice(-3), type: 'doc', deg: 1 }], edges: [{ id: 'e_' + did + '_P1', source: did, target: 'P1', label: '来源' }] }, updated: { nodes: [] }, removed: { nodeIds: [], edgeIds: [] } };
    },
  };
})();
