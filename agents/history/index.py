"""
History handler — EdgeOne Pages Functions
=========================================

文件路径 agents/history/index.py 自动映射到 **POST /history**

根据前端传入的 pages-agent-conversation-id，从 ctx.store.get_messages()
读取对话历史，返回前端可展示的 Message[] 格式。
用于页面刷新后恢复前端聊天窗口。
"""

from typing import Any

from .._logger import create_logger

logger = create_logger("history")


def _content_to_text(content: Any) -> str:
    """把 memory content 转成前端 Message.content 可展示的字符串。"""
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
    """读取对话历史并返回前端可展示的消息列表。"""
    cid = getattr(context, "conversation_id", None) or ""
    logger.log(f"conversation_id: {cid}")

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
        if not content:
            continue

        messages.append({
            "id": getattr(item, "message_id", None) or f"{role}-{getattr(item, 'created_at', 0)}",
            "role": role,
            "content": content,
            "timestamp": getattr(item, "created_at", None) or 0,
        })

    logger.log(f"loaded {len(messages)} messages")
    return {"conversation_id": cid, "messages": messages}
