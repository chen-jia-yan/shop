from pydantic import BaseModel, Field


class KGSyncStatusInput(BaseModel):
    pass


class KGSyncStatusOutput(BaseModel):
    active_version: str | None
    node_count: int
    edge_count: int
    unresolved_count: int
    extractor: str
    store: str
    enabled: bool
    report_text: str


class KGSyncEntityPreview(BaseModel):
    id: str
    type: str
    label: str
    reason: str  # matched_existing | rule_new | llm_new


class KGSyncPlanInput(BaseModel):
    op: str                              # add | update | delete
    file_path: str | None = None
    doc_id: str | None = None
    exclude_entity_ids: list[str] = Field(default_factory=list)


class KGSyncPlanOutput(BaseModel):
    op: str
    doc_id: str | None
    source_file: str | None
    nodes_added: int
    nodes_removed: int
    nodes_touched: int
    edges_added: int
    edges_removed: int
    edges_touched: int
    new_entities_for_review: list[KGSyncEntityPreview]
    warnings: list[str]
    report_text: str


class KGSyncApplyInput(BaseModel):
    op: str
    file_path: str | None = None
    doc_id: str | None = None
    exclude_entity_ids: list[str] = Field(default_factory=list)
    confirm: bool = False


class KGSyncApplyOutput(BaseModel):
    ok: bool
    from_version: str | None
    to_version: str | None
    delta_file: str | None
    message: str


class KGSyncRollbackInput(BaseModel):
    to_version: str | None = None


class KGSyncRollbackOutput(BaseModel):
    ok: bool
    active_version: str | None
    message: str
