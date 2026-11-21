# -*- coding: utf-8 -*-
"""
变更影响分析 —— 第 1 步：新旧版本比对

用法：
  python diff_docs.py <旧版> <新版> -o changes.json
                      [--doc-name 文档名称] [--old-label 旧版本号] [--new-label 新版本号]
                      [--effective-date YYYY-MM-DD] [--source 变更来源] [--config 额外配置]

支持 .docx / .md / .txt / .json（kb-to-word 内容格式或章节列表）/ .pdf（需 pdfplumber）。

算法（逻辑严谨、可追溯）：
  1. 两个版本都抽取成“块”（标题、段落、表格行），保留章节路径与条款号。
  2. 块级对齐：先按全文顺序做最长公共子序列，相同的块视为未变；
     不同的区间里再按相似度两两配对（同条款号加分、类型必须一致），配上的为“修改”，
     配不上的为“删除 / 新增”。
  3. 全局二次配对：把各区间剩下的删除块和新增块再配一次，找出“移动”与“移动并修改”。
  4. 每处修改做字词级差异，并识别信号（数值、日期、义务表述、否定词、适用范围、术语）。
  5. 只改了标点空格、或相似度很高且没有任何实质信号的，标为“措辞调整”。
  6. 比对盲区打上复核提示（review_flags）：可能的段落拆分 / 合并、同义改写、表格列结构变化；
     图片、公式、扫描页计数写进 meta.warnings。是否真有问题由模型读原文判断（见 reference/methods.md 第 4 节）。
退出码：0 成功；2 输入有误。
"""
import argparse
import os
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _tap import add_cli_args, configure     # noqa: E402

import extract                                # noqa: E402
import signals                                # noqa: E402
from ci_common import (L, R, bare, clip, fmt_date, imp, parse_date, save_json,  # noqa: E402
                       today)

PAIR_CAP = 250000          # 单个区间两两比较的上限，超过时先用快速相似度筛选


def _sim(a, b):
    sm = SequenceMatcher(None, a["norm"], b["norm"], autojunk=False)
    if sm.real_quick_ratio() < 0.3 or sm.quick_ratio() < 0.3:
        return 0.0
    s = sm.ratio()
    if a.get("anchor") and a.get("anchor") == b.get("anchor"):
        s += 0.15
    if a.get("path") and a.get("path") == b.get("path"):
        s += 0.05
    return min(s, 1.0)


def pair_blocks(olds, news, threshold):
    """贪心配对：按相似度从高到低，类型一致、超过阈值才配。返回 (pairs, 剩余旧块, 剩余新块)。"""
    cand = []
    if len(olds) * len(news) <= PAIR_CAP:
        for i, a in enumerate(olds):
            for j, b in enumerate(news):
                if a["kind"] != b["kind"]:
                    continue
                s = _sim(a, b)
                if s >= threshold:
                    cand.append((s, i, j))
    else:
        for i, a in enumerate(olds):          # 很大的区间：只和位置相近的块比较
            lo = max(0, int(i * len(news) / max(len(olds), 1)) - 40)
            for j in range(lo, min(len(news), lo + 80)):
                b = news[j]
                if a["kind"] == b["kind"]:
                    s = _sim(a, b)
                    if s >= threshold:
                        cand.append((s, i, j))
    cand.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_a, used_b, pairs = set(), set(), []
    for s, i, j in cand:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((olds[i], news[j], s))
    rest_a = [a for i, a in enumerate(olds) if i not in used_a]
    rest_b = [b for j, b in enumerate(news) if j not in used_b]
    return pairs, rest_a, rest_b


def align(old_blocks, new_blocks):
    th = imp().get("match_threshold", 0.45)
    sm = SequenceMatcher(None, [b["norm"] for b in old_blocks], [b["norm"] for b in new_blocks], autojunk=False)
    mods, dels, adds, same = [], [], [], 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            same += i2 - i1
        elif tag == "delete":
            dels += old_blocks[i1:i2]
        elif tag == "insert":
            adds += new_blocks[j1:j2]
        else:
            p, ra, rb = pair_blocks(old_blocks[i1:i2], new_blocks[j1:j2], th)
            mods += p
            dels += ra
            adds += rb
    # 全局二次配对：跨区间的移动 / 移动并修改
    p2, dels, adds = pair_blocks(dels, adds, th)
    return mods, p2, dels, adds, same


def _path(b):
    p = list(b.get("path") or [])
    if b.get("anchor"):
        p.append(b["anchor"])
    return " / ".join(p)


def _ref(b):
    return {"seq": b["seq"], "kind": b["kind"], "path": b.get("path", []), "anchor": b.get("anchor"),
            "text": b["text"]}


def describe(ch):
    """一句话描述变化：优先写数值“由…调整为…”，其次写增删改的具体文字。"""
    D = L("describe")
    sig = ch["signals"]
    t = ch["type"]
    if t == "added":
        return D["added"].format(text=clip(ch["new"]["text"], 60))
    if t == "removed":
        return D["removed"].format(text=clip(ch["old"]["text"], 60))
    if t == "moved":
        return D["moved"].format(old_path=_path(ch["old"]) or "—", new_path=_path(ch["new"]) or "—")
    parts = []
    for n in sig["numbers"]:
        if n["old"] and n["new"]:
            parts.append(D["number"].format(ctx=n["ctx"], old=n["old"], new=n["new"]))
    for d in sig["dates"]:
        if d["old"] and d["new"]:
            parts.append(D["date"].format(old=d["old"], new=d["new"]))
    if not parts:
        segs = ch["segments"]
        k = 0
        while k < len(segs) and len(parts) < 3:
            op, txt = segs[k]
            if op == "del" and k + 1 < len(segs) and segs[k + 1][0] == "ins":
                parts.append(D["rep_part"].format(a=clip(txt, 24), b=clip(segs[k + 1][1], 24)))
                k += 2
                continue
            if op == "del" and bare(txt):
                parts.append(D["del_part"].format(t=clip(txt, 30)))
            elif op == "ins" and bare(txt):
                parts.append(D["ins_part"].format(t=clip(txt, 30)))
            k += 1
    text = D["part_sep"].join(parts) if parts else clip(ch["new"]["text"], 60)
    if t == "moved_modified":
        text = D["moved"].format(old_path=_path(ch["old"]) or "—", new_path=_path(ch["new"]) or "—") + \
            D["part_sep"] + text
    return text


def build(old_doc, new_doc):
    mods, moved, dels, adds, same = align(old_doc["blocks"], new_doc["blocks"])
    minor_th = R("similarity_minor")
    move_th = imp().get("move_threshold", 0.95)
    raw = []
    for a, b, s in mods:
        raw.append(("modified", a, b, s))
    for a, b, s in moved:
        raw.append(("moved" if s >= move_th and bare(a["text"]) == bare(b["text"]) else "moved_modified", a, b, s))
    for a in dels:
        raw.append(("removed", a, None, 0.0))
    for b in adds:
        raw.append(("added", None, b, 0.0))
    # 按新版位置排序（删除的块按旧版位置就近插入），报告阅读顺序与文档一致
    total_new = max(len(new_doc["blocks"]), 1)
    total_old = max(len(old_doc["blocks"]), 1)

    def order(x):
        _, a, b, _ = x
        if b is not None:
            return b["seq"] / float(total_new)
        return a["seq"] / float(total_old) + 1e-6
    raw.sort(key=order)

    changes = []
    for n, (t, a, b, s) in enumerate(raw, 1):
        old_t = a["text"] if a else ""
        new_t = b["text"] if b else ""
        segs = signals.segments(old_t, new_t) if (a and b) else ([["del", old_t]] if a else [["ins", new_t]])
        sig = signals.analyse(old_t, new_t, segs)
        punct_only = bool(a and b and bare(old_t) == bare(new_t))
        minor = t in ("modified", "moved_modified") and (punct_only or (s >= minor_th and not signals.has_substance(sig)))
        ch = {"id": "C%02d" % n if len(raw) < 100 else "C%03d" % n,
              "type": t, "kind": (b or a)["kind"],
              "old": _ref(a) if a else None, "new": _ref(b) if b else None,
              "location": _path(b or a), "similarity": round(s, 3) if a and b else None,
              "segments": segs, "signals": sig, "minor": minor, "punct_only": punct_only}
        ch["desc"] = describe(ch)
        changes.append(ch)
    stats = {"old_blocks": len(old_doc["blocks"]), "new_blocks": len(new_doc["blocks"]), "unchanged": same,
             "changes": len(changes), "minor": sum(1 for c in changes if c["minor"]),
             "by_type": {}}
    for c in changes:
        stats["by_type"][c["type"]] = stats["by_type"].get(c["type"], 0) + 1
    flag_for_review(changes)
    stats["flagged"] = sum(1 for c in changes if c.get("review_flags"))
    return changes, stats


# ---------------- 复核提示：比对算法的已知盲区，只提示、不下结论 ----------------
def _contained(part, whole):
    """part 有多大比例的文字出现在 whole 里（按最长公共片段累加）。"""
    a, b = bare(part), bare(whole)
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    return sum(m.size for m in sm.get_matching_blocks()) / float(len(a))


def _table_keys(text):
    return [kv.split("：", 1)[0] for kv in text.split("；") if "：" in kv]


def flag_for_review(changes):
    """给模型的复核提示（review_flags）。脚本只说“这里可能有问题”，由模型读原文判断：
    split_merge  一段拆成两段 / 两段合成一段，会被识别成“修改 + 新增 / 删除”
    paraphrase   否定词、义务词变了但整体相似度很高，可能只是同义改写
    table_shape  表格行的表头（列）变了，整表每行都可能被识别为修改"""
    cf = R("review_flags")
    F = L("flags")
    for i, c in enumerate(changes):
        flags = []
        if c["type"] in ("modified", "moved_modified"):
            lo, hi = max(0, i - cf["split_window"]), min(len(changes), i + cf["split_window"] + 1)
            for d in changes[lo:hi]:
                if d is c:
                    continue
                if d["type"] == "added" and len(bare(d["new"]["text"])) >= cf["split_min_chars"] \
                        and _contained(d["new"]["text"], c["old"]["text"]) >= cf["split_contain"]:
                    flags.append({"flag": "split_merge", "with": d["id"], "note": F["split_merge"]})
                elif d["type"] == "removed" and len(bare(d["old"]["text"])) >= cf["split_min_chars"] \
                        and _contained(d["old"]["text"], c["new"]["text"]) >= cf["split_contain"]:
                    flags.append({"flag": "split_merge", "with": d["id"], "note": F["split_merge"]})
            sig = c["signals"]
            if (sig.get("negation") or sig.get("obligation")) and not sig["numbers"] and not sig["dates"] \
                    and (c.get("similarity") or 0) >= cf["paraphrase_sim"]:
                flags.append({"flag": "paraphrase", "note": F["paraphrase"]})
            if c["kind"] == "table" and _table_keys(c["old"]["text"]) != _table_keys(c["new"]["text"]):
                flags.append({"flag": "table_shape", "note": F["table_shape"]})
        if flags:
            c["review_flags"] = flags
    for c in changes:                          # 双向标记，便于两条一起看
        for f in c.get("review_flags", []):
            if f.get("with"):
                other = next((d for d in changes if d["id"] == f["with"]), None)
                if other is not None and not any(g.get("with") == c["id"] for g in other.get("review_flags", [])):
                    other.setdefault("review_flags", []).append({"flag": f["flag"], "with": c["id"], "note": f["note"]})


def doc_warnings(old_doc, new_doc):
    W = L("doc_warnings")
    out = []
    for side, d in ((L("report.version_old"), old_doc), (L("report.version_new"), new_doc)):
        if d.get("non_text"):
            out.append(W["non_text"].format(side=side, n=d["non_text"]))
        if d.get("empty_pages"):
            out.append(W["low_text"].format(side=side, n=d["empty_pages"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="变更影响分析：新旧版本比对")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--doc-name", help="文档名称，默认取新版文件名")
    ap.add_argument("--old-label", help="旧版本号或日期")
    ap.add_argument("--new-label", help="新版本号或日期")
    ap.add_argument("--effective-date", help="新版生效日期 YYYY-MM-DD，用于计算紧迫度和处置时限")
    ap.add_argument("--source", help="变更来源，如“监管新规”“产品条款修订”“内部制度修订”")
    add_cli_args(ap)
    a = ap.parse_args()
    configure("impact", a)
    old_doc, new_doc = extract.load(a.old), extract.load(a.new)
    changes, stats = build(old_doc, new_doc)
    eff = parse_date(a.effective_date) if a.effective_date else None
    name = a.doc_name or os.path.splitext(new_doc["name"])[0]
    out = {"meta": {"doc": name,
                    "old": {"file": old_doc["name"], "label": a.old_label or old_doc["name"]},
                    "new": {"file": new_doc["name"], "label": a.new_label or new_doc["name"]},
                    "effective_date": fmt_date(eff), "source": a.source or "",
                    "analysed": fmt_date(today()), "stats": stats,
                    "warnings": doc_warnings(old_doc, new_doc)},
           "changes": changes,
           # 全文：供核对分析判断里引用的原文（防止引用不存在的内容）
           "texts": {"old": "\n".join(b["text"] for b in old_doc["blocks"]),
                     "new": "\n".join(b["text"] for b in new_doc["blocks"])}}
    save_json(out, a.output)
    print("已比对：%s → %s" % (old_doc["name"], new_doc["name"]))
    print("旧版 %d 块、新版 %d 块，未变 %d 块；识别变更 %d 处（其中措辞调整 %d 处）"
          % (stats["old_blocks"], stats["new_blocks"], stats["unchanged"], stats["changes"], stats["minor"]))
    print("类型：" + "，".join("%s %d" % (L("change_types").get(k, k), v) for k, v in stats["by_type"].items()))
    if stats["flagged"]:
        print("需要读原文复核的比对 %d 处（review_flags：拆分 / 合并、同义改写、表格结构）" % stats["flagged"])
    for w in out["meta"]["warnings"]:
        print("注意：" + w)
    print("已写入：%s" % a.output)


if __name__ == "__main__":
    main()
