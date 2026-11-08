from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from kb_poc.config import KBSettings

DRAFTS_DIR = Path("data") / "chunk_studio" / "drafts"


def build_draft_dir(settings: KBSettings) -> Path:
    target = settings.resolve(DRAFTS_DIR)
    target.mkdir(parents=True, exist_ok=True)
    return target


def build_draft_path(settings: KBSettings, draft_id: str) -> Path:
    return build_draft_dir(settings) / f"{draft_id}.json"


def list_drafts(settings: KBSettings, *, file_id: int | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(build_draft_dir(settings).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        current_file_id = int(payload.get("file_id") or 0)
        if file_id is not None and current_file_id != file_id:
            continue
        items.append(
            {
                "draft_id": str(payload.get("draft_id") or path.stem),
                "name": str(payload.get("name") or path.stem),
                "file_id": current_file_id,
                "source_file": str(payload.get("source_file") or ""),
                "updated_at": str(payload.get("updated_at") or ""),
                "chunk_count": len(payload.get("edited_chunks") or []),
            }
        )
    return sorted(items, key=lambda item: item.get("updated_at") or "", reverse=True)


def load_draft(settings: KBSettings, draft_id: str) -> dict[str, Any]:
    path = build_draft_path(settings, draft_id)
    if not path.exists():
        raise FileNotFoundError(f"Draft not found: {draft_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_draft(settings: KBSettings, payload: dict[str, Any]) -> dict[str, Any]:
    draft_id = str(payload.get("draft_id")) or uuid4().hex
    now = datetime.now().isoformat(timespec="seconds")
    payload = dict[str, Any](payload)
    payload["draft_id"] = draft_id
    payload.setdefault("created_at", now)
    payload["updated_at"] = now
    path = build_draft_path(settings, draft_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload