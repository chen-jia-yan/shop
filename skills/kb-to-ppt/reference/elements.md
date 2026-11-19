# 页面与图示：JSON 格式与选用

## 整体结构

```json
{
  "meta": {
    "title": "2026 年第三季度个险渠道经营汇报", "short_title": "Q3 个险经营汇报",
    "subtitle": "副标题", "category": "经营分析",
    "deck_type": "analysis",        // work_report / proposal / training / product / project / analysis / customer / kickoff /
                                    // health / claims / service / policy / annual / impact，决定默认主题
    "theme": "blue",                // orange / warm / soft / minimal / premium / blue / teal；不填按 deck_type
    "presenter": "战略规划部", "department": "", "date": "2026 年 10 月", "confidentiality": "内部",
    "agenda": true,                 // 2 个以上章节时自动插入目录页（显示每章页数和讲述时长）
    "exec_summary": {"title": "一句总结论"},   // 或 true：在目录后自动插入执行摘要
    "duration_min": 20,             // 会议时长；预计讲述超时时构建报告会提示
    "external": false,              // 对外材料：自动插入“重要提示”页；不写时按 deck_type 判断
    "product_kind": "protection",   // 重要提示条目：protection / annuity / universal / participating / default
    "sample": false,                // 含示例数据：案例、保障责任、雷达页自动加“示例样本”标记
    "animate": true, "transition": null,   // 关闭动画 / 统一指定切换效果
    "footer": null                  // 自定义页脚文字
  },
  "slides": [ ... ]
}
```

所有文字支持 `**强调**`（标题里显示为强调色）、【待补充：XX】、【请确认：XX】。
每页可写 `notes`（演讲备注）、`transition`、`animate: false`、`key: true`（关键页，进执行摘要和精简版）、
`alert: true`（问题页，执行摘要中标红）、`source`（左下角数据来源）、`sample`（示例样本标记）。

---

## 10 种页面

| type | 用途 | 主要字段 |
|---|---|---|
| `cover` | 封面 | `icon`（封面装饰图标），其余取自 meta |
| `agenda` | 目录 | 自动生成：每章一张卡片，显示页数和讲述时长；一般不用手写 |
| `exec_summary` | 执行摘要 | 自动生成：取 `key: true` 的页（不足 3 页时补每章第一页）的标题和副标题，带页码；右侧“需要决策”取自 summary 的 `decisions`。也可手写 `items: [{title, sub, page, alert}]` |
| `section` | 章节页 | `title`、`subtitle`、`short`（眉标用短名）；右侧章节导航高亮当前章，左下显示本章页数和时长 |
| `content` | 内容页 | `title`（结论）、`kicker`（副标题）、`layout`、`data` 或 `data_from`、`insight`、`takeaway` |
| `statement` | 观点/金句页 | `text`、`sub` |
| `big_number` | 大数字页 | `title`、`value`、`unit`、`label`、`points`（右侧 2-3 条说明） |
| `summary` | 总结与行动 | `title`、`actions: [{action, desc, owner, due, status}]`（前 3 项为卡片，第一项强调，其余列成明细）、`decisions: ["……"]` |
| `disclaimer` | 重要提示 | 对外材料自动插入在结束页前；条目来自 `tap-config/compliance.json` 的 `risk_notice`，也可手写 `items` |
| `end` | 结束页 | `text`（默认“谢谢”）、`sub`、`contacts: [{label, value}]` |

内容页通用字段：
- `insight: {"title": "关键发现", "items": ["……"]}` → 右侧解读栏（适合图表页）
- `takeaway: "……"` → 底部结论条
- `eyebrow` → 覆盖左上角章节眉标

---

## 什么内容用什么版式

| 想表达 | 版式 | 数据量 |
|---|---|---|
| 几个关键数字 | `kpis`（可加迷你趋势 / 进度环 / 基准条） | 2-4 个 |
| 一个特别重要的数字 | 页面 `big_number` | 1 个 |
| 完成率、达成率等比例 | `gauge`（单个）/ `bars`（多个对比） | 1 / 3-8 |
| 趋势、对比、构成 | `chart`（可加目标线、异常项、标注框） | 分类 ≤8 |
| 从目标到实际、差异来自哪里 | `waterfall` 瀑布图 | 3-9 项 |
| 各区域 / 机构分布 | `tilemap` 方块地图 + 排名 | ≤12 个区域 |
| 明细数据 | `table` | ≤7 行 6 列 |
| 一张保单保什么 | `coverage` 保障责任一览 | 3-6 项 |
| 客户案例、方案推演 | `case` 画像 → 缺口 → 方案 → 结果 | 2-4 步 |
| 客户经历的环节、痛点 | `journey` 服务旅程 | 3-6 步 |
| 多方案、多版本的综合对比 | `radar` 雷达 + 对比表 | 3-8 个维度 |
| 多条线的计划、里程碑 | `roadmap` 泳道路线图 | ≤6 条线 |
| 客户高频问题、规范话术 | `qa` 问答话术 | 每页 3 组（多了自动拆页） |
| 先后步骤 | `process`（≤6 步）/ `timeline`（带时间） | 3-6 / 3-7 |
| 循环往复的过程 | `cycle` | 3-6 |
| 逐级转化、筛选 | `funnel` | 3-6 层 |
| 层次、优先级 | `pyramid` | 3-5 层 |
| 系统/服务分层 | `layers` | 2-5 层 |
| 组织、分类、拆解 | `hierarchy` | 2-5 个分支 |
| 围绕一个核心的协同 | `hub` | 4-6 个 |
| 逐级升级、发展路径 | `stairs` | 3-5 级 |
| 风险或优先级评估 | `matrix` | 4 象限 |
| 现状与方案对比 | `compare` | 两侧各 3-5 条 |
| 几类事物的共同点 | `venn` | 2-3 个 |
| 并列的亮点、能力、举措 | `icon_grid` | 3-8 个 |
| 有标题有说明的要点 | `bullets` | 2-8 条（>8 自动拆页） |
| 2-3 组并列清单 | `columns` | 2-3 列 |

`layout` 写 `auto` 或不写时自动选择，规则见 `scripts/smart.py` 的 `AUTO_RULES`。

---

## 26 种图示 + 2 种文字版式的 data 格式

### 原有 18 种（kpis、chart 有新增字段）

```jsonc
// process 箭头流程：highlight 为强调的步骤序号（从 1 起，可多个）
{"steps": [{"title": "名单筛选", "desc": "……", "icon": "search"}], "highlight": [2]}

// timeline 时间线：current 为当前节点下标（从 0 起），之前实色、之后浅色
{"nodes": [{"time": "11 月 1 日", "title": "专项启动", "desc": "……"}], "current": 1}

// cycle 循环：cycle 为 true，3-6 项
{"center": "客户", "cycle": true, "items": [{"title": "需求沟通", "desc": "……"}]}

// funnel 漏斗：每层都要有 value
{"levels": [{"label": "需求面谈", "value": "1,000 人", "desc": "……"}]}

// pyramid 金字塔：从塔尖到塔基
{"levels": [{"label": "财富传承", "title": "终身寿险", "desc": "……"}]}

// layers 分层架构：自上而下，每层 items 显示为标签
{"levels": [{"label": "前台展业", "items": ["产品资料", "保费试算"], "highlight": true}]}

// matrix 四象限：顺序为左上、右上、左下、右下；highlight 为下标
{"x_label": "发生可能性", "y_label": "影响程度", "highlight": 1,
 "quadrants": [{"title": "优先处置", "items": ["……"], "action": "……"}]}

// hub 中心辐射
{"center": "<核心目标>", "items": [{"title": "<协同方>", "desc": "……", "icon": "chat"}]}

// hierarchy 层级
{"root": "服务体系", "children": [{"name": "前台", "items": ["……"]}]}

// stairs 阶梯（最后一级高亮）
{"items": [{"title": "基础版", "desc": "……"}]}

// kpis 数据卡片：highlight 的卡片用主色底；alert 的卡片顶条和图标为红色；delta 以 ▲/▼ 开头自动着色，good: "down" 表示下降为好
//   每张卡可再加一种辅助图（卡片自动加高）：trend 迷你趋势线 / progress 进度环（0-1，可配 progress_label）/
//   bench 基准条 {value 当前值 0-1, mark 预警线 0-1, label 说明}
{"items": [{"label": "<指标名>", "value": "<数值>", "unit": "<单位>", "delta": "▲ <变化>", "delta_label": "同比",
            "icon": "coin", "highlight": true, "trend": [13.26, 11.8, 12.1, 13.4, 15.0]},
           {"label": "13 个月继续率", "value": "86.4%", "alert": true, "bench": {"value": 0.864, "mark": 0.85, "label": "预警线 85%"}}]}

// bars 进度条：value 与 max 同一量纲；target 画红色目标线
{"items": [{"label": "<分类>", "value": <数值>, "display": "<显示文字>", "target": <目标值>, "highlight": true}], "max": <刻度上限>}

// gauge 环形仪表：value 为 0-1
{"value": <0-1 的比例>, "display": "<显示文字>", "label": "<指标名>", "sub": "<目标说明>", "target": <0-1>}

// icon_grid 图标卡片：tag 显示右上角标签；style: "plain" 去掉卡片底
{"items": [{"title": "保额不减少", "desc": "……", "icon": "shield", "tag": "尊享版起", "highlight": false}]}

// compare 对比：左侧为现状/传统（灰），右侧为方案/改进（主色）
{"left": {"title": "传统做法", "items": ["……"]}, "right": {"title": "新方案", "items": ["……"]}, "vs": "VS"}

// venn 交集：2-3 个
{"items": [{"title": "医疗险", "desc": "报销费用"}], "center": "家庭保障"}

// table 表格：widths 为相对宽度；highlight_col 高亮一列
{"columns": ["区域", "新单保费"], "rows": [["华南", "4.10"]], "widths": [1, 1.5], "highlight_col": 1, "source": "……"}

// chart 原生图表（PowerPoint 内可直接编辑数据）
{"chart": "col", "categories": ["Q1", "Q2"], "series": [{"name": "新单保费", "values": [12.1, 13.4]}],
 "highlight": "Q2", "number_format": "0.0", "labels": true}
//   chart：col 柱 / bar 条（分类名长时）/ stacked 堆叠 / line 折线 / area 面积 / pie 饼 / donut 环形
//   智能标注（col / bar / line，单系列）：
//     target: 1.0         画红色虚线目标线并标注“目标 100.0%”
//     alert: "auto"       自动找出问题项（有目标时取低于目标的最低项；good: "down" 时取高于目标的最高项）换成警示色；也可写分类名
//     callout: "auto"     在问题项旁生成标注框，如“华东 89.7%，差 10.3pct”；也可直接写文字
//     axis_min / axis_max 固定纵轴范围（默认 0 到最大值的 1.18 倍）
//   标出问题项而标题、副标题没提到它时，构建报告会提示点明

// bullets 要点（自动配图标，>4 条分两列，>8 条自动拆页）
{"points": [{"title": "不承诺收益", "desc": "……", "icon": "lock"}]}

// columns 分栏
{"columns": [{"title": "年轻单身", "items": ["……"], "highlight": false}]}
```

### 新增 8 种

```jsonc
// waterfall 瀑布图：start 起点（如目标）→ items 逐项增减 → end 终点（不写 value 时自动累加）
//   增加为浅主色、减少为红色，贡献最大的一项数字用主色；纵轴不从 0 开始时左下角自动注明
{"start": {"label": "季度目标", "value": 14.0},
 "items": [{"label": "华南", "value": 0.5}, {"label": "华东", "value": -0.3}],
 "end": {"label": "实际完成"}, "number_format": "0.0", "axis_min": null}

// tilemap 区域方块地图：区域位置默认取 rules.ppt.tilemap_regions（华北 / 华东 / 华中 / 华南 / 西南 / 西北 / 东北）
//   其他划分（省、分公司）在每项写 pos: [行, 列, 跨行, 跨列]，grid: [行数, 列数]
//   颜色深浅表示数值，负值红色；rank: false 去掉右侧排名
{"items": [{"label": "华南", "value": 0.281}, {"label": "华东", "value": -0.041}], "number_format": "+0.0%", "rank": true}

// coverage 保障责任一览：key 为核心责任（主色卡片），optional 为可选责任（虚线框）
{"items": [{"title": "重大疾病", "amount": "100%", "unit": "基本保额", "desc": "120 种，确诊即给付", "icon": "shield", "key": true},
           {"title": "特定疾病额外给付", "amount": "+50%", "unit": "基本保额", "desc": "……", "optional": true}]}

// case 客户案例：profile 画像（左栏）→ steps 推演（最后一步为结果，主色）→ structure 可选的保障结构条
{"profile": {"name": "张先生 · 35 岁", "tags": ["家庭支柱", "有房贷"], "facts": [["年收入", "30 万元"]]},
 "steps": [{"label": "① 风险缺口", "title": "收入中断 5 年", "value": "150", "unit": "万元", "desc": "……"},
           {"label": "③ 结果", "title": "缺口补齐", "value": "4%", "unit": "年收入", "result": true}],
 "structure": {"items": [["团险", 30], ["重疾", 50], ["定期寿险", 100]], "note": "单位：万元"}}

// journey 服务旅程：emotion 为客户感受（1-5，连成曲线），pain 标为痛点（红色），note_title + note 为下方说明
{"steps": [{"title": "审核", "desc": "平均 9.5 天", "icon": "search", "emotion": 1.4, "pain": true,
            "note_title": "进度不透明", "note": "只告知“审核中”"}]}

// radar 雷达对比（原生图表，可在 PowerPoint 中改数据）：highlight 的方案用主色加粗；table 为右侧对比表（格式同 table）
{"axes": ["保额", "病种覆盖", "轻中症赔付", "增值服务", "保费负担"],
 "series": [{"name": "基础版", "values": [3, 3, 2, 1, 5]}, {"name": "尊享版", "values": [4, 4, 4, 3, 4], "highlight": true}],
 "max": 5, "table": {"columns": ["对比项", "基础版", "尊享版"], "rows": [["重疾保额", "30 万", "50 万"]], "highlight_col": 2}}

// roadmap 泳道路线图：start / end / at / now 以时间段为单位（0 = 第一段开始，1.5 = 第二段中间）
//   key 为重点项目（主色块）；同一条线时间重叠的事项自动分两行；now 画红色“当前”线
{"periods": ["10 月", "11 月", "12 月", "1 月"], "current_period": 1, "now": 1.6,
 "lanes": [{"name": "继续率", "items": [{"title": "逐单回访", "start": 1, "end": 2, "key": true}],
            "milestones": [{"at": 2, "title": "回访完成"}]}]}

// qa 问答话术：avoid 为“避免说”（写 "auto" 或不写时按 compliance.json 的 qa_avoid 自动匹配；auto_avoid: false 关闭）
//   “避免说”一栏质检时不算违规用语；每页 3 组，多了自动拆页
{"items": [{"q": "这个保险能保本吗？", "a": "这是保障型产品……", "avoid": "auto"}]}
```

---

## 与 Excel 数据联动：data_from

内容页写 `data_from`，渲染时从工作簿读取数据填进 `data`，并自动写“数据来源”脚注：

```jsonc
"data_from": {
  "file": "经营看板.xlsx",          // 相对内容 JSON 所在目录；也可以是 Excel 的内容 JSON（kb-to-excel 的 .json）
  "table": "机构明细",              // 工作表名或 Excel 表格对象名
  "categories": "机构",             // 分类字段（图表 / 进度条 / 方块地图 / 瀑布图）
  "series": ["新单保费", "目标"],    // 数值字段；进度条、地图、瀑布图只用第一个
  "columns": ["机构", "新单保费"],   // 表格的列
  "where": {"状态": ["关注", "预警"]}, "sort": "达成率", "desc": true, "top": 8,
  "number_format": "0.0%", "formats": {"达成率": "0.0%"},   // 显示格式（表格按列）
  "as": "chart"                     // 页面没写 layout 时按什么版式填：chart / bars / tilemap / waterfall / table
}
```

- 读 `.xlsx` 取的是单元格计算结果：脚本刚生成、没在 Excel 里打开保存过的文件，公式列没有值，渲染会提示先打开保存一次。
- 读 Excel 内容 JSON 只能取原始字段（公式列没有值）；需要达成率这类公式列时，引用打开保存过的 `.xlsx`。
- 找不到字段、文件或工作表时，校验阶段报错（退出码 2），不会生成错误的图表。
