"""
History handler — EdgeOne Makers
=========================================

Route: POST /history

Reads conversation history from context.agent.store.get_messages() and returns
it to the frontend for restoring the chat window after a page refresh.

Note: base64Image content is redacted from history responses to avoid
sending large payloads to the frontend. Images are restored from
client-side IndexedDB instead.
"""

import json
import time
from datetime import datetime, timezone
from typing import Any

from .._logger import create_logger
from .._redact import redact_base64_in_text

logger = create_logger("history")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conversation_id(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    value = body.get("conversation_id")
    if value is None:
        value = body.get("conversationId")
    return value if isinstance(value, str) else ""


def _content_to_text(content: Any) -> str:
    """Flatten various content shapes into a plain text string with base64 redacted."""
    if isinstance(content, str):
        return redact_base64_in_text(content)

    if isinstance(content, dict):
        if "content" in content:
            return _content_to_text(content.get("content"))
        if "output" in content:
            return _content_to_text(content.get("output"))
        if "text" in content:
            return redact_base64_in_text(str(content.get("text") or ""))
        return ""

    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("output_text") or "")
            text = redact_base64_in_text(text)
            if text:
                parts.append(text)
        return "\n".join(parts)

    if content is None:
        return ""

    return str(content)


def _attr(item: Any, *keys: str) -> Any:
    """Read attribute or dict key, trying each key in order."""
    if isinstance(item, dict):
        for k in keys:
            if k in item and item[k] is not None:
                return item[k]
        return None
    for k in keys:
        v = getattr(item, k, None)
        if v is not None:
            return v
    return None


def _serialize_for_log(obj: Any) -> Any:
    """Best-effort convert SDK message objects (or anything) to JSON-friendly form."""
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: _serialize_for_log(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_log(v) for v in obj]
    # Fallback: pull __dict__ if available, else repr
    if hasattr(obj, "__dict__"):
        return {k: _serialize_for_log(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return repr(obj)


async def handler(context: Any):
    start_time = time.time()
    logger.log(f"[history] start: {_iso_now()}")

    body = getattr(context.request, "body", None) or {}
    if not isinstance(body, dict):
        body = {}

    conversation_id = _get_conversation_id(body)

    agent = getattr(context, "agent", None)
    store = getattr(agent, "store", None) if agent is not None else None

    logger.log(f"conversationId: {conversation_id}")

    if not store or not conversation_id:
        logger.log(
            f"[history] end: {_iso_now()}, total: {int((time.time() - start_time) * 1000)}ms"
        )
        return {"conversation_id": conversation_id, "messages": []}

    getter = (
        getattr(store, "get_messages", None)
        or getattr(store, "getMessages", None)
    )

    if getter is None or not callable(getter):
        logger.error("context.agent.store.get_messages is unavailable")
        logger.log(
            f"[history] end: {_iso_now()}, total: {int((time.time() - start_time) * 1000)}ms"
        )
        return {"conversation_id": conversation_id, "messages": []}

    try:
        history = await getter(conversation_id=conversation_id, limit=100, order="asc")

        # === DEBUG: 打印 store 返回的原始历史数据 ===
        try:
            raw_dump = _serialize_for_log(history)
            logger.log(
                f"[history][store_raw] conversation_id={conversation_id}, "
                f"count={len(history) if isinstance(history, list) else 0}, "
                f"data={json.dumps(raw_dump, ensure_ascii=False, default=str)}"
            )
        except Exception as dump_err:
            logger.error(f"[history][store_raw] dump failed: {dump_err}")

        messages: list[dict] = []
        for item in history or []:
            role = _attr(item, "role")
            if role != "user" and role != "assistant":
                continue

            content = _content_to_text(_attr(item, "content"))
            if not content and role == "user":
                continue

            message_id = _attr(item, "message_id", "messageId")
            created_at = _attr(item, "created_at", "createdAt") or 0

            messages.append(
                {
                    "id": message_id or f"{role}-{created_at}",
                    "role": role,
                    "content": content or "",
                    "timestamp": int(created_at) if isinstance(created_at, (int, float)) else 0,
                }
            )

        response = {"conversation_id": conversation_id, "messages": messages}

        # === DEBUG: 打印最终返回给前端的响应 ===
        try:
            logger.log(
                f"[history][response] conversation_id={conversation_id}, "
                f"count={len(messages)}, "
                f"data={json.dumps(response, ensure_ascii=False, default=str)}"
            )
        except Exception as dump_err:
            logger.error(f"[history][response] dump failed: {dump_err}")

        logger.log(
            f"[history] end: {_iso_now()}, total: {int((time.time() - start_time) * 1000)}ms"
        )
        return response

    except Exception as e:
        logger.error(f"failed to get messages: {e}")
        logger.log(
            f"[history] end: {_iso_now()}, total: {int((time.time() - start_time) * 1000)}ms"
        )
        return {"conversation_id": conversation_id, "messages": []}
