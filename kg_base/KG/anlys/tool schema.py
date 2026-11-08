class RagEvalAnalyzeInput(BaseModel):
    results_path: str                       # 评估结果 JSON 路径
    write_path: str | None = None           # 分析结果写到哪，默认同目录 eval_analysis.json

class RagEvalAnalyzeOutput(BaseModel):
    analysis_path: str
    pass_rate: float
    bad_count: int
    weakest_dim: str | None
    retrieval_not_generation: int
    category_counts: dict[str, int]
