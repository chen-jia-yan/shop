# -*- coding: utf-8 -*-
"""
知识生成 PPT —— 渲染入口

用法：
  python render_pptx.py <内容.json> <输出.pptx> [--theme 风格名] [--brief] [--no-animation]
                        [--config 额外配置] [--font-cn 字体] [--font-en 字体] [--font-num 字体]
                        [--font-mode first|installed] [--font-scale 1.1]

  --theme   7 套主题任选：orange 橙白活力 / warm 暖阳渐变 / soft 淡雅米橙 / minimal 简约商务 /
            premium 尊享深绿 / blue 信赖科技蓝 / teal 康护青绿（见 tap-config/themes.json）
  --brief   精简版：只保留封面、执行摘要、标了 key 的页（某章没有时取该章第一页）、总结、提示和结束页

品牌、配色、字体、风格、页面尺寸、拆页阈值、固定文字、图标关键词、风险提示条目都来自 tap-config/，本脚本不写死。
流程：读取 Excel 数据（data_from）→ 校验 → 智能扩展（目录、执行摘要、拆页、对外版本插入重要提示、精简版）
      → 估算讲述时长 → 逐页绘制 → 写入动画与切换 → 保存
      → 输出构建报告（标题体检、文字放不下、版式重复、缺讲稿、超时等），同时写入 <输出名>_构建报告.md

退出码：0 成功；2 内容校验不通过。
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import CONF, add_cli_args, configure      # noqa: E402

REQUIRED = {"section": ["title"], "content": ["title"], "statement": ["text"], "big_number": ["title", "value"],
            "summary": ["title", "actions"], "cover": [], "agenda": [], "exec_summary": [], "disclaimer": [], "end": []}
NEED = {"process": "steps", "timeline": "nodes", "cycle": "items", "funnel": "levels", "pyramid": "levels",
        "matrix": "quadrants", "hub": "items", "hierarchy": "children", "stairs": "items",
        "layers": "levels", "kpis": "items", "bars": "items", "icon_grid": "items", "compare": "left",
        "venn": "items", "table": "rows", "chart": "series", "columns": "columns",
        "waterfall": "items", "tilemap": "items", "coverage": "items", "case": "steps", "journey": "steps",
        "radar": "series", "roadmap": "lanes", "qa": "items"}
LIMIT_KEY = {"waterfall": ("items", "waterfall"), "tilemap": ("items", "tilemap"), "coverage": ("items", "coverage"),
             "journey": ("steps", "journey"), "roadmap": ("lanes", "roadmap_lanes"), "radar": ("axes", "radar_axes")}


class Ctx(object):
    def __init__(self, meta, slides, minutes=None):
        self.meta = meta
        self.slides = slides
        self.sections = [s for s in slides if s.get("type") == "section"]
        self.total = len(slides)
        self.minutes = minutes or [0.0] * len(slides)
        self.page = 0
        self._cur = None

    def section_index(self, spec):
        return self.sections.index(spec) + 1 if spec in self.sections else 0

    def section_label(self, spec):
        if spec.get("eyebrow"):
            return spec["eyebrow"]
        if self._cur is None:
            return self.meta.get("short_title", "")
        return CONF.label("seq", n=self.section_index(self._cur), s=self._cur.get("short", self._cur["title"]))

    def section_stats(self, spec):
        """本章页数（不含章节页本身、总结 / 提示 / 结束页）和讲述分钟数（含章节页）。"""
        i = next(k for k, s in enumerate(self.slides) if s is spec)
        pages, mins = 0, self.minutes[i]
        for k in range(i + 1, len(self.slides)):
            tp = self.slides[k].get("type")
            if tp == "section":
                break
            if tp in ("end", "disclaimer", "summary"):
                continue
            pages += 1
            mins += self.minutes[k]
        return pages, mins

    def total_minutes(self):
        return sum(self.minutes)


def validate(data):
    # 版式模块依赖配置（页面尺寸、字号等），在 configure() 之后再导入
    from layouts import SLIDES
    from smart import DIAGRAM_LAYOUTS, choose_layout
    errs = []
    meta = data.get("meta") or {}
    themes = CONF.theme_names()
    if not meta.get("title"):
        errs.append("meta.title 缺失")
    if meta.get("theme") and meta["theme"] not in themes:
        errs.append("meta.theme 只能是：%s" % "、".join(themes))
    slides = data.get("slides") or []
    if not slides:
        errs.append("slides 为空")
    kmax, pmax = CONF.rule("kpis_max"), CONF.rule("process_max")
    lim = CONF.rule("limits")
    regions = CONF.rule("tilemap_regions")
    for i, s in enumerate(slides, 1):
        tp = s.get("type")
        where = "第 %d 页（%s）" % (i, s.get("title") or tp)
        if tp not in SLIDES:
            errs.append("%s：未知页面类型 %r，可用：%s" % (where, tp, "、".join(SLIDES)))
            continue
        for f in REQUIRED[tp]:
            if not s.get(f):
                errs.append("%s：缺少 %s" % (where, f))
        if tp != "content":
            continue
        lay = choose_layout(s)
        if lay not in DIAGRAM_LAYOUTS:
            errs.append("%s：未知版式 %r" % (where, lay))
            continue
        d = s.get("data", s)
        need = NEED.get(lay)
        if need and not d.get(need):
            errs.append("%s：版式 %s 需要字段 %s" % (where, lay, need))
            continue
        if lay == "chart":
            for se in d.get("series", []):
                if len(se.get("values", [])) != len(d.get("categories", [])):
                    errs.append("%s：系列“%s”的数据个数与分类个数不一致" % (where, se.get("name")))
        if lay == "radar":
            for se in d.get("series", []):
                if len(se.get("values", [])) != len(d.get("axes", [])):
                    errs.append("%s：雷达图系列“%s”的数据个数与维度个数不一致" % (where, se.get("name")))
        if lay == "tilemap":
            unk = [it.get("label") for it in d["items"] if not it.get("pos") and it.get("label") not in regions]
            if unk:
                errs.append("%s：区域“%s”没有预设位置，请在该项写 pos: [行, 列, 跨行, 跨列]，或在 rules.ppt.tilemap_regions 中补充"
                            % (where, "、".join(map(str, unk))))
        if lay in LIMIT_KEY:
            key, lk = LIMIT_KEY[lay]
            if len(d.get(key) or []) > lim[lk]:
                errs.append("%s：%s 最多 %d 项，请拆页或合并" % (where, lay, lim[lk]))
        if lay == "kpis" and len(d.get("items", [])) > kmax:
            errs.append("%s：数据卡片最多 %d 个" % (where, kmax))
        if lay == "process" and len(d.get("steps", [])) > pmax:
            errs.append("%s：箭头流程最多 %d 步，更多步骤请用 timeline" % (where, pmax))
    return errs


def render(data, out, theme=None, animate=True, brief=False):
    from pptx import Presentation
    import animations
    import ppt_base
    from layouts import SLIDES
    from ppt_theme import default_theme, get_theme
    from smart import check_deck, choose_layout, expand, timing

    meta = dict(data["meta"])
    if brief:
        meta["short_title"] = meta.get("short_title", meta["title"]) + CONF.label("brief_suffix")
    name = theme or meta.get("theme") or default_theme(meta.get("deck_type"))
    t = get_theme(name)
    slides = expand(meta, data["slides"], brief)
    for s in slides:
        if s.get("type") == "content":
            s["layout"] = choose_layout(s)
    minutes = timing(slides)
    prs = Presentation()
    prs.slide_width = ppt_base.I(ppt_base.W)
    prs.slide_height = ppt_base.I(ppt_base.H)
    blank = prs.slide_layouts[6]
    ctx = Ctx(meta, slides, minutes)
    layouts, steps = [], []
    animate = animate and meta.get("animate", True)
    for i, s in enumerate(slides, 1):
        ctx.page = i
        if s.get("type") == "section":
            ctx._cur = s
        slide = prs.slides.add_slide(blank)
        seq = animations.Seq(slide)
        SLIDES[s["type"]](slide, t, ctx, seq, s)
        if s.get("notes"):
            slide.notes_slide.notes_text_frame.text = s["notes"]
        tr = s.get("transition") or meta.get("transition") or ("push" if s["type"] == "section" else "fade")
        n = animations.apply(slide, seq, tr, animate and s.get("animate", True))
        layouts.append(s.get("layout") or s["type"])
        steps.append(n)
    warns = list(ppt_base.FIT_LOG) + check_deck(meta, slides, layouts, steps, minutes)
    cp = prs.core_properties
    cp.title = meta["title"]
    cp.subject = meta.get("subtitle", "")
    cp.author = meta.get("department") or CONF.org.get("author_default") or CONF.org_name(meta)
    cp.keywords = ",".join(meta.get("tags", []))
    cp.comments = json.dumps({"theme": name, "layouts": layouts, "steps": steps,
                              "minutes": [round(m, 1) for m in minutes], "brief": brief}, ensure_ascii=False)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    prs.save(out)
    return t, slides, layouts, steps, warns, minutes


def main():
    ap = argparse.ArgumentParser(description="知识生成 PPT：把内容 JSON 渲染为品牌风格 .pptx")
    ap.add_argument("content")
    ap.add_argument("output")
    ap.add_argument("--theme", help="风格名，见 tap-config/themes.json 的 themes.ppt.styles")
    ap.add_argument("--brief", action="store_true", help="生成精简版（管理层版）")
    ap.add_argument("--no-animation", action="store_true")
    add_cli_args(ap)
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as f:
        data = json.load(f)
    configure("ppt", a, data.get("meta"))
    if a.theme and a.theme not in CONF.theme_names():
        sys.exit("未知风格 %s，可选：%s" % (a.theme, "、".join(CONF.theme_names())))
    import datalink
    from smart import choose_layout
    errs = datalink.resolve(data.get("slides") or [], os.path.dirname(os.path.abspath(a.content)), choose_layout)
    errs += validate(data)
    if errs:
        print("内容校验未通过，共 %d 处：" % len(errs))
        for e in errs:
            print("  - " + e)
        sys.exit(2)
    t, slides, layouts, steps, warns, minutes = render(data, a.output, a.theme, not a.no_animation, a.brief)
    todo, confirm = CONF.count_placeholders(json.dumps(data, ensure_ascii=False))
    fonts = CONF.fonts
    lines = ["# " + CONF.label("report.build_title", name=os.path.basename(a.output)), "",
             "风格：%s；共 %d 页；预计讲述约 %d 分钟；动画步骤合计 %d 个%s" %
             (t["name"], len(slides), math.ceil(sum(minutes)), sum(steps), "；精简版" if a.brief else ""),
             "字体：中文 %s / 西文 %s / 数字 %s；字号倍数 %.2f" % (fonts["cn"], fonts["en"], fonts["num"], CONF.font_scale),
             "", "| 页 | 类型 | 版式 | 标题 | 讲述（分钟） | 动画步骤 |", "|---|---|---|---|---|---|"]
    for i, (sp, lay, n, m) in enumerate(zip(slides, layouts, steps, minutes), 1):
        title = (sp.get("title") or sp.get("text") or "").replace("|", "／").replace("**", "")[:30]
        lines.append("| %d | %s | %s | %s | %.1f | %d |" % (i, sp["type"], lay, title, m, n))
    lines += ["", "## 需要处理（%d）" % len(warns)] + (["- " + w for w in warns] or ["- " + CONF.label("report.none")])
    if todo or confirm:
        lines.append("- 占位：待补充 %d 处，请确认 %d 处" % (todo, confirm))
    report = "\n".join(lines)
    with open(os.path.splitext(a.output)[0] + "_构建报告.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
