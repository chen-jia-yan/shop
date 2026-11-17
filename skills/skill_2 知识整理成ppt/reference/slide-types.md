# 版式与内容格式

## 整体结构

```json
{
  "meta": {
    "title": "XX 项目进展汇报",
    "org": "XX 公司 · XX 部",
    "date": "2026-11-16",
    "theme": "business"
  },
  "slides": [
    {"type": "cover", "...": "..."},
    {"type": "bullets", "...": "...", "notes": "这一页要讲的话"}
  ]
}
```

- `meta.theme`：`business`（商务蓝，默认）/ `tech`（科技青）/ `china`（中国红）
- `meta.org`、`meta.date` 会显示在每页页脚
- 每页都可以写 `notes`（演讲备注），**建议每页都写**
- 文本里可以用 `**加粗**`；含 `【待补充】` 的文字会自动标为橙色

---

## 1. cover 封面

```json
{"type": "cover", "title": "XX 项目第三阶段进展汇报", "subtitle": "进度、风险与下一步计划",
 "presenter": "汇报人：张三", "date": "2026 年 11 月"}
```
`date` 不填时使用 `meta.date`。

## 2. agenda 目录

```json
{"type": "agenda", "title": "目录", "items": ["项目概况", "本期进展", "风险与问题", "下一步计划"]}
```
2-6 项。

## 3. section 章节页

```json
{"type": "section", "number": "02", "title": "本期进展", "subtitle": "第三阶段完成情况"}
```
`number` 不填时自动按章节顺序编号。

## 4. bullets 要点页

```json
{"type": "bullets", "title": "第三阶段已全部上线，剩余 6 个遗留问题",
 "items": [
   "**功能**：12 个功能模块全部上线",
   {"text": "**遗留问题**：6 个，其中 2 个严重", "sub": ["均与外部系统对接有关", "预计两周内解决"]},
   "**用户反馈**：试用部门满意度 4.5 / 5"
 ],
 "takeaway": "第四阶段可按计划于 12 月 15 日启动"}
```
- `items`：最多 6 条；每条可以是字符串，或带 `sub`（二级要点，最多 3 条）的对象
- `takeaway`：可选，底部的结论条

## 5. two_column 双栏

```json
{"type": "two_column", "title": "已做的决定与待定事项",
 "left":  {"heading": "已决定", "items": ["第四阶段 12 月 15 日启动", "遗留问题清单 11 月 22 日前发出"]},
 "right": {"heading": "待定",   "items": ["是否增加移动端（待预算确认）", "测试环境是否更换服务器"]}}
```
每栏最多 5 条。适合：对比、前后、优劣、已定/待定。

## 6. table 表格

```json
{"type": "table", "title": "风险与应对",
 "header": ["风险", "影响", "应对措施", "负责人"],
 "rows": [["外部系统对接延期", "高", "每周对齐进度", "李四"],
          ["测试资源不足", "中", "【待补充】", "王五"]],
 "highlight_col": 1, "note": "数据截至 11 月 16 日"}
```
- 最多 6 行 × 5 列
- `highlight_col`：可选，从 0 开始，这一列加粗并着色

## 7. kpi 数据卡片

```json
{"type": "kpi", "title": "整体进度符合预期",
 "metrics": [
   {"value": "100%", "label": "功能上线率", "note": "12 / 12 个模块"},
   {"value": "6", "label": "遗留问题", "note": "其中严重 2 个"},
   {"value": "4.5", "label": "用户满意度", "note": "满分 5 分"}
 ],
 "takeaway": "可进入第四阶段"}
```
2-4 个指标。`value` 要短（不超过 6 个字符）。

## 8. timeline 时间线

```json
{"type": "timeline", "title": "项目里程碑",
 "events": [
   {"date": "2026.03", "title": "项目启动", "desc": "完成需求调研"},
   {"date": "2026.07", "title": "第二阶段上线", "desc": "核心功能可用"},
   {"date": "2026.11", "title": "第三阶段上线", "desc": "全部功能上线"},
   {"date": "2026.12", "title": "第四阶段启动", "desc": "移动端待定"}
 ],
 "current": 2}
```
- 3-6 个节点
- `current`：可选，当前所处的节点（从 0 开始），会高亮；之后的节点显示为浅色

## 9. process 流程

```json
{"type": "process", "title": "报销流程",
 "steps": [
   {"title": "提交", "desc": "填写报销单，上传票据"},
   {"title": "部门审批", "desc": "部门负责人审批"},
   {"title": "财务审核", "desc": "核对票据与金额"},
   {"title": "打款", "desc": "5 个工作日内到账"}
 ]}
```
3-6 步。

## 10. chart 图表

```json
{"type": "chart", "title": "问答量逐月增长，未答出率下降",
 "chart_type": "column",
 "categories": ["8月", "9月", "10月", "11月"],
 "series": [{"name": "提问数", "values": [1200, 1580, 2100, 2450]}],
 "unit": "次",
 "insight": ["4 个月增长 **104%**", "未答出率由 18% 降至 9%", "【待补充：12 月预测】"]}
```
- `chart_type`：`column`（柱状）/ `bar`（条形）/ `line`（折线）/ `pie`（饼图，只用第一个系列）
- 最多 3 个系列
- `insight`：可选，右侧的解读要点（最多 4 条）；有解读时图表占左侧 60%
- **数据必须来自知识库**

## 11. quote 金句/重点

```json
{"type": "quote", "text": "把知识库从“能查到”变成“能用上”", "source": "2027 年知识管理目标"}
```
适合：方案的一句话概述、需要领导决策的事项、核心观点。文字不超过 40 字。

## 12. summary 总结与下一步

```json
{"type": "summary", "title": "总结与下一步",
 "points": ["第三阶段全部上线", "2 个严重遗留问题两周内解决", "第四阶段 12 月 15 日启动"],
 "next_steps": [
   {"action": "发出遗留问题清单", "owner": "李四", "due": "11 月 22 日"},
   {"action": "确认移动端预算", "owner": "【待补充】", "due": "【待补充】"}
 ]}
```
`points` 最多 4 条；`next_steps` 最多 5 条。只写其中一部分也可以。

## 13. end 结束页

```json
{"type": "end", "title": "谢谢", "subtitle": "欢迎提问与交流", "contact": "张三 · zhangsan@example.com"}
```
