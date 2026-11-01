## SDK：统一的关系名单、不丢关系、时间和切片摘要 
【任务 K1a】在 SDK 中统一定义实体类型和关系类型；大模型给出的关系不再丢弃；Neo4j 写入时带上时间和切片摘要。
（先贴【通用规则】，包括 D0 第 4 步追加的 SDK 检查命令）

【工作目录】C:\Users\234393\fwd-tap-common\fwd-tap-ingest（当前分支应为 feature/tap-10366-kg，开工前先用 git branch --show-current 确认，不是的话停下来）

【本次允许修改的文件】
- 新建 src/tap_ingest_sdk/kg_schema.py
- src/tap_ingest_sdk/sinks/_kg_schema.py
- src/tap_ingest_sdk/sinks/_kg_llm_extract.py
- src/tap_ingest_sdk/sinks/_neo4j.py
- 新建 tests/test_kg_schema.py；其他已有测试只允许追加用例，不得修改已有用例

【开工前确认（只读，贴原始输出）】
1. sinks/_kg_schema.py 全文。特别注意 ALLOWED_RELATIONS 中 "PART_OF" 那一行：逐字贴出，说明括号是否成对、_pairs 的两个参数分别是什么
2. _pairs 函数、EntityRef、所有实体类型常量（PRODUCT、STEP、STAGE、ACTION、ROLE 等）、LLM_ENTITY_TYPES 的原文
3. _neo4j.py 中 _WRITE_DOCUMENT、_WRITE_MENTIONS、_REL_ENDPOINTS_MERGE、_REL_MERGE 的原文，以及 upsert、_write_relations、_mention_rows 的原文
4. _kg_llm_extract.py 中 _SYSTEM_PROMPT、_to_specs、parse_response 的原文，并说明现在在哪几处会把关系丢掉
5. git grep -n -E "ALLOWED_RELATIONS|LLM_RELATION_MAP|LLM_ENTITY_TYPES" -- src tests 的原始输出

【要做的 7 件事】

1. 新建 src/tap_ingest_sdk/kg_schema.py：
   - 文件开头中文注释："实体类型和关系类型的唯一定义处。新增或修改类型只改这个文件，SDK 和后端都从这里读取。"
   - @dataclass(frozen=True) EntityTypeDef：name（英文名）、zh（中文名）、description（说明）
   - @dataclass(frozen=True) RelationAlias：text（中文说法）、reverse（是否交换起点和终点，默认 False）
   - @dataclass(frozen=True) RelationTypeDef：name、zh、aliases（RelationAlias 元组）、
     pairs（允许的 (起点类型, 终点类型) 元组；空元组表示不限制）、description、traversable（问答时能否顺着走）
   - ENTITY_TYPES：照抄 _kg_schema.py 中现有的全部实体类型，一个不多、一个不少。中文名：
     Concept 概念、Product 产品、System 系统、Process 流程、Data 数据、Document 文档、Role 角色、Channel 渠道、Stage 阶段、Step 步骤、Action 动作
     （现有类型里有不在这个列表中的，停下来告诉我）
   - RELATION_TYPES：
     · 现有 6 种：pairs 必须与现有 ALLOWED_RELATIONS 完全一致；aliases 照抄现有 LLM_RELATION_MAP 的中文说法（"执行"对应 HANDLED_BY，reverse=True）；traversable=True
       中文名：NEXT 下一步、HANDLED_BY 负责、PART_OF 属于、CONTAINS 包含、USES 使用、REQUIRES 需要
     · 新增 1 种：name="RELATED_TO"，zh="相关"，aliases=()，pairs=()，traversable=False，description="未归入标准关系的其他关联，原始说法保存在 raw_types"
   - 由上面生成的常量（名字固定，每个上方写中文注释说明用途）：
     ENTITY_TYPE_NAMES（元组）、ENTITY_TYPE_ZH（dict）、RELATION_ZH（dict）、TRAVERSABLE_RELATIONS（元组，traversable=True 的关系名，顺序与 RELATION_TYPES 一致）、
     SCHEMA_ALLOWED_RELATIONS（dict[str, frozenset[tuple[str, str]]]，不含 RELATED_TO）、
     SCHEMA_LLM_RELATION_MAP（dict[str, tuple[str, bool]]：每个中文说法 → (关系名, reverse)；每个关系的英文名 → (关系名, False)；包括 RELATED_TO）

2. sinks/_kg_schema.py：ALLOWED_RELATIONS、LLM_RELATION_MAP 改为从 kg_schema 导入后重新赋值，原来的名字保留，其他代码不用改。
   实体类型常量保留在原文件不动（kg_schema.py 从这里导入这些常量来写 ENTITY_TYPES 和 pairs，避免两边各写一遍）
   注意不要形成循环导入：kg_schema.py 只能从 _kg_schema.py 导入"类型常量"，_kg_schema.py 在文件末尾再从 kg_schema 导入。
   如果做不到无循环导入，停下来告诉我，不要自己想别的办法

3. RelationSpec 末尾追加可选字段：raw_type: str | None = None（带默认值，已有的调用不受影响）

4. _kg_llm_extract.py：
   - _SYSTEM_PROMPT 中"关系类型只能使用: ..."这一行，改为由 kg_schema 生成：
     "关系类型优先使用: " + 所有中文说法用"、"连接 + "（A 执行 B 表示角色 A 负责动作 B）。都不合适时，用一个简短的中文短语描述关系。"
     提示词其他部分一个字都不改。生成后的完整提示词在完成报告中贴出
   - 实体类型那一行同样改为由 ENTITY_TYPES 生成，但只列出现在提示词中已有的那 8 种（保持现状）
   - _to_specs：
     · 关系说法能在 LLM_RELATION_MAP 中找到、并且两端类型符合 ALLOWED_RELATIONS → 与现在完全一样
     · 找不到，或者两端类型不符合 → 生成 type="RELATED_TO" 的 RelationSpec，raw_type 填大模型给出的原始说法（去掉首尾空白）
     · 只有起点或终点实体缺失、或原始说法为空时才丢弃
   - 规则抽取器（_kg_extract.py）不改

5. _neo4j.py（每条 Cypher 必须保留现有的 scope 条件，不得新增不带 scope 的语句）：
   - upsert 开始时计算 now = int(time.time() * 1000)，作为参数 $now 传给本次所有写入语句
   - Document：SET d.ingested_at = $now
   - Chunk：SET c.page_or_sheet（来自 chunk.metadata.page_or_sheet）、c.preview（chunk.content 的前 200 个字符）、c.ingested_at = $now
     这些值通过 chunk_ids 之外新增的参数传入，例如把 $chunk_ids 改为 $chunks（每项含 chunk_id、page_or_sheet、preview），并同步修改 UNWIND 语句
   - Entity：ON CREATE SET e.created_at = $now；每次都 SET e.updated_at = $now
   - 实体之间的关系：ON CREATE SET e.created_at = $now；每次 SET e.updated_at = $now；
     RelationSpec.raw_type 不为空时，追加进 e.raw_types 并去重（为空时不动这个属性）
   - RELATED_TO 不经过 allowed_relations 的类型组合检查，直接写入（关系类型名来自 kg_schema 的常量，不是用户输入）
   - delete()、撤销旧数据的三条语句不改

6. 关系类型写进 Cypher 的方式检查：
   贴出 _neo4j.py 中把关系类型放进 Cypher 的那几行原文（_REL_MERGE 里的 {rel}），说明写入前是否校验过关系名一定在 RELATION_ZH 的键里。
   没有校验的话，加上校验：不在里面的关系名直接跳过并打印 warning

7. 测试（新建 tests/test_kg_schema.py；其他测试只追加）：
   a. SCHEMA_ALLOWED_RELATIONS 与修改前的 ALLOWED_RELATIONS 逐项相等（把开工前确认第 1 条中的原值，按实体类型常量写进测试作为期望值）
   b. SCHEMA_LLM_RELATION_MAP 中，原 LLM_RELATION_MAP 的每一项都存在且值相同
   c. TRAVERSABLE_RELATIONS 恰好是原来的 6 种，不含 RELATED_TO
   d. _to_specs：能对上的 → 标准关系；对不上的 → RELATED_TO，raw_type 是原始说法；类型不符合的 → RELATED_TO；实体缺失 → 丢弃
   e. 用已有测试中的假 driver 记录参数：upsert 时每条写入语句都收到 now；Chunk 的参数里有 preview，长度不超过 200；有 raw_type 的关系，参数里带上了 raw_type
   f. _SYSTEM_PROMPT 中包含每一个中文说法

【完成报告】按【通用规则】第五条中"SDK 仓库"那一组命令；另外贴出生成后的完整 _SYSTEM_PROMPT，以及新增的每个测试函数名

## 验收  sdk的检查
cd C:\Users\234393\fwd-tap-common\fwd-tap-ingest
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 10
和 D0 第 3 步的基线比：失败数不能增加，passed 要比基线多（多出来的是新增的测试）。

2. 名单和原来一致（在 SDK 目录）：
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from tap_ingest_sdk.kg_schema import TRAVERSABLE_RELATIONS, RELATION_ZH; print(TRAVERSABLE_RELATIONS); print(RELATION_ZH)"

要看到：第一行正好是 6 种关系，没有 RELATED_TO；第二行是 7 种关系和它们的中文名。

3. 后端没受影响（在后端目录）：
cd C:\Users\234393\Desktop\tap-ai-backend
uv run python -c "import tap_ai.application; print('ok')"
uv run pytest -q tests/unit/test_library_kb_ingest_plugin.py 2>&1 | Select-Object -Last 5
第一条输出 `ok`，第二条没有失败。

4. 字符检查：

```powershell
uv run python C:/Users/234393/Desktop/check_chars.py C:/Users/234393/fwd-tap-common/fwd-tap-ingest/src C:/Users/234393/fwd-tap-common/fwd-tap-ingest/tests

```

要显示”发现 0 处问题”。

**以上 4 项结果发我。**我确认通过以后，在 SDK 目录提交：

```powershell
cd C:\Users\234393\fwd-tap-common\fwd-tap-ingest
git add -A
git commit -m "feat(kg): 统一实体与关系定义，未匹配关系存为 RELATED_TO，写入时间与切片摘要"

```


