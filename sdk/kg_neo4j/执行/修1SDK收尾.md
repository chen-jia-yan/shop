# 文档内容
## 6. 核对表
| 编号 | 状态（完成 / 未找到 / 未做 / 已停下） | 证据所在的文件:行号或命令 |
| ---- | ---- | ---- |
| 开工确认1-3 | 完成 | 修K1a补_开工前确认.md |
| 1 | 完成 | tests/test_kg_and_chunk_index.py:286-295 |
| 2 | 完成 | src/tap_ingest_sdk/sinks/_neo4j.py:120-132, 371-379 |
| 3 | 完成 | tests/test_kg_and_chunk_index.py:87-113 |
| a-d | 已停下 | 本文件“4. 验证结果（原始输出）” |

## 7. 当前状态与风险
本轮目标代码已按要求收口，但验证没有全绿，原因有两个，且都不是本轮允许范围内能直接修掉的：
1. `python -m pytest -q tests` 被环境缺少 `docx` 卡住，导致 SDK 全量测试无法满足 0 error
2. `python -m ruff check ...` 被当前 Python 环境缺少 `ruff` 卡住

这两个阻塞都已如实保留原始输出，没有绕过，也没有越权处理。




---

## 四、核对表
- i. 把 `tests/conftest.py` 顶部假数据库 URL 从缺失驱动改成当前已安装异步驱动：完成。证据：`tests/conftest.py:18-23`；验证见“7.2”，`aiomysql` 阻塞已不再出现。
- ii. 删除 `tests/api/test_library_kg_api.py` 里 `library_enabled` / `library_kb_enabled` 旧开关残留：完成。证据：`tests/api/test_library_kg_api.py:126-134`。
- iii. 把 `test_only_sdk_ingest_imports_tap_ingest_sdk` 改成允许名单守卫：完成。证据：`tests/unit/test_library_kb_ingest_plugin.py:563-578`；定向验证见“7.1”。
- iv. 把 `normalize_label` 从 `application/library_kg.py` 移到插件层 `kg_browse.py`：完成。证据：`src/tap_ai/application/library_kg.py:57-68`、`src/tap_ai/plugins/extensions/knowledge/backends/kg_browse.py:15-20,265-270`；定向验证见“7.1”。
- v. 不改 `src/tap_ai/plugins/extensions/knowledge/` 下除 `backends/kg_browse.py` 外的任何文件：完成。证据：本次改动文件清单只命中 `kg_browse.py`。
- vi. 不读取 `.env`、不改依赖、不连接外部服务：完成。证据：本次改动文件与 diff 中无 `.env` / `pyproject.toml` / `uv.lock` 改动；验证命令均为本地静态检查或本地测试。

## 五、残留问题与处理结论
1. 全量 `pytest -q` 现在不再被 `aiomysql` 卡住，但会继续暴露下一个环境问题：`scripts/kg_import_poc.py` / `sdk_ingest.py` 需要 `tap_ingest_sdk`，而当前后端测试环境找不到该包。
2. `uv run pytest -q tests/api/test_library_kg_api.py tests/unit/test_library_kb_ingest_plugin.py` 里，除了本次已改的守卫测试通过外，`test_sdk_ingest_success_with_memory_mode_real_sdk` 仍因 `No module named 'tap_ingest_sdk'` 失败。这说明修2a要求中的“查清依赖问题”已经查清：当前不是 `.pptx` 缺失，而是后端环境没有把 SDK 包放进可导入路径。
3. 全量 `ruff check .`、`mypy src` 仍有仓库既有问题；本次未越权处理。
