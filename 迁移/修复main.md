核实结果收到。我已经执行 git restore 把 src/tap_ai/main.py 恢复成了修改前的原样。请按下面的要求继续修改。

一、bootstrap.py
1. 提示词库：直接使用 build_app 中已有的 default_prompt_library（与第 151/215/222 行的用法一致），不要新建，也不要调用 PromptLibraryProvider 的任何方法
2. EvalService 的构造、挂到 app.state.library_eval_service、在 lifecycle 中登记 shutdown，全部移到 build_app 中：
   - 放在其他服务构造完成之后
   - 外面套 if settings.library_enabled:
   - container、session_factory、lifecycle 使用 build_app 里已有的变量
   - qa_port 注入 None；不加入 _REACT_REQUIRED
3. _mount_routers 中 library 的部分只保留"挂载两个路由"，删掉其中所有构造对象、访问 container 的代码
4. 修改后 git diff src/tap_ai/bootstrap.py 中，P3 之前就已存在的代码不能出现删除或修改（不能有属于原有代码的 - 行）

二、main.py（只允许追加，原有的每一行都不能改动，包括缩进）
1. 在 _lifespan 函数中，找到原有的 try:（它的下一行是 yield）。在这个 try: 的正上方插入下面这段，缩进与 try: 完全相同：

    library_eval_service = getattr(app.state, "library_eval_service", None)
    if library_eval_service is not None:
        try:
            await library_eval_service.recover_stale_runs()
        except Exception:
            <用 main.py 中现有的日志对象记录一条 warning，内容包含"Library 评估中断恢复失败"和异常信息>

   说明：
   - 上面示例中的缩进只是示意，实际缩进必须与原有的 try: 对齐
   - 只判断 app.state 上有没有 library_eval_service，不要为此新增 import settings（开关关闭时这个服务根本不会被创建）
   - main.py 里如果没有现成的日志对象，停下来告诉我，不要自己新增 import
2. 插入后执行 git diff src/tap_ai/main.py：输出里只能有 + 开头的新增行，不能有任何 - 开头的行。做不到就停下来告诉我

三、测试（补充到 tests/unit/test_library_eval_service.py）
1. library_enabled=True 时构造应用，app.state.library_eval_service 存在，并且是 EvalService 的实例
2. library_enabled=False 时构造应用，app.state 上没有 library_eval_service
3. 中断恢复抛异常时，应用仍能正常启动：用假的服务让 recover_stale_runs 抛出异常，启动应用（例如用 TestClient 的 with 语句触发 lifespan），确认不报错、能正常请求一个现有接口

四、报告里必须贴出原始输出（不要只写总结）
1. git diff src/tap_ai/main.py 的完整原始输出
2. git diff src/tap_ai/bootstrap.py 的完整原始输出
3. 四道关最后 30 行的原始输出，并与基线对比
4. 然后继续完成 P3 剩下的部分，最后按通用规则交《完成报告》
