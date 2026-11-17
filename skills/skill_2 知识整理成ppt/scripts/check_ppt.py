#!/usr/bin/env python3
"""检查生成的 PPT：页数、【待补充】位置、缺演讲备注的页、文字过多的页。

用法:
    python check_pptx.py output.pptx
退出码: 0 = 无问题；1 = 有需要处理的问题

依赖: python-pptx
"""
import json
import sys

try:
    from pptx import Presentation
except ModuleNotFoundError:
    sys.exit("缺少依赖 python-pptx，请先执行: pip install python-pptx")

MAX_CHARS = 220   # 单页文字超过这个数，通常意味着内容过密


def slide_texts(slide):
    texts = []
    for shp in slide.shapes:
        if shp.has_text_frame:
            texts.append(shp.text_frame.text)
        if getattr(shp, "has_table", False) and shp.has_table:
            for row in shp.table.rows:
                for cell in row.cells:
                    texts.append(cell.text)
    return [t for t in texts if t.strip()]


def check(path):
    prs = Presentation(path)
    total = len(prs.slides)
    pages, problems = [], False
    for i, slide in enumerate(prs.slides, 1):
        texts = slide_texts(slide)
        joined = "".join(texts)
        chars = len(joined.replace("\n", ""))
        notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        info = {"page": i, "chars": chars,
                "title": (texts[0][:30] if texts else "")}
        issues = []
        n_todo = joined.count("【待补充")
        if n_todo:
            issues.append(f"{n_todo} 处【待补充】")
        if not notes and i not in (1, total):
            issues.append("缺演讲备注")
        if chars > MAX_CHARS:
            issues.append(f"文字较多（{chars} 字），建议精简或拆页")
        if issues:
            info["issues"] = issues
            problems = True
        pages.append(info)
    return {"file": path, "slides": total, "pages": pages}, problems


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    result, problems = check(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if problems else 0)
