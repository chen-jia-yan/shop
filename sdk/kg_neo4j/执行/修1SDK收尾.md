【任务 修1】SDK 收尾：让 kg_schema / lexicon 不被 pptx 卡住；补上 K1b 漏改的两个旧配置名；KB_AOAI_* 只改名不改行为。
（先贴【通用规则】，包括 D0 第 4 步追加的 SDK 检查命令）

【工作目录】C:\Users\234393\fwd-tap-common\fwd-tap-ingest
开工前先运行 git branch --show-current，必须是 feature/tap-10366-kg，不是就停下来告诉我。

【绝对禁止】
- 不读 .env；不连接任何外部服务；不安装任何包（不运行 pip / uv add / uv sync）
- git 只允许 status / diff / log / show / grep / ls-files / branch --show-current
- 不改 pyproject.toml、uv.lock 和任何工具配置
- 不对已有文件运行 ruff format
- 不改 tests 里已有的用例，只允许追加

【本次允许修改的文件】
- src/tap_ingest_sdk/__init__.py
- src/tap_ingest_sdk/embeddings/_internal/config.py
- src/tap_ingest_sdk/sinks/_internal/config.py（只改 KB_AOAI_* 这 4 个环境变量名）
- README.md（只改涉及的配置名）
- 新建 tests/test_lazy_import.py
其他文件一律不改。需要改别的文件才能完成，停下来告诉我。

【开工前确认（只读，贴原始输出）】
1. src/tap_ingest_sdk/__init__.py 全文
2. git grep -n -E "KB_EMBEDDING_ENABLED|KB_COPILOT|KB_AOAI" -- src tests README.md
3. git grep -n -E "embedding_enabled|copilot_provider_type|aoai_" -- src tests
   并逐个说明：每个字段在哪里被读取、被谁使用；没有任何地方使用的，明确写"未使用"
4. & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import pptx; print(pptx.__version__)"
5. pyproject.toml 中 [project] 的 dependencies 和 optional-dependencies 原文（只贴这两段）

【要做的 5 件事】

1. __init__.py 改为"用到才导入"：
   - 对外暴露的名字和现在完全一样（__all__ 不变，一个不多一个不少）
   - 用模块级 __getattr__(name)：访问某个名字时才导入它所在的子模块，导入后缓存到 globals()
   - 文件里不再在顶部直接导入 client、parsers 等子模块
   - 中文注释说明原因："kg_schema、lexicon 等轻量模块不应被解析器依赖（如 python-pptx）拖住"
   - 目标：import tap_ingest_sdk.kg_schema、import tap_ingest_sdk.lexicon 不再触发 parsers 的导入；from tap_ingest_sdk import TapIngestClient 写法照常可用

2. embeddings/_internal/config.py：
   - KB_EMBEDDING_ENABLED：删除这个环境变量的读取。embedding_enabled 默认 True；命令行的 --no-embedding 参数保留不变（按开工前确认第 3 条，如果 CLI 是通过这个环境变量传值的，停下来告诉我，不要自己改 CLI）
   - KB_COPILOT_PROVIDER_TYPE：开工前确认第 3 条显示 copilot_provider_type"未使用"时，删除该字段和读取；如果有地方在用，停下来告诉我

3. sinks/_internal/config.py：只把 4 个环境变量名改成新前缀，行为一个字都不改：
   KB_AOAI_ENDPOINT → TAP_AI_KB_AOAI_ENDPOINT
   KB_AOAI_EMBEDDING_DEPLOYMENT → TAP_AI_KB_AOAI_EMBEDDING_DEPLOYMENT
   KB_AOAI_EMBEDDING_MODEL → TAP_AI_KB_AOAI_EMBEDDING_MODEL
   KB_AOAI_API_KEY → TAP_AI_KB_AOAI_API_KEY
   字段名（aoai_endpoint 等）不改。README.md 中对应的两处同步改名，说明文字不改

4. 新建 tests/test_lazy_import.py（用 subprocess 起一个新的 Python 进程来测，避免影响其他测试）：
   a. 子进程里先执行 sys.modules["pptx"] = None（模拟没装 pptx），再 import tap_ingest_sdk.kg_schema 和 tap_ingest_sdk.lexicon，都要成功，并能打印出 TRAVERSABLE_RELATIONS
   b. 同一个子进程里，导入后 "tap_ingest_sdk.parsers" 不在 sys.modules 中
   c. 正常环境下（有 pptx 时）tap_ingest_sdk.__all__ 中每个名字都能通过 getattr 取到；没有 pptx 时这条用 pytest.importorskip("pptx") 跳过
   子进程用 sys.executable 启动，工作目录和 sys.path 与当前测试一致

5. 验证（全部贴原始输出）：
   a. & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 15
   b. & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from tap_ingest_sdk.kg_schema import TRAVERSABLE_RELATIONS, RELATION_ZH; print(TRAVERSABLE_RELATIONS); print(RELATION_ZH)"
   c. & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m ruff check src tests 2>&1 | Select-Object -Last 30
      （SDK 自己的 .venv 坏了，统一用后端的 Python 跑 ruff；只列出本次修改的文件里的问题，其他文件的问题单独列为"原有问题"）
   d. git grep -n -E "KB_COPILOT|KB_AOAI|KB_KG_LLM_ENABLED|KB_EMBEDDING_ENABLED|NO_AUTOLOAD" -- src tests README.md
      要求无输出
   e. uv run python C:/Users/234393/Desktop/check_chars.py src tests（在后端目录运行时，把路径换成 SDK 的绝对路径）

【完成报告】按【通用规则】第五条；另外写明：
- 第 5a 条中还剩的 error，每个一句话说明原因（预期只剩"缺少 pptx"导致的解析器相关测试）
- 新增的每个测试函数名

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–5 | | |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5a–5e | | |
