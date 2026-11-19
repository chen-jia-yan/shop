# -*- coding: utf-8 -*-
"""
openpyxl 辅助：样式工厂、列宽估算、标题区、打印设置，以及“公式联动”的引用解析。

公式联动：内容 JSON 里的公式可以用花括号引用其他位置，渲染完所有工作表后统一替换成真实地址，
所以看板可以引用排在后面的明细表。支持的写法：

  {@保费}                 当前表同一行的“保费”列（用于逐行公式，如 ={@保额}/1000*{@费率}）
  {明细.保费}              “明细”表“保费”列的全部数据行，如 '明细'!$D$5:$D$14
  {明细.保费#3}            第 3 个数据行的单元格
  {明细.保费=华南}         第一列等于“华南”的那一行的单元格
  {明细.保费:total}        合计行的单元格（表格开启了合计行时）
  {input.amount}          试算表中 key 为 amount 的录入格
  {output.premium}        试算表中 key 为 premium 的结果格
  {lookup.费率表.data}     查找表的数据区（不含首列和表头）
  {lookup.费率表.col1}     查找表首列数据
  {lookup.费率表.header}   查找表表头（不含首列）
"""
import re

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from xl_theme import BRAND, CONF, FONTS, ROLE, L

TOKEN = re.compile(r"\{([^{}]+)\}")


def _todo():
    """占位符规则（默认【待补充…】【请确认…】），见 compliance.json 的 placeholders。"""
    return CONF.placeholder_re()


# ---------------- 样式工厂 ----------------
def font(size=10, bold=False, color=None, name=None, italic=False, underline=None):
    return Font(name=name or FONTS["cn"], size=CONF.size(size), bold=bold, italic=italic, underline=underline,
                color="FF" + (color or BRAND["ink"]))


def fill(hex_color):
    if not hex_color:
        return PatternFill(fill_type=None)
    return PatternFill(fill_type="solid", start_color="FF" + hex_color, end_color="FF" + hex_color)


def side(color=None, style="thin"):
    return Side(style=style, color="FF" + (color or BRAND["line"]))


def border(top=None, bottom=None, left=None, right=None):
    return Border(top=top or Side(), bottom=bottom or Side(), left=left or Side(), right=right or Side())


def box(color=None, style="thin"):
    s = side(color, style)
    return Border(top=s, bottom=s, left=s, right=s)


def align(h="left", v="center", wrap=False, indent=0):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap, indent=indent)


def text_width(s):
    """估算显示宽度：中文按 2，英文数字按 1.1。"""
    s = str(s if s is not None else "")
    return sum(2.0 if ord(ch) > 0x2E80 else 1.1 for ch in s)


def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def auto_width(values, lo=8, hi=46, pad=3):
    return max(lo, min(hi, max([text_width(v) for v in values] + [0]) + pad))


def put(ws, row, col, value, f=None, fl=None, al=None, bd=None, fmt=None):
    c = ws.cell(row=row, column=col, value=value)
    if f is not None:
        c.font = f
    if fl is not None:
        c.fill = fl
    if al is not None:
        c.alignment = al
    if bd is not None:
        c.border = bd
    if fmt:
        c.number_format = fmt
    if isinstance(value, str) and _todo().search(value):
        c.fill = fill(ROLE["todo_bg"])
        c.font = Font(name=FONTS["cn"], size=c.font.sz or CONF.size(10), bold=True, color="FF" + BRAND["primary_dark"])
    return c


def title_block(ws, st, title, subtitle=None, ncols=6, note=None):
    """第 1 行色条，第 2 行标题，第 3 行副标题/口径；返回下一可用行号。"""
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 6
    for c in range(1, ncols + 1):
        ws.cell(row=1, column=c).fill = fill(st["title_bar"])
    ws.row_dimensions[2].height = 32
    put(ws, 2, 1, title, font(16, True, st["title"]), al=align("left", "center"))
    r = 3
    if subtitle:
        put(ws, 3, 1, subtitle, font(9.5, False, st["subtitle"]), al=align("left", "center"))
        ws.row_dimensions[3].height = 18
        r = 4
    if note:
        put(ws, r, 1, note, font(9, False, BRAND["muted"], italic=True), al=align("left", "center"))
        r += 1
    return r + 1  # 空一行


def print_setup(ws, landscape=True, title_rows=None, brand=None):
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = 0.6
    ws.page_margins.bottom = 0.6
    if title_rows:
        ws.print_title_rows = title_rows
    ws.oddHeader.left.text = L("print_header", brand=brand or CONF.org_name())
    ws.oddHeader.left.size = 8
    ws.oddFooter.center.text = L("print_footer")
    ws.oddFooter.center.size = 8


def qsheet(name):
    return "'%s'!" % name.replace("'", "''")


def absref(col, row):
    return "$%s$%d" % (get_column_letter(col), row)


# ---------------- 公式联动 ----------------
class Registry(object):
    def __init__(self):
        self.tables = {}    # sheet -> {"cols": {name: idx}, "first": r, "last": r, "keys": {key: r}, "total": r}
        self.cells = {}     # "input.x" / "output.x" -> "'试算'!$C$5"
        self.lookups = {}   # name -> {"sheet", "r0", "r1", "c0", "c1"}
        self.pending = []   # (ws, coord, raw, sheet)
        self.errors = []

    def table(self, sheet, cols, first, last, keys, total=None, tname=None, ws_name=None):
        """登记一张表。tname：Excel“表格”对象名（数据表），有它时 {表.列} 解析为结构化引用 tname[列]，
        用户在表格下方新增行时公式自动覆盖新行；ws_name：真实工作表名（登记别名时用，如仪表盘里的图表数据区）。"""
        self.tables[sheet] = {"cols": {c: i for i, c in enumerate(cols, 1)}, "first": first,
                              "last": last, "keys": keys, "total": total, "tname": tname,
                              "sheet": ws_name or sheet}

    def cell(self, ns, key, sheet, col, row):
        k = "%s.%s" % (ns, key)
        if k in self.cells:
            self.errors.append("重复的 %s：%s" % (ns, key))
        self.cells[k] = qsheet(sheet) + absref(col, row)

    def defer(self, ws, coord, raw):
        self.pending.append((ws, coord, raw))

    # -- 行内引用 {@列} 在写入时立即替换 --
    @staticmethod
    def row_formula(raw, cols, row):
        def rep(m):
            tok = m.group(1)
            if not tok.startswith("@"):
                return m.group(0)
            name = tok[1:]
            if name not in cols:
                raise KeyError("逐行公式引用了不存在的列：%s" % name)
            return "%s%d" % (get_column_letter(cols[name]), row)
        return TOKEN.sub(rep, raw)

    def resolve_token(self, tok):
        if tok.startswith("input.") or tok.startswith("output.") or tok.startswith("param.") \
                or tok.startswith("options."):
            if tok not in self.cells:
                raise KeyError("找不到 %s" % tok)
            return self.cells[tok]
        if tok.startswith("lookup."):
            _, name, part = tok.split(".", 2)
            lk = self.lookups.get(name)
            if not lk:
                raise KeyError("找不到查找表 %s" % name)
            s = qsheet(lk["sheet"])
            if part == "data":
                return s + absref(lk["c0"] + 1, lk["r0"] + 1) + ":" + absref(lk["c1"], lk["r1"])
            if part == "col1":
                return s + absref(lk["c0"], lk["r0"] + 1) + ":" + absref(lk["c0"], lk["r1"])
            if part == "header":
                return s + absref(lk["c0"] + 1, lk["r0"]) + ":" + absref(lk["c1"], lk["r0"])
            raise KeyError("查找表引用只支持 data / col1 / header：%s" % tok)
        m = re.match(r"^([^.]+)\.(.+?)(?:#(\d+)|=(.+)|:(total))?$", tok)
        if not m:
            raise KeyError("无法识别的引用 {%s}" % tok)
        sheet, col, nth, key, total = m.groups()
        t = self.tables.get(sheet)
        if not t:
            raise KeyError("找不到工作表或表格：%s" % sheet)
        if col not in t["cols"]:
            raise KeyError("“%s”中没有列：%s" % (sheet, col))
        c = t["cols"][col]
        s = qsheet(t["sheet"])
        if nth:
            return s + absref(c, t["first"] + int(nth) - 1)
        if key is not None:
            if key not in t["keys"]:
                raise KeyError("“%s”第一列中没有“%s”" % (sheet, key))
            return s + absref(c, t["keys"][key])
        if total:
            if not t["total"]:
                raise KeyError("“%s”没有合计行" % sheet)
            return s + absref(c, t["total"])
        if t.get("tname"):
            return sref(t["tname"], col)
        return s + absref(c, t["first"]) + ":" + absref(c, t["last"])

    def resolve_all(self):
        for ws, coord, raw in self.pending:
            try:
                ws[coord].value = TOKEN.sub(lambda m: self.resolve_token(m.group(1)), raw)
            except KeyError as e:
                self.errors.append("%s!%s 公式 %s：%s" % (ws.title, coord, raw, e.args[0]))
        return self.errors


def is_formula(v):
    return isinstance(v, str) and v.startswith("=")


_SREF_SPECIAL = re.compile(r"[\s,:.\[\]#'{}$^&*+=\-<>/\"!@%~`()]")


def sref(tname, col, this_row=False):
    """结构化引用：tbl[列]；列名含特殊字符时用双中括号并转义 ' [ ] #。
    this_row=True 时为“本行”写法 tbl[[#This Row],[列]]（用于表格的计算列模板）。"""
    esc = re.sub(r"(['\[\]#])", r"'\1", col)
    if this_row:
        return "%s[[#This Row],[%s]]" % (tname, esc)
    if _SREF_SPECIAL.search(col):
        return "%s[[%s]]" % (tname, esc)
    return "%s[%s]" % (tname, esc)
