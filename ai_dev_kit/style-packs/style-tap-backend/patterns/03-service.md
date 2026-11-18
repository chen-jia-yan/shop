# 服务层与错误码

核对日期：2026-11-18
核对状态：待核对（依据迁移过程中确认的 BusinessError 用法整理；首次使用前请对照来源文件核对）

## 何时使用
- 写业务逻辑：校验、编排仓储和外部端口、决定返回什么。
- 需要返回业务错误时。

## 必须
1. 服务类通过构造函数接收依赖（仓储、端口、settings），不在方法里临时创建客户端；这样测试时可以传 fake。
2. 业务错误抛 `BusinessError(错误码, 说明)`；**错误码先搜索已有的**（`grep -rn "BusinessError(" src`），能复用就复用，需要新码时停下来问用户，不要自己编前缀。
3. 一个公开方法完成一个用例（上传、删除、重试、列表），方法名是动词短语。
4. 外部调用（解析、向量化、写索引、写图）都经过 contracts 里的端口，并有超时。
5. 写共享资源前检查范围：例如写索引前确认目标不在“禁止写入的索引”列表里，写图数据前确认 scope。
6. 返回 contracts 或 DTO 能直接 `model_validate` 的数据结构。

## 禁止
1. 在服务层导入 FastAPI、读取 Request。
2. 捕获所有异常后返回 None 或空列表（吞掉错误）。
3. 用 `getattr(settings, "xxx", 默认值)` 读配置。
4. 直接导入某个插件的内部实现。

## 精简样例
```python
class LibraryKbService:
    def __init__(self, repo: LibraryKbRepo, parser: DocumentParser, writer: IndexWriter,
                 settings: Settings) -> None:
        self._repo = repo
        self._parser = parser
        self._writer = writer
        self._settings = settings

    async def delete_file(self, file_id: str) -> LibraryDeleteResult:
        doc = await self._repo.get(file_id)
        if doc is None:
            raise BusinessError("CCB001", f"文件不存在：{file_id}")
        if doc.index_name in self._settings.library_kb_write_forbidden_indexes:
            raise BusinessError("CCB001", "该索引只读，不能删除")
        await self._writer.delete_document(doc.index_name, doc.id)
        await self._repo.mark_deleted(file_id)
        return LibraryDeleteResult(file_id=file_id, status="deleted")
```
（错误码以项目实际已有的为准，样例里的 CCB001 仅示意。）

## 反例
```python
class LibraryKbService:
    async def delete_file(self, file_id):
        try:
            client = SearchClient(os.environ["KEY"])     # 错：方法里创建客户端、读环境变量
            client.delete(file_id)                        # 错：没检查只读索引
        except Exception:
            return None                                   # 错：吞掉错误
```

## 检查项
- [ ] 依赖都从构造函数传入
- [ ] 错误码复用已有的，没有自创前缀
- [ ] 写共享资源前检查了只读/范围
- [ ] 没有吞掉异常
- [ ] 外部调用有超时

## 来源
- src/tap_ai/application/library_kb.py — 知识库服务
- src/tap_ai/application/library_chunks.py — 分块服务
- src/tap_ai/application/library_eval.py — 评估服务
- `grep -rn "BusinessError(" src` — 已有错误码
