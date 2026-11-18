# 接口层写法

核对日期：2026-11-18
核对状态：待核对（依据 api/conversations.py 的路由写法整理；首次使用前请对照来源文件核对）

## 何时使用
- 新增或修改任何 HTTP 接口。

## 必须
1. 每个文件一个 `APIRouter(prefix="/tap/ai/<模块>", tags=["<模块>"])`；接口路径写相对路径（如 `/add`、`/files/list`）。
2. **只用 GET 和 POST**。增删改查用动词路径表达：`/add`、`/update`、`/delete`、`/list`、`/detail`。
3. `@router.post(..., response_model=XxxData)` 写明响应模型；函数标注返回类型。
4. 服务从 `app.state` 取（照抄同文件已有的 `_service(request)` 小函数写法），路由函数里只做：取服务 → 调用 → `XxxData.model_validate(结果)`。
5. 请求体用 Pydantic 模型（`XxxRequest`），字段带约束（长度、范围）；列表接口的分页参数与已有列表接口一致。
6. 业务错误交给服务层抛项目统一的 `BusinessError`，路由不自己拼错误响应。
7. 成功返回的外层结构（有无统一包装）照抄同模块已有接口。

## 禁止
1. 使用 PUT / PATCH / DELETE 方法。
2. 在路由里 `raise HTTPException(500, ...)` 或返回裸 dict。
3. 在路由里写 SQL、调 SDK、写业务判断。
4. 自创新的返回包装格式。

## 精简样例
```python
router = APIRouter(prefix="/tap/ai/library", tags=["library"])


def _service(request: Request) -> LibraryKbService:
    return request.app.state.library_kb_service


@router.post("/files/list", response_model=LibraryFileListData)
async def list_files(body: LibraryFileListRequest, request: Request) -> LibraryFileListData:
    result = await _service(request).list_files(body)
    return LibraryFileListData.model_validate(result)


@router.post("/files/delete", response_model=LibraryDeleteData)
async def delete_file(body: LibraryDeleteRequest, request: Request) -> LibraryDeleteData:
    result = await _service(request).delete_file(body.file_id)
    return LibraryDeleteData.model_validate(result)
```

## 反例
```python
@router.delete("/files/{file_id}")              # 错：用了 DELETE
async def delete_file(file_id: str):
    try:
        svc.delete(file_id)
    except Exception as e:
        raise HTTPException(500, str(e))        # 错：吞掉业务错误码、泄露内部信息
    return {"ok": True}                         # 错：裸 dict，没有 response_model
```

## 检查项
- [ ] 只用了 GET / POST
- [ ] 有 response_model 和返回类型标注
- [ ] 路由函数只有“取服务 → 调用 → model_validate”
- [ ] 请求模型字段有约束
- [ ] 返回结构与同模块已有接口一致

## 来源
- src/tap_ai/api/conversations.py — 路由前缀、`/add` 写法、`_service(request)`、`model_validate`
- src/tap_ai/api/library_kb.py — 知识库接口
- src/tap_ai/api/library_chunks.py — `/files/list` 等列表接口
- src/tap_ai/api/dto.py — 请求/响应模型
