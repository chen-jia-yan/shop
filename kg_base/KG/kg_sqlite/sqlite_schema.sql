-- 知识图谱 SQLite 存储结构 v1
-- 说明：WAL 模式和 foreign_keys 在连接代码里用 PRAGMA 设置，不写在这里。

-- 节点：实体节点（System:xxx 等）和 Chunk 节点都存这里
CREATE TABLE IF NOT EXISTS kg_nodes (
  node_id       TEXT PRIMARY KEY,   -- 'System:SFDC' 或 chunk 的哈希 id
  type          TEXT NOT NULL,      -- System/Concept/Product/Process/Data/Document/Role/Channel/Chunk
  label         TEXT NOT NULL,      -- 显示名
  metadata_json TEXT,               -- Chunk 节点的 source_file/page_or_sheet/cell_range，其它可空
  created_seq   INTEGER,            -- 第几次变更时加入（对应 kg_changelog.seq）
  updated_seq   INTEGER
);

-- 边：语义边（包含/属于/支撑…）和 mentioned_in 都存这里
CREATE TABLE IF NOT EXISTS kg_edges (
  edge_id             TEXT PRIMARY KEY,   -- sha256('源|类型|目标') 前 32 位
  source_id           TEXT NOT NULL,
  target_id           TEXT NOT NULL,
  type                TEXT NOT NULL,
  provenance_inferred INTEGER NOT NULL DEFAULT 0,  -- 1=推断来源（规则共现等）
  bridge_reason       TEXT,
  metadata_json       TEXT,
  created_seq         INTEGER,
  updated_seq         INTEGER,
  UNIQUE (source_id, type, target_id)
);

-- 节点来源：一行 = “这个节点由这个文档贡献”。引用计数 = 这里的行数
CREATE TABLE IF NOT EXISTS kg_node_sources (
  node_id TEXT NOT NULL,
  doc_id  TEXT NOT NULL,
  PRIMARY KEY (node_id, doc_id)
);

-- 边来源：同上
CREATE TABLE IF NOT EXISTS kg_edge_sources (
  edge_id TEXT NOT NULL,
  doc_id  TEXT NOT NULL,
  PRIMARY KEY (edge_id, doc_id)
);

-- 变更流水：每次 apply 一行。delta_json 带“改之前的值”，用于回滚
CREATE TABLE IF NOT EXISTS kg_changelog (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,
  op          TEXT NOT NULL,      -- add/update/delete/rollback
  doc_id      TEXT,
  source_file TEXT,
  ts          TEXT NOT NULL,      -- ISO 时间
  status      TEXT NOT NULL,      -- committed / rolled_back
  delta_json  TEXT NOT NULL
);

-- 元信息：schema_version、last_seq、migrated_from 等
CREATE TABLE IF NOT EXISTS kg_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- 索引：加速“按文档找/删”“查邻居”“按类型筛”
CREATE INDEX IF NOT EXISTS idx_ns_doc ON kg_node_sources(doc_id);
CREATE INDEX IF NOT EXISTS idx_es_doc ON kg_edge_sources(doc_id);
CREATE INDEX IF NOT EXISTS idx_e_src  ON kg_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_e_tgt  ON kg_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_n_type ON kg_nodes(type);
