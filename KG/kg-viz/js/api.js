/* =====================================================================
 * api.js — 知识图谱后端接口层（唯一需要对接后端的文件）
 * ---------------------------------------------------------------------
 * 对接后端：
 *   1. 把 API.BASE 改成你的后端地址，例如 'https://your-host/api'
 *   2. 把 API.MOCK 改成 false
 *   3. 可选：删除下方 MOCK 演示数据（seedData）
 * app.js 无需改动。所有方法返回 Promise。
 *
 * 建议后端实现的接口：
 *   GET    /graph                      -> { nodes:[{id,label,type,x,y}], edges:[{id,source,target,label}] }
 *   POST   /nodes            body:{id,label,type}            -> { ok:true, node }
 *   PATCH  /nodes/:id        body:{label?,type?}             -> { ok:true }
 *   DELETE /nodes/:id                                        -> { ok:true, removedEdges:[id...] }
 *   POST   /edges            body:{id,source,target,label}   -> { ok:true, edge }
 *   DELETE /edges/:id                                        -> { ok:true }
 *   GET    /graph/delta?since=<version|ISO时间>
 *          -> 增量变更：{
 *               version,                       // 本次最新版本号/时间戳，下次作为 since 传回
 *               added:   { nodes:[...], edges:[...] },
 *               updated: { nodes:[{id,label,type}] },
 *               removed: { nodeIds:[...], edgeIds:[...] }
 *             }
 * ===================================================================== */

const API = {
  BASE: '/api',   // TODO: 改成你的后端地址
  MOCK: true,     // TODO: 对接后端时改成 false
  TOKEN: '',      // 可选 Bearer Token

  _headers() { const h = { 'Content-Type': 'application/json' }; if (this.TOKEN) h.Authorization = 'Bearer ' + this.TOKEN; return h; },
  async _req(method, p, body) {
    const opt = { method, headers: this._headers() };
    if (body !== undefined) opt.body = JSON.stringify(body);
    const r = await fetch(this.BASE + p, opt);
    if (!r.ok) throw new Error(method + ' ' + p + ' -> ' + r.status);
    return r.status === 204 ? {} : r.json();
  },

  getGraph()            { return this.MOCK ? Promise.resolve(seedData()) : this._req('GET', '/graph'); },
  createNode(node)      { return this.MOCK ? Promise.resolve({ ok: true, node }) : this._req('POST', '/nodes', node); },
  updateNode(id, patch) { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('PATCH', `/nodes/${id}`, patch); },
  deleteNode(id)        { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('DELETE', `/nodes/${id}`); },
  createEdge(edge)      { return this.MOCK ? Promise.resolve({ ok: true, edge }) : this._req('POST', '/edges', edge); },
  deleteEdge(id)        { return this.MOCK ? Promise.resolve({ ok: true }) : this._req('DELETE', `/edges/${id}`); },

  // 增量同步：传入上次的 version/时间戳，返回这段时间内的增删改
  pullDelta(since)      { return this.MOCK ? Promise.resolve(MOCK_DELTA()) : this._req('GET', `/graph/delta?since=${encodeURIComponent(since || '')}`); },
};

/* ===================================================================== *
 *  以下为 MOCK（演示）数据，对接后端后可整段删除。
 * ===================================================================== */
function seedData() {
  const N = (id, label, type) => ({ id, label, type });
  const nodes = [
    N('p1', '重疾险', 'product'), N('p2', '医疗险', 'product'), N('p3', '意外险', 'product'),
    N('c1', '等待期条款', 'clause'), N('c2', '免赔额条款', 'clause'), N('c3', '保额给付条款', 'clause'),
    N('r1', '既往症风险', 'risk'), N('r2', '职业等级风险', 'risk'),
    N('cl1', '理赔申请', 'claim'), N('cl2', '资料审核', 'claim'), N('cl3', '赔款支付', 'claim'),
    N('u1', '个人客户', 'customer'), N('u2', '团体客户', 'customer'),
    N('ch1', '代理人渠道', 'channel'), N('ch2', '线上渠道', 'channel'),
  ];
  const E = (s, t, l) => ({ id: 'e_' + s + '_' + t, source: s, target: t, label: l });
  const edges = [
    E('p1', 'c1', '包含'), E('p1', 'c3', '包含'), E('p2', 'c2', '包含'), E('p3', 'c3', '包含'),
    E('p1', 'r1', '承保'), E('p3', 'r2', '承保'),
    E('cl1', 'cl2', '流转'), E('cl2', 'cl3', '流转'), E('p1', 'cl1', '触发'), E('p2', 'cl1', '触发'),
    E('u1', 'p1', '投保'), E('u1', 'p2', '投保'), E('u2', 'p3', '投保'),
    E('ch1', 'u1', '服务'), E('ch2', 'u1', '服务'), E('ch1', 'u2', '服务'),
    E('r1', 'c1', '受约束'),
  ];
  return { nodes, edges, version: Date.now() };
}

// 演示用增量 diff：每次点「同步」随机返回一点变化，模拟后端持续更新
let _mockDeltaStep = 0;
function MOCK_DELTA() {
  _mockDeltaStep++;
  if (_mockDeltaStep === 1) {
    return { version: Date.now(),
      added: { nodes: [{ id: 'p_demo1', label: '寿险', type: 'product' }], edges: [{ id: 'e_demo1', source: 'u2', target: 'p_demo1', label: '投保' }] },
      updated: { nodes: [] }, removed: { nodeIds: [], edgeIds: [] } };
  }
  if (_mockDeltaStep === 2) {
    return { version: Date.now(),
      added: { nodes: [], edges: [{ id: 'e_demo2', source: 'p_demo1', target: 'c3', label: '包含' }] },
      updated: { nodes: [{ id: 'r2', label: '职业等级风险(已细化)', type: 'risk' }] }, removed: { nodeIds: [], edgeIds: [] } };
  }
  // 之后：无新增量
  return { version: Date.now(), added: { nodes: [], edges: [] }, updated: { nodes: [] }, removed: { nodeIds: [], edgeIds: [] } };
}
