目标：重写 rag_eval 的判官 prompt，让四个维度各管一件事、每个维度都有写死的 1~5 分标准、每维输出理由。
约束：不碰 Azure 索引；temperature 保持 0.0；新逻辑用开关 KB_EVAL_JUDGE_V2（默认开，可一键回到旧判官）；每条结果写入 judge_version="v2"；改动走 plan mode 给 diff。

B1. 判官 prompt 替换为以下内容（中文，变量用 {}）：

---
你是保险业务知识库问答的严格评审员。请只根据下面提供的材料打分，不要使用你自己的知识。

【问题】{question}
【标准答案】{expected_answer}
【必答要点】（逐条编号）
{key_points}
【原始证据】（来自知识库原文，每段带 chunk_id）
{original_evidence}
【推断证据】（来自知识图谱/空间复原/流程图重建等推断，非原文；纯检索链路此项为空）
{derived_evidence}
【待评答案】{actual_output}

请按以下四个维度分别打 1~5 分。每个维度只评自己负责的那一件事，不要用其它维度的问题扣分。

1. 忠实度 faithfulness —— 只管「答案里的每句话能否在【原始证据】或【推断证据】中找到支撑，有没有凭空编造」。不管答得对不对、全不全。
   5=每句都有支撑；4=只有措辞层面的轻微引申；3=有1处无支撑的具体说法；2=有多处无支撑的说法；1=主要内容无支撑或编造。

2. 答案相关性 answer_relevance —— 只管「是否在回答这个问题本身」。不管事实对错、要点全不全。
   5=直接、聚焦地回答问题；4=回答了但夹带少量无关内容；3=部分在答、部分跑题；2=大部分没在答这个问题；1=答非所问，或只说"无法确认"而未作任何回应。

3. 完整性 completeness —— 只管「【必答要点】覆盖了多少」。不管答案读起来丰不丰满，也不管多说了什么。
   逐条判定每个要点：hit（明确说到且意思一致）/ partial（说到一部分或表达含糊）/ miss（没说到）/ wrong（说到了但说错）。
   覆盖率 = (hit数 + 0.5×partial数) ÷ 要点总数。
   映射：≥0.9→5；≥0.7→4；≥0.5→3；≥0.25→2；<0.25→1。

4. 正确性 correctness —— 只管「答案里已经说出的内容，与【标准答案】是否一致」。不管说没说全。
   5=说出的内容全部与标准答案一致；4=主干正确，有次要细节出入；3=主干正确但有1处明确错误；2=有关键事实错误；1=主要结论错误。
   硬性规则：只要日期、画面ID、金额、系统名、条款名这类关键事实有任何一处错误，正确性最高只能给2分。

只输出以下 JSON，不要输出任何其它文字：
{
  "faithfulness": {"score": 1-5, "reason": "一句话说明依据"},
  "answer_relevance": {"score": 1-5, "reason": "..."},
  "completeness": {
    "score": 1-5,
    "coverage": 0.0-1.0,
    "key_points": [{"id": 1, "status": "hit|partial|miss|wrong", "evidence": "答案中对应的原话，没有则留空"}],
    "reason": "..."
  },
  "correctness": {"score": 1-5, "critical_error": true/false, "reason": "..."},
  "summary": "一句话总评：问题主要出在检索、内容缺失还是生成"
}
---

B2. 解析与落盘：
- 把各维 score 写回原来的 scores{dim:int}，旧的统计和报告逻辑保持不变。
- 新增写入：result["rationales"]={dim: reason}、result["judge_summary"]、result["completeness_detail"]={coverage, key_points}、result["correctness_critical_error"]、result["judge_version"]="v2"。
- 解析失败时，用正则兜底只取分数，理由留空，并在 result["judge_parse_error"] 里记录原始输出。不得让整轮评估中断。
- 校验 completeness.score 是否和 coverage 按映射规则一致；不一致时以 coverage 算出的分为准，并记 warning。

B3. 纯检索链路（LLM-RAG 评估）的 {derived_evidence} 传空字符串；{original_evidence} 传实际喂给生成模型的 chunk（含表格重组后的内容），每段前面标上 [chunk_id]。

此阶段先不要跑完整评估，等阶段 C 的必答要点准备好。停。