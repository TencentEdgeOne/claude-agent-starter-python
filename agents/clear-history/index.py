"""
Clear history handler — EdgeOne Makers

Route: POST /clear-history
Clears backend messages for the current conversation.
"""

from typing import Any

from .._logger import create_logger

logger = create_logger("clear-history")


def _debug_message(item: Any) -> dict:
    """Convert a stored message object to a compact debug payload."""
    return {
        "message_id": getattr(item, "message_id", None),
        "role": getattr(item, "role", None),
        "created_at": getattr(item, "created_at", None),
        "content": getattr(item, "content", None),
    }


async def handler(context: Any):
    """Clear conversation history and log the post-clear state."""
    body = getattr(context.request, "body", None) or {}
    cid = ""
    user_id = None
    if isinstance(body, dict):
        cid = body.get("conversation_id") or body.get("conversationId") or ""
        user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None
    store = getattr(context, "store", None)

    logger.log(f"conversation_id={cid}, user_id={user_id or '-'}")

    if not cid:
        return {
            "status_code": 400,
            "body": {
                "status": "error",
                "message": "conversation_id is required",
            },
        }

    if store is None or not hasattr(store, "clear_messages"):
        logger.error("context.store.clear_messages is unavailable")
        return {
            "status_code": 501,
            "body": {
                "status": "error",
                "message": "store.clear_messages is unavailable",
            },
        }

    try:
        # clear_messages 只接受 conversation_id 参数
        await store.clear_messages(conversation_id=cid)

        if hasattr(store, "get_messages"):
            history_after_clear = await store.get_messages(conversation_id=cid, limit=100, order="asc")
            logger.log(
                "[clear-history] history after clear:",
                {
                    "conversation_id": cid,
                    "count": len(history_after_clear) if isinstance(history_after_clear, list) else 0,
                    "messages": [_debug_message(item) for item in history_after_clear],
                },
            )

        return {"status": "ok", "conversation_id": cid}
    except Exception as e:
        logger.error(f"failed to clear messages: {e}")
        return {
            "status_code": 500,
            "body": {
                "status": "error",
                "conversation_id": cid,
                "message": str(e),
            },
        }
