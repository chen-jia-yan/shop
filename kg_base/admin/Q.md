知识库管理这边，我准备这样调用 SDK，想跟你确认几点：

1. 文档编号：我会用 SourceDocument.from_bytes(content, filename, idempotency_key=固定编号)，每个文档的编号固定不变（格式 doc:: 加 16 位十六进制）。这样文件内容更新后重新入库，begin_document_upsert 会先按同一个编号删掉旧切片。Neo4j 那边，同一个编号重新入库时，旧的关系也会被撤销吗？
2. 两个 sink：我会显式传入 endpoint、index_name、key 来创建 AzureAISearchSink，需要时再加 Neo4jGraphSink。如果 Azure 写成功、Neo4j 写失败，FileIngestResult 的 status 会是什么？
3. 依赖冲突：SDK 要求 Pillow<11、pypdf<5，后端现在用的是 Pillow>=11.1、pypdf>=5.1。SDK 能不能放宽这两个版本？另外 paddleocr 比较大，后端是否一定要装？OCR 有没有更轻的方式？
4. 安装：打算用 Azure Artifacts 私有包仓库，还是 git 依赖？后端构建时的认证由谁来配？
5. AzureAISearchSink 内部还会用 KBSettings.load() 读 embedding 相关的环境变量，后端需要配置哪些？能不能也改成构造时传入？
6. 列出索引里已有的文档：我打算按 document_id 做分组统计（facets），这样可以吗？还是你那边有现成的方法？