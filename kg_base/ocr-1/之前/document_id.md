# 第一步：只读确认结果 + 统一 document id 方案
## 任务书5个问题的确认结果（均已实证，含对任务书猜想的修正）
**1. 全量重建 `replace all` 的 document id 从哪来？是不是 None→"None"?**
- 来源：`azure_search_store.py` `replace all` 里 `payload = chunk.metadata.to_dict()`，取 metadata 的 `document_id`。
- **任务书猜想部分不成立**：`ChunkMetadata`**有**`document_id`字段（`models.py:43`，`str | None = None`）；全量ingest路径会由`ingestor.py:337` `_build_document_identity`写入`local::<sha1(相对路径)16位>`；且`replace_all`对 None写的是`""`不是`"None"`。
- 索引实证：字符串`"None"` = 0条，空串 = 0条，`local::` = 0条。当前索引根本不是`replace all`建的。

**2. 增量上传（worker）的 document id 怎么生成？**
- 确认是 `worker::<绝对路径 posix>`（`upload.py:69` `build_worker_document_identity`），`version_id` 是 `worker‑version‑<毫秒时间戳>`。
- 索引实证：32363个chunk里**32325条（99.9%）是`worker::C:/Users/23493/Downloads/...`绝对路径格式**，共176个不同文档路径。

**3. 删除用什么 filter？**
- 确认是 `document_id eq '<id>'`（`azure_search_store.py:171` `delete_document_chunks`；`count_document_chunks`同）。**没有 source_file 兜底**。

**4. 管理层 documents.json 的id格式、在哪生成、删除时传哪个？**
- 格式：`new_id("doc")`随机id（`doc_xxx`），生成于`services.py:360`；删除时`services.py:281`把这个`doc_xxx`**原样**传给`delete_document_chunks` → 和索引里的`worker::`永远匹配不上 → **删除实际删0条，孤儿chunk就是这么来的**。
- 更大发现：**documents.json 当前是空的（0条文档）** —管理层簿记与worker链路完全脱节（上传走SQLite files表 + worker，没人往documents.json写）。
- 管理层内部还自相矛盾：`services.py:670`查stats用的是`worker::<path>`格式，删除却用`doc_xxx`。

**5. ChunkMetadata 有没有 document id？**
- 有，`str | None = None`。

**附带发现**：索引里有**38条 document_id 为 null 的 chunk**（样例都是`#01_当社システムの全体概要.pptx`—就是之前发现有乱码重复的那批）；另外`get_document_count`=32413与分页实拉32363差50条，疑似与乱码重复文件相关，未定位。

## 统一 document id 方案（待你批准）
**规则**：`document_id = "doc::" + sha1(相对路径 posix)[:16]`，`version_id = "docver::" + sha1(相对路径 + 内容哈希)[:16]`

- **相对路径基准**：文件相对其入库根目录（`source_dir`/上传目录）的posix路径。全量ingest和worker上传都能算出来，同一文件无论谁入库都得同一个id—稳定、可推导、与机器/盘符无关（解决worker绝对路径换机器就失效的问题）
- **两条写入路径**：`ingestor._build_document_identity`和`upload.build_worker_document_identity`都改为调用同一个新函数（放`kb_poc/models.py`或公共处），格式统一为`doc::*`。
- **管理层**：`services._ingest_file`注册文档时用同一规则算`doc::*`作为 document_id（替换`new_id("doc")`），这样删除时传给索引的id天然能对上。
- **多路径/多版本同一 source_file**：同一文件从不同目录入库会产生不同`doc::*`（相对路径不同）。删除时：① 按统一id精确删；② **同时按`source_file eq '<文件名>'`兜底删**（任务书允许的方式），干跑时分别列出两类将删的数量，由人确认。

- **存量兼容**：
    - 32,325条`worker::*`旧id：提供一次性**迁移脚本**（只读拉出 chunk_id+旧 document_id+source_file → 本地重算新id → merge回写；**由你在自己环境执行，我不自动跑**）；
    - 38条 null id：迁移时按 source file归到对应新id；
    - 迁移完成前，删除路径**同时兼容旧`worker::`id匹配**（保留旧匹配逻辑做兜底），不让旧数据变孤儿。
    - **删除干跑**：`delete document`先出"将删除 N 条 chunk，涉及 document id 列表 [...]"，确认后才真删。

**红线遵守**：只动`document_id/version_id`的写入与删除簿记；embedding、切分、检索排序、worker调度/锁/幂等一律不改。

**风险**：迁移脚本回写32k条是最重的操作（可分批、可先小批试跑）；新旧id并存期删除路径双匹配逻辑要防误删（干跑 + source_file精确匹配兜底）。

---
方案到此，**未改任何代码**。你批准后我再按第二步的护栏实现。有要调整的点（比如id规则想用别的基准）也现在提。
