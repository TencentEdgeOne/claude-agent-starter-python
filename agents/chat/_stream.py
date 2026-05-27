"""Helpers for converting Claude Agent SDK stream messages into frontend SSE events."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

try:
    from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent
except ImportError:  # Keep this module importable when SDK is missing.
    AssistantMessage = None  # type: ignore[assignment]
    ResultMessage = None  # type: ignore[assignment]
    StreamEvent = None  # type: ignore[assignment]


# Regex to match base64Image fields in JSON strings (for redaction)
_BASE64_IMAGE_RE = re.compile(
    r'"base64Image"\s*:\s*"[A-Za-z0-9+/=]{100,}"'
)


@dataclass
class StreamState:
    """Mutable state used while converting SDK messages into SSE events."""

    full_assistant_text: str = ""
    sent_text_len_by_block: dict[int, int] = field(default_factory=dict)
    logged_tool_events: set[str] = field(default_factory=set)
    bot_msg_id: str = ""
    has_images: bool = False


def _redact_base64(text: str) -> str:
    """Replace large base64Image values with placeholder for logging."""
    return _BASE64_IMAGE_RE.sub('"base64Image": "[REDACTED image data]"', text)


def _safe_json_preview(value: Any, max_length: int = 1200) -> str:
    """Serialize debug payload safely and truncate very large tool inputs/results."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    text = _redact_base64(text)
    return text if len(text) <= max_length else f"{text[:max_length]}...<truncated>"


def _log_tool_debug(debug_logger: Any, label: str, payload: dict[str, Any]) -> None:
    """Best-effort tool debug logging; never breaks streaming on logger errors."""
    if debug_logger is None or not hasattr(debug_logger, "log"):
        return
    try:
        debug_logger.log(f"[tool_debug][{label}] {_safe_json_preview(payload)}")
    except Exception:
        pass


def _log_once(state: StreamState, key: str, debug_logger: Any, label: str, payload: dict[str, Any]) -> None:
    """Avoid repeated logs from partial AssistantMessage snapshots."""
    if key in state.logged_tool_events:
        return
    state.logged_tool_events.add(key)
    _log_tool_debug(debug_logger, label, payload)


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


def _extract_images_from_tool_result(block: Any, state: StreamState) -> list[str]:
    """
    Extract base64Image from tool_result content and return SSE image events.

    Tool results may contain JSON text with a base64Image field (e.g. browser screenshot).
    We extract the image, emit it as a separate SSE event, and mark state.has_images.
    """
    events: list[str] = []
    content = getattr(block, "content", None)

    # content can be a string or a list of content blocks
    texts_to_check: list[str] = []

    if isinstance(content, str):
        texts_to_check.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                texts_to_check.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("output") or ""
                if text:
                    texts_to_check.append(str(text))
            else:
                # SDK object with text attribute
                text = getattr(item, "text", None) or getattr(item, "output", None)
                if text:
                    texts_to_check.append(str(text))

    for text in texts_to_check:
        if "base64Image" not in text:
            continue

        # Try to parse as JSON to extract base64Image
        try:
            parsed = json.loads(text)
            base64_data = None
            if isinstance(parsed, dict):
                base64_data = parsed.get("base64Image")
            if not base64_data:
                continue

            image_id = str(uuid.uuid4())
            events.append(sse_event("image", {
                "imageId": image_id,
                "base64": base64_data,
                "mimeType": "image/png",
                "size": len(base64_data),
            }))
            state.has_images = True
        except (json.JSONDecodeError, TypeError, ValueError):
            # Try regex extraction as fallback
            match = re.search(r'"base64Image"\s*:\s*"([A-Za-z0-9+/=]+)"', text)
            if match:
                base64_data = match.group(1)
                image_id = str(uuid.uuid4())
                events.append(sse_event("image", {
                    "imageId": image_id,
                    "base64": base64_data,
                    "mimeType": "image/png",
                    "size": len(base64_data),
                }))
                state.has_images = True

    return events


def _handle_stream_event(msg: Any, state: StreamState, debug_logger: Any = None) -> list[str]:
    """Convert real-time Anthropic stream events to frontend SSE events."""
    events: list[str] = []
    event = msg.event
    event_type = event.get("type", "")

    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        delta_type = delta.get("type", "")
        if delta_type == "text_delta":
            text = delta.get("text", "")
            if text:
                state.full_assistant_text += text
                events.append(sse_event("text_delta", {"delta": text}))
        elif delta_type == "input_json_delta":
            _log_tool_debug(debug_logger, "stream_tool_input_delta", {
                "index": event.get("index"),
                "partial_json": delta.get("partial_json", ""),
            })

    elif event_type == "content_block_start":
        block = event.get("content_block", {})
        if block.get("type") == "tool_use":
            tool_name = _extract_tool_name(block.get("name", ""))
            _log_tool_debug(debug_logger, "stream_tool_start", {
                "id": block.get("id"),
                "name": tool_name,
                "raw_name": block.get("name"),
                "input": block.get("input"),
                "index": event.get("index"),
            })
            if tool_name:
                events.append(sse_event("tool_called", {"tool": tool_name}))

    elif event_type == "content_block_stop":
        _log_tool_debug(debug_logger, "stream_block_stop", {"index": event.get("index")})

    return events


def _handle_assistant_message(msg: Any, state: StreamState, debug_logger: Any = None) -> tuple[list[str], bool]:
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
            tool_id = getattr(block, "id", None)
            _log_once(state, f"tool_use:{tool_id or idx}", debug_logger, "assistant_tool_use", {
                "id": tool_id,
                "name": tool_name,
                "raw_name": getattr(block, "name", "") or "",
                "input": getattr(block, "input", None),
            })
            if tool_name:
                events.append(sse_event("tool_called", {"tool": tool_name}))

        elif _is_block_type(block, "tool_result", "ToolResult"):
            tool_use_id = getattr(block, "tool_use_id", None)
            # Extract and emit screenshot images from tool results
            image_events = _extract_images_from_tool_result(block, state)
            events.extend(image_events)

            _log_once(state, f"tool_result:{tool_use_id or idx}", debug_logger, "assistant_tool_result", {
                "tool_use_id": tool_use_id,
                "is_error": getattr(block, "is_error", None),
                "content": _redact_base64(str(getattr(block, "content", None) or "")),
            })

    return events, False


def sdk_message_to_sse(msg: Any, state: StreamState, debug_logger: Any = None) -> tuple[list[str], bool]:
    """Convert one Claude SDK message to frontend SSE events. Returns (events, should_stop)."""
    if _is_sdk_message(msg, StreamEvent, "StreamEvent"):
        return _handle_stream_event(msg, state, debug_logger), False
    if _is_sdk_message(msg, AssistantMessage, "AssistantMessage"):
        return _handle_assistant_message(msg, state, debug_logger)
    if _is_sdk_message(msg, ResultMessage, "ResultMessage"):
        _log_tool_debug(debug_logger, "result_message", {
            "subtype": getattr(msg, "subtype", None),
            "duration_ms": getattr(msg, "duration_ms", None),
            "total_cost_usd": getattr(msg, "total_cost_usd", None),
            "usage": getattr(msg, "usage", None),
        })
        return [], True

    # Handle UserMessage (tool results from SDK conversation flow)
    if type(msg).__name__ == "UserMessage":
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                if _is_block_type(block, "tool_result", "ToolResult"):
                    image_events = _extract_images_from_tool_result(block, state)
                    if image_events:
                        return image_events, False
        return [], False

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
