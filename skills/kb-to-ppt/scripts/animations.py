# -*- coding: utf-8 -*-
"""
动画与切换效果（直接写入 PowerPoint 的 p:timing / p:transition XML）。

用法：
  seq = Seq(slide)
  seq.begin(); ...画一组形状...; seq.end("float")      # 这一组一起入场
  apply(slide, seq, transition="fade")

入场效果（PowerPoint 中的名称）：
  fade 淡入 / float 浮入（淡入并轻微上移，默认）/ wipe 擦除（自左）/ zoom 缩放
所有步骤在幻灯片出现后自动依次播放（“上一动画之后”），演讲时不用逐个点击；
相邻步骤有少量重叠，观感更流畅。动画总时长自动控制在约 2.5 秒内。

切换效果：fade 淡化 / push 推入 / wipe 擦除 / none
"""
from lxml import etree

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
NSDECL = 'xmlns:p="%s" xmlns:a="%s"' % (P_NS, A_NS)

PRESETS = {"fade": (10, 0), "float": (42, 0), "wipe": (22, 8), "zoom": (53, 16)}


class Seq(object):
    def __init__(self, slide):
        self.slide = slide
        self.steps = []          # [(shape_ids, effect)]
        self._ids = None

    def begin(self):
        self._ids = {s.shape_id for s in self.slide.shapes}

    def end(self, effect="float"):
        new = [s.shape_id for s in self.slide.shapes if s.shape_id not in self._ids]
        if new:
            self.steps.append((new, effect))
        self._ids = None

    def add(self, shapes, effect="float"):
        ids = [s.shape_id for s in (shapes if isinstance(shapes, (list, tuple)) else [shapes])]
        if ids:
            self.steps.append((ids, effect))


class _Ids(object):
    def __init__(self):
        self.n = 2

    def next(self):
        self.n += 1
        return self.n


def _set(ids, spid):
    return ('<p:set><p:cBhvr><p:cTn id="%d" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            '</p:cTn><p:tgtEl><p:spTgt spid="%d"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName>'
            '</p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>') % (ids.next(), spid)


def _filter(ids, spid, flt, dur):
    return ('<p:animEffect transition="in" filter="%s"><p:cBhvr><p:cTn id="%d" dur="%d"/><p:tgtEl>'
            '<p:spTgt spid="%d"/></p:tgtEl></p:cBhvr></p:animEffect>') % (flt, ids.next(), dur, spid)


def _anim(ids, spid, attr, v0, v1, dur):
    return ('<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="%d" dur="%d" fill="hold"/>'
            '<p:tgtEl><p:spTgt spid="%d"/></p:tgtEl><p:attrNameLst><p:attrName>%s</p:attrName></p:attrNameLst>'
            '</p:cBhvr><p:tavLst><p:tav tm="0"><p:val><p:strVal val="%s"/></p:val></p:tav><p:tav tm="100000">'
            '<p:val><p:strVal val="%s"/></p:val></p:tav></p:tavLst></p:anim>') % (ids.next(), dur, spid, attr, v0, v1)


def _effect(ids, spid, effect, dur, node_type, grp):
    pid, sub = PRESETS.get(effect, PRESETS["fade"])
    body = _set(ids, spid)
    if effect == "float":
        body += _filter(ids, spid, "fade", dur) + _anim(ids, spid, "ppt_x", "#ppt_x", "#ppt_x", dur) + \
            _anim(ids, spid, "ppt_y", "#ppt_y+0.06", "#ppt_y", dur)
    elif effect == "wipe":
        body += _filter(ids, spid, "wipe(left)", dur)
    elif effect == "zoom":
        body += _anim(ids, spid, "ppt_w", "0", "#ppt_w", dur) + _anim(ids, spid, "ppt_h", "0", "#ppt_h", dur) + \
            _filter(ids, spid, "fade", dur)
    else:
        body += _filter(ids, spid, "fade", dur)
    return ('<p:par><p:cTn id="%d" presetID="%d" presetClass="entr" presetSubtype="%d" fill="hold" grpId="%d" '
            'nodeType="%s"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>%s</p:childTnLst>'
            '</p:cTn></p:par>') % (ids.next(), pid, sub, grp, node_type, body)


def _timing_xml(steps, total_ms=2500):
    ids = _Ids()
    n = len(steps)
    dur = 500 if n <= 4 else (420 if n <= 7 else 350)
    gap = max(120, min(380, int((total_ms - dur) / max(n - 1, 1)))) if n > 1 else 0
    inner = []
    t = 0
    for si, (spids, effect) in enumerate(steps):
        effs = []
        for k, spid in enumerate(spids):
            effs.append(_effect(ids, spid, effect, dur, "afterEffect" if k == 0 else "withEffect", 0))
        inner.append('<p:par><p:cTn id="%d" fill="hold"><p:stCondLst><p:cond delay="%d"/></p:stCondLst>'
                     '<p:childTnLst>%s</p:childTnLst></p:cTn></p:par>' % (ids.next(), t, "".join(effs)))
        t += gap
    xml = ('<p:timing %s><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
           '<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
           '<p:childTnLst><p:par><p:cTn id="%d" fill="hold"><p:stCondLst><p:cond delay="indefinite"/>'
           '<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>%s</p:childTnLst>'
           '</p:cTn></p:par></p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl>'
           '<p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst><p:nextCondLst><p:cond evt="onNext" delay="0">'
           '<p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq></p:childTnLst></p:cTn></p:par>'
           '</p:tnLst></p:timing>') % (NSDECL, ids.next(), "".join(inner))
    return xml


TRANSITIONS = {
    "fade": '<p:transition %s spd="med"><p:fade/></p:transition>',
    "push": '<p:transition %s spd="med"><p:push dir="u"/></p:transition>',
    "wipe": '<p:transition %s spd="med"><p:wipe dir="r"/></p:transition>',
}


def apply(slide, seq=None, transition="fade", animate=True):
    sld = slide._element
    for tag in ("transition", "timing"):
        for old in sld.findall("{%s}%s" % (P_NS, tag)):
            sld.remove(old)
    ext = sld.find("{%s}extLst" % P_NS)
    if transition and transition != "none":
        tr = etree.fromstring(TRANSITIONS.get(transition, TRANSITIONS["fade"]) % NSDECL)
        if ext is not None:
            ext.addprevious(tr)
        else:
            sld.append(tr)
    if animate and seq is not None and seq.steps:
        tm = etree.fromstring(_timing_xml(seq.steps))
        if ext is not None:
            ext.addprevious(tm)
        else:
            sld.append(tm)
    return len(seq.steps) if seq else 0
