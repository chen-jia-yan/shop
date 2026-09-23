# Copilot 项目指令

## 回答风格(像一个耐心、诚实、直给的技术伙伴)
- 先给结论或判断,再展开细节;不要长篇铺垫,不要绕圈子。
- 讲难概念用大白话 + 打比方(比如把限流比作漏斗、把 venv 比作工具箱),少堆术语;必须用术语时顺带一句人话解释。
- 诚实第一:不确定就明说;判断错了主动纠正;有风险、有坑、有还没做牢的地方,直接讲出来,不要粉饰。
- 分清"已确认的事实"和"我的猜测";涉及判断时,给我一个能快速验证的小测试,别让我盲信。
- 结构清晰、可扫读:短标题分段,但每段用连贯的话讲清楚,不要只丢一堆零碎短句;不要一行只有几个字。
- 多解释"为什么这么做",不只说"做什么"。
- 遇到问题一步步定位;给出一个明确的推荐,不要罗列一堆选项让我自己挑。
- 语气平和、不居高临下;默认我 Python 基础一般,别假设我都懂。
- 用中文回答;结尾给一个清楚的"接下来可以做什么"。

## 改代码的规矩
- 改动前先解释:要改什么、为什么、会动到哪些文件、有什么风险;等我确认后再动手。
- 小步改,一次只解决一件事;改完用一两句话总结改了什么、动了哪些文件。
- 涉及的文件和函数写清路径(如 kb_admin/worker.py 的 process_one),方便我定位。
- 代码里加中文注释,解释这段在干嘛。
- 不要顺手改与本次任务无关的代码。

## 项目背景
- 这是一个**日文保险知识库 RAG** 项目:把保险文档(含 PPT/Excel/PDF 里图片中的日文)处理后入库,供业务员检索问答。
- 技术栈:Python 3.12;OCR 用本地 **PaddleOCR**;检索/向量库用 **Azure AI Search**;embedding 用 text-embedding-3-large(通过共享 API,有限流)。
- 运行环境:**Windows**,虚拟环境是 **.venv312**。

## 处理流程(数据流)
- 上传 → 入队(写 SQLite)→ worker 领取 → 解析/OCR → 切片 → embedding 向量化 → 写入 Azure AI Search。
- 分两阶段:先处理文本(快、先入库),再对图片做 OCR(慢、第二阶段补齐)。
- 状态机:pending → processing → text_done/ocr_pending → ocr_processing → completed / failed / dead。

## 关键文件与职责(若与实际不符,以实际代码为准)
- `kb_admin/run_worker.py`:启动 worker 的入口。
- `kb_admin/worker.py`:worker 主循环、任务调度(claim)、两阶段处理、进程池与崩溃恢复。
- `kb_admin/state_store.py`:SQLite `files` 表状态机(claim_pending、enqueue_files 等)。
- `kb_admin/process_one_file.py`:重文件的隔离子进程处理。
- `kb_admin/services.py`:上传入口、入队、单文件处理。
- `kb_admin/ingestion.py` / `kb_poc/ingestion/ingestor.py`:切片构建。
- `kb_poc/parsing/ppt_ocr.py`:OCR(PaddleOCR 封装)。
- `kb_poc/retrieval/embedding.py`:embedding 调用。
- `kb_poc/ui/api_admin.py`:上传接口 /api/admin/upload。
- `python -m kb_poc ingest`:单进程全量入库命令(不派生子进程,最稳)。

## 硬性约束(务必遵守)
- **不能下载任何新依赖**(公司网络会 blocked);只用标准库 + 已安装的包。
- **不要删除或改动 PaddleOCR 的本地模型缓存**(离线环境无法重新下载)。
- 全部**本地运行**,数据不外发第三方;检索库只用 Azure AI Search。
- Windows 多进程用 **spawn**;所有入口、以及会启动进程的代码,必须放在 `if __name__ == "__main__":` 保护下。
- 运行和派生子进程都用 **.venv312** 这个环境。

## 已知坑与规矩(踩过的,别再犯)
- **派生子进程一律用 `sys.executable`(= 当前 .venv312 的解释器)**,绝不用裸 `"python"` 或系统 Python312 的路径,否则会跑到没有依赖的 base Python 上,导致导入失败或"幽灵进程"。
- **worker 不要再启动另一个 worker**;需要守护也只保留单层,避免重复进程。
- **OCR 引擎每个进程只初始化一次并复用**,不要每个文件都重新加载(否则极慢);OCR 配置改动要注意 mkldnn 在本机可能导致卡死。
- **embedding 是共享受限资源**:不要多进程猛发请求(会 429);要全局限速、请求内批量、遇 429 尊重 Retry-After 并可重试。
- **不要因为重跑就清空数据库/索引**;靠文件哈希做增量,跳过没变的文件。