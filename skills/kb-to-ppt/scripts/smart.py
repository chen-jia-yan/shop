# -*- coding: utf-8 -*-
"""
智能排版与整套检查：
  1. choose_layout  内容页 layout 写 "auto"（或不写）时，按数据形状自动选择最合适的图示
  2. expand         自动目录、执行摘要（由各页结论标题汇总）、长要点 / 问答拆页、
                    对外版本自动插入“重要提示”、精简版只保留关键页
  3. timing         按讲稿字数估算每页讲述时长，目录页和章节页显示每章时长
  4. check_deck     标题体检（是不是结论、有没有数字、是否过长、是否点明异常项）、版式重复、信息密度、
                    强调过多、缺讲稿、动画过多、超出会议时长等，汇总到构建报告
"""
import copy
import math
import re

from ppt_theme import CONF, L as label, R

AUTO_RULES = """
数据特征 → 自动选择的版式
  chart / categories+series     → chart 原生图表
  start + items                 → waterfall 瀑布图（差异归因）
  axes + series                 → radar 雷达对比
  lanes                         → roadmap 泳道路线图
  profile + steps               → case 客户案例推演
  quadrants                     → matrix 四象限
  steps 带 emotion               → journey 服务旅程
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
  items 带 q                    → qa 问答话术
  items 带 amount               → coverage 保障责任一览
  map: true，或 items 全是区域名  → tilemap 区域方块地图
  items 带 label + value（≤4）  → kpis 数据卡片
  items 带 value 且为比例         → bars 进度条
  items（3-8 条，说明较短）       → icon_grid 图标卡片
  points / items（其他）         → bullets 要点
"""

DIAGRAM_LAYOUTS = {"process", "timeline", "cycle", "funnel", "pyramid", "matrix", "hub", "hierarchy", "stairs",
                   "layers", "kpis", "bars", "gauge", "icon_grid", "compare", "venn", "table", "chart", "bullets",
                   "columns", "waterfall", "tilemap", "coverage", "case", "journey", "radar", "roadmap", "qa"}
FRAME = ("cover", "agenda", "section", "end", "disclaimer")


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
    if d.get("start") and d.get("items"):
        return "waterfall"
    if d.get("axes") and d.get("series"):
        return "radar"
    if d.get("lanes"):
        return "roadmap"
    if d.get("profile") and d.get("steps"):
        return "case"
    if d.get("quadrants"):
        return "matrix"
    if d.get("nodes"):
        return "timeline"
    if d.get("steps"):
        steps = d["steps"]
        if any(isinstance(s, dict) and s.get("emotion") is not None for s in steps):
            return "journey"
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
        if all(isinstance(i, dict) and i.get("q") for i in items):
            return "qa"
        if all(isinstance(i, dict) and "amount" in i for i in items):
            return "coverage"
        regions = R("tilemap_regions")
        if d.get("map") or (len(items) >= 3 and all(isinstance(i, dict) and i.get("label") in regions and _num(i.get("value"))
                                                    for i in items)):
            return "tilemap"
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


def _plain(s):
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(s or ""))


def _split(s, key, per, out):
    d = s.get("data", s)
    pts = d.get(key) or []
    for k in range(0, len(pts), per):
        part = copy.deepcopy(s)
        pd = part.get("data", part)
        pd[key] = pts[k:k + per]
        if k:
            part["title"] = s["title"] + label("continued")
            part.pop("key", None)
        if k + per < len(pts):            # 结论条只保留在最后一页
            part.pop("takeaway", None)
        out.append(part)


def _brief(slides):
    """精简版：保留封面、执行摘要、总结、提示、结束页，以及标了 key 的页；某章没有 key 页时保留该章第一页内容。"""
    keep_t = set(R("brief")["keep_types"])
    per = R("brief")["per_section"]
    parts, chap = [], None                 # parts：("page", 页) 或 ("chap", {章节页, 关键页, 候选页})
    for s in slides:
        tp = s.get("type")
        if tp == "section":
            chap = {"spec": s, "kept": [], "cands": []}
            parts.append(("chap", chap))
        elif tp in keep_t or tp == "agenda":
            parts.append(("page", s))
        elif chap is None:
            if s.get("key"):
                parts.append(("page", s))
        else:
            (chap["kept"] if s.get("key") else chap["cands"]).append(s)
    res = []
    for kind, it in parts:
        if kind == "page":
            res.append(it)
            continue
        body = it["kept"] or it["cands"][:per]
        if body:
            res.append(it["spec"])
            res += body
    return res


def expand(meta, slides, brief=False):
    """自动目录 / 执行摘要 / 拆页 / 重要提示 / 精简版。返回新的幻灯片列表。"""
    out = []
    sections = [s for s in slides if s.get("type") == "section"]
    has = {s.get("type") for s in slides}
    lim = R("limits")
    for s in slides:
        if s.get("type") == "content":
            lay = choose_layout(s)
            d = s.get("data", s)
            if lay == "bullets":
                key = "points" if d.get("points") else "items"
                if len(d.get(key) or []) > R("bullets_split_over"):
                    _split(s, key, R("bullets_per_page"), out)
                    continue
            if lay == "qa" and len(d.get("items") or []) > lim["qa"]:
                _split(s, "items", lim["qa"], out)
                continue
        out.append(s)
        if s.get("type") == "cover":
            if meta.get("agenda", True) and "agenda" not in has and len(sections) >= R("agenda_min_sections"):
                out.append({"type": "agenda", "auto": True})
            if meta.get("exec_summary") and "exec_summary" not in has:
                es = meta["exec_summary"] if isinstance(meta["exec_summary"], dict) else {}
                out.append(dict(es, type="exec_summary", auto=True))
    if external(meta) and "disclaimer" not in has:
        pos = next((i for i in range(len(out) - 1, -1, -1) if out[i].get("type") == "end"), len(out))
        out.insert(pos, {"type": "disclaimer", "auto": True})
    for s in out:
        if s.get("type") == "disclaimer" and not s.get("items"):
            rn = CONF.compliance().get("risk_notice") or {}
            s["items"] = rn.get(meta.get("product_kind") or "default") or rn.get("default", [])
    if brief:
        out = _brief(out)
    _fill_exec(meta, out)
    return out


def external(meta):
    """对外材料：meta.external 为 true，或 deck_type 属于对客户类型（compliance.customer_facing_types）。"""
    if meta.get("external") is not None:
        return bool(meta["external"])
    return meta.get("deck_type") in (CONF.compliance().get("customer_facing_types") or [])


def _fill_exec(meta, slides):
    """执行摘要的条目：优先取 key: true 的页，不足 3 条时补每章第一页；页码在最终顺序确定后计算。"""
    for es in (s for s in slides if s.get("type") == "exec_summary"):
        if not es.get("items"):
            body = [(i + 1, s) for i, s in enumerate(slides) if s.get("type") in ("content", "big_number", "statement")]
            picked = [p for p in body if p[1].get("key")]
            if len(picked) < 3:
                seen_sec, cur = set(), None
                for i, s in enumerate(slides):
                    if s.get("type") == "section":
                        cur = i
                    elif s.get("type") in ("content", "big_number") and cur not in seen_sec:
                        seen_sec.add(cur)
                        if (i + 1, s) not in picked:
                            picked.append((i + 1, s))
                picked.sort(key=lambda p: p[0])
            es["items"] = [{"title": _plain(s.get("title") or s.get("text")),
                            "sub": _plain(s.get("kicker") or s.get("takeaway") or ""), "page": pg, "alert": s.get("alert")}
                           for pg, s in picked[:R("exec_summary_max")]]
        if es.get("decisions") is None:
            sm = next(((i + 1, s) for i, s in enumerate(slides) if s.get("type") == "summary" and s.get("decisions")), None)
            if sm:
                es["decisions"] = [d if isinstance(d, str) else d.get("text", "") for d in sm[1]["decisions"]]
                es["decisions_page"] = sm[0]
        elif not es.get("decisions_page"):
            es["decisions_page"] = next((i + 1 for i, s in enumerate(slides) if s.get("type") == "summary"), None)


# ---------------- 讲述时长 ----------------
def timing(slides):
    """每页预计讲述分钟数：有讲稿按字数估算（rules.ppt.timing.chars_per_min），否则取每页最少时长；框架页取 frame_min。"""
    tm = R("timing")
    out = []
    for s in slides:
        if s.get("type") in FRAME:
            out.append(tm["frame_min"])
            continue
        chars = len(re.sub(r"\s", "", s.get("notes") or ""))
        out.append(max(tm["min_per_slide"], chars / float(tm["chars_per_min"])))
    return out


# ---------------- 整套检查 ----------------
def check_deck(meta, slides, layouts, steps, minutes=None):
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
    tmax, suffixes, numlays = R("title_max"), R("topic_suffixes"), R("number_layouts")
    for i, s in enumerate(slides, 1):
        if s.get("type") in ("content", "big_number", "summary", "statement") and not s.get("notes"):
            warns.append("第 %d 页没有演讲备注" % i)
        if s.get("type") == "content":
            title = _plain(s.get("title", ""))
            topic = (len(title) <= R("topic_title_len") and not any(ch.isdigit() for ch in title)) or \
                any(title.endswith(x) for x in suffixes)
            if topic:
                warns.append("第 %d 页标题“%s”像话题而不是结论，建议改成一句判断（如“华东是唯一未完成目标的区域”）" % (i, title))
            if len(title) > tmax:
                warns.append("第 %d 页标题 %d 字，超过 %d 字，建议压缩，细节放到副标题" % (i, len(title), tmax))
            lay = s.get("layout")
            if lay in numlays and not any(ch.isdigit() for ch in title):
                warns.append("第 %d 页是数据页（%s），标题里没有数字，建议写出关键数字" % (i, lay))
            d = s.get("data", s)
            al = d.get("_alert_name")
            if al and al not in title and al not in _plain(s.get("kicker", "")):
                warns.append("第 %d 页图表标出了异常项“%s”，标题和副标题都没有提到，建议点明" % (i, al))
            hl = sum(1 for it in (d.get("items") or []) if isinstance(it, dict) and it.get("highlight"))
            if hl > R("highlight_max"):
                warns.append("第 %d 页强调了 %d 项，超过 %d 项会失去重点" % (i, hl, R("highlight_max")))
        if steps[i - 1] > R("anim_steps_max"):
            warns.append("第 %d 页动画步骤 %d 个，偏多，建议拆页或合并" % (i, steps[i - 1]))
    n_content = sum(1 for s in slides if s.get("type") == "content")
    if n_content and not any(s.get("type") == "summary" for s in slides) and n_content >= R("summary_min_content"):
        warns.append("内容页较多（%d 页）但没有总结与行动页（summary）" % n_content)
    if minutes and meta.get("duration_min"):
        total = sum(minutes)
        if total > float(meta["duration_min"]):
            cands = [i + 1 for i, s in enumerate(slides) if s.get("type") == "content" and not s.get("key")]
            warns.append("预计讲述约 %d 分钟，超出会议时长 %s 分钟；可考虑删减或移到附录：第 %s 页（未标 key 的内容页），"
                         "或用 --brief 生成精简版" % (math.ceil(total), meta["duration_min"], "、".join(map(str, cands[-4:]))))
    return warns
