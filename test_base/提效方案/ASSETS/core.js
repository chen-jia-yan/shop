/* 框架：和本机服务通信、菜单、页签、通用组件。页面不做任何分析，数据和结论都来自 /api/state。 */
window.APP = (function () {
  const S = { runs: [], cases: [], drafts: [], rules: {}, custom: [], changelog: [], corrections: [], jira: {}, jiraLog: [], settings: {}, ocr: {}, view: {} };
  const M = {};  // 分类、重跑建议、规则名称等（来自 Python）

  /* ---------- 本机服务 ---------- */
  async function api(path, body) {
    let r;
    try { r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-TA": "1" }, body: JSON.stringify(body || {}) }); }
    catch (e) { throw new Error("连不上测试分析助手的本机服务，请确认命令行窗口没有关闭"); }
    const j = await r.json().catch(() => ({ error: "服务返回的内容不对（HTTP " + r.status + "）" }));
    if (!r.ok) throw new Error(j.error || "HTTP " + r.status);
    return j;
  }
  async function refresh(noRender) {
    let st;
    try { st = await (await fetch("/api/state", { cache: "no-store" })).json(); }
    catch (e) { toast("连不上本机服务，请确认命令行窗口没有关闭", true); return; }
    const view = S.view;
    Object.keys(M).forEach(k => delete M[k]); Object.assign(M, st.meta); delete st.meta;
    Object.assign(S, st); S.view = view;
    S.byUid = {}; S.cases.forEach(c => { S.byUid[c.uid] = c; });
    pollOcr();
    if (!noRender) render();
  }
  // 发请求 → 重新取数据 → 刷新页面；出错时提示
  async function act(path, body, msg) {
    try {
      const r = await api(path, body);
      await refresh();
      if (msg) toast(typeof msg === "function" ? msg(r) : msg);
      return r;
    } catch (e) { toast(e.message, true); return null; }
  }
  let ocrTimer = null;
  function pollOcr() {
    const bar = $("#ocrBar");
    if (bar) bar.textContent = S.ocr.running ? "⟳ " + (S.ocr.msg || "正在识别截图文字…") : "";
    if (!S.ocr.running || ocrTimer) return;
    ocrTimer = setTimeout(async () => {
      ocrTimer = null;
      const o = await (await fetch("/api/ocr", { cache: "no-store" })).json().catch(() => ({}));
      if (o.running) { S.ocr = o; pollOcr(); return; }
      await refresh(); if (o.msg) toast(o.msg);
    }, 2000);
  }
  const fileData = f => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => rej(r.error); r.readAsDataURL(f); });
  const fileText = f => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => rej(r.error); r.readAsText(f, "utf-8"); });

  /* ---------- 小工具 ---------- */
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  function highlight(text, hits) {
    let s = esc(text);
    (hits || []).filter(h => h && h.length > 1).forEach(h => { const e = esc(h).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); s = s.replace(new RegExp(e, "gi"), m => "<mark>" + m + "</mark>"); });
    return s;
  }
  let tt;
  function toast(msg, err) { const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : ""); clearTimeout(tt); tt = setTimeout(() => { t.className = ""; }, 2800); }
  function copy(text) {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    if (ok) { toast("已复制到剪贴板"); return; }
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => toast("已复制到剪贴板"), () => showText("请手动复制", text)); else showText("请手动复制", text);
  }
  function showText(title, text) { dialog(title, '<textarea class="ta" style="height:360px" readonly>' + esc(text) + "</textarea>", [{ t: "关闭" }]); const ta = $("#dlg textarea"); ta.focus(); ta.select(); }
  // 复制成表格：粘贴到 Outlook、Teams、Excel 时保留表格
  function copyRich(html, text) {
    const box = document.createElement("div");
    box.contentEditable = "true"; box.innerHTML = html; box.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
    document.body.appendChild(box);
    const sel = getSelection(), rg = document.createRange(); rg.selectNodeContents(box); sel.removeAllRanges(); sel.addRange(rg);
    let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
    sel.removeAllRanges(); box.remove();
    if (ok) toast("已复制为表格"); else copy(text);
  }
  function download(name, data, type) {
    const blob = data instanceof Blob ? data : new Blob([data], { type: type || "text/plain;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  const fetchDownload = (url, name) => { const a = document.createElement("a"); a.href = url; a.download = name || ""; document.body.appendChild(a); a.click(); a.remove(); };
  const now = () => new Date().toLocaleString();
  const runName = id => (S.runs.find(r => r.id === id) || {}).name || "-";
  const catTag = cat => { const c = M.CATS[cat] || M.CATS.NEEDS_HUMAN; return '<span class="tag ' + c.color + '">' + c.name + "</span>"; };
  const statusTag = c => c.override ? '<span class="dot" style="--c:#409eff">人工已改</span>' : c.auto.status === "confirmed" ? '<span class="dot" style="--c:#67c23a">规则确认</span>' : '<span class="dot" style="--c:#e6a23c">待复核</span>';
  const planTag = c => { const p = c.plan || { b: "no" }; return '<span class="tag ' + M.PLAN_COLOR[p.b] + '" title="' + esc(p.why) + '">' + (p.b === "done" ? (c.rerun === "pass" ? "重跑通过" : c.r2 && c.r2.same === false ? "重跑失败·报错不同" : "重跑失败·同一问题") : M.PLAN[p.b]) + "</span>"; };
  const caseLabel = c => esc(c.id) + (c.parent ? ' <span class="tag gray" style="font-size:11px;line-height:16px">重跑第2次</span>' : "");
  const emptyBlock = (title, text, btn) => '<div class="empty"><b>' + title + "</b>" + (text || "") + (btn ? '<div style="margin-top:12px">' + btn + "</div>" : "") + "</div>";
  const failed = runId => S.cases.filter(c => c.failed && (!runId || c.run === runId));
  const lastRun = () => S.runs.length ? S.runs[S.runs.length - 1].id : "";
  const runSelect = (id, val, all) => '<select class="sel" id="' + id + '">' + (all ? '<option value="">全部批次</option>' : "") + S.runs.map(r => '<option value="' + r.id + '"' + (val === r.id ? " selected" : "") + ">" + esc(r.name) + "</option>").join("") + "</select>";
  const catOptions = (val, blank) => (blank ? '<option value="">' + blank + "</option>" : "") + Object.keys(M.CATS).map(k => '<option value="' + k + '"' + (val === k ? " selected" : "") + ">" + M.CATS[k].name + "</option>").join("");
  const who = () => S.settings.reviewer || "";
  function bindGo(root) { $$("[data-go]", root).forEach(b => b.onclick = () => go(b.dataset.go, b.dataset.opts ? JSON.parse(b.dataset.opts) : null)); }
  const noData = root => { root.innerHTML = '<div class="card">' + emptyBlock("还没有导入数据", "", '<button class="btn pri" data-go="import">去导入</button>') + "</div>"; bindGo(root); };

  /* ---------- 对话框、抽屉 ---------- */
  function dialog(title, body, buttons) {
    $("#dlg").style.width = ""; $("#dlgT").textContent = title; $("#dlgB").innerHTML = body;
    const f = $("#dlgF"); f.innerHTML = "";
    (buttons || [{ t: "关闭" }]).forEach(b => {
      const el = document.createElement("button"); el.className = "btn" + (b.pri ? " pri" : ""); el.textContent = b.t;
      el.onclick = async () => { if (b.fn && (await b.fn()) === false) return; closeDialog(); }; f.appendChild(el);
    });
    $("#mask").classList.add("open"); $("#dlg").classList.add("open");
  }
  function closeDialog() { $("#dlg").classList.remove("open"); if (!$("#drawer").classList.contains("open")) $("#mask").classList.remove("open"); }
  let drawerFn = null;
  function drawer(title, body, foot, reopen) {
    drawerFn = reopen || null;
    $("#drwT").innerHTML = title; $("#drwB").innerHTML = body; $("#drwF").innerHTML = foot || "";
    $("#mask").classList.add("open"); $("#drawer").classList.add("open");
  }
  function closeDrawer() { drawerFn = null; $("#drawer").classList.remove("open"); $("#mask").classList.remove("open"); $("#dlg").classList.remove("open"); }
  const drawerOpen = () => $("#drawer").classList.contains("open");

  /* ---------- 菜单与页签 ---------- */
  const MENU = [
    { id: "home", name: "工作台", crumb: "工作台" },
    { grp: "测试分析" },
    { id: "import", name: "数据导入", crumb: "测试分析 / 数据导入" },
    { id: "triage", name: "失败分诊", crumb: "测试分析 / 失败分诊", badge: () => S.cases.filter(c => c.failed && !c.override && c.auto.status === "suspected").length },
    { grp: "缺陷提报" },
    { id: "jira", name: "Jira 提报", crumb: "缺陷提报 / Jira 提报", badge: () => S.drafts.filter(d => d.status === "draft").length },
    { grp: "设置" },
    { id: "config", name: "配置", crumb: "设置 / 配置", badge: () => S.corrections.filter(x => !x.test.ok).length },
  ];
  const ALIAS = { rerun: ["triage", "rerun"], dispatch: ["triage", "dispatch"], rules: ["config", "rules"], custom: ["config", "custom"], corrections: ["config", "corrections"], changelog: ["config", "changelog"] };
  const SUBS = {}, PAGES = {}, hist = [];
  let open = ["home"], cur = "home";
  function composite(id, tabs) {
    SUBS[id] = tabs;
    PAGES[id] = (root, v) => {
      if (!tabs.find(t => t[0] === v.sub)) v.sub = tabs[0][0];
      root.innerHTML = '<div class="ptabs">' + tabs.map(([k, n, , bd]) => { const b = bd ? bd() : 0; return '<button data-sub="' + k + '" class="' + (v.sub === k ? "on" : "") + '">' + n + (b ? "<i>" + b + "</i>" : "") + "</button>"; }).join("") + '</div><div id="subBody"></div>';
      $$("[data-sub]", root).forEach(b => b.onclick = () => go(id, { sub: b.dataset.sub }));
      const t = tabs.find(x => x[0] === v.sub), key = id + ":" + v.sub;
      t[2]($("#subBody", root), S.view[key] || (S.view[key] = {}));
    };
  }
  function go(id, opts, noPush) {
    let target = id;
    if (ALIAS[id]) { const [p, s] = ALIAS[id]; id = p; (S.view[p] = S.view[p] || {}).sub = s; target = p + ":" + s; }
    else if (SUBS[id] && opts) { const s = opts.sub || SUBS[id][0][0]; (S.view[id] = S.view[id] || {}).sub = s; target = id + ":" + s; opts = Object.assign({}, opts); delete opts.sub; }
    if (!MENU.find(x => x.id === id)) return;
    if (!open.includes(id)) open.push(id);
    const before = cur + ":" + ((S.view[cur] || {}).sub || "");
    if (!noPush && id + ":" + ((S.view[id] || {}).sub || "") !== before) { hist.push(before); if (hist.length > 30) hist.shift(); }
    cur = id;
    if (opts && Object.keys(opts).length) S.view[target] = Object.assign(S.view[target] || {}, opts);
    render();
  }
  function back() {
    while (hist.length) {
      const [p, s] = hist.pop().split(":");
      if (MENU.find(x => x.id === p) && (p !== cur || s !== ((S.view[cur] || {}).sub || ""))) { if (s) (S.view[p] = S.view[p] || {}).sub = s; go(p, null, true); return; }
    }
    go("home", null, true);
  }
  function closeTab(id) { if (id === "home") return; const i = open.indexOf(id); open.splice(i, 1); if (cur === id) cur = open[Math.max(0, i - 1)]; render(); }
  function renderMenu() {
    $("#menu").innerHTML = MENU.map(m => {
      if (m.grp) return '<li class="grp">' + m.grp + "</li>";
      const n = m.badge ? m.badge() : 0;
      return '<li class="it' + (m.id === cur ? " on" : "") + '" data-go="' + m.id + '">' + m.name + (n ? '<span class="cnt">' + n + "</span>" : "") + "</li>";
    }).join("");
    $$("#menu [data-go]").forEach(li => li.onclick = () => go(li.dataset.go));
    $("#tabs").innerHTML = open.map(id => { const m = MENU.find(x => x.id === id); return '<span class="tab' + (id === cur ? " on" : "") + '" data-tab="' + id + '">' + m.name + (id === "home" ? "" : '<button class="x" data-x="' + id + '">×</button>') + "</span>"; }).join("");
    $$("#tabs [data-tab]").forEach(t => t.onclick = e => { if (e.target.dataset.x) closeTab(e.target.dataset.x); else go(t.dataset.tab); });
    const m = MENU.find(x => x.id === cur), sub = SUBS[cur] && (SUBS[cur].find(t => t[0] === (S.view[cur] || {}).sub) || SUBS[cur][0]);
    $("#crumb").innerHTML = (hist.length || cur !== "home" ? '<button class="btn sm" id="backBtn">← 返回</button>' : "") + '<a id="crumbHome">首页</a> / <b>' + esc(m.crumb) + (sub ? " / " + esc(sub[1]) : "") + "</b>";
    if ($("#backBtn")) $("#backBtn").onclick = back;
    $("#crumbHome").onclick = () => go("home");
    $("#projInfo").innerHTML = (S.runs.length ? "已导入 " + S.runs.length + " 个批次" : "尚未导入数据") + "<small>" + (S.runs.length ? "失败用例 " + failed().filter(c => !c.parent).length + " 条" : "&nbsp;") + "</small>";
  }
  // 规则更新提醒：团队的规则文件变了（别人改过或同步了新版本）
  function notice() {
    const n = S.changelog.length, seen = S.settings.seenRules;
    if (seen === undefined || n <= seen) return "";
    const l = S.changelog[n - 1];
    return '<div class="notice"><b>判断规则已更新</b><span>' + esc(l.at) + " " + esc(l.by || "") + "：" + esc(l.what) + (n - seen > 1 ? "（共 " + (n - seen) + " 处修改）" : "") + '</span><span class="sp"></span><a data-go="changelog">查看</a><a id="ntOk">知道了</a></div>';
  }
  function render() {
    renderMenu();
    const c = $("#content");
    c.innerHTML = "";
    const nt = notice();
    const box = document.createElement("div"); c.appendChild(box);
    (PAGES[cur] || (r => { r.innerHTML = emptyBlock("页面不存在"); }))(box, S.view[cur] || (S.view[cur] = {}));
    if (nt) { box.insertAdjacentHTML("afterbegin", nt); bindGo(box); $("#ntOk").onclick = () => act("/api/settings", { key: "seenRules", value: S.changelog.length }); }
    if (drawerFn && drawerOpen()) drawerFn();
  }

  async function init() {
    $("#mask").onclick = closeDrawer; $("#drwX").onclick = closeDrawer; $("#dlgX").onclick = closeDialog;
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") closeDrawer();
      if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); if (drawerOpen()) closeDrawer(); else back(); }
    });
    await refresh(true);
    if (S.settings.seenRules === undefined) await api("/api/settings", { key: "seenRules", value: S.changelog.length }).then(() => { S.settings.seenRules = S.changelog.length; }).catch(() => {});
    render();
  }

  return { S, M, api, refresh, act, fileData, fileText, esc, $, $$, highlight, toast, copy, copyRich, showText, download, fetchDownload, now, runName, catTag, statusTag, planTag, caseLabel,
    emptyBlock, failed, lastRun, runSelect, catOptions, who, bindGo, noData, dialog, closeDialog, drawer, closeDrawer, drawerOpen, go, back, render, PAGES, composite, init };
})();
