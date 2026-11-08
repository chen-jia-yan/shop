【任务】盘点同事的 SDK 项目，并和 POC 对比（完全只读）
SDK 目录：<填你克隆下来的 SDK 完整路径>
POC 目录：C:\Users\234393\Desktop\jap-cycle-poc

【安全规则，必须严格遵守】
- 两个目录都只读：不修改、不新建、不删除任何文件
- 不运行 SDK 和 POC 中的任何脚本、命令行工具、测试。尤其是任何入库、写索引、写图谱、写数据库的代码，一律不得运行
- 不读 .env 和任何包含密钥的配置文件，不输出任何密码、密钥、连接串。配置只列出配置项的名字
- 不连接 Azure、Neo4j、MySQL 或任何模型服务
- git 只能用 status / log / branch / show / ls-tree 这些只读命令
- 每个结论附 文件:行号 和原文

【一、SDK 概况】
1. 目录结构（两层）、README 原文、pyproject 中的依赖、对外提供的入口（命令行、函数、类）
2. git log --oneline -20、git branch -a：最近在做什么，有哪些分支

【二、入库链路】逐项写出在 SDK 中怎么做，并和 POC 对比（相同 / 不同 / SDK 缺少 / POC 缺少）
3. 文件解析：支持哪些格式（pdf、docx、xlsx、pptx 等），用什么库，表格和图片怎么处理
4. 切分：切分策略、大小、重叠；每个切片带哪些元数据（source_file、页码或 sheet、标题等）
5. 编号规则：doc_id、chunk_id 怎么生成。POC 中是 doc::sha256[:16] 和 sha1(source_file:locator:part)[:12]，SDK 是否一致
6. 向量：用哪个模型，在哪里调用
7. 写入索引：用什么函数写 Azure AI Search，索引名从哪个配置项读；有没有"删除或替换某个文件的全部切片"的函数
8. 增量：怎么判断文件是新增、修改还是删除；状态记录存在哪；失败了怎么重试

【三、知识图谱链路】同样逐项对比
9. 抽取：用什么提示词、什么模型；抽出哪些节点类型和关系类型（列出完整列表）
10. 存储：存到哪里（Neo4j、SQLite、JSON），写入的代码在哪
11. 节点和关系的字段：id 怎么生成、有哪些属性；和 POC 的 kg.db（kg_nodes、kg_edges、kg_node_sources、kg_edge_sources）是否一致
12. 增量：文件变了以后，图谱怎么更新；删除文件时，节点和关系怎么处理
13. 去重、合并实体、推断关系：SDK 有没有做，POC 是怎么做的
14. 哪些地方明显还没写完：TODO、空函数、raise NotImplementedError、注释里写着"待实现"的地方

【四、对照我们的图谱接口】
15. kg_api 中 8 个接口（stats、files/list、graph/overview、nodes/search、nodes/{id}、nodes/expand、nodes/chunks/list、chunks/{id}）需要的数据，
    SDK 产出的数据里有没有：逐个接口说明 有 / 没有 / 字段名不同（列出对应关系）
16. 如果以后改成从 Neo4j 读：SDK 写进 Neo4j 的节点 label、关系 type、属性名，和 kg_api 的字段如何对应

【五、总结】
17. 一张表：SDK 已经做好的、没做完的、和 POC 不一致的、POC 中值得搬到 SDK 的（附理由）
18. 风险清单：哪些函数会写外部服务（索引、图谱、数据库），写的是哪里