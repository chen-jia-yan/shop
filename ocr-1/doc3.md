内容哈希作 document_id 的方向认可,实现前再补两条,然后就可以进实现:

1. 【关键】解决"更新后旧版本不消失":重新入库某文件时,在插入新 chunk 之前,先按稳定的逻辑键(source_file / 文件路径)删掉它旧的 chunk。否则同名文件内容一变就生成新 id、旧 chunk 永久残留(这正是现在多版本污染的成因)。请说明在哪条入库路径加、怎么保证只删这个文件的旧 chunk、并同样走干跑确认。

2. 【修掉活的孤儿源】/api/files/delete(api_admin.py:240)只删物理文件、不删索引 chunk。请一并处理:要么让它同时删除对应索引 chunk,要么禁用/改道到正规删除入口。给出你的方案。

另外:
- document_id 与 version_id 现在是同一哈希,version_id 冗余 → 既然已确认无依赖,就不必改 version_id 格式了,保持现状,减少改动面。
- 迁移完成后跑一次 backfill_worker_managed_documents 对齐 documents.json,并验证一个既有文档能被完整删除。

这两条补进方案后,把更新后的实现计划发我,就可以进第二步实现了。
</parameter>