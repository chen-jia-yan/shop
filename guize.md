把所有规则做成一张表，改之前和改之后的差别用不同底色标出来。下面是要改的地方，共 5 个文件，都在 ‎⁠regression-triage-jira/⁠ 下。

做出来的效果

“配置 → 判断规则”分成两个页签：

页签   |   每一行是什么   |    列

规则清单（可以改）  |  ⁠rules.json⁠ 里的一个清单，共 30 个   |   分组 · 清单名称和说明 · 用于哪些规则 · 内容（每项一个小标签） · 差异 · 编辑/撤销

规则一览（只看）   |   一条判断规则：最上面是自定义规则，下面是 41 条内置规则，按判断顺序排   |   顺序 · 编号 · 名称 · 什么情况下命中 · 用到的清单（点一下跳到那个清单去改） · 分类 · 判定 · 重跑



底色的意思：

- 绿：比对照多了项。

- 红：比对照少了项，少掉的项划删除线显示。

- 橙：有增有删，或者数值改了。

- 黄：改了但还没保存。

在规则一览里，某条规则用到的清单改过，这一行也会跟着标色。

“对照”可以选两种：

- 默认规则：看团队一共改了哪些。

- 最近一次修改之前：看上一次改了什么。

另外还有“只看有差异 / 只看未保存”筛选和搜索。改几行之后点一次“保存”，会一起保存。

1. ‎⁠scripts/ta_engine.py⁠：加规则说明表

在 ‎⁠RULE_NAMES = {...}⁠ 结束的 ‎⁠}⁠ 之后、‎⁠def rule_name(c):⁠ 之前（大约第 870 行），插入下面这段。它只给页面显示用，不参与判断：# ======================= 规则一览（只用于页面展示和说明，判断逻辑在上面的 classify_core / classify 里） =======================

# 改了判断逻辑（新增规则编号、改条件、改分类）时，同步改这里；ta.py check 会检查每个规则编号都在这里有一行。

# stage：判断顺序，数字小的先判断，第一条命中的生效。uses：用到 rules.json 里的哪些清单。

# cat 写分类代码；“按核查结果”的写 "CHECK"。rerun：go 立即重跑 / fix 处理后再重跑 / no 不需要（核查前一律 fix）。

RULE_STAGES = {"1": "环境", "2": "系统提示", "3": "原生对话框", "4": "业务报错", "5": "网页弹框", "6": "桌面端控件（需要 Python 日志）",

               "7": "脚本问题", "8": "断言", "9": "兜底", "10": "截图观察（人工记录后修正）"}

RULE_TABLE = [

    {"id": "ENV1", "stage": "1", "when": "异常类型在清单里（浏览器/驱动/设备起不来）", "uses": ["env_exceptions"], "cat": "ENVIRONMENT", "status": "confirmed", "rerun": "go"},

    {"id": "ENV-DESK", "stage": "1", "when": "报错含环境关键字，且是桌面类（SetCursorPos、active desktop、DESKTOP_UNAVAILABLE）", "uses": ["env_patterns"], "cat": "ENVIRONMENT", "status": "confirmed", "rerun": "go"},

    {"id": "ENV2", "stage": "1", "when": "报错含其他环境关键字（连接、服务、数据库）", "uses": ["env_patterns"], "cat": "ENVIRONMENT", "status": "confirmed", "rerun": "go"},

    {"id": "ENV3", "stage": "1", "when": "同一报错出现在至少 N 个用例、占失败数至少 X%，且执行顺序连续或集中在 M 分钟内", "uses": ["mass_min_cases", "mass_ratio", "mass_window_min"], "cat": "ENVIRONMENT", "status": "suspected", "rerun": "go"},

    {"id": "SYS-EMPTY", "stage": "2", "when": "出现了弹窗，但脚本没读到弹窗文字", "uses": [], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "go"},

    {"id": "DATA-LOCK", "stage": "2", "when": "系统提示（或截图里抄下的文字）含数据被占用的提示", "uses": ["lock_messages"], "cat": "TEST_DATA", "status": "confirmed", "rerun": "fix"},

    {"id": "CHK-LOCK1", "stage": "2", "when": "同上，人工核查：被本批次前面失败的用例占用", "uses": ["lock_messages"], "cat": "SCRIPT_ISSUE", "status": "confirmed", "rerun": "fix"},

    {"id": "SYS-CFG", "stage": "2", "when": "系统提示含缺少配置，还没核查", "uses": ["config_messages"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "CHK-CFG", "stage": "2", "when": "同上，已核查：缺配置 → 环境问题；配置正确仍报错 → 产品缺陷；不支持的场景 → 测试数据", "uses": ["config_messages"], "cat": "CHECK", "status": "confirmed", "rerun": "fix"},

    {"id": "SYS-CRASH", "stage": "2", "when": "被测程序弹出未处理异常对话框", "uses": ["crash_messages"], "cat": "PRODUCT_DEFECT", "status": "suspected", "rerun": "no"},

    {"id": "OBS-POPN", "stage": "2", "when": "截图里抄下（或识别出）的文字在干扰弹窗清单里", "uses": ["noise_popups"], "cat": "POPUP_INTERFERENCE", "status": "confirmed", "rerun": "go"},

    {"id": "POP1", "stage": "3", "when": "出现原生对话框，文字在干扰弹窗清单里", "uses": ["alert_exceptions", "noise_popups"], "cat": "POPUP_INTERFERENCE", "status": "confirmed", "rerun": "go"},

    {"id": "POP1-未知", "stage": "3", "when": "出现原生对话框，文字既不是干扰弹窗也不是业务报错", "uses": ["alert_exceptions", "noise_popups", "business_errors"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "go"},

    {"id": "BIZ2", "stage": "4", "when": "页面/弹窗文字含业务报错，人工核查：数据正常", "uses": ["business_errors"], "cat": "PRODUCT_DEFECT", "status": "confirmed", "rerun": "no"},

    {"id": "BIZ1", "stage": "4", "when": "同上，人工核查：数据不存在、已使用或状态不对", "uses": ["business_errors"], "cat": "TEST_DATA", "status": "confirmed", "rerun": "fix"},

    {"id": "BIZ3", "stage": "4", "when": "同上，还没核查（断言失败或没有异常类型时也看报错文字）", "uses": ["business_errors", "assertion_exceptions"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "POP2", "stage": "5", "when": "页面上有干扰弹框，且是点击/定位失败", "uses": ["noise_popups", "intercept_exceptions", "locator_exceptions"], "cat": "POPUP_INTERFERENCE", "status": "confirmed", "rerun": "go"},

    {"id": "POP3", "stage": "5", "when": "点击被挡住，挡住的元素有弹框特征", "uses": ["intercept_exceptions", "overlay_keywords"], "cat": "POPUP_INTERFERENCE", "status": "suspected", "rerun": "go"},

    {"id": "POP3-弱", "stage": "5", "when": "点击被挡住，挡住的元素没有弹框特征", "uses": ["intercept_exceptions"], "cat": "POPUP_INTERFERENCE", "status": "suspected", "rerun": "go"},

    {"id": "MASK1", "stage": "6", "when": "最先的异常是 bool/None 的使用错误（前一步没找到东西，返回了 False/None）", "uses": ["masked_patterns"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "DSK-AMB", "stage": "6", "when": "定位条件匹配到多个控件", "uses": ["desk_ambiguous"], "cat": "SCRIPT_ISSUE", "status": "confirmed", "rerun": "fix"},

    {"id": "DSK-OPT", "stage": "6", "when": "下拉框没有要选的选项", "uses": ["desk_option_missing"], "cat": "SCRIPT_ISSUE", "status": "suspected", "rerun": "fix"},

    {"id": "CHK-DTP", "stage": "6", "when": "日期控件设置失败，已核查：超出范围 → 测试数据；在范围内 → 脚本问题", "uses": ["desk_datetime"], "cat": "CHECK", "status": "confirmed", "rerun": "fix"},

    {"id": "DSK-DTP", "stage": "6", "when": "日期控件设置失败，还没核查", "uses": ["desk_datetime"], "cat": "SCRIPT_ISSUE", "status": "suspected", "rerun": "fix"},

    {"id": "DSK-DIS", "stage": "6", "when": "要操作的控件不可用（灰色）", "uses": ["desk_not_enabled"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "DSK-VIS", "stage": "6", "when": "控件存在但不可见", "uses": ["desk_not_visible"], "cat": "SCRIPT_ISSUE", "status": "suspected", "rerun": "go"},

    {"id": "DSK-NF", "stage": "6", "when": "找不到窗口或控件", "uses": ["desk_not_found"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "go"},

    {"id": "GEN1", "stage": "6", "when": "异常类型就是 Exception，消息里没有说明原因", "uses": ["business_errors"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "SCR2", "stage": "7", "when": "定位表达式本身写错", "uses": ["invalid_selector"], "cat": "SCRIPT_ISSUE", "status": "confirmed", "rerun": "fix"},

    {"id": "SCR3", "stage": "7", "when": "测试代码运行错误（堆栈里有测试代码路径才算确认）", "uses": ["code_errors", "test_code_paths"], "cat": "SCRIPT_ISSUE", "status": "confirmed", "rerun": "fix"},

    {"id": "SCR1", "stage": "7", "when": "找不到元素 / 等待超时，没有其他证据", "uses": ["locator_exceptions"], "cat": "SCRIPT_ISSUE", "status": "suspected", "rerun": "go"},

    {"id": "AST1", "stage": "8", "when": "断言失败，有明确的期望值和实际值", "uses": ["assertion_exceptions", "expected_actual"], "cat": "PRODUCT_DEFECT", "status": "suspected", "rerun": "go"},

    {"id": "AST2", "stage": "8", "when": "断言失败，没有期望值和实际值", "uses": ["assertion_exceptions"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "NONE", "stage": "9", "when": "以上都没命中，或没有报错信息", "uses": [], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "OBS-OK", "stage": "10", "when": "人工看截图：页面正常，控件就在屏幕上", "uses": [], "cat": "SCRIPT_ISSUE", "status": "confirmed", "rerun": "fix"},

    {"id": "OBS-POP", "stage": "10", "when": "人工看截图：有弹窗，没抄文字", "uses": [], "cat": "POPUP_INTERFERENCE", "status": "suspected", "rerun": "go"},

    {"id": "OBS-POPU", "stage": "10", "when": "人工看截图：有弹窗，文字不在任何清单里", "uses": ["noise_popups", "business_errors"], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "OBS-BLANK", "stage": "10", "when": "人工看截图：页面空白、报错页或一直加载", "uses": [], "cat": "PRODUCT_DEFECT", "status": "suspected", "rerun": "go"},

    {"id": "OBS-OTHER", "stage": "10", "when": "人工看截图：停在别的窗口或页面", "uses": [], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "go"},

    {"id": "OBS-DIS", "stage": "10", "when": "人工看截图：控件是灰色的", "uses": [], "cat": "NEEDS_HUMAN", "status": "suspected", "rerun": "fix"},

    {"id": "OBS-DESK", "stage": "10", "when": "人工看截图：锁屏、黑屏或远程桌面断开", "uses": [], "cat": "ENVIRONMENT", "status": "confirmed", "rerun": "go"},

]

# rules.json 里每个清单的名称和说明（页面“判断规则 → 规则清单”显示）

RULE_LISTS = [

    {"key": "env_exceptions", "group": "环境问题", "name": "环境类异常类型", "note": "异常名称，命中即判为环境问题"},

    {"key": "env_patterns", "group": "环境问题", "name": "环境类报错关键字", "note": "连接、服务、数据库、桌面不可用等"},

    {"key": "mass_min_cases", "group": "大面积相同报错", "name": "至少几个用例", "note": "同一报错达到这个数量才算大面积"},

    {"key": "mass_ratio", "group": "大面积相同报错", "name": "占失败数比例（%）", "note": ""},

    {"key": "mass_window_min", "group": "大面积相同报错", "name": "时间窗口（分钟）", "note": "执行顺序不连续时，要集中在这个时间内"},

    {"key": "noise_popups", "group": "弹窗", "name": "干扰弹窗文字", "note": "与被测功能无关的公告、会话、浏览器提示"},

    {"key": "business_errors", "group": "弹窗", "name": "业务报错文字", "note": "系统给出的报错，要核查数据才能分清"},

    {"key": "overlay_keywords", "group": "弹窗", "name": "遮挡元素特征", "note": "挡住点击的元素 HTML 里出现这些词，就当作弹框"},

    {"key": "lock_messages", "group": "系统提示", "name": "数据被占用", "note": "命中判为测试数据问题"},

    {"key": "config_messages", "group": "系统提示", "name": "缺少配置", "note": "命中后需要人工核查"},

    {"key": "crash_messages", "group": "系统提示", "name": "程序未处理异常", "note": "命中判为疑似产品缺陷"},

    {"key": "alert_exceptions", "group": "异常类型", "name": "原生对话框", "note": ""},

    {"key": "intercept_exceptions", "group": "异常类型", "name": "点击被遮挡", "note": ""},

    {"key": "locator_exceptions", "group": "异常类型", "name": "找不到元素 / 超时", "note": ""},

    {"key": "invalid_selector", "group": "异常类型", "name": "定位表达式错误", "note": ""},

    {"key": "code_errors", "group": "异常类型", "name": "测试代码运行错误", "note": ""},

    {"key": "assertion_exceptions", "group": "异常类型", "name": "断言失败", "note": ""},

    {"key": "masked_patterns", "group": "桌面端控件", "name": "掩盖型报错", "note": "真实原因被前一步的 False/None 掩盖"},

    {"key": "desk_ambiguous", "group": "桌面端控件", "name": "匹配到多个控件", "note": ""},

    {"key": "desk_not_found", "group": "桌面端控件", "name": "找不到窗口 / 控件", "note": ""},

    {"key": "desk_not_visible", "group": "桌面端控件", "name": "控件不可见", "note": ""},

    {"key": "desk_not_enabled", "group": "桌面端控件", "name": "控件不可用", "note": ""},

    {"key": "desk_option_missing", "group": "桌面端控件", "name": "下拉框没有该选项", "note": ""},

    {"key": "desk_datetime", "group": "桌面端控件", "name": "日期控件设置失败", "note": ""},

    {"key": "framework_paths", "group": "日志解析", "name": "框架和第三方库路径", "note": "找真正出错的业务代码时跳过这些路径"},

    {"key": "handler_funcs", "group": "日志解析", "name": "失败后执行的处理函数", "note": "截图、清理函数里的报错不当作根因"},

    {"key": "success_marks", "group": "日志解析", "name": "业务已成功的文字", "note": "出现后说明失败发生在结果校验阶段"},

    {"key": "test_code_paths", "group": "其他", "name": "测试代码路径特征", "note": "用于 SCR3 确认是测试代码出错"},

    {"key": "expected_actual", "group": "其他", "name": "期望值/实际值格式", "note": "用于 AST1"},

    {"key": "fail_words", "group": "其他", "name": "执行结果中表示失败的文字", "note": "导入时判断哪些用例失败"},

]

2. ‎⁠scripts/ta_store.py⁠：传给页面，并在修改记录里存改前的值

① 大约第 803 行，‎⁠state()⁠ 里，把："JIRA_FIELDS": J.FIELD_NAMES, "DEFAULT_RULES": E.default_rules(),

改成："JIRA_FIELDS": J.FIELD_NAMES, "RULE_TABLE": E.RULE_TABLE, "RULE_LISTS": E.RULE_LISTS, "RULE_STAGES": E.RULE_STAGES, "DEFAULT_RULES": E.default_rules(),

② 大约第 490 行，‎⁠save_rules⁠ 里，在 ‎⁠entry={...}⁠ 最后的 ‎⁠"note": note or ""⁠ 后面加 ‎⁠, "diff": {k: [old.get(k), new[k]] for k in new if old.get(k) != new[k]}⁠，整行变成：            self._write_rules(rules=new, entry={"at": now()[:16], "by": by or "", "what": "修改判断规则：" + "；".join(what), "note": note or "", "diff": {k: [old.get(k), new[k]] for k in new if old.get(k) != new[k]}})

③ 大约第 496 行，‎⁠reset_rules⁠ 里，把这一行换成下面两行：            d = E.default_rules()

            self._write_rules(rules=d, entry={"at": now()[:16], "by": by or "", "what": "判断规则恢复默认（自定义规则保留）", "note": note or "", "diff": {k: [self.rules.get(k), d[k]] for k in d if self.rules.get(k) != d[k]}})

“最近一次修改之前”就是靠 ‎⁠diff⁠ 实现的。以前的修改记录没有 ‎⁠diff⁠，所以要等改过一次之后，这个选项才能选。

3. ‎⁠scripts/ta.py⁠：检查说明表有没有漏

大约第 201 行，‎⁠errs += ["不认识的规则项 " ...⁠ 这一行下面加两行：    errs += ["规则编号 " + k + " 在 ta_engine.RULE_TABLE 里没有说明" for k in E.RULE_NAMES if k not in {r["id"] for r in E.RULE_TABLE}]

    errs += ["清单 " + k + " 在 ta_engine.RULE_LISTS 里没有说明" for k in base if k not in {l["key"] for l in E.RULE_LISTS}]

以后谁加了新规则编号却忘了补说明，‎⁠ta.py check⁠ 会报出来。

4. ‎⁠assets/config.js⁠：换掉判断规则页

把第 20 行 ‎⁠/* ===== 判断规则 ===== */⁠ 到第 59 行（‎⁠function rulesPage⁠ 结束的 ‎⁠}⁠）整段删掉，换成下面这段。第 61 行的“自定义规则”及后面的内容都不动。原来写在页面里的 ‎⁠RULE_SECTIONS⁠ / ‎⁠RULE_ADV⁠ 也一起删了，清单名称改成从 Python 读，页面里不再有第二份。  /* ============================== 判断规则 ============================== */

  // 规则一览（内置规则 + 自定义规则）和规则清单（rules.json 的 rules）。名称、说明、条件都来自 ta_engine.py 的 RULE_TABLE / RULE_LISTS。

  // 底色：绿 = 比对照新增，红 = 比对照删除，橙 = 改过（有增有删或数值变了），黄 = 改了还没保存。

  const LEGEND = '<span class="lg"><i class="d-add"></i>新增</span><span class="lg"><i class="d-del"></i>删除</span><span class="lg"><i class="d-mod"></i>修改</span><span class="lg"><i class="d-edit"></i>未保存</span>';

  const isNum = k => typeof M.DEFAULT_RULES[k] === "number";

  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  // 对照：默认规则，或最近一次修改之前

  function baseRules(v) {

    if (v.cmp !== "last") return M.DEFAULT_RULES;

    const l = S.changelog.slice().reverse().find(x => x.diff);

    const b = Object.assign({}, S.rules);

    if (l) Object.entries(l.diff).forEach(([k, d]) => { b[k] = d[0]; });

    return b;

  }

  const curOf = (v, k) => (k in v.edit ? v.edit[k] : S.rules[k]);

  function diffKind(v, k, base) {

    const cur = curOf(v, k);

    if (k in v.edit && !same(v.edit[k], S.rules[k])) return "edit";

    if (same(cur, base[k])) return "";

    if (isNum(k)) return "mod";

    const add = cur.filter(x => !(base[k] || []).includes(x)).length, del = (base[k] || []).filter(x => !cur.includes(x)).length;

    return add && del ? "mod" : add ? "add" : "del";

  }

  const KIND_NAME = { add: "新增", del: "删除", mod: "修改", edit: "未保存" };

  function chips(v, k, base) {

    const cur = curOf(v, k), b = base[k];

    if (isNum(k)) return same(cur, b) ? '<span class="kw">' + esc(cur) + "</span>" : '<span class="kw del">' + esc(b) + '</span> → <span class="kw add">' + esc(cur) + "</span>";

    return cur.map(x => '<span class="kw' + ((b || []).includes(x) ? "" : " add") + '">' + esc(x) + "</span>").join("") +

      (b || []).filter(x => !cur.includes(x)).map(x => '<span class="kw del">' + esc(x) + "</span>").join("");

  }

  function rulesPage(root, v) {

    v.edit = v.edit || {}; v.tab = v.tab || "lists"; v.cmp = v.cmp || "default"; v.show = v.show || "all";

    if (v.focus) { v.tab = "lists"; v.open = v.focus; v.focus = null; }

    const base = baseRules(v), last = S.changelog[S.changelog.length - 1];

    const pending = Object.keys(v.edit).filter(k => !same(v.edit[k], S.rules[k]));

    const hasLast = S.changelog.some(x => x.diff);

    let html = '<div class="card"><div class="card-h"><div class="seg"><button data-rt="lists" class="' + (v.tab === "lists" ? "on" : "") + '">规则清单</button><button data-rt="table" class="' + (v.tab === "table" ? "on" : "") + '">规则一览</button></div>' +

      '<label class="fi" style="margin-left:10px"><span>对照</span><select class="sel" id="rCmp"><option value="default">默认规则</option><option value="last"' + (v.cmp === "last" ? " selected" : "") + (hasLast ? "" : " disabled") + ">最近一次修改之前</option></select></label>" + LEGEND +

      '<span class="sp"></span><span class="hint">' + (last ? "最近修改：" + esc(last.at) + " " + esc(last.by || "") : "") + '</span><button class="btn sm" id="rFile">规则文件</button><button class="btn sm" id="rImport">导入</button><a class="btn sm" href="/api/rules/file" download="rules.json">下载</a><button class="btn sm" id="rReset">恢复默认</button>' +

      '<button class="btn sm pri" id="rSave"' + (pending.length ? "" : " disabled") + ">保存 " + (pending.length ? pending.length + " 项修改" : "") + "</button></div></div>";

    html += v.tab === "table" ? ruleTable(v, base) : listTable(v, base);

    root.innerHTML = html;

    A.bindGo(root);

    $$("[data-rt]", root).forEach(b => b.onclick = () => { v.tab = b.dataset.rt; A.render(); });

    $("#rCmp").onchange = e => { v.cmp = e.target.value; A.render(); };

    $$("[data-rshow]", root).forEach(b => b.onclick = () => { v.show = b.dataset.rshow; A.render(); });

    if ($("#rQ")) $("#rQ").onchange = e => { v.q = e.target.value.trim(); A.render(); };

    $$("[data-rlist]", root).forEach(a => a.onclick = () => { v.tab = "lists"; v.open = a.dataset.rlist; v.q = ""; v.show = "all"; A.render(); });

    $$("[data-redit]", root).forEach(a => a.onclick = () => { v.open = v.open === a.dataset.redit ? null : a.dataset.redit; A.render(); });

    $$("[data-rin]", root).forEach(el => el.oninput = () => {

      const k = el.dataset.rin;

      v.edit[k] = isNum(k) ? +el.value : lines(el.value);

      const kind = diffKind(v, k, base), tr = el.closest("tr");

      tr.className = kind ? "d-" + kind : ""; $(".rk", tr).innerHTML = kind ? KIND_NAME[kind] : ""; $(".rchips", tr).innerHTML = chips(v, k, base);

      const n = Object.keys(v.edit).filter(x => !same(v.edit[x], S.rules[x])).length;

      $("#rSave").disabled = !n; $("#rSave").textContent = "保存 " + (n ? n + " 项修改" : "");

    });

    $$("[data-rundo]", root).forEach(a => a.onclick = () => { delete v.edit[a.dataset.rundo]; A.render(); });

    const open = v.open && $('[data-rin="' + v.open + '"]', root);

    if (open) { open.closest("tr").scrollIntoView({ block: "center" }); open.focus(); }

    $("#rSave").onclick = () => {

      const rules = {}; Object.keys(v.edit).forEach(k => { if (!same(v.edit[k], S.rules[k])) rules[k] = v.edit[k]; });

      whoDialog("保存判断规则（" + Object.keys(rules).length + " 项）", "", async (by, note) => { const r = await A.act("/api/rules/save", { rules, by, note }, afterMsg); if (r) { v.edit = {}; v.open = null; } return r; });

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

  // 规则清单：每行一个清单，可直接编辑

  function listTable(v, base) {

    const q = (v.q || "").toLowerCase();

    const rows = M.RULE_LISTS.filter(l => {

      const kind = diffKind(v, l.key, base);

      if (v.show === "changed" && !kind) return false;

      if (v.show === "edit" && kind !== "edit") return false;

      return !q || (l.key + " " + l.name + " " + l.note + " " + JSON.stringify(curOf(v, l.key))).toLowerCase().includes(q);

    });

    const used = k => M.RULE_TABLE.filter(r => r.uses.includes(k)).map(r => r.id);

    const nChanged = M.RULE_LISTS.filter(l => diffKind(v, l.key, base)).length;

    let html = '<div class="card"><div class="bar"><div class="chips">' + [["all", "全部 " + M.RULE_LISTS.length], ["changed", "有差异 " + nChanged], ["edit", "未保存"]].map(([k, n]) => '<button data-rshow="' + k + '" class="' + (v.show === k ? "on" : "") + '">' + n + "</button>").join("") +

      '</div><input class="inp" id="rQ" placeholder="搜索清单名称或内容" value="' + esc(v.q || "") + '"><span class="sp"></span><span class="hint">每行一项，不区分大小写；<code>re:</code> 开头是模糊匹配</span></div>' +

      '<div class="tbl-wrap"><table class="tbl rlist"><thead><tr><th>分组</th><th>清单</th><th>用于规则</th><th style="width:48%">内容</th><th>差异</th><th></th></tr></thead><tbody>';

    let g = "";

    rows.forEach(l => {

      const k = l.key, kind = diffKind(v, k, base), cur = curOf(v, k);

      html += '<tr class="' + (kind ? "d-" + kind : "") + '"><td class="nw hint">' + (l.group !== g ? esc(l.group) : "") + '</td><td class="nw"><b>' + esc(l.name) + '</b><div class="hint mono">' + esc(k) + "</div>" + (l.note ? '<div class="hint">' + esc(l.note) + "</div>" : "") + "</td>" +

        '<td class="hint">' + used(k).map(esc).join(" ") + "</td><td>" + (v.open === k

          ? (isNum(k) ? '<input class="inp" type="number" min="0" data-rin="' + k + '" value="' + esc(cur) + '">' : '<textarea class="ta" rows="' + Math.min(14, Math.max(4, cur.length + 1)) + '" data-rin="' + k + '">' + esc(cur.join("\n")) + "</textarea>") + '<div class="rchips" style="margin-top:4px">' + chips(v, k, base) + "</div>"

          : '<div class="rchips">' + chips(v, k, base) + "</div>") +

        '</td><td class="nw rk">' + (kind ? KIND_NAME[kind] : "") + '</td><td class="ops nw"><a data-redit="' + k + '">' + (v.open === k ? "收起" : "编辑") + "</a>" + (k in v.edit ? '<a data-rundo="' + k + '">撤销</a>' : "") + "</td></tr>";

      g = l.group;

    });

    return html + "</tbody></table></div>" + (rows.length ? "" : A.emptyBlock("没有符合条件的清单")) + "</div>";

  }

  // 规则一览：判断顺序，先自定义规则，再内置规则；用到的清单有差异时整行标色

  function ruleTable(v, base) {

    const name = k => (M.RULE_LISTS.find(l => l.key === k) || { name: k }).name;

    const cat = k => k === "CHECK" ? '<span class="tag gray">按核查结果</span>' : A.catTag(k);

    const st = s => s === "confirmed" ? '<span class="dot" style="--c:#67c23a">规则确认</span>' : '<span class="dot" style="--c:#e6a23c">待复核</span>';

    const rank = { edit: 4, mod: 3, add: 2, del: 1, "": 0 };

    let html = '<div class="card"><div class="tbl-wrap"><table class="tbl rlist"><thead><tr><th>顺序</th><th>编号</th><th>名称</th><th style="width:34%">什么情况下命中</th><th>用到的清单</th><th>分类</th><th>判定</th><th>重跑</th></tr></thead><tbody>';

    html += S.custom.map(u => {

      const w = u.when || {}, t = u.then || {};

      return '<tr class="' + (u.enabled === false ? "off" : "") + '"><td class="hint nw">0 自定义</td><td class="mono">' + esc(u.id) + "</td><td>" + esc(u.name || "") + (u.enabled === false ? ' <span class="tag gray xs">停用</span>' : "") + "</td>" +

        '<td class="basis">' + esc([w.any && w.any.length ? "出现任一：" + w.any.join("、") : "", w.all && w.all.length ? "全部出现：" + w.all.join("、") : "", w.none && w.none.length ? "不能出现：" + w.none.join("、") : "", w.exceptions && w.exceptions.length ? "异常：" + w.exceptions.join("、") : ""].filter(Boolean).join("；")) +

        '</td><td><a data-go="custom">自定义规则</a></td><td>' + cat(t.category) + "</td><td>" + st(t.status) + "</td><td>" + (t.rerun ? M.PLAN[t.rerun] : "按分类") + "</td></tr>";

    }).join("");

    let stg = "";

    M.RULE_TABLE.forEach(r => {

      const kinds = r.uses.map(k => diffKind(v, k, base)), kind = kinds.reduce((a, b) => rank[b] > rank[a] ? b : a, "");

      html += '<tr class="' + (kind ? "d-" + kind : "") + '"><td class="hint nw">' + (r.stage !== stg ? r.stage + " " + esc(M.RULE_STAGES[r.stage]) : "") + '</td><td class="mono nw">' + esc(r.id) + '</td><td class="nw">' + esc(M.RULE_NAMES[r.id] || r.id) + '</td><td class="basis">' + esc(r.when) + "</td>" +

        "<td>" + r.uses.map((k, i) => '<a data-rlist="' + k + '" class="kw' + (kinds[i] ? " k-" + kinds[i] : "") + '" title="' + esc(k) + '">' + esc(name(k)) + "</a>").join("") + "</td><td>" + cat(r.cat) + "</td><td>" + st(r.status) + '</td><td class="nw">' + M.PLAN[r.rerun] + "</td></tr>";

      stg = r.stage;

    });

    return html + '</tbody></table></div><p class="hint" style="margin:6px 0 0">按顺序判断，第一条命中的生效。需要人工核查的规则，核查前一律“处理后再重跑”。条件和顺序写在 scripts/ta_engine.py，改它们见 references/maintenance.md。</p></div>';

  }

5. ‎⁠assets/app.css⁠：加底色样式

在文件最后追加：/* 判断规则：规则清单 / 规则一览 的差异底色 */

.lg { display: inline-flex; align-items: center; gap: 3px; margin-left: 10px; font-size: 12px; color: var(--muted); }

.lg i { display: inline-block; width: 14px; height: 10px; border: 1px solid #ddd; border-radius: 2px; }

.d-add, tr.d-add td { background: #f0f9eb; }

.d-del, tr.d-del td { background: #fef0f0; }

.d-mod, tr.d-mod td { background: #fdf6ec; }

.d-edit, tr.d-edit td { background: #fffbe0; }

tr.off td { opacity: .5; }

.rlist td { vertical-align: top; }

.kw { display: inline-block; margin: 1px 4px 1px 0; padding: 0 6px; line-height: 20px; border-radius: 3px; background: #f2f4f7; font-size: 12px; color: #333; word-break: break-all; }

.kw.add, .kw.k-add { background: #d9f2c9; color: #23651a; }

.kw.del, .kw.k-del { background: #fbd5d5; color: #a8262b; text-decoration: line-through; }

.kw.k-mod { background: #fae1bd; color: #8a4b00; }

.kw.k-edit { background: #fff1a8; color: #6b5800; }

a.kw { cursor: pointer; }

改完运行 ‎⁠python scripts\ta.py check⁠ 和 ‎⁠python evals\selftest.py⁠，然后重新打开助手看一下。这几处 Python 改动没在 Windows 上跑过；页面部分在我这边用模拟数据测过。


关于页面是怎么分类的
分类不靠模型，也不读 references，是 ‎⁠scripts/ta_engine.py⁠ 里固定的规则在判断。

- 怎么判断： 打开页面或导入报告时，页面向本机服务要数据（‎⁠/api/state⁠）。服务用当前的 ‎⁠config/rules.json⁠ 调用 ‎⁠ta_engine.classify_all()⁠，把每个失败用例按上面“规则一览”的顺序逐条比对，第一条命中的就是结论：

 - 比如报错里出现 ‎⁠There is no active desktop⁠，它在 ‎⁠env_patterns⁠ 清单里，就判为环境问题（ENV-DESK）；

 - 比如弹窗文字含 ‎⁠currently used by other user⁠，它在 ‎⁠lock_messages⁠ 清单里，就判为测试数据问题（DATA-LOCK）。

- 页面只负责显示： 把 Python 算好的分类、依据和证据显示出来。你在页面上记录截图观察、核查结果或改分类，页面把记录发回 Python，Python 再重新判一遍。

- ‎⁠references/taxonomy.md⁠ 的作用： 是写给人和 AI 看的分类标准，和代码一一对应。程序不读它，所以改代码时要同时改它。

模型只在一种情况下用到： 你在 AI 工具里调用这个 skill，比如“分析这份报告”。这时 AI 也是先运行 ‎⁠ta.py analyze⁠，拿到的是同一套规则的结果。规则判为“确认”的，AI 不改；它只对“待复核”和“需人工判断”的用例，按 references 里的方法看证据，告诉你可能的原因和还缺什么，最终的改判还是你在页面上做。

这样设计是为了同一份报告无论谁、什么时候分析，结果都一样，也能用纠错样本和基准样本检查规则有没有被改坏。如果让模型来分类，每次结果可能不同，也没法做这种检查。