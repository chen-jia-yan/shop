# 25 种文档元素：格式与用法

内容 JSON 的整体结构：

```json
{
  "meta": {
    "title": "富卫安康重大疾病保险产品说明书",
    "short_title": "安康重疾产品说明书",
    "subtitle": "客户版",
    "category": "产品资料",
    "doc_type": "product",
    "style": "classic",
    "brand": "富卫人寿",
    "department": "产品部",
    "audience": "客户及销售人员",
    "version": "V1.0",
    "doc_no": "FWD-PD-2026-018",
    "date": "2026年11月",
    "confidentiality": "公开",
    "toc": true,
    "numbering": true,
    "cover_note": "本资料仅供参考，具体以保险合同条款为准",
    "end_note": "本说明书仅为产品介绍，不构成保险合同的组成部分……",
    "tags": ["重疾险", "产品说明书"]
  },
  "blocks": [ { "type": "heading", "level": 1, "text": "产品概览" }, ... ]
}
```

| meta 字段 | 必填 | 说明 |
|---|---|---|
| `title` | ✓ | 封面标题 |
| `short_title` | | 页眉显示的短标题，默认同 title |
| `doc_type` | 建议 | product / proposal / claims / underwriting / training / policy / analysis / project / notice / compliance；决定默认风格和质检规则 |
| `style` | | classic / premium / minimal；不填则按 doc_type 推荐 |
| `confidentiality` | | 公开 / 内部 / 机密；显示在封面和页眉右侧 |
| `toc` | | 是否生成目录；不填时一级标题 ≥4 个自动生成 |
| `numbering` | | 标题自动编号（一、/1.1/1.1.1），默认 true |

**文字中的通用标记**（所有文字字段都支持）：
- `**加粗**`
- `【待补充：XX】`、`【请确认：XX】`：渲染为黄底高亮，质检脚本会统计数量

---

## 一、文字类（9 种）

### 1. heading 标题
```json
{"type": "heading", "level": 1, "text": "保障责任", "new_page": false}
```
level 1-3。一级标题带下划线，可用 `new_page` 强制分页。**标题写内容不写话题。**

### 2. paragraph 正文
```json
{"type": "paragraph", "text": "本产品……", "align": "justify", "indent": false}
```
一段 80-200 字为宜，超过 320 字质检会提示拆分。

### 3. lead 导语
```json
{"type": "lead", "text": "三季度新单保费同比增长 14%，增速连续三个季度提升。"}
```
章节开头的 1-2 句结论，较大字号加左侧色条。每个一级章节建议都以导语或核心要点开头。

### 4. bullets 要点列表
```json
{"type": "bullets", "items": ["要点一", {"text": "要点二", "sub": ["子项 a", "子项 b"]}]}
```
3-6 条为宜；支持一层子项。

### 5. numbered 编号列表
```json
{"type": "numbered", "items": ["先……", "再……"]}
```
有先后顺序但不需要流程图时使用。

### 6. callout 提示框
```json
{"type": "callout", "kind": "risk", "title": "风险提示", "text": "……", "items": ["……"]}
```
| kind | 用途 |
|---|---|
| `key` 核心要点 | 一章最重要的结论 |
| `summary` 摘要 | 文档或长章节的摘要 |
| `info` 说明 | 口径、背景补充 |
| `tip` 提示 | 实用建议、窍门 |
| `warning` 注意 | 容易出错的地方 |
| `risk` 风险提示 | 监管要求的风险提示、免责、等待期等 |

一页内不超过 2 个提示框，否则重点就不突出了。

### 7. quote 引文
```json
{"type": "quote", "text": "客户第一，诚信为本。", "source": "公司服务理念"}
```

### 8. note 注释
```json
{"type": "note", "text": "以上数据为未经审计的管理口径。", "label": "注"}
```

### 9. page_break 分页
```json
{"type": "page_break"}
```

---

## 二、表格与清单类（7 种）

### 10. table 品牌表格
```json
{
  "type": "table",
  "caption": "保障责任一览",
  "columns": ["保障责任", "给付条件", "给付金额"],
  "rows": [["重大疾病", "确诊约定重疾", "基本保额 × 100%"], ["合计", "", "—"]],
  "widths": [3.5, 6.4, 6.5],
  "highlight_col": 2,
  "total_row": false,
  "first_col_bold": true,
  "note": "中症、轻症不占用重疾保额。",
  "source": "《富卫安康重大疾病保险条款》第 2.4 条"
}
```
- 表头随风格变色，跨页时自动重复表头，行不跨页断开。
- 数字列自动右对齐；`highlight_col` 高亮一列（如推荐方案）；`total_row` 把最后一行设为合计行。
- `widths` 单位 cm，总宽 16.4；不填则按内容自动分配。
- 列数建议 ≤6；更多维度改用 Excel。

### 11. glossary 术语表
```json
{"type": "glossary", "items": [{"term": "等待期", "definition": "合同生效后的一段时间……"}]}
```

### 12. faq 常见问题
```json
{"type": "faq", "items": [{"q": "等待期内确诊怎么办？", "a": "……"}]}
```
问题用读者的原话来写。

### 13. checklist 清单
```json
{"type": "checklist", "items": [{"text": "理赔申请书", "required": true, "note": "需被保险人签字"}]}
```
`required: false` 显示为“如适用”。

### 14. signoff 签批栏
```json
{"type": "signoff", "roles": ["编制", "审核", "批准"]}
```

### 15. revisions 版本记录
```json
{"type": "revisions", "items": [{"version": "V1.0", "date": "2026-11-01", "author": "产品部", "change": "首次发布"}]}
```

### 16. contact 联系卡片
```json
{"type": "contact", "items": [{"label": "客服热线", "value": "【待补充】", "desc": "工作日 9:00-18:00"}]}
```
**联系方式必须来自知识库，查不到写【待补充】，绝不编造电话号码。**

---

## 三、图示与数据类（9 种）

### 17. kpi 数据卡片
```json
{"type": "kpi", "items": [
  {"value": "15.0", "unit": "亿元", "label": "新单保费", "delta": "▲ 14%", "delta_label": "同比"},
  {"value": "68.2%", "label": "综合赔付率", "delta": "▼ 1.5pct", "good": "down"}
], "source": "……"}
```
2-4 个。`delta` 以 ▲/+ 或 ▼/- 开头时自动判断颜色；`good: "down"` 表示下降是好事（赔付率、费用率、投诉率）。

### 18. flow 流程图
```json
{"type": "flow", "steps": [{"title": "报案", "desc": "出险后 10 日内"}, ...],
 "highlight": [3], "per_row": 4, "caption": "理赔办理流程"}
```
3-8 步；超过 `per_row` 自动换行；`highlight` 为强调步骤序号（从 1 起）。

### 19. timeline 时间线
```json
{"type": "timeline", "nodes": [{"time": "第 0 天", "title": "提交申请", "desc": "……"}], "current": 2, "caption": "……"}
```
`current` 为当前节点下标（从 0 起）：之前为已完成，之后为未来（浅色）。不填则全部为已完成。适合项目里程碑、理赔时效。

### 20. structure 产品责任结构图
```json
{"type": "structure", "root": "富卫安康重疾险",
 "children": [{"name": "重大疾病", "note": "100% 保额", "items": ["120 种重疾", "给付 1 次"]}],
 "caption": "保障责任构成"}
```
2-5 个分支，每个分支 ≤5 个子项。

### 21. matrix 四象限矩阵
```json
{"type": "matrix", "x_label": "发生可能性", "y_label": "影响程度",
 "quadrants": [
   {"title": "重点关注", "items": ["……"], "action": "……"},
   {"title": "优先处置", "items": ["……"], "action": "……"},
   {"title": "常规监控", "items": ["……"]},
   {"title": "持续跟踪", "items": ["……"]}
 ], "caption": "风险评估矩阵"}
```
顺序：左上（高影响低可能）、右上（高影响高可能）、左下（低影响低可能）、右下（低影响高可能）。右上为红色。

### 22. compare 对比卡片
```json
{"type": "compare", "cards": [
  {"title": "基础版", "subtitle": "适合预算有限的年轻客户", "points": ["……"]},
  {"title": "尊享版", "tag": "推荐", "highlight": true, "points": ["……"]}
]}
```
2-4 张。对外文档中“推荐”需有依据（如“适合有家庭责任的客户”），不能是绝对化推荐。

### 23. steps 纵向步骤
```json
{"type": "steps", "items": [{"title": "准备材料", "owner": "客户", "time": "1 天", "desc": "……"}]}
```
步骤说明较长、需要写负责人和时限时用它，比 flow 能容纳更多文字。

### 24. chart 数据图表
```json
{"type": "chart", "chart": "combo", "caption": "新单保费与同比增速",
 "categories": ["Q1", "Q2", "Q3"],
 "series": [{"name": "新单保费（亿元）", "values": [12.1, 13.4, 15.0]}],
 "secondary": {"name": "同比增速", "values": [6, 10, 14], "unit": "%"},
 "unit": "亿元", "highlight": "Q3", "target": {"value": 14, "label": "目标"},
 "source": "……"}
```
| chart | 适合 |
|---|---|
| `bar` | 少量分类比较、时间序列（≤8 期） |
| `barh` | 分类名较长、排名 |
| `highlight` | 排名中突出一项（自动高亮最大值或 `highlight` 指定项） |
| `line` | 趋势（≥5 期） |
| `combo` | 规模 + 增速（柱 + 线，双轴） |
| `stacked` | 构成随时间变化 |
| `donut` | 构成占比（≤6 项），可用 `center_text`/`center_label` 在中心显示总数 |
| `pie` | 同上，项数更少时 |

**一图一结论**：caption 写结论（“Q3 新单保费创年内新高”），而不是“新单保费情况”。

### 25. image 图片
```json
{"type": "image", "path": "assets/flow.png", "width_cm": 12, "caption": "……"}
```
路径相对于内容 JSON 所在目录。找不到图片时会插入【待补充】提示，不会报错中断。
