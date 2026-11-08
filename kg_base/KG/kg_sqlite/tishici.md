## 1. file_hash：文件内容哈希

### 计算代码
有两处完全一致的实现：

① kb_admin/storage.py L37-45（主要使用）
```python
def file_hash_for_path(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)  # 1MB 分块读
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
```

② kb_admin/state_store.py L760-765（state.db 入库时使用）
```python
def _file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
```

### 结论

| 项目 | 值 |
| ---- | ---- |
| 算法 | SHA-256 |
| 计算对象 | 文件内容（二进制逐块读），不是路径/名字 |
| 输出 | 完整 hexdigest，64 位十六进制字符 |
| 分块大小 | 1MB (适应大文件) |

### state.db 真实样本
```
file 1: bb991a7b8f95a5ca088d46e9c8c12be89aca0ea90f55003374ea2c66e96ffe55  (64位)
file 2: 79d132fe484bee7a94b4df3c69544ea2a7c42b7791ab899812f4c464d7457084  (64位)
file 3: 99e75e835a283467b63c21b00c7ca46260407c1de0336699117c29dd899f9c2f  (64位)
file 4: 3c174d9faa4bb9f7c5ac2a152849cd48e846cfa10cddef0f739fef3a34061e4b  (64位)
file 5: 1da241fec845d711f60afbbe2c16ad704112896e3343bb5e130dd085ae916ce1  (64位)
```
✅ 全部 64 位 hex 字符，确认 sha256 完整输出。

## 2. doc_id 规则：`doc::` + file_hash 前 16 位

### 拼接代码
kb_poc/indexing/identity.py L14-19
```python
DOC_ID_PREFIX = "doc::"

def document_id_for_content_hash(content_sha256: str) -> str:
    """已算好的sha256字符串---直接从 state.db 的 file_hash生成ID。"""
    return f"{DOC_ID_PREFIX}{content_sha256[:16]}"
```

### 验证 (取第 1 个文件的 file_hash 实测)
```
file_hash: bb991a7b8f95a5ca088d46e9c8c12be89aca0ea90f55003374ea2c66e96ffe55
doc_id:    doc::bb991a7b8f95a5ca
           ^^^^^^ ^^^^^^^^^^^^^^^^
           前缀    前16位 hex
```
✅ 规则确认：`doc::` + sha256 hexdigest 前 16 位字符。

### 实际写入索引的调用链
1. services.py L727: `index_document_id = document_id_for_content_hash(file_hash)`
2. services.py L729-731: 用这个 `index_document_id` 写入 Azure Search → 清旧 chunk → upsert 新 chunk

### ⚠️ 发现的不一致
kb_poc/ingestion/ingestor.py L343-347 使用另一套规则：
```python
def _build_document_identity(path, source_dir):
    relative = path.resolve().relative_to(source_dir.resolve())
    normalized = relative.as_posix()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"local::{digest}", f"local-version::{digest}"
```
这是 `local::` + sha1(相对路径)[:16]，与 identity.py 的 `doc::` + sha256(内容)[:16] 完全不同。但 `_build_document_identity` 仅在 `ingest_directory()` 内部调用，写入 jsonl 时 doc_id 还是 null —— 真正的 doc_id 是在 worker/services.py L727 写入 Azure 时才用 identity.py 的规则覆盖写入的。因此实际入库到 Azure 的是 `doc::` 规则。


## 3. chunk_id 一致性

### (a) jsonl 中的 chunk_id（file-1.jsonl 前 3 行）
```
chunk_id: 00d8e1fed500
chunk_id: 5e1af8f7f252
chunk_id: 112796cd7260
```
全部 12 位 hex 字符。

### (b) 生成 chunk_id 的代码
kb_poc/ingestion/ingestor.py L219（唯一生成点）
```python
chunk_id = hashlib.sha1(
    f"{document.source_file}:{segment.locator}:{part}".encode()
).hexdigest()[:12]
```
规则：`sha1(source_file:locator:part_text)` → hexdigest 前 12 位

| 输入要素 | 说明 |
| ---- | ---- |
| source_file | 文档文件名（如 `#01_当社システムの全体概要.pptx`） |
| locator | 段落在文档中的位置（如 `slide-1`） |
| part | 切分后的文本片段内容 |

### (c) 与图谱/Azure Search 的 Chunk 节点一致性
当前无法直连 Azure Search 验证（合约限制）。但根据代码追踪：
- jsonl 写入时 chunk_id 已生成（ingestor.py L219）
- Azure Search 写入时原样使用 chunk_id 作为 key（azure_search_store.py L95: `simpleField(name="chunk_id", type="Edm.String", key=True)`）
- services.py L729-731 调用 `index_repo.append_document_chunks()` → `upload_document_chunks()`，chunk_id 不发生任何二次哈希

✅ 三者是同一个值：jsonl 中的 chunk_id 就是最终 Azure Search 中的 key，中间无转换。

## 4. state.db 结构
表名：`files`

### 列定义
```sql
CREATE TABLE files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_name   TEXT,
    batch_id     TEXT,
    path         TEXT NOT NULL UNIQUE,   -- 文件绝对路径
    file_hash    TEXT UNIQUE,             -- sha256 内容哈希（64位），UNIQUE 做去重
    status       TEXT DEFAULT 'pending',  -- pending/processing/completed/failed/dead
    stage        TEXT,                   -- 当前处理阶段
    attempts     INTEGER DEFAULT 0,       -- 处理尝试次数
    crash_count  INTEGER DEFAULT 0,        -- 崩溃次数
    error        TEXT,                    -- 最后错误信息
    updated_at   TEXT,                    -- 最后更新时间
    original_path TEXT                    -- 原始上传路径
);
```

统计：239 行

### 3 行样例
```
path: #01_当社システムの全体概要.pptx
hash: bb991a7b8f95a5ca088d46e9c8c12be89aca0ea90f55003374ea2c66e96ffe55
status: completed

path: #02_OPEN系基礎（Server、DB、NW）、資源管理.pptx
hash: 79d132fe484bee7a94b4df3c69544ea2a7c42b7791ab899812f4c464d7457084
status: completed

path: #06_新契約システム概要.pptx
hash: 99e75e835a283467b63c21b00c7ca46260407c1de0336699117c29dd899f9c2f
status: completed
```

### 关键列说明
| 列 | 用途 |
| ---- | ---- |
| path | 源文件路径（绝对路径），UNIQUE |
| file_hash | 内容哈希（sha256全文），UNIQUE 保证同一内容不重复入库 |
| status | 上传/处理状态：pending → processing → completed/failed/dead |
| original_path | 原始上传路径（可能与 path 不同） |

## 总结
| 问题 | 结论 |
| ---- | ---- |
| file_hash | sha256(文件全部字节).hexdigest()，64位，内容级去重 |
| doc_id | `doc::` + file_hash[:16]，写入 Azure 时由 identity.py 统一生成 |
| chunk_id | sha1(source_file:locator:part)[:12]，jsonl 和 Azure Search 完全一致 |
| state.db | files 表 12 列 239 行，path/file_hash UNIQUE 双重去重 |
```
