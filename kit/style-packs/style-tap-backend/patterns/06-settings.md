# 配置项与功能开关

核对日期：2026-11-18
核对状态：待核对（依据 config/settings.py 与 TAP_AI_ 前缀的环境变量整理；首次使用前请对照来源文件核对）

## 何时使用
- 新增配置项、功能开关、外部服务地址/密钥的读取。

## 必须
1. 配置项统一声明在 `config/settings.py` 的 Settings 类里（pydantic-settings），写类型和默认值；环境变量是 `TAP_AI_` 前缀 + 大写字段名（例如 `library_kb_enabled` ↔ `TAP_AI_LIBRARY_KB_ENABLED`）。
2. **新功能开关默认 False**（例如 `library_kb_enabled`、`library_kb_graph_enabled`）；开启后缺少必要配置时，启动或调用时给出清楚的错误说明缺哪一项。
3. 代码里直接用 `settings.xxx`，靠类型检查发现拼写错误。
4. 列表类配置（例如禁止写入的索引）用 `list[str]`，默认空列表，照抄已有列表字段的解析方式。
5. 密钥类字段用项目已有的类型（如 SecretStr，如项目在用）且不打印到日志。
6. 新增配置项时同步更新 `.env.template`（只写键名和说明，不写真实值）。

## 禁止
1. `getattr(settings, "xxx", 默认值)`（真实事故：掩盖拼写错误，功能静默失效）。
2. 在业务代码里 `os.environ[...]` / `os.getenv(...)` 直接读环境变量。
3. 新功能默认开启。
4. 打开、读取、打印 `.env` 或 `.env.example`（后者含真实口令，应尽快轮换）。

## 精简样例
```python
class Settings(BaseSettings):
    # ---- 知识库管理 ----
    library_kb_enabled: bool = False
    library_kb_graph_enabled: bool = False
    library_kb_max_files_per_upload: int = 20
    library_kb_write_forbidden_indexes: list[str] = []
    kb_azure_search_endpoint: str = ""


def require_kb_search(settings: Settings) -> None:
    if settings.library_kb_enabled and not settings.kb_azure_search_endpoint:
        raise BusinessError("CCB500", "已开启知识库但未配置 TAP_AI_KB_AZURE_SEARCH_ENDPOINT")
```

## 反例
```python
enabled = getattr(settings, "libary_kb_enabled", True)   # 错：拼错了也不报错，而且默认开启
endpoint = os.getenv("TAP_AI_KB_AZURE_SEARCH_ENDPOINT")   # 错：绕过 Settings
```

## 检查项
- [ ] 新配置在 Settings 里有类型和默认值
- [ ] 新功能开关默认 False
- [ ] 没有 getattr(settings, ...)（checks: getattr_settings）
- [ ] 没有 os.getenv / os.environ
- [ ] .env.template 同步了键名（没有真实值）

## 来源
- src/tap_ai/config/settings.py — Settings 定义
- src/tap_ai/plugins/extensions/knowledge/settings.py — 同事插件的配置写法（只读参考，不要改）
