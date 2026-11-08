// ===== Neo4j 网页控制台：按作用域（scope）看图谱 =====
// 这些都是只读查询，可以放心运行。

// 0. 先看库里有哪些 scope、各有哪些节点（找到 hk 的 scope 真实名字）
MATCH (n) WHERE n.scope IS NOT NULL
RETURN n.scope AS scope, labels(n) AS 节点类型, count(*) AS 数量
ORDER BY scope, 数量 DESC;

// 1. "切换图谱"：设置一个参数，后面的查询都用 $scope
//    想看哪个就设哪个，下面两行二选一运行
:param scope => 'jp-poc'
:param scope => '<把第 0 步查到的 hk 的 scope 填在这里>'

// 2. 看实体之间的业务关系（jp-poc 有数据；hk 目前没有实体，会是空的）
MATCH p = (a:Entity {scope: $scope})-[r]->(b:Entity {scope: $scope})
RETURN p LIMIT 200;

// 3. 只看某几种关系
MATCH p = (a:Entity {scope: $scope})-[r:NEXT|HANDLED_BY|REQUIRES]->(b:Entity {scope: $scope})
RETURN p LIMIT 200;

// 4. 看文档和切片（hk 现在能看到的就是这一层）
MATCH p = (d:Document {scope: $scope})-[:HAS_CHUNK]->(c:Chunk {scope: $scope})
RETURN p LIMIT 100;

// 5. 从一个实体出发，看它出现在哪些切片、属于哪个文档
MATCH (e:Entity {scope: $scope}) WHERE e.label CONTAINS '理赔'
WITH e LIMIT 5
MATCH p = (e)-[:MENTIONED_IN]->(c:Chunk {scope: $scope})<-[:HAS_CHUNK]-(d:Document {scope: $scope})
RETURN p;

// 6. 以表格形式核对关系（不画图，最准确）
MATCH (a:Entity {scope: $scope})-[r]->(b:Entity {scope: $scope})
RETURN a.label AS 起点, type(r) AS 关系, r.raw_types AS 原始说法, b.label AS 终点
LIMIT 50;
