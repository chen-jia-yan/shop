/* 页面：工作台（概览、分类与重跑标准）、数据导入（字段对应、补充截图） */
(function () {
  const A = APP, S = A.S, M = A.M, esc = A.esc, $ = A.$, $$ = A.$$;
  const CAT_ORDER = ["ENVIRONMENT", "PRODUCT_DEFECT", "SCRIPT_ISSUE", "TEST_DATA", "POPUP_INTERFERENCE", "NEEDS_HUMAN"];
  const NEXT = { ENVIRONMENT: "测试联系环境负责人，恢复后重跑", POPUP_INTERFERENCE: "补充弹窗处理，重跑确认", SCRIPT_ISSUE: "修脚本，修好后重跑", TEST_DATA: "补数据或换数据后重跑", PRODUCT_DEFECT: "确认后起草 Jira", NEEDS_HUMAN: "让 AI 看截图，或人工确认后改分类" };
  A.NEXT = NEXT; A.CAT_ORDER = CAT_ORDER;

  /* ============================== 工作台 · 概览 ============================== */
  const kpi = (n, label, color, goId, opts) => goId ? '<button class="kpi" style="--c:' + color + '" data-go="' + goId + '"' + (opts ? " data-opts='" + JSON.stringify(opts) + "'" : "") + "><b>" + n + "</b><span>" + label + " ›</span></button>"
    : '<div class="kpi" style="--c:' + color + '"><b>' + n + "</b><span>" + label + "</span></div>";
  // 仪表盘：通过率、失败原因分布、处理进度、同一报错出现最多
  const DB_COLOR = { ENVIRONMENT: "#6250d6", PRODUCT_DEFECT: "#e34948", SCRIPT_ISSUE: "#2a78d6", TEST_DATA: "#1baf7a", POPUP_INTERFERENCE: "#eb6834", NEEDS_HUMAN: "#9a9fa8" };
  const looked = c => !!((c.obs && c.obs.by === "AI") || c.ai);
  const needLook = c => looked(c) || (!c.override && (c.auto.status !== "confirmed" || c.auto.cat === "NEEDS_HUMAN"));
  const num = (n, dec) => '<span class="db-n" data-count="' + n + '"' + (dec ? ' data-dec="' + dec + '"' : "") + ">" + n.toFixed(dec || 0) + "</span>";
  const goAttr = (id, o) => ' data-go="' + id + '"' + (o ? ' data-opts="' + esc(JSON.stringify(o)) + '"' : "");
  function dashboard(v) {
    if (v.scope === undefined || (v.scope && !S.runs.some(r => r.id === v.scope))) v.scope = A.lastRun();
    const runs = v.scope ? S.runs.filter(r => r.id === v.scope) : S.runs, one = v.scope ? runs[0] : null, run = v.scope || A.lastRun();
    const f = A.failed(v.scope), base = f.filter(c => !c.parent);
    const total = runs.reduce((a, r) => a + r.total, 0), pass = total ? Math.max(0, total - base.length) * 100 / total : 0;
    // “较上批”只和同一环境的上一个批次比
    const prev = one ? S.runs.slice(0, S.runs.indexOf(one)).reverse().find(r => (r.env || "") === (one.env || "")) : null, pf = prev ? A.failed(prev.id).filter(c => !c.parent).length : 0;
    const conf = base.filter(c => !c.override && !c.aiUsed && c.auto.status === "confirmed").length;
    const need = f.filter(needLook), lk = need.filter(looked).length;
    const sus = f.filter(c => !c.override && c.auto.status === "suspected").length, rev = f.filter(c => c.override).length;
    const rr = base.filter(c => c.plan.b === "go" || c.rerun), rrDone = rr.filter(c => c.rerun).length;
    const ds = S.drafts.filter(d => d.status !== "discarded" && (!v.scope || d.run === v.scope)), sub = ds.filter(d => d.status === "submitted").length;
    const defects = base.filter(c => c.final === "PRODUCT_DEFECT").length;
    const dTotal = prev ? '<span class="db-d">较上批 ' + (total - prev.total >= 0 ? "+" : "") + (total - prev.total) + "</span>" : "";
    const dFail = prev ? '<span class="db-d ' + (base.length > pf ? "bad" : base.length < pf ? "good" : "") + '">' + (base.length > pf ? "▲ " + (base.length - pf) : base.length < pf ? "▼ " + (pf - base.length) : "与上批持平") + "</span>" : "";
    const L = 2 * Math.PI * 58, arcV = L * pass / 100;

    let h = '<div class="dash"><div class="db-top"><div><b class="db-t">概览</b><div class="hint">' +
      (one ? esc(one.name) + " · 导入于 " + esc(one.at) + (one.env ? " · " + esc(one.env) : "") : "全部 " + S.runs.length + " 个批次") + "</div></div>" +
      '<span class="db-chip"><i class="db-live' + (lk < need.length ? " wait" : "") + '"></i>' + (need.length ? "AI 看图 " + num(lk) + " / " + need.length : "无需 AI 看图") + "</span>" +
      '<span class="sp"></span>' + A.runSelect("dbRun", v.scope, true) + '<button class="btn sm" id="dbPlay">重播动画</button><button class="btn sm pri" data-go="import">导入新批次</button></div><div class="db-grid">';

    // 通过率
    h += '<div class="db-card db-hero" style="--d:0s"><div class="db-gauge"><svg viewBox="0 0 150 150" aria-label="通过率 ' + pass.toFixed(1) + '%"><defs><linearGradient id="dbGg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#2a78d6"/><stop offset="1" stop-color="#19b4d8"/></linearGradient></defs>' +
      '<g class="db-rot"><circle cx="75" cy="75" r="71" fill="none" stroke="#c9d6e8" stroke-dasharray="2 6"/></g><circle cx="75" cy="75" r="58" fill="none" stroke="#edf1f6" stroke-width="10"/>' +
      '<circle id="dbArc" cx="75" cy="75" r="58" fill="none" stroke="url(#dbGg)" stroke-width="10" stroke-linecap="round" transform="rotate(-90 75 75)" data-l="' + L + '" data-v="' + arcV + '" style="stroke-dasharray:' + arcV + " " + L + '"/>' +
      '<circle cx="75" cy="75" r="45" fill="none" stroke="#edf1f6"/></svg><div class="db-gc">' + num(pass, 1) + "<span>通过率 %</span></div></div>" +
      '<div class="db-hs"><div class="db-hr"><span class="hint">执行用例</span>' + num(total) + dTotal + "</div>" +
      '<div class="db-hr click"' + goAttr("triage", { run, st: "" }) + '><span class="hint">失败用例</span><span class="red">' + num(base.length) + "</span>" + dFail + "</div>" +
      '<div class="db-hr"><span class="hint">规则直接确认</span>' + num(conf) + '<span class="db-d">' + (base.length ? "占失败 " + Math.round(conf * 100 / base.length) + "%" : "") + "</span></div></div></div>";

    // 失败原因分布
    const cats = CAT_ORDER.map(k => [k, f.filter(c => c.final === k).length]).filter(x => x[1]);
    h += '<div class="db-card db-dist" style="--d:.06s"><div class="db-h"><b>失败原因分布</b><span class="db-tag">' + f.length + ' 条</span><span class="sp"></span><span class="hint">点分类进入失败分诊</span></div>' +
      (!f.length ? '<div class="hint db-empty">' + (one ? "这个批次没有失败用例" : "没有失败用例") + "</div>" :
        '<div class="db-stack">' + cats.map(([k, n]) => '<div style="--sc:' + DB_COLOR[k] + ";width:" + n * 100 / f.length + '%" data-w="' + n * 100 / f.length + '" title="' + esc(M.CATS[k].name) + " " + n + ' 条"' + goAttr("triage", { run, open: [k] }) + "></div>").join("") + "</div>" +
        '<div class="db-cats">' + cats.map(([k, n]) => '<div class="db-cat"' + goAttr("triage", { run, open: [k] }) + ' style="--sc:' + DB_COLOR[k] + '"><i></i><span>' + esc(M.CATS[k].name) + "</span>" + num(n) + '<span class="db-p">' + Math.round(n * 100 / f.length) + "%</span></div>").join("") + "</div>") + "</div>";

    // 处理进度
    const steps = [
      ["导入", total + " 条", true, goAttr("import")],
      ["规则分诊", f.length + " 条失败", true, goAttr("triage", { run, st: "" })],
      ["AI 看图", need.length ? lk + " / " + need.length : "无需看图", lk >= need.length, goAttr("triage", { run, st: "" })],
      ["人工复核", sus ? "还剩 " + sus + " 条" : rev ? "已复核 " + rev + " 条" : "无需复核", !sus, goAttr("triage", { run, st: "sus" })],
      ["重跑", rr.length ? rrDone + " / " + rr.length : "无需重跑", rrDone >= rr.length, goAttr("rerun", { run, tab: "go" })],
      ["Jira", ds.length ? sub + " / " + ds.length + " 已提交" : defects ? defects + " 条待起草" : "无需提单", ds.length ? sub === ds.length : !defects, goAttr("jira")],
    ];
    let now = steps.findIndex(s => !s[2]);
    const pct = (now < 0 ? steps.length - 1 : now) * 100 / (steps.length - 1);
    h += '<div class="db-card db-pipe" style="--d:.12s"><div class="db-h"><b>处理进度</b><span class="sp"></span><span class="hint">' + (now < 0 ? "全部处理完成" : "当前在“" + steps[now][0] + "”") + '</span></div><div class="db-flow">' +
      '<div class="db-track"><div class="db-on" style="width:' + pct + '%" data-w="' + pct + '"></div>' + (now > 0 ? '<i class="db-dot" style="--w:' + pct + '%"></i>' : "") + "</div>" +
      steps.map((s, i) => '<div class="db-node ' + (s[2] ? "done" : i === now ? "now" : "") + '"' + s[3] + '><div class="db-nd">' + (s[2] ? "✓" : i + 1) + '</div><div class="db-nt">' + s[0] + '</div><div class="db-nv">' + esc(s[1]) + "</div></div>").join("") + "</div></div>";

    // 同一报错出现最多
    const bySig = {};
    base.forEach(c => (bySig[c.sig || c.uid] = bySig[c.sig || c.uid] || []).push(c));
    const top = Object.values(bySig).filter(g => g.length > 1).sort((a, b) => b.length - a.length).slice(0, 6), mx = top.length ? top[0].length : 1;
    h += '<div class="db-card db-errs" style="--d:.18s"><div class="db-h"><b>同一报错出现最多</b><span class="db-tag">' + (one ? "本批次" : "全部批次") + '</span><span class="sp"></span><span class="hint">点一条只看这些用例</span></div>' +
      (!top.length ? '<div class="hint db-empty">没有重复出现的报错</div>' : '<div class="db-el">' + top.map((g, i) => {
        const c = g[0], t = c.error1 || c.ruleName;
        return '<div class="db-err"' + goAttr("triage", { run: c.run, sig: c.sig, st: "" }) + ' style="--sc:' + DB_COLOR[c.final] + '"><span class="db-r">' + String(i + 1).padStart(2, "0") + '</span><div class="db-m"><div class="db-mt" title="' + esc(t) + '">' + esc(t) + '</div><div class="hint">' + esc(M.CATS[c.final].name) + " · " + esc(c.ruleName) + '</div><div class="db-bar"><i style="width:' + g.length * 100 / mx + '%" data-w="' + g.length * 100 / mx + '"></i></div></div>' + num(g.length) + "</div>";
      }).join("") + "</div>") + "</div>";

    return { html: h + "</div></div>", key: [v.scope || "all", total, f.length, lk, sus, rrDone, sub].join("|") };
  }
  // 数字滚动、环形和条形展开、卡片依次浮现；减少动态效果的系统设置下不播放
  function dbPlay(root) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const db = $(".dash", root); if (!db) return;
    db.classList.remove("db-anim"); void db.offsetWidth; db.classList.add("db-anim");
    $$("[data-count]", db).forEach(el => {
      const to = +el.dataset.count, dec = +(el.dataset.dec || 0), t0 = performance.now();
      el.textContent = (0).toFixed(dec);
      const step = t => { if (!el.isConnected) return; const k = Math.min(1, (t - t0) / 1100); el.textContent = (to * (1 - Math.pow(1 - k, 3))).toFixed(dec); if (k < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    });
    const bars = $$("[data-w]", db), arc = $("#dbArc", db);
    bars.forEach(b => { b.style.transition = "none"; b.style.width = "0"; });
    if (arc) { arc.style.transition = "none"; arc.style.strokeDasharray = "0 " + arc.dataset.l; }
    void db.offsetWidth;
    requestAnimationFrame(() => {
      bars.forEach(b => { b.style.transition = ""; b.style.width = b.dataset.w + "%"; });
      if (arc) { arc.style.transition = ""; arc.style.strokeDasharray = arc.dataset.v + " " + arc.dataset.l; }
    });
  }
  function overview(root, v) {
    if (!S.runs.length) {
      root.innerHTML = '<div class="card"><div class="card-h"><b>开始使用</b></div><div class="flow">' +
        '<div class="step"><h6><span class="n you">1</span>导入执行结果</h6><p>报告网页（.mhtml / .html）、JSON、CSV、JUnit、Allure，或粘贴表格。截图文字自动识别。</p></div>' +
        '<div class="step"><h6><span class="n auto">2</span>分析根本原因</h6><p>每条失败用例给出分类、判断依据和重跑建议。</p></div>' +
        '<div class="step"><h6><span class="n you">3</span>复核、重跑、分派、提 Jira</h6><p>在“失败分诊”和“Jira 提报”里完成。</p></div></div>' +
        '<div style="margin-top:10px"><button class="btn pri" data-go="import">去导入数据</button></div></div>';
      A.bindGo(root); return;
    }
    const d = dashboard(v);
    root.innerHTML = d.html + '<div class="card"><div class="card-h"><b>已导入批次</b></div>' + runTable() + "</div>";
    A.bindGo(root); bindRunTable(root);
    $("#dbRun").onchange = e => { v.scope = e.target.value; A.render(); };
    $("#dbPlay").onclick = () => dbPlay(root);
    // 只在第一次打开或数据变了时播放动画，页面刷新不重复播放
    if (v.played !== d.key) { v.played = d.key; dbPlay(root); }
  }
  function runTable() {
    return '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>批次名称</th><th>测试计划</th><th>设备</th><th>环境</th><th>导入时间</th><th>总数</th><th>失败</th><th>截图</th><th>操作</th></tr></thead><tbody>' +
      S.runs.slice().reverse().map(r => {
        const fs = A.failed(r.id), shots = fs.filter(c => c.shots.length).length;
        return "<tr><td>" + esc(r.name) + '<div class="hint clip" title="' + esc(r.file) + '">' + esc(r.file) + "</div></td><td>" + esc(r.plan || "-") + "</td><td>" + esc(r.device || "-") + "</td><td>" + esc(r.env || "-") + "</td><td>" + esc(r.at) + "</td><td>" + r.total + "</td><td>" + fs.filter(c => !c.parent).length + "</td><td>" + (shots ? shots + " 条" : "-") +
          '</td><td class="ops"><a data-run-view="' + r.id + '">分诊</a><a data-run-shot="' + r.id + '">补截图</a><a href="/api/export/cases.csv?run=' + r.id + '" download>导出</a><a data-run-del="' + r.id + '" class="red">删除</a></td></tr>';
      }).join("") + "</tbody></table></div>";
  }
  function bindRunTable(root) {
    $$("[data-run-view]", root).forEach(a => a.onclick = () => A.go("triage", { run: a.dataset.runView }));
    $$("[data-run-shot]", root).forEach(a => a.onclick = () => A.go("import", { shotRun: a.dataset.runShot }));
    $$("[data-run-del]", root).forEach(a => a.onclick = () => {
      const r = S.runs.find(x => x.id === a.dataset.runDel);
      A.dialog("删除批次", "确定删除“" + esc(r.name) + "”？人工记录、截图和未提交的草稿一起删除，无法恢复。", [{ t: "取消" }, { t: "删除", pri: true, fn: () => A.act("/api/run/delete", { run: r.id }, "已删除") }]);
    });
  }
  A.runTable = runTable; A.bindRunTable = bindRunTable;

  /* ============================== 工作台 · 分类与重跑标准 ============================== */
  function guide(root) {
    root.innerHTML = '<div class="card"><div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:110px">分类</th><th>什么情况下归入</th><th style="width:80px">处理方</th><th>容易误判的地方</th></tr></thead><tbody>' +
      [["ENVIRONMENT", "执行机没有可用桌面、浏览器/设备起不来、连接数据库或服务失败；同一报错在连续多个用例出现", "单个用例超时不算环境问题"],
       ["POPUP_INTERFERENCE", "与被测功能无关的弹窗挡住了操作（弹窗文字在干扰清单里）", "弹窗文字是系统报错（如 record not found）时按业务报错判断"],
       ["TEST_DATA", "系统提示数据被占用；人工核查确认数据不存在、已被使用或状态不对", "没有核查结果时不能下结论"],
       ["PRODUCT_DEFECT", "核查确认数据正常但系统仍报错；被测程序崩溃；断言期望值与实际值不同；页面没显示出来", "断言的期望值可能已经过时"],
       ["SCRIPT_ISSUE", "定位条件匹配到多个控件、定位写错、测试代码错误；截图显示页面正常但脚本没找到控件", "找不到元素也可能是页面没加载出来，要看截图"],
       ["NEEDS_HUMAN", "未知弹窗、需要核查的业务报错、证据不足、没有规则命中", "-"]].map(([k, w, x]) => "<tr><td>" + A.catTag(k) + "</td><td>" + w + "</td><td>" + M.CATS[k].owner + "</td><td>" + x + "</td></tr>").join("") + "</tbody></table></div>" +
      '<div class="card-h" style="margin-top:10px"><b>重跑标准</b></div><div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:110px">建议</th><th>适用情况</th><th>为什么</th></tr></thead><tbody>' +
      '<tr><td><span class="tag blue">建议立即重跑</span></td><td>环境问题（恢复后）、紧挨环境中断起点、弹窗干扰、找不到窗口或元素、控件不可见、断言不一致、停在别的页面、有残留窗口</td><td>可能是偶发</td></tr>' +
      '<tr><td><span class="tag orange">处理后再重跑</span></td><td>未核查的业务报错、数据被占用、缺少配置、测试数据问题、脚本问题、原因被掩盖、证据不足</td><td>不处理，结果不会变</td></tr>' +
      '<tr><td><span class="tag gray">不需要重跑</span></td><td>已确认的产品问题、重跑产生的第 2 次记录</td><td>结论已明确</td></tr></tbody></table></div>' +
      '<p class="hint" style="margin:6px 0 0">重跑结果不改变分类：通过 → 偶发，不提单；失败且同一问题 → 必现，两次写进同一张 Jira；失败但报错不同 → 第 2 次单独分析、单独提单。</p></div>';
  }
  A.composite("home", [["overview", "概览", overview], ["guide", "分类与重跑标准", guide]]);

  /* ============================== 数据导入 ============================== */
  const blankInfo = () => ({ name: "", plan: "", device: "", env: "", mode: "new", rerunOf: "" });
  const inp = (id, label, val, ph) => '<label class="fi"><span>' + label + '</span><input class="inp" id="' + id + '" value="' + esc(val) + '" placeholder="' + esc(ph) + '"></label>';
  A.PAGES.import = function (root, v) {
    v.info = v.info || blankInfo();
    let html = '<div class="card"><div class="card-h"><b>导入执行结果</b></div><div class="form" style="margin-bottom:8px">' +
      '<label class="fi"><span>导入类型</span><select class="sel" id="iMode"><option value="new">新的执行结果</option><option value="rerun"' + (v.info.mode === "rerun" ? " selected" : "") + (S.runs.length ? "" : " disabled") + ">重跑结果（更新已有批次）</option></select></label>" +
      (v.info.mode === "rerun" ? '<label class="fi"><span>原批次</span>' + A.runSelect("iRerunOf", v.info.rerunOf || A.lastRun()) + "</label>" : "") +
      inp("iName", "批次名称", v.info.name, "默认用文件名") + inp("iPlan", "测试计划", v.info.plan, "TestPlan000015") + inp("iDevice", "执行设备", v.info.device, "RGT_AVD_11") + inp("iEnv", "测试环境", v.info.env, "U401 / SIT") + "</div>" +
      '<div class="imp2"><div class="drop" id="drop"><b>拖入文件，或 <a id="pick">选择文件</a></b><span class="hint">报告网页（.mhtml / .html）、JSON、CSV、JUnit XML、Allure；可以多选</span><input type="file" id="file" multiple accept=".json,.csv,.tsv,.txt,.xml,.html,.htm,.mhtml,.mht" style="display:none"></div>' +
      '<div><textarea class="ta" id="paste" rows="4" placeholder="或粘贴：Excel / 报告页面上复制的表格（含表头），或接口返回的 JSON"></textarea><div style="margin-top:6px;display:flex;gap:6px"><button class="btn sm pri" id="pasteGo">解析粘贴内容</button><button class="btn sm" id="pasteClr">清空</button></div></div></div></div>';
    if (v.parsed) html += mapCard(v);
    html += shotCard(v);
    if (S.runs.length) html += '<div class="card"><div class="card-h"><b>已导入批次</b></div>' + runTable() + "</div>";
    root.innerHTML = html;

    const keep = () => { v.info.name = $("#iName").value; v.info.plan = $("#iPlan").value; v.info.device = $("#iDevice").value; v.info.env = $("#iEnv").value; if ($("#iRerunOf")) v.info.rerunOf = $("#iRerunOf").value; };
    $("#iMode").onchange = e => { keep(); v.info.mode = e.target.value; A.render(); };
    ["iName", "iPlan", "iDevice", "iEnv"].forEach(id => $("#" + id).oninput = keep);
    if ($("#iRerunOf")) $("#iRerunOf").onchange = keep;
    const drop = $("#drop");
    $("#pick").onclick = () => $("#file").click();
    $("#file").onchange = e => { keep(); handleFiles(Array.from(e.target.files), v); };
    drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); keep(); handleFiles(Array.from(e.dataTransfer.files), v); };
    $("#paste").onpaste = e => {
      const h = e.clipboardData && e.clipboardData.getData("text/html");
      if (h && /<table/i.test(h)) { e.preventDefault(); keep(); parse(v, { text: h, html: true }, "粘贴的网页表格"); }
    };
    $("#pasteGo").onclick = () => { const t = $("#paste").value.trim(); if (!t) { A.toast("请先粘贴内容", true); return; } keep(); parse(v, { text: t }, "粘贴内容"); };
    $("#pasteClr").onclick = () => { $("#paste").value = ""; };
    if (v.parsed) bindMap(root, v);
    bindShotCard(root, v);
    if (S.runs.length) bindRunTable(root);
  };

  async function handleFiles(files, v) {
    if (!files.length) return;
    // 手动生成的识别结果（自动识别不可用时的备用办法）
    const ocrF = files.filter(f => /\.ocr\.json$/i.test(f.name));
    for (const f of ocrF) await A.act("/api/ocr/import", { data: await A.fileData(f) }, r => "识别结果已导入，新增 " + r.n + " 张");
    files = files.filter(f => !ocrF.includes(f));
    if (!files.length) return;
    A.toast("正在读取 " + files.length + " 个文件…");
    const list = [];
    for (const f of files) list.push({ name: f.name, data: await A.fileData(f) });
    parse(v, { files: list }, files[0].name);
  }
  async function parse(v, body, first) {
    try {
      const p = await A.api("/api/parse", body);
      if (p.errors.length) A.toast("有 " + p.errors.length + " 个文件无法解析：" + p.errors[0], true);
      v.parsed = p; v.table = 0; v.map = p.map;
      if (!v.info.name) v.info.name = String(first || "").replace(/\.[^.]+$/, "");
      await preview(v);
      setTimeout(() => { const el = $("#mapCard"); if (el) el.scrollIntoView({ behavior: "smooth" }); }, 50);
    } catch (e) { A.toast(e.message, true); }
  }
  async function preview(v) {
    try { v.pv = await A.api("/api/parse/preview", { token: v.parsed.token, table: v.table, map: v.map }); }
    catch (e) { A.toast(e.message, true); v.parsed = null; }
    A.render();
  }
  function mapCard(v) {
    const p = v.parsed, t = p.tables[v.table], pv = v.pv || { n: 0, nFail: 0, resVals: [], missing: [], rows: [] };
    let html = '<div class="card" id="mapCard"><div class="card-h"><b>字段对应</b><span class="hint">' + esc(p.kind) + " · " + esc(p.files.join("、")).slice(0, 120) + "</span></div>";
    if (p.tables.length > 1) html += '<div class="form" style="margin-bottom:8px"><label class="fi"><span>用例列表</span><select class="sel" id="mTable">' + p.tables.map((x, i) => '<option value="' + i + '"' + (i === v.table ? " selected" : "") + ">" + esc(x.path) + "（" + x.nrows + " 行）</option>").join("") + "</select></label></div>";
    html += '<div class="map">' + M.FIELDS.map(f => "<label><span>" + f.name + (f.req ? "<i>*</i>" : "") + '</span><select class="sel" data-f="' + f.key + '"><option value="">（不使用）</option>' + t.cols.map(c => '<option value="' + esc(c) + '"' + (v.map[f.key] === c ? " selected" : "") + ">" + esc(c) + "</option>").join("") + "</select></label>").join("") + "</div>";
    html += '<div class="kpis" style="margin:10px 0 6px">' + kpi(pv.n, "共导入", "#409eff") + kpi(pv.nFail, "失败（要分析）", "#f56c6c") + kpi(pv.n - pv.nFail, "通过 / 其他", "#67c23a") + (p.images ? kpi(p.images, "内嵌截图", "#909399") : "") + "</div>";
    html += '<div style="margin:0 0 6px;display:flex;gap:14px;flex-wrap:wrap" class="hint"><span>执行结果：' + pv.resVals.map(([k, n]) => esc(k) + " × " + n).join("，") + '</span><a data-go="rules" data-opts=\'{"focus":"fail_words"}\'>失败判断不对？</a></div>';
    html += '<div style="margin-top:8px;display:flex;gap:6px;align-items:center">' + (pv.missing.length ? '<span class="hint red">请先对应：' + pv.missing.join("、") + "</span>" : "") +
      '<span class="sp"></span><button class="btn" id="mCancel">取消</button><button class="btn pri" id="mOk"' + (pv.missing.length ? " disabled" : "") + ">" + (v.info.mode === "rerun" ? "导入重跑结果" : "确认导入") + "</button></div></div>";
    return html;
  }
  function bindMap(root, v) {
    A.bindGo($("#mapCard"));
    if ($("#mTable")) $("#mTable").onchange = e => { v.table = +e.target.value; preview(v); };
    $$("[data-f]", root).forEach(s => s.onchange = () => { v.map[s.dataset.f] = s.value; if (!s.value) delete v.map[s.dataset.f]; preview(v); });
    $("#mCancel").onclick = () => { v.parsed = null; A.render(); };
    $("#mOk").onclick = async () => {
      $("#mOk").disabled = true;
      const r = await A.act("/api/import", { token: v.parsed.token, table: v.table, map: v.map, info: v.info }, r => r.msg);
      if (!r) { $("#mOk").disabled = false; return; }
      v.parsed = null; v.info = blankInfo();
      if (r.rerun) A.go("rerun", { run: r.run, tab: "done" }); else A.go("triage", { run: r.run, st: "", q: "", sig: "" });
    };
  }

  /* ---------- 补充截图：选中一条用例后 Ctrl+V，自动跳到下一条 ---------- */
  function shotCard(v) {
    if (!S.runs.length) return "";
    v.shotRun = S.runs.find(r => r.id === v.shotRun) ? v.shotRun : A.lastRun();
    const cs = A.failed(v.shotRun).sort((a, b) => a.seq - b.seq || (a.parent ? 1 : -1));
    const have = cs.filter(c => c.shots.length).length;
    if (!cs.some(c => c.uid === v.shotAt)) v.shotAt = (cs.find(c => !c.shots.length) || cs[0] || {}).uid;
    return '<div class="card" id="shotCard"><div class="card-h"><b>补充截图</b><span class="hint">失败 ' + cs.length + " 条，有截图 " + have + ' 条</span><span class="sp"></span><a id="sFold">' + (v.shotOpen ? "收起" : "逐条补截图") + "</a></div>" +
      (v.shotOpen ? "" : '<div class="form"><label class="fi"><span>批次</span>' + A.runSelect("sRun", v.shotRun) + '</label><span class="sp"></span><button class="btn sm" id="sDir">选择截图文件夹</button><input type="file" id="sDirIn" webkitdirectory multiple style="display:none"></div><div class="hint" id="sMsg"></div></div>') +
      (!v.shotOpen ? "" : '<div class="form" style="margin-bottom:6px"><label class="fi"><span>批次</span>' + A.runSelect("sRun", v.shotRun) + "</label>" +
      '<span class="hint">点一条用例，按 <b>Ctrl+V</b> 粘贴，自动跳到下一条</span><span class="sp"></span><button class="btn sm" id="sDir">选择截图文件夹</button><input type="file" id="sDirIn" webkitdirectory multiple style="display:none"></div>' +
      '<div class="hint" id="sMsg"></div><div class="tbl-wrap" style="max-height:360px"><table class="tbl"><thead><tr><th>用例</th><th>名称</th><th>分类</th><th>截图</th><th>操作</th></tr></thead><tbody>' +
      cs.map(c => '<tr class="click' + (c.uid === v.shotAt ? " sel" : "") + '" data-sa="' + c.uid + '"><td class="mono nw">' + A.caseLabel(c) + '</td><td class="nm">' + esc(c.name) + "</td><td>" + A.catTag(c.final) + '</td><td><div class="thumbs">' +
        c.shots.slice(0, 4).map(s => '<img src="' + s.src + '" alt="">').join("") + (c.shots.length > 4 ? '<span class="hint">+' + (c.shots.length - 4) + "</span>" : "") + (!c.shots.length ? '<span class="hint">' + (c.uid === v.shotAt ? "← Ctrl+V" : "-") + "</span>" : "") +
        '</div></td><td class="ops nw"><a data-sp="' + c.uid + '">选图片</a>' + (c.shots.length ? '<a data-sx="' + c.uid + '" class="red">清除</a>' : "") + "</td></tr>").join("") +
      '</tbody></table></div><input type="file" id="sOne" accept="image/*" multiple style="display:none"></div>');
  }
  let shotView = null;
  async function addImgs(uid, files) {
    const c = S.byUid[uid], n = c.shots.length, items = [];
    for (let i = 0; i < files.length; i++) items.push({ name: files[i].name && files[i].name !== "image.png" ? files[i].name : c.id + "_" + (n + i + 1) + ".png", data: await A.fileData(files[i]) });
    return A.act("/api/shots/add", { uid, items }, "已添加到 " + c.id);
  }
  A.addImgs = addImgs;
  function advance(v, uid) {
    const cs = A.failed(v.shotRun).sort((a, b) => a.seq - b.seq || (a.parent ? 1 : -1));
    const i = cs.findIndex(c => c.uid === uid), nx = cs.slice(i + 1).find(c => !c.shots.length);
    if (nx) v.shotAt = nx.uid;
  }
  document.addEventListener("paste", e => {
    const v = shotView;
    if (!v || !v.shotOpen || !$("#shotCard") || A.drawerOpen() || $("#dlg").classList.contains("open")) return;
    if (e.target && /^(TEXTAREA|INPUT)$/.test(e.target.tagName)) return;
    const files = Array.from((e.clipboardData || {}).items || []).filter(i => i.type.indexOf("image") === 0).map(i => i.getAsFile());
    if (!files.length || !v.shotAt) return;
    e.preventDefault();
    const uid = v.shotAt; advance(v, uid); addImgs(uid, files);
  });
  function bindShotCard(root, v) {
    shotView = v;
    if (!S.runs.length) return;
    $("#sFold").onclick = () => { v.shotOpen = !v.shotOpen; A.render(); };
    $("#sRun").onchange = e => { v.shotRun = e.target.value; v.shotAt = null; A.render(); };
    $("#sDir").onclick = () => $("#sDirIn").click();
    $("#sDirIn").onchange = async e => {
      const imgs = Array.from(e.target.files).filter(f => /\.(png|jpe?g|gif|bmp|webp)$/i.test(f.name));
      if (!imgs.length) return A.toast("文件夹里没有图片", true);
      A.toast("正在上传 " + imgs.length + " 张…");
      const items = [];
      for (const f of imgs) items.push({ name: f.webkitRelativePath || f.name, data: await A.fileData(f) });
      const r = await A.act("/api/shots/match", { run: v.shotRun, items });
      if (r) $("#sMsg").innerHTML = "共 " + imgs.length + " 张，已匹配 " + r.matched + " 张" + (r.unmatched.length ? "；未匹配 " + r.unmatched.length + " 张（文件名里没有用例编号），例如：" + r.unmatched.slice(0, 5).map(esc).join("、") : "");
    };
    $$("[data-sa]", root).forEach(tr => {
      tr.onclick = e => { if (e.target.closest("a")) return; v.shotAt = tr.dataset.sa; $$("[data-sa]", root).forEach(x => x.classList.toggle("sel", x === tr)); };
      tr.ondragover = e => { e.preventDefault(); tr.classList.add("over"); };
      tr.ondragleave = () => tr.classList.remove("over");
      tr.ondrop = e => { e.preventDefault(); const fs = Array.from(e.dataTransfer.files).filter(f => /^image\//.test(f.type)); if (fs.length) addImgs(tr.dataset.sa, fs); };
    });
    let pickFor = null;
    $$("[data-sp]", root).forEach(a => a.onclick = () => { pickFor = a.dataset.sp; $("#sOne").click(); });
    if ($("#sOne")) $("#sOne").onchange = e => { v.shotAt = pickFor; advance(v, pickFor); addImgs(pickFor, Array.from(e.target.files)); };
    $$("[data-sx]", root).forEach(a => a.onclick = () => A.act("/api/shots/del", { uid: a.dataset.sx }, "已清除"));
    const sel = $("tr.sel", root); if (sel && v.scrollShot !== v.shotAt) { v.scrollShot = v.shotAt; sel.scrollIntoView({ block: "nearest" }); }
  }
})();
