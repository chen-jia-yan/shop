"""看文件：批次文件夹里生成 index.html。左边是 Case 列表（可搜索、只看有变化的），右边看这个 Case 的变化和截图，
或者直接在页面里打开他的 total / ignore / difference 页面，不用再一个个去文件夹里点。双击 index.html 就能看，不需要联网。
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from common import rel

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>__TITLE__</title>
<style>
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{font:13px/1.55 "Microsoft YaHei UI","Microsoft YaHei","PingFang SC",sans-serif;color:#1f2329;background:#f5f6f7}
.app{display:grid;grid-template-columns:300px minmax(0,1fr);height:100vh}
aside{background:#fff;border-right:1px solid #dee0e3;display:flex;flex-direction:column;min-height:0}
.hd{padding:14px 14px 10px;border-bottom:1px solid #eff0f1}.hd b{font-size:15px}.hd small{display:block;color:#8f959e}
.sum{display:flex;gap:14px;margin-top:8px;font-size:12px;color:#646a73}.sum b{font-size:15px;color:#1f2329}
.flt{padding:8px 12px;display:flex;gap:6px;align-items:center;border-bottom:1px solid #eff0f1}
.flt input[type=search]{flex:1;height:28px;border:1px solid #dee0e3;border-radius:6px;padding:0 8px;font:inherit}
.flt label{font-size:12px;color:#646a73;white-space:nowrap}
.list{flex:1;overflow:auto}
.ci{padding:9px 14px;border-bottom:1px solid #f2f3f5;cursor:pointer}
.ci:hover{background:#f7f9ff}.ci.on{background:#e1eaff}
.ci .k{font-weight:600;display:flex;align-items:center;gap:8px}.ci .f{font-size:11.5px;color:#8f959e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.n{margin-left:auto;font-size:12px;border-radius:10px;padding:0 8px;background:#eff0f1;color:#646a73}
.n.has{background:#fde2e2;color:#d83931}.n.err{background:#fff3cf;color:#8f6200}
main{display:flex;flex-direction:column;min-width:0;min-height:0}
.tabs{display:flex;gap:4px;padding:8px 14px 0;background:#fff;border-bottom:1px solid #dee0e3}
.tab{padding:6px 12px;border-radius:6px 6px 0 0;cursor:pointer;color:#646a73;border:1px solid transparent;border-bottom:0}
.tab.on{color:#3370ff;background:#f5f6f7;border-color:#dee0e3;font-weight:600}.tab.off{opacity:.4;pointer-events:none}
.tabs .sp{flex:1}.tabs a{align-self:center;font-size:12px;color:#3370ff;margin-left:10px}
.body{flex:1;overflow:auto;padding:14px}
iframe{width:100%;height:100%;border:1px solid #dee0e3;background:#fff;border-radius:6px}
.it{background:#fff;border:1px solid #e5e6eb;border-radius:8px;margin-bottom:12px;overflow:hidden}
.it .h{display:flex;gap:10px;align-items:baseline;padding:8px 12px;background:#fafbfc;border-bottom:1px solid #eff0f1}
.it .h b{font-family:Consolas,monospace}.it .h .chg{color:#d83931;font-weight:600}.it .h .m{margin-left:auto;color:#8f959e;font-size:12px}
.two{display:grid;grid-template-columns:1fr 1fr}.two>div{padding:8px 12px;min-width:0}.two>div+div{border-left:1px solid #eff0f1}
.lab{font-size:11.5px;color:#8f959e}.val{font-family:Consolas,"Microsoft YaHei",monospace;white-space:pre-wrap;word-break:break-all}
.val i{font-style:normal;background:#fde2e2;color:#d83931;font-weight:600;border-radius:2px}
.two img{max-width:100%;border:1px solid #e5e6eb;border-radius:4px;margin-top:6px;cursor:zoom-in}
.miss{color:#8f6200;font-size:12px;margin-top:6px}.note{padding:6px 12px;background:#fffbe6;color:#8f6200;font-size:12px}
.empty{color:#8f959e;padding:40px;text-align:center}.err{color:#d83931}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:9}
#zoom img{max-width:94vw;max-height:94vh;background:#fff}
</style></head><body>
<div class="app">
<aside>
 <div class="hd"><b>__TITLE__</b><small>__META__</small>
  <div class="sum"><span>Case <b id="sc"></b></span><span>有变化 <b id="sh"></b></span><span>变化 <b id="si"></b></span><span>出错 <b id="se"></b></span></div></div>
 <div class="flt"><input type="search" id="q" placeholder="搜 Case、字段、值"><label><input type="checkbox" id="only"> 只看有变化</label></div>
 <div class="list" id="list"></div>
</aside>
<main>
 <div class="tabs" id="tabs"><span class="tab on" data-t="items">变化和截图</span><span class="tab" data-t="difference">difference</span><span class="tab" data-t="total">total</span><span class="tab" data-t="ignore">ignore</span><span class="tab" data-t="log">运行日志</span><span class="sp"></span>__LINKS__</div>
 <div class="body" id="body"></div>
</main></div>
<div id="zoom"><img alt=""></div>
<script>
const D=__DATA__;
const $=s=>document.querySelector(s),esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let cur=null,tab="items";
$("#sc").textContent=D.cases.length;$("#sh").textContent=D.cases.filter(c=>c.items.length).length;
$("#si").textContent=D.cases.reduce((a,c)=>a+c.items.length,0);$("#se").textContent=D.cases.filter(c=>c.error).length;
function hit(c,q){if(!q)return true;q=q.toLowerCase();return [c.key,c.baseline,c.new].concat(c.items.flatMap(i=>[i.field,i.old,i.new])).some(x=>String(x||"").toLowerCase().includes(q))}
function list(){const q=$("#q").value.trim(),only=$("#only").checked;
 $("#list").innerHTML=D.cases.filter(c=>(!only||c.items.length)&&hit(c,q)).map(c=>`<div class="ci${cur===c?" on":""}" data-k="${esc(c.key)}"><div class="k">${esc(c.key)}<span class="n ${c.error?"err":c.items.length?"has":""}">${c.error?"出错":c.items.length+" 处"}</span></div><div class="f">${esc(c.new||c.baseline||"")}</div></div>`).join("")||'<div class="empty">没有符合的 Case</div>';
 document.querySelectorAll(".ci").forEach(e=>e.onclick=()=>{cur=D.cases.find(c=>c.key===e.dataset.k);list();show()})}
function seg(s){return s.length?s.map(([t,ch])=>ch?`<i>${esc(t)}</i>`:esc(t)).join(""):'<span class="lab">（无）</span>'}
function shot(it,side){const p=it["shot_"+side];if(p)return `<img src="${esc(p)}" alt="">`;return it[side]?'<div class="miss">截图待补</div>':""}
function show(){document.querySelectorAll(".tab").forEach(t=>{t.classList.toggle("on",t.dataset.t===tab);t.classList.toggle("off",!!cur&&t.dataset.t!=="items"&&!cur.files[t.dataset.t])});
 const b=$("#body");if(!cur){b.innerHTML='<div class="empty">左边选一个 Case</div>';return}
 if(tab!=="items"){const f=cur.files[tab];b.innerHTML=f?`<iframe src="${esc(f)}"></iframe>`:'<div class="empty">这个 Case 没有这个文件</div>';return}
 let h=cur.error?`<div class="note err">对比出错：${esc(cur.error)}（看“运行日志”）</div>`:"";
 h+=cur.items.length?"":'<div class="empty">没有变化</div>';
 h+=cur.items.map(it=>`<div class="it"><div class="h"><b>${esc(it.id)}</b><span>${esc(it.field||"（无字段名）")}</span><span>${esc(it.kind)}</span><span class="chg">${esc(it.change)}</span><span class="m">${esc(it.where_old)} ⇢ ${esc(it.where_new)}</span></div>
 <div class="two"><div><div class="lab">原值（baseline）</div><div class="val">${seg(it.seg_old)}</div>${shot(it,"old")}</div><div><div class="lab">新值</div><div class="val">${seg(it.seg_new)}</div>${shot(it,"new")}</div></div>
 ${(it.shot_note||[]).length?`<div class="note">${esc(it.shot_note.join("；"))}</div>`:""}</div>`).join("");
 b.innerHTML=h;b.querySelectorAll("img").forEach(i=>i.onclick=()=>{$("#zoom img").src=i.src;$("#zoom").style.display="flex"})}
$("#zoom").onclick=()=>$("#zoom").style.display="none";
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{tab=t.dataset.t;show()});
$("#q").oninput=list;$("#only").onchange=list;
cur=D.cases.find(c=>c.items.length)||D.cases[0]||null;list();show();
</script></body></html>"""


def write_index(batch_dir: Path, batch: dict, cfg: dict, outputs: dict) -> Path:
    cases = []
    for p in batch["pairs"]:
        if p.get("items") is None and not p.get("error"):
            continue
        files = {k: rel(v, batch_dir) for k, v in (p.get("files") or {}).items() if k in ("difference", "total", "ignore")}
        log = batch_dir / "cases" / p["dir"] / "run.log"
        if log.is_file():
            files["log"] = rel(log, batch_dir)
        items = []
        for it in p.get("items") or []:
            if it.get("skip"):
                continue
            items.append({**{k: it.get(k) for k in ("id", "field", "kind", "change", "old", "new", "seg_old", "seg_new", "shot_note")},
                          "shot_old": rel(it["shot_old"], batch_dir) if it.get("shot_old") else "",
                          "shot_new": rel(it["shot_new"], batch_dir) if it.get("shot_new") else "",
                          "where_old": _where(it, "old"), "where_new": _where(it, "new")})
        cases.append({"key": p["key"], "baseline": Path(p["baseline"]).name if p["baseline"] else "",
                      "new": Path(p["new"]).name if p["new"] else "", "error": p.get("error") or "",
                      "files": files, "items": items})
    links = " ".join(f'<a href="{rel(v, batch_dir)}">{k}</a>' for k, v in outputs.items() if v)
    title = cfg["deliver"]["title"]
    meta = f"{datetime.datetime.now():%Y-%m-%d %H:%M} · {batch_dir.name}"
    data = json.dumps({"cases": cases}, ensure_ascii=False).replace("</", "<\\/")
    html = PAGE.replace("__TITLE__", title).replace("__META__", meta).replace("__LINKS__", links).replace("__DATA__", data)
    out = batch_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def _where(it, side):
    page = it.get(f"pageno_{side}") or it.get(f"page_{side}")
    line = it.get(f"line_{side}")
    return " · ".join(x for x in (f"第 {page} 页" if page else "", f"行 {line}" if line else "") if x) or "—"
