你是这个仓库的后端排查助手。只读排查，不改代码，不写任何数据（可以对索引、数据库做只读查询）。目标：找出"/files/list 能返回文件和 file_id，但用这个 file_id 调 /chunks/list 返回空，接口也不报错"的根因，每个结论都要有代码位置或实测证据。

【现象】
- 接口：POST /tap/ai/library/files/list 正常返回文件，带 file_id
- 接口：POST /tap/ai/library/chunks/list 传同一个 file_id，HTTP 正常，没有报错，切片列表为空
- 相关代码大概在：azure_chunk_source.py（索引读取，按 chunk_index 排序，文件列表扫描切片后聚合，有扫描上限）、contracts/library.py、对应的 api 路由和 application service、envelope.py

【第一步：画出两条调用链】
分别写出 /files/list 和 /chunks/list 从路由到服务、数据源、Azure Search 请求的完整调用链，每一步给出文件名和行号。重点回答：
1. /files/list 返回的 file_id 是从索引的哪个字段来的？有没有经过加工（拼前缀、去扩展名、编码、大小写转换、strip、取 document_key 或 source_file）？把加工代码贴出来。
2. /chunks/list 用哪个索引字段过滤 file_id？过滤串是怎么拼的？把最终的 filter、orderby、select、top、skip 原样写出来。
3. 两个字段、两种处理方式能不能对上？

【第二步：逐条确认或排除下面 6 个假设，每条都要写"成立 / 不成立 / 无法确认"，并给出证据】
H1 字段不一致：files/list 的 file_id 和 chunks/list 过滤用的不是同一个字段，或者不是同一个值。
H2 过滤转义或比较方式有问题：file_id 里有单引号、#、::、空格、日文、斜杠时，OData 过滤串对不对（单引号要写成两个单引号）；这个字段在索引 schema 里是不是 filterable；是不是集合类型（是的话要用 any()）。
H3 排序字段缺失：orderby 用了 chunk_index，目标索引的 schema 里有没有这个字段，是不是 sortable。字段不存在时 Azure 返回 400，看代码有没有吞掉这个错误、返回空列表。
H4 租户或索引不同：两个接口各自怎么解析 saas_id，怎么决定查哪个索引；chunks/list 如果没收到 saas_id，会不会退回默认索引。把两次请求实际解析出的索引名写出来。
H5 分页或映射有问题：go_page 是从 0 还是从 1 开始，skip 怎么算；total 和 items 是否一致；响应转换 DTO 时，有没有因为字段缺失或类型不对把记录丢掉（比如 part_index、page_or_sheet 为 null）。
H6 异常被吞掉：在调用链上全局搜索 except Exception、except、return []、logger.warning，列出所有可能让错误变成"空结果"的地方。

【第三步：实测（只读）】
在 dev 或者能连的环境里：
1. 调一次 /files/list，取一个返回的 file_id（原样贴出来，包括特殊字符）。
2. 用这个 file_id 调 /chunks/list，贴出请求和响应。
3. 临时加一条 debug 日志，或者用断点、脚本，打印 chunks/list 发给 Azure Search 的最终请求（index 名、filter、orderby、top、skip）和 Azure 原始返回的 count 和错误信息。不要提交这段代码。
4. 用 Azure Search 只读查询直接验证：
   a. 用相同的 filter，但不带 orderby，查得到吗？
   b. 用 search=* 加 select 查这个文件的一条切片，看各字段的真实值（file_id、document_key、source_file、chunk_index 有没有、是什么类型）。
   c. 拿索引的字段定义（GET indexes/{name}），确认这几个字段是不是 filterable、sortable。
5. 换一个文件名里没有特殊字符的文件再试一次，对比结果。

【第四步：输出格式】
1. 根因：一句话，加上代码位置和证据。
2. 六个假设的判定表。
3. 两个接口的调用链和关键代码片段。
4. 实测的请求和响应原文（去掉 key 和正文内容）。
5. 修复方案：给出最小改动的 diff 建议（先不要应用），说明会影响哪些租户和接口，还要说明对旧索引（缺 chunk_index）怎么兼容。
6. 建议新增的回归测试：用假数据源覆盖特殊字符 file_id、缺 chunk_index、租户不一致这三种情况。
7. 没能确认的点，以及原因。

约束：不改索引，不重建索引，不写数据库，不提交代码；日志里不要打印切片正文和 key。