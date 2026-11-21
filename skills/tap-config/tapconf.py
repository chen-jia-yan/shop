# -*- coding: utf-8 -*-
"""
TAP 文档生成 —— 共享配置加载器（Word / Excel / PPT / 变更影响分析共用）

所有品牌、配色、字体、主题、文字标签、合规词表、阈值都放在 JSON 里，脚本不写死。
加载顺序（后面的覆盖前面的，字典逐层合并，列表整体替换）：
  1. 本目录的 brand.json / themes.json / labels.json / compliance.json / rules.json
  2. 环境变量 TAP_CONFIG 指定的文件或目录（多个用系统路径分隔符隔开）
  3. 命令行 --config（可写多次，文件或目录）
  4. 内容 JSON 的 meta.config（只写要改的部分，例如 {"fonts": {"cn": ["思源黑体"]}}）
  5. 快捷覆盖：meta.brand（机构名）、meta.fonts、命令行 --font-cn / --font-en / --font-num / --font-mode / --font-scale

字体按顺序叠加：fonts → fonts_by_scope[当前 skill] → font_presets[字体方案]（如有）→ 用户指定（meta.fonts / 命令行）。

颜色引用：主题里写 "@primary" 表示 brand.json 中 colors.primary；也可以直接写 "#RRGGBB"。
"""
import copy
import json
import os
import re
import subprocess
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("brand.json", "themes.json", "labels.json", "compliance.json", "rules.json", "icons.json", "impact.json")
FONT_ROLES = ("cn", "head", "en", "num", "quote", "mono")
_TOKEN = re.compile(r"^@[A-Za-z_]\w*$")          # @primary
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")          # #E87722（“#,##0” 这类数字格式不受影响）


def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_path(p):
    p = os.path.abspath(os.path.expanduser(p))
    if os.path.isdir(p):
        merged = {}
        names = [n for n in FILES if os.path.exists(os.path.join(p, n))]
        names += sorted(n for n in os.listdir(p) if n.endswith(".json") and n not in FILES)
        for n in names:
            merged = deep_merge(merged, _read_path(os.path.join(p, n)))
        return merged
    if not os.path.exists(p):
        raise SystemExit("配置文件不存在：%s" % p)
    with open(p, encoding="utf-8") as f:
        try:
            return json.load(f)
        except ValueError as e:
            raise SystemExit("配置文件不是合法 JSON：%s（%s）" % (p, e))


_INSTALLED = None


def installed_fonts():
    """本机已安装字体名（小写）；检测不到时返回空集合。"""
    global _INSTALLED
    if _INSTALLED is not None:
        return _INSTALLED
    names = set()
    try:
        from matplotlib import font_manager
        names |= {f.name.lower() for f in font_manager.fontManager.ttflist}
    except Exception:                       # noqa: BLE001  未装 matplotlib 时退回 fc-list
        pass
    if not names:
        try:
            out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                for n in line.split(","):
                    names.add(n.strip().lower())
        except Exception:                   # noqa: BLE001
            pass
    _INSTALLED = names
    return names


def _chain(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else [x for x in v if x]


def pick_font(chain, mode="first"):
    chain = _chain(chain)
    if not chain:
        return None
    if mode == "installed":
        inst = installed_fonts()
        for f in chain:
            if f.lower() in inst:
                return f
    return chain[0]


class Conf(object):
    """单例。colors / fonts / org / sizes 等字典在重新加载时原地更新，模块里提前 import 的引用不会失效。"""

    def __init__(self):
        self.raw = {}
        self.scope = None
        self.colors = {}
        self.fonts = {}
        self.font_chains = {}
        self.org = {}
        self.sizes = {}
        self.chart_palette = []
        self.font_scale = 1.0
        self.sources = []
        self.user_fonts = {}
        self.font_preset = None
        self._hooks = []

    # ---------- 加载 ----------
    def load(self, scope, paths=None, inline=None, fonts=None, font_mode=None, font_scale=None, brand=None):
        raw = {}
        srcs = [HERE]
        env = os.environ.get("TAP_CONFIG")
        if env:
            srcs += [p for p in env.split(os.pathsep) if p]
        srcs += list(paths or [])
        for p in srcs:
            raw = deep_merge(raw, _read_path(p))
        if inline:
            raw = deep_merge(raw, inline)
        f = raw.setdefault("fonts", {})
        # 用户指定的字体（meta.fonts / 命令行）最后生效，不会被 fonts_by_scope 或字体方案覆盖
        self.user_fonts = {role: _chain(v) for role, v in (fonts or {}).items() if v}
        if font_mode:
            f["mode"] = font_mode
        if font_scale:
            f["scale"] = float(font_scale)
        if brand:
            raw.setdefault("org", {})["name"] = brand
        self.raw, self.scope, self.sources = raw, scope, srcs
        self._build()
        return self

    def _build(self):
        r, sc = self.raw, self.scope
        colors = dict(r.get("colors", {}))
        colors.update((r.get("colors_by_scope") or {}).get(sc, {}))
        _replace(self.colors, {k: str(v).lstrip("#").upper() for k, v in colors.items() if not k.startswith("_")})
        _replace(self.org, r.get("org", {}))
        fspec = dict(r.get("fonts", {}))
        for k, v in ((r.get("fonts_by_scope") or {}).get(sc) or {}).items():
            fspec[k] = v
        if self.font_preset:
            for k, v in ((r.get("font_presets") or {}).get(self.font_preset) or {}).items():
                if not k.startswith("_"):
                    fspec[k] = v
        fspec.update(self.user_fonts)
        mode = fspec.get("mode", "first")
        chains = {role: _chain(fspec.get(role)) for role in FONT_ROLES}
        resolved = {role: pick_font(chains[role], mode) for role in FONT_ROLES}
        missing = [role for role in ("cn", "en", "num") if not resolved[role]]
        if missing:
            raise SystemExit("字体配置缺少：%s（见 tap-config/brand.json 的 fonts）" % "、".join(missing))
        resolved["head"] = resolved["head"] or resolved["cn"]
        resolved["quote"] = resolved["quote"] or resolved["en"]
        resolved["mono"] = resolved["mono"] or resolved["en"]
        # 图表是本机渲染成图片的，必须用本机装了的字体；先用标题字体（黑体系），图表里不用宋体
        seen, chart = set(), []
        for x in chains["head"] + chains["cn"] + chains["en"] + _chain(fspec.get("chart_extra")):
            if x.lower() not in seen:
                seen.add(x.lower())
                chart.append(x)
        resolved["chart"] = chart
        _replace(self.font_chains, chains)
        _replace(self.fonts, resolved)
        self.font_scale = float(fspec.get("scale", 1.0) or 1.0)
        _replace(self.sizes, dict((self.rules_raw().get("sizes") or {})))
        self.chart_palette[:] = [self.color(c) for c in r.get("chart_palette", [])]
        for fn in self._hooks:
            fn(self)

    def preset_names(self):
        return [k for k in (self.raw.get("font_presets") or {}) if not k.startswith("_")]

    def set_font_preset(self, name):
        """套用 brand.json 的 font_presets 中的一套字体方案（用户另行指定的字体仍然优先）。"""
        if name and name not in self.preset_names():
            raise SystemExit("未知字体方案 %r，可选：%s" % (name, "、".join(self.preset_names())))
        self.font_preset = name or None
        self._build()

    def on_load(self, fn):
        """注册“配置重新加载后”的回调，用于刷新模块里由配置派生的字典；注册时立即执行一次。"""
        self._hooks.append(fn)
        if self.scope is not None:
            fn(self)
        return fn

    # ---------- 取值 ----------
    def color(self, v):
        """'@primary' → 'E87722'；'#c9d6d1' → 'C9D6D1'；None 原样返回。"""
        if v is None or not isinstance(v, str):
            return v
        if _TOKEN.match(v):
            k = v[1:]
            if k not in self.colors:
                raise SystemExit("颜色 %s 未在 brand.json 的 colors 中定义" % v)
            return self.colors[k]
        if _HEX.match(v):
            return v[1:].upper()
        return v

    def resolve(self, obj):
        if isinstance(obj, dict):
            return {k: self.resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.resolve(v) for v in obj]
        return self.color(obj)

    def size(self, pt):
        return None if pt is None else pt * self.font_scale

    def _themes(self):
        t = (self.raw.get("themes") or {}).get(self.scope)
        if not t:
            raise SystemExit("themes.json 中没有 %s 的主题" % self.scope)
        return t

    def theme_names(self):
        return list(self._themes().get("styles", {}))

    def theme(self, name):
        styles = self._themes().get("styles", {})
        if name not in styles:
            raise SystemExit("未知风格 %r，可选：%s" % (name, "、".join(styles)))
        t = self.resolve(styles[name])
        t["_name"] = name
        return t

    def default_theme(self, kind_key, kind):
        th = self._themes()
        return (th.get(kind_key) or {}).get(kind) or th.get("fallback") or self.theme_names()[0]

    def theme_part(self, key):
        return self.resolve(self._themes().get(key, {}))

    def label(self, key, **kw):
        labels = self.raw.get("labels", {})
        for path in ("%s.%s" % (self.scope, key), "common." + key, key):
            v = _dig(labels, path)
            if v is not None:
                break
        else:
            warnings.warn("labels.json 缺少文字：%s" % key)
            v = key
        if kw and isinstance(v, str):
            return v.format(**kw)
        return copy.deepcopy(v)

    def glyph(self, name):
        return self.label("glyphs." + name)

    def rules_raw(self):
        return (self.raw.get("rules") or {}).get(self.scope) or {}

    def rule(self, key):
        v = _dig(self.rules_raw(), key)
        if v is None:
            raise SystemExit("rules.json 缺少规则：%s.%s" % (self.scope, key))
        return copy.deepcopy(v)

    def compliance(self):
        return self.raw.get("compliance") or {}

    def org_name(self, meta=None):
        return (meta or {}).get("brand") or self.org.get("name", "")

    def org_short(self):
        return self.org.get("short", "")

    def placeholder_re(self):
        return re.compile(self.compliance().get("placeholders", {}).get("pattern", r"(?!x)x"))

    def count_placeholders(self, s):
        ph = self.compliance().get("placeholders", {})
        return s.count(ph.get("todo", "\0")), s.count(ph.get("confirm", "\0"))


def _dig(d, path):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _replace(target, new):
    target.clear()
    target.update(new)


CONF = Conf()


# ---------- 命令行 ----------
def add_cli_args(ap):
    g = ap.add_argument_group("配置覆盖（可选）")
    g.add_argument("--config", action="append", default=[], help="额外的配置文件或目录，可写多次")
    g.add_argument("--font-cn", help="中文字体，多个用英文逗号分隔表示候选顺序")
    g.add_argument("--font-en", help="西文字体")
    g.add_argument("--font-num", help="数字字体")
    g.add_argument("--font-mode", choices=["first", "installed"], help="first：用候选第一个；installed：优先本机已安装")
    g.add_argument("--font-scale", type=float, help="整体字号倍数，如 1.1")
    return ap


def configure(scope, args=None, meta=None):
    """在读完命令行和内容 JSON 之后调用，按全部覆盖项重新加载配置。"""
    meta = meta or {}
    fonts = dict(meta.get("fonts") or {})
    for role in ("cn", "en", "num"):
        v = getattr(args, "font_" + role, None) if args is not None else None
        if v:
            fonts[role] = [x.strip() for x in v.split(",") if x.strip()]
    return CONF.load(scope,
                     paths=getattr(args, "config", None) or [],
                     inline=meta.get("config"),
                     fonts=fonts,
                     font_mode=getattr(args, "font_mode", None) if args is not None else None,
                     font_scale=getattr(args, "font_scale", None) if args is not None else None,
                     brand=meta.get("brand"))
