谢谢！有几件事跟进一下：

1. 依赖版本：我对照了后端的 uv.lock，SDK 需要放宽的一共 4 个：Pillow 改为 >=11.1,<13；pypdf 改为 >=5.1,<7；openai 改为 >=1.0,<3；azure-search-documents 改为 >=11.6,<13。paddleocr 移到可选依赖 [ocr]。我先在本地的 feat/relax-deps-for-backend 分支上改了版本号，跑通后提 PR 给你看。pypdf 和 openai 跨了大版本，可能要改代码，到时候还要你帮忙看一下。
2. 安装方式：正式上线时，后端怎么装 SDK？私有包仓库、git 依赖都可以，你定一个，我来改后端的 pyproject。
3. 测试索引：入库联调时，我不想写你们现在在用的索引。能不能帮我建一个同样结构的空索引，比如 hk-kb-chunk-tap-dit-kbtest？Neo4j 的 scope 也会跟着用这个名字。
4. 嵌入模型：现在 hk 的索引用的是哪个嵌入模型、多少维？AzureAISearchSink 会读 KB_AOAI_ENDPOINT、KB_AOAI_EMBEDDING_DEPLOYMENT、KB_AOAI_EMBEDDING_MODEL、KB_AOAI_API_KEY、KB_EMBEDDING_DIMENSIONS 这几个环境变量，开发环境的这几个值找谁要？
5. Azure 写入要用 admin key，Neo4j 要账号密码。开发环境的这些由谁提供给我？我只放在本机私人的启动脚本里，不会提交。
6. 图谱：重新入库同一个文档时，Neo4jGraphSink 会撤销旧关系，这个我看到了。孤立实体（prune_orphans）一般什么时候清理？