# ORM 模型与仓储（条件更新）

核对日期：2026-11-18
核对状态：待核对（依据 persistence/models.py 里 LibraryChunkDraft 的写法和 rowcount 修复经验整理；首次使用前请对照来源文件核对）

## 何时使用
- 新增表/模型、新增仓储方法，特别是更新状态（pending → processing → completed / failed）。

## 必须
1. ORM 模型类定义在 `persistence/models.py` **模块顶层**，继承 `Base`，写 `__tablename__`（小写下划线）。
2. 字段用 SQLAlchemy 2.0 写法：`xxx: Mapped[类型] = mapped_column(...)`；可空字段 `Mapped[str | None]` + `nullable=True`；多租户字段 `saas_id / workspace_id / project_id / user_id` 带 `index=True`；字符串字段写长度（照抄已有的 `String(n)` / `OptionalString(n)`）。
3. 主键照抄已有写法（`String(32), primary_key=True, default=_new_uuid`）。
4. 状态更新用**条件更新**：`update(Model).where(Model.id == id, Model.status == 旧状态).values(...)`，并检查影响行数；为 0 表示被别人抢先或状态不对，返回 False 让调用方处理。
5. 读取影响行数：**先照抄仓库里已有的写法**；没有现成写法时用 `cast(CursorResult[Any], result).rowcount`（只允许 cast 到 CursorResult，不允许 cast 到 Any）。
6. 查询都带范围条件（saas_id 等），带索引字段过滤。
7. 新表配套 SQL 迁移文件，放在项目已有迁移目录，命名照抄。

## 禁止
1. 把模型类嵌套在另一个类里（真实事故：表没有注册）。
2. 先 SELECT 再在 Python 里判断状态再 UPDATE（并发时会互相覆盖）。
3. 用 f-string 拼 SQL。
4. 在仓储里抛 HTTP 异常、写业务判断。
5. 在循环里每条记录单独 commit。

## 精简样例
```python
class LibraryKbDocument(Base):
    __tablename__ = "library_kb_document"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_uuid)
    saas_id: Mapped[str | None] = mapped_column(OptionalString(64), nullable=True, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class LibraryKbRepo:
    async def transition(self, doc_id: str, from_status: str, to_status: str,
                         error: str | None = None) -> bool:
        stmt = (update(LibraryKbDocument)
                .where(LibraryKbDocument.id == doc_id, LibraryKbDocument.status == from_status)
                .values(status=to_status, error=error))
        result = await self._session.execute(stmt)
        await self._session.commit()
        return cast(CursorResult[Any], result).rowcount == 1
```

## 反例
```python
class TokenUsage(Base):
    __tablename__ = "token_usage"

    class LibraryChunkDraft(Base):        # 错：嵌套定义，表不会按预期注册
        __tablename__ = "library_chunk_draft"

def mark_done(doc_id):
    doc = session.get(Doc, doc_id)
    if doc.status == "processing":        # 错：先读后写，两个 worker 会同时通过
        doc.status = "completed"
```

## 检查项
- [ ] 模型类在模块顶层（checks: nested_orm_class）
- [ ] 字段用 Mapped / mapped_column，长度、可空、索引写清
- [ ] 状态更新带旧状态条件并检查影响行数
- [ ] rowcount 写法照抄已有或 cast 到 CursorResult
- [ ] 查询带范围条件
- [ ] 有对应的迁移文件

## 来源
- src/tap_ai/persistence/models.py — LibraryChunkDraft 等模型
- src/tap_ai/persistence/library_eval_repo.py — 读取影响行数的写法
- src/tap_ai/persistence/library_kb_repo.py — 知识库仓储
- src/tap_ai/persistence/library_draft_repo.py — 草稿仓储
