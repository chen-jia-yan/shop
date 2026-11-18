# 页面与图示：JSON 格式与选用

## 整体结构

```json
{
  "meta": {
    "title": "2026 年第三季度个险渠道经营汇报", "short_title": "Q3 个险经营汇报",
    "subtitle": "副标题", "category": "经营分析",
    "deck_type": "analysis",        // work_report / proposal / training / product / project / analysis / customer / kickoff
    "theme": "premium",             // orange / premium / minimal / warm；不填按 deck_type
    "presenter": "战略规划部", "department": "", "date": "2026 年 10 月", "confidentiality": "内部",
    "agenda": true,                 // 2 个以上章节时自动插入目录页
    "animate": true, "transition": null,   // 关闭动画 / 统一指定切换效果
    "footer": null                  // 自定义页脚文字
  },
  "slides": [ ... ]
}
```

所有文字支持 `**加粗**`、【待补充：XX】、【请确认：XX】。每页可写 `notes`（演讲备注）、`transition`、`animate: false`。

---

## 8 种页面

| type | 用途 | 主要字段 |
|---|---|---|
| `cover` | 封面 | `icon`（封面装饰图标），其余取自 meta |
| `agenda` | 目录 | 自动列出所有章节；一般不用手写 |
| `section` | 章节页 | `title`、`subtitle`、`short`（眉标用短名）；右侧自动显示章节导航并高亮当前章 |
| `content` | 内容页 | `title`（结论）、`kicker`（副标题）、`layout`、`data`、`insight`、`takeaway` |
| `statement` | 观点/金句页 | `text`、`sub` |
| `big_number` | 大数字页 | `title`、`value`、`unit`、`label`、`points`（右侧 2-3 条说明） |
| `summary` | 总结与行动 | `title`、`actions: [{action, desc, owner, due}]` |
| `end` | 结束页 | `text`（默认“谢谢”）、`sub`、`contacts: [{label, value}]` |

内容页通用字段：
- `insight: {"title": "关键发现", "items": ["……"]}` → 右侧解读栏（适合图表页）
- `takeaway: "……"` → 底部结论条
- `eyebrow` → 覆盖左上角章节眉标

---

## 什么内容用什么版式

| 想表达 | 版式 | 数据量 |
|---|---|---|
| 几个关键数字 | `kpis` | 2-4 个 |
| 一个特别重要的数字 | 页面 `big_number` | 1 个 |
| 完成率、达成率等比例 | `gauge`（单个）/ `bars`（多个对比） | 1 / 3-8 |
| 趋势、对比、构成 | `chart` | 分类 ≤8 |
| 明细数据 | `table` | ≤7 行 6 列 |
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

## 18 种图示 + 2 种文字版式的 data 格式

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

// kpis 数据卡片：highlight 的卡片用主色底；delta 以 ▲/▼ 开头自动着色，good: "down" 表示下降为好
{"items": [{"label": "<指标名>", "value": "<数值>", "unit": "<单位>", "delta": "▲ <变化>", "delta_label": "同比",
            "icon": "coin", "highlight": true}]}

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

// bullets 要点（自动配图标，>4 条分两列，>8 条自动拆页）
{"points": [{"title": "不承诺收益", "desc": "……", "icon": "lock"}]}

// columns 分栏
{"columns": [{"title": "年轻单身", "items": ["……"], "highlight": false}]}
```
