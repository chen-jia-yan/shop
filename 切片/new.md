# 切片排查报告-2026-11-26

## 0. 用户补充的真实响应

用户补充基线响应为 `code=CCB001`、`message=预览源文件不可用`、`data=null`，并提供 `total_items=423`、`total_pages=22`、`go_page=1`、`page_size=20`；基线响应为 `data=null`，该总数不能来自此基线的 `data.source`。

用户随后确认 423 和 22 来自 `/files/list`；它们表示文件列表总数和总页数，不是所选文件的切片数，也不能说明 `/chunks/list` 返回了什么。

用户对 `library_kb_document` 执行了按所填租户与 `document_key=file_id` 的只读统计，报告三个数量均为 0：匹配记录数、已索引未删除数、必要元数据齐全数。它证明该查询实际使用的库和输入条件下没有匹配文档；它仍不能解释普通 `/chunks/list` 的实际表现。

用户随后确认查询使用的数据库与后端相同，租户及 `file_id` 与基线请求完全一致。由此可定位本次基线错误：MySQL 缺少该租户及 `document_key=file_id` 的文档记录，当前代码在读取切片前查不到预览源。条件是运行服务执行的逻辑与当前代码一致；实际运行版本及查询到请求之间是否有并发数据变化未独立核实。本结论不适用于尚未取证的普通 `/chunks/list` 空结果。

纠正现象：这次基线不是“成功返回空切片”，而是明确的业务失败，HTTP 200 不代表业务成功。按当前源码，该提示对应 `library_chunk_preview_common.py:134` 的租户或文件 ID 为空，或者按租户、ID、状态和非空身份范围查询未找到文档，或者文档缺少路径、哈希、文件名。上述情况共用同一提示，还不能确定具体哪一项。正常控制流中这一步失败发生在读取 Azure 切片之前，证据：`library_chunk_preview_live.py:229`。

这条证据定位了基线失败的阶段，不证明普通 `/chunks/list` 的返回是什么；运行服务与当前源码是否一致也尚未独立核实。先前某 HK 文件的工作空间与项目不匹配是历史个例，不能直接当成本次文件的根因。

## 1. 结论与证据等级

基线报错原因已定位，普通切片列表的空结果原因尚未确认。用户确认同一数据库、租户和 `file_id` 下不存在对应文档；按照当前代码，基线在读取线上切片前会因此返回“预览源文件不可用”。仍未独立核实运行服务版本和数据库并发变化。未取得普通切片列表的业务响应、Azure 原始响应和索引 schema，不能将它的空结果归因于字段、租户、排序或分页。

已确认：

1. 当前代码中的文件列表使用 Azure `document_id` 分面值作为 `file_id`；普通切片查询也使用同一个 `document_id` 等值过滤。文件 ID 不被去前缀、去扩展名、转大小写或 `strip`。证据：`azure_chunk_source.py`、`azure_chunk_source.py`。
2. 基线预览会先查询数据库文档并校验归属、状态及元数据，再读取全部线上切片；成功创建基线会新增并提交预览元数据，因此它不是只读接口。证据：`library_chunk_preview_live.py`、`library_live_preview_repo.py`。
3. 如果运行服务确实是当前这份代码，且响应 `code=00000`，基线的源切片总数必须大于 0；但请求页超出总页数时，`source.items` 可以为空而 `source.total_items` 仍大于 0。仅有 HTTP 200、或只看到空 `items`，不能判断为成功空数据。证据：`library_chunk_preview_live.py`、`library_chunk_preview.py`、`handlers.py`。
4. 本地端口 9006 存在监听进程，只能证明端口在监听，不能证明进程使用当前源码、哪一个索引或请求成功。
5. 本次工作区 HEAD 是 `c89d70a`；之前加入文件列表的身份过滤已不在当前受跟踪源码中，仍有一个未跟踪的旧过滤测试文件。不要把先前版本的过滤行为误认为当前列表行为。

## 2. 六个假设

| 假设 | 判定 | 依据与限制 |
| --- | --- | --- |
| H1 字段或值不一致 | 无法确认实测；当前代码字段一致 | 分面 `document_id` 赋值到 `FileSummary.file_id`，`_document_filter` 也过滤 `document_id`。真实两次请求值、运行进程版本与索引数据未取得；不能排除前端传参或运行版本本身差异。 |
| H2 转义、字段属性或集合类型 | 无法确认 | 单引号在 `_document_filter` 中加倍；`#`、`::`、空格、日文、斜杠在 Python 构造过滤表达式时不被额外改写。是否为可过滤的单值字符串由实际 schema 决定，未读取 schema，也未验证完整 HTTP 序列化。现有假对象测试覆盖 `doc'1` 文件摘要语义，但本次未运行测试。 |
| H3 `chunk_index` 缺失或不可排序 | 无法确认当前目标索引；已确认失败不会在本链路变成成功空列表 | 切片分页和 `get_file` 内定位符查询都使用 `chunk_index asc`；对应查询或结果迭代异常会包装成 `ChunkSourceError`，再转为 `CCB001`；预览对被识别的缺字段错误使用顺序不可用提示。错误消息不匹配时也是一般错误，不是空成功。历史项目记忆曾记录 JP 缺字段日志，但不证明本次目标索引同样缺失。 |
| H4 租户或索引不同 | 无法确认实测；不存在静默默认索引代码 | 两条路由使用统一请求上下文、同一装配的数据源；`_client_for` 按归一化租户映射索引，无映射抛错，不回退默认索引。两次真实上下文可能不同；索引名未实测。 |
| H5 分页或映射 | 无法确认；页码越界是可验证假设 | `go_page` 从 1 开始，`skip=(go_page-1)*page_size`；越界可得到 `items=[]`、`total_items>0`。基线也先取得全部 `source`，再按请求页切片。`page_or_sheet` 可为 None，非整数 `chunk_index` 映射为 `part_index=None`；预览会拒绝无可靠顺序，而非默默丢记录。响应模型异常走错误信封，不是静默过滤。真实页码和总数未取得。 |
| H6 异常吞掉 | 无法确认具体实测；未发现主读取异常转成功空列表的路径 | `_search`、`_collect`、`_result_count` 捕获异常后记录并抛数据源错误；API 异常处理器多数返回 HTTP 200 但 `code=CCB001`、`data=null`。仅检查 HTTP 状态会误以为没有错误。详见第 5 节。 |

## 3. 两条主要调用链及基线补充

### A. 文件列表 `/tap/ai/library/files/list`

1. `library_chunks.py:82`：路由接收 `keyword/go_page/page_size`，调用 `ChunkReviewService.list_files`，返回 `Page`。
2. `library_chunks.py:83`：`tenant_from` 取当前身份上下文；调用 `source.list_files`。
3. `azure_chunk_source.py:81`：`_client_for` 按租户选索引；`_file_groups` 先分面，再 `_file_metadata` 读取文件摘要；当前实现不是扫描所有切片后在应用层聚合。
4. `azure_chunk_source.py:96`：调用参数为 `search_text="*"`，`facets=["document_id,count:10001,sort:value"]`，`top=0`，`include_total_count=True`；最多接受 10000 个文件分组，并校验分组计数之和。
5. `azure_chunk_source.py:133`：文件元数据调用使用 `filter=_document_filter(file_id)`、`select=["document_id","source_file","doc_type"]`、`top=1`；若查到文档 ID 与分面值不一致则报错。
6. `routing.py:77`：正常分页封装为 `code/message/data`。

关键代码（摘录）：

```
file_id, count = bucket.get("value"), bucket.get("count")
# 仅用 strip 判断是不是空白，不会修改 file_id 的值
if not isinstance(file_id, str) or not file_id.strip():
    raise ChunkSourceError("索引文件分组无效")
counts[file_id] = count
# 后续
return FileSummary(file_id=file_id, source_file=source_file,
                   doc_type=str(doc_type) if doc_type else None,
                   chunk_count=count)
```

上面是摘录，原始分支还包含其他校验，不能将摘录作为完整实现复制。

### B. 普通切片 `/tap/ai/library/chunks/list`

1. `library_chunks.py:134`：隐藏于 Swagger，但仍可 POST；调用 `ChunkReviewService.list_chunks` 并逐项转 DTO。
2. `library_chunks.py:111`：读取请求上下文租户，先调用 `source.get_file`；不存在则业务错误，再调用 `source.list_chunks`。
3. `azure_chunk_source.py:169`：`get_file` 先 count，再查文件字段，再扫描定位符。定位符扫描本身也按 `chunk_index asc` 排序，可能在正式切片分页之前失败。
4. `azure_chunk_source.py:207`：`list_chunks` 发起带排序、分页和总数的查询，将每一行映射为 `ChunkView`。
5. `library_chunks.py:134`、`routing.py:77`：逐项 `model_validate`，分页信封原样返回；没有逐条过滤空字段的逻辑。

切片分页实际代码传给 SDK 的参数模板（这是代码模板，不是本次真实抓包）：

```
search_text = "*"
filter = "document_id eq '<file_id 中单引号替换为两个单引号>'"
order_by = ["chunk_index asc"]
select = ["chunk_id", "document_id", "source_file", "page_or_sheet", "content", "chunk_index"]
top = page_size
skip = (go_page - 1) * page_size
include_total_count = True
```

实际 Azure 请求具体序列化结果、目标索引名、count 和错误内容本次未抓取，不能称为原样实测请求。示例：ID `doc'1` 得到 `document_id eq 'doc''1'`。

过滤实现：

```
return f"document_id eq '{str(file_id).replace(chr(39), chr(39) * 2)}'"
```

定位符查询另用 `select=["document_id","page_or_sheet"]`、`order_by=["chunk_index asc"]`、动态 `top` 和 `skip`；count 查询使用 `select=["chunk_id"]`、`top=1`、`include_total_count=True`。它们都是同一个 `document filter`。

### C. 基线 `/tap/ai/library/chunk-previews/baseline`

1. `library_chunk_preview.py:78`：`create_baseline` 返回 `baseline` 和 `source`；`source.items` 是完整读取结果按请求页的切片。
2. `library_chunk_preview_live.py:264`：`create_baseline` → `_create_live`。
3. `library_chunk_preview_common.py:134`：按租户和非空的 `workspace/project/user`，用 `document_key=file_id` 查 MySQL 已索引、未删除记录，检查文件名、路径、哈希和大小。此检查比文件列表严格。
4. `library_chunk_preview_live.py:84`：通过同一个 `chunk_source.list_chunks` 从第 1 页、每页 200 条读齐，要求总数大于 0、页非空、ID 唯一且顺序递增。
5. `library_chunk_preview_live.py:245 → library_live_preview_repo.py:20`：保存预览记录并提交。因此本次没有实测基线。

注意：`/library/chunks/list` 与 `/library/chunk-previews/chunks/list` 不是同一路由，后者查询候选预览，参数是 `preview_id` 而不是文件 `file_id`。

## 4. 身份、索引与响应

- `deps.py:45` 解析并绑定请求上下文；`identity.py:125` 在请求内优先使用上下文租户，不使用请求体覆盖。
- `bootstrap.py:856` 使用租户注册表的 `index_by_saas` 构造唯一数据源；`azure_chunk_source.py:236` 根据租户 `strip().lower()` 查索引映射，不存在则抛错。
- 两次请求实测解析出的索引名：未获取。不能靠代码推断具体值，也未读取任何凭据或配置值。
- `page.py:8` 的 `go_page >= 1`，默认 1；`envelope.py:68` 基于总数计算总页数。超过最后一页不自动归回第一页。
- `handlers.py:97` 业务错误也可能返回 HTTP 200；必须同时核对 `code`、`message` 和 `data`。

## 5. 空结果与异常出口排查

- `_file_groups` 的 facet/计数异常或数据不完整：记录并抛错，不返回空列表；一个真正没有切片的索引可以返回空分组。
- `_search`、`_collect`、`_result_count`：捕获异常，记录后抛 `ChunkSourceError`；`_source_call` 转业务错误。`_result_count` 对非整数、负数也抛错。
- `_first_file_fields` 查询到空时返回空文件名和类型，不代表整个切片结果为空。`_collect_locators` 空页时结束扫描，返回可能为空的定位符列表，不清空切片分组。
- `get_chunk` 在 `ResourceNotFoundError` 时返回 None，是单条 chunk 点查，与本次两个列表主路径无关。
- 关闭缓存客户端的异常仅记录 debug，不构造列表。提交草稿处宽泛异常不在本次只读链路。
- Azure 结果迭代本身的返回零时，`list_chunks` 可直接返回空列表及 Azure count；越界页属于正常空页。基线额外检查零行和总数，不能按成功空全集处理。
- 响应校验错误和未捕获异常分别映射 HTTP 200、`CCB001`、`data=null`，并非成功空 `items`。

## 6. 本次实测与未完成项

- 本地监听检查：`127.0.0.1:9006` 存在 LISTEN（不证明应用版本或可用性）
- `files/list` 请求与响应：未实测，未获得安全的请求身份及原始响应
- `chunks/list` 请求与响应：未实测，同上
- `baseline`：未调用；成功执行会写入并提交预览记录，与本次禁止写数据冲突
- Azure 搜索原始 `filter/orderby/count`：未实测
- Azure 索引 schema、`filterable/sortable`、字段类型：未实测
- 无 `orderby` 对照及第二个文件：未实测

没有读取或输出 `.env`、密钥、认证头、切片正文或数据库连接地址；没有运行会写入预览数据的接口，也没有运行真实数据库测试。历史图示中的身份信息不足以证明本次现象，亦不应复用其中凭证。

## 7. 后续只读取证与条件性修复

先请操作者在同一登录身份、同一租户和同一服务下，对文件 A 记录 `/files/list` 返回的 `file_id`、`chunk_count`；请求普通 `/chunks/list` 第 1 页并提供脱敏后的 `code/message/data.total_items/data.total_pages/items` 数量。如已有基线响应，请提供原有请求的 `go_page/page_size` 及 `code/message/source.total_items/source.total_pages/source.items` 数量，不必再调用基线。再选文件 B 对照。不要提供认证头、切片正文、个人信息或数据库连接地址；若 ID 本身敏感，请用一致的代号代替，并说明是否有单引号、空格、斜杠等字符。

由具有只读权限的操作者在 Azure Portal 或已有安全工具中，分别验证目标索引的字段属性，按相同 `document_id` 查询并对比有无排序，投影仅限非正文的必要字段。不要输出 endpoint、凭据、正文或其他个人信息；如索引名属于敏感信息，提供一致代号即可。还需核实运行服务的部署版本与当前 `c89d70a` 是否相同。

修复方案尚不能锁定，故不提供可直接应用的真实 diff。根据证据再选最小修改：
当前代码有从索引清单补齐文档表的同步逻辑，但它属于写操作，且新建记录时 `size_bytes=0`、`content_sha256=""`、`storage_path=None`，不能直接满足现有基线的源元数据校验；具体文件的归属和原文件来源也没有查明。不得把调用同步或手工插入记录当作已验证的解决方案。证据：`library_kb.py:1030`。

1. 若只是页码越界：优先检查前端选择文件时是否重置为第一页；若要更改后端越界语义须确认兼容性。
2. 若索引缺 `chunk_index`：可考虑仅对普通浏览提供明确提示或经确认后的兼容展示；在无法证明原始顺序时，不能为预览用任意排序伪造稳定顺序。需要核查可排序的其他稳定字段及其业务含义；改动会影响依赖该数据源的所有相应租户、普通切片浏览和预览，不应盲目降级。
3. 若真实 `filter/索引不一致`：针对已验证的传参、转义或租户解析处修复，保持对外字段与其他租户兼容。

建议追加假数据源回归：特殊字符 ID 在列表与切片的同一过滤表达式中保持一致；缺失或不可排序的 `chunk_index` 不被伪装成成功空列表；两个请求租户不一致时索引选择及失败行为；首页、越界页、`total_items > 0` 的空页；基线确保源为空时报业务错误；通过 DTO 的可空字段不丢记录。建议另加离线 SDK 序列化验证；真实索引行为仍需只读联调。

## 8. 核对表

- 当前工作区静态调用链与六个假设检查。
- 区分普通切片接口、基线预览及候选预览接口。
- 明确基线有数据库写入，未调用。
- 用真实请求复现、索引 schema 和 Azure 原始响应：未取得安全访问条件。
- 根因及可执行最小 diff：等待实测，不猜测。
- 运行测试：本次未运行；用户要求不写任何数据。
- 不修改项目代码、索引、数据库和 Git 状态；仅创建本报告。