"""
Delete-conversation handler — EdgeOne Makers Python cloud function.

POST /delete-conversation
  Body:    { conversation_id, user_id? }
  Returns: { status: "ok", conversation_id }

Permanently deletes a conversation (messages, metadata, and global index).
This operation is irreversible.
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

logger = create_logger("delete-conversation")


def _read_body(rfile, headers) -> dict:
    """Decode the JSON request body; return an empty dict on any failure."""
    length = int(headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    try:
        return json.loads(rfile.read(length).decode("utf-8")) or {}
    except (ValueError, UnicodeDecodeError):
        return {}


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

        conversation_id = str(body.get("conversation_id") or body.get("conversationId") or "").strip()
        user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None

        if not conversation_id:
            self._write_json(400, {"status": "error", "message": "conversation_id is required"})
            return

        store = self.context.agent.store

        logger.log(
            f"delete_conversation: conversation_id={conversation_id!r} user_id={user_id!r}"
        )

        try:
            store.delete_conversation(conversation_id=conversation_id)
            logger.log(f"delete_conversation: deleted conversation_id={conversation_id!r}")
            self._write_json(200, {"status": "ok", "conversation_id": conversation_id})

        except Exception as e:
            logger.error(
                f"delete_conversation failed: conversation_id={conversation_id!r} "
                f"user_id={user_id!r} type={type(e).__name__} err={e!r}"
            )
            logger.error(f"traceback:\n{traceback.format_exc()}")
            self._write_json(
                500,
                {"status": "error", "conversation_id": conversation_id, "message": str(e)},
            )
