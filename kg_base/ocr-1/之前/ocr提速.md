# 任务:统一 OCR 引擎 + 每进程复用(提速关键)+ 清理无效配置

## 背景与目标
项目里 OCR 目前有三个问题,既慢又乱:
1. worker 每处理一个文件都新建一次 OCR 引擎(build_ppt_ocr),不复用 → 每文件重装模型,极慢。
2. 存在两套 OCR:真正解析用的 ppt_ocr.py 里的 PaddleOCRLocal;以及 worker 预热用的 ocr_provider.py 里的 LocalPaddleProvider(并未真正用于解析)。
3. 一批配置无效:enable_mkldnn 从未传给 PaddleOCR;language 被写死为 japan;cpu_threads 只在未使用的 provider 里生效;两套参数不一致(use_angle_cls 一处 True 一处 False)。

目标:统一成一套 OCR 创建路径 + 每个进程只创建一次并复用 + 让配置真正生效,从而显著提速、也更清晰。

## 先做(务必)
先不要改代码。先告诉我:计划改哪些文件、每处怎么改、为什么、有什么风险,以及会不会影响 Windows 多进程、重文件隔离、解析正确性。等我确认后再动手,小步进行。

## 要实现的改造

### 1. 唯一的 OCR 创建入口
- 只保留一个创建 OCR 的函数(以真正用于解析的 ppt_ocr.py / PaddleOCRLocal 为准),让 ingest、worker、重文件子进程都用它。
- 移除或改造 ocr_provider.py 里那个"预热但没被解析真正使用"的 LocalPaddleProvider:要么删掉,要么让"预热"就是创建那个将被复用的唯一实例(见第 2 点)。

### 2. 每个进程只创建一次 OCR 并复用(提速核心)
- 多进程 worker:在进程池的 initializer 里创建一个 OCR 实例,存为该子进程内的模块级全局;process_one / 解析(build_chunks / ppt_ocr)复用这个全局实例,严禁每个文件调用 build_ppt_ocr() 新建。
- 注意 Windows spawn:OCR 实例不能在父进程创建后传给子进程(不可 pickle),必须在每个子进程内创建一次(通过 initializer,或首次使用时懒加载 + 全局缓存)。
- 重文件隔离子进程(process_one_file.py):每个子进程处理一个文件,创建一次 OCR 即可,确认内部不会重复创建。
- ingest(单进程):已是复用一个实例,保持不变。

### 3. 让配置真正生效
- 把 enable_mkldnn、cpu_threads、use_angle_cls、language 等从单一配置源读出,真正传给唯一的 OCR 创建函数。
- 当前 PaddleOCR 版本不接受的参数(如已删的 show_log)不要传。
- 任何无法真正生效的配置项,从 config 里删掉,避免"以为在调、其实没用"。

### 4. 参数统一
- 所有地方用同一套 OCR 参数(方向识别、线程、mkldnn、语言等一致),不再一处 True 一处 False。

## 必须保持不变
- 解析结果正确(OCR 仍能正常识别日文)。
- 重文件独立子进程隔离;子进程解释器用 sys.executable(.venv312)。
- 失败重试、崩溃计数、续跑、幂等、embedding 限速与批量。
- 只用标准库 + 已安装包;不删除 PaddleOCR 模型缓存;Windows spawn,入口在 if __name__=="__main__" 下。

## 加诊断日志(用于验证复用)
- 每次真正创建 OCR 实例时打印:`OCR engine created pid=... count=N`(N 为该进程累计创建次数,正常应为 1)。
- 每个文件处理打印一次耗时,便于对比提速前后。

## 验收标准
- 跑一批文件:`OCR engine created` 出现次数 ≈ worker 进程数(+ 每个重文件子进程一次),不随文件数增长(不是每文件一次)。
- 单个文件处理明显变快,接近 ingest 单进程的速度。
- 代码里只有一条 OCR 创建路径;config 里的开关(mkldnn/线程/语言等)改动能真实影响 OCR 行为。
- 重文件、重试、续跑、解析正确性全部照常。
- 改完给我改动清单:动了哪些文件、每处解决什么、怎么验证。