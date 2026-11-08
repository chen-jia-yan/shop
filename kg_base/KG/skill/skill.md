---
name: kg_sync
description: >
  知识图谱增量同步。当需要让知识图谱随某个文档的新增、更新或删除而增量更新时使用。
  能预演变更、按引用计数安全增删、版本化落盘并可回滚。不整图重建、不碰检索索引、不删源文件。
when_to_use:
  - 用户要把某个文档的变更同步进知识图谱（新增/更新/删除）
  - 用户想在改动前预览"图谱会怎么变"
  - 用户要查看图谱当前版本、规模或健康度
  - 用户要撤销上一次图谱变更
when_not_to_use:
  - 普通的知识检索 / 问答 → 用 kb_retrieval
  - 重建或入库文档到 Azure 检索索引 → 不属于本 skill
  - 任何需要删除源文件的操作 → 本 skill 永不删源文件
---

# kg_sync 使用说明（面向 Agent）

## 工具清单
- `kg_sync_status` — 只读。返回在用版本、节点/边数、无来源实体数、当前开关。
- `kg_sync_plan` — 预演。输入 `op`(add|update|delete) + `file_path` 或 `doc_id`。**不写盘**，返回变更计数与 `new_entities_for_review`。
- `kg_sync_apply` — 写入。同样的输入 + `confirm=True` 才真正落成新版本。可用 `exclude_entity_ids` 剔除不想要的新实体。
- `kg_sync_rollback` — 回退到上一个/指定版本。

## 标准操作流程（必须按顺序）
1. 先 `kg_sync_status` 了解现状（可选但推荐）。
2. 调 `kg_sync_plan` 预演，把 `report_text` 和 `new_entities_for_review` **原样呈现给用户**。
3. **等待用户明确确认**。若用户要去掉某些规则新实体，收集其 id 放入 `exclude_entity_ids`。
4. 用户确认后，调 `kg_sync_apply` 且 `confirm=True`。
5. 如需撤销，调 `kg_sync_rollback`。

## 硬性规则（不得违反）
- **先预演后写入**：任何 apply 之前必须先 `kg_sync_plan` 并经用户确认。禁止跳过预演直接 apply。
- **confirm 必须来自用户**：没有用户明确同意，不得把 `confirm` 设为 True，也不得"整轮会话一次性授权"。
- **一次只处理一个文档**：不要在未经确认下批量 apply。
- **不碰 Azure 索引、不删源文件、不重新入库**：这些都不在本 skill 职责内，遇到此类请求应拒绝或改走对应流程。
- **规则抽取有噪声**：`new_entities_for_review` 里的实体默认视为"待人工确认"，不要擅自判定其正确性，交给用户裁决。

## 输入填写
- 用户给的是文件名/路径 → 填 `file_path`；给的是 `doc::...` 指纹 → 填 `doc_id`。
- `op`：新增=`add`，内容变化=`update`，移除=`delete`。

## 输出解读
- 计数 `+N / -M / ~K` 分别是新增 / 删除 / 仅更新来源标签。
- `warnings` 非空时必须转述给用户（常见："找不到正文文件→只能匹配已有实体，无法抽新实体"）。
- `kg_sync_apply` 返回 `from_version → to_version`，据此告知用户可用 rollback 回到 `from_version`。

## 失败处理
- `plan` 返回无法解析文档 → 向用户要准确的文件名或 `doc_id`，不要猜。
- 抽取需要新实体但报 warning 缺正文 → 告知用户该文档可能未入库或正文文件缺失，先补齐再同步。
