# 第二步实现完成｜改动清单 & 验收方案

## 改动清单（9改2新增，共11个文件）

|文件|改动说明|
|---|---|
|`identity.py`（新增）|统一身份规则：`doc::<sha256(内容)前16位>` + `legacy_worker_document_id`兼容函数|
|`upload.py`|worker写入改用内容哈希id（version_id不变）；**入库前清理旧chunk**（环境变量`KB_PREINSERT_CLEANUP`，默认`dry`仅输出计划日志）|
|`ingestor.py`|全量ingest采用同一套内容哈希id规则|
|`services.py`|① `delete_document`重写：候选id自动收集(全版本哈希+旧管理id+旧worker id) + `dry_run`干跑 + source_file兜底显式开关；② `_ingest_file`索引侧写内容哈希id + 预清理；③ backfill查数兼容新旧id；④ 新增`collect_index_document_ids_for_path`（仅绝对路径匹配，**不按文件名**）、`delete_chunks_for_path`|
|`api_admin.py`|删除接口增加`?dry=1`、`source_file_fallback=1`参数；**`/api/files/delete`修活**：先删除索引chunk，再删除物理文件，索引删除失败时不删除文件|
|`azure_search_store.py` + repo三层|新增`count/delete_chunks_by_source_file`（OData转义），仅兜底开关启用|
|`config.py`|新增`KB_PREINSERT_CLEANUP`配置开关|
|`migrate_document_ids.py`（新增）|存量32k迁移脚本：默认干跑、`--execute --limit N`小批量执行、幂等可重跑、输出映射日志、迁移前后条数核对、null id仅唯一归属才归并|

**红线复核**：embedding/切分/检索排序/worker调度/锁/幂等逻辑一律未改动；version_id格式保持原样。

## 验证结果
- `py_compile` ×11 ✅
- 本地仓库8场景单测全过 ✅（同文件id稳定、内容变更id改变、干跑不执行删除、真实删除5条全部清除、**同名不同文件不受影响**、`delete_chunks_for_path`逻辑正常）
‑ 迁移脚本对真实索引干跑 ✅：可正确识别旧`worker::`id并算出对应chunk数量（例：`#01`共23 chunks → `doc::bb991a7b8f95a5ca`）

## 待执行验收（不触碰真实索引写操作）
```powershell
# 1.迁移小批试跑
python -m kb_admin.migrate_document_ids --execute --limit 2

# 2.全量迁移(确认无误后)
python -m kb_admin.migrate_document_ids --execute

# 3.对齐管理层
# 调用 backfill_worker_managed_documents(或UI触发)

# 4.删除验收:UI或API先 ?dry=1查看计划，再执行真实删除

# 5.确认预清理日志无误后，把 KB_PREINSERT_CLEANUP=on 写入 .env
```

## 风险与回退
1. 所有删除路径：**先干跑后真实执行**
2. 写入规则回退：`git checkout`恢复这11个文件；依靠迁移日志反向查询旧id。

