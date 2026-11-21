# 删除写法与对应的只读计数

删除前先用同样的条件做只读查询，把数量和几条样例告诉用户。

## SQL（MySQL / PostgreSQL）
| 删除写法 | 先做的只读查询 | 风险提示 |
|---|---|---|
| `DELETE FROM t WHERE cond` | `SELECT COUNT(*) FROM t WHERE cond`；`SELECT * FROM t WHERE cond LIMIT 5` | 没有 WHERE = 整表 |
| `DELETE t FROM t JOIN u ...` | 把 DELETE 换成 `SELECT COUNT(*)`，JOIN 和条件不变 | JOIN 条件写错会多删 |
| `TRUNCATE TABLE t` | `SELECT COUNT(*) FROM t` | 整表、不能回滚、会重置自增 |
| `DROP TABLE / DATABASE / INDEX` | `SHOW CREATE TABLE t`（先保存结构） | 结构和数据一起没了 |
| ORM：`session.query(M).filter(...).delete()` | 同样的 filter 换成 `.count()` | filter 为空 = 整表 |

## Cypher（Neo4j）
| 删除写法 | 先做的只读查询 | 风险提示 |
|---|---|---|
| `MATCH (n:L {k:v}) DETACH DELETE n` | `MATCH (n:L {k:v}) RETURN count(n)` | DETACH 会连关系一起删 |
| `MATCH (a)-[r:R]->(b) WHERE ... DELETE r` | 同样的 MATCH，`RETURN count(r)` | 只删关系，节点会变成孤立点 |
| `MATCH (n) DETACH DELETE n` | `MATCH (n) RETURN count(n)` | 整个图都没了（高风险） |
| `MATCH (n:L) REMOVE n.prop` / `REMOVE n:Label` | `MATCH (n:L) WHERE n.prop IS NOT NULL RETURN count(n)` | 属性或标签删了无法恢复 |
| `DROP INDEX / CONSTRAINT` | `SHOW INDEXES` / `SHOW CONSTRAINTS` | 查询会变慢、唯一约束失效 |
共享图库里先按 scope 等范围字段过滤，确认只碰本任务范围的数据。

## 搜索索引 / 云存储
| 删除写法 | 先做的只读查询 | 风险提示 |
|---|---|---|
| Azure Search `delete_documents` | 用同样的过滤条件 `search(filter=..., include_total_count=True)` | 只有查询密钥时本来就删不了 |
| 删除整个索引 / 容器 | 列出索引统计（文档数、大小） | 一般无法恢复 |
| `az storage blob delete-batch` | `az storage blob list --query "length(@)"` | 批量删除范围靠通配符 |

## HTTP 接口
| 删除写法 | 先做的只读查询 | 风险提示 |
|---|---|---|
| `DELETE /xxx/{id}` 或 `POST /xxx/delete` | 先 GET 同一资源，确认存在和内容 | 接口内部可能级联删除 |

## 本项目里的提醒
- 本地 `TAP_AI_LIBRARY_KB_GRAPH_ENABLED=false`；Neo4j 和搜索索引和同事共用。
- jp-poc 搜索索引手上只有查询密钥，实际只读。
