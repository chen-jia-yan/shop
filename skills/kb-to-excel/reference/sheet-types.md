# 内容 JSON 格式

一个工作簿 = 数据层（`data`）+ 视图层（`views`）+ 分析层（`dashboard` `rules`）+ 可选的专用工作表（`sheets`）。
完整示范见 `examples/complaints_tracker.json`。

```json
{
  "meta":      { ... },          // 必填
  "params":    [ ... ],          // 可调阈值，放在“参数”表
  "options":   { ... },          // 公共下拉选项（可省略，单选字段自带的 options 会自动汇总进来）
  "data":      [ ... ],          // 原始数据表（一张或多张）
  "rules":     [ ... ],          // 提醒规则
  "views":     [ ... ],          // 列表视图 / 看板视图
  "dashboard": { ... },          // 仪表盘（一个）
  "sheets":    [ ... ]           // 对比矩阵、甘特、试算、清单、口径说明、简单表
}
```

**工作表顺序**（自动）：使用说明 →（仪表盘，`dashboard_first` 时）→ 各数据表 → 字段说明 → 各视图 → 仪表盘 → sheets → 提醒规则 → 参数。
工作表名 ≤ 31 字，不能含 `[ ] : * ? / \`，不能与自动生成的表重名。

---

## meta

```json
{"title": "客户投诉处理台账",
 "purpose": "这个文件用来做什么、谁在什么时候更新",     // 显示在“使用说明”第一行
 "kind": "tracker",            // tracker / dashboard / compare / checklist / calculator / ledger / roster，决定默认色系
 "style": "blue",              // blue 蓝色系（默认）/ soft 淡色系 / orange 橙色系；命令行 --style 优先
 "source": "TAP 工单系统导出", "date": "2026-11-19", "department": "客户服务部",
 "confidentiality": "内部", "disclaimer": "使用说明里的提示语",
 "dashboard_first": false,      // true：仪表盘排在数据表前面（管理层看板类）
 "readme": true,                // false：不生成“使用说明”
 "tags": []}
```

## params 参数

```json
[{"key": "limit", "name": "处理时限（天）", "value": 15, "format": "int", "desc": "改这里，所有时限自动更新"}]
```
公式里写 `{param.limit}`。参数格是淡黄录入格，改值后全工作簿联动。

## options 公共下拉

```json
{"部门": ["理赔部", "客户服务部", "运营部"]}
```
字段写 `"options_ref": "部门"` 共用一组选项；字段直接写 `options` 也可以，会自动汇总到“参数”表（同名不同值时自动改名为“表·字段”）。

---

## data 原始数据表

```json
{"name": "数据", "title": "客户投诉处理台账", "source": "TAP 工单系统", "date": "2026-11-19",
 "key": "工单号",               // 主键：不能为空、不能重复；视图跳转、回写都靠它。省略时取第一个字段
 "expect_rows": 16,             // 检索到的记录数；与 rows 条数不符则拒绝渲染
 "desc": "原始工单，一行一件，原样保留",
 "table_name": "tblTickets",    // 可省略，默认 tbl1、tbl2…（Excel 表格对象名）
 "fields": [ ... ],
 "rows": [ ... ],
 "charts": [ {图表 spec} ]}      // 可选：放在数据表右侧
```

### fields 字段

```json
{"name": "状态", "type": "select", "required": true, "input": true,
 "options": ["待处理", "处理中", "已结案"],
 "styles": {"待处理": "grey", "处理中": "info", "已结案": "good"},
 "desc": "口径说明，显示在表头批注和字段说明里", "src": "人工登记"}
```

| 键 | 说明 |
|---|---|
| `type` | `text` `longtext` `number` `money` `percent` `date` `select` `multi` `person` `link` `formula` `ai` `bool` |
| `required` | 必填；为空时整格标黄，字段说明里的填写率 < 100% 标黄 |
| `input` | 需要人工更新的列，淡黄录入格 |
| `format` | 数字格式键：`text` `int` `money` `money2` `wan` `yi` `pct` `pct0` `ratio` `date` `month` `delta` `delta_pt`，或直接写 Excel 格式（`0.0`）。省略时按类型取默认 |
| `options` / `options_ref` | 下拉选项（`select`）；`bool` 自动用 是 / 否 |
| `styles` | 某个取值的颜色：`bad` 红 / `warn` 黄 / `info` 紫 / `good` 绿 / `grey` 灰。适用于单选和公式字段 |
| `formula` | `type: formula` 时必填，逐行公式（见下方“引用写法”）。写入表格对象的计算列，新增行自动带公式 |
| `ai` | `type: ai` 时：`{"from": "依据字段", "date": "生成日期", "check": "对照字段"}`。表头浅紫并在批注写明依据和日期，有 `check` 时两列不一致标紫 |
| `display` | `type: link` 时的显示文字，可含 `{@字段}`，如 `"工单 {@工单号}"` |
| `databar` | 数据条 |
| `freeze` | 冻结到该列（含）为止 |
| `width` | 列宽；省略时按内容估算，长文本自动换行 |
| `desc` / `src` | 口径说明 / 数据来源 |

自动追加的列（不要写进 fields）：
- **提醒标记**：有 `rules` 指向这张表时生成，命中的规则名写在格子里。
- **辅助列**：视图和仪表盘需要的匹配、序号列，放在最右侧、折叠隐藏、灰色字，不要删除。

### rows 记录

两种写法任选（可混用）：

```json
["TS2026-0912", "2026-09-03", "客服热线", ...]                 // 数组：按非公式字段的顺序（公式列不占位）
{"工单号": "TS2026-0918", "受理日期": "2026-09-10", ...}         // 对象：按字段名
```
- 数组写法里，`ai` 和 `link` 字段**要占位**（它们是值，不是公式）。值少于字段数时，后面的格子留空。
- 日期写 `YYYY-MM-DD`，自动转成日期值；空值写 `""`（写入为真正的空格子）。
- 数组多于字段数、对象出现字段之外的键 → 拒绝渲染（防止数据丢失）。

---

## rules 提醒规则

```json
{"name": "超时", "table": "数据", "when": "{@时效}=\"超时\"", "level": "bad", "fields": ["时效"],
 "how": "可选，规则表里“怎么处理”一栏的说明"}
```
- `when`：条件表达式（不带 `=`），写法同字段公式。
- `level`：`bad` 红 / `warn` 黄 / `info` 紫；`fields`：命中时着色的字段。
- `table` 省略时为第一张数据表。
- 规则名不能互相包含（“超时”和“超时结案”会混淆计数），校验会拦下。
- “提醒规则”表列出每条规则的条件、着色字段、当前命中数；“启用”列改成“否”即停用该规则。

## views 视图

### 列表视图

```json
{"type": "list", "name": "视图·待办", "from": "数据", "desc": "未结案工单，按处理时限排序",
 "columns": ["工单号", "受理日期", "状态", "处理时限", "时效", "提醒标记"],
 "where": "{@状态}<>\"已结案\"",
 "sort": "处理时限",                       // 或 {"by": "处理天数", "desc": true}；省略则按原顺序
 "rows": 100}                              // 预留行数，默认见 rules.json → excel.view_rows
```
- 每一格都是 INDEX/MATCH 公式，数据表改了视图自动更新；新旧版本 Excel 均可用。
- 主键可点击跳回数据表原始行；列沿用数据表的格式和颜色。
- 视图顶部写明来源、条件、排序和当前条数。

### 看板视图

```json
{"type": "board", "name": "视图·看板", "from": "数据", "group": "状态",
 "groups": ["待处理", "处理中", "已结案"],   // 省略时取分组字段的 options
 "card": ["客户", "投诉类别", "承办人"],      // 卡片上显示的字段（主键自动在首行）
 "where": "...", "rows": 40, "desc": "按状态分列"}
```
列头显示“状态（件数）”；卡片按提醒规则着色。

---

## dashboard 仪表盘

```json
{"name": "仪表盘", "from": "数据", "title": "投诉处理驾驶舱", "desc": "进度、趋势与异常",
 "kpis": [...], "insights": [...], "trend": {...}, "heatmap": {...},
 "group": {...}, "breakdown": {...}, "anomalies": {...}, "charts": [...]}
```
每个部分都可省略。版面（12 列网格）：指标卡 → 洞察 + 趋势 → 热力 + 分组 → 异常 + 分布 → 图表两两一行。
图表的数据放在右侧计算区（灰色小字），都是公式，不要手改。

| 部分 | 格式 | 说明 |
|---|---|---|
| `kpis` | `{"label", "value": "=公式", "unit", "format", "note": "=公式", "tone": "up/down", "alert": true, "ring": "=0~1 的公式"}` | 2–8 个。`unit` 写进数字格式（值仍可计算）；`tone` 是 note 的颜色（up/bad 红，down/good 绿）；`alert` 数字标红；`ring` 加一个进度圆环 |
| `insights` | `[{"text": "=公式拼句子", "level": "bad/warn"}]` | 每句由公式拼成，数据变了句子跟着变；最多见 `excel.insight_max` |
| `trend` | `{"title", "note", "periods": "auto", "date": "日期字段", "bars": [{"name", "date", "where"}], "line": {"name", "avg", "date", "where"}}` | 按月 COUNTIFS 计数（柱）+ 平均值（右轴折线）；`auto` 从数据的最早月到最晚月 |
| `heatmap` | `{"title", "rows": "字段", "cols": "字段", "row_values", "col_values"}` | 两个字段交叉计数，色阶着色 |
| `group` | `{"title", "by": "字段", "values": [...], "measures": [{"name", "agg": "count/sum/avg", "field", "where", "format", "databar", "alert"}]}` | 分组汇总表；`alert` 大于 0 标红 |
| `breakdown` | `{"title", "by": "字段", "values": [...], "where"}` | 计数 + 条形图 |
| `anomalies` | `{"title", "note", "columns": [...], "where", "sort", "rows"}` | 内嵌列表视图；`where` 省略时 = 提醒标记不为空 |
| `charts` | `[图表 spec]` | 引用数据表的原生图表，见文末 |

`where` 在 group / trend / breakdown 里是条件数组：`[["状态", "<>已结案"], ["渠道", "监管转办"]]`（COUNTIFS 条件写法）。
`values` 省略时：取字段的 options；没有 options 则按数据中出现的顺序。

---

## 引用写法

| 写法 | 含义 | 渲染结果 |
|---|---|---|
| `{@字段}` | 本行该字段 | `tbl1[[#This Row],[字段]]`（条件格式里为 `$C3`） |
| `{表.字段}` | 数据表的整列 | `tbl1[字段]`，表格新增行自动包含 |
| `{param.键}` | 参数 | `'参数'!$B$3` |
| `{options.名称}` | 一组下拉选项 | `'参数'!$A$12:$A$15` |
| `{表.列#3}` `{表.列=华南}` `{表.列:total}` | 专用工作表（sheets）的单格引用 | 见下方 |
| `{input.key}` `{output.key}` `{lookup.名称.data/col1/header}` | 试算表 | 见下方 |

- 跨表统计用 COUNTIFS / SUMIFS / AVERAGEIFS / INDEX+MATCH；**不用** FILTER、SORT、UNIQUE、XLOOKUP、LET（旧版 Excel 不支持）。
- 公式中的中文字符串要转义引号：`"=IF({@状态}=\"已结案\",1,0)"`。
- 引用在全部工作表写完后统一解析，解析失败以退出码 3 列出位置。

---

## sheets 专用工作表

原有的专用表保留，适合“不是一行一条记录”的内容。可以与 data 并用（例如对比矩阵 + 试算）。
`cover`（封面）和旧版 `dashboard` 已停用：使用说明自动生成，仪表盘用上面的 `dashboard`。

### table 简单表

只在内容很少、不需要视图和提醒时使用；**多于十几行的记录请用 data**。

```json
{"type": "table", "name": "费率表", "title": "……", "subtitle": "单位：元",
 "columns": [{"name": "年龄", "format": "int"}, {"name": "费率", "format": "0.00", "total": "avg",
              "rule": {"type": "lt", "value": 1, "style": "bad"}}],
 "rows": [[18, 30.5]], "total": "合计", "notes": [], "source": "", "charts": []}
```
列字段：`format` `unit` `formula` `total`（sum/avg/count 或公式）`options` `rule`（sign / lt / gt / between / eq / top / scale / text）`databar` `input` `width` `wrap` `align`。

### matrix 对比矩阵

```json
{"type": "matrix", "name": "版本对比", "objects": ["基础版", "尊享版", "臻享版"],
 "highlight": "尊享版", "highlight_label": "★ 多数家庭适用", "corner": "对比项",
 "groups": [{"name": "保障责任", "rows": [{"label": "重疾保额", "values": ["—", "50 万", "100 万"]}]}],
 "notes": [], "source": ""}
```
`✓ ✗ —` 自动着色；可被引用：`{版本对比.尊享版=示例年交保费（元）}`。

### notes 口径说明

```json
{"type": "notes", "name": "口径说明",
 "sections": [{"heading": "指标定义", "items": [["新单保费", "首年规模保费"], "也可以是一句话"]}]}
```

### gantt 甘特跟踪

```json
{"type": "gantt", "name": "整改跟踪", "start": "2026-10-12", "end": "2027-01-24", "unit": "week",
 "statuses": ["未开始", "进行中", "已完成"],
 "tasks": [{"id": "ZG-01", "task": "……", "dept": "个险渠道部", "owner": "陈**",
            "start": "2026-10-12", "end": "2026-10-30", "status": "已完成", "progress": 1}]}
```
需要视图 / 提醒 / 仪表盘时，任务本身放 data，甘特只作为时间轴补充。

### calculator 试算

```json
{"type": "calculator", "name": "保费试算",
 "inputs": [{"key": "age", "label": "被保险人年龄", "value": 30, "unit": "周岁",
             "validation": {"type": "whole", "min": 18, "max": 50}, "hint": "输入提示"}],
 "outputs": [{"key": "premium", "label": "年交保费", "format": "money", "emphasis": true,
              "formula": "=ROUND({input.amount}/1000*{output.rate},0)"}],
 "lookups": [{"name": "费率表", "columns": ["年龄起", "男10年"], "rows": [[18, 30.5]]}],
 "notes": ["试算结果仅供参考……"], "protect": true, "iferror": true}
```
录入格解锁、其余锁定（无密码）；查找表按年龄段用 `MATCH(…,{lookup.X.col1},1)`（首列升序）。

### checklist 清单

```json
{"type": "checklist", "name": "材料清单",
 "groups": [{"name": "医疗险", "items": [{"text": "医疗费用发票", "required": true, "note": "……", "who": "医院", "done": false}]}]}
```

---

## 图表 spec

```json
{"type": "col", "title": "写结论，不写“XX 图”", "data": "<数据表或简单表名>", "categories": "<分类字段>",
 "series": ["<数值字段>"], "secondary": ["<右轴字段>"], "secondary_format": "0%",
 "highlight": "<分类名>", "number_format": "0.0", "labels": true, "width": 16, "height": 8}
```

| type | 适合 |
|---|---|
| `col` | 分类比较、≤8 期的时间序列 |
| `bar` | 分类名较长、排名 |
| `line` | ≥5 期趋势 |
| `combo` | 规模 + 增速（柱 + 右轴折线，需 `secondary`） |
| `stacked` | 构成随时间或机构变化 |
| `area` | 累计趋势 |
| `pie` / `donut` | 构成占比（≤6 项） |

图表直接引用数据表的单元格，改数据图表跟着变。`highlight`：单系列中高亮一项，其余灰色。
