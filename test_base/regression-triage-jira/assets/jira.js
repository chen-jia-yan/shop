/* 页面：Jira 提报（起草与审核、提交与导出）。草稿内容、检查、CSV、提交都由本机服务完成。 */
(function () {
  const A = APP, S = A.S, M = A.M, esc = A.esc, $ = A.$, $$ = A.$$;
  const SRC = { 脚本: "blue", AI: "purple", 人工: "orange" };
  const ST = { draft: ["待审核", "orange"], approved: ["已审核", "blue"], submitted: ["已提交", "green"], discarded: ["已放弃", "gray"] };
  const caseOf = d => S.byUid[d.uids[0]];
  const caseId = d => { const c = caseOf(d); return c ? c.id + (c.parent ? "（第2次）" : "") : "-"; };
  const upd = (d, act, data, msg) => A.act("/api/jira/update", { id: d.id, act, data: data || {} }, msg);

  /* ============================== 起草与审核 ============================== */
  function draftPage(root, v) {
    const C = S.jira;
    if (!S.runs.length) return A.noData(root);
    v.run = S.runs.find(r => r.id === v.run) ? v.run : A.lastRun(); v.st = v.st || "open";
    const used = new Set(); S.drafts.filter(d => d.status !== "discarded").forEach(d => d.uids.forEach(u => used.add(u)));
    const avail = A.failed(v.run).filter(c => !used.has(c.uid) && c.rerun !== "pass").sort((a, b) => a.seq - b.seq || (a.parent ? 1 : -1));
    const skipped = A.failed(v.run).filter(c => c.rerun === "pass").length;
    if (!v.pick || v.pickRun !== v.run) { v.pick = avail.filter(c => C.draftCats.includes(c.final)).map(c => c.uid); v.pickRun = v.run; }
    v.pick = v.pick.filter(u => avail.some(c => c.uid === u));
    const drafts = S.drafts.filter(d => d.run === v.run && (v.st === "all" || (v.st === "open" ? ["draft", "approved"].includes(d.status) : d.status === v.st)))
      .sort((a, b) => ((caseOf(a) || {}).seq || 0) - ((caseOf(b) || {}).seq || 0));
    if (!v.cur || !drafts.find(d => d.id === v.cur)) v.cur = drafts[0] ? drafts[0].id : null;
    if (v.availOpen === undefined) v.availOpen = !drafts.length;
    let html = '<div class="card"><div class="form"><label class="fi"><span>批次</span>' + A.runSelect("jRun", v.run) + "</label>" +
      '<span class="hint">可起草 <b class="ink">' + avail.length + "</b> 条" + (skipped ? "；重跑通过 " + skipped + " 条不提单" : "") + '</span><span class="sp"></span><a id="jAvail">' + (v.availOpen ? "收起" : "选择用例（已选 " + v.pick.length + "）") + '</a><button class="btn sm pri" id="jGen"' + (v.pick.length ? "" : " disabled") + ">起草选中的 " + v.pick.length + " 个</button></div>";
    if (v.availOpen) html += '<div style="margin-top:8px"><div class="bar"><span class="hint">默认勾选：' + C.draftCats.map(k => M.CATS[k].name).join("、") + '</span><span class="sp"></span><button class="btn sm" id="jCats">起草范围</button><button class="btn sm" id="jPickAll">全选</button><button class="btn sm" id="jPickNone">全不选</button></div>' +
      (avail.length ? '<div class="tbl-wrap" style="max-height:300px"><table class="tbl"><thead><tr><th class="ck"></th><th>用例</th><th>名称</th><th>分类</th><th>判断依据</th><th>重跑</th></tr></thead><tbody>' + avail.map(c => '<tr class="' + (v.pick.includes(c.uid) ? "sel" : "") + '"><td class="ck"><input type="checkbox" data-jp="' + c.uid + '"' + (v.pick.includes(c.uid) ? " checked" : "") + '></td><td class="mono nw">' + A.caseLabel(c) + '</td><td class="nm">' + esc(c.name) + "</td><td>" + A.catTag(c.final) + '</td><td class="basis">' + esc(c.auto.brief) + '</td><td class="nw">' + A.planTag(c) + "</td></tr>").join("") + "</tbody></table></div>" : A.emptyBlock("没有可起草的用例")) + "</div>";
    html += "</div>";
    html += '<div class="jlay"><div class="card jlist"><div class="subtabs">' + [["open", "进行中"], ["submitted", "已提交"], ["discarded", "已放弃"], ["all", "全部"]].map(([k, n]) => '<button data-jst="' + k + '" class="' + (v.st === k ? "on" : "") + '">' + n + "</button>").join("") + "</div>" +
      (drafts.length ? drafts.map(d => { const c = caseOf(d); return '<div class="ji' + (d.id === v.cur ? " on" : "") + '" data-jd="' + d.id + '" title="' + esc(d.f.summary) + '"><span class="mono">' + esc(c ? c.id : "?") + (c && c.parent ? "·2" : "") + "</span>" + A.catTag(c ? c.final : d.cat) + '<span class="sp"></span>' + (d.status === "draft" && d.val.errs.length ? '<span class="tag red">' + d.val.errs.length + "</span>" : "") + '<span class="tag ' + ST[d.status][1] + '">' + ST[d.status][0] + "</span></div>"; }).join("") : '<div class="empty">没有草稿</div>') + "</div>";
    const d = v.cur ? S.drafts.find(x => x.id === v.cur) : null;
    html += '<div class="card jform">' + (d ? form(d, v) : A.emptyBlock("请选择左侧的草稿")) + "</div></div>";
    root.innerHTML = html;
    $("#jRun").onchange = e => { v.run = e.target.value; v.cur = null; A.render(); };
    $("#jAvail").onclick = () => { v.availOpen = !v.availOpen; A.render(); };
    if ($("#jCats")) $("#jCats").onclick = () => catsDialog(v);
    if ($("#jPickAll")) $("#jPickAll").onclick = () => { v.pick = avail.map(c => c.uid); A.render(); };
    if ($("#jPickNone")) $("#jPickNone").onclick = () => { v.pick = []; A.render(); };
    $$("[data-jp]", root).forEach(cb => cb.onchange = () => { const u = cb.dataset.jp; v.pick = cb.checked ? v.pick.concat(u) : v.pick.filter(x => x !== u); A.render(); });
    $("#jGen").onclick = async () => {
      const r = await A.api("/api/jira/new", { uids: v.pick }).catch(e => { A.toast(e.message, true); return null; });
      if (!r) return;
      v.st = "open"; v.cur = r.ids[0]; v.tab = "preview"; v.availOpen = false;
      await A.refresh(); A.toast("已起草 " + r.ids.length + " 张");
    };
    $$("[data-jst]", root).forEach(b => b.onclick = () => { v.st = b.dataset.jst; v.cur = null; A.render(); });
    $$("[data-jd]", root).forEach(el => el.onclick = () => { v.cur = el.dataset.jd; v.tab = "preview"; A.render(); });
    if (d) bindForm(root, d, v);
  }
  function catsDialog(v) {
    const C = S.jira;
    A.dialog("起草范围", '<p style="margin-top:0">默认勾选哪些分类？</p>' + Object.keys(M.CATS).map(k => '<label style="display:flex;gap:8px;align-items:center;margin:6px 0"><input type="checkbox" data-dcat="' + k + '"' + (C.draftCats.includes(k) ? " checked" : "") + ">" + A.catTag(k) + "</label>").join(""),
      [{ t: "取消" }, { t: "保存", pri: true, fn: () => { v.pick = null; return A.act("/api/jira/cfg", { cfg: { draftCats: $$("[data-dcat]").filter(x => x.checked).map(x => x.dataset.dcat) } }, "已保存"); } }]);
  }

  const srcTag = s => '<span class="tag ' + (SRC[s] || "gray") + ' xs">' + (s || "脚本") + "</span>";
  function form(d, v) {
    v.tab = v.tab || "preview";
    const c = caseOf(d), lock = d.status === "submitted";
    let h = '<div class="bar"><span class="tag ' + ST[d.status][1] + '">' + ST[d.status][0] + "</span>" + (d.issueKey ? '<span class="tag green">' + esc(d.issueKey) + "</span>" : "") + '<span class="hint">起草于 ' + esc(d.created) + (d.reviewedAt ? " · 审核于 " + esc(d.reviewedAt) : "") + '</span><span class="sp"></span>' +
      '<div class="seg"><button data-jt="preview" class="' + (v.tab === "preview" ? "on" : "") + '">① 预览</button><button data-jt="edit" class="' + (v.tab === "edit" ? "on" : "") + '"' + (lock || d.v !== 2 ? " disabled" : "") + ">② 编辑</button></div></div>";
    if (c) h += '<div class="verdict info"><b class="mono">' + esc(c.id) + "</b>" + (c.parent ? '<span class="tag orange">重跑第2次的新问题</span>' : c.rerun === "fail" ? '<span class="tag orange">重跑仍失败</span>' : "") + " " + esc(c.name || "") + " · " + A.catTag(c.final) + " " + esc(c.auto.brief) + ' <a data-jopen="' + c.uid + '">看证据</a></div>';
    if (v.tab !== "edit" || lock || d.v !== 2) return h + preview(d) + checksBlock(d, lock) + actions(d, lock);
    const C = S.jira, dis = lock ? " disabled" : "";
    const row = (k, input, extra) => '<label class="frow"><span>' + M.JIRA_FIELDS[k] + " " + srcTag(d.src[k]) + "</span><div>" + input + (extra || "") + "</div></label>";
    const txt = (k, ph) => '<input class="inp" style="width:100%" data-jf="' + k + '" value="' + esc(d.f[k]) + '" placeholder="' + esc(ph || "") + '"' + dis + ">";
    const sel = (k, opts) => '<select class="sel" data-jf="' + k + '"' + dis + ">" + opts.map(o => "<option" + (d.f[k] === o ? " selected" : "") + ">" + o + "</option>").join("") + "</select>";
    h += '<div class="sec"><h5>1. Title</h5>' + row("summary", txt("summary"), '<div class="hint">' + d.f.summary.length + " / 255</div>") + "</div>";
    h += '<div class="sec"><h5>2. Description <span class="sp"></span><button class="btn sm" id="jAI">复制给 AI 润色</button><button class="btn sm" id="jPaste">粘贴 AI 结果</button></h5>' +
      row("desc", '<textarea class="ta" rows="' + Math.min(14, Math.max(6, d.f.desc.split("\n").length + 1)) + '" data-jf="desc"' + dis + ">" + esc(d.f.desc) + "</textarea>") +
      row("data", '<textarea class="ta" rows="3" data-jf="data" placeholder="agent code: 48100"' + dis + ">" + esc(d.f.data) + "</textarea>") + "</div>";
    h += '<div class="sec"><h5>3. Details</h5><div class="form" style="margin-bottom:8px"><label class="fi"><span>提交方式</span><select class="sel" id="jMode"><option value="create"' + (d.mode === "create" ? " selected" : "") + '>新建 Jira 单</option><option value="comment"' + (d.mode === "comment" ? " selected" : "") + ">追加评论到已有单</option></select></label>" +
      (d.mode === "comment" ? '<label class="fi"><span>已有单号</span><input class="inp" id="jTarget" value="' + esc(d.target) + '" placeholder="ROTQA-5339"></label>' : "") + '<span class="hint">项目 ' + esc(C.project) + "</span></div>" +
      '<div class="fgrid">' + row("issueType", sel("issueType", Array.from(new Set([C.issueType, C.issueTypeEnv, "Bug", "Task"])))) +
      row("priority", sel("priority", ["Highest", "High", "Medium", "Low", "Lowest"]), d.meta ? '<div class="hint">' + esc(d.meta.priorityWhy) + "</div>" : "") +
      row("system", txt("system")) + row("components", txt("components")) + row("labels", txt("labels")) + "</div>" +
      row("environment", '<textarea class="ta" rows="4" data-jf="environment">' + esc(d.f.environment) + "</textarea>") + "</div>";
    return h + checksBlock(d, lock) + actions(d, lock);
  }
  function checksBlock(d, lock) {
    const val = d.val;
    return '<div class="sec"><h5>提交前检查</h5>' + (val.errs.length || val.warns.length ? "" : '<div class="verdict">全部通过</div>') +
      val.errs.map(e => '<div class="verdict err">必须修改：' + esc(e) + (/个人信息/.test(e) && !lock ? ' <a id="jMask">一键脱敏</a>' : "") + "</div>").join("") +
      val.warns.map(w => '<div class="verdict sus">请确认：' + esc(w.t) + (w.k === "sus" && !lock ? '<label style="display:flex;gap:6px;align-items:center;margin-top:4px"><input type="checkbox" id="jAck"' + (d.ack ? " checked" : "") + ">已看过证据，确认提这张单</label>" : "") + "</div>").join("") + "</div>" +
      (d.history.length ? '<details class="sec"><summary class="hint">记录（' + d.history.length + '）</summary><div class="hint">' + d.history.slice(-8).map(esc).join("<br>") + "</div></details>" : "");
  }
  function actions(d, lock) {
    let h = '<div class="acts-row">';
    if (lock || d.v !== 2) h += '<button class="btn" id="jCopy">复制 Description</button>';
    else {
      h += '<button class="btn dang" id="jDiscard">' + (d.status === "discarded" ? "恢复草稿" : "放弃这张单") + '</button><button class="btn" id="jRefresh">按最新分诊刷新</button><button class="btn" id="jCopy">复制 Description</button>';
      h += d.status === "approved" ? '<button class="btn" id="jUnapprove">撤回审核</button><button class="btn pri" data-go="jira" data-opts=\'{"sub":"submit"}\'>去提交</button>' : d.status === "draft" ? '<button class="btn pri" id="jApprove"' + (d.val.ok ? "" : " disabled") + ">审核通过</button>" : "";
    }
    return h + "</div>";
  }
  function bindForm(root, d, v) {
    A.bindGo(root);
    $$("[data-jt]", root).forEach(b => b.onclick = () => { v.tab = b.dataset.jt; A.render(); });
    $$("[data-jopen]", root).forEach(a => a.onclick = () => A.openCase(a.dataset.jopen));
    $$("[data-pimg]", root).forEach(img => img.onclick = () => { A.dialog("截图", '<img src="' + img.src + '" style="max-width:100%">', [{ t: "关闭" }]); $("#dlg").style.width = "90vw"; });
    $$("[data-jf]", root).forEach(el => el.onchange = () => { if (d.f[el.dataset.jf] !== el.value) upd(d, "fields", { f: { [el.dataset.jf]: el.value } }); });
    if ($("#jMode")) $("#jMode").onchange = e => upd(d, "mode", { mode: e.target.value, target: d.target });
    if ($("#jTarget")) $("#jTarget").onchange = e => upd(d, "mode", { mode: d.mode, target: e.target.value });
    if ($("#jAck")) $("#jAck").onchange = e => upd(d, "ack", { ack: e.target.checked });
    if ($("#jMask")) $("#jMask").onclick = () => upd(d, "mask", null, "已脱敏");
    if ($("#jAI")) $("#jAI").onclick = async () => { const r = await A.api("/api/jira/ai", { id: d.id }).catch(e => A.toast(e.message, true)); if (r) A.showText("给 AI 润色的材料", r.text); };
    if ($("#jPaste")) $("#jPaste").onclick = () => A.dialog("粘贴 AI 结果", '<textarea class="ta" id="jAiIn" rows="14" placeholder="按【Title cause】【Description】格式返回的内容"></textarea>',
      [{ t: "取消" }, { t: "填入", pri: true, fn: async () => (await A.act("/api/jira/aifill", { id: d.id, text: $("#jAiIn").value }, "已填入，请核对")) ? true : false }]);
    $("#jCopy").onclick = () => A.copy(d.wiki);
    if ($("#jRefresh")) $("#jRefresh").onclick = () => upd(d, "refresh", null, "已刷新；改过的字段没有变");
    if ($("#jDiscard")) $("#jDiscard").onclick = () => upd(d, "discard");
    if ($("#jUnapprove")) $("#jUnapprove").onclick = () => upd(d, "unapprove");
    if ($("#jApprove")) $("#jApprove").onclick = () => A.dialog("审核通过", '<p style="margin-top:0">确认：原因有证据、没有编造、没有个人信息。</p>',
      [{ t: "取消" }, { t: "确认通过", pri: true, fn: async () => !!(await upd(d, "approve", {}, "已审核通过")) }]);
  }

  function renderWiki(t, srcOf) {
    const out = []; let list = null, inNo = false, pre = [];
    const inline = s => esc(s).replace(/\{\{(.+?)\}\}/g, "<code>$1</code>").replace(/\*([^*\n]+)\*/g, "<b>$1</b>")
      .replace(/!([^!|]+)\|thumbnail!/g, (_, n) => { const src = srcOf(n.replace(/&amp;/g, "&")); return src ? '<img class="pimg" src="' + src + '" data-pimg alt="" title="' + n + '">' : '<span class="tag gray">截图 ' + n + "</span>"; });
    const close = () => { if (list) { out.push("</ul>"); list = null; } };
    String(t || "").split("\n").forEach(l => {
      if (l.trim() === "{noformat}") { if (inNo) { out.push("<pre>" + esc(pre.join("\n")) + "</pre>"); pre = []; } else close(); inNo = !inNo; return; }
      if (inNo) { pre.push(l); return; }
      let m;
      if ((m = /^h(\d)\.\s*(.*)/.exec(l))) { close(); out.push("<h4>" + inline(m[2]) + "</h4>"); }
      else if ((m = /^[*#]\s+(.*)/.exec(l))) { if (!list) { out.push("<ul>"); list = "ul"; } out.push("<li>" + inline(m[1]) + "</li>"); }
      else { close(); if (l.trim()) out.push("<p>" + inline(l) + "</p>"); }
    });
    if (inNo && pre.length) out.push("<pre>" + esc(pre.join("\n")) + "</pre>");
    close();
    return out.join("");
  }
  const base = p => String(p || "").split(/[\\/]/).pop().trim();
  function preview(d) {
    const C = S.jira, c = caseOf(d), pool = c ? c.shots.concat(c.shots2) : [];
    const srcOf = n => { const s = pool.find(x => base(x.name) === n); return s && s.src; };
    const det = [["Project", C.project], ["Issue Type", d.f.issueType], ["Priority", d.f.priority], ["Labels", d.labelsAll.join(", ")], ["Components", d.f.components], ["System", d.f.system]]
      .concat(C.envMode === "field" ? [["Environment", d.f.environment]] : []).concat([["提交方式", d.mode === "comment" ? "追加评论到 " + d.target : "新建"], ["附件", (d.meta ? d.meta.attach : []).join(", ") || "无"]]);
    return '<table class="ptbl"><tr class="ph"><td colspan="2">1. Title</td></tr><tr><th class="pk">Summary</th><td class="pv"><b>' + esc(d.f.summary) + "</b></td></tr>" +
      '<tr class="ph"><td colspan="2">2. Description</td></tr><tr><td class="pv wiki" colspan="2">' + renderWiki(d.wiki, srcOf) + "</td></tr>" +
      '<tr class="ph"><td colspan="2">3. Details</td></tr>' + det.map(([k, val]) => '<tr><th class="pk">' + k + '</th><td class="pv pre">' + esc(val) + "</td></tr>").join("") + "</table>";
  }

  /* ============================== 提交与导出 ============================== */
  function submitPage(root, v) {
    const C = S.jira, ready = S.drafts.filter(d => d.status === "approved");
    v.sel = (v.sel || ready.map(d => d.id)).filter(id => ready.find(d => d.id === id));
    const pick = ready.filter(d => v.sel.includes(d.id)), sub = S.drafts.filter(d => d.status === "submitted");
    const creates = pick.filter(d => d.mode === "create");
    let html = '<div class="kpis">' + [["待审核", S.drafts.filter(d => d.status === "draft").length, "#e6a23c"], ["已审核待提交", ready.length, "#409eff"], ["已提交", sub.length, "#67c23a"], ["已放弃", S.drafts.filter(d => d.status === "discarded").length, "#909399"]]
      .map(([l, n, c]) => '<div class="kpi" style="--c:' + c + '"><b>' + n + "</b><span>" + l + "</span></div>").join("") + "</div>";
    html += '<div class="card"><div class="card-h"><b>已审核待提交</b><span class="sp"></span><button class="btn sm" data-go="jira" data-opts=\'{"sub":"draft"}\'>回到起草</button></div>' +
      (ready.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr><th class="ck"><input type="checkbox" id="sAll"' + (pick.length === ready.length ? " checked" : "") + "></th><th>用例</th><th>标题</th><th>方式</th><th>Priority</th><th>附件</th><th>操作</th></tr></thead><tbody>" +
        ready.map(d => '<tr><td class="ck"><input type="checkbox" data-ss="' + d.id + '"' + (v.sel.includes(d.id) ? " checked" : "") + '></td><td class="mono nw">' + esc(caseId(d)) + '</td><td class="nm2">' + esc(d.f.summary) + "</td><td>" + (d.mode === "create" ? '<span class="tag blue">新建</span>' : '<span class="tag purple">追加到 ' + esc(d.target) + "</span>") + "</td><td>" + esc(d.f.priority) + "</td><td>" + (d.meta ? d.meta.attach.length : 0) + '</td><td class="ops nw"><a data-sopen="' + d.id + '">查看</a><a data-skey="' + d.id + '">回填单号</a></td></tr>').join("") + "</tbody></table></div>"
        : A.emptyBlock("没有已审核的单")) + "</div>";
    html += '<div class="card"><div class="card-h"><b>提交方式</b><span class="hint">已选 ' + pick.length + " 张</span></div><div class=\"flow\">" +
      '<div class="step"><h6><span class="n ' + (M.jiraEnv ? "auto" : "later") + '">A</span>直接提交到 Jira</h6><p>' + (M.jiraEnv ? "先预检（查重、确认单号存在），确认后建单并上传截图，单号自动回填。" : "需要在本机环境变量设置 JIRA_BASE_URL、JIRA_API_TOKEN" + (C.deploy === "cloud" ? "、JIRA_EMAIL" : "") + "，然后重新打开助手。") + '</p><div class="acts-row l"><button class="btn sm" id="sPayload"' + (pick.length ? "" : " disabled") + '>查看请求内容</button><button class="btn sm pri" id="sSubmit"' + (pick.length && M.jiraEnv ? "" : " disabled") + ">预检</button></div></div>" +
      '<div class="step"><h6><span class="n you">B</span>导出 Jira CSV</h6><p>Jira 外部系统导入 → CSV。截图建单后手动上传。只含“新建”的单。</p><div class="acts-row l"><button class="btn sm" id="sCsv"' + (creates.length ? "" : " disabled") + ">导出 CSV</button></div></div>" +
      '<div class="step"><h6><span class="n you">C</span>复制到 Jira 网页</h6><p>复制标题和描述（Jira 文本格式）。</p><div class="acts-row l"><button class="btn sm" id="sCopyAll"' + (pick.length ? "" : " disabled") + ">复制全部</button></div></div></div></div>";
    html += '<div class="card"><div class="card-h"><b>已提交的单</b></div>' + (sub.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>单号</th><th>用例</th><th>标题</th><th>提交时间</th></tr></thead><tbody>' + sub.map(d => '<tr><td class="mono">' + (C.baseUrl && d.issueKey ? '<a href="' + esc(C.baseUrl.replace(/\/$/, "") + "/browse/" + d.issueKey) + '" target="_blank" rel="noopener">' + esc(d.issueKey) + "</a>" : esc(d.issueKey || "-")) + '</td><td class="mono nw">' + esc(caseId(d)) + '</td><td class="nm2">' + esc(d.f.summary) + "</td><td>" + esc(d.submittedAt || "") + "</td></tr>").join("") + "</tbody></table></div>" : '<p class="hint" style="margin:0">还没有。</p>') +
      (S.jiraLog.length ? '<details style="margin-top:8px"><summary class="hint">提交记录（' + S.jiraLog.length + '）</summary><div class="tbl-wrap"><table class="tbl mini"><thead><tr><th>时间</th><th>方式</th><th>单数</th><th>结果</th><th>操作人</th></tr></thead><tbody>' + S.jiraLog.slice().reverse().map(l => "<tr><td>" + esc(l.at) + "</td><td>" + esc(l.how) + "</td><td>" + l.n + "</td><td>" + esc(l.result) + "</td><td>" + esc(l.by || "") + "</td></tr>").join("") + "</tbody></table></div></details>" : "") + "</div>";
    root.innerHTML = html;
    A.bindGo(root);
    $$("[data-ss]", root).forEach(cb => cb.onchange = () => { const id = cb.dataset.ss; v.sel = cb.checked ? v.sel.concat(id) : v.sel.filter(x => x !== id); A.render(); });
    if ($("#sAll")) $("#sAll").onchange = e => { v.sel = e.target.checked ? ready.map(d => d.id) : []; A.render(); };
    $$("[data-sopen]", root).forEach(a => a.onclick = () => { const d = S.drafts.find(x => x.id === a.dataset.sopen); A.go("jira", { sub: "draft", run: d.run, cur: d.id, st: "open", tab: "preview" }); });
    $$("[data-skey]", root).forEach(a => a.onclick = () => keyDialog(S.drafts.find(x => x.id === a.dataset.skey)));
    const ids = pick.map(d => d.id);
    $("#sCsv").onclick = async () => { const r = await A.act("/api/jira/csv", { ids: creates.map(d => d.id) }); if (r) A.download("jira_import_" + new Date().toISOString().slice(0, 10) + ".csv", r.text, "text/csv;charset=utf-8"); };
    $("#sCopyAll").onclick = () => A.showText("标题和描述", pick.map((d, i) => "#" + (i + 1) + " " + caseId(d) + (d.mode === "comment" ? " 追加评论到 " + d.target : "") + "\nSummary: " + d.f.summary + "\nPriority: " + d.f.priority + "\nLabels: " + d.labelsAll.join(", ") + (C.envMode === "field" ? "\nEnvironment:\n" + d.f.environment : "") + "\n\nDescription:\n" + d.wiki).join("\n\n====================\n\n"));
    $("#sPayload").onclick = async () => { const r = await A.api("/api/jira/payload", { ids }).catch(e => A.toast(e.message, true)); if (r) A.showText("提交到 Jira 的内容", JSON.stringify(r.items, null, 2)); };
    $("#sSubmit").onclick = () => submit(ids, true);
  }
  function resultTable(list, dry) {
    return '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>用例</th><th>结果</th><th>说明</th></tr></thead><tbody>' + list.map(r => { const d = S.drafts.find(x => x.id === r.draftId) || { uids: [] };
      return '<tr><td class="mono">' + esc(caseId(d)) + "</td><td>" + (r.error ? '<span class="tag red">失败</span>' : r.duplicateOf ? '<span class="tag orange">疑似重复</span>' : r.key ? '<span class="tag green">' + esc(r.key) + "</span>" : dry ? '<span class="tag blue">可以提交</span>' : "-") + "</td><td>" + esc(r.error || (r.duplicateOf ? "已有 " + r.duplicateOf + "（" + (r.duplicateSummary || "") + "）" : r.message || "")) + "</td></tr>"; }).join("") + "</tbody></table></div>";
  }
  async function submit(ids, dry) {
    A.toast(dry ? "正在预检…" : "正在提交…");
    const r = await A.act("/api/jira/submit", { ids, dryRun: dry });
    if (!r) return;
    const res = r.results;
    if (dry) {
      const ok = res.filter(x => !x.error && !x.key).map(x => x.draftId);
      A.dialog("预检结果（还没有写入 Jira）", resultTable(res, true) + '<p class="hint">疑似重复的单可以回到起草页改为“追加评论”。</p>', [{ t: "取消" }].concat(ok.length ? [{ t: "正式提交 " + ok.length + " 张", pri: true, fn: () => { setTimeout(() => submit(ok, false), 50); } }] : []));
    } else A.dialog("提交结果", resultTable(res, false), [{ t: "关闭" }]);
  }
  function keyDialog(d) {
    A.dialog("回填 Jira 单号", '<p style="margin-top:0">' + esc(caseId(d)) + " · " + esc(d.f.summary) + '</p><label class="fi"><span>单号</span><input class="inp" id="kIn" value="' + esc(d.mode === "comment" ? d.target : d.issueKey || "") + '" placeholder="ROTQA-5339"></label>',
      [{ t: "取消" }, { t: "保存", pri: true, fn: async () => !!(await upd(d, "key", { key: $("#kIn").value }, "已回填")) }]);
  }

  A.composite("jira", [["draft", "起草与审核", draftPage, () => S.drafts.filter(d => d.status === "draft").length], ["submit", "提交与导出", submitPage, () => S.drafts.filter(d => d.status === "approved").length]]);
})();
