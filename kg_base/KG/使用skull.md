# kg_skill调研补充内容
我按”先懂概念 → 再讲存储 → 最后怎么用/怎么接 UI”来，每块尽量短。

① 三个概念（配代码看最清楚）

provenance（来源） = 每个节点/边身上记着”我是哪些文档生出来的”那个 `source_docs` 字段。
```json
{"id":"System:SFDC","type":"System","label":"SFDC","source_docs":["doc::ab12","doc::cd34"]}
```

作用：文档一改，靠它定位该动图谱哪部分。回填脚本第一次给它填上，之后增量引擎维护它。

引用计数（reference counting） = 一个节点被几个文档引用，就是 `len(source_docs)`。
作用：决定什么时候能删。
```python
# 删除文档 D：对每个节点
node["source_docs"].discard(D)   # 从来源里划掉 D

if not node["source_docs"]:       # 计数归零 = 没文档再引用它
    delete(node)                  # 才真删；否则保留
```
就像一份共享文件，谁提到它算一个”持有人”，删到最后一个持有人走了才删文件。这就是为什么共享实体不会被误删。

delta（变更量） = “这一次操作改了什么”的清单：加了哪些点/边、删了哪些、哪些只更新了来源。
```json
{"op":"add","doc":"doc::ef56","nodes_added":[...],"nodes_removed":[],"edges_added":[...],"source_docs_changed":[...]}
```
`plan_delta()` 算出它（预演就是给你看这个 delta），`apply_delta()` 执行它。它既是”预演内容”，也是”版本里存的东西”。

② Cosmos DB 用不了 → 能用 AI Search 吗？能，但有取舍

可以。AI Search 本质是”搜索索引”不是图数据库，所以把图谱存成文档：

- 节点存成一类文档（字段：id、type、label、source_docs 可筛选集合），边存成另一类（加 source/target/type）。

- “查某实体的邻居” = 一次带过滤的搜索（`source eq X or target eq X`），多跳就多查几次——遍历要你自己写。

- 更新 = 按 key 重新 upsert 那条；删除 = 按 key 删。引用计数照常（source_docs 当可筛选字段）。

取舍：你已经有 AI Search、不用新服务；但它没有原生图遍历，深层/复杂关系查询慢、要手写。1~2 跳、规模中等完全够用。放进我们那套设计就是——写一个 `AISearchGraphStore` 实现同一个 GraphStore 接口，`runtime` 的 4 个操作不用改。

③ 版本”只记变更”怎么实现

不再每版存整张图，而是：

1. 只保留一份当前图；

2. 每次 apply 往一个只追加的日志写一条 delta（含能”重做”和”撤销”的信息）；

3. 回滚 = 对最近一条 delta反向应用（删的加回来、加的删掉、来源还原）；

4. 偶尔存一个完整快照当检查点，免得从头重放上千条。

```
current_graph.json        ← 当前状态（唯一一份）

changelog/
  0001.delta.json         ← 每次变更
  0002.delta.json

checkpoints/v100.json     ← 每 N 次存个完整快照
```

作用：图大了之后，整图拷贝又慢又占空间，delta 很小。但你现在的全量快照法完全够用，这是”将来变大了”才换的，不急。

④ 这个 skill 我怎么用、怎么测

先说一个你必须知道的实情：现在 kg_sync 是手动触发，而且它操作的是已经入库（有 chunk）的文档。“上传文档就自动增量同步”需要把它挂到入库完成的钩子上——那是我们之前标为”可选 Phase 3”的部分，还没做。所以现在的测法是：文档照常入库 → 你手动跑 kg_sync 对它做增量。

命令（就是 skill 自带的 CLI）：
```bash
# 1 看现状（记住当前节点/边数）
python -m kb_poc.skills.kg_sync --status

# 2 预演新增一个已入库的文档（不写盘，看会加什么）
python -m kb_poc.skills.kg_sync --plan-add "某文档.xlsx"

# 3 确认无误，手动应用
python -m kb_poc.skills.kg_sync --apply --op add --file "某文档.xlsx" --confirm

# 4 再看现状——节点数变了 / 新实体出现了 = 增量成功
python -m kb_poc.skills.kg_sync --status

# 5 想还原
python -m kb_poc.skills.kg_sync --rollback
```

怎么看出成功：第 1 步和第 4 步的节点/边数对比；或 `--plan-add` 报告里的 `+N`；或用图谱查询工具查那个新实体在不在。

⑤ UI 怎么接入看增量 —— 关键看你有没有后端

你问”自然语言还是点按钮、按钮怎么对应 API”，有三种方式，你的离线静态页面决定了用哪种：

方式一·自然语言（Agent）：因为 kg_sync 注册成了工具，Agent 读 SKILL.md 后，你打字”把这个文档同步进图谱”它就会调 `kg_sync_plan/apply`。不需要按钮。

方式二·按钮 → API（需要一个本地后端）：静态 HTML 的按钮不能直接跑 Python，得有个小服务在本机跑：
```javascript
// 前端按钮
btn.onclick = async () => {
  const r = await fetch('/api/kg_sync/plan', {method:'POST',
            body: JSON.stringify({op:'add', file_path:'某文档.xlsx'})});
  renderPlan(await r.json());   // 显示 +N/-M 和待确认新实体
};
```
```python
# 后端（FastAPI）把这个路由连到 skill
@app.post('/api/kg_sync/plan')
def plan(req: KGSyncPlanInput):
    return KGSyncSkillRuntime(settings).kg_sync_plan(req)
```
按钮对应 API 就是这样：按钮 fetch 一个后端路由，路由里调 skill 的方法。但这需要你能在公司机器上起一个本地服务。

方式三·文件法（离线最省事，推荐你先用这个）：不接后端，让 skill 把结果写成 JSON 文件，UI读文件展示——跟你那个评估分析页”载入 JSON”一模一样：

- `kg_sync --status` 写一份 `kg_status.json`；

- `kg_sync --apply` 写新版本图 + 一份 `delta.json`（这次加了/删了什么）；

- 那个图谱可视化页载入”当前图 + delta.json”，把新增节点标绿、删除标红——你当场就看见增量效果了（这正是我之前给你做的”增量变化”视图）。

建议你先这么试（最小闭环）

1. 挑一个已入库文档，跑 `--status → --plan-add → --apply --confirm → --status`，看节点数变化。✅ 先证明引擎能动。

2. 让 skill 把 `delta.json` 和当前图谱导出来，用图谱可视化页载入 → 绿/红高亮看增量。✅ 这就是 UI 端”看见成功”。

3. 想要”点按钮/说句话就同步”再上方式二或一（要起后端或接 Agent）。

你先告诉我：公司机器上能不能起一个本地小服务（后端）？ 能的话我帮你把”按钮→API→skill”这条接起来；不能的话我们就走方式三（文件法），我帮你把 skill 导出 `delta.json` + 可视化页载入这条打通。这决定了接 UI 的具体做法。

---
