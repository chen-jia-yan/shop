# -*- coding: utf-8 -*-
"""
知识生成 PPT —— 渲染入口

用法：
  python render_pptx.py <内容.json> <输出.pptx> [--theme 风格名] [--no-animation]
                        [--config 额外配置] [--font-cn 字体] [--font-en 字体] [--font-num 字体]
                        [--font-mode first|installed] [--font-scale 1.1]

品牌、配色、字体、风格、页面尺寸、拆页阈值、固定文字、图标关键词都来自 tap-config/，本脚本不写死。
流程：校验 → 智能扩展（自动目录、长要点拆页、自动选版式）→ 逐页绘制 → 写入动画与切换 → 保存
      → 输出构建报告（文字放不下、版式重复、缺讲稿等），同时写入 <输出名>_构建报告.md

退出码：0 成功；2 内容校验不通过。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import CONF, add_cli_args, configure      # noqa: E402

REQUIRED = {"section": ["title"], "content": ["title"], "statement": ["text"], "big_number": ["title", "value"],
            "summary": ["title", "actions"], "cover": [], "agenda": [], "end": []}
NEED = {"process": "steps", "timeline": "nodes", "cycle": "items", "funnel": "levels", "pyramid": "levels",
        "matrix": "quadrants", "hub": "items", "hierarchy": "children", "stairs": "items",
        "layers": "levels", "kpis": "items", "bars": "items", "icon_grid": "items", "compare": "left",
        "venn": "items", "table": "rows", "chart": "series", "columns": "columns"}


class Ctx(object):
    def __init__(self, meta, slides):
        self.meta = meta
        self.slides = slides
        self.sections = [s for s in slides if s.get("type") == "section"]
        self.total = len(slides)
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
    for i, s in enumerate(slides, 1):
        tp = s.get("type")
        where = "第 %d 页（%s）" % (i, s.get("title") or tp)
        if tp not in SLIDES:
            errs.append("%s：未知页面类型 %r，可用：%s" % (where, tp, "、".join(SLIDES)))
            continue
        for f in REQUIRED[tp]:
            if not s.get(f):
                errs.append("%s：缺少 %s" % (where, f))
        if tp == "content":
            lay = choose_layout(s)
            if lay not in DIAGRAM_LAYOUTS:
                errs.append("%s：未知版式 %r" % (where, lay))
            d = s.get("data", s)
            need = NEED.get(lay)
            if need and not d.get(need):
                errs.append("%s：版式 %s 需要字段 %s" % (where, lay, need))
            if lay == "chart":
                for se in d.get("series", []):
                    if len(se.get("values", [])) != len(d.get("categories", [])):
                        errs.append("%s：系列“%s”的数据个数与分类个数不一致" % (where, se.get("name")))
            if lay == "kpis" and len(d.get("items", [])) > kmax:
                errs.append("%s：数据卡片最多 %d 个" % (where, kmax))
            if lay == "process" and len(d.get("steps", [])) > pmax:
                errs.append("%s：箭头流程最多 %d 步，更多步骤请用 timeline" % (where, pmax))
    return errs


def render(data, out, theme=None, animate=True):
    from pptx import Presentation
    import animations
    import ppt_base
    from layouts import SLIDES
    from ppt_theme import default_theme, get_theme
    from smart import check_deck, choose_layout, expand

    meta = data["meta"]
    name = theme or meta.get("theme") or default_theme(meta.get("deck_type"))
    t = get_theme(name)
    slides = expand(meta, data["slides"])
    for s in slides:
        if s.get("type") == "content":
            s["layout"] = choose_layout(s)
    prs = Presentation()
    prs.slide_width = ppt_base.I(ppt_base.W)
    prs.slide_height = ppt_base.I(ppt_base.H)
    blank = prs.slide_layouts[6]
    ctx = Ctx(meta, slides)
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
    warns = list(ppt_base.FIT_LOG) + check_deck(meta, slides, layouts, steps)
    cp = prs.core_properties
    cp.title = meta["title"]
    cp.subject = meta.get("subtitle", "")
    cp.author = meta.get("department") or CONF.org.get("author_default") or CONF.org_name(meta)
    cp.keywords = ",".join(meta.get("tags", []))
    cp.comments = json.dumps({"theme": name, "layouts": layouts, "steps": steps}, ensure_ascii=False)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    prs.save(out)
    return t, slides, layouts, steps, warns


def main():
    ap = argparse.ArgumentParser(description="知识生成 PPT：把内容 JSON 渲染为品牌风格 .pptx")
    ap.add_argument("content")
    ap.add_argument("output")
    ap.add_argument("--theme", help="风格名，见 tap-config/themes.json 的 themes.ppt.styles")
    ap.add_argument("--no-animation", action="store_true")
    add_cli_args(ap)
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as f:
        data = json.load(f)
    configure("ppt", a, data.get("meta"))
    if a.theme and a.theme not in CONF.theme_names():
        sys.exit("未知风格 %s，可选：%s" % (a.theme, "、".join(CONF.theme_names())))
    errs = validate(data)
    if errs:
        print("内容校验未通过，共 %d 处：" % len(errs))
        for e in errs:
            print("  - " + e)
        sys.exit(2)
    t, slides, layouts, steps, warns = render(data, a.output, a.theme, not a.no_animation)
    todo, confirm = CONF.count_placeholders(json.dumps(data, ensure_ascii=False))
    fonts = CONF.fonts
    lines = ["# " + CONF.label("report.build_title", name=os.path.basename(a.output)), "",
             "风格：%s；共 %d 页；动画步骤合计 %d 个" % (t["name"], len(slides), sum(steps)),
             "字体：中文 %s / 西文 %s / 数字 %s；字号倍数 %.2f" % (fonts["cn"], fonts["en"], fonts["num"], CONF.font_scale),
             "", "| 页 | 类型 | 版式 | 动画步骤 |", "|---|---|---|---|"]
    for i, (sp, lay, n) in enumerate(zip(slides, layouts, steps), 1):
        lines.append("| %d | %s | %s | %d |" % (i, sp["type"], lay, n))
    lines += ["", "## 需要处理（%d）" % len(warns)] + (["- " + w for w in warns] or ["- " + CONF.label("report.none")])
    if todo or confirm:
        lines.append("- 占位：待补充 %d 处，请确认 %d 处" % (todo, confirm))
    report = "\n".join(lines)
    with open(os.path.splitext(a.output)[0] + "_构建报告.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
