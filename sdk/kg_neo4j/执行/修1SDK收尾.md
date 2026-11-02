Set-Location C:\Users\234393\Desktop\tap-ai-backend
uv pip install --offline -e C:\Users\234393\fwd-tap-common\fwd-tap-ingest
python -c "import tap_ingest_sdk; print('ok')"


【任务 修K1a-补】把"时间"测试改成真正有效的检查；不合法关系类型补警告和测试；重跑 SDK 全量测试。

【工作目录】C:\Users\234393\fwd-tap-common\fwd-tap-ingest
Python 用当前已激活环境的 python（先运行 (Get-Command python).Source 贴出路径）

【绝对禁止】
- 不读 .env；不连接外部服务；不安装任何包
- git 只允许 status / diff / log / show / grep / ls-files / branch --show-current
- 不改 kg_schema.py、sinks/_kg_schema.py、_kg_llm_extract.py
- 只允许修改下面点名的 2 个测试函数；不允许 skip / xfail / 删除测试

【本次允许修改的文件】
- src/tap_ingest_sdk/sinks/_neo4j.py
- tests/test_kg_and_chunk_index.py（只限 test_neo4j_sink_upsert_passes_now_preview_and_raw_type、test_neo4j_sink_drops_relations_outside_whitelist）

【开工前确认（只读，贴原始输出）】
1. git grep -n -E "MERGE|\$now|DETACH DELETE" -- src/tap_ingest_sdk/sinks/_neo4j.py
2. 列一张表：_neo4j.py 中每一个 Cypher 常量（以及 _write_relations 生成的关系写入语句）→ 是"写入（含 MERGE）"还是"撤销 / 删除" → 语句里有没有 $now
3. 修K1a 第 2 件事当时是哪条语句的参数缺 now、为什么

【要做的 3 件事】
1. test_neo4j_sink_upsert_passes_now_preview_and_raw_type：
   - writes 的筛选条件改为：if "CYPHER 25 " in q and "MERGE" in q
     （按"是不是写入语句"来筛，不能再用"$now" in q 来筛）
   - 断言 writes 不为空，且至少包含：HAS_CHUNK 的语句、MENTIONED_IN 的语句、实体间关系（"MERGE (a)-[e:"）的语句
   - assert all("now" in params for _, params in writes) 保留
   - 其余断言不变
   - 如果改完后失败，说明某条写入语句确实缺 now：去 _neo4j.py 给这条语句补上（新建时写 created_at、每次写 updated_at，用 $now），不能再改测试筛选条件绕过

2. _neo4j.py：关系类型名不合法、或不在 ALLOWED_RELATIONS 的键里（且不是 RELATED_TO）时，在 return None 之前 logger.warning("忽略未知关系类型: %s", rel)。没有 logger 的话照文件里已有写法加一个；已经有就直接用

3. test_neo4j_sink_drops_relations_outside_whitelist：
   - 在测试数据里追加一条关系类型为 "OWNS" 的关系（端点用已有的实体）
   - 追加断言：driver.calls 中没有任何语句包含 "e:OWNS"；caplog 中有"忽略未知关系类型: OWNS"
   - 原有断言不变

【验证（贴原始输出）】
a. python -m pytest -q tests 2>&1 | Select-Object -Last 15   必须是全量，要求 0 failed、0 error
b. python -m ruff check src/tap_ingest_sdk/sinks/_neo4j.py tests/test_kg_and_chunk_index.py
c. git status 和 git diff --stat
d. check_chars（SDK 的 src tests）

【完成报告】按【通用规则】第五条；写明开工确认第 2 条的表格，以及第 1 件事是否需要改代码

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–3 | | |
| 1 | | |
| 2 | | |
| 3 | | |
| a–d | | |
