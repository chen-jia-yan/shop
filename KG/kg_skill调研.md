目标：实现一个生产级知识图谱同步 skill「kg_sync」，放在 kb_poc/skills/kg_sync/，规格对齐现有 skills（rag_eval、kb_retrieval）。核心设计：接口与实现分离——skill 只依赖「GraphStore 存储接口」和「EntityExtractor 抽取接口」两个抽象，现在用 JSON 存储 + 规则抽取，将来换图数据库 + LLM 抽取时调用方不变。

全程硬约束：不碰 Azure 检索索引；绝不删源文件；所有写操作走版本化、可回滚、原子写；功能开关默认关（不开则行为与现状完全一致）；apply / rollback / 删除由我手动执行，你只给命令和 diff，不自动跑；离线 $0，默认不调 LLM。

=== 阶段 A · 只读调研（先做，停下给我看）===
不写任何文件。查清并给出文件:行号证据：
1. 现有 kg_incremental.py 的增删改、版本、manifest、回滚是怎么实现的？列出可复用的函数。
2. kg_extractor.py 的输入输出接口（喂什么、吐什么结构、哪步调 LLM）。
3. 离线下如何拿到「某文档所有 chunk 的正文文字」？从哪取。
4. skills 框架规范：一个 skill 的 runtime / 注册（tool_registry、tool_schemas）长什么样，照抄这个规格。
5. 当前实体节点/边/来源标签的真实字段结构。
→ 输出简短调研，停。

=== 阶段 B · 骨架（接口 + 存储 + 规则抽取 + 合并 + 版本）===
在 kb_poc/skills/kg_sync/ 新建：
1. interfaces.py：GraphStore（load/save_version/get_active/set_active/list_versions）、EntityExtractor（extract(chunks)->SubGraph）两个抽象基类。
2. schemas.py：Pydantic 定义 DocRef、SyncPlan（含 new_entities_for_review 单列）、SyncResult、KGStatus。
3. stores/json_store.py：实现 GraphStore 的 JSON 全量快照版（复用现有 kg_incremental 的版本/manifest 逻辑），原子写（临时文件+改名）。
4. extractors/rule_extractor.py：离线免费的规则抽取——① 用现有全部实体 label + 可编辑 aliases.json 做词典匹配连已有实体；② 结构化规则抽新实体（如画面ID 正则，先把你归纳的模式列给我确认再写死）；③ 同 chunk 共现建弱关联边，标 provenance_inferred=true；带类型语义关系判不准就留空。产物都带 source_docs。
5. merger.py：ProvenanceMerger，按 source_docs 做引用计数的合并与清理（归零才删、清悬空边）。
6. resolver.py：DocResolver，文件↔doc 指纹、离线列 chunk。
配套单元测试：用小的内存 fixture 图谱，绝不碰真图、不碰 Azure。覆盖 新增已有实体只加来源 / 删除归零才删 / 共享实体不误删 / 幂等重复新增空操作 / 回滚一致。
→ 停。

=== 阶段 C · 对外 API + CLI + 注册 ===
1. runtime.py：KGSyncRuntime 暴露 status()、plan_add()、plan_update()、plan_delete()、apply(plan, confirm)、rollback(version)。plan_* 只预演不写盘，输出 SyncPlan 报告（分三栏：连上的已有实体 / 待确认的规则新实体 / 新建关系）。
2. config.py：开关 KB_KGSYNC_ENABLED(默认关)、KB_KGSYNC_EXTRACTOR=rule|llm(默认rule)、KB_KGSYNC_STORE=json|gremlin(默认json)、KB_KGSYNC_AUTO_APPLY(默认否)。
3. extractors/llm_extractor.py：把现有 kg_extractor.py 包成 EntityExtractor 接口，仅当开关=llm 时启用。
4. cli.py：python -m kb_poc.skills.kg_sync，支持 --status / --plan-add / --plan-delete / --apply / --rollback；--apply 必须显式且打印确认提示。
5. 在 tool_registry、tool_schemas 注册。
给我一个端到端 dry-run 演示（预演新增+删除一个已有文档），active 和 manifest 不变。
→ 停，我手动 apply。

=== 阶段 D · 生产件 ===
1. 结构化日志 + 每次运行一份变更报告 + 关键计数指标。
2. 运行锁（防并发同步互相覆盖）；apply 前自动备份当前版本。
3. status() 健康检查：在用版本、节点/边数、unresolved 数、有无悬空引用。
4. stores/gremlin_store.py：实现 GraphStore 接口的 Azure Cosmos DB(Gremlin) 占位版（可先留 NotImplemented 的清晰骨架 + 映射说明：节点→顶点、边→边、source_docs→属性），证明「换存储不改 runtime」。
→ 停。

交付顺序：A→停→B→停→C→停→我手动 apply→D→停。每个停止点等我确认，不要连跑。