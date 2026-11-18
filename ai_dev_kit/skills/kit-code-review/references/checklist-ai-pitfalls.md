# 清单：AI 常见错误（来自本项目真实事故）

每一条都在实际执行中出现过。评审时逐条确认没有再犯。对应的自动检查写在括号里。

| # | 错误 | 怎么发现 | 自动检查 |
|---|------|----------|----------|
| 1 | ORM 模型类嵌套在另一个类里，表没有注册 | view 模型文件，看缩进 | checks: nested_orm_class |
| 2 | 改了类名/函数名，别处的导入没改 | grep 旧名字 | checks: removed_names |
| 3 | 用 PowerShell `>` 写文件，产生 UTF-16，Python 读不了 | 编码检查 | checks: chars；守卫拦截 |
| 4 | 新增导入形成循环导入，测试收集阶段就报错 | 看 “ERROR collecting” | checks: test_collection |
| 5 | 测试读取真实 .env / 真实服务 | grep `.env`、`load_dotenv` | checks: env_in_tests |
| 6 | 测试依赖当前环境没有的数据库驱动 | 收集阶段 ImportError | checks: test_collection |
| 7 | 测试放错目录或命名不对，0 条测试被“通过” | 看 collected 数量 | run_checks 识别 0 条 |
| 8 | grep 写错（大小写、路径、正则），得出“没有引用”的错误结论 | 换一种写法再确认 | 人工 |
| 9 | 永远成立的断言（`assert x == x`） | 读测试 | checks: tautological_asserts |
| 10 | 用 `in` 代替 `==`，断言太宽 | 读测试 | 人工 |
| 11 | 改到了范围外的文件（例如同事的问答插件） | diff 文件清单对照 scope | checks: scope_diff；守卫拦截 |
| 12 | 声称“全部完成”，实际只做了一部分 | 逐条对照需求找改动 | 人工 |
| 13 | 缺依赖时自作主张改 pyproject / 装包 | diff 里出现锁定文件 | 守卫拦截 |
| 14 | 新功能默认开启，缺配置时启动就报错 | 看默认值和缺配置路径 | 人工 |
| 15 | 用线程 + join(timeout) 做超时，超时后线程继续写数据 | 读超时实现 | 人工 |

## 另外三条通用的
- 用 `getattr(settings, "x", 默认值)` 掩盖配置拼写错误（checks: getattr_settings）。
- 用 `# type: ignore`、`# noqa`、`skip` 让检查“通过”（checks: forbidden_markers；守卫拦截）。
- 根因分析停在表面（“缺少某个包”），没有追到真正原因（例如其实是循环导入）。结论前问一句：“如果这个原因是对的，还有什么现象应该同时出现？”去验证它。
