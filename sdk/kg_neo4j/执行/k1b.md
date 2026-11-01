## SDK：配置名统一、不自动读 `.env`、修维度问题 
【任务 K1b】SDK 的配置名与后端统一；SDK 被导入时不再自动读取 .env；修复向量维度的读取问题；删除没人使用的配置。
（先贴【通用规则】，包括 D0 第 4 步追加的 SDK 检查命令）

【工作目录】C:\Users\234393\fwd-tap-common\fwd-tap-ingest（先用 git branch --show-current 确认是 feature/tap-10366-kg）

【本次允许修改的文件】
src/tap_ingest_sdk/__init__.py、src/tap_ingest_sdk/env_config.py、src/tap_ingest_sdk/cli/main.py、
src/tap_ingest_sdk/embeddings/_internal/config.py、src/tap_ingest_sdk/sinks/_internal/config.py、
src/tap_ingest_sdk/sinks/_kg_llm_extract.py、src/tap_ingest_sdk/sinks/_azure.py（只改读取配置的地方）、README.md、
tests/ 下与这些文件对应的测试（只改配置名，不改断言的含义）

【配置名对照表】左边是现在的名字，右边是改成的名字；默认值一列为空表示没有默认值
| 现在 | 改成 | 默认值 |
| KB_AZURE_SEARCH_ENDPOINT | TAP_AI_KB_AZURE_SEARCH_ENDPOINT | |
| KB_AZURE_SEARCH_KEY | TAP_AI_KB_AZURE_SEARCH_KEY | |
| KB_AZURE_SEARCH_INDEX | TAP_AI_KB_AZURE_SEARCH_INDEX（只给命令行用） | |
| KB_AZURE_SEARCH_VECTOR_FIELD | TAP_AI_KB_VECTOR_FIELD | content_vector |
| KB_NEO4J_URI / _USER / _PASSWORD / _DATABASE | TAP_AI_KB_NEO4J_URI / _USER / _PASSWORD / _DATABASE | USER 默认 neo4j，DATABASE 默认 neo4j |
| KB_EMBEDDING_MODEL | TAP_AI_KB_EMBEDDING_MODEL | text-embedding-3-large |
| KB_EMBEDDING_DIMENSIONS | TAP_AI_KB_EMBEDDING_DIMENSIONS | 3072 |
| KB_EMBEDDING_BASE_URL、KB_COPILOT_PROVIDER_BASE_URL | TAP_AI_LITELLM_BASE_URL | |
| KB_EMBEDDING_API_KEY、KB_COPILOT_PROVIDER_API_KEY | TAP_AI_LITELLM_API_KEY | |
| KB_KG_LLM_MODEL | TAP_AI_KB_KG_LLM_MODEL | |
| 删除：KB_COPILOT_PROVIDER_TYPE、KB_AOAI_ENDPOINT、KB_AOAI_EMBEDDING_DEPLOYMENT、KB_AOAI_EMBEDDING_MODEL、KB_AOAI_API_KEY、KB_KG_LLM_ENABLED、KB_EMBEDDING_ENABLED、TAP_INGEST_SDK_NO_AUTOLOAD_ENV | — | |
OCR（KB_LOCAL_OCR_*）、KB_ENABLE_LEGACY_CONVERSION、TAP_INGEST_LEXICON、KB_SOURCE_URL_BASE 以及 Paddle 的日志变量保持不变

【开工前确认（只读，贴原始输出）】
1. 后端 C:\Users\234393\Desktop\tap-ai-backend\src\tap_ai\plugins\extensions\knowledge\settings.py 中 azure_search_endpoint、azure_search_key、vector_field、
   embedding_model、embedding_dimensions、neo4j_* 这几个字段的原文。核对上面的对照表与后端字段名一致（TAP_AI_KB_ + 字段名大写）；不一致的列出来
2. 上面每个旧配置名的 git grep -n 结果（src、tests、README.md、docs 都要搜）
3. __init__.py 中自动加载 .env 的原文；CLI 入口函数（click 的 group 或 command）原文
4. AzureAISearchSink 的 __init__ 原文：它生成切片向量时，地址、密钥、模型是从参数来，还是在内部读环境变量（逐层贴出读取的代码）
5. KB_AOAI_* 被使用的全部代码。说明删除以后，创建 Azure 索引时会少什么（例如索引上绑定的向量化器）
6. KB_EMBEDDING_ENABLED 和命令行 --no-embedding 的关系：删除这个环境变量以后，--no-embedding 是否还能单独使用

【要做的 7 件事】
1. 在 env_config.py 中集中定义所有配置名常量（每个一行，上方中文注释写用途），其他文件一律引用这些常量，不得再出现配置名字符串
2. 按对照表修改 src 中所有读取配置的地方，默认值按对照表设置。对照表里"没有默认值"的配置缺失时，报错信息要写明缺少的新配置名
3. __init__.py 不再自动加载 .env；改为在 CLI 入口函数的第一行显式调用 load_env_file()。load_env_file 函数本身保留，删除 TAP_INGEST_SDK_NO_AUTOLOAD_ENV 的判断
4. 修复 cli/main.py 中所有 int(os.getenv(...)) or 3072 的写法，改为 int(os.getenv(新名字) or 3072)。没有设置时用 3072，不报错
5. 命令行的关系抽取默认改为"规则 + 大模型"：--kg-extractor 的默认值改为 llm；传 rule 时只用规则抽取。删除 llm_enabled() 和 KB_KG_LLM_ENABLED 相关代码；
   OpenAILLMProvider.from_env 改为读取 TAP_AI_LITELLM_BASE_URL、TAP_AI_LITELLM_API_KEY、TAP_AI_KB_KG_LLM_MODEL
6. 删除 KB_AOAI_* 和 KB_COPILOT_PROVIDER_TYPE 相关的代码分支。如果开工前确认第 5 条显示删除会让创建索引缺少必需的字段或配置，停下来告诉我，不要删
7. 更新 README 中的配置说明表格，以及 tests 中使用旧名字的地方。最后运行：
   git grep -n -E "KB_COPILOT|KB_AOAI|KB_KG_LLM_ENABLED|KB_EMBEDDING_ENABLED|NO_AUTOLOAD|\"KB_AZURE|\"KB_NEO4J|\"KB_EMBEDDING" -- src tests README.md
   必须没有输出（docs 目录下的历史设计文档不改）

【完成报告】按【通用规则】第五条中"SDK 仓库"那一组命令；另外贴出第 7 条 git grep 的原始输出，以及开工前确认第 4 条的结论



## 验收方法 ￼

1. SDK 测试（在 SDK 目录），失败数不能比 K1a 之后多：

```powershell
cd C:\Users\234393\fwd-tap-common\fwd-tap-ingest
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 10

```

2. 旧配置名已经清干净：

```powershell
git grep -n -E "KB_COPILOT|KB_AOAI|KB_KG_LLM_ENABLED|KB_EMBEDDING_ENABLED|NO_AUTOLOAD" -- src tests README.md

```

要什么都不输出。

**3. 导入 SDK 不再读 `.env`。**先在 SDK 目录建一个临时的 `.env` 来试：

```powershell
Set-Content -Path .env -Value "TAP_AI_KB_EMBEDDING_MODEL=should-not-load" -Encoding utf8
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys, os; sys.path.insert(0,'src'); import tap_ingest_sdk; print(os.getenv('TAP_AI_KB_EMBEDDING_MODEL'))"
Remove-Item .env

```

要输出 `None`。如果输出 `should-not-load`，说明导入时还在读 `.env`。最后一行 `Remove-Item .env` 一定要运行，把临时文件删掉。

这里 `Set-Content` 是你自己用来做测试的，没关系。不让 Copilot 用它，是因为它会改代码文件的编码。

4. 后端没受影响（在后端目录）：

```powershell
cd C:\Users\234393\Desktop\tap-ai-backend
uv run python -c "import tap_ai.application; print('ok')"
uv run pytest -q tests/unit/test_library_kb_ingest_plugin.py 2>&1 | Select-Object -Last 5

```

**5. 本地 `.env` 里的旧名字改掉。**如果你本地后端的 `.env` 里有 `KB_` 开头的配置，按对照表改成新名字。这一步你自己做，不要发我内容，告诉我”已改”或”没有”就行。

通过以后，在 SDK 目录提交：

```powershell
cd C:\Users\234393\fwd-tap-common\fwd-tap-ingest
git add -A
git commit -m "refactor(config): 配置名与后端统一，移除导入时自动读取 .env，修复维度默认值"

```


