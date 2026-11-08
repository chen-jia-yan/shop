# runtime.py 里新增（RagEvalSkillRuntime 内）
def rag_eval_analyze(self, inp):   # inp: RagEvalAnalyzeInput(results_path, write_path=None)
    import json
    from pathlib import Path
    from .analyzer import analyze_results

    # ⚠️对齐点B：确认评估结果文件路径与 JSON 结构（results 列表在顶层还是 j["results"]）
    raw = json.loads(Path(inp.results_path).read_text("utf-8"))
    results = raw if isinstance(raw, list) else raw.get("results", [])
    report = analyze_results(results)

    out_path = inp.write_path or str(Path(inp.results_path).with_name("eval_analysis.json"))
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    return RagEvalAnalyzeOutput(analysis_path=out_path, **{k: report[k] for k in
        ("pass_rate","bad_count","weakest_dim","retrieval_not_generation","category_counts")})
