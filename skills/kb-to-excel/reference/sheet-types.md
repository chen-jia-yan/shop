# 8 种工作表：JSON 格式

整体结构：

```json
{
  "meta": {
    "title": "工作簿标题", "subtitle": "副标题", "category": "经营分析",
    "kind": "dashboard",             // compare / dashboard / tracker / checklist / calculator / ledger / roster，决定默认风格
    "style": "premium",              // classic / premium / minimal，可省略
    "department": "战略规划部", "audience": "公司管理层", "as_of": "数据口径",
    "version": "V1.0", "date": "2026-10-15", "confidentiality": "内部",
    "disclaimer": "说明页底部的免责/使用提示", "tags": []
  },
  "sheets": [ { "type": "cover", "name": "说明", ... }, ... ]
}
```

- `name` 是工作表名（≤31 字符，不能含 `[ ] : * ? / \`），也是公式引用时的表名。
- 每个工作表可写 `desc`，会显示在说明页的目录里。
- 所有文字支持【待补充：XX】【请确认：XX】，渲染后单元格标为橙黄色。

---

## 公式引用写法（跨表联动）

| 写法 | 含义 | 例 |
|---|---|---|
| `{@列名}` | 当前表同一行 | `=IFERROR({@新单保费}/{@目标},0)` |
| `{表名.列名}` | 该列全部数据行 | `=SUM({机构明细.新单保费})` |
| `{表名.列名#3}` | 第 3 个数据行 | |
| `{表名.列名=华南}` | 第一列为“华南”的那一行 | `={机构明细.达成率=华南}` |
| `{表名.列名:total}` | 合计行 | `={机构明细.同比:total}` |
| `{input.key}` / `{output.key}` | 试算表的录入格 / 结果格 | `={input.amount}/1000*{output.rate}` |
| `{lookup.名称.data/col1/header}` | 试算表查找表的数据区 / 首列 / 表头 | 见试算示例 |

对比矩阵（matrix）也可以被引用：`{版本对比.尊享版=示例年交保费（元）}`。
引用在全部工作表写完后统一解析，解析失败会以退出码 3 列出具体位置。

---

## 1. cover 说明页

```json
{"type": "cover", "name": "说明", "purpose": "这个文件用来做什么",
 "how_to": ["第一步……", "第二步……"], "legend": true}
```
自动生成：品牌色带标题、文件信息（取自 meta）、**工作表目录（带跳转链接）**、单元格颜色说明（录入格/公式格/待补充）、免责提示。

## 2. table 明细表

```json
{"type": "table", "name": "机构明细", "title": "区域机构经营明细", "subtitle": "单位：亿元",
 "total": "合计",
 "columns": [
   {"name": "机构"},
   {"name": "新单保费", "format": "yi", "total": "sum"},
   {"name": "达成率", "format": "pct", "formula": "=IFERROR({@新单保费}/{@目标},0)",
    "total": "=IFERROR({@新单保费}/{@目标},0)", "rule": {"type": "lt", "value": 1, "style": "bad"}},
   {"name": "状态", "options": ["正常", "关注", "预警"]},
   {"name": "人均产能", "unit": "万元", "format": "0.0", "databar": true}
 ],
 "rows": [["华南", 4.10, null, "正常", null]],
 "highlight_col": "新单保费", "notes": ["……"], "source": "……",
 "charts": [ {图表 spec，data 默认为本表} ],
 "spare_rows": 20, "row_height": 20, "filter": true, "freeze_first_col": true}
```

| 列字段 | 说明 |
|---|---|
| `format` | text / int / money / money2 / wan / yi / pct / pct0 / ratio / date / month / delta / delta_pt，或直接写 Excel 格式如 `0.0` |
| `unit` | 显示在表头括号里 |
| `formula` | 逐行公式；该列在 rows 中填 `null` |
| `total` | `sum` / `avg` / `count`（生成 SUBTOTAL，筛选后只算可见行），或公式字符串（按合计行计算） |
| `options` | 下拉选项（数据校验）；`spare_rows` 给下方空行也加上 |
| `rule` | 条件格式，可为一个或数组：`sign`（正绿负红，`good: "down"` 反向）、`lt`/`gt`/`between`/`eq`（`value`, `style`: bad/warn/good）、`top`（前 N 名）、`scale`（色阶）、`text`（等于某文字时着色） |
| `databar` | 数据条 |
| `input` | 标为录入格（黄底） |
| `width` / `wrap` / `align` | 列宽、自动换行、对齐 |

自动处理：表头冻结、筛选、隔行底色、数字右对齐、按内容估算列宽、打印时每页重复表头。

## 3. matrix 对比矩阵

```json
{"type": "matrix", "name": "版本对比", "objects": ["基础版", "尊享版", "臻享版"],
 "highlight": "尊享版", "highlight_label": "★ 多数家庭适用", "corner": "对比项",
 "groups": [{"name": "保障责任", "rows": [{"label": "中症", "values": ["—", "50% 保额", "60% 保额"]}]}],
 "label_width": 20, "col_width": 24, "notes": [], "source": ""}
```
`✓ ✗ —` 自动着色放大；推荐列整列浅色高亮；行可加 `format` 和 `emphasis`。

## 4. notes 口径说明

```json
{"type": "notes", "name": "口径说明",
 "sections": [{"heading": "指标定义", "items": [["新单保费", "首年规模保费"], "也可以是一句话"]}]}
```

## 5. dashboard 看板

```json
{"type": "dashboard", "name": "经营看板", "title": "三季度经营看板",
 "kpis": [{"label": "新单保费", "unit": "亿元", "value": "={机构明细.新单保费:total}", "format": "yi",
           "delta": "={机构明细.同比:total}", "delta_format": "delta", "good": "up", "note": "无 delta 时显示"}],
 "insights": ["关键结论 1", "关键结论 2"],
 "rank": {"title": "达成率排名", "data": "机构明细", "by": "达成率", "key": "机构", "top": 5,
          "columns": ["机构", "新单保费", "达成率"], "formats": {"达成率": "pct"}, "ascending": false},
 "charts": [ {图表 spec}, ... ]}
```
指标卡 2-6 个，横向平分 12 列；图表自动两列排布。排名由公式动态生成，明细改了排名跟着变。

## 6. gantt 甘特跟踪

```json
{"type": "gantt", "name": "整改跟踪", "start": "2026-10-12", "end": "2027-01-24", "unit": "week",
 "statuses": ["未开始", "进行中", "已完成"],
 "tasks": [{"id": "ZG-01", "task": "……", "dept": "个险渠道部", "owner": "陈伟",
            "start": "2026-10-12", "end": "2026-10-30", "status": "已完成", "progress": 1}]}
```
固定列：编号、事项、责任部门、责任人、开始、完成、状态（下拉）、进度（0-100%，数据条）、预警（公式）。
时间轴按周（`week`，自动对齐到周一）或按天（`day`）；条件格式：计划橙、完成绿、逾期红、本周浅黄。
顶部汇总条：事项总数、已完成、进行中、已逾期、完成率，全部为公式。
可被引用的列名：编号 / 事项 / 责任部门 / 责任人 / 开始 / 完成 / 状态 / 进度 / 预警。

## 7. calculator 试算

```json
{"type": "calculator", "name": "保费试算",
 "inputs": [{"key": "age", "label": "被保险人年龄", "value": 30, "unit": "周岁",
             "validation": {"type": "whole", "min": 18, "max": 50}, "hint": "输入提示"},
            {"key": "gender", "label": "性别", "value": "男", "options": ["男", "女"]}],
 "outputs": [{"key": "premium", "label": "年交保费", "format": "money", "emphasis": true,
              "formula": "=ROUND({input.amount}/1000*{output.rate},0)", "comment": "元/年"}],
 "lookups": [{"name": "费率表", "title": "……", "columns": ["年龄起", "男10年"], "rows": [[18, 30.5]], "format": "0.0", "note": "……"}],
 "notes": ["试算结果仅供参考……"], "protect": true, "iferror": true}
```
- 录入格黄底并解锁，其余单元格锁定（工作表保护无密码，可随时撤销）。
- `iferror: true` 时结果公式自动包 `IFERROR(…,"请检查录入")`。
- 查找表按年龄段取值用 `MATCH(…,{lookup.X.col1},1)`（首列须升序）；按名称取值用 `MATCH(…,0)`。

## 8. checklist 清单

```json
{"type": "checklist", "name": "材料清单",
 "groups": [{"name": "医疗险", "items": [{"text": "医疗费用发票", "required": true, "note": "……", "who": "医院", "done": false}]}]}
```
“完成”列下拉 ☐/☑；勾选后整行变浅绿；顶部显示完成比例和“必备项还差 N 项”。

---

## 图表 spec

```json
{"type": "col", "title": "写结论", "data": "机构明细", "categories": "机构",
 "series": ["新单保费", "目标"], "secondary": ["同比"], "secondary_format": "0%",
 "rows": [1, 5], "highlight": "华南", "number_format": "0.0", "labels": true,
 "anchor": "B20", "width": 16, "height": 8}
```

| type | 适合 |
|---|---|
| `col` | 分类比较、时间序列（≤8 期） |
| `bar` | 分类名较长、排名（第一项在最上方） |
| `line` | 趋势（≥5 期） |
| `combo` | 规模 + 增速（柱 + 右轴折线，需 `secondary`） |
| `stacked` | 构成随时间或机构变化 |
| `area` | 累计趋势 |
| `pie` / `donut` | 构成占比（≤6 项） |

`highlight`：单系列柱/条形图中高亮一项、其余灰色。数据是数值时可写 `max`/`min`；数据是公式时写分类名。
