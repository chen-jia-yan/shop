【任务 KG-API 调整】图谱浏览接口联调前调整：节点和边字段统一（保留旧字段，保证兼容）；画布接口支持按类型和文档过滤；切片列表按文档分组；节点不存在时报错；统计接口返回中文名列表；文件列表可搜索。全部只读，不改数据。
（先贴【通用规则】）

【工作目录】C:\Users\234393\Desktop\tap-ai-backend
Python 统一用 C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe。开工先运行
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys, tap_ingest_sdk, neo4j; print(sys.executable)"
贴出输出。不得使用系统 python，不得用 uv run（会同步环境）。下文 <py> 都指这个路径。

【绝对禁止】
- 所有 Cypher 只能用读操作，用只读会话（execute_read）执行；源码中不得出现 CREATE、MERGE、SET、DELETE、REMOVE、DROP
- 用户输入一律作为参数传入 Cypher（$xxx），不得拼接进语句；depth=1 和 depth=2 各写一条固定语句
- 不改 src/tap_ai/plugins/extensions/knowledge/ 下除 backends/kg_browse.py 以外的任何文件（问答是同事的业务）
- 不删除任何已有接口，不删除任何已有返回字段（前端可能在用），只新增或补充
- 不读 .env；不连接外部服务；不安装包；git 只允许只读命令；不对已有文件运行 ruff format

【本次允许修改的文件】
- src/tap_ai/contracts/library_kg.py
- src/tap_ai/plugins/extensions/knowledge/backends/kg_browse.py
- src/tap_ai/application/library_kg.py
- src/tap_ai/api/library_kg.py
- src/tap_ai/api/dto.py（只改图谱相关的类）
- docs/API-文档.md（只改图谱那一节）
- src/tap_ai/config/settings.py（只新增 S0-c 的一项配置）
- tests/unit/test_library_kg_service.py、tests/api/test_library_kg_api.py（只追加；已有用例因本次改动不成立时才改，并逐个说明）
需要改别的文件，停下来告诉我。

【开工前确认（只读，贴原始输出）】
1. api/library_kg.py 全文（9 个路由：scopes/list、stats、graph/overview、nodes/search、nodes/{node_id}、nodes/expand、nodes/chunks/list、files/list、entities/list）
2. 这 9 个接口的请求模型和返回模型原文（dto.py 中对应的类）
3. kg_browse.py 中每个接口对应的函数和 Cypher 原文
4. contracts/library_kg.py 全文
5. git status

==================================================
【统一数据结构（本次以此为准）】

S0 租户上下文与图谱选择（前端在 dit 联调时实际发的就是这种请求体，必须支持）
   前端实际请求示例：
   {"saas_id": "hk", "workspace_id": "29708a0c-...", "project_id": "f30bbd6d-...", "user_id": "tapadmin", "limit": 50}
   a. 新建公共请求基类 KgScopedRequest（dto.py），除 scopes/list 外的 8 个接口的请求模型都继承它：
      saas_id: str | None = None        // 1–64 字符
      workspace_id: str | None = None   // 只接收，不参与查询
      project_id: str | None = None     // 只接收，不参与查询
      user_id: str | None = None        // 只接收，不参与查询
      scope: str | None = None          // 1–200 字符；原来是必填，改为可选
      规则：scope 和 saas_id 至少传一个，否则 422（用 model_validator 校验，错误信息"scope 和 saas_id 至少传一个"）
      模型不得设置 extra="forbid"；按后端已有 DTO 的写法处理多余字段
   b. 解析顺序（写在 application/library_kg.py 的 _resolve_scope 中，中文注释）：
      ① 传了 scope：直接用 scope（两个都传时以 scope 为准）
      ② 只传 saas_id：先查 KnowledgeSettings().indexes（saas_id → 索引名，只读，不修改该类）
      ③ 查不到：再查本模块配置 settings.library_kg_saas_scope_map（默认 {"jp": "jp-poc"}）
      ④ 都查不到：CCB001 "该租户未配置知识图谱"
      saas_id 比较时统一转小写、去首尾空白
      解析出的 scope 仍要通过原有的"scope 是否存在"校验（不存在时 CCB001 "图谱不存在"）
   c. config/settings.py 新增（只加这一项）：
      library_kg_saas_scope_map: dict[str, str] = {"jp": "jp-poc"}
      注释："图谱页面按租户选择图谱时的补充映射；知识库索引映射里查不到时才用。可用 JSON 覆盖"
      对应环境变量 TAP_AI_LIBRARY_KG_SAAS_SCOPE_MAP
   d. nodes/{node_id}（GET）：查询参数同样支持 scope 或 saas_id（两个都是可选的 query 参数，规则同上）
   e. scopes/list：返回不变（已有 saas_ids）；请求体允许带 saas_id 等字段但忽略

S1 节点对象 KgNode（所有返回节点的接口都用它：graph/overview、nodes/expand、nodes/search、entities/list、nodes/{node_id}）
   {
     "id": "System:SFDC",        // 节点编号，原样返回，前端调其他接口时原样传回
     "label": "SFDC",            // 显示名
     "name": "SFDC",             // 旧字段，值与 label 相同，保留兼容，文档中标注"已弃用，请用 label"
     "type": "System",           // 英文类型，筛选时传它
     "type_zh": "系统",          // 中文类型，显示用；查不到中文时等于 type
     "degree": 12                // 与其他实体之间的业务关系数（不含 MENTIONED_IN / HAS_CHUNK）；接口里算不出来的写 null
   }
   接口原来返回的其他节点字段全部保留。

S2 边对象 KgEdge（graph/overview、nodes/expand）
   {
     "id": "...",                // 原来就有的边编号，保留；原来没有的，用 elementId(r)
     "source": "System:SFDC",    // 起点节点 id
     "target": "Data:顧客情報",   // 终点节点 id
     "type": "USES",             // 英文关系类型
     "type_zh": "使用",          // 中文关系名
     "label": "使用"             // 显示名：raw_types 第一个非空值优先，否则等于 type_zh
   }
   原来返回的其他边字段全部保留。

S3 中文名来源（K4c）：contracts/library_kg.py 中
   from tap_ingest_sdk.kg_schema import ENTITY_TYPE_ZH, RELATION_ZH  # type: ignore[import-untyped]
   （导入写法照抄 sdk_ingest.py 里导入 tap_ingest_sdk 的写法）。后端不再手写任何中文类型名。
   业务关系白名单 BUSINESS_RELATION_TYPES = tuple(RELATION_ZH.keys())（含 RELATED_TO，不含 MENTIONED_IN、HAS_CHUNK），作为 Cypher 参数 $business_types 传入。

S4 过滤参数（graph/overview、nodes/expand、entities/list、nodes/search 共用，字段名、含义、校验完全一致）
   "entity_types":   ["System", "Process"]   // 可选；不传或 null = 不过滤
   "relation_types": ["USES", "NEXT"]        // 可选；不传或 null = 不过滤（entities/list、nodes/search 没有这个参数）
   "document_id":         "doc::ab12..."           // 可选；不传或 null = 不过滤；值来自 files/list 返回的文档编号
   校验（用 pydantic，不通过时由框架返回 422，与后端其他接口一致）：
   - 列表长度 1–20；空列表 [] 不合法（前端全部取消勾选时不要调接口，直接清空画布）
   - 每项匹配 ^[A-Za-z_]{1,40}$；自动去重，保持原顺序
   - document_id 长度 1–200
   - 不校验"类型是否存在"：不存在的类型只是查不到数据，不报错（原因：库里实际出现的类型可能多于 SDK 定义）
   entities/list 原来的参数名 types 保留兼容：用 Field(validation_alias=AliasChoices("entity_types", "types"))，两种写法都能用，文档写 entity_types，注明 types 已弃用。

S5 过滤语义（Cypher 中全部用参数和 "$x IS NULL OR ..." 的写法）
   - entity_types：节点类型必须在列表中；边的两端都必须保留，边才保留
   - relation_types：只保留这些类型的边
   - document_id：只保留"出现在该文档的切片中"的实体，即
     EXISTS { (n)-[:MENTIONED_IN]->(:Chunk {scope: $scope, document_id: $document_id}) }
   - 多个条件同时传时取交集
   - nodes/expand 的中心节点永远保留，即使它的类型不在 entity_types 里（用户点的就是它）

S6 truncated：画布接口取 limit + 1 条边；超过 limit 时只返回前 limit 条，并返回 truncated=true，否则 false。

S7 节点不存在：nodes/{node_id}、nodes/expand、nodes/chunks/list 传入的 node_id 在该 scope 中查不到 Entity 时，抛 BusinessError，返回 CCB001 "节点不存在"（不要返回空列表）。

==================================================
【要做的 7 件事】

1. contracts/library_kg.py：按 S3 导入中文名，新增 BUSINESS_RELATION_TYPES；新增 KgNode、KgEdge 的数据结构（写法照抄文件里已有的数据结构）；新增两个小函数并写中文注释：
   - entity_type_zh(t: str) -> str：查 ENTITY_TYPE_ZH，查不到返回 t
   - edge_label(rel_type: str, raw_types: list[str] | None) -> str：raw_types 第一个非空字符串，否则 RELATION_ZH.get(rel_type, rel_type)

2. stats：返回结构中原有字段全部保留，新增：
   "entity_types":   [{"type": "System", "type_zh": "系统", "count": 120}, ...]   // 按 count 降序，再按 type 升序
   "relation_types": [{"type": "USES", "type_zh": "使用", "count": 300}, ...]   // 只统计 BUSINESS_RELATION_TYPES，按 count 降序
   用途：左侧"类型图例 / 过滤"面板的勾选项和数量。

3. graph/overview：
   请求体（原有参数保留，新增 S4 的三个过滤参数）：
   {
     "scope": "jp-poc",
     "limit": 300,                  // 原有；最大边数
     "entity_types": ["System", "Process"],
     "relation_types": ["USES"],
     "document_id": null
   }
   查询逻辑（固定语句，参数化）：
   MATCH (a:Entity {scope: $scope})-[r]->(b:Entity {scope: $scope})
   WHERE type(r) IN $business_types
     AND ($relation_types IS NULL OR type(r) IN $relation_types)
     AND ($entity_types IS NULL OR (a.type IN $entity_types AND b.type IN $entity_types))
     AND ($document_id IS NULL OR (EXISTS { (a)-[:MENTIONED_IN]->(:Chunk {scope: $scope, document_id: $document_id}) }
                          AND EXISTS { (b)-[:MENTIONED_IN]->(:Chunk {scope: $scope, document_id: $document_id}) }))
   按 coalesce(r.weight, 1) 降序取 $limit + 1 条
   节点 = 这些边的两端（去重）
   补充规则：如果一条边都没有，但符合 entity_types / document_id 的实体存在，则返回这些实体中 degree 最高的前 min(limit, 100) 个作为孤立节点，edges 为空（避免画布空白）
   返回体：{"nodes": [KgNode...], "edges": [KgEdge...], "truncated": false}（原有字段保留）

4. nodes/expand：
   请求体（原有参数保留，新增 relation_types、entity_types）：
   {
     "scope": "jp-poc",
     "node_id": "System:SFDC",
     "depth": 1,                    // 原有，1 或 2
     "limit": 200,                  // 原有，最大边数
     "entity_types": null,
     "relation_types": ["USES", "REQUIRES"]
   }
   查询逻辑：先确认中心节点存在（S7）；depth=1、depth=2 各一条固定语句：
   MATCH (c:Entity {scope: $scope, id: $node_id})
   MATCH p = (c)-[*1..1]-(n:Entity {scope: $scope})        // depth=2 的语句写 *1..2
   WHERE ALL(r IN relationships(p) WHERE type(r) IN $business_types
                                    AND ($relation_types IS NULL OR type(r) IN $relation_types))
     AND ALL(x IN nodes(p)[1..] WHERE $entity_types IS NULL OR x.type IN $entity_types)
   UNWIND relationships(p) AS r WITH DISTINCT r
   按 coalesce(r.weight, 1) 降序取 $limit + 1 条
   返回体：{"center_id": "System:SFDC", "nodes": [...含中心节点...], "edges": [...], "truncated": false}（原有字段保留）
   用途：右侧"展开邻居"按钮，和"相邻节点"列表。

5. nodes/chunks/list 改为"按文档分组"：
   请求体：
   {
     "scope": "jp-poc",
     "node_id": "entity::123",      // 必填
     "document_id": null,                // 可选：不传 = 文档分组模式；传 = 文档内模式
     "page": 1,                     // ≥1
     "page_size": 20,               // 1–100；文档分组模式下是"每页文档数"，文档内模式下是"每页切片数"
     "chunks_per_doc": 3            // 1–10，默认 3；只在文档分组模式下生效
   }
   切片对象 KgChunk：
   {
     "chunk_id": "1305a76fed20",
     "page_or_sheet": "slide-5",
     "preview": "1-2. 代理店手数料の概要……",   // Chunk.preview，截到前 200 个字符；没有时为 ""
     "has_content": true,                          // preview 非空为 true
     "source_file": "...",                         // 旧字段保留
     "label": "...",                               // 旧字段保留，值改为与 preview 相同（没有时为 chunk_id，与原来一致）
     "direction": "entity_to_chunk"                // 旧字段保留，文档中标注"已弃用"
   }
   文档分组对象 KgChunkGroup：
   {
     "document_id": "doc::ab12...",       // Chunk.document_id；没有的切片归到 document_id = "" 一组
     "source_file": "#06_新契約システム概要.pptx",   // 优先取 Document 节点的 filename / source_file，取不到用该组第一个切片的 source_file；document_id 为 "" 时写 "未知文档"
     "chunk_total": 5,               // 该文档中提到此节点的切片总数
     "chunks": [KgChunk...],
     "has_more": true                // chunk_total > 本次返回的 chunks 数
   }
   返回体：
   {
     "items": [KgChunkGroup...],
     "total": 3,                     // 文档分组模式 = 文档数；文档内模式 = 该文档的切片数
     "page": 1,
     "page_size": 20,
     "chunk_total": 9,               // 提到此节点的切片总数（所有文档合计）
     "mode": "by_document"           // 或 "in_document"
   }
   实现：
   a. 先按 S7 确认节点存在
   b. 文档分组模式：
      第一步 Cypher：MATCH (e:Entity {scope: $scope, id: $node_id})-[:MENTIONED_IN]->(c:Chunk {scope: $scope})
                    WITH coalesce(c.document_id, "") AS document_id, count(c) AS n
                    RETURN document_id, n ORDER BY n DESC, document_id ASC SKIP $skip LIMIT $page_size
                    （另一条语句算文档总数和切片总数）
      第二步 Cypher：取这一页文档里提到此节点的全部切片（chunk_id、document_id、page_or_sheet、preview、source_file），以及这些文档的 Document 节点名称
      第三步 Python：每组切片按"页码自然顺序"排序后取前 chunks_per_doc 条
   c. 文档内模式：只查该 document_id 的切片，全部按自然顺序排序后按 page / page_size 分页；items 只有一组
   d. 页码自然顺序：写一个函数 _page_sort_key(page_or_sheet, chunk_id)：取 page_or_sheet 中最后一段数字作为整数排序（slide-5 < slide-11），没有数字的排在有数字的后面并按字符串排序，最后按 chunk_id 排序。写中文注释
   e. 文档组的排序：切片数降序，相同时按 document_id 升序（保证翻页稳定）

6. 其他：
   a. nodes/{node_id}：路由改为 {node_id:path}（编号中可能有 / ），按 S7 报错；返回的节点按 S1 补字段；properties 中去掉 embedding、label_norm、doc_ids 这类内部字段，其余保留
   b. nodes/search：keyword 仍必填；新增可选 entity_types；返回节点按 S1
   c. entities/list：参数按 S4（types 兼容）；新增可选 document_id；返回节点按 S1
   d. files/list：新增可选 keyword（1–100 字符），按文件名包含匹配，不区分大小写（toLower(...) CONTAINS toLower($keyword)）
   e. docs/API-文档.md：图谱一节按本次结构重写每个接口的请求体、返回体、字段含义、示例；写明"422 = 参数不合法；200 + code≠成功 = 业务错误（如图谱不存在、节点不存在）"；写明 name、direction、types 已弃用但仍可用

7. 测试（用假的会话 / 假 driver，不连 Neo4j）：
   a. 9 个接口的返回中，节点都有 id、label、name、type、type_zh；边都有 source、target、type、type_zh、label
   b. RELATED_TO 边：raw_types=["支撑"] 时 label="支撑"；raw_types 为空时 label="相关"
   c. 过滤参数：传 [] → 422；传 "Sys tem" → 422；传重复值自动去重；entities/list 用 types 和 entity_types 都能用
   d. overview：过滤参数被作为参数传给 Cypher（检查 driver 收到的参数）；语句里没有拼接用户输入；无边时返回孤立节点
   e. expand：中心节点不在 entity_types 中仍然返回；depth=1 和 depth=2 用的是两条不同的固定语句
   f. truncated：返回 limit+1 条时 truncated=true 且只返回 limit 条
   g. chunks/list：
      - 两个文档各 5 条、2 条切片，chunks_per_doc=3：两组，第一组 chunk_total=5、返回 3 条、has_more=true；第二组返回 2 条、has_more=false；total=2，chunk_total=7，mode=by_document
      - 传 document_id：mode=in_document，按 page_size 分页
      - 排序：slide-2、slide-11、slide-1 → slide-1、slide-2、slide-11
      - preview 超过 200 字符被截断；没有 preview 时 preview=""、has_content=false、label=chunk_id
      - 没有 document_id 的切片归到"未知文档"组
   h. 节点不存在：detail、expand、chunks/list 都返回 CCB001 "节点不存在"
   i. stats：entity_types、relation_types 按 count 降序，type_zh 正确；relation_types 不含 MENTIONED_IN
   j. 原有测试"源码中无写关键字""除 scopes 外 Cypher 都含 $scope"仍然通过
   k. S0：
      - 用前端实际请求体 {"saas_id":"hk","workspace_id":"...","project_id":"...","user_id":"tapadmin","limit":50} 调 graph/overview：不报 422，解析到 hk 的 scope
      - saas_id="JP "：解析到 jp-poc（走补充映射）
      - 知识库索引映射里有 jp 时优先用索引映射
      - scope 和 saas_id 都传：以 scope 为准
      - 都不传：422
      - 未配置的 saas_id：CCB001 "该租户未配置知识图谱"
      - 旧写法 {"scope":"jp-poc","document_id":null,"types":null,"limit":300} 仍然可用

【验证（贴原始输出）】
a. & <py> -m pytest -q tests/unit/test_library_kg_service.py tests/api/test_library_kg_api.py 2>&1 | Select-Object -Last 15
b. & <py> -m pytest -q 2>&1 | Select-Object -Last 15（失败数不得比修改前多；修改前先跑一次记下数字）
c. & <py> -m ruff check src/tap_ai/contracts/library_kg.py src/tap_ai/plugins/extensions/knowledge/backends/kg_browse.py src/tap_ai/application/library_kg.py src/tap_ai/api/library_kg.py src/tap_ai/api/dto.py tests/unit/test_library_kg_service.py tests/api/test_library_kg_api.py
d. & <py> -m mypy src/tap_ai/contracts/library_kg.py src/tap_ai/application/library_kg.py src/tap_ai/api/library_kg.py
e. git grep -n -E "CREATE|MERGE|SET |DELETE|REMOVE|DROP" -- src/tap_ai/plugins/extensions/knowledge/backends/kg_browse.py   要求无输出
f. git diff --stat 和 git status：只能出现允许的文件
g. & <py> C:/Users/234393/Desktop/check_chars.py src tests docs

【完成报告】按【通用规则】第五条；另外：
- 每个接口贴一个"请求体 + 返回体"示例（用测试里的假数据）
- 改过的已有测试，逐个写"原来断言什么、为什么不成立、改成什么"

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–5 | | |
| S0a–S0e | | |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5a–5e | | |
| 6a–6e | | |
| 7a–7j | | |
| 验证 a–g | | |
