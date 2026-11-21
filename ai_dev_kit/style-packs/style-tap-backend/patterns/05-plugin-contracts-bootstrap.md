# 插件、契约（端口）与启动装配

核对日期：2026-11-18
核对状态：待核对（依据 bootstrap.py 的 _mount_routers / app.state 装配方式和 SDK 接入经验整理；首次使用前请对照来源文件核对）

## 何时使用
- 接入外部系统（文档解析 SDK、Azure AI Search、Neo4j、大模型）。
- 新增服务后，需要在启动时创建并让接口能拿到它。

## 必须
1. 在 `contracts/` 里用 `Protocol`（或项目已有的抽象方式）定义端口：只写方法签名和数据结构，不导入任何外部 SDK。
2. 在 `plugins/` 里写适配器实现端口；外部 SDK 只在适配器里导入。
3. SDK 可能不在后端虚拟环境里：适配器里用**延迟导入**（在方法或工厂函数内部 import），导入失败时给出清楚的错误，而不是让整个应用启动失败。
4. `bootstrap.py` 里：按已有模式创建服务（照抄已有的 container / 工厂写法）→ 挂到 `app.state.xxx_service` → 在 `_mount_routers` 里注册新路由。
5. 功能开关关闭时：不创建依赖外部系统的适配器，路由仍可注册但返回“未启用”的业务错误（照抄已有模块的做法）。
6. 要求隔离的模块（例如 SDK 里的 schema 定义文件）不能导入项目里的重依赖。

## 禁止
1. application 或 api 直接 `import` 某个外部 SDK。
2. 在模块顶层导入可能不存在的 SDK（会让测试收集阶段就失败）。
3. 修改同事的问答知识插件 `plugins/extensions/knowledge/`（`backends/kg_browse.py` 除外，需任务明确要求）。
4. 新增导入时形成循环导入（contracts 不能导入 application / plugins）。

## 精简样例
```python
# contracts/library_kb.py
class IndexWriter(Protocol):
    async def upsert_chunks(self, index_name: str, chunks: list[ChunkData]) -> int: ...
    async def delete_document(self, index_name: str, document_id: str) -> None: ...


# plugins/ingest/sdk_ingest.py
class SdkDocumentParser:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def parse(self, path: Path) -> list[ChunkData]:
        from tap_ingest_sdk import parse_file  # 延迟导入：SDK 不一定在当前环境
        return [ChunkData.model_validate(c) for c in parse_file(path)]


# bootstrap.py（示意，按已有模式写）
if settings.library_kb_enabled:
    app.state.library_kb_service = LibraryKbService(repo, SdkDocumentParser(settings), writer, settings)
_mount_routers(app)  # 在这里加 library_kb.router
```

## 反例
```python
# application/library_kb.py
from tap_ingest_sdk import parse_file        # 错：业务层直接依赖 SDK；SDK 不在环境里时测试全挂
from tap_ai.plugins.extensions.knowledge.service import QaService   # 错：依赖同事插件内部
```

## 检查项
- [ ] 端口在 contracts，适配器在 plugins
- [ ] 外部 SDK 只在适配器里、延迟导入
- [ ] bootstrap 按已有模式挂 app.state 并注册路由
- [ ] 开关关闭时不会因缺配置报错
- [ ] 没有循环导入（checks: test_collection、isolated_imports）
- [ ] 没碰同事的插件

## 来源
- src/tap_ai/bootstrap.py — 服务装配、_mount_routers
- src/tap_ai/contracts/library.py、src/tap_ai/contracts/library_kb.py — 端口定义
- src/tap_ai/plugins/ingest/sdk_ingest.py — SDK 适配器（含只读索引检查）
- src/tap_ai/plugins/extensions/knowledge/backends/kg_browse.py — 图谱浏览适配器（唯一允许改的同事插件文件）
