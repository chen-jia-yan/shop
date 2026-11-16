# 公司 Word 模板

把公司的 Word 模板（.docx）放在这个目录。

## 模板要求

- 格式必须是 `.docx`。如果是 `.dotx`，在 Word 里打开后"另存为 .docx"。
- 模板里要定义好这些样式，脚本会直接使用：
  - `Title`（标题）、`Subtitle`（副标题）
  - `Heading 1` / `Heading 2` / `Heading 3`（标题 1-3）
  - `List Bullet`（项目符号列表）、`List Number`（编号列表）
  - `Table Grid`（网格表格）
  - 样式缺失时，脚本会退回到 `Normal` 样式，不会报错，但效果会变差。
- 页眉、页脚、Logo、页边距会被保留。
- 模板里原有的正文默认会被清空；如果要保留（比如固定的封面页），生成时加 `--keep-template-body`，内容会追加在后面。

## 命名建议

| 文件名 | 用途 |
|---|---|
| `default.docx` | 默认模板 |
| `client.docx` | 对外（给客户）的文档 |
| `internal.docx` | 内部文档 |

在 SKILL.md 第 1 步里，根据"读者"选择对应的模板。
