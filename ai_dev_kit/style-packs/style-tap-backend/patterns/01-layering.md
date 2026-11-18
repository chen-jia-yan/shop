# 分层与文件放置

核对日期：2026-11-18
核对状态：待核对（依据迁移过程中确认的目录结构整理；首次使用前请对照来源文件核对）

## 何时使用
- 新增一个功能模块（例如知识库管理、图谱浏览、评估），决定每段代码放哪个文件。
- 从老项目（POC）迁移代码时，把“一个大文件”拆进后端的分层。

## 必须
1. 按层放置：
   - `api/`：路由函数和请求/响应模型（DTO），只做参数解析、调用服务、转换响应；
   - `application/`：业务服务（一个功能一个文件，如 `library_kb.py`），后台工作循环也在这里（如 `library_kb_worker.py`）；
   - `core/`：与框架无关的纯逻辑（算法、打分、汇总，例如 `core/library_eval/`）；
   - `persistence/`：ORM 模型（`models.py`）和仓储（`*_repo.py`）；
   - `contracts/`：跨层/跨插件的接口定义（端口）和共享数据结构；
   - `plugins/`：外部系统的适配器（SDK、搜索、图数据库），实现 contracts 里的端口；
   - `config/settings.py`：所有配置项；`bootstrap.py`：装配（创建服务、挂到 app.state、注册路由）。
2. 依赖方向只能向内：api → application → contracts / core / persistence；plugins 实现 contracts。
3. 新文件命名和同层已有文件一致（`library_xxx.py`、`library_xxx_repo.py`）。

## 禁止
1. 在 api 层写 SQL、调用外部 SDK、写业务判断。
2. 在 application 层导入 FastAPI 的 Request/Response。
3. application 直接导入某个 plugin 的内部模块（应依赖 contracts 里的端口）。
4. 为了“以后可能用到”新建抽象层或通用框架。

## 精简样例
```text
src/tap_ai/
  api/library_kb.py            # 路由：参数 → service → DTO
  api/dto.py                   # 请求/响应模型（或按模块放）
  application/library_kb.py    # 业务服务：编排仓储与端口
  application/library_kb_worker.py  # 后台处理循环
  contracts/library_kb.py      # 端口：IndexWriter、DocumentParser 等协议
  persistence/models.py        # ORM 模型（顶层类）
  persistence/library_kb_repo.py    # 仓储：增删改查、条件更新
  plugins/ingest/sdk_ingest.py # 适配器：实现 contracts 的端口
  config/settings.py           # 配置项（默认关闭的功能开关）
  bootstrap.py                 # 装配：创建服务 → app.state → 挂路由
```

## 反例
```python
# api/library_kb.py —— 错：路由里直接查库、调 SDK
@router.post("/upload")
async def upload(file: UploadFile):
    rows = session.execute(text(f"SELECT * FROM doc WHERE name='{file.filename}'"))  # SQL 拼接
    sdk.ingest(file.file)                                                         # 直接调外部 SDK
```
错在：分层被打穿、SQL 注入风险、无法用 fake 测试。

## 检查项
- [ ] 每个新文件都在正确的层
- [ ] api 层没有 SQL / SDK 调用
- [ ] application 没有导入 plugin 内部模块
- [ ] 文件命名与同层已有文件一致

## 来源
- src/tap_ai/api/library_kb.py — 接口层
- src/tap_ai/application/library_kb.py — 服务层
- src/tap_ai/application/library_kb_worker.py — 后台处理
- src/tap_ai/persistence/library_kb_repo.py — 仓储
- src/tap_ai/contracts/library_kb.py — 端口
- src/tap_ai/bootstrap.py — 装配
