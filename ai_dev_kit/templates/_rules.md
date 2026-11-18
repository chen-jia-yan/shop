【通用规则】（固定开头：每次都放在最前面、内容不变，方便模型服务端命中前缀缓存）
1. 只做下面编号列出的事；做不到或信息不够时停下来说明，不要猜，不要顺手改别的。
2. 绝对禁止：读取 .env 等可能含密钥的文件；安装或卸载依赖；git 写操作（add / commit / push / pull / merge / rebase / reset / checkout / restore / stash / clean）；用 > 或 Out-File / Set-Content 写文件；对已有文件运行 ruff format；新增 # type: ignore、# noqa、skip、xfail、cast(Any, ...)。
3. 标识符只用 ASCII；文件用 UTF-8 无 BOM；不重命名已有的类、函数、字段（需要改名先问）。
4. 证据优先：凡是说“已完成”“已通过”，都要附原始输出或 文件:行号。“0 个测试运行”“收集阶段中断”都算失败。
5. 结尾必须有核对表：每个编号一行，状态只能是 完成 / 未找到 / 未做 / 已停下。
