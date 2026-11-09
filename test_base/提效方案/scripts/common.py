"""公共工具：配置读取、JSON 读写、个人信息脱敏、文本匹配、报错特征标准化。

所有脚本都从这里导入，保证行为一致。
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

import yaml

TZ_HK = timezone(timedelta(hours=8))

CATEGORIES = {
    "RERUN_PASS": "重跑可过",
    "ENVIRONMENT": "环境问题",
    "POPUP_INTERFERENCE": "弹窗干扰",
    "SCRIPT_ISSUE": "脚本问题",
    "TEST_DATA": "测试数据问题",
    "PRODUCT_DEFECT": "产品缺陷",
    "NEEDS_HUMAN": "需人工判断",
}

OWNERS = {
    "RERUN_PASS": "测试",
    "ENVIRONMENT": "环境负责人",
    "POPUP_INTERFERENCE": "测试",
    "SCRIPT_ISSUE": "测试",
    "TEST_DATA": "测试",
    "PRODUCT_DEFECT": "开发",
    "NEEDS_HUMAN": "测试",
}

REVIEW_STATUSES = ["待审核", "通过", "驳回", "追加到已有单"]


# ---------------------------------------------------------------- 基础 IO

def setup_logging(verbose: bool = False) -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("triage")


def now_iso() -> str:
    return datetime.now(TZ_HK).isoformat(timespec="seconds")


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)  # 原子替换，避免中途失败留下半个文件


def read_yaml(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return default if data is None else data


def write_yaml(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_config(path: str | Path) -> dict:
    cfg = read_yaml(path)
    if not cfg:
        fail(f"找不到配置文件或内容为空：{path}。请从 config/config.example.yaml 复制并填写。")
    return cfg


def fail(msg: str, code: int = 2) -> None:
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- 文本匹配

def match_any(text: str | None, patterns: Iterable[str]) -> str | None:
    """返回第一个命中的规则原文；未命中返回 None。

    规则以 "re:" 开头时按正则匹配，否则做不区分大小写的子串匹配。
    """
    if not text:
        return None
    low = text.lower()
    for p in patterns or []:
        if p.startswith("re:"):
            if re.search(p[3:], text, flags=re.IGNORECASE | re.DOTALL):
                return p
        elif p.lower() in low:
            return p
    return None


def short_exception_name(error_type: str | None) -> str | None:
    """'selenium.common.exceptions.TimeoutException' -> 'TimeoutException'"""
    if not error_type:
        return None
    return error_type.strip().split(".")[-1].split(":")[0].strip() or None


INTERCEPT_RE = re.compile(r"Other element would receive the click:\s*(<[^>]+>)", re.IGNORECASE)


def intercepting_element(error_message: str | None) -> str | None:
    """从 ElementClickInterceptedException 的报错中取出遮挡点击的元素 HTML 片段。"""
    if not error_message:
        return None
    m = INTERCEPT_RE.search(error_message)
    return m.group(1) if m else None


# ---------------------------------------------------------------- 报错特征标准化

_NORMALIZERS = [
    (re.compile(r"\(Session info:[^)]*\)", re.I), ""),
    (re.compile(r"Stacktrace:.*", re.I | re.S), ""),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<hex>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?"), "<time>"),
    (re.compile(r"\bat point \(\d+,\s*\d+\)"), "at point (<x>,<y>)"),
    (re.compile(r"\d+"), "<n>"),
    (re.compile(r"\s+"), " "),
]


def normalize_signature(text: str | None, max_len: int = 200) -> str:
    """把报错中会变化的部分（数字、时间、网址、会话信息）替换掉，用于判断“是不是同一个报错”。"""
    if not text:
        return ""
    s = text
    for pattern, repl in _NORMALIZERS:
        s = pattern.sub(repl, s)
    return s.strip().lower()[:max_len]


# ---------------------------------------------------------------- 个人信息脱敏

_PII_PATTERNS = [
    # 香港身份证：A123456(7) / AB123456(A)
    ("<HKID>", re.compile(r"\b[A-Z]{1,2}\d{6}\s?\(?[0-9A]\)?(?![0-9])")),
    # 内地身份证 18 位
    ("<CN_ID>", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    # 澳门身份证：1234567(8)
    ("<MO_ID>", re.compile(r"(?<!\d)[157]\d{6}\(\d\)")),
    ("<EMAIL>", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # 内地手机号
    ("<PHONE>", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    # 带 +852 / +853 区号的港澳电话
    ("<PHONE>", re.compile(r"\+85[23][\s-]?[2-9]\d{3}[\s-]?\d{4}(?!\d)")),
]

# 港澳 8 位电话没有固定特征，容易和保单号、日期（20261106）混淆，
# 所以只在前面出现“电话 / Tel / Mobile”等字样时才替换。
_PHONE_CONTEXT_RE = re.compile(
    r"((?:tel|phone|mobile|contact|電話|电话|手機|手机|聯絡|联系)[^0-9\n]{0,12})([2-9]\d{3}[\s-]?\d{4})(?!\d)",
    re.IGNORECASE,
)

_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _mask_card(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    # 只替换通过 Luhn 校验的号码，避免误伤长保单号
    return "<CARD>" if _luhn_ok(digits) else m.group(0)


def mask_pii(text: str | None, extra_values: Iterable[str] = ()) -> str | None:
    """替换文本中的证件号、手机号、邮箱、银行卡号，以及调用方传入的已知敏感值（如测试姓名）。

    注意：正则无法识别所有姓名。测试数据中的姓名字段请通过 extra_values 传入。
    """
    if text is None:
        return None
    s = str(text)
    for value in sorted({str(v) for v in extra_values if v and len(str(v)) >= 2}, key=len, reverse=True):
        s = s.replace(value, "<NAME>")
    for label, pattern in _PII_PATTERNS:
        s = pattern.sub(label, s)
    s = _PHONE_CONTEXT_RE.sub(lambda m: m.group(1) + "<PHONE>", s)
    s = _CARD_CANDIDATE_RE.sub(_mask_card, s)
    return s


def split_test_data(test_data: dict | None, cfg: dict) -> tuple[dict, list[str]]:
    """把测试数据拆成“可保留的业务编码”和“需要从文本中替换掉的敏感值”。"""
    test_data = test_data or {}
    pii_cfg = cfg.get("pii", {})
    allowed = {k.lower() for k in pii_cfg.get("allowed_fields", [])}
    sensitive = {k.lower() for k in pii_cfg.get("sensitive_fields", [])}
    kept, secrets = {}, []
    for k, v in test_data.items():
        key = str(k).lower()
        if key in allowed:
            kept[k] = v
        elif key in sensitive or any(s in key for s in sensitive):
            if v:
                secrets.append(str(v))
        else:
            kept[k] = mask_pii(str(v)) if v is not None else None
    return kept, secrets


# ---------------------------------------------------------------- 证据

def add_evidence(case: dict, kind: str, content: str | None = None, path: str | None = None,
                 **extra: Any) -> str:
    """给用例追加一条证据，返回证据编号（E1、E2……）。"""
    ev = case.setdefault("evidence", [])
    eid = f"E{len(ev) + 1}"
    item = {"id": eid, "kind": kind}
    if content is not None:
        item["content"] = content
    if path is not None:
        item["path"] = path
    item.update(extra)
    ev.append(item)
    return eid


def find_evidence(case: dict, kind: str) -> list[dict]:
    return [e for e in case.get("evidence", []) if e.get("kind") == kind]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ_HK)
    except ValueError:
        return None
