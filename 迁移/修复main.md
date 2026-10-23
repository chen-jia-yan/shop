方案调整：中断恢复不再放到 main.py，改成"第一次调用评估接口时执行"。main.py 一行都不改。

一、main.py
- 不修改 main.py。我已经把它恢复成原样，完成后 git diff src/tap_ai/main.py 必须没有任何输出
- 删除 P3 提示词里"服务启动时调用一次 recover_stale_runs()"的要求，以及对应的测试

二、application/library_eval.py 的 EvalService 中新增
1. 两个实例属性：
   - self._recovery_done: bool = False
   - self._recovery_lock = asyncio.Lock()
2. 方法 async def _ensure_recovered(self) -> None：
   - self._recovery_done 为 True 时直接返回
   - async with self._recovery_lock: 进入后再检查一次 self._recovery_done，为 True 就返回
   - 调用 await self.recover_stale_runs()
     · 成功：self._recovery_done = True
     · 抛出 Exception：用日志记录一条 warning（内容包含"Library 评估中断恢复失败"和异常信息），不抛出异常，self._recovery_done 保持 False（下次调用时再试）
   - 日志写法照抄 application 目录下其他服务的现有写法
3. 在下面这些公开方法的第一行调用 await self._ensure_recovered()：
   start_run、list_runs、get_run、cancel_run、list_items、get_item、get_analysis
   （评估集相关的方法不需要调用）

三、修改已有文件时的要求（本次和以后都适用）
- 只允许改 application/library_eval.py 和测试文件。bootstrap.py 按上一条消息的要求处理，不涉及 main.py
- 用查找替换插入代码时：定位用的原文必须是完整的行，并且在文件里只出现一次；不要把不需要修改的原有行写进替换内容里重新输入
- 每修改一次已有文件，立即运行 git diff <该文件>：
  · 出现了不应该删除或修改的原有行（前面是 - 的行），就停下来告诉我，不要自己恢复，也不要反复重试
- 不要运行 git restore、git checkout 等会丢弃修改的命令，需要恢复时告诉我，由我来执行

四、测试（补充到 tests/unit/test_library_eval_service.py）
1. 第一次调用 list_runs 时，recover_stale_runs 被调用 1 次；第二次调用 list_runs 时，不会再调用
2. 同时并发调用 3 次 get_run（用 asyncio.gather），recover_stale_runs 只被调用 1 次
3. recover_stale_runs 抛出异常时：list_runs 仍然正常返回，不报错；下一次调用时会再执行一次恢复
4. 心跳超时的 running 任务，在第一次调用 get_run 之后，状态变成 interrupted

五、报告里贴出原始输出
1. git diff src/tap_ai/main.py（应为空）
2. git diff src/tap_ai/bootstrap.py
3. git diff src/tap_ai/application/library_eval.py
4. 四道关最后 30 行的原始输出，并与基线对比
然后继续完成 P3 剩下的部分，按通用规则交《完成报告》



- 修改已有文件时，定位用的原文必须是完整的行，并且在文件中只出现一次；不要把不需要修改的原有行写进替换内容里重新输入
- 每修改一次已有文件，立即运行 git diff <该文件>。出现不应该删除或修改的原有行（- 开头）时，停下来告诉我，不要自己恢复、不要反复重试
- 不要运行 git restore、git checkout、git clean 等会丢弃修改的命令。需要恢复时告诉我，由我来执行
- 能新建文件解决的，就不要往已有文件里插代码；必须插入时，优先追加在文件末尾或类的末尾
