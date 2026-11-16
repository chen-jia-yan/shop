# 提交方式配置

与 **meeting-notes-to-kb** 共用同一套提交方式和接口。下面的配置值应与 `meeting-notes-to-kb/reference/submission.md` 保持一致；核实清单和接口说明见那个文件。

```
SUBMIT_MODE = file
```

## 文件入库的额外字段

调用 TAP 写入接口时，除了标题、正文、分类、标签，文件入库还需要：

| 字段 | 来源 |
|---|---|
| `summary` | 生成的摘要 |
| `chunks` | `chunks.json` 中的片段（如果接口支持分段入库） |
| `effective_date` / `expire_date` | 文件里写了才填 |
| `owner` | 默认上传人 |
| `original_file` | 原文件（如果接口支持附件） |
| `replaces_doc_id` | 是"更新已有文档"时，填被更新的文档 ID |
| `status` | 必须是 `pending_review`（待审核），不能直接发布 |

> ⚠️ 待核实：TAP 写入接口是否支持分段入库、附件、"更新已有文档"。不支持的字段可以省略；不支持"更新"时，在提交说明里写明"用于替换文档 XX"，由审核人处理。

## file 模式

生成以下文件交给用户：
- `<标题>_入库.md`：入库信息（标题、摘要、分类、标签）+ 正文
- `<标题>_入库.json`：结构化数据（含片段）

用户到 TAP 的 <提交入口名称，待补充> 上传，分类选择 json 中的 `category`。
