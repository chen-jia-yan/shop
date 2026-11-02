# K2a_执行现状总结.md
## 1. 当前现状简述
本步已按 k2a.md、k2a_开工前确认.md、通用规则.md 的范围完成主要代码修改，核心目标已经落地：
- 删除 K2a 要求移除的 5 个旧开关：
  - library_enabled
  - library_kb_enabled
  - library_kb_worker_enabled
  - library_chunk_publish_enabled
  - library_eval_llm_analysis_enabled
- bootstrap.py 已改为默认装配并挂载 library chunks / eval / kb / kg 相关能力。
- api/library_kb.py 已修复 app.state.library_kb_service 缺失时直接抛 AttributeError 的问题，改为稳定返回 BusinessError(code="CCB001", message="知识库管理未就绪")。
- 测试侧已补上“不读取 .env”的隔离处理，避免测试误连真实环境。
- K2a 点名的几个测试文件已同步调整，移除了依赖旧开关的测试与断言。
- 本次变更也已经追加写入 docs/PROJECT_MEMORY.md。目前可以确认：
  - 代码已经完成 K2a 主体改造；
  - 目标文件 ruff check 已通过；
  - import tap_ai.application 通过；
  - check_chars 通过。

但当前还不能算完全验收收口，因为仍有两个阻塞项未被彻底消除，见下文。

## 2. 本步实际处理了哪些问题
### 问题 1：Library 相关功能仍被旧开关控制
现象：K2a 要求删除 5 个旧开关，但代码和测试里仍存在这些开关依赖。处理方式：
- 在 src/tap_ai/config/settings.py 中删除 5 个开关字段；
- 在 src/tap_ai/bootstrap.py 中删除基于这些开关的装配/挂载判断；
- 在 src/tap_ai/application/library_chunks.py、src/tap_ai/application/library_eval.py 中移除对应开关判断；
- 在 K2a 允许修改的测试文件里同步清理旧开关相关断言、辅助参数和测试用例。处理结果：主体逻辑已不再依赖这 5 个旧开关，K2a 目标达成。

### 问题 2：library_kb_service 缺失时会直接抛 AttributeError
现象：原实现直接访问 request.app.state.library_kb_service。如果 app.state 上没有该属性，就会抛 AttributeError，不会转成业务错误。为什么这是问题：
- 这会把“服务未就绪”暴露成框架级异常；
- 外部表现不稳定，不符合现有业务错误返回约定；
- 与 K2a 明确要求不一致。处理方式：
- 在 src/tap_ai/api/library_kb.py 中改为使用 getattr(request.app.state, "library_kb_service", None) 获取服务；
- 当服务不存在时，显式抛出 BusinessError(code="CCB001", message="知识库管理未就绪")；
- 同步在 tests/api/test_library_kb_api.py 中补了对应测试覆盖。处理结果：这个问题已经修复，行为已从“不稳定的 AttributeError”收敛为“稳定的业务错误返回”。

### 问题 3：测试会读取 .env，存在误连真实环境风险
现象：测试初始化时会经过 settings 创建流程，而原配置默认读取 .env，这会把本地真实配置带进测试。风险：
- 测试可能误连真实数据库 / Redis / 外部服务；
- 不符合 K2a 对测试隔离的要求；
- 测试结果会受本机环境污染，复现性差。处理方式：
- 在 src/tap_ai/config/settings.py 中新增 env_file_path()；
- 在 TAP_AI_DISABLE_DOTENV == "1" 时返回 None，否则返回 ".env"；
- Settings 与 KnowledgeSettings 都改为使用这个方法；
- 在 tests/conftest.py 顶部、任何 import tap_ai 前强制设置：
  - TAP_AI_DISABLE_DOTENV=1
  - 以及一组假的 LiteLLM / DB / Redis 连接配置。处理结果：测试层面已经做到“不读 .env”，这部分目标已完成。

## 3. 当前仍然存在的问题
### 问题 A：目标 pytest 无法直接跑通
现象：执行目标测试时，在导入 tests/conftest.py 阶段就失败，报错为缺少 aiomysql。实际错误：ModuleNotFoundError: No module named 'aiomysql' 根因判断：
- 这不是本次 K2a 逻辑改坏导致；
- 而是 tests/conftest.py 导入 build_app() 后，会进一步触发数据库引擎初始化；
- 当前环境里没有安装 aiomysql，因此在测试导入阶段就挂掉。本步怎么处理的：
- 已先完成 K2a 代码与测试文件改造；
- 验证 import tap_ai.application、check_chars、目标文件 ruff check；
- 对 pytest 失败原因进行了定位，确认是环境依赖缺失，不是当前改动直接引入的新错误。当前状态：这是一个真实阻塞项，导致本步暂时拿不到“目标 pytest 通过”的最终证据。

### 问题 B：最终 grep 仍有范围外残留
现象：按 K2a 要求执行旧开关 grep 时，仍能命中 tests/api/test_library_kg_api.py。命中的原因：
- tests/api/test_library_kg_api.py 里仍保留对 library_enabled / library_kb_enabled 的旧写法；
- 但这个文件不在 K2a 允许修改的文件名单里。本步怎么处理的：
- 没有越界直接改这个文件；
- 只把它如实标记为“范围外残留”；
- 其余 K2a 允许修改的文件已全部完成清理。当前状态：因此，本步还不能给出“grep 完全无输出”的最终证明。

## 4. 这一步是怎么推进和处理问题的
本步处理方式遵循的是“先确认事实，再小步改，改完就看证据”的原则：
1. 先重新详细阅读并对齐：
   - 通用规则.md
   - k2a.md
   - k2a_开工前确认.md
2. 只在 K2a 允许范围内改文件，不顺手扩改。
3. 每改一个文件后，都对照 diff 形态，避免改动失控。
4. 先处理代码核心问题：
   - 删除旧开关
   - 删除旧判断
   - 修复 library_kb_service 缺失时的异常路径
   - 处理测试不读 .env
5. 再处理测试侧：
   - 删除依赖旧开关的老测试
   - 改成默认挂载/默认存在的测试预期
   - 补上“知识库管理未就绪”的新测试覆盖
6. 最后做验证与收尾：
   - 已通过：check_chars、import tap_ai.application、目标文件 ruff check
   - 未完全通过：目标 pytest、最终 grep 无输出
   - 已将本次现状与阻塞写入 docs/PROJECT_MEMORY.md

## 5. 当前结论
一句话总结：K2a 主体改造已经完成，关键逻辑问题也已修掉，尤其是 library_kb_service 缺失时的 AttributeError 已被稳定业务错误替代；但当前还存在两个未彻底收口的问题：
1. 测试环境缺少 aiomysql，导致目标 pytest 无法直接跑通；
2. tests/api/test_library_kg_api.py 中仍有旧开关引用，但它属于 K2a 范围外文件，因此本步没有越界修改。所以，这一步的状态更准确地说是：
- 代码改造主体完成；
- 主要问题已修复；
- 验证证据拿到了一部分；
- 仍有环境阻塞与范围外残留待后续确认。

## K2a 的验收方法
1. 新开一个 PowerShell 窗口，不设任何环境变量，直接跑全部测试：这一步是在检查“测试不再依赖手动设的环境变量”。要求：
   - 能跑起来，不再报 4 个配置项缺失
   - 和第 0 步记下的基线比，失败数不增加
```powershell
cd C:\Users\234393\Desktop\tap-ai-backend
uv run pytest -q 2>&1 | Select-Object -Last 15
```
报错：src/tap_ai/persistence/db.py:13: in engine = create_async_engine(...)
```
venv/Lib/site-packages/sqlalchemy/ext/asyncio/engine.py:120: in create_async_engine
sync_engine = _create_engine(url, **kwargs) # type: ignore[no-any-return]
venv/Lib/site-packages/sqlalchemy/engine/create.py:617: in create_engine
dbapi = dbapi_meth(*dbapi_args)
venv/Lib/site-packages/sqlalchemy/dialects/mysql/aiomysql.py:229: in import_dbapi
import("pymysql")
E ModuleNotFoundError: No module named 'aiomysql'
```

2. 开关已经清干净：要什么都不输出。
```bash
git grep -n -E "library_enabled|library_kb_enabled|library_kb_worker_enabled|library_chunk_publish_enabled|library_eval_llm_analysis_enabled" -- src tests .env.example
```
```
tests/api/test_library_kg_api.py:130: old_library_enabled = app_settings.library_enabled
tests/api/test_library_kg_api.py:131: old_library_kb_enabled = app_settings.library_kb_enabled
tests/api/test_library_kg_api.py:133: app_settings.library_kb_enabled = True
tests/api/test_library_kg_api.py:134: app_settings.library_enabled = True
tests/api/test_library_kg_api.py:139: app_settings.library_enabled = old_library_enabled
tests/api/test_library_kg_api.py:140: app_settings.library_kb_enabled = old_library_kb_enabled
```

3. 接口都挂上了（这一步需要手动设 4 个环境变量）：要看到 Library 的评估、切片、知识库接口全部列出来，不需要设任何开关。
```python
uv run python -c "from tap_ai.bootstrap import build_app; app=build_app(); paths=[r.path for r in app.routes if '/library' in getattr(r,'path','')]; print(len(paths)); print('\n'.join(sorted(paths)))"
```
报错：获取模型目录失败，仅使用显式声明的能力
```
httpx.ConnectError: [WinError 10061] No connection could be made because the target machine actively refused it. openai.APIConnectionError: Connection error. 0
```

4. bootstrap.py 只删了 if 那几行：
```powershell
git diff -w src/tap_ai/bootstrap.py | Select-String "^-"
```
```diff
--- a/src/tap_ai/bootstrap.py
- if getattr(app_settings, "library_enabled", False):
- if getattr(app_settings, "library_enabled", False) and getattr(
    app_settings, "library_kb_enabled", False
):
    from tap_ai.application.library_kg import LibraryKgService
- if getattr(app_settings, "library_kb_worker_enabled", False):
- settings = app.state.settings
- if getattr(settings, "library_enabled", False):
- if getattr(settings, "library_enabled", False) and getattr(
    settings, "library_kb_enabled", False
):
    from tap_ai.api.library_kb import router as library_kb_router
    from tap_ai.api.library_kg import router as library_kg_router

    app.include_router(library_kb_router, tags=["library-kb"])
    app.include_router(library_kg_router, tags=["library-kg"])
```

通过以后，在后端目录提交：
```bash
git commit -m "refactor(config): 删除 5 个功能开关，测试统一使用假配置且不读取 .env"
```
