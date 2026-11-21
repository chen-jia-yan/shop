/* 页面：失败分诊（① 分诊 ② 重跑 ③ 分派）与用例详情 */
(function () {
  const A = APP, S = A.S, M = A.M, esc = A.esc, $ = A.$, $$ = A.$$;
  const flagTags = c => { const f = c.auto.flags.filter(x => x !== "重跑第2次"); return f.length ? '<div class="flags">' + f.map(x => '<span class="tag ' + (x === "重跑通过" ? "green" : "orange") + '">' + esc(x) + "</span>").join("") + "</div>" : ""; };
  const DISPATCH = [
    { k: "test", name: "交给测试", cats: ["SCRIPT_ISSUE", "TEST_DATA", "POPUP_INTERFERENCE"], todo: "修脚本、换数据、补弹窗处理，处理后重跑" },
    { k: "dev", name: "交给开发", cats: ["PRODUCT_DEFECT"], todo: "起草 Jira，附截图和执行情况" },
    { k: "env", name: "交给环境/运维", cats: ["ENVIRONMENT"], todo: "确认执行机、数据库、服务，恢复后重跑" },
    { k: "human", name: "待判断", cats: ["NEEDS_HUMAN"], todo: "看截图记录观察，或做人工核查" },
  ];
  const causeName = c => { const h = c.auto.hits[0] || c.error1; return c.ruleName + (h && !c.override ? " · “" + String(h).replace(/\s+/g, " ").slice(0, 70) + "”" : ""); };
  function causesOf(cs) {
    const g = {}; cs.forEach(c => { const k = c.sig || "(无报错)"; (g[k] = g[k] || []).push(c); });
    return Object.entries(g).map(([sig, list]) => ({ sig, cs: list.sort((a, b) => a.seq - b.seq || (a.parent ? 1 : -1)) })).sort((a, b) => b.cs.length - a.cs.length);
  }
  const needCheck = c => !c.override && c.auto.checkKind && !c.dataCheck;
  const isSel = (v, u) => v.sel.includes(u);
  const rerunText = c => c.rerun === "pass" ? "重跑通过" : c.rerun === "fail" ? (c.r2 && c.r2.same === false ? "重跑失败（报错不同）" : "重跑失败（同一问题）") : "";

  /* ============================== ① 分诊 ============================== */
  const ST = [["", "全部"], ["sus", "待复核"], ["check", "待人工核查"], ["manual", "人工已改"]];
  function filterCases(v, st) {
    const q = (v.q || "").toLowerCase(); st = st === undefined ? v.st : st;
    return A.failed(v.run).filter(c => (!q || (c.id + " " + c.name + " " + c.error1 + " " + c.module).toLowerCase().includes(q)) && (!v.sig || c.sig === v.sig) &&
      (st === "sus" ? !c.override && c.auto.status === "suspected" : st === "check" ? needCheck(c) : st === "manual" ? !!c.override : true));
  }
  function checkCell(c) {
    const k = c.auto.checkKind && !c.override ? M.CHECK_KINDS[c.auto.checkKind] : null;
    if (!k) return '<span class="hint">-</span>';
    return '<select class="sel xs' + (c.dataCheck ? "" : " todo") + '" data-dc="' + c.uid + '" title="' + esc(k.what) + '"><option value="">待核查：' + esc(k.name.split(" → ")[0]) + "</option>" + Object.entries(k.options).map(([ok, o]) => '<option value="' + ok + '"' + (c.dataCheck === ok ? " selected" : "") + ">" + esc(o[0]) + " → " + M.CATS[o[1]].name + "</option>").join("") + "</select>";
  }
  const caseRow = (c, v) => '<tr class="' + (isSel(v, c.uid) ? "sel" : "") + '"><td class="ck"><input type="checkbox" data-sel="' + c.uid + '"' + (isSel(v, c.uid) ? " checked" : "") + '></td><td class="mono nw"><a data-open="' + c.uid + '">' + A.caseLabel(c) + "</a></td>" +
    '<td class="nm" title="' + esc(c.name) + '">' + esc(c.name || "-") + (v.run ? "" : '<div class="hint">' + esc(A.runName(c.run)) + "</div>") + "</td>" +
    '<td class="basis">' + esc(c.auto.brief) + flagTags(c) + '</td><td class="nw">' + A.statusTag(c) + '</td><td class="nw">' + A.planTag(c) + "</td><td>" + checkCell(c) + "</td>" +
    '<td class="ops nw"><a data-open="' + c.uid + '">证据' + (c.shots.length ? "·图" : "") + '</a><a data-quick="' + c.uid + '">改分类</a></td></tr>';
  function mainPage(root, v) {
    if (!S.runs.length) return A.noData(root);
    v.sel = (v.sel || []).filter(u => S.byUid[u]); v.open = v.open || [];
    if (v.st === undefined) v.st = "";
    if (v.run === undefined || (v.run && !S.runs.find(r => r.id === v.run))) v.run = A.lastRun();
    const list = filterCases(v);
    const byCat = {}; list.forEach(c => (byCat[c.final] = byCat[c.final] || []).push(c));
    const cats = A.CAT_ORDER.filter(k => byCat[k]);
    let html = '<div class="card"><div class="form"><label class="fi"><span>批次</span>' + A.runSelect("fRun", v.run, true) + "</label>" +
      '<label class="fi"><span>搜索</span><input class="inp" id="fQ" placeholder="编号 / 名称 / 报错关键字" value="' + esc(v.q || "") + '"></label>' +
      '<div class="chips">' + ST.map(([k, n]) => '<button data-st="' + k + '" class="' + (v.st === k ? "on" : "") + '">' + n + " " + filterCases(v, k).length + "</button>").join("") + "</div>" +
      '<span class="sp"></span><button class="btn sm" id="bAI">复制复核材料</button><a class="btn sm" href="/api/export/cases.csv' + (v.run ? "?run=" + v.run : "") + '" download>导出 CSV</a></div>' +
      (v.sig ? '<div class="hint" style="margin-top:6px">只看同一原因：' + esc(list[0] ? causeName(list[0]) : "") + ' <a id="fSigX">显示全部</a></div>' : "") + "</div>";
    html += '<div class="card">' + (v.sel.length ? '<div class="selbar"><b>已选 ' + v.sel.length + ' 条</b><button class="btn sm" id="bBatch">批量改分类</button><button class="btn sm" id="bRerun">加入重跑名单</button><button class="btn sm" id="bClr">清空选择</button></div>' : "") +
      '<div class="card-h"><b>失败 ' + list.length + " 条</b><span class=\"sp\"></span><a id=\"fAll\">" + (cats.length && cats.every(k => v.open.includes(k)) ? "全部收起" : "全部展开") + "</a></div>";
    if (!list.length) html += A.emptyBlock("没有符合条件的用例");
    else {
      html += '<div class="tbl-wrap"><table class="tbl cat"><thead><tr><th style="width:24px"></th><th>分类</th><th>用例</th><th>原因</th><th>待复核</th><th>待核查</th><th>建议重跑</th><th>处理方</th><th>下一步</th></tr></thead><tbody>';
      cats.forEach(k => {
        const cs = byCat[k], open = v.open.includes(k), causes = causesOf(cs);
        const sus = cs.filter(c => !c.override && c.auto.status === "suspected").length, chk = cs.filter(needCheck).length, go = cs.filter(c => c.plan.b === "go").length;
        html += '<tr class="crow' + (open ? " open" : "") + '" data-cat="' + k + '"><td class="fold">' + (open ? "▾" : "▸") + "</td><td>" + A.catTag(k) + "</td><td><b>" + cs.length + "</b></td><td>" + causes.length + "</td><td>" + (sus ? '<span class="num o">' + sus + "</span>" : "-") + "</td><td>" + (chk ? '<span class="num o">' + chk + "</span>" : "-") + "</td><td>" + (go ? '<span class="num b">' + go + "</span>" : "-") + "</td><td>" + M.CATS[k].owner + '</td><td class="hint">' + A.NEXT[k] + "</td></tr>";
        if (!open) return;
        html += '<tr class="cdet"><td colspan="9"><div class="cbox"><div class="cbar"><a data-gsel="' + k + '">全选本类</a><a data-gedit="' + k + '">整类改分类</a><a data-gcopy="' + k + '">复制用例编号</a></div>' +
          '<table class="tbl inner"><thead><tr><th class="ck"></th><th>用例</th><th>名称</th><th>判断依据</th><th>判定</th><th>重跑</th><th>人工核查</th><th>操作</th></tr></thead><tbody>' +
          causes.map((x, xi) => '<tr class="g2"><td colspan="8">原因 ' + (xi + 1) + "：" + esc(causeName(x.cs[0])) + " <b>" + x.cs.length + ' 条</b><span class="g-ops"><a data-gsel="' + k + "|" + xi + '">全选</a><a data-gedit="' + k + "|" + xi + '">整组改分类</a><a data-gcopy="' + k + "|" + xi + '">复制用例编号</a></span></td></tr>' + x.cs.map(c => caseRow(c, v)).join("")).join("") +
          "</tbody></table></div></td></tr>";
      });
      html += "</tbody></table></div>";
    }
    root.innerHTML = html + "</div>";

    const apply = () => { v.run = $("#fRun").value; v.q = $("#fQ").value.trim(); A.render(); };
    $("#fRun").onchange = apply; $("#fQ").onchange = apply;
    if ($("#fSigX")) $("#fSigX").onclick = () => { v.sig = ""; A.render(); };
    $$("[data-st]", root).forEach(b => b.onclick = () => { v.st = b.dataset.st; if (v.st) v.open = A.CAT_ORDER.slice(); A.render(); });
    if ($("#fAll")) $("#fAll").onclick = () => { v.open = cats.every(k => v.open.includes(k)) ? [] : cats.slice(); A.render(); };
    $$("tr.crow", root).forEach(tr => tr.onclick = () => { const k = tr.dataset.cat; v.open = v.open.includes(k) ? v.open.filter(x => x !== k) : v.open.concat(k); A.render(); });
    const groupOf = key => { const [k, xi] = key.split("|"); const cs = byCat[k] || []; return xi === undefined ? cs : causesOf(cs)[+xi].cs; };
    $$("[data-gsel]", root).forEach(a => a.onclick = () => { const ids = groupOf(a.dataset.gsel).map(c => c.uid); const on = ids.every(u => v.sel.includes(u)); v.sel = on ? v.sel.filter(u => !ids.includes(u)) : Array.from(new Set(v.sel.concat(ids))); A.render(); });
    $$("[data-gedit]", root).forEach(a => a.onclick = () => batchDialog(groupOf(a.dataset.gedit).map(c => c.uid)));
    $$("[data-gcopy]", root).forEach(a => a.onclick = () => A.copy(Array.from(new Set(groupOf(a.dataset.gcopy).map(c => c.id))).join("\n")));
    $$("[data-sel]", root).forEach(cb => cb.onchange = () => { const u = cb.dataset.sel; v.sel = cb.checked ? v.sel.concat(u) : v.sel.filter(x => x !== u); A.render(); });
    $$("[data-open]", root).forEach(a => a.onclick = () => openCase(a.dataset.open));
    $$("[data-quick]", root).forEach(a => a.onclick = () => batchDialog([a.dataset.quick]));
    $$("[data-dc]", root).forEach(s => { s.onclick = e => e.stopPropagation(); s.onchange = () => setCheck(s.dataset.dc, s.value); });
    if (v.sel.length) {
      $("#bBatch").onclick = () => batchDialog(v.sel, () => { v.sel = []; });
      $("#bRerun").onclick = () => addToRerun(v.sel.map(u => S.byUid[u]));
      $("#bClr").onclick = () => { v.sel = []; A.render(); };
    }
    $("#bAI").onclick = () => material(v.sel.length ? v.sel.map(u => S.byUid[u]) : list.filter(c => !c.override && c.auto.status === "suspected"));
  }
  function material(pick) {
    if (!pick.length) { A.toast("没有待复核的用例；也可以先勾选用例", true); return; }
    A.showText("复核材料（" + pick.length + " 条）", pick.map(c => {
      const a = c.auto;
      let s = "用例 " + c.id + (c.parent ? "（重跑第2次）" : "") + (c.name ? "  " + c.name : "") + "\n初步结论：" + M.CATS[c.final].name + "（" + (c.override ? "人工已改" : a.status === "confirmed" ? "规则确认" : "待复核") + " · " + c.ruleName + "）\n判断依据：" + a.brief + "\n" +
        (a.why.length ? "详细依据：\n" + a.why.map(w => "  - " + w).join("\n") + "\n" : "") + (a.need.length ? "还需确认：\n" + a.need.map(w => "  - " + w).join("\n") + "\n" : "") + "证据：\n";
      a.ev.forEach(e => { let t = e.text; if (e.kind === "stack" && t.length > 1500) t = t.slice(0, 1500) + "\n…（已截断）"; s += "  " + e.id + " " + e.label + "：" + (t.indexOf("\n") >= 0 ? "\n" + t.split("\n").map(l => "    " + l).join("\n") : t) + "\n"; });
      return s;
    }).join("\n----------\n\n"));
  }
  async function setCheck(uid, val) {
    const c = S.byUid[uid], before = c.final, kind = c.auto.checkKind, sig = c.sig;
    if (!(await A.act("/api/case", { uids: [uid], set: { dataCheck: val || null } }))) return;
    const n = S.byUid[uid];
    const same = S.cases.filter(x => x.uid !== uid && x.failed && !x.override && x.auto.checkKind === kind && x.sig === sig && x.dataCheck !== n.dataCheck);
    if (val && same.length) A.dialog("同一原因的其他用例", "已保存（" + M.CATS[before].name + " → " + M.CATS[n.final].name + "）。还有 " + same.length + " 条是同一原因：" + same.map(x => esc(x.id)).join("、") + "。用的是同一组数据时可以沿用。",
      [{ t: "不用" }, { t: "沿用到这 " + same.length + " 条", pri: true, fn: () => A.act("/api/case", { uids: same.map(x => x.uid), set: { dataCheck: val, dataNote: (n.dataNote || "") + "（沿用 " + n.id + " 的核查）" } }, "已沿用") }]);
    else A.toast("已保存：" + M.CATS[before].name + (before !== n.final ? " → " + M.CATS[n.final].name : "，分类不变"));
  }
  function addToRerun(list) {
    const cs = list.filter(c => c && !c.parent && !c.rerun);
    if (!cs.length) return A.toast("选中的用例都已重跑过，或是重跑产生的第2次记录", true);
    const rv = S.view["triage:rerun"] = S.view["triage:rerun"] || {};
    if (rv.run !== cs[0].run) rv.sel = [];
    rv.run = cs[0].run; rv.sel = Array.from(new Set((rv.sel || []).concat(cs.filter(c => c.run === cs[0].run).map(c => c.uid)))); rv.tab = "all";
    A.go("rerun"); A.toast("已加入重跑名单");
  }

  function batchDialog(uids, after) {
    const cs = uids.map(u => S.byUid[u]).filter(Boolean);
    if (!cs.length) return;
    const one = cs.length === 1 ? cs[0] : null;
    A.dialog(one ? "修改分类：" + one.id : "批量修改分类（" + cs.length + " 条）",
      (one ? '<p class="hint" style="margin-top:0">自动分类：' + M.CATS[one.auto.cat].name + "（" + esc(one.ruleName) + "）</p>" : '<p class="hint" style="margin-top:0">' + cs.slice(0, 12).map(c => esc(c.id)).join("、") + (cs.length > 12 ? " 等" : "") + "</p>") +
      '<div style="display:grid;gap:8px"><label><div style="margin-bottom:4px">人工分类</div><select class="sel" id="bdCat" style="width:100%">' + A.catOptions(one && one.override ? one.override.cat : "", "请选择") + "</select></label>" +
      '<label><div style="margin-bottom:4px">原因 <span class="red">*</span></div><textarea class="ta" id="bdReason" rows="3" placeholder="看到的证据，例如：截图中有“系統公告”弹窗挡住了提交按钮">' + esc(one && one.override ? one.override.reason : "") + "</textarea></label>" +
      (one ? '<label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="bdCorr">同时加入纠错样本（以后改规则时检查这条能不能判对）</label>' : "") + "</div>",
      [{ t: "取消" }].concat(cs.some(c => c.override) ? [{ t: "恢复自动分类", fn: () => A.act("/api/case", { uids, set: { override: null } }, "已恢复").then(() => after && after()) }] : []).concat([{ t: "保存", pri: true, fn: async () => {
        const cat = $("#bdCat").value, reason = $("#bdReason").value.trim(), corr = $("#bdCorr") && $("#bdCorr").checked;
        if (!cat || !reason) { A.toast("请选择分类并填写原因", true); return false; }
        if (!(await A.act("/api/case", { uids, set: { override: { cat, reason, at: A.now() } } }, "已保存"))) return false;
        if (corr) await A.act("/api/corrections/add", { uid: one.uid, category: cat, reason, by: A.who() }, r => "已加入纠错样本 " + r.id + (r.test.ok ? "（规则已能判对）" : "（规则现在判为 " + M.CATS[r.test.got.category].name + "，需要补规则）"));
        if (after) after();
      } }]));
  }
  A.batchDialog = batchDialog;

  function corrDialog(c) {
    const cat = c.override ? c.override.cat : c.final;
    A.dialog("加入纠错样本：" + c.id, '<p class="hint" style="margin-top:0">保存这条用例的日志和人工记录。以后每次改规则，都检查它还能不能判对。</p>' +
      '<div style="display:grid;gap:8px"><label><div style="margin-bottom:4px">正确分类</div><select class="sel" id="ccCat" style="width:100%">' + A.catOptions(cat) + "</select></label>" +
      (!c.override ? '<label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ccRule">还要命中同一条规则（' + esc(c.ruleName) + "）</label>" : "") +
      '<label><div style="margin-bottom:4px">为什么是这个分类 <span class="red">*</span></div><textarea class="ta" id="ccWhy" rows="3">' + esc(c.override ? c.override.reason : "") + "</textarea></label></div>",
      [{ t: "取消" }, { t: "保存", pri: true, fn: () => {
        const why = $("#ccWhy").value.trim(); if (!why) { A.toast("请写明原因", true); return false; }
        return A.act("/api/corrections/add", { uid: c.uid, category: $("#ccCat").value, keepRule: $("#ccRule") && $("#ccRule").checked, reason: why, by: A.who() },
          r => "已保存为 " + r.id + (r.test.ok ? "，规则能判对" : "，规则现在判为 " + M.CATS[r.test.got.category].name + "，需要补规则（配置 → 自定义规则）"));
      } }]);
  }

  /* ---------- 用例详情 ---------- */
  let pasteUid = null;
  document.addEventListener("paste", e => {
    if (!pasteUid || !A.drawerOpen() || $("#dlg").classList.contains("open")) return;
    if (e.target && /^(TEXTAREA|INPUT)$/.test(e.target.tagName)) return;
    const files = Array.from((e.clipboardData || {}).items || []).filter(i => i.type.indexOf("image") === 0).map(i => i.getAsFile());
    if (!files.length) return;
    e.preventDefault(); A.addImgs(pasteUid, files);
  });
  const shotsHtml = (list, del, pre) => list.map((s, i) => '<div class="shot"><img src="' + s.src + '" alt="" data-big="' + s.src + '" title="' + esc(s.name) + '"><div class="hint">' + esc(s.name) + (del ? ' <a data-delshot="' + i + '" class="red">删除</a>' : "") + ' <a href="' + s.src + '" download="' + esc(s.name) + '">下载</a></div></div>').join("");
  function openCase(uid) {
    const c = S.byUid[uid]; if (!c) { A.closeDrawer(); return; }
    pasteUid = uid;
    const a = c.auto, sus = a.status === "suspected", o = c.obs || {};
    const hits = a.hits.concat(c.exception ? [c.exception] : []);
    const kind = a.checkKind && !c.override && M.CHECK_KINDS[a.checkKind];
    const sameN = S.cases.filter(x => x.failed && x.sig === c.sig && x.final === c.final).length;
    let b = '<div class="sec"><h5>判断依据 ' + A.catTag(c.final) + A.statusTag(c) + '<span class="tag gray">' + esc(c.ruleName) + "</span>" + A.planTag(c) + "</h5>" +
      '<div class="verdict' + (sus && !c.override ? " sus" : "") + '"><div class="brief">' + esc(a.brief) + "</div><ul>" + a.why.map(w => "<li>" + esc(w) + "</li>").join("") + "</ul>" + (a.need.length ? "<b>下一步</b><ul>" + a.need.map(w => "<li>" + esc(w) + "</li>").join("") + "</ul>" : "") + '<div class="hint">重跑：' + esc(c.plan.why) + "</div></div></div>";
    if (c.override) b += '<div class="sec"><h5>人工结论 ' + A.catTag(c.override.cat) + '</h5><div class="verdict">' + esc(c.override.reason) + '<div class="hint">' + esc(c.override.at || "") + "；规则原本判为 " + M.CATS[a.cat].name + "</div></div></div>";
    b += '<div class="sec"><h5>截图' + (c.shots2.length ? "（第 1 次）" : "") + '</h5><div class="shots">' + shotsHtml(c.shots, true) +
      '<label class="shot add"><input type="file" accept="image/*" multiple id="dShotF" hidden><span>＋ 选择图片<br><small>或 Ctrl+V</small></span></label></div>' +
      (!c.shots.length && c.screenshot ? '<p class="hint">报告里的截图路径：' + esc(c.screenshot) + "</p>" : "") +
      (c.shots2.length ? '<h5 style="margin-top:8px">截图（第 2 次）</h5><div class="shots">' + shotsHtml(c.shots2, false) + "</div>" : "") + "</div>";
    b += '<div class="sec obs"><h5>截图观察</h5><div class="obs-k">' + Object.entries(M.OBS_KINDS).map(([k, n]) => '<label><input type="radio" name="obsK" value="' + k + '"' + (o.kind === k ? " checked" : "") + ">" + esc(n) + "</label>").join("") + "</div>" +
      '<input class="inp" id="obsT" style="width:100%;margin-top:6px" placeholder="弹窗或页面上的文字（照抄原文）" value="' + esc(o.text || "") + '">' +
      '<div style="margin-top:6px;display:flex;gap:6px;align-items:center"><button class="btn sm pri" id="obsGo">保存并重新分析</button>' + (c.ocrText && !o.text ? '<button class="btn sm" id="ocrUse">填入识别文字</button>' : "") + (o.kind || o.text ? '<button class="btn sm" id="obsClr">清除</button>' : "") + "</div></div>";
    if (kind) b += '<div class="sec"><h5>人工核查：' + esc(kind.name) + '</h5><div class="verdict sus"><div>' + esc(kind.what) + '</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px"><select class="sel" id="dData"><option value="">未核查</option>' + Object.entries(kind.options).map(([k, op]) => '<option value="' + k + '"' + (c.dataCheck === k ? " selected" : "") + ">" + esc(op[0]) + " → " + M.CATS[op[1]].name + "</option>").join("") + '</select><input class="inp" id="dNote" placeholder="查了什么、谁查的" value="' + esc(c.dataNote || "") + '"></div><button class="btn sm pri" id="dSave" style="margin-top:6px">保存核查结果</button></div></div>';
    // 证据：完整日志、截图识别文字默认收起
    const evBody = e => e.kind === "shot" && e.src ? '<img class="evimg" src="' + e.src + '" data-big="' + e.src + '" alt="">' : "<pre>" + A.highlight(e.text, hits) + "</pre>";
    b += '<div class="sec"><h5>证据</h5>' + a.ev.filter(e => e.kind !== "shot").map(e => ["stack", "ocr"].includes(e.kind)
      ? '<details class="ev"><summary class="eh"><b>' + e.id + "</b>" + esc(e.label) + "</summary>" + evBody(e) + "</details>"
      : '<div class="ev"><div class="eh"><b>' + e.id + "</b>" + esc(e.label) + "</div>" + evBody(e) + "</div>").join("") + "</div>";
    b += '<div class="sec"><h5>基本信息</h5><dl class="kv"><dt>批次</dt><dd>' + esc(A.runName(c.run)) + "</dd><dt>执行结果</dt><dd>" + esc(c.result) + (c.parent ? '（重跑第2次，<a id="dPar">看第一次</a>）' : "") + "</dd>" +
      (c.module ? "<dt>模块</dt><dd>" + esc(c.module) + "</dd>" : "") + (c.device ? "<dt>设备</dt><dd>" + esc(c.device) + "</dd>" : "") + (c.start ? "<dt>开始时间</dt><dd>" + esc(c.start) + "</dd>" : "") +
      '<dt>同一原因</dt><dd><a id="dSig">共 ' + sameN + " 条</a></dd>" +
      (!c.parent ? '<dt>重跑结果</dt><dd><select class="sel xs" id="dRerun"><option value="">未重跑</option><option value="pass"' + (c.rerun === "pass" ? " selected" : "") + '>重跑通过</option><option value="fail"' + (c.rerun === "fail" ? " selected" : "") + ">重跑仍失败（同一问题）</option></select></dd>" : "") + "</dl></div>";
    A.drawer(A.caseLabel(c) + ' <span class="hint n">' + esc(c.name || "") + "</span>", b,
      '<button class="btn" id="dCorr">加入纠错样本</button><button class="btn" id="dAI">复制复核材料</button><button class="btn pri" id="dOver">' + (c.override ? "修改人工结论" : "确认 / 改分类") + "</button>", () => openCase(uid));
    const save = (set, msg) => { const before = c.final; return A.act("/api/case", { uids: [uid], set }, () => { const n = S.byUid[uid]; return msg + (n ? (before !== n.final ? "：" + M.CATS[before].name + " → " + M.CATS[n.final].name : "：分类不变") : ""); }); };
    $("#dSig").onclick = () => { A.closeDrawer(); A.go("triage", { sig: c.sig, st: "", run: "", open: [c.final] }); };
    if ($("#dPar")) $("#dPar").onclick = () => openCase(c.parent);
    $("#dAI").onclick = () => material([c]);
    $("#dCorr").onclick = () => corrDialog(c);
    $("#dOver").onclick = () => batchDialog([uid]);
    $("#dShotF").onchange = e => A.addImgs(uid, Array.from(e.target.files));
    $$("[data-delshot]").forEach(x => x.onclick = () => A.act("/api/shots/del", { uid, idx: +x.dataset.delshot }, "已删除"));
    $$("[data-big]").forEach(img => img.onclick = () => { A.dialog("截图", '<img src="' + img.dataset.big + '" style="max-width:100%">', [{ t: "关闭" }]); $("#dlg").style.width = "90vw"; });
    if ($("#ocrUse")) $("#ocrUse").onclick = () => { $("#obsT").value = c.ocrText.replace(/\s*\n\s*/g, " / ").slice(0, 500); $("#obsT").focus(); };
    $("#obsGo").onclick = () => {
      const k = ($$('input[name="obsK"]').find(r => r.checked) || {}).value || "", t = $("#obsT").value.trim();
      if (!k && !t) { A.toast("请选择看到的现象，或填写截图中的文字", true); return; }
      save({ obs: { kind: k, text: t, at: A.now() } }, "已重新分析");
    };
    if ($("#obsClr")) $("#obsClr").onclick = () => save({ obs: null }, "已清除");
    if ($("#dSave")) $("#dSave").onclick = () => save({ dataCheck: $("#dData").value || null, dataNote: $("#dNote").value.trim() }, "核查结果已保存");
    if ($("#dRerun")) $("#dRerun").onchange = e => setRerun(c, e.target.value);
  }
  A.openCase = openCase;
  function setRerun(c, val) {
    const set = val ? { rerun: val, rerunNote: "手工填写 " + A.now(), rerunReq: null, r2: c.r2 || { same: val === "fail" ? true : null } } : { rerun: null, rerunNote: null, r2: null };
    return A.act("/api/case", { uids: [c.uid], set }, "已保存");
  }

  /* ============================== ② 重跑 ============================== */
  const BK = [["go", "建议立即重跑"], ["fix", "处理后再重跑"], ["no", "不需要重跑"], ["done", "已重跑"]];
  function rerunPage(root, v) {
    if (!S.runs.length) return A.noData(root);
    v.run = S.runs.find(r => r.id === v.run) ? v.run : A.lastRun(); v.tab = v.tab || "all";
    const fs = A.failed(v.run).sort((a, b) => a.seq - b.seq || (a.parent ? 1 : -1));
    if (!v.sel) v.sel = fs.filter(c => c.plan.b === "go").map(c => c.uid);
    v.sel = v.sel.filter(u => fs.some(c => c.uid === u && !c.parent && !c.rerun));
    const cnt = k => fs.filter(c => c.plan.b === k).length;
    const shown = fs.filter(c => v.tab === "all" || c.plan.b === v.tab);
    const sent = fs.filter(c => c.rerunReq && !c.rerun && !c.parent).length;
    let html = '<div class="card"><div class="form"><label class="fi"><span>批次</span>' + A.runSelect("rRun", v.run) + '</label><span class="hint">建议立即重跑 ' + cnt("go") + "，处理后再重跑 " + cnt("fix") + "，不需要 " + cnt("no") + "，已重跑 " + cnt("done") + (sent ? "；已发起、等待结果 " + sent : "") + '</span><span class="sp"></span><a data-go="home" data-opts=\'{"sub":"guide"}\'>重跑标准</a></div></div>';
    html += '<div class="card"><div class="bar"><div class="chips"><button data-rt="all" class="' + (v.tab === "all" ? "on" : "") + '">全部 ' + fs.length + "</button>" + BK.map(([k, n]) => '<button data-rt="' + k + '" class="' + (v.tab === k ? "on" : "") + '">' + n + " " + cnt(k) + "</button>").join("") + '</div><span class="sp"></span>' +
      '<span class="hint">名单 ' + v.sel.length + ' 条</span><button class="btn sm" id="rPickGo">勾选“建议立即重跑”</button><button class="btn sm" id="rClear">清空</button><button class="btn sm" id="rCopy">复制用例编号</button><button class="btn sm" id="rImp">导入重跑结果</button><button class="btn sm pri" id="rRun1"' + (v.sel.length ? "" : " disabled") + ">一键重跑（" + v.sel.length + "）</button></div>" +
      '<div class="tbl-wrap"><table class="tbl"><thead><tr><th class="ck"><input type="checkbox" id="rAll"></th><th>用例</th><th>名称</th><th>分类</th><th>判断依据</th><th>重跑建议</th><th>理由</th><th>重跑结果</th></tr></thead><tbody>' +
      shown.map(c => {
        const can = !c.parent && !c.rerun;
        return '<tr class="' + (isSel(v, c.uid) ? "sel" : "") + '"><td class="ck">' + (can ? '<input type="checkbox" data-rs="' + c.uid + '"' + (isSel(v, c.uid) ? " checked" : "") + ">" : "") + '</td><td class="mono nw"><a data-open="' + c.uid + '">' + A.caseLabel(c) + '</a></td><td class="nm">' + esc(c.name) + "</td><td>" + A.catTag(c.final) + '</td><td class="basis">' + esc(c.auto.brief) + '</td><td class="nw">' + A.planTag(c) + (c.rerunReq && can ? '<div class="hint">已发起 ' + esc(String(c.rerunReq).slice(0, 16)) + "</div>" : "") + '</td><td class="hint">' + esc(c.plan.why) + "</td>" +
          "<td>" + (c.parent ? "-" : '<select class="sel xs" data-rr="' + c.uid + '"><option value="">未重跑</option><option value="pass"' + (c.rerun === "pass" ? " selected" : "") + '>通过</option><option value="fail"' + (c.rerun === "fail" ? " selected" : "") + ">仍失败</option></select>") + "</td></tr>";
      }).join("") + "</tbody></table></div>" + (shown.length ? "" : A.emptyBlock("这一类没有用例")) + "</div>";
    root.innerHTML = html;
    A.bindGo(root);
    $("#rRun").onchange = e => { v.run = e.target.value; v.sel = null; A.render(); };
    $$("[data-rt]", root).forEach(b => b.onclick = () => { v.tab = b.dataset.rt; A.render(); });
    $$("[data-rs]", root).forEach(cb => cb.onchange = () => { const u = cb.dataset.rs; v.sel = cb.checked ? v.sel.concat(u) : v.sel.filter(x => x !== u); A.render(); });
    $("#rAll").onchange = e => { const ids = shown.filter(c => !c.parent && !c.rerun).map(c => c.uid); v.sel = e.target.checked ? Array.from(new Set(v.sel.concat(ids))) : v.sel.filter(x => !ids.includes(x)); A.render(); };
    $("#rPickGo").onclick = () => { v.sel = Array.from(new Set(v.sel.concat(fs.filter(c => c.plan.b === "go").map(c => c.uid)))); A.render(); };
    $("#rClear").onclick = () => { v.sel = []; A.render(); };
    $$("[data-rr]", root).forEach(s => s.onchange = () => setRerun(S.byUid[s.dataset.rr], s.value));
    $$("[data-open]", root).forEach(a => a.onclick = () => openCase(a.dataset.open));
    const picked = () => v.sel.map(u => S.byUid[u]);
    $("#rCopy").onclick = () => { if (!v.sel.length) return A.toast("请先勾选用例", true); A.copy(picked().map(c => c.id).join("\n")); };
    $("#rImp").onclick = () => A.go("import", { info: { name: "", plan: "", device: "", env: "", mode: "rerun", rerunOf: v.run } });
    $("#rRun1").onclick = () => {
      const cs = picked(), fixN = cs.filter(c => c.plan.b === "fix").length, url = (S.jira.rerunUrl || "").trim();
      A.dialog("一键重跑（" + cs.length + " 条）", (fixN ? '<p style="margin-top:0" class="orange">其中 ' + fixN + " 条是“处理后再重跑”，请确认已处理。</p>" : "") +
        '<p class="hint" style="margin-top:0">' + cs.map(c => esc(c.id)).join("、") + "</p>" + (url ? "<p>发送到重跑接口：<code>" + esc(url) + "</code></p>" : "<p>没有配置重跑接口，会复制用例编号，请到平台粘贴重跑。</p>"),
        [{ t: "取消" }, { t: url ? "确认并发送" : "确认并复制编号", pri: true, fn: async () => {
          const r = await A.act("/api/rerun/send", { run: v.run, uids: cs.map(c => c.uid) }, r => r.msg);
          if (r && r.copied) A.copy(r.ids.join("\n"));
        } }]);
    };
  }

  /* ============================== ③ 分派 ============================== */
  const PACK_COLS = ["序号", "用例编号", "用例名称", "分类", "原因", "判断依据", "需要做什么", "重跑", "截图"];
  function packRows(d, scope) {
    const cs = scope.filter(c => d.cats.includes(c.final) && c.rerun !== "pass"), rows = [];
    A.CAT_ORDER.filter(k => d.cats.includes(k)).forEach(k => causesOf(cs.filter(c => c.final === k)).forEach(x => x.cs.forEach(c => rows.push([
      rows.length + 1, c.id + (c.parent ? "（第2次）" : ""), c.name || "", M.CATS[c.final].name, c.ruleName, c.auto.brief, c.auto.need[0] || A.NEXT[c.final], c.rerun ? rerunText(c) : M.PLAN[c.plan.b], c.shots.length ? "有（" + c.shots.length + "）" : c.screenshot ? "见报告" : "无"]))));
    return rows.map(r => r.map(String));
  }
  function packHtml(title, rows) {
    const td = "border:1px solid #c8ccd2;padding:4px 6px;vertical-align:top;";
    return '<p style="font-family:Arial,Microsoft YaHei;font-size:12px;margin:0 0 6px"><b>' + esc(title) + '</b></p><table style="border-collapse:collapse;font-family:Arial,Microsoft YaHei;font-size:12px"><tr>' + PACK_COLS.map(h => '<th style="' + td + 'background:#eef1f5;text-align:left">' + h + "</th>").join("") + "</tr>" +
      rows.map(r => "<tr>" + r.map(x => '<td style="' + td + '">' + esc(x) + "</td>").join("") + "</tr>").join("") + "</table>";
  }
  function dispatchPage(root, v) {
    if (!S.runs.length) return A.noData(root);
    v.run = S.runs.find(r => r.id === v.run) ? v.run : A.lastRun(); v.who = v.who || "dev";
    const scope = A.failed(v.run), skip = scope.filter(c => c.rerun === "pass").length;
    const d = DISPATCH.find(x => x.k === v.who), rows = packRows(d, scope);
    const title = "【" + d.name + "】" + A.runName(v.run) + "：共 " + rows.length + " 条";
    let html = '<div class="card"><div class="form"><label class="fi"><span>批次</span>' + A.runSelect("dRun", v.run) + "</label>" + (skip ? '<span class="hint">重跑已通过的 ' + skip + " 条不列入</span>" : "") + "</div></div>";
    html += '<div class="dispatch">' + DISPATCH.map(x => {
      const cs = scope.filter(c => x.cats.includes(c.final) && c.rerun !== "pass");
      return '<button class="dp' + (x.k === v.who ? " on" : "") + (cs.length ? "" : " zero") + '" data-who="' + x.k + '"><div class="dp-h"><b>' + x.name + '</b><span class="num">' + cs.length + '</span></div><div class="hint">' + x.cats.map(k => M.CATS[k].name + " " + cs.filter(c => c.final === k).length).join(" · ") + '</div><div class="hint">' + x.todo + "</div></button>";
    }).join("") + "</div>";
    html += '<div class="card"><div class="card-h"><b>' + esc(title) + '</b><span class="sp"></span><button class="btn sm pri" id="pkRich"' + (rows.length ? "" : " disabled") + '>复制为表格</button><button class="btn sm" id="pkText"' + (rows.length ? "" : " disabled") + ">复制为文字</button></div>" +
      (rows.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr>' + PACK_COLS.map(h => "<th>" + h + "</th>").join("") + "</tr></thead><tbody>" + rows.map(r => "<tr>" + r.map((x, i) => "<td" + (i === 5 ? ' class="basis"' : i === 1 ? ' class="mono nw"' : "") + ">" + esc(x) + "</td>").join("") + "</tr>").join("") + "</tbody></table></div>" : A.emptyBlock("没有用例")) + "</div>";
    root.innerHTML = html;
    $("#dRun").onchange = e => { v.run = e.target.value; A.render(); };
    $$("[data-who]", root).forEach(b => b.onclick = () => { v.who = b.dataset.who; A.render(); });
    const text = () => title + "\n" + [PACK_COLS].concat(rows).map(r => r.map(x => String(x).replace(/[\t\n]+/g, " ")).join("\t")).join("\n");
    if ($("#pkRich")) $("#pkRich").onclick = () => A.copyRich(packHtml(title, rows), text());
    if ($("#pkText")) $("#pkText").onclick = () => A.copy(text());
  }

  A.composite("triage", [
    ["main", "① 分诊", mainPage, () => S.cases.filter(c => c.failed && !c.override && c.auto.status === "suspected").length],
    ["rerun", "② 重跑", rerunPage, () => S.cases.filter(c => c.failed && c.plan.b === "go").length],
    ["dispatch", "③ 分派", dispatchPage],
  ]);
})();
