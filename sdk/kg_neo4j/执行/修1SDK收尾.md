import subprocess, sys, types
sys.path.insert(0, "src")
raw = subprocess.check_output(["git", "show", "HEAD:fwd-tap-ingest/src/tap_ingest_sdk/kg_schema.py"])
old = types.ModuleType("old_kg_schema")
sys.modules["old_kg_schema"] = old
exec(compile(raw.decode("utf-8"), "old_kg_schema", "exec"), vars(old))
import tap_ingest_sdk.kg_schema as new
names = ["ENTITY_TYPES", "RELATION_TYPES", "ENTITY_TYPE_NAMES", "ENTITY_TYPE_ZH", "RELATION_ZH",
         "TRAVERSABLE_RELATIONS", "SCHEMA_ALLOWED_RELATIONS", "SCHEMA_LLM_RELATION_MAP"]
for name in names:
    a = getattr(old, name, "<missing>")
    b = getattr(new, name, "<missing>")
    print(name, "SAME" if repr(a) == repr(b) else "DIFFERENT")



【任务 修K1a】修复 K1a 遗留的 4 个 SDK 测试失败：2 个改代码，2 个按新设计更新旧测试。不新增功能。

【工作目录】C:\Users\234393\fwd-tap-common\fwd-tap-ingest
开工先运行 git branch --show-current，必须是 feature/tap-10366。
Python 用当前已激活环境的 python（先运行 (Get-Command python).Source 贴出路径）。

【绝对禁止】
- 不读 .env；不连接外部服务；不安装任何包
- git 只允许 status / diff / log / show / grep / ls-files / branch --show-current
- 不改 pyproject.toml、uv.lock；不对已有文件运行 ruff format
- 不改 kg_schema.py 和 sinks/_kg_schema.py 的任何内容
- 只允许修改下面点名的测试函数，其他测试一个字都不改；不允许用 skip / xfail / 删除测试来"通过"

【本次允许修改的文件】
- src/tap_ingest_sdk/sinks/_neo4j.py
- src/tap_ingest_sdk/sinks/_kg_llm_extract.py
- tests/test_kg_and_chunk_index.py（只限 test_neo4j_sink_upsert_and_delete、test_neo4j_sink_drops_relations_outside_whitelist、test_neo4j_sink_upsert_passes_now_preview_and_raw_type 这 3 个函数）
- tests/test_kg_llm_extract.py（不允许修改，只读）

【开工前确认（只读，贴原始输出）】
1. python -m pytest -q tests/test_kg_and_chunk_index.py tests/test_kg_llm_extract.py --tb=short 2>&1 | Select-Object -Last 60
2. 上面 4 个失败测试函数的完整原文
3. tests/test_kg_llm_extract.py 中该测试用的 reply（模型回复的假数据）原文
4. _kg_llm_extract.py 中 _to_specs（或负责把模型回复转成 RelationSpec 的函数）全文
5. _neo4j.py 中 upsert 全文、_write_relations 全文、所有 Cypher 常量的名字和它们需要的参数名
6. 对第 3 个失败测试：列出测试里 writes 包含的每一条语句（常量名），并标出哪几条参数里没有 now

【统一规则（本次以此为准）】
R1 大模型回复转关系：起点和终点都必须出现在本次回复的实体列表中，且实体类型不为空、关系说法不为空，否则丢弃。实体列表里没有的实体，绝不能凭关系里的信息临时生成
R2 写图时关系类型的处理：
   - 类型名不在 RELATION_ZH 的键里（例如 OWNS）：丢弃，打印警告（防止把任意字符串拼进 Cypher）
   - 类型名合法，但端点类型组合不在 ALLOWED_RELATIONS 中：降级为 RELATED_TO，raw_type 记为原类型名
   - 合法且组合允许：按原类型写入
   - RELATED_TO 本身：照常写入
R3 时间：所有新建或更新 Document、Chunk、Entity、MENTIONED_IN、实体间关系的语句都必须带 now 参数；只做撤销或删除的语句不需要

【要做的 4 件事】
1. test_extractor_drops_relations_when_entity_missing_or_type_blank：按 R1 修改 _kg_llm_extract.py，测试不改
2. test_neo4j_sink_upsert_passes_now_preview_and_raw_type：
   - 开工确认第 6 条中，如果有"写入语句"缺 now → 按 R3 改 _neo4j.py，测试不改
   - 如果缺 now 的只有撤销或删除语句 → 只改测试里 writes 的筛选条件，使它只包含写入语句，断言内容不变
   - 两种情况都在报告里写明是哪条语句、选了哪种处理
3. test_neo4j_sink_drops_relations_outside_whitelist：
   - 先按开工确认第 5 条，说明现在的代码对测试数据中每一条关系是怎么处理的（丢弃 / 降级 / 原样写入）
   - 代码行为和 R2 不一致的，改 _neo4j.py
   - 测试改为按 R2 断言：不出现非法类型名（如 OWNS）的写入语句；端点不允许的那条以 RELATED_TO 写入，且 raw_type 等于原类型名；函数名不改，在函数开头加一行中文注释说明"白名单外的关系不再全部丢弃，规则见 R2"
4. test_neo4j_sink_upsert_and_delete：
   - 先说明 stmts[3] 现在是哪条语句、参数结构是什么
   - 只改测试：从新的参数结构中取出所有切片编号，断言集合与 chunks 的 chunk_id 完全一致；如果顺序也有意义就按顺序断言
   - 测试里其他断言不变

【验证（贴原始输出）】
a. python -m pytest -q tests 2>&1 | Select-Object -Last 15   要求 0 failed、0 error
b. python -m ruff check src/tap_ingest_sdk/sinks/_neo4j.py src/tap_ingest_sdk/sinks/_kg_llm_extract.py tests/test_kg_and_chunk_index.py
c. git diff --stat 和 git status：只能出现允许的文件（fwd-tap-common | 0 那一行是子仓库，忽略，不处理）
d. uv run python C:/Users/234393/Desktop/check_chars.py src tests（路径用 SDK 的绝对路径）

【完成报告】按【通用规则】第五条；对每个改过的测试写出"原来断言什么、为什么不成立、改成什么"

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–6 | | |
| 1 | | |
| 2（写明选了哪种情况） | | |
| 3 | | |
| 4 | | |
| a–d | | |
