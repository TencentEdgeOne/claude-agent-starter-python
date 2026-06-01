"""
Delete-conversation handler — EdgeOne Makers

Route: POST /delete-conversation

Permanently deletes a conversation (messages, metadata, global index).
Uses context.store.delete_conversation(conversation_id=...).
Irreversible.
"""

from typing import Any
from .._logger import create_logger

logger = create_logger("delete-conversation")


async def handler(context: Any):
    body = getattr(context.request, "body", None) or {}
    if not isinstance(body, dict):
        body = {}

    cid = str(body.get("conversation_id") or body.get("conversationId") or "").strip()
    user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None

    logger.log(f"conversation_id={cid}, user_id={user_id or '-'}")

    if not cid:
        return {
            "status_code": 400,
            "body": {"status": "error", "message": "conversation_id is required"},
        }

    store = getattr(context, "store", None)

    deleter = (
        getattr(store, "delete_conversation", None)
        or getattr(store, "deleteConversation", None)
    )

    if deleter is None or not callable(deleter):
        logger.error("context.store.delete_conversation is unavailable")
        return {
            "status_code": 501,
            "body": {
                "status": "error",
                "message": "store.delete_conversation is unavailable",
            },
        }

    try:
        # delete_conversation 只接受 conversation_id 参数
        await deleter(conversation_id=cid)

        logger.log(f"deleted conversation_id={cid}")
        return {"status": "ok", "conversation_id": cid}

    except Exception as e:
        logger.error(f"failed to delete conversation: {e}")
        return {
            "status_code": 500,
            "body": {
                "status": "error",
                "conversation_id": cid,
                "message": str(e),
            },
        }
