【任务 修1b】解开 kg_schema 的循环导入，让 kg_schema 成为真正的"最底层"文件；在正确的目录重跑 SDK 全量测试。修1 的改动保留，不要撤销。

【工作目录】C:\Users\234393\fwd-tap-common\fwd-tap-ingest
所有命令开头先 Set-Location 到这个目录。Python 统一用 & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe

【绝对禁止】
- 不读 .env；不连接外部服务；不安装任何包
- git 只允许 status / diff / log / show / grep / ls-files / branch --show-current
- 不改 pyproject.toml、uv.lock；不对已有文件运行 ruff format
- 不改实体类型、关系类型的任何取值（名字、中文名、别名、端点组合一个字都不变）
- 不改 tests 里已有用例的断言，只允许追加；tests/test_lazy_import.py 是修1 新建的，允许修改

【本次允许修改的文件】
- src/tap_ingest_sdk/kg_schema.py
- src/tap_ingest_sdk/sinks/_kg_schema.py
- tests/test_lazy_import.py
其他文件一律不改。需要改别的文件才能完成，停下来告诉我。

【开工前确认（只读，贴原始输出）】
1. git branch --show-current（必须是 feature/tap-10366-kg）
2. git status
3. git diff --stat 中出现的 "fwd-tap-common | 0" 是什么：
   git -C C:\Users\234393\fwd-tap-common status --short
   git -C C:\Users\234393\fwd-tap-common diff -- fwd-tap-common
   git -C C:\Users\234393\fwd-tap-common ls-files -s fwd-tap-common
   只报告，不处理
4. src/tap_ingest_sdk/kg_schema.py 中所有 import 语句（含行号）
5. src/tap_ingest_sdk/sinks/_kg_schema.py 中所有 import 语句（含行号），以及第 140 行到文件末尾的原文
6. src/tap_ingest_sdk/sinks/__init__.py 全文
7. tests/test_lazy_import.py 全文

【要做的 4 件事】

1. kg_schema.py 改成最底层文件：
   - 只允许导入 Python 标准库（如 __future__、dataclasses、typing）。不得导入 tap_ingest_sdk 下的任何模块
   - 原来从 sinks._kg_schema 导入的名字（按开工前确认第 4 条），在 kg_schema.py 里直接定义，取值和原来完全一样
   - 文件开头的说明注释保留，追加一句："本文件不得导入 tap_ingest_sdk 的任何模块，否则会形成循环导入"

2. sinks/_kg_schema.py 改成单向依赖：
   - 第 156 行附近 from tap_ingest_sdk.kg_schema import ... 移到文件顶部的 import 区域
   - 第 1 件事里挪到 kg_schema.py 的那些名字，在这里改为从 kg_schema 导入，原名字照样能从 sinks._kg_schema 取到（对外不变）
   - 不能在两个文件里各定义一份相同的常量：同一个值只能定义一次

3. tests/test_lazy_import.py 追加 / 修改（都用 subprocess 起新进程，sys.executable 启动）：
   a. 新进程里 sys.modules["pptx"] = None，然后第一句就 import tap_ingest_sdk.kg_schema（前面不能先导入 sinks），成功并打印 TRAVERSABLE_RELATIONS
   b. 同一进程里检查 "tap_ingest_sdk.sinks" 和 "tap_ingest_sdk.parsers" 都不在 sys.modules
   c. 另一个新进程：先 import tap_ingest_sdk.sinks，再 import tap_ingest_sdk.kg_schema，都成功（如果 sinks 因 pptx 导入失败，用 importorskip("pptx") 跳过这一条，并说明）
   d. sinks._kg_schema.ALLOWED_RELATIONS == kg_schema.SCHEMA_ALLOWED_RELATIONS，LLM_RELATION_MAP == SCHEMA_LLM_RELATION_MAP
   e. 读取 kg_schema.py 源码，断言其中没有 "tap_ingest_sdk" 和 "from ." 开头的导入

4. 验证（全部贴原始输出，命令都在工作目录下执行）：
   a. & <后端 python> -m pytest -q tests 2>&1 | Select-Object -Last 20
      必须显示收集到测试；逐个列出剩下的 failed / error，每个一句话说明原因
   b. & <后端 python> -c "import sys; sys.path.insert(0, 'src'); sys.modules['pptx'] = None; from tap_ingest_sdk.kg_schema import TRAVERSABLE_RELATIONS, RELATION_ZH; print(TRAVERSABLE_RELATIONS); print(RELATION_ZH)"
   c. & <后端 python> -m ruff check src/tap_ingest_sdk/kg_schema.py src/tap_ingest_sdk/sinks/_kg_schema.py src/tap_ingest_sdk/__init__.py tests/test_lazy_import.py
      （只检查本次和修1 改过的文件）
   d. git grep -n -E "(^|[^_A-Z])KB_(COPILOT|AOAI|KG_LLM_ENABLED|EMBEDDING_ENABLED)" -- src tests README.md
      要求无输出
   e. git diff --stat 和 git status

【完成报告】按【通用规则】第五条；另外写明：第 1 件事从 sinks 挪过来了哪些名字

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–7 | | |
| 1 | | |
| 2 | | |
| 3a–3e | | |
| 4a–4e | | |
