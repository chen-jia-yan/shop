from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import parse_qs

from kb_poc.config import KBSettings
from kb_poc.ui.api_common import parse_json_body
from kb_poc.ui.api_common import send_json

from .service import build_context, create_draft, edit_draft_chunks, get_artifact_detail, get_draft_detail, get_file_detail, list_files, list_file_drafts, preview_file_detail, save_draft_detail


def handle_get(handler, parsed) -> bool:
    if parsed.path == "/api/chunk-studio/files":
        context = build_context(KBSettings.load())
        send_json(handler, list_files(context))
        return True
    if parsed.path == "/api/chunk-studio/file":
        query = parse_qs(parsed.query)
        file_id_raw = str((query.get("file_id") or [""])[0]).strip()
        if not file_id_raw.isdigit():
            send_json(handler, payload={"error": "file_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return True
        try:
            context = build_context(KBSettings.load())
            send_json(handler, get_file_detail(context, int(file_id_raw)))
        except FileNotFoundError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        return True
    if parsed.path == "/api/chunk-studio/artifact":
        query = parse_qs(parsed.query)
        artifact_path = str((query.get("path") or [""])[0]).strip()
        locator = str((query.get("locator") or [""])[0]).strip() or None
        source_file = str((query.get("source_file") or [""])[0]).strip() or None
        try:
            context = build_context(KBSettings.load())
            send_json(
                handler,
                get_artifact_detail(
                    context,
                    artifact_path=artifact_path,
                    locator=locator,
                    source_file=source_file,
                ),
            )
        except FileNotFoundError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        return True
    if parsed.path == "/api/chunk-studio/preview":
        query = parse_qs(parsed.query)
        file_id_raw = str((query.get("file_id") or [""])[0]).strip()
        overrides_raw = str((query.get("overrides") or ["{}"])[0]).strip()
        if not file_id_raw.isdigit():
            send_json(handler, payload={"error": "file_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return True
        try:
            overrides = json.loads(overrides_raw)
            context = build_context(KBSettings.load())
            send_json(handler, preview_file_detail(context, int(file_id_raw), overrides))
        except json.JSONDecodeError:
            send_json(handler, payload={"error": "overrides must be valid JSON"}, status=HTTPStatus.BAD_REQUEST)
        except FileNotFoundError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        return True
    if parsed.path == "/api/chunk-studio/drafts":
        query = parse_qs(parsed.query)
        file_id_raw = str((query.get("file_id") or [""])[0]).strip()
        if not file_id_raw.isdigit():
            send_json(handler, payload={"error": "file_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return True
        context = build_context(KBSettings.load())
        send_json(handler, list_file_drafts(context, int(file_id_raw)))
        return True
    if parsed.path == "/api/chunk-studio/draft":
        query = parse_qs(parsed.query)
        draft_id = str((query.get("draft_id") or [""])[0]).strip()
        if not draft_id:
            send_json(handler, payload={"error": "draft_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return True
        try:
            context = build_context(KBSettings.load())
            send_json(handler, get_draft_detail(context, draft_id))
        except FileNotFoundError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        return True
    return False


def handle_post(handler, parsed) -> bool:
    if parsed.path == "/api/chunk-studio/draft/create":
        payload = parse_json_body(handler)
        file_id = int(payload.get("file_id") or 0)
        if file_id <= 0:
            send_json(handler, payload={"error": "file_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return True
        context = build_context(KBSettings.load())
        send_json(
            handler,
            create_draft(
                context,
                file_id,
                str(payload.get("name") or ""),
                dict(payload.get("profiles") or {}),
                initial_chunks=list(payload.get("initial_chunks") or []),
            ),
        )
        return True
    if parsed.path == "/api/chunk-studio/draft/save":
        payload = parse_json_body(handler)
        draft_id = str(payload.get("draft_id") or "").strip()
        if not draft_id:
            send_json(handler, payload={"error": "draft_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return True
        context = build_context(KBSettings.load())
        send_json(
            handler,
            save_draft_detail(
                context,
                draft_id,
                name=str(payload.get("name") or ""),
                profiles=dict(payload.get("profiles") or {}),
                edited_chunks=list(payload.get("edited_chunks") or []),
                operations=list(payload.get("operations") or []),
            ),
        )
        return True
    if parsed.path == "/api/chunk-studio/draft/edit":
        payload = parse_json_body(handler)
        draft_id = str(payload.get("draft_id") or "").strip()
        operation = dict(payload.get("operation") or {})
        if not draft_id:
            send_json(handler, payload={"error": "draft_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return True
        try:
            context = build_context(KBSettings.load())
            send_json(handler, edit_draft_chunks(context, draft_id, operation))
        except FileNotFoundError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            send_json(handler, payload={"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        return True
    return False