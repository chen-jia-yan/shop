from kb_poc.tool_schemas import (
    KGSyncStatusInput, KGSyncStatusOutput,
    KGSyncPlanInput, KGSyncPlanOutput,
    KGSyncApplyInput, KGSyncApplyOutput,
    KGSyncRollbackInput, KGSyncRollbackOutput,
)

# ... 在已有 registry 字典里追加：
"kg_sync_status": ToolSpec(name="kg_sync_status", description="查看知识图谱当前状态（版本/节点数/健康度）",
                           input_model=KGSyncStatusInput, output_model=KGSyncStatusOutput, skill="kg_sync"),
"kg_sync_plan":   ToolSpec(name="kg_sync_plan", description="预演文档 add/update/delete 对图谱的变更（不写盘）",
                           input_model=KGSyncPlanInput, output_model=KGSyncPlanOutput, skill="kg_sync"),
"kg_sync_apply":  ToolSpec(name="kg_sync_apply", description="应用一次增量变更并落成新版本（需 confirm=True）",
                           input_model=KGSyncApplyInput, output_model=KGSyncApplyOutput, skill="kg_sync"),
"kg_sync_rollback": ToolSpec(name="kg_sync_rollback", description="回退到上一个/指定版本",
                           input_model=KGSyncRollbackInput, output_model=KGSyncRollbackOutput, skill="kg_sync"),





##mini patch
# kg_incremental.py 的 _plan_add 里，加一个可选参数：有就直接用，没有才自己构建
def _plan_add(op, kg, *, subgraph=None):
    doc_id = op["doc_id"]
    sub = subgraph if subgraph is not None else build_subgraph_for_document(doc_id, kg)
    # ...后续引用计数/合并逻辑不变...
