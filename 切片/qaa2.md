> **本轮只读排查完成，诊断脚本和方案草案均未执行、未应用。**

核心结论：
1. 后端正常上传时，MySQL `document_key` 会透传为 Azure `document_id`；但 SDK 独立入库可使用**不同的生成规则**。
2. 你遇到的文件在 Azure 有、MySQL 没有，符合“由其他流程直接写入索引”的可能性，但**目前不能断定它具体由哪条流程写入**。
3. “MySQL 元数据完整”不等于“一定可预览”：还涉及身份范围、文件大小、切片顺序及索引状态。

## 一、两个 ID 是怎么生成的
### 1. 后端正常上传
新文件在 `library_kb.py:563` 调用 `new_document_key()`，写入 MySQL 文档行。

生成规则在 `rules.py:43` 和 `rules.py:89`:
```python
DOCUMENT_KEY_PREFIX = "doc::"
DOCUMENT_KEY_RANDOM_HEX_LEN = 16

return f"{DOCUMENT_KEY_PREFIX}{uuid4().hex[:DOCUMENT_KEY_RANDOM_HEX_LEN]}"
```
即 `doc::` 加 16 位小写随机十六进制字符；**不是文件路径、文件名或文件内容哈希**。已有文档的重试、更新路径会复用既有 `document_key`，见 `library_kb.py:429`。

入库 worker 把该键交给 SDK 入库插件：`library_kb_worker.py:319`。插件将它作为 `idempotency_key` 传给 SDK：`sdk_ingest.py:300`。

SDK 解析时优先使用该键；例如 PDF/Markdown 解析器：`SDK 解析器`。索引写入时，SDK 将文档 ID 放入切片的 `document_id`：`Azure 写入代码`。

因此，在**正常执行且遵循当前 SDK 实现**时：
```text
MySQL document_key = SourceDocument.idempotency_key
                   = SDK document_id
                   = Azure 切片 document_id
```
插件还检查处理后的文档 ID 与键是否相等，但这个检查发生在 sink 写入**之后**：`sdk_ingest.py:323`。因此异常、部分写入或实际运行版本不同不能仅凭该检查排除。

### 2. SDK 独立入库
如果调用方没有指定 `idempotency_key`，SDK 使用文件内容的 SHA-256 前 16 位，前缀同样是 `doc::`；`SDK models`。

所以两种 ID **格式相同，但生成依据不同**：

| 路径 | ID来源 | 与文件名、路径关系 |
|---|---|---|
| 后端正常上传 | 随机 UUID 的前16位 | 不由文件名或路径生成 |
| SDK 默认独立入库 | 文件内容 SHA-256 的前 16 位 | 不由文件名或路径生成；相同内容产生相同默认 ID |

这不证明现有问题文件一定是 SDK 独立入库生成的。

## 二、可能出现“有索引、无文档表记录”的路径
| 路径 | 证据 | 本次是否确认发生 |
|---|---|---|
| SDK CLI 直接入库 Azure | `CLI ingest` 构造 sink 并调用 `client.ingest`；`Azure sink` 写索引，不经过后端文档仓储 | 未确认 |
| 其他程序直接使用 SDK 的 Azure sink | 同一 sink 可直接接收处理后的文档并写入 Azure | 未确认 |
| 后端尚未建立文档管理时的旧索引、历史直灌 | `索引清单适配器` 明确说明有此兼容场景 | 未确认本文件来源 |
| 外部系统、人工或其他仓库写索引 | 当前仓库无法穷举外部写入者 | 无法确认，不能列为已发生 |
| 后端写入部分完成后失败、文档后续被处理 | 当前 SDK sink 写入与文档状态更新不是同一个跨系统原子事务 | 可能性，未确认 |

**同步逻辑不是“只写索引不写MySQL”**：它是反方向，从索引清单补齐 MySQL，见 `library_kb.py:1030`。但新增记录的大小为 0、哈希为空、路径为空，因此同步**不能保证通过基线校验**。本次没有执行同步。

JP 旧索引的具体写入来源，本轮没有找到足够的完整证据，不能断言所有 JP 文件都来自某一个流程，也不能宣称已列尽外部写入路径。

## 三、只读诊断脚本草案——请先审阅，不执行
下面的草案使用**人工提供的 Azure 只读凭证和 MySQL 只读账号**，不读取 `.env`，只执行 Azure 搜索和 SQL `SELECT`。它要求明确指定租户与索引；**不会自动证明该索引就是后端实际映射的索引**。

重要边界：
- `a` 改名为“元数据完整候选”，**不能断言一定可预览**。
- `b` 包含已删除、非 `indexed`、缺元数据或大小为 0；不检查具体用户的身份范围。
- `c` 按项目的文件名规范化方式匹配 `name_key`，只表示**疑似**，不是确认同一文件。一个文件名可能对应多个候选。
- 每个分类最多展示 10 个 Azure ID；`c` 每个示例最多展示 10 个 MySQL ID。ID 可能是敏感业务标识，请只在授权环境查看。
- Azure 分面有 10,000 文件上限；结果缺失、不完整或超时时脚本报错，不给出貌似完整的统计。
- Azure 与 MySQL 不是原子快照，排查时仍可能并发变化。

```python
"""只读诊断草案：Azure 文件 ID 与 MySQL 文档记录。
未执行、未验证。运行前必须审阅并确认目标环境。
仅允许使用 Azure 查询凭证和 MySQL SELECT-only 账号。
环境变量由操作者在当前进程中设置，不从 .env 加载：
DIAG_AZURE_ENDPOINT
DIAG_AZURE_INDEX
DIAG_AZURE_QUERY_KEY
DIAG_MYSQL_ASYNC_URL
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import unicodedata
from collections import defaultdict

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

MAX_GROUPS = 10_000
BATCH_SIZE = 200
EXAMPLE_LIMIT = 10

def normalize_name(value: str) -> str:
    name = value.split("/", 1)[-1].split("\\", 1)[-1]
    return unicodedata.normalize("NFKC", name).strip().lower()

def batches(values: list[str]):
    for start in range(0, len(values), BATCH_SIZE):
        yield values[start : start + BATCH_SIZE]

def probe_table(values: list[str]) -> tuple[str, dict[str, str]]:
    # SQL 结构仅由整数生成，所有用户及索引值均为绑定参数。
    clauses = [f"SELECT :p{i} AS probe" for i in range(len(values))]
    params = {f"p{i}": value for i, value in enumerate(values)}
    return " UNION ALL ".join(clauses), params

def document_filter(file_id: str) -> str:
    escaped = file_id.replace("'", "''")
    return f"document_id eq '{escaped}'"

async def get_index_files(client: SearchClient) -> list[tuple[str, str]]:
    results = await client.search(
        search_text="*",
        facets=[f"document_id,count:{MAX_GROUPS + 1},sort:value"],
        top=0,
        include_total_count=True,
    )
    facets = await results.get_facets()
    total = await results.get_count()

    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise RuntimeError("Azure 返回无效计数")
    if not isinstance(facets, dict) or not isinstance(
        facets.get("document_id"), list
    ):
        raise RuntimeError("索引 document_id 分面不可用")
    buckets = facets["document_id"]
    if len(buckets) > MAX_GROUPS:
        raise RuntimeError("文件分组超限，不能报告完整结果")

    groups: dict[str, int] = {}
    for bucket in buckets:
        if not isinstance(bucket, dict):
            raise RuntimeError("索引分面无效")
        file_id = bucket.get("value")
        count = bucket.get("count")
        if (
            not isinstance(file_id, str)
            or not file_id.strip()
            or file_id in groups
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
        ):
            raise RuntimeError("索引分面无效")
        groups[file_id] = count

    if sum(groups.values()) != total:
        raise RuntimeError("分面与索引计数不一致，结果不可用")

    files: list[tuple[str, str]] = []
    for file_id in sorted(groups):
        rows = await client.search(
            search_text="*",
            filter=document_filter(file_id),
            select=["document_id", "source_file"],
            top=1,
        )
        items = [row async for row in rows]
        if (
            len(items) != 1
            or items[0].get("document_id") != file_id
            or not isinstance(items[0].get("source_file"), str)
            or not items[0]["source_file"].strip()
        ):
            raise RuntimeError("索引文件信息缺失或查询期间发生变化")
        files.append((file_id, items[0]["source_file"]))
    return files

async def query_documents(conn, tenant: str, values: list[str], field: str):
    if field not in ("document_key", "name_key"):
        raise ValueError("不支持的查询字段")
    found = defaultdict(list)
    for batch in batches(values):
        probes, params = probe_table(batch)
        params["tenant"] = tenant
        # 字段名来自上方固定白名单；输入值始终使用参数。
        query = text(
            f"""
            SELECT q.probe, d.document_key, d.status, d.deleted,
              d.storage_path IS NOT NULL AND d.storage_path <> '' AS has_path,
              d.content_sha256 IS NOT NULL AND d.content_sha256 <> '' AS has_hash,
              d.file_name IS NOT NULL AND d.file_name <> '' AS has_name,
              d.size_bytes
            FROM ({probes}) q
            JOIN library_kb_document AS d
              ON d.{field} = q.probe
              AND d.saas_id = :tenant
            """
        )
        result = await conn.execute(query, params)
        for row in result.mappings():
            found[row["probe"]].append(row)
    return found
```

```markdown
```python
async def diagnose(tenant: str) -> dict:
endpoint = os.environ["DIAG_AZURE_ENDPOINT"]
index = os.environ["DIAG_AZURE_INDEX"]
key = os.environ["DIAG_AZURE_QUERY_KEY"]
mysql_url = os.environ["DIAG_MYSQL_ASYNC_URL"]

engine = create_async_engine(mysql_url, echo=False)
try:
async with SearchClient(
    endpoint=endpoint,
    index_name=index,
    credential=AzureKeyCredential(key),
) as client:
    files = await get_index_files(client)

async with engine.connect() as conn:
    ids = [file_id for file_id, _ in files]
    by_id = await query_documents(conn, tenant, ids, "document_key")

missing = [
    (file_id, name)
    for file_id, name in files
    if not by_id.get(file_id)
]
names = sorted({normalize_name(name) for _, name in missing})
by_name = await query_documents(conn, tenant, names, "name_key")

report = {
    "a_metadata_complete_candidates": {"count": 0, "examples": []},
    "b_record_ineligible_or_incomplete": {"count": 0, "examples": []},
    "c_same_name_possible_id_mismatch": {"count": 0, "examples": []},
    "d_no_id_or_name_match": {"count": 0, "examples": []},
}

for file_id, filename in files:
    records = by_id.get(file_id, [])
    if len(records) > 1:
        raise RuntimeError("同一索引ID匹配多个数据库记录，停止统计")

    if records:
        row = records[0]
        complete = (
            row["status"] == "indexed"
            and not row["deleted"]
            and row["has_path"]
            and row["has_hash"]
            and row["has_name"]
            and isinstance(row["size_bytes"], int)
            and row["size_bytes"] > 0
        )
        category = (
            "a_metadata_complete_candidates"
            if complete
            else "b_record_ineligible_or_incomplete"
        )
        example = {"azure_id": file_id}
    else:
        candidates = [
            row["document_key"]
            for row in by_name.get(normalize_name(filename), [])
            if not row["deleted"]
        ]
        if candidates:
            category = "c_same_name_possible_id_mismatch"
            example = {
                "azure_id": file_id,
                "mysql_ids": candidates[:EXAMPLE_LIMIT],
                "mysql_match_count": len(candidates),
            }
        else:
            category = "d_no_id_or_name_match"
            example = {"azure_id": file_id}

    item = report[category]
    item["count"] += 1
    if len(item["examples"]) < EXAMPLE_LIMIT:
        item["examples"].append(example)

    return report
finally:
    await engine.dispose()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    args = parser.parse_args()

    try:
        result = asyncio.run(diagnose(args.tenant.strip().lower()))
    except Exception as exc:
        # 不输出异常正文：驱动异常可能包含连接信息、查询参数或标识符。
        print(f"诊断失败: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

**审阅提示：** 该草案使用项目现有 Azure/SQLAlchemy 依赖的常见接口，但本轮未验证当前安装版本签名，也未测试。文件名元数据需要对每个 Azure 文件读一次摘要，MySQL 则按批查询；大索引会有较多只读请求。它不检查权限归属，不应给普通用户运行。

## 四、方案 A：列表增加可预览信息
**建议把字段语义定义为“当前已检查条件下的预览资格”，不要承诺一定成功。** 若不读取切片顺序，布尔值为 `true` 也仍可能因缺少 `chunk_index` 等原因失败；因此最好改名为 `preview_metadata_ready`，或增加 `unknown` 状态。若必须用 `previewable: bool`，应明确它只代表**静态预检查通过**。

设计性 diff 草案，**不是可直接应用的补丁**：
```diff
# contracts/library.py、api/dto.py
class FileSummary / LibraryFileData:
+ previewable: bool
+ preview_unavailable_reason: str | None

# persistence/library_kb_repo.py
+async def batch_preview_metadata(..., document_keys: list[str]):
+ # 按租户及当前可信身份批量查询；每批使用参数化 IN
+ # 返回状态、必要元数据与大小检查结果，不返回路径或哈希

# application/library_chunks.py
items, total = await source.list_files(...)
+metadata = await repo.batch_preview_metadata(
+   scope=当前可信身份, document_keys=[item.file_id for item in items]
+)
+# 为当前页逐项补充资格和稳定原因码
return items, total
```

**范围和风险：**
- 至少涉及列表服务、文档仓储、响应 DTO/契约、API 文档与测试；所有租户的文件列表响应会新增字段。
- MySQL 查询应**按当前页分批**，避免 N+1；搜索和分页行为保持不变。
- 当前文件列表只按租户列出索引文件；精确告诉用户“别人的记录存在但不属于你”会泄露归属信息。未授权与不存在应对外合并成中性原因，例如 `source_unavailable`。
- DB 异常不能返回一排 `false` 假装校验完成，应明确报错，或经设计确认使用可表达“未知”的状态。
- `storage_path/hash/name` 齐全还不够；必须考虑状态、删除、当前身份、大小上限；切片顺序与并发变化仍可能使之后的预览失败。

## 五、方案 B：拆分基线错误原因
目前 `library_chunk_preview_common.py:134` 把“无可访问记录”和“缺路径、哈希、文件名”合为同一提示。

建议：
```diff
document = await repo.get_document_for_preview(...)
-if document is None or missing_metadata:
-  raise source_unavailable
+if document is None:
+  raise source_unavailable # 不区分不存在与无权限
+if missing_path_or_hash_or_filename:
+  raise metadata_missing
```
已有的大小错误与状态校验保持明确提示。原因码若新增到响应 `data`，需先核对 `handlers` 的 `BusinessError.details` 契约并取得接口变更确认；**只增加多语言 message key 风险更小**
确需“无记录、无权限、状态错误、元数据缺失”四种精确原因，前两者存在枚举和泄露风险，应仅供内部授权诊断，不能直接返回给所有调用者。
涉及预览校验、消息键、五种语言词表及对应测试；现有 `CCB001` 可以保持不变。

## 六、哈希、路径与“看到的就是保存的”
- **路径**：当前基线检查路径存在，但不读取原文件，也没有把路径保存进预览记录：`library_chunk_preview_common.py:134`。
- **文件哈希**：基线把哈希保存为 `source_version`；生成候选时重新读取并与基线版本比较：`library_chunk_preview_live.py:271`。保存草稿时锁定文档并再次比对哈希：`library_chunk_preview_live.py:401`。
- **切片和候选指纹**：读取预览、保存草稿时重新计算源切片与候选结果，并比较双指纹：`library_chunk_preview_transform.py:22`、`library_chunk_preview_live.py:298`。

如果把源文件校验从基线挪到候选预览，**不一定立刻破坏双指纹对“保存结果与候选结果一致”的检查**；但会改变基线的可信身份和源版本保证，且现有生成流程要求基线持有 `source_version`。没有设计替代的身份授权、版本绑定与保存时复核前，不能直接移动校验，更不能声称保证不变。Azure 数据并发变化也不构成跨系统原子快照。

## 七、回归测试设计
全部使用假 Azure 数据源和假 MySQL：
1. 四类：完整记录、缺字段/非 indexed、同名不同 ID、完全无记录；断言分类及每类最多 10 个示例。
2. 名字碰撞、多候选、已删除记录、大小为 0；不将同名认定为同一文件。
3. 不同租户及身份范围：不泄露其他用户记录；数据库不可用不伪造 `previewable=false`。
4. 单页多个文件只进行批量查询；文件数超过单批时验证批次与结果完整。
5. A 的字段兼容、排序分页不变；B 的对外提示及五种语言键完整。
6. 基线创建后文件哈希、源切片或候选算法变化：生成/保存必须拒绝不一致结果；保持草稿幂等。
7. 分面超限、数量不一致、Azure/MySQL 异常时明确失败，不输出部分统计。

**未完成：** 脚本未保存到仓库、未执行；没有连接真实 Azure/MySQL，也没有运行测试或修改代码。
```