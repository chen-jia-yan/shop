# -*- coding: utf-8 -*-
"""
仪表盘：指标卡 · 智能洞察 · 趋势 · 热力 · 分组进度 · 分布 · 异常清单。

全部由公式驱动（引用数据表的结构化引用），改了原始数据打开即重算；图表引用仪表盘右侧的“图表数据”区，
该区也全是公式。用到的都是 Excel 原生元素：渐变色条、圆环图、组合图、色阶、数据条、条件格式。

{"name": "仪表盘", "from": "数据", "title": "投诉处理驾驶舱",
 "kpis": [{"label": "未结案", "value": "=COUNTIFS({数据.状态},\"<>已结案\")", "unit": "件", "format": "int",
           "note": "=\"待处理 \"&COUNTIFS({数据.状态},\"待处理\")", "tone": "flat|up|down|bad",
           "ring": "=…（0-1 的占比，可选）", "alert": false}],
 "insights": [{"text": "=\"超时未结 \"&COUNTIFS({数据.时效},\"超时\")&\" 件\"", "level": "bad"}],
 "trend": {"title": "…", "periods": "auto" 或 ["2026-09", …], "date": "受理日期",
           "bars": [{"name": "受理", "date": "受理日期"}, {"name": "结案", "date": "结案日期"}],
           "line": {"name": "平均处理天数", "avg": "处理天数", "date": "结案日期"}},
 "heatmap": {"title": "…", "rows": "承办部门", "cols": "投诉类别"},
 "group": {"title": "…", "by": "承办部门", "measures": [{"name": "未结", "agg": "count", "where": [["状态", "<>已结案"]],
           "alert": false, "databar": true}, {"name": "平均天数", "agg": "avg", "field": "处理天数", "format": "ratio"}]},
 "breakdown": {"title": "…", "by": "时效", "values": ["超时", "临近", …]},
 "anomalies": {"title": "…", "where": "{@提醒标记}<>\"\"", "columns": […], "sort": "处理时限", "rows": 30}}
"""
import datetime as dt

from openpyxl.chart import BarChart, DoughnutChart, LineChart, Reference
from openpyxl.chart.series import SeriesLabel
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, DataBarRule, FormulaRule
from openpyxl.styles import GradientFill
from openpyxl.utils import get_column_letter

from xl_charts import _axes, _labels, _paint
from xl_data import _grid, field_fmt, level_style, to_date
from xl_helpers import TOKEN, align, border, fill, font, is_formula, put, side, sref
from xl_theme import BRAND, FONTS, FORMATS, ROLE, L, R
from xl_views import list_view

C0, NC = 2, 12                    # 网格：从 B 列起 12 列
CALC = C0 + NC + 3                # 图表数据区起始列


def plan_dash(ctx, d):
    """异常清单是一个内嵌列表视图，需要在数据表上登记辅助列。"""
    a = d.get("anomalies")
    if not a:
        return []
    info = ctx.tables[d["from"]]
    v = {"type": "list", "name": d["name"] + "·" + L("anomaly_title"), "from": d["from"],
         "columns": a.get("columns") or [info["key"], info.get("remind") or info["cols"][1]],
         "where": a.get("where") or ('{@%s}<>""' % info["remind"] if info.get("remind") else None),
         "sort": a.get("sort"), "rows": a.get("rows") or R("anomaly_rows")}
    d["_anom"] = v
    return [v]


class Dash(object):
    def __init__(self, ctx, ws, d):
        self.ctx, self.ws, self.d, self.st = ctx, ws, d, ctx.st
        self.info = ctx.tables[d["from"]]
        self.T = self.info["tname"]
        self.calc_r = 3                         # 图表数据区下一可用行
        self.charts = []

    # -- 写单元格（含 {表.列} 的公式延后统一解析） --
    def w(self, r, c, v, f=None, fl=None, al=None, bd=None, fmt=None):
        cell = put(self.ws, r, c, v, f, fl, al, bd, fmt)
        if is_formula(v) and TOKEN.search(v):
            self.ctx.reg.defer(self.ws, cell.coordinate, v)
        return cell

    def col(self, name):
        if name not in self.info["cols"]:
            raise KeyError("仪表盘引用了不存在的字段：%s" % name)
        return sref(self.T, name)

    def crit(self, where):
        return "".join(',%s,"%s"' % (self.col(f), str(c).replace('"', '""')) for f, c in (where or []))

    def bg(self, r0, r1):
        for r in range(r0, r1 + 1):
            for c in range(1, C0 + NC + 1):
                cell = self.ws.cell(row=r, column=c)
                if getattr(cell.fill, "fill_type", "gradient") is None:      # 只填空白格，不覆盖面板和渐变色条
                    cell.fill = fill(self.st["head_bg"])

    def panel(self, r0, r1, c0, c1, title, note=None, tag=None):
        """白底面板：标题行 + 说明行，四周细边框。返回内容起始行。"""
        st = self.st
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                self.ws.cell(row=r, column=c).fill = fill(BRAND["white"])
                self.ws.cell(row=r, column=c).border = border(
                    top=side(st["grid"]) if r == r0 else None, bottom=side(st["grid"]) if r == r1 else None,
                    left=side(st["grid"]) if c == c0 else None, right=side(st["grid"]) if c == c1 else None)
        self.w(r0, c0, title + ("　" + tag if tag else ""), font(11, True, BRAND["ink"]), al=align("left", "center"))
        if note:
            self.w(r0 + 1, c0, note, font(9, False, BRAND["muted"]), al=align("left", "center"))
        return r0 + (2 if note else 1)

    # -- 图表数据区 --
    def calc_block(self, title, header, rows):
        """写一块图表数据；返回 (首数据行, 末行)。rows: [[值或公式, …]]"""
        r = self.calc_r
        self.w(r, CALC, title, font(9, True, BRAND["muted"]))
        for j, h in enumerate(header):
            self.w(r + 1, CALC + j, h, font(9, True, BRAND["ink_soft"]), fill(ROLE["aux_bg"]))
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                self.w(r + 2 + i, CALC + j, v, font(9, False, ROLE["fx_fg"], FONTS["num"]),
                       fmt=FORMATS["ratio"] if j and isinstance(v, str) and "AVERAGE" in v else None)
        self.calc_r = r + 3 + len(rows)
        return r + 2, r + 1 + len(rows)

    def run(self):
        ws, st, d = self.ws, self.st, self.d
        ws.sheet_view.showGridLines = False
        ws.column_dimensions[get_column_letter(1)].width = 2
        for c in range(C0, C0 + NC):
            ws.column_dimensions[get_column_letter(c)].width = 11.5
        ws.column_dimensions[get_column_letter(C0 + NC)].width = 2
        # 标题行
        today = '"&TEXT(TODAY(),"yyyy-mm-dd")&"'
        self.w(1, C0, d.get("title") or d["name"], font(15, True, st["title"]), al=align("left", "center"))
        self.w(1, C0 + 4, '="%s"' % L("dash_live", date=today).replace('""&', "").replace('&""', ""),
               font(9.5, True, st["accent_dark"], FONTS["mono"]), al=align("left", "center"))
        self.w(1, C0 + 8, '="%s"' % L("dash_ref", src=d["from"], n='"&ROWS(%s)&"' % self.col(self.info["key"])),
               font(9, False, BRAND["muted"]), al=align("left", "center"))
        ws.row_dimensions[1].height = 30
        r = 3
        r = self.kpis(r)
        r = self.row_block(r, [("insights", 4), ("trend", 8)])
        r = self.row_block(r, [("heatmap", 6), ("group", 6)])
        r = self.row_block(r, [("anomalies", 7), ("breakdown", 5)])
        r = self.p_charts(r, self.d.get("charts") or [])
        self.bg(1, r)
        for ch, anchor in self.charts:
            ws.add_chart(ch, anchor)
        if self.calc_r > 3:
            self.w(2, CALC, L("chart_note"), font(9, True, BRAND["muted"]))
        ws.sheet_properties.tabColor = st["tab_dash"]
        from xl_helpers import print_setup
        print_setup(ws, landscape=True)
        ws.print_area = "A1:%s%d" % (get_column_letter(C0 + NC), r)

    # -- 指标卡：渐变色条 + 名称 + 数值 + 说明，可带圆环 --
    def kpis(self, r):
        ks = self.d.get("kpis") or []
        if not ks:
            return r
        per = min(6, len(ks))
        span = NC // per
        for i, k in enumerate(ks):
            row = r + (i // per) * 6
            c = C0 + (i % per) * span
            c1 = c + span - 1
            alert = k.get("alert")
            accent, second = (ROLE["bad_fg"], BRAND["warn"]) if alert else (self.st["accent"], self.st["second"])
            self.ws.row_dimensions[row].height = 4
            for cc in range(c, c1 + 1):
                self.ws.cell(row=row, column=cc).fill = GradientFill(type="linear", degree=0,
                                                                     stop=("FF" + accent, "FF" + second))
                for rr in range(row + 1, row + 4):
                    self.ws.cell(row=rr, column=cc).fill = fill(BRAND["white"])
                    self.ws.cell(row=rr, column=cc).border = border(
                        bottom=side(self.st["grid"]) if rr == row + 3 else None,
                        left=side(self.st["grid"]) if cc == c else None, right=side(self.st["grid"]) if cc == c1 else None)
            self.w(row + 1, c, k["label"], font(9.5, False, BRAND["muted"]), al=align("left", "bottom", indent=1))
            fmt = FORMATS.get(k.get("format"), k.get("format"))
            self.w(row + 2, c, k["value"], font(22, True, ROLE["bad_fg"] if alert else BRAND["ink"], FONTS["num"]),
                   al=align("left", "center", indent=1), fmt=fmt)
            if k.get("unit") and not (fmt and ";" in fmt):            # 单位写进数字格式，数值仍可参与计算
                self.ws.cell(row=row + 2, column=c).number_format = '%s "%s"' % (fmt or "General", k["unit"])
            tone = {"up": ROLE["bad_fg"], "bad": ROLE["bad_fg"], "down": ROLE["good_fg"], "good": ROLE["good_fg"]}.get(
                k.get("tone"), BRAND["muted"])
            if k.get("note"):
                self.w(row + 3, c, k["note"], font(9, True, tone), al=align("left", "top", indent=1))
            self.ws.row_dimensions[row + 1].height = 18
            self.ws.row_dimensions[row + 2].height = 34
            self.ws.row_dimensions[row + 3].height = 20
            if k.get("ring") and span >= 2:
                a, b = self.calc_block(L("chart_note") + "·" + k["label"], [k["label"], ""],
                                       [[k["ring"]], ["=MAX(0,1-%s%d)" % (get_column_letter(CALC), self.calc_r + 2)]])
                self.ring(a, b, accent, ROLE["bad_bg"] if alert else self.st["accent_pale"],
                          "%s%d" % (get_column_letter(c1), row + 1))
        rows = (len(ks) - 1) // per + 1
        return r + rows * 6

    def ring(self, a, b, on, off, anchor):
        ch = DoughnutChart(holeSize=68)
        ch.add_data(Reference(self.ws, min_col=CALC, min_row=a, max_row=b), titles_from_data=False)
        s = ch.series[0]
        from openpyxl.chart.marker import DataPoint
        s.dPt = [DataPoint(idx=0, spPr=GraphicalProperties(solidFill=on, ln=LineProperties(noFill=True))),
                 DataPoint(idx=1, spPr=GraphicalProperties(solidFill=off, ln=LineProperties(noFill=True)))]
        ch.legend = None
        ch.width, ch.height = 1.9, 1.9
        self.charts.append((ch, anchor))

    def row_block(self, r, parts):
        """一行放两个面板；返回下一行。"""
        h = 0
        c = C0
        for kind, width in parts:
            spec = self.d.get(kind)
            if not spec:
                continue
            h = max(h, getattr(self, "p_" + kind)(r, c, c + width - 1, spec))
            c += width
        return r + h + 1 if h else r

    # -- 智能洞察：每句话由公式拼成 --
    def p_insights(self, r, c0, c1, items):
        items = items[:R("insight_max")]
        r1 = r + 2 + len(items) * 2 + 1
        r1 = max(r1, r + 15)
        top = self.panel(r, r1, c0, c1, L("insights_title"), L("insights_note"))
        for i, it in enumerate(items):
            rr = top + i * 2
            lv = it.get("level")
            badge = ROLE["bad_fg"] if lv == "bad" else (ROLE["warn_fg"] if lv == "warn" else self.st["accent"])
            self.w(rr, c0, str(i + 1), font(9, True, BRAND["white"], FONTS["num"]), fill(badge), align("center", "center"))
            self.ws.merge_cells(start_row=rr, start_column=c0 + 1, end_row=rr + 1, end_column=c1)
            self.w(rr, c0 + 1, it["text"], font(10, False, BRAND["ink"]), fill(BRAND["white"]), align("left", "center", True))
            self.ws.row_dimensions[rr].height = 18
        return r1 - r + 1

    # -- 趋势：组合图（柱 = 件数，折线 = 平均值，右轴） --
    def p_trend(self, r, c0, c1, t):
        periods = t.get("periods") or "auto"
        if periods == "auto":
            periods = self._months(t.get("date") or t["bars"][0]["date"])
        head = [""] + [b["name"] for b in t["bars"]] + ([t["line"]["name"]] if t.get("line") else [])
        rows = []
        for p in periods:
            y, m = (int(x) for x in p.split("-")[:2])
            lo, hi = "DATE(%d,%d,1)" % (y, m), "DATE(%d,%d,1)" % (y, m + 1)
            row = [L("month", y=y, m=m)]
            for b in t["bars"]:
                row.append('=COUNTIFS(%s,">="&%s,%s,"<"&%s%s)' % (self.col(b["date"]), lo, self.col(b["date"]), hi,
                                                                   self.crit(b.get("where"))))
            if t.get("line"):
                ln = t["line"]
                row.append('=IFERROR(AVERAGEIFS(%s,%s,">="&%s,%s,"<"&%s%s),NA())' % (
                    self.col(ln["avg"]), self.col(ln["date"]), lo, self.col(ln["date"]), hi, self.crit(ln.get("where"))))
            rows.append(row)
        a, b = self.calc_block(t.get("title") or "trend", head, rows)
        r1 = r + 15
        self.panel(r, r1, c0, c1, t.get("title") or "", t.get("note"))
        bar = BarChart()
        bar.type, bar.grouping, bar.overlap, bar.gapWidth = "col", "clustered", -10, 80
        for j, s in enumerate(t["bars"]):
            ref = Reference(self.ws, min_col=CALC + 1 + j, min_row=a - 1, max_row=b)
            bar.add_data(ref, titles_from_data=True)
            _paint(bar.series[-1], self.st["palette"][j % len(self.st["palette"])])
        bar.set_categories(Reference(self.ws, min_col=CALC, min_row=a, max_row=b))
        bar.dataLabels = _labels()
        _axes(bar)
        if t.get("line"):
            ln = LineChart()
            ln.add_data(Reference(self.ws, min_col=CALC + 1 + len(t["bars"]), min_row=a - 1, max_row=b),
                        titles_from_data=True)
            _paint(ln.series[0], self.st["deep"], line=True)
            ln.y_axis.axId = 200
            ln.y_axis.crosses = "max"
            ln.y_axis.majorGridlines = None
            _axes(ln, FORMATS["ratio"])
            bar += ln
        bar.legend.position = "b"
        bar.width = (c1 - c0 + 1) * 2.25
        bar.height = 6.6
        self.charts.append((bar, "%s%d" % (get_column_letter(c0), r + 2)))
        return r1 - r + 1

    def _months(self, field):
        from xl_data import _row_values
        ds = [to_date(_row_values(self.info["spec"], x).get(field)) for x in self.info["spec"].get("rows") or []]
        ds = [x for x in ds if isinstance(x, dt.date)]
        if not ds:
            return []
        y, m = min(ds).year, min(ds).month
        out = []
        while (y, m) <= (max(ds).year, max(ds).month):
            out.append("%d-%02d" % (y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    def _values(self, field, given=None):
        if given:
            return given
        f = self.info["fields"].get(field) or {}
        if f.get("options_ref"):
            return self.ctx.options[f["options_ref"]]
        from xl_data import _row_values
        seen = []
        for x in self.info["spec"].get("rows") or []:
            v = _row_values(self.info["spec"], x).get(field)
            if v not in (None, "") and v not in seen:
                seen.append(v)
        if not seen:
            raise KeyError("仪表盘按“%s”分组时取不到取值（公式字段请写 values / row_values / col_values）" % field)
        return seen

    # -- 热力：两个字段交叉计数 + 色阶 --
    def p_heatmap(self, r, c0, c1, h):
        rows = self._values(h["rows"], h.get("row_values"))
        cols = self._values(h["cols"], h.get("col_values"))[:min(R("heat_max_cols"), c1 - c0)]
        top = self.panel(r, r + 3 + len(rows), c0, c1, h.get("title") or L("heat_title", rows=h["rows"], cols=h["cols"]),
                         L("heat_note"), tag="")
        for j, v in enumerate(cols, 1):
            self.w(top, c0 + j, v, font(9, False, BRAND["muted"]), al=align("center", "center", True))
        self.ws.row_dimensions[top].height = 28
        for i, rv in enumerate(rows, 1):
            rr = top + i
            self.w(rr, c0, rv, font(9.5, False, BRAND["ink_soft"]), al=align("left", "center"))
            for j, cv in enumerate(cols, 1):
                self.w(rr, c0 + j, '=COUNTIFS(%s,$%s%d,%s,%s$%d)' % (
                    self.col(h["rows"]), get_column_letter(c0), rr, self.col(h["cols"]), get_column_letter(c0 + j), top),
                    font(10, True, BRAND["ink"], FONTS["num"]), al=align("center", "center"),
                    bd=border(top=side(BRAND["white"], "medium"), bottom=side(BRAND["white"], "medium"),
                              left=side(BRAND["white"], "medium"), right=side(BRAND["white"], "medium")),
                    fmt='0;-0;"·"')
            self.ws.row_dimensions[rr].height = 22
        rng = "%s%d:%s%d" % (get_column_letter(c0 + 1), top + 1, get_column_letter(c0 + len(cols)), top + len(rows))
        self.ws.conditional_formatting.add(rng, ColorScaleRule(
            start_type="num", start_value=0, start_color="FF" + BRAND["white"],
            mid_type="percentile", mid_value=50, mid_color="FF" + self.st["accent_light"],
            end_type="max", end_color="FF" + self.st["heat_high"]))
        return len(rows) + 4

    # -- 分组进度：按某字段分组的多个统计 --
    def p_group(self, r, c0, c1, g):
        vals = self._values(g["by"], g.get("values"))
        ms = g["measures"]
        top = self.panel(r, r + 3 + len(vals), c0, c1, g.get("title") or g["by"], g.get("note"))
        heads = [g["by"]] + [m["name"] for m in ms]
        for j, hname in enumerate(heads):
            self.w(top, c0 + j, hname, font(9.5, True, BRAND["ink"]), fill(self.st["head_bg"]),
                   align("left" if j == 0 else "right", "center"), border(bottom=side(self.st["head_line"], "medium")))
        for i, v in enumerate(vals, 1):
            rr = top + i
            self.w(rr, c0, v, font(10), bd=_grid(self.st))
            for j, m in enumerate(ms, 1):
                base = ',%s,$%s%d' % (self.col(g["by"]), get_column_letter(c0), rr)
                if m.get("agg") == "avg":
                    fx = '=IFERROR(AVERAGEIFS(%s%s%s),"—")' % (self.col(m["field"]), base, self.crit(m.get("where")))
                elif m.get("agg") == "sum":
                    fx = '=SUMIFS(%s%s%s)' % (self.col(m["field"]), base, self.crit(m.get("where")))
                else:
                    fx = '=COUNTIFS(%s%s)' % (base.lstrip(","), self.crit(m.get("where")))
                self.w(rr, c0 + j, fx, font(10, False, BRAND["ink"], FONTS["num"]), al=align("right"), bd=_grid(self.st),
                       fmt=FORMATS.get(m.get("format"), m.get("format")))
        for j, m in enumerate(ms, 1):
            L_ = get_column_letter(c0 + j)
            rng = "%s%d:%s%d" % (L_, top + 1, L_, top + len(vals))
            if m.get("databar"):
                self.ws.conditional_formatting.add(rng, DataBarRule(start_type="num", start_value=0, end_type="max",
                                                                    color="FF" + self.st["accent_mid"], showValue=True))
            if m.get("alert"):
                fl, ft = level_style("bad")
                self.ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], fill=fl, font=ft))
        return len(vals) + 4

    # -- 分布：横向条形图 --
    def p_breakdown(self, r, c0, c1, b):
        vals = self._values(b["by"], b.get("values"))
        a, z = self.calc_block(b.get("title") or b["by"], [b["by"], ""],
                               [[v, '=COUNTIFS(%s,"%s"%s)' % (self.col(b["by"]), v, self.crit(b.get("where")))] for v in vals])
        r1 = r + max(9, len(vals) + 5)
        self.panel(r, r1, c0, c1, b.get("title") or b["by"], b.get("note"))
        ch = BarChart()
        ch.type, ch.gapWidth = "bar", 60
        ch.add_data(Reference(self.ws, min_col=CALC + 1, min_row=a, max_row=z), titles_from_data=False)
        ch.set_categories(Reference(self.ws, min_col=CALC, min_row=a, max_row=z))
        _paint(ch.series[0], self.st["accent"])
        ch.dataLabels = _labels()
        ch.legend = None
        ch.x_axis.scaling.orientation = "maxMin"
        _axes(ch)
        ch.width, ch.height = (c1 - c0 + 1) * 2.25, max(4.2, len(vals) * 0.9 + 1.6)
        self.charts.append((ch, "%s%d" % (get_column_letter(c0), r + 2)))
        return r1 - r + 1

    # -- 异常清单：内嵌列表视图，主键可跳回原始记录 --
    def p_anomalies(self, r, c0, c1, a):
        v = self.d["_anom"]
        n = v["rows"]
        top = self.panel(r, r + 2 + n, c0, c1, a.get("title") or L("anomaly_title"), a.get("note"))
        v["columns"] = v["columns"][:c1 - c0]                      # 面板宽度内放得下的列
        list_view(self.ctx, self.ws, v, start_row=top, title=False, start_col=c0)
        return n + 3


def dashboard(ctx, ws, d):
    Dash(ctx, ws, d).run()


def _p_charts(self, r, charts):
    """仪表盘里引用数据表的原生图表（柱、条、线、组合、饼、环形），每行两个面板。"""
    for i in range(0, len(charts), 2):
        h = 16
        for j, spec in enumerate(charts[i:i + 2]):
            c0 = C0 + j * 6
            self.panel(r, r + h, c0, c0 + 5, spec.get("title", ""), spec.get("note"))
            sp = dict(spec)
            sp["title"] = None                     # 标题已在面板上
            sp.setdefault("anchor", "%s%d" % (get_column_letter(c0), r + 2))
            sp.setdefault("width", 6 * 2.25)
            sp.setdefault("height", 6.8)
            self.ctx.charts.append((self.ws.title, sp))
        r += h + 2
    return r


Dash.p_charts = _p_charts
