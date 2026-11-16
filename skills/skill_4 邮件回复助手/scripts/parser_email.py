#!/usr/bin/env python3
"""解析来信：支持 .eml 文件，以及从 Outlook 复制的邮件文本（中/英文）。
分离出本次正文、引用的历史邮件、签名档。

用法:
    python parse_email.py mail.eml [--domains example.com,example.cn]
    python parse_email.py pasted.txt
    cat pasted.txt | python parse_email.py -

输出 JSON: {from, from_domain, is_external, to, cc, subject, date, body, history, signature, source}
只用 Python 标准库。
"""
import argparse
import html
import json
import re
import sys
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr

# 历史邮件的分隔标记（出现即认为后面是引用内容）
QUOTE_MARKERS = [
    re.compile(r"^-{2,}\s*(原始邮件|Original Message)\s*-{2,}", re.I),
    re.compile(r"^_{5,}\s*$"),
    re.compile(r"^(发件人|From)\s*[:：]", re.I),
    re.compile(r"^在.{0,40}写道[:：]?\s*$"),
    re.compile(r"^On .{0,80} wrote:\s*$", re.I),
    re.compile(r"^>"),
]
SIGNATURE_MARKERS = [
    re.compile(r"^--\s*$"),
    re.compile(r"^(此致|敬礼|顺祝|祝好|谢谢[!！]?$|Best regards|Regards|Thanks[!,]?$|Best,?$)", re.I),
]
HEADER_LABELS = {
    "from": ["发件人", "From"], "to": ["收件人", "To"], "cc": ["抄送", "Cc"],
    "subject": ["主题", "Subject"], "date": ["发送时间", "日期", "Sent", "Date"],
}
LABEL_TO_FIELD = {l.lower(): f for f, ls in HEADER_LABELS.items() for l in ls}
LABEL_RE = re.compile(r"^\s*([^:：]{1,12})\s*[:：]\s*(.*)$")
EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.)+[\w-]+")


def html_to_text(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def split_body(text):
    """返回 (本次正文, 历史邮件, 签名档)。"""
    lines = text.replace("\r\n", "\n").split("\n")
    cut = len(lines)
    for i, line in enumerate(lines):
        if any(p.match(line.strip()) for p in QUOTE_MARKERS):
            # "From:" 只有出现在正文中间、且之前已有内容时才算历史邮件开始
            if i == 0:
                continue
            cut = i
            break
    current, history = lines[:cut], lines[cut:]
    sig_at = None
    for i in range(len(current) - 1, max(len(current) - 12, -1), -1):
        if any(p.match(current[i].strip()) for p in SIGNATURE_MARKERS):
            sig_at = i
            break
    signature = []
    if sig_at is not None:
        signature = current[sig_at:]
        current = current[:sig_at]
    clean = lambda ls: "\n".join(ls).strip()
    return clean(current), clean(history), clean(signature)


def domain_of(addr):
    m = EMAIL_RE.search(addr or "")
    return m.group(0).split("@", 1)[1].lower() if m else None


def people(value):
    return [f"{n} <{a}>" if n else a for n, a in getaddresses([value]) if a or n]


def parse_eml(path):
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)
    body = msg.get_body(preferencelist=("plain", "html"))
    text = ""
    if body is not None:
        text = body.get_content()
        if body.get_content_type() == "text/html":
            text = html_to_text(text)
    name, addr = parseaddr(str(msg.get("From", "")))
    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    return {"from": f"{name} <{addr}>" if name else addr, "to": people(str(msg.get("To", ""))),
            "cc": people(str(msg.get("Cc", ""))), "subject": str(msg.get("Subject", "")),
            "date": str(msg.get("Date", "")), "text": text, "attachments": attachments, "source": "eml"}


def parse_pasted(text):
    out = {"from": "", "to": [], "cc": [], "subject": "", "date": "", "attachments": [], "source": "text"}
    lines = text.replace("\r\n", "\n").split("\n")
    body_start, seen_header = 0, False
    for i, line in enumerate(lines[:15]):
        m = LABEL_RE.match(line)
        field = LABEL_TO_FIELD.get(m.group(1).strip().lower()) if m else None
        if not field:
            if not seen_header:
                break                       # 开头不是邮件头，整段都是正文
            if line.strip():
                break                       # 邮件头之后的第一行正文
            body_start = i + 1              # 邮件头和正文之间的空行
            continue
        seen_header = True
        v = m.group(2).strip()
        if field in ("to", "cc"):
            out[field] = [p for p in re.split(r"\s*[;；,，]\s*", v) if p]
        elif not out[field]:
            out[field] = v
        body_start = i + 1
    out["text"] = "\n".join(lines[body_start:])
    return out


def main():
    ap = argparse.ArgumentParser(description="解析来信")
    ap.add_argument("file", help=".eml / .txt，或 - 表示从标准输入读取")
    ap.add_argument("--domains", default="", help="公司邮箱域名，逗号分隔，用于判断是否外部来信")
    args = ap.parse_args()

    if args.file == "-":
        data = parse_pasted(sys.stdin.read())
    elif args.file.lower().endswith(".eml"):
        data = parse_eml(args.file)
    else:
        with open(args.file, encoding="utf-8-sig", errors="replace") as f:
            data = parse_pasted(f.read())

    body, history, signature = split_body(data.pop("text"))
    dom = domain_of(data["from"])
    company = {d.strip().lower() for d in args.domains.split(",") if d.strip()}
    data.update({
        "from_domain": dom,
        "is_external": (dom not in company) if (dom and company) else None,
        "body": body, "history": history or None, "signature": signature or None,
    })
    if not body:
        data["warning"] = "没有识别出正文，请确认粘贴的内容"
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
