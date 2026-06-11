"""
History handler — EdgeOne Makers Python cloud function.

POST /history
  Body:    { conversation_id, user_id? }
  Returns: { conversation_id, messages: [{ id, role, content, timestamp }, ...] }

Returns the chat history for a conversation so the frontend can restore the
chat window after a page refresh.

Note: base64Image content is redacted from history responses to avoid sending
large payloads to the frontend. Images are restored from client-side IndexedDB.
"""

import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler
from typing import Any

# EdgeOne loads each index.py as a top-level module without package context,
# so the parent directory must be on sys.path to import sibling helpers.
_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from _logger import create_logger  # noqa: E402
from _redact import redact_base64_in_text  # noqa: E402

logger = create_logger("history")

MESSAGE_LIMIT = 100


def _read_body(rfile, headers) -> dict:
    """Decode the JSON request body; return an empty dict on any failure."""
    length = int(headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    try:
        return json.loads(rfile.read(length).decode("utf-8")) or {}
    except (ValueError, UnicodeDecodeError):
        return {}


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


def _content_to_text(content: Any) -> str:
    """Flatten a message content (string / dict / list) into plain text with base64 redacted."""
    if content is None:
        return ""
    if isinstance(content, str):
        return redact_base64_in_text(content)
    if isinstance(content, dict):
        if "content" in content:
            return _content_to_text(content["content"])
        if "output" in content:
            return _content_to_text(content["output"])
        if "text" in content:
            return redact_base64_in_text(str(content["text"] or ""))
        return ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = redact_base64_in_text(str(item.get("text") or item.get("output_text") or ""))
            if text:
                parts.append(text)
        return "\n".join(parts)
    return str(content)


def _normalize_message(item: Any) -> dict | None:
    """Normalize a SDK message into the frontend response shape, dropping unsupported roles."""
    role = _attr(item, "role")
    if role not in ("user", "assistant"):
        return None

    content = _content_to_text(_attr(item, "content"))
    if not content and role == "user":
        return None

    message_id = _attr(item, "message_id", "messageId")
    created_at = _attr(item, "created_at", "createdAt") or 0
    timestamp = int(created_at) if isinstance(created_at, (int, float)) else 0

    return {
        "id": message_id or f"{role}-{timestamp}",
        "role": role,
        "content": content or "",
        "timestamp": timestamp,
    }


class handler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        start = time.time()

        body = _read_body(self.rfile, self.headers)
        conversation_id = str(body.get("conversation_id") or body.get("conversationId") or "").strip()
        user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None

        store = self.context.agent.store
        logger.log(f"get_messages: conversation_id={conversation_id!r} user_id={user_id!r}")

        if not conversation_id:
            self._write_json(200, {"conversation_id": conversation_id, "messages": []})
            return

        try:
            history = store.get_messages(
                conversation_id=conversation_id, limit=MESSAGE_LIMIT, order="asc"
            ) or []
            messages = [m for item in history if (m := _normalize_message(item))]

            elapsed_ms = int((time.time() - start) * 1000)
            logger.log(
                f"get_messages: returned {len(messages)} messages in {elapsed_ms}ms"
            )
            self._write_json(200, {"conversation_id": conversation_id, "messages": messages})

        except Exception as e:
            logger.error(
                f"get_messages failed: conversation_id={conversation_id!r} "
                f"user_id={user_id!r} type={type(e).__name__} err={e!r}"
            )
            logger.error(f"traceback:\n{traceback.format_exc()}")
            self._write_json(200, {"conversation_id": conversation_id, "messages": []})
