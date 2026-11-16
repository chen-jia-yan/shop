# 文件入库评测用例

上线前和每次修改后跑一遍。

## A. 触发判断

| # | 用户输入 | 期望 |
|---|---|---|
| A1 | （上传产品手册）帮我入库 | 触发 |
| A2 | （上传一份 PDF）把这个加到知识库，归到人事 | 触发，分类为人事 |
| A3 | （粘贴会议纪要）整理入库 | 不触发（meeting-notes-to-kb） |
| A4 | （上传合同）帮我检查一下 | 不触发（compliance-check） |

## B. 提取脚本（用 `examples/sample.md`）

运行：
```bash
python scripts/extract_file.py examples/sample.md --out out/ingest/
```

| # | 检查项 | 期望 |
|---|---|---|
| B1 | `suggested_title` | "差旅费报销规定（2026 版）" |
| B2 | chunks | 每个片段带章节路径，如"差旅费报销规定（2026 版） > 第二章 报销标准" |
| B3 | 表格 | 住宿标准表格完整保留在一个片段里，没有被拆开 |
| B4 | sensitive | 标出邮箱 finance@example.com 和手机号 13800000000 |
| B5 | 文件名含"草稿" | warnings 提示可能是草稿 |
| B6 | 内容不足 100 字 | warnings 提示很难被检索到 |
| B7 | .docx | 按标题样式识别章节；表格转为 Markdown 表格 |
| B8 | .pptx | 每页一节，标题为"第 N 页：<页标题>"；备注带"（备注）"前缀；无文字的页给出警告 |
| B9 | .xlsx | 每个工作表一节；超过 200 行时警告 |
| B10 | 扫描版 PDF | 警告没有文字层、需要 OCR |
| B11 | .doc 旧格式 | 提示另存为 .docx |

## C. 提交脚本（用 `examples/submission.json`）

运行：
```bash
python scripts/build_ingest.py examples/submission.json --chunks out/ingest/chunks.json --check
python scripts/build_ingest.py examples/submission.json --chunks out/ingest/chunks.json --out out/
```

| # | 检查项 | 期望 |
|---|---|---|
| C1 | 正常提交 | 无阻断问题；警告"保留了敏感信息：财务部公共邮箱" |
| C2 | 生成文件 | `差旅费报销规定（2026_版）_入库.md` 和 `.json`；json 中 `status` 为 `pending_review`，不含 `confirmed` |
| C3 | 把 `confirmed` 改为 false | 阻断："用户尚未确认"，不生成文件 |
| C4 | 删掉 `category` | 阻断 |
| C5 | 标题改成"报销规定终版v3" | 警告标题含版本字样 |
| C6 | 标签加入"制度" | 警告标签过宽 |
| C7 | 有 `duplicate_of` 但删掉 `replaces_doc_id` | 警告确认是新增还是更新 |

## D. 整体流程

| # | 场景 | 期望 |
|---|---|---|
| D1 | 知识库已有同名文档 | 建议更新已有文档，不重复新增 |
| D2 | 已有同主题文档但规定不一致 | 列出冲突点，可建议用 change-impact 分析 |
| D3 | 个人手机号 | 默认去掉，确认后才保留；部门公共邮箱可以保留 |
| D4 | 标签 | 包含用户可能用的其他叫法（如"出差报销"） |
| D5 | 分类 | 只从已有分类中选；拿不准给 2 个候选 |
| D6 | 用户确认前 | 不提交 |
| D7 | 提交后 | 告知"待审核，通过后才生效" |
| D8 | 一次上传 3 个文件 | 逐个处理、逐个确认，最后汇总 |
