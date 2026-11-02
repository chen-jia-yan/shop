# K1a 执行后情况与问题汇总

## 2. 已确认通过的检查
- 字符检查通过：
  - 命令：`uv run python C:/Users/234393/Desktop/check_chars.py C:/Users/234393/fwd-tap-common/fwd-tap-ingest/src C:/Users/234393/fwd-tap-common/fwd-tap-ingest/tests`
  - 结果：扫描了 72 个文件，发现 0 处问题
- 本次新增/修改的 3 个测试文件格式检查通过：
  - 命令：`python -m ruff format --check tests/test_kg_schema.py tests/test_kg_llm_extract.py tests/test_kg_and_chunk_index.py`
  - 结果：`3 files already formatted`

## 3. K1a 验收相关现状（按 D0 的 4 条指令）
### 3.1 SDK pytest
- 命令：`& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 20`
- 当前结果：`10 errors during collection`
- 直接报错链最终落点：
  - `src/tap_ingest_sdk/parsers/_internal/pptx_parser.py:7`
  - `from pptx import Presentation`
  - `ModuleNotFoundError: No module named 'pptx'`

- 与 D0 中记录的早上基线相比：
  - 早上是 `9 errors during collection`
  - 当前多出的 1 个是：`ERROR tests/test_kg_schema.py`

- 证据与判断：
  - `tests/test_kg_schema.py` 是本轮新增测试文件；
  - 单独运行该文件时，同样因为导入 `tap_ingest_sdk.kg_schema` 进入 `tap_ingest_sdk.__init__` -> client -> parsers -> pptx_parser 链路而被 pptx 缺失卡住；
  - 因此 9 -> 10 的增量，不是编码问题，而是新增测试文件在当前缺 `python-pptx` 的环境里也无法完成 collection。

### 3.2 名单检查（TRAVERSABLE_RELATIONS / RELATION_ZH）
- 命令：
```powershell
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); from tap_ingest_sdk.kg_schema import TRAVERSABLE_RELATIONS, RELATION_ZH; print(TRAVERSABLE_RELATIONS); print(RELATION_ZH)"
```
- 当前结果：未输出名单，直接失败。
- 直接报错链落点同样是：
  - `src\tap_ingest_sdk\parsers\_internal\pptx_parser.py:7`
  - `ModuleNotFoundError: No module named 'pptx'`
- 证据与判断：
  - 这不是 `sys.path` 问题，也不是编码问题；
  - 根因是 `tap_ingest_sdk` 顶层导入链过重，导入 `kg_schema` 前就先触发了 `tap_ingest_sdk.__init__`，随后连带导入 parser 体系，再因为缺 pptx 失败。

### 3.3 后端联动检查
- 命令 1：`uv run python -c "import tap_ai.application; print('ok')"`
- 结果：`ok`
- 命令 2：`uv run pytest -q tests/unit/test_library_kb_ingest_plugin.py 2>&1 | Select-Object -Last 20`
- 当前结果：`2 failed, 17 passed, 1 warning`
- 直接证据：
  - `FAILED tests/unit/test_library_kb_ingest_plugin.py::test_sdk_ingest_success_with_memory_mode_real_sdk`
  - `FAILED tests/unit/test_library_kb_ingest_plugin.py::test_only_sdk_ingest_imports_tap_ingest_sdk`
  - 第二个失败的关键断言为：
    - `Left contains one more item: 'tap_ai/application/library_kg.py'`
- 进一步查证：
  - `src/tap_ai/application/library_kg.py:22` 确实存在：
    - `from tap_ingest_sdk.lexicon import normalize_label`
- 判断：
  - 这里的失败不是编码问题；
  - 是后端现有代码状态与该测试约束不一致。

## 4. 关于“乱码”现象的结论
- 在 `scripts\kg_import_poc.py` 中，源码原文是：
  - `raise RuntimeError("缺少 tap_ingest_sdk，无法计算 normalize_label") from exc`
- 已读取该字符串的文件原始字节，内容是标准 UTF-8 字节序列，可正常匹配。
- 同一条命令在本轮复现时，终端输出为正常中文：
  - `RuntimeError: 缺少 tap_ingest_sdk，无法计算 normalize_label`
- 因此目前证据支持：
  - 截图中的乱码是终端显示链路问题（代码页 / 输出编码 / 渲染），不是源码文件本身编码损坏。

## 5. 当前可确认结论
1. K1a 的核心代码改动与新增测试已经落地。
2. 字符检查与本次测试文件的格式检查已通过。
3. D0 中 K1a 验收未全通过，但当前暴露出的主要问题都不是编码问题：
   - SDK 两条失败主因是当前环境缺 `python-pptx`，且 `tap_ingest_sdk` 顶层导入链会提前触发 parser / pptx 依赖；
   - 后端插件测试失败主因是后端已有 `library_kg.py` 直接 import 了 `tap_ingest_sdk`，与测试约束冲突；
   - 截图里的乱码更像终端显示问题，不是源码编码损坏。

## 6. 待后续处理/决策的问题
- 是否要处理 `tap_ingest_sdk` 顶层导入过重的问题，使 `from tap_ingest_sdk.kg_schema import ...` 不再被 pptx 缺失阻塞。
- 是否要处理后端 `src/tap_ai/application/library_kg.py` 对 `tap_ingest_sdk.lexicon` 的直接依赖，以恢复 `test_only_sdk_ingest_imports_tap_ingest_sdk` 通过。
- 是否要进一步固定终端编码/输出链路，避免中文异常消息在某些会话里显示成乱码。

# 验收k1a sdk的检查
```powershell
cd C:\Users\234393\fwd-tap-common\fwd-tap-ingest & C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 10
```
> 和 D0 第 3 步的基线比：失败数不能增加，passed 要比基线多（多出来的是新增的测试）。

多了一个error,基线是9个
```
ERROR tests/test_chunker.py ERROR tests/test_cli.py ERROR tests/test_env_config.py ERROR tests/test_kg_and_chunk_index.py ERROR tests/test_kg_llm_extract.py ERROR tests/test_kg_plan.py ERROR tests/test_kg_schema.py ERROR tests/test_parser_registry.py !!!!!!!!!!!!!!!!!!!!!!!!!! Interrupted: 10 errors during collection !!!!!!!!!!!!!!!!!!!!!!!!!! 10 errors in 2.34s
```

2. 名单和原来一致（在 SDK 目录）：
```powershell
& C:\Users\234393\Desktop\tap-ai-backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from tap_ingest_sdk.kg_schema import TRAVERSABLE_RELATIONS, RELATION_ZH; print(TRAVERSABLE_RELATIONS); print(RELATION_ZH)"
```
> 要看到：第一行正好是 6 种关系，没有 RELATED_TO；第二行是 7 种关系和它们的中文名。

報錯：`from pptx import Presentation`
`ModuleNotFoundError: No module named 'pptx'`

3. 后端没受影响（在后端目录）：第一条输出 `ok`，第二条没有失败。
```powershell
cd C:\Users\234393\Desktop\tap-ai-backend
uv run python -c "import tap_ai.application; print('ok')"
uv run pytest -q tests/unit/test_library_kb_ingest_plugin.py 2>&1 | Select-Object -Last 5
```
```
-- Docs: [https://docs.pytest.org/en/stable/how-to/capture-warnings.html](https://docs.pytest.org/en/stable/how-to/capture-warnings.html)
============================ short test summary info =============================
FAILED tests/unit/test_library_kb_ingest_plugin.py::test_sdk_ingest_success_with_memory_mode_real_sdk
FAILED tests/unit/test_library_kb_ingest_plugin.py::test_only_sdk_ingest_imports_tap_ingest_sdk
2 failed, 17 passed, 1 warning in 5.33s
```

4. 字符检查：要显示“发现 0 处问题”。
```powershell
uv run python C:/Users/234393/Desktop/check_chars.py C:/Users/234393/fwd-tap-common/fwd-tap-ingest/src C:/Users/234393/fwd-tap-common/fwd-tap-ingest/tests
```
