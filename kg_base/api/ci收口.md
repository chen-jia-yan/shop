【任务 CI 收口】只修复本分支引入的 mypy / ruff 问题，并只格式化本分支改过的文件，使各项检查回到不差于 develop 的水平。不改任何业务逻辑。

【工作目录】C:\Users\234393\Desktop\tap-ai-backend
Python 统一用 C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe（下文 <py>）；ruff、mypy 用 & <py> -m ruff、& <py> -m mypy。

【绝对禁止】
- 不改业务逻辑、接口参数和返回结构；不改测试的断言
- 不改 pyproject.toml、uv.lock、任何流水线配置文件
- 不使用 # type: ignore、# noqa、cast(Any, ...)；不加 skip / xfail
- 只允许对"本分支新增或修改过的 .py 文件"运行 ruff format；其他文件一律不格式化
- 不读 .env；git 只允许只读命令

【开工前确认（只读，贴原始输出）】
1. $changed = git diff --name-only --diff-filter=AM origin/develop... HEAD -- "*.py"; $changed
2. & <py> -m mypy src 2>&1 | Select-Object -Last 30
3. & <py> -m mypy src/tap_ai/bootstrap.py --show-error-context 2>&1 | Select-String -Pattern "bootstrap|LibraryKgBrowse|Neo4jKgBrowse|note" 
   （要看到"哪个方法的参数对不上"的说明）
4. & <py> -m ruff check . --output-format concise 2>&1 | Select-Object -Last 20
5. & <py> -m ruff format --check $changed 2>&1 | Select-Object -Last 40
6. git -c core.pager=cat show origin/develop:src/tap_ai/api/library_kb.py 2>&1 | Select-Object -First 5
   （确认 develop 上有没有 library_kb.py，判断上传接口的 mypy 错误是不是本分支引入的）

【要做的 5 件事】
1. kg_browse.py:596：变量的类型声明和实际赋值对不上。改成两个名字不同的变量，或者修正类型声明，二选一，不改函数行为
2. api/library_kb.py:167、174：从表单取出的值类型是 UploadFile | str
   - 第 167 行：值是 UploadFile 时先读出内容并按 utf-8 解码，再交给 model_validate_json；是 str 时直接使用
   - 第 174 行：用 isinstance(x, UploadFile) 判断，不是文件的项抛 BusinessError（CCB001 "上传内容不是文件"），是文件的才取 filename / content_type / read
   - 已有测试全部要通过
3. bootstrap.py:510：按开工前确认第 3 条，找出 Neo4jKgBrowse 和 contracts 中 LibraryKgBrowse 不一致的方法，把 contracts 里的接口定义改成和实现一致（参数名、参数类型、返回类型）。不改 Neo4jKgBrowse 的行为
4. ruff check：
   - tests/compression/run_compression_cases.py 的 F821（未定义 os）：在文件顶部的 import 区加 import os
   - 开工前确认第 4 条中，其他错误如果在 $changed 里的文件中，逐个修复；不在 $changed 里的，列出来，不修
5. ruff format：& <py> -m ruff format $changed（只格式化第 1 条列出的文件）

【验证（贴原始输出）】
a. & <py> -m mypy src 2>&1 | Select-Object -Last 15
   要求：只剩 restricted.py（5 个）和 parsers.py（1 个）这 6 个原有错误
b. & <py> -m ruff check . --output-format concise 2>&1 | Select-Object -Last 15
   要求：错误数不超过 4，且剩下的都不在 $changed 的文件中
c. & <py> -m ruff format --check $changed   要求：全部 already formatted
d. & <py> -m pytest -q tests/unit/test_library_kb_service.py tests/unit/test_library_kb_worker.py tests/unit/test_library_kb_repo.py tests/unit/test_library_kb_rules.py tests/unit/test_library_kb_ingest_plugin.py tests/unit/test_library_kb_skeleton.py tests/unit/test_library_kg_service.py tests/api/test_library_kb_api.py tests/api/test_library_kg_api.py tests/unit/test_library_chunks.py tests/unit/test_library_eval_service.py tests/unit/test_library_eval_core.py 2>&1 | Select-Object -Last 15
   要求：0 failed、0 error
e. git diff --stat：除第 5 件事格式化的文件外，只出现第 1–4 件事涉及的文件

【完成报告】按【通用规则】第五条；列出第 4 件事中"不在本分支、未修复"的错误；列出第 5 件事格式化了哪些文件

【核对表】
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| 开工确认 1–6 | | |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 验证 a–e | | |



Set-Location C:\Users\234393\fwd-tap-common
python -m pytest -q fwd-tap-ingest/tests/test_lazy_import.py
Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
git grep -n -E "234393|C:\\\\|Desktop" -- tests src




Set-Location C:\Users\234393\fwd-tap-common
python -m pytest -q fwd-tap-ingest/tests/test_lazy_import.py
Set-Location C:\Users\234393\fwd-tap-common\fwd-tap-ingest
git grep -n -E "234393|C:\\\\|Desktop" -- tests src


uv run pytest -q tests/unit/test_library_kb_service.py tests/unit/test_library_kb_worker.py tests/unit/test_library_kb_repo.py tests/unit/test_library_kb_rules.py tests/unit/test_library_kb_ingest_plugin.py tests/unit/test_library_kb_skeleton.py tests/unit/test_library_kg_service.py tests/api/test_library_kb_api.py tests/api/test_library_kg_api.py tests/unit/test_library_chunks.py tests/unit/test_library_eval_service.py tests/unit/test_library_eval_core.py 2>&1 | Select-Object -Last 15



Set-Location C:\Users\234393\Desktop\tap-ai-backend
git ls-files | Select-String -Pattern "pipeline|\.ya?ml$|Dockerfile"
