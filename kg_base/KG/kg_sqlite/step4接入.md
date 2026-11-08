目标：把 SqliteGraphStore 接入 kg_sync 的 runtime 和图谱加载器，并新增只读的「待同步清单」工具。全程用开关控制，默认关闭——不开启时系统行为与现在完全一致。
硬约束：不碰 Azure；只读挂载 state.db（file:...?mode=ro, uri=True），绝不写 state.db；已确认 doc_id = 'doc::' || substr(file_hash,1,16)；改动走 plan mode 给 diff；apply/rollback 仍由人工执行。

1. runtime 接入：
   - kg_sync 的 runtime 在环境变量 KB_KGSYNC_STORE=sqlite 时，使用 SqliteGraphStore；否则维持现状。

2. 加载器接入（关键，默认关）：
   - 改 get_default_kg()：当 KB_KGSYNC_STORE=sqlite 且 data/kg/kg.db 存在时，从 SqliteGraphStore.load_graph() 加载图谱；否则【完全保持现有逻辑不变】（继续读 provenance.json 等）。
   - apply_plan / rollback 成功后，清空内存缓存，使下次查询重新从 kg.db 加载。
   - 默认 KB_KGSYNC_STORE 不等于 sqlite，即默认仍走老 JSON，不改变任何现有行为。

3. 新增只读工具 kg_sync_pending()（不写任何数据）：
   - 只读挂载 state.db，对比它和 kg.db，输出三份清单：
     · 待新增：state.db 里状态为完成、但其 doc_id（'doc::'||substr(file_hash,1,16)）在 kg_node_sources 中不存在的文件；
     · 待更新：同一个文件（按 path 的 basename 对应图谱 Chunk 节点的 source_file），state.db 当前算出的 doc_id 与图谱里记录的该文件 doc_id 不一致的；
     · 待删除：图谱 source_docs 里存在、但 state.db 里已无对应 file_hash 的 doc_id。
   - 每类给出文件名清单和条数。注册为 kg_sync 的一个工具。

4. 新增 scripts/kg_report.sql（只读查询集，供我用 sqlite3 命令行直接看）：
   每个文件贡献的实体数/Chunk 数、某实体来自哪些文件、引用计数最高的 20 个实体、无来源的实体、最近 20 条 changelog。

5. 新增 scripts/kg_export_json.py：把 kg.db 导出为与原图谱同结构的 JSON（供图谱可视化页面载入）；可选导出某条 changelog 的 delta 用于页面高亮。

6. 不要动 v1~v9 和任何现有 JSON 文件。归档由我后续手动做。

给我 diff；并在不开启 sqlite 开关的情况下确认现有查询行为无变化。停。