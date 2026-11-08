按下面的决定更新 C:\Users\234393\Desktop\miya\前端对接\KB前端对接文档.md。只改这个文档，不修改仓库中的任何文件。

1. 字段长度：从 src/tap_ai/persistence/models.py 中 Library* 类每一列的 String(n) / OptionalString(n) 读出长度，填进各接口字段表的"取值范围"
2. summary：读 src/tap_ai/core/library_eval/summary.py 和 application/library_eval.py，列出 summary 对象中的每一个键：名称、类型、含义、示例值，嵌套的也要展开
3. token_usage：读 application/library_eval.py 和 core/library_eval/ 中写入 token_usage 的代码，列出子字段
4. category：改为 7 个值加 null（出错的题目为 null），附 SUGGESTIONS 原文。删除"剩余 1 个待确认"
5. status、category 筛选：注明前端用下拉框，选项为第五节的枚举值；后端不校验，传入不存在的值返回空列表
6. 已发布草稿可以删除：注明删除的只是草稿记录，已落库的切片不受影响，前端删除前需要弹窗确认
7. 评估集导入：前端读取 Excel / JSONL 后转成 JSON，调用 gold-sets/import 接口，后端不提供文件上传。
   补一节"导入模板"：表格的每一列对应 import 请求中题目对象的哪个字段，哪些必填，并给一个 3 道题的 JSON 示例
8. operator：前端不用传，后端取请求中的 user_id
9. 租户字段：注明"与会话、聊天接口的传法相同"
10. doc_type、locators、metadata：写目前的理解（文件类型、页码或 sheet 列表、预留字段），标"第二期接入后确定"
11. analysis 接口的返回中增加 llm_analysis（对象或 null，开关关闭或没有 badcase 时为 null），注明"后端补充中"
12. "待确认问题清单"只保留 3 条：租户字段的传法、开发环境建表和开关、Excel 转 JSON 的分工

完成后在回复中贴出：summary 的字段表、token_usage 的字段表、导入模板这一节的全文




D中第2步的最后 可以新增：
8. 唯一允许的逻辑修改：api/dto.py 中评估分析的返回模型追加 llm_analysis 字段（类型 dict | None，默认 None）；
   get_analysis 返回时，把 run.summary 中的 llm_analysis 原样带上。补一个测试：summary 中有 llm_analysis 时，接口能返回它