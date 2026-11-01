## 后端：知识库配置（完整版） 
【任务 K2b】知识库配置调整：去掉两个开关；关系名单改为从 SDK 读取；每个租户可以单独配置 Azure 地址和密钥；禁止写入的索引改为可配置的名单；图谱写入开关默认打开。
（先贴【通用规则】）

【工作目录】C:\Users\234393\Desktop\tap-ai-backend

【本次允许修改的文件】
- src/tap_ai/plugins/extensions/knowledge/ 下的 settings.py、plugin.py、tools.py、prompts.py、spaces.py、backends/neo4j_graph.py、backends/azure_search.py
- src/tap_ai/config/settings.py（只改 library_kb_graph_enabled 这一个字段）
- src/tap_ai/plugins/ingest/sdk_ingest.py
- .env.example
- tests/ 下与上面这些文件对应的测试
- tests/unit/test_library_kb_skeleton.py（只改 library_kb_graph_enabled 默认值的断言：False 改为 True）


【开工前确认（只读）】贴出原始输出
1. knowledge/settings.py 全文
2. plugin.py 中判断"知识库是否启用"、读取 kg_entity_vector、构造 Azure 检索对象的原文
3. backends/azure_search.py 中：endpoint 和 key 从哪里来、按索引名创建 SearchClient 的函数（_client）原文
4. tools.py 中关系枚举、prompts.py 中 RELATION_LEGEND、neo4j_graph.py 中 DEFAULT_RELATION_TYPES 的原文
5. sdk_ingest.py 中：两处 jp-poc 检查（_contains_forbidden_index 的定义和两处调用）、Neo4j 配置不全时报错的原文
6. config/settings.py 中 library_kb_graph_enabled 的原文
7. spaces.py 中 KnowledgeSpace 的定义原文

【要做的 6 件事】

1. 知识库问答不再需要开关
   - 删除 KnowledgeSettings 中"启用知识库"的 bool 字段（字段名以开工前确认第 1 条为准）
   - plugin.py：indexes 映射不为空就加载知识库；为空时返回 None，并打印一条 info 日志"未配置知识库索引映射，知识库未启用"
   - 删除 kg_entity_vector 字段：问答时始终尝试按向量匹配实体。Neo4j 里没有向量索引时，沿用 neo4j_graph.py 现有的处理（打印警告，只按名字匹配），不能报错

2. 关系名单从 SDK 读取
   - 导入写法照抄 sdk_ingest.py 中导入 tap_ingest_sdk 的写法：from tap_ingest_sdk.kg_schema import TRAVERSABLE_RELATIONS, RELATION_ZH
   - kg_relation_types 的默认值改为 tuple(TRAVERSABLE_RELATIONS)。用环境变量覆盖的功能保留（JSON 数组写法）
   - neo4j_graph.py 的 DEFAULT_RELATION_TYPES 改为 tuple(TRAVERSABLE_RELATIONS)
   - tools.py 中关系的 enum 改为 list(TRAVERSABLE_RELATIONS)
   - prompts.py 中 RELATION_LEGEND 改为由 RELATION_ZH 生成，格式："(关系说明: NEXT=流程下一步, HANDLED_BY=由该角色负责, ...)"，只列出 TRAVERSABLE_RELATIONS 中的关系
   - 生成以后，这三处都不允许再出现手写的关系名字符串

3. 每个租户可以单独配置 Azure 地址和密钥
   - knowledge/settings.py 新增：
       class SearchOverride(BaseModel):
           endpoint: str
           api_key: SecretStr
       search_overrides: dict[str, SearchOverride] = {}
     字段上方中文注释：某个租户的索引不在默认 Azure 服务下时，在这里单独配置地址和密钥；没有配置的租户使用 azure_search_endpoint / azure_search_key
   - KnowledgeSpace 追加两个字段：search_endpoint: str、search_key: str（放在最后，带默认值 ""）
   - KnowledgeSpaceResolver.resolve：租户在 search_overrides 里，就用覆盖值；否则用默认值。租户名比较统一转小写
   - azure_search.py：创建 SearchClient 时使用 space.search_endpoint 和 space.search_key，不再直接读全局配置。
     客户端缓存的键改为 (search_endpoint, index_name)，不同服务下同名索引不能共用一个客户端
   - 默认 endpoint 或 key 为空、并且租户也没有覆盖值时，这个租户不启用知识库（resolve 返回 None），打印一条 warning
   - .env.example 追加示例（值用占位符，不得写真实地址和密钥）：
       # 某个租户的索引在另一个 Azure 搜索服务下时使用；JSON 格式
       # TAP_AI_KB_SEARCH_OVERRIDES={"jp":{"endpoint":"https://<服务名>.search.windows.net","api_key":"<只读查询密钥>"}}

4. 禁止写入的索引改为可配置的名单
   - knowledge/settings.py 新增：write_forbidden_indexes: tuple[str, ...] = ("jp-poc",)
     字段上方中文注释：入库、删除时禁止写入的索引名；比较时转小写、完全相等才算命中
   - sdk_ingest.py：
     · 删除"启动时只要映射里有 jp-poc 就报错"的检查（大约第 150 行）
     · 保留"每次写入时检查"（大约第 175 行），改为判断 index_name.lower() 是否在 write_forbidden_indexes 中（同样转小写），错误码和提示保持不变
     · _contains_forbidden_index 函数改为使用这个名单；函数名保留
   - .env.example 追加：# TAP_AI_KB_WRITE_FORBIDDEN_INDEXES=["jp-poc"]

5. 图谱写入开关默认打开，规则改为
   - config/settings.py：library_kb_graph_enabled 默认值改为 True；注释改为"入库时是否同时写知识图谱。本地连接共用的 Neo4j 时请在 .env 中设为 false"
   - sdk_ingest.py：
     · 开关为 True、并且 neo4j_uri 不为空 → 创建 Neo4j 连接，写图谱
     · 开关为 True、但 neo4j_uri 为空 → 不写图谱，打印 info 日志"未配置 Neo4j 地址，入库不写图谱"，不报错
     · neo4j_uri 不为空、但用户名或密码为空 → 保持现在的报错
     · 开关为 False → 不写图谱
   - .env.example 中这一项的说明同步修改
   - sdk_ingest.py 中 getattr(settings, "library_kb_graph_enabled", False) 改为直接读 settings.library_kb_graph_enabled


6. 测试（手写假实现，不连任何服务）
   a. indexes 为空时 plugin.build 返回 None；不为空时不需要任何开关就能加载
   b. KnowledgeSpaceResolver：有覆盖值的租户用覆盖的 endpoint/key；没有覆盖的用默认值；默认值为空且没有覆盖的返回 None；租户名大小写不同也能匹配
   c. 映射里同时有 hk 和 jp-poc 时，入库功能能正常构造（不再报错）；写入 jp-poc 返回 forbidden_index；写入 hk 正常走到 sink
   d. kg_relation_types 默认值等于 SDK 的 TRAVERSABLE_RELATIONS；tools.py 的 enum 和它一致；RELATION_LEGEND 包含每种可遍历关系的中文名
   e. 图谱写入的四种情况（第 5 条）各一个用例
   f. 运行 git grep -n -E "\"NEXT\"|\"HANDLED_BY\"|\"PART_OF\"|\"REQUIRES\"" -- src/tap_ai，贴出原始输出，并逐行说明为什么还保留（应当没有输出，或只剩测试以外不得不保留的地方）

【完成报告】按【通用规则】第五条；另外列出新增的每个测试函数名


## yanshou ￼
1. 全部测试（新窗口，不设环境变量）：

```powershell
cd C:\Users\234393\Desktop\tap-ai-backend
uv run pytest -q 2>&1 | Select-Object -Last 15
```
失败数不比 K2a 之后多。

2. 关系名单已经改成从 SDK 读取：
```powershell
git grep -n -E "\"NEXT\", \"HANDLED_BY\"" -- src

```
要什么都不输出（原来手写的 4 种关系名单都已经去掉）。
**3. 映射里同时有 hk 和 jp，入库不再报错。**在本地 ‎`.env` 里加上这几项（值你自己填，不要发我）：
```
TAP_AI_KB_INDEXES={"hk":"<hk 的索引名>","jp":"jp-poc"}
TAP_AI_KB_SEARCH_OVERRIDES={"jp":{"endpoint":"<jp-poc 所在服务的地址>","api_key":"<jp-poc 的查询密钥>"}}
TAP_AI_LIBRARY_KB_GRAPH_ENABLED=false
```
jp-poc 的地址和查询密钥，在旧项目 jap-cycle-poc 的 ‎`.env` 里找。**用查询密钥（query key），不用管理密钥（admin key）。**旧项目里如果只有管理密钥，先告诉我，我们再想办法。
然后启动后端（你平时怎么启动就怎么启动），看启动日志：
- 不能出现 “禁止写入 jp-poc 索引”
- 能正常启动

**4. 用 jp 身份提问一次。**打开 ‎`http://127.0.0.1:<端口>/docs`，找到新建会话的接口 ‎`POST /tap/ai/conversations/chat`，请求体填：
```json
{"message_content": "<一个 jp-poc 里有答案的问题>", "saas_id": "jp"}
```

返回的内容里能看到引用了 jp-poc 的文档，就说明问答已经能读 jp-poc。把结果告诉我”有引用”或”没有引用”就行，不用发内容。
通过以后提交：
```powershell
git add -A
git commit -m "refactor(kb): 关系名单改由 SDK 提供，租户可单独配置搜索服务，禁止写入名单可配置"
```


