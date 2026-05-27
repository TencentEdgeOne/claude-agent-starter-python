"""
History handler — EdgeOne Pages Functions

Route: POST /history
Returns conversation history for frontend chat recovery after page refresh.
"""

from typing import Any

from .._logger import create_logger

logger = create_logger("history")


def _content_to_text(content: Any) -> str:
    """Convert stored content to a displayable string for the frontend."""
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        if "content" in content:
            return _content_to_text(content.get("content"))
        if "output" in content:
            return _content_to_text(content.get("output"))
        if "text" in content:
            return str(content.get("text") or "")
        return ""

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("output_text")
                if text:
                    parts.append(str(text))
        return "\n".join(part for part in parts if part)

    return str(content) if content else ""


async def handler(context: Any):
    """Read conversation history and return frontend-displayable message list."""
    cid = getattr(context, "conversation_id", None) or ""

    store = getattr(context, "store", None)
    if store is None or not cid:
        return {"conversation_id": cid, "messages": []}

    try:
        history = await store.get_messages(cid, limit=100, order="asc")
    except Exception as e:
        logger.error(f"failed to get messages: {e}")
        return {"conversation_id": cid, "messages": []}

    messages: list[dict] = []
    for item in history:
        role = getattr(item, "role", None)
        if role not in ("user", "assistant"):
            continue

        content = _content_to_text(getattr(item, "content", ""))

        # Don't skip messages with [image] placeholder or empty content for assistant
        # This ensures image-only responses are represented in history
        if not content and role == "user":
            continue

        messages.append({
            "id": getattr(item, "message_id", None) or f"{role}-{getattr(item, 'created_at', 0)}",
            "role": role,
            "content": content or "",
            "timestamp": getattr(item, "created_at", None) or 0,
        })

    return {"conversation_id": cid, "messages": messages}
