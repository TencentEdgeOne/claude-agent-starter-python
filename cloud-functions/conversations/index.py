"""
Conversations handler — EdgeOne Makers

Route: POST /conversations

Lists conversations for the requesting eo-uuid user.
Calls context.agent.store.list_conversations(user_id=..., limit=..., order=..., after=..., before=...).
Returns: { conversations, next_cursor, previous_cursor }

user_id is REQUIRED — returns 400 without it.
"""

from typing import Any
import json
from .._logger import create_logger

logger = create_logger("conversations")

DEFAULT_LIMIT = 20
MIN_LIMIT = 1
MAX_LIMIT = 100


def _clamp_limit(raw) -> int:
    try:
        v = int(raw)
        return max(MIN_LIMIT, min(MAX_LIMIT, v))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def _serialize_for_log(obj: Any) -> Any:
    """Best-effort convert SDK objects (or anything) to JSON-friendly form."""
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: _serialize_for_log(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_log(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: _serialize_for_log(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return repr(obj)


def _normalize_conversation(item: Any) -> dict | None:
    """Normalize a runtime ConversationMeta object into a stable frontend shape.

    SDK Python 端字段（snake_case）：
      conversation_id, created_at, last_message_at, message_count, metadata
    """
    if item is None:
        return None

    # Support both object attributes and dict keys
    def get(key, *aliases):
        for k in (key, *aliases):
            v = getattr(item, k, None) if not isinstance(item, dict) else item.get(k)
            if v is not None:
                return v
        return None

    # SDK 字段：conversation_id (Python snake_case)
    conv_id = get("conversation_id", "conversationId", "id")
    if not conv_id:
        return None

    # Title: SDK ConversationMeta 本身没有 title 字段，从 metadata 里取；
    # 若没有，title fallback 由后面的 get_messages 补充
    meta = get("metadata") or {}
    if isinstance(meta, dict):
        explicit_title = meta.get("title") or meta.get("name") or meta.get("subject")
    else:
        explicit_title = getattr(meta, "title", None) or getattr(meta, "name", None)

    # 也尝试 first_user_message（老式字段）
    first_question = get("first_user_message", "firstUserMessage", "first_message", "firstMessage")
    if not explicit_title and first_question:
        text = str(first_question).replace("\n", " ").strip()
        explicit_title = text if len(text) <= 8 else text[:8] + "..."

    title = explicit_title or "New chat"

    preview = None
    if isinstance(meta, dict):
        preview = meta.get("preview") or meta.get("last_message") or meta.get("snippet")

    def to_ts(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return int(v)
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return {
        "id": str(conv_id),
        "title": title,
        "preview": str(preview) if preview else None,
        # SDK Python: last_message_at / created_at
        "lastMessageAt": to_ts(get("last_message_at", "lastMessageAt", "updated_at", "updatedAt")),
        "createdAt": to_ts(get("created_at", "createdAt")),
        "userId": str(u) if (u := get("user_id", "userId")) else None,
        # SDK Python: message_count
        "messageCount": int(mc) if (mc := get("message_count", "messageCount")) else None,
    }


async def handler(context: Any):
    body = getattr(context.request, "body", None) or {}
    if not isinstance(body, dict):
        body = {}

    user_id = str(body.get("user_id") or body.get("userId") or "").strip()
    limit = _clamp_limit(body.get("limit", DEFAULT_LIMIT))
    order = "asc" if body.get("order") == "asc" else "desc"
    after = str(body.get("after") or "").strip() or None
    before = str(body.get("before") or "").strip() or None

    if not user_id:
        logger.error("Missing user_id")
        return {
            "status_code": 400,
            "body": {"status": "error", "message": "user_id is required"},
        }

    agent = getattr(context, "agent", None)
    store = getattr(agent, "store", None) if agent is not None else None

    lister = (
        getattr(store, "list_conversations", None)
        or getattr(store, "listConversations", None)
    )

    if lister is None or not callable(lister):
        logger.error("context.agent.store.list_conversations is unavailable")
        return {
            "status_code": 501,
            "body": {
                "status": "error",
                "message": "store.list_conversations is unavailable",
                "conversations": [],
            },
        }

    params = {"user_id": user_id, "limit": limit, "order": order}
    if after:
        params["after"] = after
    if before:
        params["before"] = before

    logger.log(f"list_conversations params: user_id=..., limit={limit}, order={order}, has_after={bool(after)}")

    try:
        result = await lister(**params)

        # === DEBUG: 打印 store 返回的原始 list_conversations 数据 ===
        try:
            raw_dump = _serialize_for_log(result)
            logger.log(
                f"[conversations][store_raw] user_id={user_id}, "
                f"data={json.dumps(raw_dump, ensure_ascii=False, default=str)}"
            )
        except Exception as dump_err:
            logger.error(f"[conversations][store_raw] dump failed: {dump_err}")

        # SDK list_conversations 返回 ListConversationsResult 对象，Python 端字段：
        #   result.items          → list[ConversationMeta]
        #   result.next_cursor    → str | None
        #   result.previous_cursor → str | None
        raw_items = []
        if hasattr(result, "items") and isinstance(result.items, list):
            raw_items = result.items
        elif isinstance(result, list):
            raw_items = result
        elif isinstance(result, dict):
            for key in ("items", "conversations", "data", "results"):
                if isinstance(result.get(key), list):
                    raw_items = result[key]
                    break

        conversations = [c for item in raw_items if (c := _normalize_conversation(item))]

        # --- Title fallback: fetch first user message for untitled conversations ---
        if store and hasattr(store, "get_messages"):
            untitled = [c for c in conversations if c["title"] == "New chat"]
            for conv in untitled:
                try:
                    messages = await store.get_messages(
                        conversation_id=conv["id"], limit=5, order="asc"
                    )
                    for msg in (messages or []):
                        role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
                        if role != "user":
                            continue
                        content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
                        text = str(content or "").replace("\n", " ").strip()
                        if text:
                            conv["title"] = text if len(text) <= 8 else text[:8] + "..."
                            break
                except Exception as e:
                    logger.error(f"failed to fetch first message for {conv['id']}: {e}")
        # -------------------------------------------------------------------------

        def _pick_cursor(key, *aliases):
            if isinstance(result, dict):
                for k in (key, *aliases):
                    v = result.get(k)
                    if v and isinstance(v, str):
                        return v
            for k in (key, *aliases):
                v = getattr(result, k, None)
                if v and isinstance(v, str):
                    return v
            return None

        # SDK Python 返回 next_cursor / previous_cursor (snake_case)
        next_cursor = _pick_cursor("next_cursor", "nextCursor")
        previous_cursor = _pick_cursor("previous_cursor", "previousCursor", "prev_cursor", "prevCursor")

        logger.log(f"list_conversations: count={len(conversations)}, has_next={bool(next_cursor)}")

        response = {
            "conversations": conversations,
            "nextCursor": next_cursor,
            "previousCursor": previous_cursor,
        }

        # === DEBUG: 打印最终返回给前端的响应 ===
        try:
            logger.log(
                f"[conversations][response] user_id={user_id}, "
                f"count={len(conversations)}, "
                f"data={json.dumps(response, ensure_ascii=False, default=str)}"
            )
        except Exception as dump_err:
            logger.error(f"[conversations][response] dump failed: {dump_err}")

        return response

    except Exception as e:
        logger.error(f"failed to list conversations: {e}")
        return {
            "status_code": 500,
            "body": {
                "status": "error",
                "message": str(e),
                "conversations": [],
            },
        }
