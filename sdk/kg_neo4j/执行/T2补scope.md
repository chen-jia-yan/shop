【任务 T2-补】图谱接口的作用域（scope）列表：没有实体、只有文档和切片的图谱（如 hk）也要能切换；同时返回它对应的租户 saas_id。仍然全部只读。
（先贴【通用规则】）

【背景】
现在 scopes/list 只从 Entity 节点上取 scope。hk 目前在 Neo4j 里只有 Document 和 Chunk 节点、没有 Entity，所以列表里只有 jp-poc。
Neo4j 里存的是 scope（等于 Azure 索引名），没有存 saas_id；saas_id → 索引名 的对应关系只在配置 TAP_AI_KB_INDEXES 里。
所以改成：scope 列表 = Neo4j 里实际出现过的 scope（Entity、Chunk、Document 三种节点都算）∪ 配置里映射到的索引名；每一项带上对应的 saas_id。

【工作目录】C:\Users\234393\Desktop\tap-ai-backend

【绝对禁止】
- 不改 src/tap_ai/plugins/extensions/knowledge/ 下除 backends/kg_browse.py 以外的任何文件；KnowledgeSettings 只允许"读取"，不允许修改
- 所有 Cypher 只能用读操作，用只读会话执行；不得出现 CREATE、MERGE、SET、DELETE、REMOVE、DROP
- 不读 .env；不连接任何外部服务；git 只允许只读命令

【本次允许修改的文件】
- src/tap_ai/contracts/library_kg.py
- src/tap_ai/plugins/extensions/knowledge/backends/kg_browse.py
- src/tap_ai/application/library_kg.py
- src/tap_ai/api/library_kg.py
- src/tap_ai/api/dto.py（只改图谱 scope 相关的那几个类）
- src/tap_ai/bootstrap.py（只改创建 LibraryKgService 的那几行，把映射传进去）
- docs/API-文档.md（只改 scopes/list 那一节）
- tests/unit/test_library_kg_service.py、tests/api/test_library_kg_api.py

【开工前确认（只读，贴原始输出）】
1. kg_browse.py 中 scopes 列表和统计的 Cypher 原文，以及对应函数原文
2. application/library_kg.py 中 scope 校验、缓存 60 秒的原文
3. bootstrap.py 中创建 LibraryKgService 的原文
4. dto.py 中 scopes/list 返回模型的原文

【要做的 5 件事】

1. kg_browse.py：scope 列表改为三种节点的并集（固定语句，不拼接）：
   MATCH (e:Entity) WHERE e.scope IS NOT NULL RETURN DISTINCT e.scope AS scope
   UNION
   MATCH (c:Chunk) WHERE c.scope IS NOT NULL RETURN DISTINCT c.scope AS scope
   UNION
   MATCH (d:Document) WHERE d.scope IS NOT NULL RETURN DISTINCT d.scope AS scope
   每个 scope 的统计照旧（entity_count、relation_count、chunk_count、document_count、last_updated），没有的算 0 / null

2. bootstrap.py：创建 LibraryKgService 时，读取 KnowledgeSettings().indexes（saas_id → 索引名），整理成"索引名 → saas_id 列表"传进去（都转小写）。KnowledgeSettings 只读，不改

3. application/library_kg.py：
   - 返回列表 = Neo4j 里出现的 scope ∪ 配置映射里的索引名，去重后按 scope 排序
   - 每一项新增两个字段：
     · saas_ids：对应的租户列表（配置里没有就是 []）
     · has_graph：entity_count > 0
   - 配置里有、Neo4j 里还没有数据的 scope 也要返回，计数都是 0
   - 其他 6 个接口的 scope 校验改用这个新列表；缓存 60 秒不变
   - 请求参数不变，仍然用 scope；不新增按 saas_id 查询的参数

4. dto.py、docs/API-文档.md 同步新增的两个字段，并在文档里写明：
   "scope 是 Neo4j 中的数据隔离标识，等于 Azure 索引名；saas_ids 是配置中映射到它的租户。has_graph 为 false 表示该图谱暂时只有文档和切片、没有实体，前端可以提示'暂无实体关系，可在文档列表中查看'"

5. 测试（用假实现，不连 Neo4j）：
   a. Neo4j 中只有 Document/Chunk 的 scope（模拟 hk）：出现在列表里，has_graph=false，entity_count=0
   b. 只在配置里、Neo4j 里没有任何数据的 scope：出现在列表里，计数全为 0
   c. 只在 Neo4j 里、配置里没有的 scope（模拟 jp-poc 未加映射）：出现在列表里，saas_ids=[]
   d. 配置里两个租户映射到同一个索引：saas_ids 有两个
   e. 对 a 中的 scope 调 overview、documents/list：正常返回，不报"图谱不存在"
   f. 不存在的 scope：仍然返回 CCB001 "图谱不存在"
   g. 原有的"Cypher 不含写关键字""除 scopes 外都含 $scope"两个测试仍然通过

验证：uv run pytest -q tests/unit/test_library_kg_service.py tests/api/test_library_kg_api.py；uv run pytest -q 全量（失败数不增加）；ruff、mypy 只列本次文件的问题；check_chars；git diff --stat 只能出现允许的文件

【完成报告】按【通用规则】第五条；另外贴出 scopes/list 新的返回示例

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–4 | | |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5a–5g | | |
