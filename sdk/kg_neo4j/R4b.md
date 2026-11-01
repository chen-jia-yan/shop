【任务 R4b】只读排查：租户身份来源、名字归一化、重新入库、SDK 配置的使用方、测试配置。

【绝对禁止】违反任意一条，立即停止并告诉我：
- 不修改、不新建、不删除任何文件；不读取任何 .env 文件（.env.example 可以读）
- 不连接任何外部服务；不运行入库命令；不执行 SQL
- git 只允许 status / log / show / grep / ls-files
- 找不到的写"未找到"，并贴出用过的搜索命令。不允许推测

【范围】
- 后端：C:\Users\234393\Desktop\tap-ai-backend
- SDK 所在仓库：C:\Users\234393\fwd-tap-common（整个仓库，不只是 fwd-tap-ingest）

【要做的 6 件事】每一件都必须贴出 文件:行号 + 原文

1. saas_id 是从哪里来的
   从接收聊天请求的接口开始，追到会话里存的 saas_id：它来自请求头、请求体、登录令牌，还是别的地方？逐层贴出原文
   最后说明：本地测试时，要让一次提问使用 saas_id='jp'，需要在请求里传什么

2. 实体名字的归一化规则，后端和 SDK 是否一致
   a. 后端问答按名字查实体时，计算 norm 用的函数原文
   b. SDK normalize_label 的原文
   c. 结论：两边是不是同一个函数，或者规则完全相同。只能回答「一致」「不一致」，不一致的话写出具体差别

3. 有没有"对已有文件重新入库"的功能
   在后端搜索 reindex、reingest、retry、rebuild 等关键词，贴出原始输出
   有的话贴出接口或函数的原文；没有的写"没有"

4. SDK 配置和大模型调用的使用方
   在整个 fwd-tap-common 仓库中分别搜索下面几项，贴出全部原始输出：
   git grep -n "env_config"
   git grep -n "OpenAILLMProvider"
   git grep -n -E "KB_AOAI_|KB_COPILOT_PROVIDER|KB_EMBEDDING_|KB_KG_LLM"
   然后列出：除了 fwd-tap-ingest 自己以外，还有哪些项目或文件在使用这些配置（没有的写"只有 fwd-tap-ingest 自己使用"）

5. 后端的配置是怎么读取的
   a. src/tap_ai/config/settings.py 中 Settings 的 model_config 原文（有没有 env_file，指向哪里）
   b. knowledge/settings.py 中 KnowledgeSettings 的 model_config 原文
   c. tests/conftest.py 的完整原文
   d. 后端导入 SDK 的所有位置：git grep -n "tap_ingest_sdk" -- src，贴出原始输出

6. 入库任务表里，有没有记录"图谱写入状态"的字段
   a. 知识库入库任务对应的 ORM 类完整原文（在 persistence/models.py 或同事的文件里）
   b. 对应建表 SQL 的原文（在 sql/ 目录下）
   c. 结论：现在能不能单独记录"Azure 写入成功、Neo4j 写入失败"这种状态。只能回答「能」「不能」，并说明依据

【报告格式】
- 按 1 到 6 的顺序写，每条一个小标题
- 最后必须有这张核对表，6 行都要有，不能合并：
  | 编号 | 状态（完成 / 未找到 / 未做） | 证据所在的文件:行号 |
- 核对表里写"完成"、但正文没有原文代码的，视为未做
