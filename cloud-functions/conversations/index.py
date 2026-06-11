"""
Conversations handler — EdgeOne Makers Python cloud function.

POST /conversations
  Body:    { user_id, limit?, order?, after?, before? }
  Returns: { conversations: [...], nextCursor, previousCursor }

Lists conversations for the requesting user. `user_id` is required.
"""

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from typing import Any

# EdgeOne loads each index.py as a top-level module without package context,
# so the parent directory must be on sys.path to import sibling helpers.
_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from _logger import create_logger  # noqa: E402

logger = create_logger("conversations")

DEFAULT_LIMIT = 20
MIN_LIMIT = 1
MAX_LIMIT = 100
TITLE_MAX_LEN = 8


def _read_body(rfile, headers) -> dict:
    """Decode the JSON request body; return an empty dict on any failure."""
    length = int(headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    try:
        return json.loads(rfile.read(length).decode("utf-8")) or {}
    except (ValueError, UnicodeDecodeError):
        return {}


def _clamp_limit(raw: Any) -> int:
    try:
        return max(MIN_LIMIT, min(MAX_LIMIT, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def _attr(item: Any, *keys: str) -> Any:
    """Read attribute or dict key, trying each name in order until a value is found."""
    if isinstance(item, dict):
        for k in keys:
            if item.get(k) is not None:
                return item[k]
        return None
    for k in keys:
        v = getattr(item, k, None)
        if v is not None:
            return v
    return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truncate_title(text: str) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= TITLE_MAX_LEN else text[:TITLE_MAX_LEN] + "..."


def _normalize_conversation(item: Any) -> dict | None:
    """Normalize a SDK ConversationMeta into the frontend response shape."""
    conv_id = _attr(item, "conversation_id", "conversationId", "id")
    if not conv_id:
        return None

    metadata = _attr(item, "metadata") or {}
    title = None
    preview = None
    if isinstance(metadata, dict):
        title = metadata.get("title") or metadata.get("name") or metadata.get("subject")
        preview = metadata.get("preview") or metadata.get("last_message") or metadata.get("snippet")

    if not title:
        first_message = _attr(item, "first_user_message", "firstUserMessage", "first_message")
        if first_message:
            title = _truncate_title(str(first_message))

    user_id = _attr(item, "user_id", "userId")

    return {
        "id": str(conv_id),
        "title": title or "New chat",
        "preview": str(preview) if preview else None,
        "lastMessageAt": _to_int(_attr(item, "last_message_at", "lastMessageAt", "updated_at")),
        "createdAt": _to_int(_attr(item, "created_at", "createdAt")),
        "userId": str(user_id) if user_id else None,
        "messageCount": _to_int(_attr(item, "message_count", "messageCount")),
    }


def _extract_items(result: Any) -> list:
    """Pull the list of conversation items from various possible result shapes."""
    if hasattr(result, "items") and isinstance(result.items, list):
        return result.items
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("items", "conversations", "data", "results"):
            if isinstance(result.get(key), list):
                return result[key]
    return []


def _pick_cursor(result: Any, *keys: str) -> str | None:
    """Return the first non-empty string cursor from a result (dict or object)."""
    for k in keys:
        value = result.get(k) if isinstance(result, dict) else getattr(result, k, None)
        if isinstance(value, str) and value:
            return value
    return None


def _fill_missing_titles(store: Any, conversations: list[dict]) -> None:
    """Replace the placeholder title with the first user message, when available."""
    if not hasattr(store, "get_messages"):
        return
    for conv in conversations:
        if conv["title"] != "New chat":
            continue
        try:
            messages = store.get_messages(conversation_id=conv["id"], limit=5, order="asc") or []
        except Exception as e:
            logger.error(f"failed to fetch first message for {conv['id']}: {e}")
            continue
        for msg in messages:
            if _attr(msg, "role") != "user":
                continue
            text = str(_attr(msg, "content") or "")
            if text.strip():
                conv["title"] = _truncate_title(text)
                break


class handler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = _read_body(self.rfile, self.headers)

        user_id = str(body.get("user_id") or body.get("userId") or "").strip()
        if not user_id:
            self._write_json(400, {"status": "error", "message": "user_id is required"})
            return

        limit = _clamp_limit(body.get("limit", DEFAULT_LIMIT))
        order = "asc" if body.get("order") == "asc" else "desc"
        after = str(body.get("after") or "").strip() or None
        before = str(body.get("before") or "").strip() or None

        store = self.context.agent.store

        params: dict = {"user_id": user_id, "limit": limit, "order": order}
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        logger.log(
            f"list_conversations: user_id={user_id!r} limit={limit} order={order} "
            f"after={after!r} before={before!r}"
        )

        try:
            result = store.list_conversations(**params)
            conversations = [
                c for item in _extract_items(result) if (c := _normalize_conversation(item))
            ]

            # Dedupe by id — the user_conversation_index can carry multiple
            # entries for the same conversation_id (one per appended user
            # message, since agents/chat writes a user-indexed copy on every
            # turn). The runtime's list_conversations does not collapse them,
            # so the sidebar would otherwise render N rows for the same
            # thread. Keep the FIRST occurrence so the runtime's intended
            # ordering (driven by `order=` and pagination cursors) is
            # preserved.
            seen_ids: set[str] = set()
            deduped: list[dict] = []
            for conv in conversations:
                if conv["id"] in seen_ids:
                    continue
                seen_ids.add(conv["id"])
                deduped.append(conv)
            duplicates_dropped = len(conversations) - len(deduped)
            conversations = deduped

            _fill_missing_titles(store, conversations)

            response = {
                "conversations": conversations,
                "nextCursor": _pick_cursor(result, "next_cursor", "nextCursor"),
                "previousCursor": _pick_cursor(
                    result, "previous_cursor", "previousCursor", "prev_cursor", "prevCursor"
                ),
            }
            logger.log(
                f"list_conversations: returned {len(conversations)} unique items "
                f"({duplicates_dropped} duplicate(s) dropped)"
            )
            self._write_json(200, response)

        except Exception as e:
            logger.error(
                f"list_conversations failed: user_id={user_id!r} "
                f"type={type(e).__name__} err={e!r}"
            )
            logger.error(f"traceback:\n{traceback.format_exc()}")
            self._write_json(
                500,
                {"status": "error", "message": str(e), "conversations": []},
            )
