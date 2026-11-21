/* 页面：工作台（概览、分类与重跑标准）、数据导入（字段对应、补充截图） */
(function () {
  const A = APP, S = A.S, M = A.M, esc = A.esc, $ = A.$, $$ = A.$$;
  const CAT_ORDER = ["ENVIRONMENT", "PRODUCT_DEFECT", "SCRIPT_ISSUE", "TEST_DATA", "POPUP_INTERFERENCE", "NEEDS_HUMAN"];
  const NEXT = { ENVIRONMENT: "汇总给环境负责人，恢复后重跑", POPUP_INTERFERENCE: "补充弹窗处理，重跑确认", SCRIPT_ISSUE: "修脚本，修好后重跑", TEST_DATA: "补数据或换数据后重跑", PRODUCT_DEFECT: "确认后起草 Jira", NEEDS_HUMAN: "看截图，记录观察后重新分析" };
  A.NEXT = NEXT; A.CAT_ORDER = CAT_ORDER;

  /* ============================== 工作台 · 概览 ============================== */
  const kpi = (n, label, color, goId, opts) => goId ? '<button class="kpi" style="--c:' + color + '" data-go="' + goId + '"' + (opts ? " data-opts='" + JSON.stringify(opts) + "'" : "") + "><b>" + n + "</b><span>" + label + " ›</span></button>"
    : '<div class="kpi" style="--c:' + color + '"><b>' + n + "</b><span>" + label + "</span></div>";
  function overview(root) {
    if (!S.runs.length) {
      root.innerHTML = '<div class="card"><div class="card-h"><b>开始使用</b></div><div class="flow">' +
        '<div class="step"><h6><span class="n you">1</span>导入执行结果</h6><p>报告网页（.mhtml / .html）、JSON、CSV、JUnit、Allure，或粘贴表格。截图文字自动识别。</p></div>' +
        '<div class="step"><h6><span class="n auto">2</span>分析根本原因</h6><p>每条失败用例给出分类、判断依据和重跑建议。</p></div>' +
        '<div class="step"><h6><span class="n you">3</span>复核、重跑、分派、提 Jira</h6><p>在“失败分诊”和“Jira 提报”里完成。</p></div></div>' +
        '<div style="margin-top:10px"><button class="btn pri" data-go="import">去导入数据</button></div></div>';
      A.bindGo(root); return;
    }
    const f = A.failed(), base = f.filter(c => !c.parent);
    const sus = f.filter(c => !c.override && c.auto.status === "suspected").length;
    const pend = f.filter(c => !c.override && c.auto.checkKind && !c.dataCheck).length;
    const go = base.filter(c => c.plan.b === "go").length;
    const total = S.runs.reduce((a, r) => a + r.total, 0);
    let html = '<div class="kpis">' + kpi(total, "执行用例", "#409eff") + kpi(base.length, "失败用例", "#f56c6c", "triage", { st: "", cat: "" }) +
      kpi(sus, "待复核", "#e6a23c", "triage", { st: "sus" }) + kpi(pend, "待人工核查", "#e6a23c", "triage", { st: "check" }) +
      kpi(go, "建议立即重跑", "#409eff", "rerun", { tab: "go" }) + kpi(S.drafts.filter(d => d.status !== "discarded").length, "Jira 草稿", "#909399", "jira") + "</div>";
    html += '<div class="card"><div class="card-h"><b>失败原因分布</b><span class="hint">全部批次</span></div><div class="tbl-wrap"><table class="tbl"><thead><tr><th>分类</th><th>数量</th><th style="width:30%">占比</th><th>处理方</th><th>下一步</th></tr></thead><tbody>' +
      CAT_ORDER.map(k => {
        const n = f.filter(c => c.final === k).length; if (!n) return "";
        const pct = Math.round(n * 100 / f.length);
        return '<tr class="click" data-go="triage" data-opts=\'' + JSON.stringify({ open: [k] }) + "'><td>" + A.catTag(k) + "</td><td>" + n + '</td><td><div class="bar-p"><div style="width:' + pct + '%"></div></div><span class="hint">' + pct + "%</span></td><td>" + M.CATS[k].owner + "</td><td>" + NEXT[k] + "</td></tr>";
      }).join("") + "</tbody></table></div></div>";
    html += '<div class="card"><div class="card-h"><b>已导入批次</b><span class="sp"></span><button class="btn sm" data-go="import">导入新批次</button></div>' + runTable() + "</div>";
    root.innerHTML = html;
    A.bindGo(root); bindRunTable(root);
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
    html += '<div style="margin:8px 0 6px;display:flex;gap:14px;flex-wrap:wrap" class="hint"><span>共 <b class="ink">' + pv.n + '</b> 行</span><span>失败 <b class="red">' + pv.nFail + "</b> 行</span>" + (p.images ? '<span>内嵌截图 <b class="ink">' + p.images + "</b> 张</span>" : "") +
      "<span>执行结果：" + pv.resVals.map(([k, n]) => esc(k) + " × " + n).join("，") + '</span><a data-go="rules" data-opts=\'{"focus":"fail_words"}\'>失败判断不对？</a></div>';
    html += '<div class="tbl-wrap" style="max-height:300px"><table class="tbl"><thead><tr><th>#</th><th>用例编号</th><th>用例名称</th><th>执行结果</th><th>判定</th><th>报错第一行</th></tr></thead><tbody>' +
      pv.rows.map(c => '<tr><td class="hint">' + c.seq + '</td><td class="mono nw">' + esc(c.id) + '</td><td class="nm">' + esc(c.name || "-") + "</td><td>" + esc(c.result) + "</td><td>" + (c.failed ? '<span class="tag red">失败</span>' : '<span class="tag gray">不分析</span>') + '</td><td class="clip">' + esc(c.first || "-") + "</td></tr>").join("") + "</tbody></table></div>";
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
    return '<div class="card" id="shotCard"><div class="card-h"><b>补充截图</b><span class="hint">点一条用例，按 <b>Ctrl+V</b> 粘贴，自动跳到下一条</span></div>' +
      '<div class="form" style="margin-bottom:6px"><label class="fi"><span>批次</span>' + A.runSelect("sRun", v.shotRun) + "</label>" +
      '<span class="hint">失败 ' + cs.length + " 条，有截图 " + have + ' 条</span><span class="sp"></span><button class="btn sm" id="sDir">选择截图文件夹</button><input type="file" id="sDirIn" webkitdirectory multiple style="display:none"></div>' +
      '<div class="hint" id="sMsg"></div><div class="tbl-wrap" style="max-height:360px"><table class="tbl"><thead><tr><th>用例</th><th>名称</th><th>分类</th><th>截图</th><th>操作</th></tr></thead><tbody>' +
      cs.map(c => '<tr class="click' + (c.uid === v.shotAt ? " sel" : "") + '" data-sa="' + c.uid + '"><td class="mono nw">' + A.caseLabel(c) + '</td><td class="nm">' + esc(c.name) + "</td><td>" + A.catTag(c.final) + '</td><td><div class="thumbs">' +
        c.shots.slice(0, 4).map(s => '<img src="' + s.src + '" alt="">').join("") + (c.shots.length > 4 ? '<span class="hint">+' + (c.shots.length - 4) + "</span>" : "") + (!c.shots.length ? '<span class="hint">' + (c.uid === v.shotAt ? "← Ctrl+V" : "-") + "</span>" : "") +
        '</div></td><td class="ops nw"><a data-sp="' + c.uid + '">选图片</a>' + (c.shots.length ? '<a data-sx="' + c.uid + '" class="red">清除</a>' : "") + "</td></tr>").join("") +
      '</tbody></table></div><input type="file" id="sOne" accept="image/*" multiple style="display:none"></div>';
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
    if (!v || !$("#shotCard") || A.drawerOpen() || $("#dlg").classList.contains("open")) return;
    if (e.target && /^(TEXTAREA|INPUT)$/.test(e.target.tagName)) return;
    const files = Array.from((e.clipboardData || {}).items || []).filter(i => i.type.indexOf("image") === 0).map(i => i.getAsFile());
    if (!files.length || !v.shotAt) return;
    e.preventDefault();
    const uid = v.shotAt; advance(v, uid); addImgs(uid, files);
  });
  function bindShotCard(root, v) {
    shotView = v;
    if (!S.runs.length) return;
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
    $("#sOne").onchange = e => { v.shotAt = pickFor; advance(v, pickFor); addImgs(pickFor, Array.from(e.target.files)); };
    $$("[data-sx]", root).forEach(a => a.onclick = () => A.act("/api/shots/del", { uid: a.dataset.sx }, "已清除"));
    const sel = $("tr.sel", root); if (sel && v.scrollShot !== v.shotAt) { v.scrollShot = v.shotAt; sel.scrollIntoView({ block: "nearest" }); }
  }
})();
