"""交付物：差异汇总.docx 和 差异汇总.xlsx。只放字段、原值、新值、变化和新旧截图，值照抄他的结果。

用到的库：python-docx、openpyxl（pip install -r requirements.txt）。
"""
from __future__ import annotations

import datetime
from pathlib import Path

from common import need

RED = (0xD8, 0x39, 0x31)


def _rows(batch):
    for p in batch["pairs"]:
        for it in p.get("items") or []:
            if not it.get("skip"):
                yield p, it


def _where(it, side):
    page = it.get(f"pageno_{side}") or it.get(f"page_{side}")
    line = it.get(f"line_{side}")
    parts = []
    if page:
        parts.append(f"第 {page} 页")
    if line:
        parts.append(f"行 {line}")
    return " · ".join(parts)


def write_word(path, batch, cfg) -> None:
    need("docx")
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    d = Document()
    sec = d.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, m, Cm(1.6))
    st = d.styles["Normal"]
    st.font.name = "Microsoft YaHei"
    st.font.size = Pt(9.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")

    title = cfg["deliver"]["title"]
    d.add_heading(title, level=0)
    cases = [p for p in batch["pairs"] if p.get("items") is not None]
    n_items = sum(1 for _ in _rows(batch))
    d.add_paragraph(
        f"生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M}　　Case 数：{len(cases)}　　差异：{n_items} 条\n"
        f"baseline：{batch.get('baseline_dir') or '—'}\n新文件：{batch.get('new_dir') or '—'}")
    width = Cm(cfg["deliver"]["image_width_cm"] * 1.45)   # 横向页面，两张图并排

    for p in cases:
        items = [it for it in p["items"] if not it.get("skip")]
        d.add_heading(f"{p['key']}（{len(items)} 处变化）", level=1)
        d.add_paragraph(f"baseline：{Path(p['baseline']).name if p['baseline'] else '—'}　　新文件：{Path(p['new']).name if p['new'] else '—'}")
        if not items:
            d.add_paragraph("没有变化。")
            continue
        for it in items:
            head = d.add_paragraph()
            r = head.add_run(f"{it['id']}　{it['field'] or '（无字段名）'}　{it['kind']}")
            r.bold = True
            if it["change"]:
                head.add_run(f"　　{it['change']}")
            t = d.add_table(rows=3, cols=2)
            t.style = "Table Grid"
            t.cell(0, 0).text = f"原值（baseline）{_where(it, 'old')}"
            t.cell(0, 1).text = f"新值{_where(it, 'new')}"
            for col, seg in ((0, it["seg_old"]), (1, it["seg_new"])):
                para = t.cell(1, col).paragraphs[0]
                if not seg:
                    para.add_run("（无）")
                for txt, ch in seg:
                    run = para.add_run(txt)
                    if ch:
                        run.bold = True
                        run.font.color.rgb = RGBColor(*RED)
            for col, side in ((0, "old"), (1, "new")):
                cell = t.cell(2, col)
                shot = it.get(f"shot_{side}")
                if shot and Path(shot).is_file():
                    cell.paragraphs[0].add_run().add_picture(shot, width=width)
                else:
                    cell.paragraphs[0].add_run("—" if not it[side] else "截图待补").italic = True
            if it.get("shot_note"):
                note = d.add_paragraph("；".join(it["shot_note"]))
                note.runs[0].font.color.rgb = RGBColor(0x8F, 0x62, 0x00)
            d.add_paragraph()
    d.save(str(path))


def write_excel(path, batch, cfg) -> None:
    need("openpyxl")
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill
    from PIL import Image as PILImage

    px = cfg["deliver"]["excel_image_px"]
    wb = Workbook()
    ws = wb.active
    ws.title = "差异"
    head = ["编号", "Case", "字段", "类型", "原值", "新值", "变化", "旧位置", "新位置", "旧截图", "新截图", "备注"]
    ws.append(head)
    fill = PatternFill("solid", fgColor="E1EAFF")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = fill
    widths = [8, 12, 22, 7, 40, 40, 26, 12, 12, px / 7, px / 7, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "C2"
    wrap = Alignment(wrap_text=True, vertical="top")
    r = 1
    for p, it in _rows(batch):
        r += 1
        ws.append([it["id"], p["key"], it["field"], it["kind"], it["old"], it["new"], it["change"],
                   _where(it, "old"), _where(it, "new"), "", "", "；".join(it.get("shot_note") or [])])
        for c in ws[r]:
            c.alignment = wrap
        ws.cell(r, 7).font = Font(color="D83931", bold=True)
        hmax = 0
        for col, side in ((10, "old"), (11, "new")):
            shot = it.get(f"shot_{side}")
            if not (shot and Path(shot).is_file()):
                ws.cell(r, col).value = "截图待补" if it[side] else "—"
                continue
            with PILImage.open(shot) as im:
                w, h = im.size
            img = XLImage(shot)
            img.width, img.height = px, int(h * px / w)
            hmax = max(hmax, img.height)
            ws.add_image(img, f"{ws.cell(r, col).column_letter}{r}")
        ws.row_dimensions[r].height = min(409, max(30, hmax * 0.75 + 6))

    s = wb.create_sheet("汇总")
    s.append(["Case", "baseline", "新文件", "变化条数", "截图待补", "状态"])
    for c in s[1]:
        c.font = Font(bold=True)
        c.fill = fill
    for p in batch["pairs"]:
        items = [it for it in p.get("items") or [] if not it.get("skip")]
        miss = sum(1 for it in items if (it["old"] and not it.get("shot_old")) or (it["new"] and not it.get("shot_new")))
        s.append([p["key"], Path(p["baseline"]).name if p["baseline"] else "", Path(p["new"]).name if p["new"] else "",
                  len(items), miss, p.get("error") or p.get("status") or ""])
    for col, w in zip("ABCDEF", (12, 50, 50, 10, 10, 30)):
        s.column_dimensions[col].width = w
    wb.save(str(path))
