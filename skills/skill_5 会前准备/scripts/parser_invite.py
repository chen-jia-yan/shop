#!/usr/bin/env python3
"""解析会议邀请：支持 .ics 文件，以及从 Outlook 复制的邀请文本（中/英文）。

用法:
    python parse_invite.py invite.ics
    python parse_invite.py pasted.txt
    cat pasted.txt | python parse_invite.py -

输出 JSON:
    {subject, start, end, organizer, required, optional, location, body, source, missing}

只用 Python 标准库，无需安装依赖。
"""
import json
import re
import sys
from datetime import datetime

# ---------- .ics ----------

def unfold(text):
    """iCalendar 折行：以空格或 Tab 开头的行是上一行的延续。"""
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def ics_unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n")
             .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def ics_time(value, params):
    v = value.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        out = dt.strftime("%Y-%m-%d %H:%M") if "T" in v else dt.strftime("%Y-%m-%d")
        if v.endswith("Z"):
            out += " UTC"
        elif "TZID" in params:
            out += f" ({params['TZID']})"
        return out
    return v


def ics_person(value, params):
    email = re.sub(r"^mailto:", "", value.strip(), flags=re.IGNORECASE)
    name = params.get("CN", "").strip('"')
    return f"{name} <{email}>" if name else email


def parse_ics(text):
    result = {"subject": "", "start": "", "end": "", "organizer": "",
              "required": [], "optional": [], "location": "", "body": ""}
    in_event = False
    for line in unfold(text):
        if line.strip() == "BEGIN:VEVENT":
            in_event = True
            continue
        if line.strip() == "END:VEVENT":
            break  # 只取第一个会议
        if not in_event or ":" not in line:
            continue
        head, value = line.split(":", 1)
        parts = head.split(";")
        key = parts[0].upper()
        params = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.upper()] = v
        if key == "SUMMARY":
            result["subject"] = ics_unescape(value)
        elif key == "DTSTART":
            result["start"] = ics_time(value, params)
        elif key == "DTEND":
            result["end"] = ics_time(value, params)
        elif key == "ORGANIZER":
            result["organizer"] = ics_person(value, params)
        elif key == "ATTENDEE":
            role = params.get("ROLE", "REQ-PARTICIPANT").upper()
            bucket = "optional" if role == "OPT-PARTICIPANT" else "required"
            result[bucket].append(ics_person(value, params))
        elif key == "LOCATION":
            result["location"] = ics_unescape(value)
        elif key == "DESCRIPTION":
            result["body"] = ics_unescape(value).strip()
    result["source"] = "ics"
    return result

# ---------- 粘贴文本 ----------

LABELS = {
    "subject": ["主题", "会议主题", "Subject", "Title"],
    "time": ["时间", "When", "Date"],
    "start": ["开始时间", "开始", "Start", "Start time"],
    "end": ["结束时间", "结束", "End", "End time"],
    "organizer": ["组织者", "Organizer", "From", "发件人"],
    "required": ["必需参加者", "必选参加者", "必需与会者", "参会人", "与会者", "Required", "Required Attendees", "To", "收件人"],
    "optional": ["可选参加者", "可选与会者", "Optional", "Optional Attendees", "Cc", "抄送"],
    "location": ["地点", "位置", "Where", "Location"],
}
LABEL_TO_FIELD = {lab.lower(): f for f, labs in LABELS.items() for lab in labs}
LABEL_RE = re.compile(r"^\s*([^:：]{1,24})\s*[:：]\s*(.*)$")
SPLIT_PEOPLE = re.compile(r"\s*[;；,，、]\s*")


def parse_text(text):
    result = {"subject": "", "start": "", "end": "", "organizer": "",
              "required": [], "optional": [], "location": "", "body": ""}
    body_lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        m = LABEL_RE.match(line)
        field = LABEL_TO_FIELD.get(m.group(1).strip().lower()) if m else None
        if not field:
            body_lines.append(line)
            continue
        value = m.group(2).strip()
        if field in ("required", "optional"):
            result[field] += [p for p in SPLIT_PEOPLE.split(value) if p]
        elif field == "time":
            # "2026年11月17日 14:00-15:00" / "2026-11-17 14:00 至 15:00"：只在时刻之后拆分，避免拆开日期里的 "-"
            rng = re.match(r"^(.*?\d{1,2}:\d{2})\s*(?:-|–|—|~|至|到)\s*(.+)$", value)
            if rng:
                result["start"], result["end"] = rng.group(1).strip(), rng.group(2).strip()
            else:
                result["start"] = value
        elif not result[field]:
            result[field] = value
    result["body"] = "\n".join(body_lines).strip()
    result["source"] = "text"
    return result

# ---------- 入口 ----------

def parse(text):
    data = parse_ics(text) if "BEGIN:VCALENDAR" in text or "BEGIN:VEVENT" in text else parse_text(text)
    data["missing"] = [k for k in ("subject", "start") if not data[k]]
    if not data["required"] and not data["optional"]:
        data["missing"].append("attendees")
    return data


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    if sys.argv[1] == "-":
        text = sys.stdin.read()
    else:
        with open(sys.argv[1], encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    print(json.dumps(parse(text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
