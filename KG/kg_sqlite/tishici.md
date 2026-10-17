只读调查，不写文件、不改代码、不碰 Azure。给出 文件:行号 证据：

1. 入库系统怎么算 file_hash：
   - 贴出计算 file_hash 的代码。
   - 它是对"文件内容"还是"文件路径/名字"算的？用的什么算法（sha256？）？取多少位？
   - 从 state.db 取 2 个真实 file_hash 值贴出来，数一下是多少位。

2. doc_id 的规则：
   - 代码里 'doc::' 后面接的是完整 file_hash 还是截断（如前 16 位）？贴出拼接 doc_id 的代码。
   - 取一个文件，把它的 file_hash 和图谱里对应的 doc_id 并排贴出来，确认拼接规则。

3. chunk_id 一致性（关键）：任选一个文件，并排贴出：
   (a) data/kb_admin/jsonl/file-{hash}.jsonl 前 3 行里的 chunk_id；
   (b) 当前图谱里同一文件的 Chunk 节点 id；
   (c) 生成 chunk_id 的代码（是不是 sha256(正文)[:12]，还是别的规则）。
   明确回答：三者是不是同一个值。

4. state.db 结构：列出记录文件的那张表的所有列、行数，贴 3 行样例，说明哪列是 source_file、file_hash、上传状态。

输出一份简短调查结果，停。