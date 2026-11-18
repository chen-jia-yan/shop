# -*- coding: utf-8 -*-
"""
智能排版：
  1. choose_layout  内容页 layout 写 "auto"（或不写）时，按数据形状自动选择最合适的图示
  2. expand         自动插入目录页；要点过多自动拆成多页（阈值见 rules.ppt.bullets_split_over / bullets_per_page）
  3. check_deck     版式重复、信息密度、缺少讲稿、动画过多等问题汇总，供交付前修改
"""
import copy

from ppt_theme import L as label, R

AUTO_RULES = """
数据特征 → 自动选择的版式
  chart / categories+series     → chart 原生图表
  quadrants                     → matrix 四象限
  nodes，或 steps 带 time        → timeline 时间线
  steps                         → process 箭头流程（≤6 步）
  levels 都带 value             → funnel 漏斗
  levels 带 items               → layers 分层架构
  levels                        → pyramid 金字塔
  root + children               → hierarchy 层级结构
  left + right                  → compare 对比
  columns + rows                → table 表格
  columns（每列带 items）        → columns 分栏
  center + items（cycle: true） → cycle 循环
  center + items                → hub 中心辐射
  items 带 label + value（≤4）  → kpis 数据卡片
  items 带 value 且为比例         → bars 进度条
  items（3-8 条，说明较短）       → icon_grid 图标卡片
  points / items（其他）         → bullets 要点
"""

DIAGRAM_LAYOUTS = {"process", "timeline", "cycle", "funnel", "pyramid", "matrix", "hub", "hierarchy", "stairs",
                   "layers", "kpis", "bars", "gauge", "icon_grid", "compare", "venn", "table", "chart", "bullets",
                   "columns"}


def _num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def choose_layout(spec):
    lay = spec.get("layout", "auto")
    if lay and lay != "auto":
        return lay
    d = spec.get("data", spec)
    if d.get("chart") or (d.get("categories") and d.get("series")):
        return "chart"
    if d.get("quadrants"):
        return "matrix"
    if d.get("nodes"):
        return "timeline"
    if d.get("steps"):
        steps = d["steps"]
        if any(isinstance(s, dict) and s.get("time") for s in steps):
            d["nodes"] = [{"time": s.get("time", ""), "title": s.get("title", ""), "desc": s.get("desc", "")}
                          for s in steps]
            return "timeline"
        return "process" if len(steps) <= R("process_max") else "timeline"
    if d.get("levels"):
        lv = d["levels"]
        if all(L.get("value") is not None for L in lv):
            return "funnel"
        if any(L.get("items") for L in lv):
            return "layers"
        return "pyramid"
    if d.get("root") and d.get("children"):
        return "hierarchy"
    if d.get("left") and d.get("right"):
        return "compare"
    if d.get("columns") and d.get("rows"):
        return "table"
    if d.get("columns") and isinstance(d["columns"][0], dict):
        return "columns"
    if d.get("center") and d.get("items"):
        return "cycle" if d.get("cycle") else "hub"
    items = d.get("items")
    if items:
        if all(isinstance(i, dict) and "label" in i and "value" in i for i in items):
            if all(_num(i["value"]) and 0 <= float(i["value"]) <= 1.0 for i in items) or len(items) > R("kpis_max"):
                return "bars"
            return "kpis"
        if all(isinstance(i, dict) and _num(i.get("value")) for i in items):
            return "bars"
        if 3 <= len(items) <= 8:
            avg = sum(len(i.get("desc", "")) if isinstance(i, dict) else 0 for i in items) / float(len(items))
            if avg <= 46:
                return "icon_grid"
        return "bullets"
    if d.get("points"):
        return "bullets"
    if d.get("value") is not None:
        return "gauge"
    return "bullets"


def expand(meta, slides):
    """自动目录、长要点拆页。返回新的幻灯片列表。"""
    out = []
    sections = [s for s in slides if s.get("type") == "section"]
    has_agenda = any(s.get("type") == "agenda" for s in slides)
    for s in slides:
        if s.get("type") == "content" and choose_layout(s) == "bullets":
            d = s.get("data", s)
            key = "points" if d.get("points") else "items"
            pts = d.get(key) or []
            per = R("bullets_per_page")
            if len(pts) > R("bullets_split_over"):
                for k in range(0, len(pts), per):
                    part = copy.deepcopy(s)
                    pd = part.get("data", part)
                    pd[key] = pts[k:k + per]
                    if k:
                        part["title"] = s["title"] + label("continued")
                    if k + per < len(pts):        # 结论条只保留在最后一页
                        part.pop("takeaway", None)
                    out.append(part)
                continue
        out.append(s)
        if s.get("type") == "cover" and meta.get("agenda", True) and not has_agenda and len(sections) >= R("agenda_min_sections"):
            out.append({"type": "agenda", "auto": True})
    return out


def check_deck(meta, slides, layouts, steps):
    warns = []
    rep = R("repeat_run")
    run = 1
    for i in range(1, len(layouts)):
        if layouts[i] and layouts[i] == layouts[i - 1] and layouts[i] not in ("section",):
            run += 1
            if run == rep:
                warns.append("第 %d-%d 页连续 %d 页使用同一版式（%s），建议换一种呈现方式" % (i - rep + 2, i + 1, rep, layouts[i]))
        else:
            run = 1
    for i, s in enumerate(slides, 1):
        if s.get("type") in ("content", "big_number", "summary", "statement") and not s.get("notes"):
            warns.append("第 %d 页没有演讲备注" % i)
        if s.get("type") == "content":
            title = s.get("title", "")
            if len(title) <= R("topic_title_len") and not any(ch.isdigit() for ch in title):
                warns.append("第 %d 页标题“%s”像话题而不是结论，建议改成一句判断" % (i, title))
        if steps[i - 1] > R("anim_steps_max"):
            warns.append("第 %d 页动画步骤 %d 个，偏多，建议拆页或合并" % (i, steps[i - 1]))
    n_content = sum(1 for s in slides if s.get("type") == "content")
    if n_content and not any(s.get("type") == "summary" for s in slides) and n_content >= R("summary_min_content"):
        warns.append("内容页较多（%d 页）但没有总结与行动页（summary）" % n_content)
    return warns
