目标：给 gold 集每道题生成「必答要点 key_points」，由我人工审核后固定下来，供判官的完整性逐点核对使用。
约束：原 gold 文件不覆盖，产出写到新文件；不碰 Azure。

C1. 写脚本 scripts/build_key_points.py：
- 读取 gold 集，对每题用模型从 expected_answer 里拆出必答要点。拆分规则写进 prompt：
  · 每个要点是一个可以独立核对的事实（一个系统名、一个画面ID+名称、一个日期、一个目的、一个步骤）；
  · 不要拆出标准答案里没有的东西；
  · 列举类答案（如"受影响系统有A、B、C"）每一项单独成一个要点；
  · 每题一般 1~6 个要点。
- 输出到 evals/rag_gold_set.keypoints.draft.jsonl，每行在原记录上增加 "key_points": ["要点1", "要点2", ...]。
- temperature=0.0。

C2. 同时输出一份人工审核表 evals/key_points_review.md：每题列出 问题 / 标准答案 / 拆出的要点，方便我逐条看、改、删。

C3. 我审完后会把确认版保存为 evals/rag_gold_set.keypoints.jsonl。评估加载 gold 集时：优先读这个确认版；某题没有 key_points 时，退回为"把整条标准答案当作 1 个要点"，并在结果里记 warning。

只跑 C1、C2，产出文件给我审，停。