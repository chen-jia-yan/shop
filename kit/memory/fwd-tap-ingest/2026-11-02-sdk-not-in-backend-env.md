---
id: 2026-11-02-sdk-not-in-backend-env
type: fact
project: fwd-tap-ingest
subject: 后端 pyproject 没有声明 SDK 依赖，本地需手动安装 SDK 及其解析依赖
tags: 依赖, pptx, 环境
status: active
priority: normal
created: 2026-11-02
verified: 2026-11-18
source: 修1b 排查
citations:
  - pyproject.toml#python-pptx
---
事实：SDK 的 pyproject 把 python-pptx、python-docx、openpyxl、pypdf 列为必需依赖，但后端 pyproject 没有引用 SDK，后端虚拟环境里默认既没有 SDK 也没有这些依赖。
原因：缺依赖时，导入 SDK 的解析器会失败，入库插件可能整个不可用。
怎么用：本地用 uv pip install --offline 手动补装；执行 uv sync 后需要重新安装；线上环境如何安装 SDK 要问同事。
