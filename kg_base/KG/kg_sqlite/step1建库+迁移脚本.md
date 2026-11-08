目标：建立知识图谱 SQLite 存储，并写一次性迁移脚本把当前图谱导入。先只 dry-run，不生成正式库。
硬约束：不碰 Azure；只读挂载 state.db（file:...?mode=ro）；不修改/不写入 state.db；不删除、不覆盖现有任何 JSON 图谱和 v1~v9；改动走 plan mode 给 diff。

已确认的事实（照此实现，不要再自己推断）：
- file_hash = sha256(文件内容)，完整 64 位，存于 state.db 的 files 表。
- doc_id = 'doc::' + file_hash 的前 16 位。关联表达式用：'doc::' || substr(file_hash,1,16)。
- chunk_id = sha1(source_file:locator:part)[:12]，jsonl 与 Azure 一致；迁移时 Chunk 节点 id 一律取现有图谱里的原值，不要重算。
- 当前生效图谱通过 get_active_graph() 得到（active=null 时是 provenance 基线），迁移就迁它。
- state.db 表名 files，关键列 path / file_hash / status。

1. 放入 kb_poc/skills/kg_sync/stores/sqlite_schema.sql（我已提供的建表语句：kg_nodes / kg_edges / kg_node_sources / kg_edge_sources / kg_changelog / kg_meta + 索引）。另在其中加一个视图：
   CREATE VIEW IF NOT EXISTS v_file_doc AS
   SELECT path, file_hash, 'doc::'||substr(file_hash,1,16) AS doc_id FROM ingest.files;
   （视图依赖 ATTACH ingest，使用前先挂载。）

2. 写 scripts/kg_migrate_json_to_sqlite.py：
   - 用 get_active_graph() 取当前图谱。
   - 节点逐个写 kg_nodes；其 source_docs 数组拆成多行写 kg_node_sources(node_id,doc_id)。
   - 边逐个写 kg_edges，edge_id = sha256(f"{source}|{type}|{target}")[:32]；其 source_docs 拆成 kg_edge_sources。
   - 整个导入在一个事务里。
   - 校验（任一不符就报错、并删除本次生成物）：
     · SQLite 节点数 == JSON 节点数；边数一致；按 type 分组计数一致。
     · 随机抽 20 个节点，其 kg_node_sources 的 doc_id 集合 == JSON 里该节点 source_docs 集合。
     · 检查所有 doc_id 是否都是 'doc::' 开头且长度=21（doc:: + 16 位）；不符的列出来（可能是回填时没映射上的，记 warning，不中断）。
   - kg_meta 写 schema_version=1、migrated_from=<来源文件名>、last_seq=0、migrated_at=<时间>。
   - --dry-run（默认）：只用内存库 :memory: 跑一遍 + 打印全部统计，不生成磁盘文件。
   - --apply：才写 data/kg/kg.db；若该文件已存在则报错退出，不覆盖。

3. 只跑 --dry-run，把统计（各表行数、按 type 的节点/边数、doc_id 异常数）给我。--apply 由我手动执行。
→ 停。