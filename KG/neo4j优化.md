1 + 2 「全连到一个点 / 太密集」——根因是 mentioned_in 边

你那 38,609 条边里有 37,984 条是 ⁠mentioned_in⁠(实体→切片),所以画面被”众星捧全连到几个切片 hub”占满了,真正的业务关系被淹没。别再 ⁠MATCH (n) RETURN n⁠。改成只看语义边、并限量:
MATCH (a)-[r]->(b)
WHERE r.type <> 'mentioned_in'
RETURN a, r, b
LIMIT 200

想从某个实体出发、看它一到两跳的关系(更聚焦、更不密):
MATCH p=(a {label:'新契約'})-[r*1..2]-(b)
WHERE all(x IN relationships(p) WHERE x.type <> 'mentioned_in')
RETURN p LIMIT 80

再把密度压一压:右上角 齿轮 ⚙ → Graph Visualization,把 ⁠Initial Node Display⁠(默认300)调小,并关掉 ⁠Connect result nodes⁠。

3 「按类型过滤」——用 Cypher 的 WHERE 过滤
Browser 没有勾选式过滤框,过滤靠查询。按类型只看某一类:
MATCH (a)-[r]->(b)
WHERE a.type = 'System' AND r.type <> 'mentioned_in'
RETURN a, r, b LIMIT 150

打完下面第 4 步给节点加了标签后,还能直接点结果区上方的标签小胶囊快速筛那一类。

4 「节点按类型上色」——Browser 只按 :Label 上色,不认属性
这就是你说”标签有颜色却管不到节点”的原因:节点现在多半只有 ⁠:Node⁠ + ⁠type⁠ 属性,没有各自的 ⁠:Label⁠,所以全一个色。先给每种类型补上真正的标签(9 种,逐条跑一次,或在设置里开启多语句一次性粘):
MATCH (n:Node) WHERE n.type='System'   SET n:System;
MATCH (n:Node) WHERE n.type='Concept'  SET n:Concept;
MATCH (n:Node) WHERE n.type='Product'  SET n:Product;
MATCH (n:Node) WHERE n.type='Process'  SET n:Process;
MATCH (n:Node) WHERE n.type='Data'     SET n:Data;
MATCH (n:Node) WHERE n.type='Document' SET n:Document;
MATCH (n:Node) WHERE n.type='Role'     SET n:Role;
MATCH (n:Node) WHERE n.type='Channel'  SET n:Channel;
MATCH (n:Node) WHERE n.type='Chunk'    SET n:Chunk;

跑完后重新查一次图,结果区上方会出现每种类型的标签胶囊。点一个胶囊 → 底部弹出样式条 → 选颜色、还能把 ⁠caption⁠ 设成 ⁠label⁠(显示实体名而不是 id)、调节点大小。每种类型设一次,颜色就落到节点上了。

5 「右栏 source_file 每个文件独立成块」——Neo4j Browser 做不到 ❌
右侧那栏是 Browser 固定的属性查看器(点一个节点,列出它的 key-value),它的结构改不了,没法把 source_file 拆成一块一块。顶多把 source_file 存成数组让它换行好看一点点,但做不到”每个文件独立板块”。

6 「切片正文导入右栏」——同样,Browser 里体验很差 ❌
技术上能把正文 SET c.content=...⁠ 挂到 Chunk 节点,但:① 当初导入时只匹配上了 1,300 / 40,641(因为这版图谱是旧的、chunk_id 对不上);② 就算挂上,Browser 也只会把它当一长串文本塞进属性栏,不是你要的清爽面板。

所以结论很直接:1~4 在 Neo4j Browser 里能解(照上面做);但 5 和 6——右栏分文件、切片正文清爽展示——是你最看重的,偏偏正是 Browser 的死角。这俩只有自定义页能做好。

我的建议:让我用你之前导出的那几个 CSV(nodes / edges / nodes_files / chunk_content)做一个专门的”图谱浏览器”页面,六个问题一次全解决——按类型配色、类型过滤勾选、右栏每个来源文件独立成块、点节点看切片正文,纯离线用文件选择器本地加载,不联网。要我做吗?做的话你确认一下:那几个 CSV 现在还在、字段没变吧?(尤其 chunk_content 那份,因为图谱是旧的,正文可能只能对上一部分,我会在页面里如实标出来。)