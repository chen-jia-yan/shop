# -*- coding: utf-8 -*-
"""
Excel 原生图表（在 Excel 里可直接改数据、改样式）。所有图表在全部工作表写完后统一生成，
因此看板可以引用排在后面的明细表。

图表 spec（写在任意工作表的 charts 列表中）：
{
  "type": "col | bar | line | combo | stacked | area | pie | donut",
  "title": "（写结论，不写话题）",
  "data": "（数据来源工作表名，必须是 table 类型）",
  "categories": "（分类列名）",
  "series": ["（数值列名）"],          # 一个或多个
  "secondary": ["（右轴列名）"],       # combo 专用：右轴折线
  "rows": [1, 5],                       # 可选：只画第 1-5 个数据行
  "highlight": "max | min | 分类名",    # 可选：单系列柱/条形图中高亮一项，其余灰色
  "number_format": "0.0%",              # 可选：主轴数字格式
  "labels": true,                       # 是否显示数据标签，默认 true
  "anchor": "H4", "width": 16, "height": 8   # 位置与尺寸（cm）
}
"""
from openpyxl.chart import AreaChart, BarChart, DoughnutChart, LineChart, PieChart, Reference
from openpyxl.chart.data_source import NumFmt
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import DataPoint, Marker
from openpyxl.chart.series import SeriesLabel
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties

from xl_theme import BRAND, CHART_PALETTE, ROLE


def _labels(show_val=True, show_pct=False, pos=None):
    d = DataLabelList()
    d.showVal = show_val
    d.showPercent = show_pct
    d.showSerName = False
    d.showCatName = False
    d.showLegendKey = False
    if pos:
        d.position = pos
    return d


def _axes(ch, fmt=None):
    for ax in (ch.x_axis, ch.y_axis):
        try:
            ax.delete = False          # openpyxl 3.1 默认可能隐藏坐标轴，显式打开
        except AttributeError:
            pass
    try:
        if ch.y_axis.majorGridlines is not None:
            ch.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill=BRAND["grid"]))
    except AttributeError:
        pass
    if fmt:
        ch.y_axis.numFmt = NumFmt(formatCode=fmt, sourceLinked=False)


def _paint(series, color, line=False):
    """显式构造填充、线条和标记对象（不依赖 openpyxl 是否预先创建了它们）。"""
    if line:
        series.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill=color, w=28575))
        series.marker = Marker(symbol="circle", size=7)
        series.marker.graphicalProperties = GraphicalProperties(
            solidFill=BRAND["white"], ln=LineProperties(solidFill=color, w=19050))
        series.smooth = False
    else:
        series.graphicalProperties = GraphicalProperties(solidFill=color,
                                                         ln=LineProperties(solidFill=color))


def _point(idx, color, line=None):
    return DataPoint(idx=idx, spPr=GraphicalProperties(solidFill=color,
                                                      ln=LineProperties(solidFill=line or BRAND["white"])))


def _values(ws, col, r0, r1):
    out = []
    for r in range(r0, r1 + 1):
        v = ws.cell(row=r, column=col).value
        out.append(v if isinstance(v, (int, float)) else None)
    return out


def build_chart(wb, reg, spec, errors):
    src = spec.get("data")
    t = reg.tables.get(src)
    if not t:
        errors.append("图表“%s”：数据表 %s 不存在或不是 table 类型" % (spec.get("title", ""), src))
        return None
    ws = wb[t.get("sheet") or src]
    first, last = t["first"], t["last"]
    if spec.get("rows"):
        a, b = spec["rows"]
        first, last = t["first"] + a - 1, t["first"] + b - 1
    if last < first:
        errors.append("图表“%s”：没有数据行" % spec.get("title", ""))
        return None
    cols = t["cols"]
    for name in [spec.get("categories")] + spec.get("series", []) + spec.get("secondary", []):
        if name not in cols:
            errors.append("图表“%s”：数据表 %s 中没有列 %s" % (spec.get("title", ""), src, name))
            return None
    cats = Reference(ws, min_col=cols[spec["categories"]], min_row=first, max_row=last)
    kind = spec.get("type", "col")
    show = spec.get("labels", True)

    if kind in ("pie", "donut"):
        ch = DoughnutChart(holeSize=55) if kind == "donut" else PieChart()
        name = spec["series"][0]
        ch.add_data(Reference(ws, min_col=cols[name], min_row=first, max_row=last), titles_from_data=False)
        ch.set_categories(cats)
        s = ch.series[0]
        s.tx = SeriesLabel(v=name)
        for i in range(last - first + 1):
            s.dPt.append(_point(i, CHART_PALETTE[i % len(CHART_PALETTE)]))
        if show:
            s.dLbls = _labels(show_val=False, show_pct=True)
        ch.legend.position = "r"
    elif kind == "line" or kind == "area":
        ch = LineChart() if kind == "line" else AreaChart()
        for i, name in enumerate(spec["series"]):
            ch.add_data(Reference(ws, min_col=cols[name], min_row=first, max_row=last), titles_from_data=False)
            s = ch.series[-1]
            s.tx = SeriesLabel(v=name)
            _paint(s, CHART_PALETTE[i % len(CHART_PALETTE)], line=(kind == "line"))
            if show and kind == "line":
                s.dLbls = _labels(pos="t")
        ch.set_categories(cats)
        _axes(ch, spec.get("number_format"))
    else:
        ch = BarChart()
        ch.type = "bar" if kind == "bar" else "col"
        ch.gapWidth = 60
        if kind == "stacked":
            ch.grouping = "stacked"
            ch.overlap = 100
        for i, name in enumerate(spec["series"]):
            ch.add_data(Reference(ws, min_col=cols[name], min_row=first, max_row=last), titles_from_data=False)
            s = ch.series[-1]
            s.tx = SeriesLabel(v=name)
            _paint(s, CHART_PALETTE[i % len(CHART_PALETTE)])
        ch.set_categories(cats)
        hi = spec.get("highlight")
        if hi is not None and len(spec["series"]) == 1:
            s = ch.series[0]
            vals = _values(ws, cols[spec["series"][0]], first, last)
            keys = [ws.cell(row=r, column=cols[spec["categories"]]).value for r in range(first, last + 1)]
            idx = None
            nums = [v for v in vals if v is not None]
            if hi == "max" and nums:
                idx = vals.index(max(nums))
            elif hi == "min" and nums:
                idx = vals.index(min(nums))
            elif hi in keys:
                idx = keys.index(hi)
            if idx is not None:
                # 只有确定了高亮项才把其余柱子改成灰色；公式列算不出最大值时保持品牌色
                _paint(s, ROLE["grey_bar"])
                s.dPt.append(_point(idx, BRAND["primary"], BRAND["primary"]))
            else:
                errors.append("图表“%s”：highlight=%s 无法确定（数据是公式时请直接写分类名）"
                              % (spec.get("title", ""), hi))
        if show:
            for s in ch.series:
                s.dLbls = _labels(pos="outEnd" if kind != "stacked" else "ctr")
        if kind == "bar":
            ch.x_axis.scaling.orientation = "maxMin"   # 条形图第一项在最上面
        _axes(ch, spec.get("number_format"))
        if kind == "combo" or spec.get("secondary"):
            ln = LineChart()
            for j, name in enumerate(spec.get("secondary", [])):
                ln.add_data(Reference(ws, min_col=cols[name], min_row=first, max_row=last),
                            titles_from_data=False)
                s = ln.series[-1]
                s.tx = SeriesLabel(v=name)
                _paint(s, CHART_PALETTE[(j + 1) % len(CHART_PALETTE)], line=True)
                if show:
                    s.dLbls = _labels(pos="t")
            ln.y_axis.axId = 200
            ln.y_axis.crosses = "max"
            try:
                ln.y_axis.delete = False
                ln.y_axis.majorGridlines = None
            except AttributeError:
                pass
            if spec.get("secondary_format"):
                ln.y_axis.numFmt = NumFmt(formatCode=spec["secondary_format"], sourceLinked=False)
            ch += ln

    ch.title = spec.get("title")
    n_series = len(spec.get("series", [])) + len(spec.get("secondary", []))
    if kind not in ("pie", "donut"):
        if n_series <= 1:
            ch.legend = None
        else:
            ch.legend.position = "b"
    ch.width = spec.get("width", 16)
    ch.height = spec.get("height", 8)
    return ch


def place_charts(wb, reg, chart_jobs):
    """chart_jobs: [(工作表名, spec)]；返回错误列表。"""
    errors = []
    for sheet, spec in chart_jobs:
        ch = build_chart(wb, reg, spec, errors)
        if ch is not None:
            wb[sheet].add_chart(ch, spec.get("anchor", "H4"))
    return errors
