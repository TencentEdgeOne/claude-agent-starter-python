"""Helpers for converting Claude Agent SDK stream messages into frontend SSE events."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

try:
    from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent
except ImportError:  # Keep this module importable when SDK is missing.
    AssistantMessage = None  # type: ignore[assignment]
    ResultMessage = None  # type: ignore[assignment]
    StreamEvent = None  # type: ignore[assignment]


@dataclass
class StreamState:
    """Mutable state used while converting SDK messages into SSE events."""

    full_assistant_text: str = ""
    sent_text_len_by_block: dict[int, int] = field(default_factory=dict)


def sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_tool_name(raw_name: str) -> str:
    """Extract short name from MCP tool full name (e.g. mcp__edgeone__commands → commands)."""
    if "__" in raw_name:
        return raw_name.split("__")[-1]
    return raw_name


def _is_sdk_message(msg: Any, sdk_type: Any, class_name: str) -> bool:
    """Check SDK message type while keeping fallback support when SDK imports are unavailable."""
    return (sdk_type is not None and isinstance(msg, sdk_type)) or type(msg).__name__ == class_name


def _is_block_type(block: Any, block_type: str, class_hint: str) -> bool:
    """Check block type while supporting SDK objects that only expose class names."""
    actual_type = getattr(block, "type", None)
    return actual_type == block_type or (actual_type is None and class_hint in type(block).__name__)


def _first_text_from_content(content: Any) -> str:
    """Return the first text value from an AssistantMessage content list."""
    if not isinstance(content, list):
        return ""
    for block in content:
        text = getattr(block, "text", None)
        if text:
            return text
    return ""


def _handle_stream_event(msg: Any, state: StreamState) -> list[str]:
    """Convert real-time Anthropic stream events to frontend SSE events."""
    events: list[str] = []
    event = msg.event
    event_type = event.get("type", "")

    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type", "") == "text_delta":
            text = delta.get("text", "")
            if text:
                state.full_assistant_text += text
                events.append(sse_event("text_delta", {"delta": text}))

    elif event_type == "content_block_start":
        block = event.get("content_block", {})
        if block.get("type") == "tool_use":
            tool_name = _extract_tool_name(block.get("name", ""))
            if tool_name:
                events.append(sse_event("tool_called", {"tool": tool_name}))

    return events


def _handle_assistant_message(msg: Any, state: StreamState) -> tuple[list[str], bool]:
    """Convert AssistantMessage blocks to SSE events. Returns (events, should_stop)."""
    content = getattr(msg, "content", None)
    error = getattr(msg, "error", None)
    if error:
        err_text = _first_text_from_content(content)
        return [sse_event("error", {"message": err_text or str(error)})], True

    if not isinstance(content, list):
        return [], False

    events: list[str] = []
    for idx, block in enumerate(content):
        if _is_block_type(block, "text", "TextBlock"):
            full_text = getattr(block, "text", "") or ""
            already_sent = state.sent_text_len_by_block.get(idx, 0)
            if len(full_text) > already_sent:
                delta = full_text[already_sent:]
                state.sent_text_len_by_block[idx] = len(full_text)
                state.full_assistant_text = full_text
                events.append(sse_event("text_delta", {"delta": delta}))

        elif _is_block_type(block, "tool_use", "ToolUse"):
            tool_name = _extract_tool_name(getattr(block, "name", "") or "")
            if tool_name:
                events.append(sse_event("tool_called", {"tool": tool_name}))

    return events, False


def sdk_message_to_sse(msg: Any, state: StreamState) -> tuple[list[str], bool]:
    """Convert one Claude SDK message to frontend SSE events. Returns (events, should_stop)."""
    if _is_sdk_message(msg, StreamEvent, "StreamEvent"):
        return _handle_stream_event(msg, state), False
    if _is_sdk_message(msg, AssistantMessage, "AssistantMessage"):
        return _handle_assistant_message(msg, state)
    if _is_sdk_message(msg, ResultMessage, "ResultMessage"):
        return [], True
    return [], False


async def iter_query_messages(
    response_iter: Any,
    cancel_signal: Any,
    heartbeat_interval_s: int,
) -> AsyncGenerator[tuple[str, Any], None]:
    """Yield query messages, heartbeat pings, or cancellation markers."""
    cancel_task = asyncio.create_task(cancel_signal.wait())
    pending: asyncio.Task[Any] | None = None

    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(response_iter.__anext__())

            done, _ = await asyncio.wait(
                {pending, cancel_task},
                timeout=heartbeat_interval_s,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if cancel_task in done:
                yield "cancelled", None
                break

            if not done:
                yield "ping", None
                continue

            try:
                msg = pending.result()
            except StopAsyncIteration:
                yield "finished", None
                break
            pending = None
            yield "message", msg

    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except BaseException:
                pass
        if not cancel_task.done():
            cancel_task.cancel()
            try:
                await cancel_task
            except BaseException:
                pass
        aclose = getattr(response_iter, "aclose", None)
        if callable(aclose):
            await aclose()
