/* 页面：配置（判断规则、自定义规则、纠错样本、修改记录、Jira 与接口）。保存在 skill 的 config/ 里，团队共用。 */
(function () {
  const A = APP, S = A.S, M = A.M, esc = A.esc, $ = A.$, $$ = A.$$;
  const lines = s => s.split("\n").map(x => x.trim()).filter(Boolean);
  // 改规则后的结果：多少用例分类变了、纠错样本是否都判对
  const afterMsg = r => r.msg || ("已保存：" + r.changed + " 条用例分类有变化；纠错样本 " + r.corrections.filter(x => x.ok).length + "/" + r.corrections.length + " 条判对");
  function whoDialog(title, body, fn) {
    A.dialog(title, (body || "") + '<div style="display:grid;gap:8px;margin-top:6px"><label class="fi"><span>修改人</span><input class="inp" id="wBy" value="' + esc(A.who()) + '"></label><label><div style="margin-bottom:4px">修改说明（为什么改）</div><input class="inp" id="wNote" style="width:100%" placeholder="例如：LAS 新增锁单提示 “Policy is being edited”"></label></div>',
      [{ t: "取消" }, { t: "保存", pri: true, fn: async () => {
        const by = $("#wBy").value.trim(); if (!by) { A.toast("请填写修改人", true); return false; }
        if (by !== A.who()) await A.api("/api/settings", { key: "reviewer", value: by }).catch(() => {});
        const r = await fn(by, $("#wNote").value.trim());
        // 自己改的不用再提醒
        if (r) await A.act("/api/settings", { key: "seenRules", value: S.changelog.length });
        if (r && r.corrections && r.corrections.some(x => !x.ok)) setTimeout(() => A.go("corrections"), 50);
        return !!r;
      } }]);
  }

  /* ============================== 判断规则 ============================== */
  const RULE_SECTIONS = [
    ["环境问题", [["env_exceptions", "异常类型"], ["env_patterns", "报错关键字"]]],
    ["大面积相同报错", [["mass_min_cases", "至少几个用例", "num"], ["mass_ratio", "占失败数比例（%）", "num"], ["mass_window_min", "时间窗口（分钟）", "num"]]],
    ["弹窗清单", [["noise_popups", "干扰弹窗文字"], ["business_errors", "业务报错文字"], ["overlay_keywords", "遮挡元素特征"]]],
    ["系统提示", [["lock_messages", "数据被占用 → 测试数据问题"], ["config_messages", "缺少配置 → 需核查"], ["crash_messages", "程序未处理异常 → 疑似产品缺陷"]]],
  ];
  const RULE_ADV = [
    ["异常类型", [["alert_exceptions", "原生对话框"], ["intercept_exceptions", "点击被遮挡"], ["locator_exceptions", "找不到元素 / 超时"], ["invalid_selector", "定位表达式错误"], ["code_errors", "测试代码运行错误"], ["assertion_exceptions", "断言失败"]]],
    ["桌面端控件（pywinauto）", [["masked_patterns", "掩盖型报错"], ["desk_ambiguous", "匹配到多个控件"], ["desk_not_found", "找不到窗口 / 控件"], ["desk_not_visible", "控件不可见"], ["desk_not_enabled", "控件不可用"], ["desk_option_missing", "下拉框没有该选项"], ["desk_datetime", "日期控件设置失败"]]],
    ["日志解析", [["framework_paths", "框架和第三方库路径"], ["handler_funcs", "失败后执行的处理函数"], ["success_marks", "业务已成功的文字"]]],
    ["其他", [["test_code_paths", "测试代码路径特征"], ["expected_actual", "期望值/实际值格式"], ["fail_words", "执行结果中表示失败的文字"]]],
  ];
  const changed = k => JSON.stringify(S.rules[k]) !== JSON.stringify(M.DEFAULT_RULES[k]);
  const ruleBlock = ([t, items]) => '<div class="card"><div class="card-h"><b>' + t + "</b>" + (items.some(([k]) => changed(k)) ? '<span class="tag orange xs">已改</span>' : "") + '</div><div class="rgrid">' +
    items.map(([k, label, type]) => '<label><div class="hint" style="margin-bottom:3px">' + label + (changed(k) ? ' <span class="orange">*</span>' : "") + "</div>" + (type === "num" ? '<input class="inp" type="number" data-r="' + k + '" value="' + S.rules[k] + '">' : '<textarea class="ta" rows="6" data-r="' + k + '" id="r_' + k + '">' + esc((S.rules[k] || []).join("\n")) + "</textarea>") + "</label>").join("") + "</div></div>";
  function rulesPage(root, v) {
    const last = S.changelog[S.changelog.length - 1];
    let html = '<div class="card"><div class="card-h"><b>判断规则</b><span class="hint">每行一项，不区分大小写；<code>re:</code> 开头是模糊匹配。' + (last ? "最近修改：" + esc(last.at) + " " + esc(last.by || "") : "") + '</span><span class="sp"></span>' +
      '<button class="btn sm" id="rFile">查看规则文件</button><button class="btn sm" id="rImport">导入</button><a class="btn sm" href="/api/rules/file" download="rules.json">下载</a><button class="btn sm" id="rReset">恢复默认</button><button class="btn sm pri" id="rSave">保存并重新分类</button></div></div>';
    html += RULE_SECTIONS.map(ruleBlock).join("");
    html += '<details class="adv"' + (v.adv ? " open" : "") + "><summary>高级（异常名称、桌面端控件、日志解析）</summary>" + RULE_ADV.map(ruleBlock).join("") + "</details>";
    root.innerHTML = html;
    $("details.adv", root).ontoggle = e => { v.adv = e.target.open; };
    if (v.focus) { const el = $("#r_" + v.focus); if (el) { if (el.closest("details")) el.closest("details").open = true; el.scrollIntoView(); el.focus(); } v.focus = null; }
    $("#rSave").onclick = () => {
      const rules = {};
      $$("[data-r]", root).forEach(el => { rules[el.dataset.r] = el.type === "number" ? +el.value : lines(el.value); });
      whoDialog("保存判断规则", "", (by, note) => A.act("/api/rules/save", { rules, by, note }, afterMsg));
    };
    $("#rReset").onclick = () => whoDialog("恢复默认规则", "<p style=\"margin-top:0\">判断规则恢复为默认值（自定义规则、纠错样本保留）。</p>", (by, note) => A.act("/api/rules/reset", { by, note }, afterMsg));
    $("#rFile").onclick = () => { A.dialog("config/rules.json", '<pre class="json">' + esc(JSON.stringify({ tool: "ta-rules", v: 2, rules: S.rules, custom: S.custom, changelog: S.changelog }, null, 2)) + "</pre>", [{ t: "关闭" }]); $("#dlg").style.width = "80vw"; };
    $("#rImport").onclick = () => A.dialog("导入规则文件", '<p class="hint" style="margin-top:0">同事的 rules.json。会替换判断规则和自定义规则。</p><input type="file" id="rImpF" accept=".json"><textarea class="ta" id="rImpIn" rows="10" placeholder="或粘贴内容"></textarea>',
      [{ t: "取消" }, { t: "导入", pri: true, fn: async () => {
        const f = $("#rImpF").files[0], text = f ? await A.fileText(f) : $("#rImpIn").value;
        const r = await A.act("/api/rules/import", { text, by: A.who() }, afterMsg);
        if (r) await A.act("/api/settings", { key: "seenRules", value: S.changelog.length });
        return !!r;
      } }]);
  }

  /* ============================== 自定义规则 ============================== */
  const srcName = k => M.CUSTOM_SOURCES[k];
  const code = l => l.map(x => "<code>" + esc(x) + "</code>").join(" ");
  function customCard(u, i, n) {
    const w = u.when || {}, t = u.then || {};
    return '<div class="cu' + (u.enabled === false ? " off" : "") + '"><div class="cu-h"><b class="mono">' + esc(u.id) + "</b><b>" + esc(u.name || "") + "</b>" + A.catTag(t.category) + '<span class="tag ' + (t.status === "confirmed" ? "green" : "orange") + ' xs">' + (t.status === "confirmed" ? "规则确认" : "待复核") + "</span>" + (t.rerun ? '<span class="tag ' + M.PLAN_COLOR[t.rerun] + ' xs">' + M.PLAN[t.rerun] + "</span>" : "") +
      '<span class="sp"></span><span class="hint">' + esc((u.by || "") + " " + (u.at || "")) + '</span><span class="ops"><a data-cup="' + i + '"' + (i ? "" : ' style="visibility:hidden"') + '>上移</a><a data-cdn="' + i + '"' + (i < n - 1 ? "" : ' style="visibility:hidden"') + '>下移</a><a data-ced="' + i + '">编辑</a><a data-con="' + i + '">' + (u.enabled === false ? "启用" : "停用") + '</a><a data-cdel="' + i + '" class="red">删除</a></span></div>' +
      '<div class="cond">在 ' + (w.in || ["log", "popup"]).map(srcName).join("、") + " 里：" + (w.any && w.any.length ? "出现任一 " + code(w.any) + "；" : "") + (w.all && w.all.length ? "全部出现 " + code(w.all) + "；" : "") + (w.none && w.none.length ? "不能出现 " + code(w.none) + "；" : "") + (w.exceptions && w.exceptions.length ? "异常类型 " + code(w.exceptions) + "；" : "") +
      (t.brief ? "<br>结论：" + esc(t.brief) : "") + (t.need ? "<br>下一步：" + esc(t.need) : "") + (u.note ? "<br>说明：" + esc(u.note) : "") + "</div></div>";
  }
  function customPage(root) {
    const C = S.custom;
    root.innerHTML = '<div class="card"><div class="card-h"><b>自定义规则</b><span class="hint">团队自己补的判断，优先于内置规则，按顺序第一条命中的生效</span><span class="sp"></span><button class="btn sm pri" id="cuNew">新增规则</button></div>' +
      (C.length ? C.map((u, i) => customCard(u, i, C.length)).join("") : A.emptyBlock("还没有自定义规则", "遇到规则判错的用例：先“加入纠错样本”，再在这里补一条规则。")) + "</div>";
    const saveList = (list, title) => whoDialog(title, "", (by, note) => A.act("/api/custom/save", { custom: list, by, note }, afterMsg));
    const copyList = () => JSON.parse(JSON.stringify(C));
    $("#cuNew").onclick = () => editDialog(null);
    $$("[data-ced]", root).forEach(a => a.onclick = () => editDialog(+a.dataset.ced));
    $$("[data-con]", root).forEach(a => a.onclick = () => { const l = copyList(), u = l[+a.dataset.con]; u.enabled = u.enabled === false; saveList(l, (u.enabled ? "启用 " : "停用 ") + u.id); });
    $$("[data-cdel]", root).forEach(a => a.onclick = () => { const l = copyList(), u = l.splice(+a.dataset.cdel, 1)[0]; saveList(l, "删除 " + u.id); });
    const move = (i, d) => { const l = copyList(); [l[i], l[i + d]] = [l[i + d], l[i]]; saveList(l, "调整顺序"); };
    $$("[data-cup]", root).forEach(a => a.onclick = () => move(+a.dataset.cup, -1));
    $$("[data-cdn]", root).forEach(a => a.onclick = () => move(+a.dataset.cdn, 1));
  }
  function editDialog(idx) {
    const C = S.custom, old = idx === null ? null : C[idx];
    const nid = "U" + (Math.max(0, ...C.map(u => +String(u.id).slice(1) || 0)) + 1);
    const u = old ? JSON.parse(JSON.stringify(old)) : { id: nid, enabled: true, name: "", when: { in: ["log", "popup"], any: [], all: [], none: [], exceptions: [] }, then: { category: "TEST_DATA", status: "suspected", brief: "", need: "", rerun: "" }, note: "" };
    const w = u.when, t = u.then;
    const ta = (id, label, val, ph) => '<label><div class="hint">' + label + '</div><textarea class="ta" rows="3" id="' + id + '" placeholder="' + esc(ph || "每行一项") + '">' + esc((val || []).join("\n")) + "</textarea></label>";
    A.dialog(old ? "编辑 " + u.id : "新增自定义规则 " + u.id,
      '<div class="cgrid"><label class="full"><div class="hint">规则名称</div><input class="inp" id="cuName" style="width:100%" value="' + esc(u.name) + '" placeholder="例如：保单被编辑锁定"></label>' +
      '<div class="full"><div class="hint">在哪些文字里找</div>' + Object.keys(M.CUSTOM_SOURCES).map(k => '<label style="margin-right:12px"><input type="checkbox" data-cin="' + k + '"' + ((w.in || ["log", "popup"]).includes(k) ? " checked" : "") + "> " + esc(srcName(k)) + "</label>").join("") + "</div>" +
      ta("cuAny", "出现任一", w.any, "每行一项，例如：Policy is being edited") + ta("cuAll", "还要全部出现（可空）", w.all) + ta("cuNone", "不能出现（可空）", w.none) + ta("cuExc", "异常类型（可空）", w.exceptions, "例如：ElementNotFoundError") +
      '<label><div class="hint">判为</div><select class="sel" id="cuCat" style="width:100%">' + A.catOptions(t.category) + "</select></label>" +
      '<label><div class="hint">判定</div><select class="sel" id="cuSt" style="width:100%"><option value="suspected"' + (t.status !== "confirmed" ? " selected" : "") + '>待复核（只是线索）</option><option value="confirmed"' + (t.status === "confirmed" ? " selected" : "") + ">规则确认（证据直接说明原因）</option></select></label>" +
      '<label><div class="hint">重跑建议</div><select class="sel" id="cuRr" style="width:100%"><option value="">按分类默认</option>' + ["go", "fix", "no"].map(k => '<option value="' + k + '"' + (t.rerun === k ? " selected" : "") + ">" + M.PLAN[k] + "</option>").join("") + "</select></label>" +
      '<label><div class="hint">一句话结论（可空）</div><input class="inp" id="cuBrief" style="width:100%" value="' + esc(t.brief) + '"></label>' +
      '<label class="full"><div class="hint">下一步（可空）</div><input class="inp" id="cuNeed" style="width:100%" value="' + esc(t.need) + '"></label>' +
      '<label class="full"><div class="hint">为什么加这条</div><input class="inp" id="cuNote" style="width:100%" value="' + esc(u.note) + '"></label></div><div id="cuTest" class="hint" style="margin-top:8px"></div>',
      [{ t: "取消" }, { t: "试一下", fn: async () => {
        const it = read(); const r = await A.api("/api/custom/test", { item: it }).catch(e => { A.toast(e.message, true); return null; });
        if (r) $("#cuTest").innerHTML = "当前数据里会命中 <b>" + r.n + "</b> 条失败用例" + (r.n ? "：" + r.cases.slice(0, 15).map(c => esc(c.id) + "（现在 " + M.CATS[c.now].name + "）").join("、") : "");
        return false;
      } }, { t: "保存", pri: true, fn: () => {
        const it = read();
        const list = JSON.parse(JSON.stringify(C)); if (old) list[idx] = it; else list.push(it);
        setTimeout(() => whoDialog((old ? "修改 " : "新增 ") + it.id, "", (by, note) => A.act("/api/custom/save", { custom: list, by, note: note || it.note }, afterMsg)), 30);
      } }]);
    $("#dlg").style.width = "720px";
    function read() {
      return { id: u.id, enabled: u.enabled !== false, name: $("#cuName").value.trim(),
        when: { in: $$("[data-cin]").filter(x => x.checked).map(x => x.dataset.cin), any: lines($("#cuAny").value), all: lines($("#cuAll").value), none: lines($("#cuNone").value), exceptions: lines($("#cuExc").value) },
        then: Object.assign({ category: $("#cuCat").value, status: $("#cuSt").value }, $("#cuBrief").value.trim() ? { brief: $("#cuBrief").value.trim() } : {}, $("#cuNeed").value.trim() ? { need: $("#cuNeed").value.trim() } : {}, $("#cuRr").value ? { rerun: $("#cuRr").value } : {}),
        note: $("#cuNote").value.trim(), by: u.by, at: u.at };
    }
  }

  /* ============================== 纠错样本 ============================== */
  function corrPage(root) {
    const L = S.corrections, bad = L.filter(x => !x.test.ok).length;
    root.innerHTML = '<div class="card"><div class="card-h"><b>纠错样本 ' + L.length + " 条</b>" + (L.length ? (bad ? '<span class="tag red">' + bad + " 条没判对</span>" : '<span class="tag green">全部判对</span>') : "") + '<span class="hint">每次改规则都会重新检查；在用例详情里点“加入纠错样本”添加</span></div>' +
      (L.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>编号</th><th>来源</th><th>应为</th><th>现在判为</th><th>结果</th><th>原因</th><th>添加人</th><th></th></tr></thead><tbody>' +
        L.map(x => "<tr><td class=\"mono\">" + esc(x.id) + '</td><td class="nw">' + esc((x.from || {}).case_id || "") + '<div class="hint">' + esc((x.from || {}).run || "") + "</div></td><td>" + A.catTag(x.expect.category) + (x.expect.rule ? '<div class="hint">' + esc(M.RULE_NAMES[x.expect.rule] || x.expect.rule) + "</div>" : "") + "</td><td>" + A.catTag(x.test.got.category) + '<div class="hint">' + esc(x.test.got.rule_name) + '</div></td><td class="nw">' + (x.test.ok ? '<b class="ok">✓ 判对</b>' : '<b class="bad">✗ 判错</b>') + '</td><td class="basis">' + esc(x.reason) + (x.test.ok ? "" : '<div class="hint">现在：' + esc(x.test.got.brief) + "</div>") + "</td><td class=\"nw\">" + esc(x.by || "") + '<div class="hint">' + esc(x.at || "") + '</div></td><td class="ops"><a data-cxd="' + esc(x.id) + '" class="red">删除</a></td></tr>').join("") + "</tbody></table></div>"
        : A.emptyBlock("还没有纠错样本")) + "</div>";
    $$("[data-cxd]", root).forEach(a => a.onclick = () => A.dialog("删除样本", "删除 " + esc(a.dataset.cxd) + "？", [{ t: "取消" }, { t: "删除", pri: true, fn: () => A.act("/api/corrections/delete", { id: a.dataset.cxd }, "已删除") }]));
  }

  /* ============================== 修改记录 ============================== */
  function logPage(root) {
    root.innerHTML = '<div class="card"><div class="card-h"><b>规则修改记录</b><span class="hint">保存在 config/rules.json</span></div>' +
      (S.changelog.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th>修改人</th><th>改了什么</th><th>说明</th></tr></thead><tbody>' + S.changelog.slice().reverse().map(l => '<tr><td class="nw">' + esc(l.at) + '</td><td class="nw">' + esc(l.by || "") + '</td><td class="basis">' + esc(l.what) + '</td><td class="basis">' + esc(l.note || "") + "</td></tr>").join("") + "</tbody></table></div>" : A.emptyBlock("没有记录")) + "</div>";
  }

  /* ============================== Jira 与接口 ============================== */
  function jiraCfgPage(root) {
    const C = S.jira;
    const f = (k, label, ph, note) => '<label class="frow"><span>' + label + '</span><div><input class="inp" style="width:100%" data-c="' + k + '" value="' + esc(Array.isArray(C[k]) ? C[k].join(", ") : C[k]) + '" placeholder="' + esc(ph || "") + '">' + (note ? '<div class="hint">' + note + "</div>" : "") + "</div></label>";
    root.innerHTML = '<div class="card"><div class="card-h"><b>Jira 与接口</b><span class="hint">保存在 config/jira.json。账号和 Token 只放本机环境变量：JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN（' + (M.jiraEnv ? '<b class="ok">已设置</b>' : '<b class="bad">未设置</b>') + '）</span><span class="sp"></span><button class="btn sm pri" id="cfgSave">保存</button></div>' +
      '<div class="cfg2"><div><h5>连接</h5><label class="frow"><span>Jira 类型</span><div><select class="sel" data-c="deploy"><option value="cloud"' + (C.deploy === "cloud" ? " selected" : "") + '>Jira Cloud</option><option value="dc"' + (C.deploy === "dc" ? " selected" : "") + ">Data Center / Server</option></select></div></label>" +
      f("baseUrl", "Jira 地址", "https://xxx.atlassian.net") + f("rerunUrl", "重跑接口", "http://内网地址/api/rerun", "POST {run, cases:[用例编号]}；留空时复制编号") +
      "<h5>字段</h5>" + f("project", "Project Key", "ROTQA") + f("issueType", "Issue Type", "Bug") + f("issueTypeEnv", "环境问题用的类型", "Task") +
      f("system", "System 默认值", "NBS") + f("systemField", "System 字段 ID", "customfield_10xxx") + f("components", "默认 Components", "SYSTEM-QA") + f("labels", "默认 Labels", "regression, auto-triage") +
      '<label class="frow"><span>Environment 放在</span><div><select class="sel" data-c="envMode"><option value="field"' + (C.envMode === "field" ? " selected" : "") + '>Environment 字段</option><option value="description"' + (C.envMode === "description" ? " selected" : "") + ">Description 最前面</option></select></div></label></div>" +
      "<div><h5>起草</h5>" + f("market", "市场", "HK") + f("titleTpl", "标题模板", "", "{system} {market} {module} {case} {cause}") + f("descTpl", "描述第一句", "", "{env} {system} {module} {case} {problem} {action}") +
      f("highKeywords", "高优先级关键字", "", "逗号分隔") + '<label style="display:flex;gap:8px;align-items:center;margin:4px 0 8px"><input type="checkbox" data-c="maskOnExport"' + (C.maskOnExport ? " checked" : "") + ">导出和提交时再做一次个人信息脱敏</label></div></div></div>";
    $("#cfgSave").onclick = () => {
      const cfg = {};
      $$("[data-c]", root).forEach(el => { const k = el.dataset.c; cfg[k] = el.type === "checkbox" ? el.checked : el.value.trim(); });
      A.act("/api/jira/cfg", { cfg }, "已保存。已有草稿可以点“按最新分诊刷新”更新");
    };
  }

  A.composite("config", [["rules", "判断规则", rulesPage], ["custom", "自定义规则", customPage], ["corrections", "纠错样本", corrPage, () => S.corrections.filter(x => !x.test.ok).length],
    ["changelog", "修改记录", logPage], ["jira", "Jira 与接口", jiraCfgPage]]);
})();
