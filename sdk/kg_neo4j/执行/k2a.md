## 后端：删开关、测试不读 `.env
【任务 K2a】删除 5 个开关；测试时不读取 .env，测试需要的假环境变量统一写进 conftest。
（先贴【通用规则】）

【工作目录】C:\Users\234393\Desktop\tap-ai-backend

【本次允许修改的文件】
- src/tap_ai/config/settings.py、.env.example
- src/tap_ai/plugins/extensions/knowledge/settings.py（只改 model_config 中的 env_file 这一处）
- src/tap_ai/bootstrap.py
- src/tap_ai/application/library_chunks.py、src/tap_ai/application/library_eval.py（只改读开关的地方）
- src/tap_ai/api/library_kb.py（只改"服务未就绪"的处理）
- tests/conftest.py
- 下面这些测试中引用开关的部分：tests/unit/test_library_skeleton.py、tests/unit/test_library_kb_skeleton.py、tests/api/test_library_kb_api.py、
  tests/unit/test_library_chunks.py、tests/unit/test_library_eval_service.py

【要删除的 5 个开关】
library_enabled、library_kb_enabled、library_kb_worker_enabled、library_chunk_publish_enabled、library_eval_llm_analysis_enabled
（library_kb_graph_enabled 保留，本次不动）

【开工前确认（只读，贴原始输出）】
1. 5 个开关的 git grep -n 结果（src、tests、.env.example）
2. bootstrap.py 中 Library 评估服务、知识库服务和 worker 的装配代码原文，以及 _mount_routers 中 library 相关路由的原文
3. api/library_kb.py 中 _service(request) 的原文：app.state 中没有知识库服务时现在会怎样
4. application/library_chunks.py 第 140–160 行；application/library_eval.py 中 _build_llm_analysis 的原文
5. tests/conftest.py 全文
6. git grep -n "getattr(settings\|getattr(app_settings\|getattr(self.settings" -- src 的原始输出

【要做的 7 件事】
1. settings.py 和 .env.example：删除这 5 个字段和它们上方的注释
2. bootstrap.py：
   - Library 评估服务、切片审核服务：删除外层 if，改为无条件装配
   - 知识库服务：删除两个开关的 if；blob_store 为 None 时"打印警告并跳过"的逻辑保留
   - worker：ingest 不为 None 时就创建并登记关闭；删除开关判断
   - _mount_routers：library_kb 路由改为无条件挂载
   - 删掉外层 if 后，里面的代码整体左移 4 个空格。每处改完立即贴出 git diff --stat 和 git diff -w --stat：
     -w 的结果中，被删除的只能是 if 那几行，不得有其他删除
3. library_chunks.py：删除"落库功能未启用"的检查；保留 publisher 为 None 的检查，提示改为"落库功能未接入"
   library_eval.py：删除 _build_llm_analysis 中的开关判断；保留"存在 badcase 才调用"的判断
4. api/library_kb.py：app.state 中没有知识库服务时，返回 BusinessError(code="CCB001", message="知识库管理未就绪")，不能抛出 AttributeError
5. 测试时不读 .env：
   - config/settings.py 新增函数 env_file_path() -> str | None：环境变量 TAP_AI_DISABLE_DOTENV 为 "1" 时返回 None，否则返回 ".env"。上方中文注释说明用途
   - Settings 和 KnowledgeSettings 的 model_config 中 env_file 改为 env_file_path()
   - tests/conftest.py 文件最开头（任何 import tap_ai 之前）用 os.environ 强制赋值（不是 setdefault）：
     TAP_AI_DISABLE_DOTENV=1、TAP_AI_LITELLM_BASE_URL=http://127.0.0.1:4000、TAP_AI_LITELLM_API_KEY=test-dummy-key、
     TAP_AI_DATABASE_URL=mysql+asyncmy://test:test@127.0.0.1:3306/test、TAP_AI_REDIS_URL=redis://127.0.0.1:6379/0
     上方中文注释："测试一律使用假配置，不读取 .env，避免误连真实服务"
6. 开关读取的隐患：第 6 条 git grep 结果中，凡是读取 Settings 中确实存在的字段的 getattr，改为直接读属性（settings.xxx）。
   只改本次允许修改的文件；其他文件里的列出来，不改
7. 测试调整（这是设计变更，允许按下面的规则修改这几个测试）：
   - "开关关闭时不挂载路由 / 不构造服务"的用例：删除
   - "开关默认值为 False"的断言：删除
   - 先设置开关再测试的用例：删除设置开关的那几行，断言不变
   - test_library_skeleton.py 新增一个用例：不设置任何开关，19 个 Library 路由全部存在
   - test_library_chunks.py：publisher 为 None 时提交返回"落库功能未接入"
   - test_library_eval_service.py：存在 badcase 时调用一次分析；没有 badcase 不调用（不再依赖开关）
   每删除一个用例，在报告中写明文件、用例名、删除原因

【额外检查】完成后，新开一个 PowerShell 窗口，不设置任何环境变量，在后端目录运行：
uv run pytest -q tests/unit/test_library_skeleton.py 2>&1 | Select-Object -Last 10
贴出原始输出，证明不再需要手动设置环境变量

【完成报告】按【通用规则】第五条；另外贴出：
git grep -n -E "library_enabled|library_kb_enabled|library_kb_worker_enabled|library_chunk_publish_enabled|library_eval_llm_analysis_enabled" -- src tests .env.example
的原始输出（必须没有输出），以及第 7 条删除的用例清单


## 验证
K2a 的验收方法 ￼

1. 新开一个 PowerShell 窗口，不设任何环境变量，直接跑全部测试：

```powershell
cd C:\Users\234393\Desktop\tap-ai-backend
uv run pytest -q 2>&1 | Select-Object -Last 15

```

这一步是在检查”测试不再依赖手动设的环境变量”。要求：

- 能跑起来，不再报 4 个配置项缺失

- 和今晚第 0 步记下的基线比，失败数不增加

2. 开关已经清干净：

```powershell
git grep -n -E "library_enabled|library_kb_enabled|library_kb_worker_enabled|library_chunk_publish_enabled|library_eval_llm_analysis_enabled" -- src tests .env.example

```

要什么都不输出。

3. 接口都挂上了（这一步需要手动设 4 个假环境变量）：

```powershell
$env:TAP_AI_LITELLM_BASE_URL="http://127.0.0.1:4000"
$env:TAP_AI_LITELLM_API_KEY="test-dummy-key"
$env:TAP_AI_DATABASE_URL="mysql+asyncmy://test:test@127.0.0.1:3306/test"
$env:TAP_AI_REDIS_URL="redis://127.0.0.1:6379/0"
uv run python -c "from tap_ai.bootstrap import build_app; app=build_app(); paths=[r.path for r in app.routes if '/library' in getattr(r,'path','')]; print(len(paths)); print('\n'.join(sorted(paths)))"

```

要看到 Library 的评估、切片、知识库接口全部列出来，不需要设任何开关。

4. bootstrap.py 只删了 if 那几行：

```powershell
git diff -w src/tap_ai/bootstrap.py | Select-String "^-"

```

除了 ‎`---` 文件头，只能看到 ‎`if getattr(...)` 这类开关判断的行。

通过以后，在后端目录提交：

```powershell
git add -A
git commit -m "refactor(config): 删除 5 个功能开关，测试统一使用假配置且不读取 .env"

```

