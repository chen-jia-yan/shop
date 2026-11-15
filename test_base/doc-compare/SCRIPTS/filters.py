"""日期、人名过滤：决定“只差日期、只差人名”的内容算不算 difference。

文档对比里所有过滤规则只放在这个文件。同事A 现有脚本里的过滤核实后合并到这里
（template 负责把日期、人名换成占位符，Filter 的其他方法负责收集人名和判断），其他脚本不用改。

规则（详见 references/design.md 第 4 节）：
- 日期：只认配置里 date_formats 的写法（默认“2026 11 20”和“2026-11-20 / 2026/11/20”），
  前后不能紧挨数字、小数点、逗号，而且必须是真实存在的日期，所以 587.85 这类金额不会被当成日期；
- 人名：标签后面的值（被保人姓名 梁柏翰）自动收集，测试数据里的名字从名单文件读取，其余写在配置里；
- 只有换成占位符后两边完全相同，才算“只差日期或人名”。日期变成金额、人名变成别的内容，一定报出来。
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

DATE_PH, NAME_PH = "‹日期›", "‹人名›"
LATIN = re.compile(r"[A-Za-z]")

FILTER_DEFAULTS = {
    "date_formats": [
        r"(?<![\d.,])(?P<y>(?:19|20)\d{2}) (?P<m>0[1-9]|1[0-2]) (?P<d>0[1-9]|[12]\d|3[01])(?![\d.,])",
        r"(?<![\d.,/-])(?P<y>(?:19|20)\d{2})[-/](?P<m>0[1-9]|1[0-2])[-/](?P<d>0[1-9]|[12]\d|3[01])(?![\d.,/-])",
    ],
    "name_labels": ["被保人姓名", "投保人姓名", "受保人姓名", "保單持有人姓名", "保单持有人姓名"],
    "names": [],
    "not_names": [],
    "date_any_shift_labels": [],
    "date_shift_must_match": True,
    # 两边人名行数不同（例如 baseline 1 个名字、新文件 3 个）：ignore 忽略并在附录注明；unsure 交给人看
    "name_count_change": "ignore",
    "suspect_name_pattern": r"^[A-Z][A-Z'\-]{3,29}(?: [A-Z][A-Z'\-]{1,29}){0,3}$",
}


def read_names_file(path: str | None) -> dict:
    """测试数据里的人名：一行一个，或表格另存的 csv（逗号或 Tab 分隔，每格一个名字）。# 开头的行是注释。"""
    out = {}
    if not path:
        return out
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith("#"):
            continue
        for cell in re.split(r"[,\t]", line):
            cell = cell.strip().strip('"')
            if len(cell) >= 2:
                out.setdefault(cell, "测试数据")
    return out


def collect_names(texts: list[str], labels: list[str]) -> dict:
    """标签后面的值当作人名：同一行“被保人姓名 梁柏翰”，或标签单独一行时取下一行。"""
    found = {}
    for i, line in enumerate(texts):
        for lab in labels:
            k = line.find(lab)
            if k < 0:
                continue
            rest = line[k + len(lab):].strip(" \t:：")
            if not rest and i + 1 < len(texts):
                rest = texts[i + 1].strip()
            value = re.split(r"\s{2,}", rest)[0].strip() if rest else ""
            if 2 <= len(value) <= 40 and not re.search(r"\d", value):
                found.setdefault(value, f"标签“{lab}”")
    return found


def name_regex(names):
    parts = []
    for n in sorted(names, key=len, reverse=True):  # 长的名字先匹配
        e = re.escape(n)
        # 英文名前后不能紧挨字母，避免 LEE 匹配到 FLEET
        parts.append(rf"(?<![A-Za-z]){e}(?![A-Za-z])" if LATIN.search(n) else e)
    return re.compile("|".join(parts)) if parts else None


def fmt_shift(n: int) -> str:
    return f"推后 {n} 天" if n > 0 else f"提前 {-n} 天" if n < 0 else "不变"


class Filter:
    """一次对比用一个 Filter：人名清单由两边文件、名单文件和配置合在一起。"""

    def __init__(self, cfg: dict, texts_a: list[str], texts_b: list[str], extra_names: dict | None = None):
        self.cfg = {**FILTER_DEFAULTS, **(cfg or {})}
        self.date_res = [re.compile(p) for p in self.cfg["date_formats"]]
        names = {n: "配置文件" for n in self.cfg["names"]}
        for n, src in (extra_names or {}).items():
            names.setdefault(n, src)
        for texts in (texts_a, texts_b):
            for n, src in collect_names(texts, self.cfg["name_labels"]).items():
                names.setdefault(n, src)
        for n in self.cfg["not_names"]:
            names.pop(n, None)
        self.names = names
        self.name_re = name_regex(names)
        self.suspect_re = re.compile(self.cfg["suspect_name_pattern"])

    def template(self, text: str):
        """把日期、人名换成占位符。返回 (替换后的文字, 日期列表, 人名列表)，顺序与原文一致。"""
        spans = []
        for rx in self.date_res:
            for m in rx.finditer(text):
                try:
                    d = dt.date(int(m["y"]), int(m["m"]), int(m["d"]))
                except ValueError:  # 2026 02 30 这类不存在的日期不算日期
                    continue
                spans.append((m.start(), m.end(), d))
        spans.sort(key=lambda s: (s[0], -s[1]))
        out, dates, pos = [], [], 0
        for s, e, d in spans:
            if s < pos:  # 与前一个日期重叠
                continue
            out += [text[pos:s], DATE_PH]
            dates.append(d)
            pos = e
        out.append(text[pos:])
        key = "".join(out)
        names = []
        if self.name_re:
            key = self.name_re.sub(lambda m: names.append(m[0]) or NAME_PH, key)
        return key, dates, names

    def source_of(self, name: str) -> str:
        return self.names.get(name, "清单")

    def suspects(self, texts: list[str]) -> list[str]:
        """不在人名清单里、但像人名的大写英文（只提醒，不忽略）。"""
        return list(dict.fromkeys(t.strip() for t in texts if self.suspect_re.match(t.strip()) and t.strip() not in self.names))

    def any_shift_label(self, text: str) -> bool:
        return any(lab in text for lab in self.cfg["date_any_shift_labels"])
