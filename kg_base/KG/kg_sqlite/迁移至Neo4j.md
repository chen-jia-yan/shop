背景：把本地知识图谱的「实体图」导入本地 Neo4j（评估试点，非生产）。请帮我执行，但严格遵守下面的红线。

红线（违反即停）：
- data\kg\kg.db 全程【只读】，只允许 SELECT；绝不对 kg.db 执行 UPDATE/DELETE/ALTER/DROP 或任何写操作。
- 【不要】触碰 Azure AI Search、state.db、任何现有的 JSON 图谱文件；【不要】运行 kg_sync 的 apply/delete/rollback。
- 只导入实体图：type <> 'Chunk' 的节点，以及两端都是实体的边。【绝不】导入那 1.6 万个 Chunk 节点或 mentioned_in 关系。
- Neo4j 密码不要写进任何脚本或日志；运行 cypher-shell 时不要用 -p 带明文密码，让我在提示时手动输入。
- 导入前先检查 Neo4j 是否为空；若非空，停下来问我，【不要】自动清库。
- 每一步做完简要汇报，不要擅自做额外操作。

步骤：
1. 用 sqlite3 对 data\kg\kg.db【只读】导出两个 CSV 到新目录 data\kg\neo4j_export\：
   nodes.csv ←
     SELECT n.node_id, n.type, n.label,
       (SELECT GROUP_CONCAT(doc_id,'|') FROM kg_node_sources s WHERE s.node_id=n.node_id) AS source_docs
     FROM kg_nodes n WHERE n.type <> 'Chunk';
   edges.csv ←
     SELECT e.source_id, e.target_id, e.type,
       (SELECT GROUP_CONCAT(doc_id,'|') FROM kg_edge_sources s WHERE s.edge_id=e.edge_id) AS source_docs,
       e.provenance_inferred
     FROM kg_edges e
     WHERE e.source_id IN (SELECT node_id FROM kg_nodes WHERE type<>'Chunk')
       AND e.target_id IN (SELECT node_id FROM kg_nodes WHERE type<>'Chunk');
   （用 sqlite3 的 .mode csv、.headers on 导出，保证 UTF-8。）

2. 找到 Neo4j 安装目录下的 import 文件夹，把 nodes.csv、edges.csv 复制进去（只复制这两个文件，别动 import 里其它东西）。

3. 生成 data\kg\neo4j_export\import.cypher，内容如下：
   CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.node_id IS UNIQUE;
   LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
   CREATE (n:Node {node_id: row.node_id, type: row.type, label: row.label, source_docs: row.source_docs});
   LOAD CSV WITH HEADERS FROM 'file:///edges.csv' AS row
   MATCH (a:Node {node_id: row.source_id}), (b:Node {node_id: row.target_id})
   CREATE (a)-[:REL {type: row.type, source_docs: row.source_docs, inferred: row.provenance_inferred}]->(b);

4. 执行导入：用 cypher-shell -u neo4j（不带 -p，在提示时我手动输密码）运行 import.cypher。
   如果 cypher-shell 不可用或连不上，就把 import.cypher 原样给我，我自己在 Neo4j Browser 里粘贴执行。

5. 导入后验证并报告两个数字：
   MATCH (n:Node) RETURN count(n);
   MATCH ()-[r:REL]->() RETURN count(r);