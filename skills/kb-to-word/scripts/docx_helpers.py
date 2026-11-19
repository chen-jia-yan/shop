# -*- coding: utf-8 -*-
"""
python-docx 底层辅助函数：字体、底纹、边框、列宽、域代码等。

Word 对 XML 子元素的先后顺序有严格要求，顺序错了打开时会提示“无法读取的内容”。
所以这里所有手工插入的元素都走 insert_ordered()，按 OOXML 规范的顺序放置。
"""
import re

from docx.enum.text import WD_COLOR_INDEX, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from themes import BRAND, CONF, FONTS

# ---- OOXML 子元素顺序（只列出本项目会用到的及其相邻元素） ----
PPR_ORDER = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
             "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
             "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
             "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing",
             "mirrorIndents", "suppressOverlap", "jc", "textDirection", "textAlignment",
             "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange"]
TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
               "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders",
               "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription"]
TCPR_ORDER = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap",
              "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark"]
TRPR_ORDER = ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter", "cantSplit",
              "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden"]
SECTPR_ORDER = ["headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz",
                "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols", "formProt",
                "vAlign", "noEndnote", "titlePg", "textDirection", "bidi", "rtlGutter", "docGrid",
                "printerSettings"]
SETTINGS_AFTER_UPDATEFIELDS = ["hdrShapeDefaults", "footnotePr", "endnotePr", "compat", "docVars",
                               "rsids", "mathPr", "attachedSchema", "themeFontLang",
                               "clrSchemeMapping", "doNotIncludeSubdocsInStats",
                               "doNotAutoCompressPictures", "forceUpgrade", "captions",
                               "readModeInkLockDown", "smartTagType", "schemaLibrary",
                               "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol",
                               "listSeparator"]


def _local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def insert_ordered(parent, child, order):
    """按 order 把 child 插到 parent 中正确位置；同名旧元素先删除。"""
    name = _local(child.tag)
    for old in parent.findall(child.tag):
        parent.remove(old)
    pos = order.index(name)
    for existing in list(parent):
        en = _local(existing.tag)
        if en in order and order.index(en) > pos:
            existing.addprevious(child)
            return child
    parent.append(child)
    return child


def el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn("w:" + k), str(v))
    return e


def rgb(h):
    return RGBColor.from_string(h.lstrip("#").upper())


# ---------------- 字体与文字 ----------------
def set_run(run, size=None, bold=None, color=None, font=None, italic=None, cn=None):
    """font 为西文/数字字体（默认 FONTS["en"]），cn 为中文字体（默认 FONTS["cn"]；标题传 FONTS["head"]）。"""
    f = run.font
    if size is not None:
        f.size = Pt(CONF.size(size))
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if color:
        f.color.rgb = rgb(color)
    name_en = font or FONTS["en"]
    name_cn = cn or (FONTS["cn"] if font in (None, FONTS["en"], FONTS["num"]) else font)
    f.name = name_en
    rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name_cn)
    return run


def add_rich(par, text, size=None, color=None, bold=False, font=None, cn=None):
    """写入一段文字：支持 **加粗**；占位符（默认【待补充…】【请确认…】，见 compliance.json）自动黄底高亮。"""
    ph = CONF.placeholder_re()
    inline = re.compile(r"(\*\*.+?\*\*|%s)" % ph.pattern)
    for part in inline.split(str(text or "")):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            set_run(par.add_run(part[2:-2]), size, True, color, font, cn=cn)
        elif ph.fullmatch(part):
            r = set_run(par.add_run(part), size, True, BRAND["ink"], font, cn=cn)
            r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        else:
            set_run(par.add_run(part), size, bold, color, font, cn=cn)
    return par


def spacing(par, before=None, after=None, line=None, exact=None):
    pf = par.paragraph_format
    if before is not None:
        pf.space_before = Pt(before)
    if after is not None:
        pf.space_after = Pt(after)
    if line is not None:
        pf.line_spacing = line
    if exact is not None:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(exact)
    return par


def para_border(par, side="bottom", color=None, sz=8, space=4):
    """段落边框（标题下划线、封面细线、引文竖线）。sz 单位为 1/8 磅。"""
    pPr = par._p.get_or_add_pPr()
    pbdr = pPr.find(qn("w:pBdr"))
    if pbdr is None:
        pbdr = insert_ordered(pPr, el("w:pBdr"), PPR_ORDER)
    for old in pbdr.findall(qn("w:" + side)):
        pbdr.remove(old)
    b = el("w:" + side, val="single", sz=sz, space=space, color=(color or BRAND["line"]))
    # pBdr 子元素顺序：top, left, bottom, right, between, bar
    order = ["top", "left", "bottom", "right", "between", "bar"]
    insert_ordered(pbdr, b, order)


def para_shade(par, fill):
    pPr = par._p.get_or_add_pPr()
    insert_ordered(pPr, el("w:shd", val="clear", color="auto", fill=fill), PPR_ORDER)


def mark_size(par, pt=1):
    """把段落标记（回车符）字号调到很小，用于封面表格后必须存在的空段，避免多出空白页。"""
    pPr = par._p.get_or_add_pPr()
    rpr = el("w:rPr")
    rpr.append(el("w:sz", val=int(pt * 2)))
    rpr.append(el("w:szCs", val=int(pt * 2)))
    insert_ordered(pPr, rpr, PPR_ORDER)
    spacing(par, 0, 0, exact=pt)


def add_tab_stop_right(par, pos_twips):
    pPr = par._p.get_or_add_pPr()
    tabs = el("w:tabs")
    tabs.append(el("w:tab", val="right", pos=pos_twips))
    insert_ordered(pPr, tabs, PPR_ORDER)


# ---------------- 表格 ----------------
def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    insert_ordered(tcPr, el("w:shd", val="clear", color="auto", fill=fill), TCPR_ORDER)


def cell_borders(cell, **sides):
    """cell_borders(cell, top=("single", 12, BRAND["primary"]), bottom=None, ...)；None 表示无边框。"""
    tcPr = cell._tc.get_or_add_tcPr()
    tcb = tcPr.find(qn("w:tcBorders"))
    if tcb is None:
        tcb = insert_ordered(tcPr, el("w:tcBorders"), TCPR_ORDER)
    order = ["top", "start", "left", "bottom", "end", "right", "insideH", "insideV", "tl2br", "tr2bl"]
    for side, spec in sides.items():
        if spec is None:
            b = el("w:" + side, val="nil")
        else:
            val, sz, color = spec
            b = el("w:" + side, val=val, sz=sz, space=0, color=color)
        insert_ordered(tcb, b, order)


def cell_margins(cell, top=60, bottom=60, left=100, right=100):
    tcPr = cell._tc.get_or_add_tcPr()
    mar = el("w:tcMar")
    for side, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        mar.append(el("w:" + side, w=v, type="dxa"))
    insert_ordered(tcPr, mar, TCPR_ORDER)


def table_borders(table, color=None, sz=4, inside_h=True, inside_v=False, outer=True):
    tblPr = table._tbl.tblPr
    b = el("w:tblBorders")
    c = color or BRAND["line"]
    for side in ("top", "left", "bottom", "right"):
        b.append(el("w:" + side, val="single" if outer else "nil", sz=sz, space=0, color=c))
    b.append(el("w:insideH", val="single" if inside_h else "nil", sz=sz, space=0, color=c))
    b.append(el("w:insideV", val="single" if inside_v else "nil", sz=sz, space=0, color=c))
    insert_ordered(tblPr, b, TBLPR_ORDER)


def no_borders(table):
    table_borders(table, outer=False, inside_h=False, inside_v=False)


def table_layout(table, widths_cm, indent_twips=None, total_twips=None):
    """固定列宽。Word 以 tblGrid + 每个单元格 tcW 为准，两处都要写。"""
    from docx.shared import Cm
    table.autofit = False
    tblPr = table._tbl.tblPr
    total = total_twips or int(sum(widths_cm) * 567)
    insert_ordered(tblPr, el("w:tblW", w=total, type="dxa"), TBLPR_ORDER)
    if indent_twips is not None:
        insert_ordered(tblPr, el("w:tblInd", w=indent_twips, type="dxa"), TBLPR_ORDER)
    insert_ordered(tblPr, el("w:tblLayout", type="fixed"), TBLPR_ORDER)
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths_cm):
        gc.set(qn("w:w"), str(int(w * 567)))
    for row in table.rows:
        for cell, w in zip(row.cells, widths_cm):
            cell.width = Cm(w)


def table_cell_margins(table, top=50, bottom=50, left=110, right=110):
    tblPr = table._tbl.tblPr
    mar = el("w:tblCellMar")
    for side, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        mar.append(el("w:" + side, w=v, type="dxa"))
    insert_ordered(tblPr, mar, TBLPR_ORDER)


def row_flags(row, header=False, cant_split=True):
    trPr = row._tr.get_or_add_trPr()
    if cant_split:
        insert_ordered(trPr, el("w:cantSplit"), TRPR_ORDER)
    if header:
        insert_ordered(trPr, el("w:tblHeader"), TRPR_ORDER)


def clear_cell(cell):
    """新建单元格自带一个空段落；返回它以便直接写入。"""
    return cell.paragraphs[0]


# ---------------- 域代码 ----------------
def _fld(run, kind):
    run._r.append(el("w:fldChar", fldCharType=kind))


def add_field(par, instr, display="", size=None, color=None, bold=None):
    r = set_run(par.add_run(), size, bold, color)
    _fld(r, "begin")
    r = set_run(par.add_run(), size, bold, color)
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = " %s " % instr
    r._r.append(it)
    r = set_run(par.add_run(), size, bold, color)
    _fld(r, "separate")
    set_run(par.add_run(display), size, bold, color)
    r = set_run(par.add_run(), size, bold, color)
    _fld(r, "end")


def field_begin(par, instr):
    r = par.add_run()
    _fld(r, "begin")
    r = par.add_run()
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = " %s " % instr
    r._r.append(it)
    r = par.add_run()
    _fld(r, "separate")


def field_end(par):
    _fld(par.add_run(), "end")


def enable_update_fields(doc):
    """打开文档时让 Word 更新目录和页码域。"""
    settings = doc.settings.element
    for old in settings.findall(qn("w:updateFields")):
        settings.remove(old)
    uf = el("w:updateFields", val="true")
    for existing in list(settings):
        if _local(existing.tag) in SETTINGS_AFTER_UPDATEFIELDS:
            existing.addprevious(uf)
            return
    settings.append(uf)


def section_page_start(section, start=1):
    sectPr = section._sectPr
    insert_ordered(sectPr, el("w:pgNumType", start=start), SECTPR_ORDER)


def strip_theme(style):
    """去掉样式里的主题字体和主题色，否则自定义字体、颜色会被主题覆盖。"""
    rpr = style.element.get_or_add_rPr()
    rf = rpr.get_or_add_rFonts()
    for a in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        rf.attrib.pop(qn("w:" + a), None)
    c = rpr.find(qn("w:color"))
    if c is not None:
        for a in ("themeColor", "themeShade", "themeTint"):
            c.attrib.pop(qn("w:" + a), None)
    return rf
