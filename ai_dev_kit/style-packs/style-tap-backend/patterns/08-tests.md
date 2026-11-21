# 单元测试

核对日期：2026-11-18
核对状态：待核对（依据迁移过程中的测试约定和多次假通过事故整理；首次使用前请对照来源文件核对）

## 何时使用
- 任何新功能、修 bug、改行为的改动。

## 必须
1. 测试放在项目已有的测试目录（例如 `tests/unit/`），文件名 `test_<模块>.py`，函数名 `test_<行为>_<条件>`。放之前先确认 pytest 能收集到（看 collected 数量）。
2. 只用 fake：为端口写内存版实现（FakeIndexWriter、FakeParser、FakeRepo），通过服务构造函数传入。
3. 配置在测试里显式构造 `Settings(...)`，禁止读取 .env（项目如有 `TAP_AI_DISABLE_DOTENV` 之类开关，按已有测试的方式设置）。
4. 断言具体值：`assert result.status == "skipped"`、`assert writer.upserts == [("idx", 3)]`。
5. 每个新功能至少：正常路径、边界（空、重复、超限）、失败路径（外部报错、只读索引）。
6. 修 bug 先写一条在修复前会失败的测试。
7. 异步测试照抄项目已有的写法（pytest-asyncio 标记或 anyio）。

## 禁止
1. 连接真实 MySQL / Azure Search / Neo4j / 大模型 / Redis。
2. `assert x == x`、`assert True`、只断言 `is not None`、用 `in` 代替相等。
3. `pytest.skip`、`xfail`、`# type: ignore`、`# noqa` 让测试或检查“通过”。
4. 用被测函数自己算期望值。
5. 依赖测试执行顺序或当前时间。

## 精简样例
```python
class FakeIndexWriter:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, int]] = []

    async def upsert_chunks(self, index_name: str, chunks: list[ChunkData]) -> int:
        self.upserts.append((index_name, len(chunks)))
        return len(chunks)


async def test_upload_same_file_twice_is_skipped() -> None:
    writer = FakeIndexWriter()
    service = LibraryKbService(FakeRepo(), FakeParser(chunks=3), writer, Settings(library_kb_enabled=True))
    first = await service.upload(make_file("a.pdf", b"x"))
    second = await service.upload(make_file("a.pdf", b"x"))
    assert first.status == "queued"
    assert second.status == "skipped"
    assert second.document_id == first.document_id
```

## 反例
```python
def test_upload():
    load_dotenv()                                   # 错：读真实 .env
    svc = LibraryKbService.from_env()               # 错：连真实服务
    r = svc.upload("a.pdf")
    assert r is not None                            # 错：几乎永远成立
    assert "ok" in r.message                        # 错：太宽，"not ok" 也通过
```

## 检查项
- [ ] collected > 0，且新增测试出现在输出里
- [ ] 只用 fake，没读 .env
- [ ] 断言具体值
- [ ] 正常 / 边界 / 失败三类都有
- [ ] 没有 skip / xfail / type: ignore / noqa

## 来源
- tests/unit/ — 现有单元测试（找一个 library_ 开头的测试文件作参照）
- tests/conftest.py — 已有 fixture（如存在）
