【任务：修 _score_toehold 用 expected_file 匹配 + 加除零 guard（plan mode 看 diff 再落地，不碰数据/不动检索/不动阈值）】

背景：Toehold 现在恒为假/数字不可信，因为代码用 `expected in source_file` 子串匹配，而 gold set 的 expected_source 是 "#18_QlikSense.pptx (slide-3: …)" 这种长串，永远不是文件名的子串。gold set 里已经有纯文件名字段 expected_file。

红线：只改 eval 评分里 toehold 这一处逻辑；不动检索、不动门禁/阈值、不改 gold set 数据、不写删索引、不跑 ingest。改动先 plan mode 给我看 diff。

要求：
1. 文件级 toehold：改成拿 gold 的 expected_file（纯文件名）去匹配检索命中 chunk 的 source_file（casefold 后相等或互为子串皆可）。
2. 段级（可选保留）：expected_source 里若带 slide/sheet 信息，作为 section 级附加判断，不要用它做文件级匹配。
3. 除零 guard：expected_file 为空时，该题 toehold 记为 N/A 跳过、不计入分母，别崩。
4. 不改其它维度逻辑。

验证：改完重跑一次检索诊断，报每题 toehold 命中(hit/miss) + 总召回率，确认不再是恒 1/恒满、而是反映真实命中。

给我 diff + 验证结果。只修这一处。