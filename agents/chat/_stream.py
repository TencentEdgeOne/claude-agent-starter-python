"""
Helpers for converting Claude Agent SDK stream messages into frontend SSE events.

Architecture aligned with the TypeScript reference (claude-agent-starter/agents/chat/_stream.ts):

SDK message types → SSE events:
  StreamEvent (content_block_delta/text_delta)  → text_delta (real-time streaming)
  AssistantMessage (tool_use blocks)            → tool_called, skill_loaded, debug_block
  UserMessage (tool_result with base64Image)    → image, debug_msg
  ResultMessage                                 → signals end of stream

Key principle: text is ONLY emitted via StreamEvent to avoid duplication.
AssistantMessage text blocks are tracked (sent_text_len_by_block) but NOT re-emitted.
"""

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


# Project skills configuration
PROJECT_SKILLS = [
    {
        "name": "sandbox-algorithms",
        "label": "Sandbox algorithm execution",
        "description": "Run deterministic algorithm scripts through the EdgeOne sandbox code_interpreter and return verified execution results.",
    },
]


# Regex to match base64Image fields in JSON strings (for redaction)
_BASE64_IMAGE_RE = re.compile(
    r'"base64Image"\s*:\s*"[A-Za-z0-9+/=]{100,}"'
)
_MARKDOWN_DATA_IMAGE_RE = re.compile(
    r"!\[[^\]]*]\(\s*data:image/[^;)\s]+;base64,[A-Za-z0-9+/=]+\s*\)",
    re.IGNORECASE,
)
_MARKDOWN_DATA_IMAGE_TAIL_RE = re.compile(
    r"!\[[^\]]*]\(\s*data:image/[^;)\s]+;base64[\s\S]*\Z",
    re.IGNORECASE,
)
_BARE_DATA_IMAGE_RE = re.compile(
    r"data:image/[^;)\s]+;base64,[A-Za-z0-9+/=]+",
    re.IGNORECASE,
)
_BARE_DATA_IMAGE_TAIL_RE = re.compile(
    r"data:image/[^;)\s]+;base64,[A-Za-z0-9+/=]*\Z",
    re.IGNORECASE,
)
_INCOMPLETE_MARKDOWN_IMAGE_TEXT_RE = re.compile(r"!\[[^\]]*\Z")
_INCOMPLETE_MARKDOWN_IMAGE_LINK_RE = re.compile(r"!\[[^\]]*]\([^\)]*\Z")


@dataclass
class StreamState:
    """Mutable state used while converting SDK messages into SSE events."""

    full_assistant_text: str = ""
    emitted_assistant_text_len: int = 0
    sent_text_len_by_block: dict[int, int] = field(default_factory=dict)
    logged_tool_events: set[str] = field(default_factory=set)
    bot_msg_id: str = ""
    has_images: bool = False
    last_msg_type: str = ""  # Track message type transitions (like TS lastMsgType)


def _redact_base64(text: str) -> str:
    """Replace large base64Image values with placeholder for logging."""
    return _BASE64_IMAGE_RE.sub('"base64Image": "[REDACTED image data]"', text)


def sanitize_assistant_text(text: str) -> str:
    """Remove inline image data URIs from assistant prose before streaming/storage."""
    cleaned = _MARKDOWN_DATA_IMAGE_RE.sub("", text)
    cleaned = _MARKDOWN_DATA_IMAGE_TAIL_RE.sub("", cleaned)
    cleaned = _BARE_DATA_IMAGE_RE.sub("", cleaned)
    cleaned = _BARE_DATA_IMAGE_TAIL_RE.sub("", cleaned)
    cleaned = _INCOMPLETE_MARKDOWN_IMAGE_LINK_RE.sub("", cleaned)
    cleaned = _INCOMPLETE_MARKDOWN_IMAGE_TEXT_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.lstrip()


def _safe_json_preview(value: Any, max_length: int = 4000) -> str:
    """Serialize debug payload safely, redact base64, and truncate."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    # Fast path: skip regex if no base64Image
    if "base64Image" in text:
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


def _extract_skill_name_from_tool_input(tool_input: Any) -> str | None:
    """Extract skill name from a load_skill tool invocation input."""
    if isinstance(tool_input, dict):
        value = tool_input.get("skill") or tool_input.get("name") or tool_input.get("skillName")
        return value if isinstance(value, str) else None
    return None


# ---------------------------------------------------------------------------
# Image extraction from tool results (matches TS emitToolResultImages)
# ---------------------------------------------------------------------------

def _extract_images_from_tool_result(block: Any, state: StreamState) -> list[str]:
    """
    Extract images from tool_result content and return SSE image events.
    Matches TS reference: emitToolResultImages().

    Handles two shapes:
      1. Anthropic standard image content block:
         {type: "image", source: {type: "base64", media_type: "image/png", data: "<b64>"}}
         — emitted by EdgeOne's browser screenshot tool, code_interpreter
         renders, and anything else that returns images natively. Without
         this branch the model inlines a giant ![](data:image/png;base64,...)
         blob into the assistant text instead of streaming a real image.
      2. Legacy JSON inside a text block:
         [{type: "text", text: '{"base64Image": "<b64>"}'}]
         — used by some EdgeOne first-party tools.
    """
    events: list[str] = []
    content = getattr(block, "content", None)

    # Normalize content into an iterable of items so we can walk both shapes.
    items: list[Any]
    if isinstance(content, list):
        items = content
    elif content is None:
        items = []
    else:
        items = [content]

    # ── Shape 1: native image content block ────────────────────────────────
    for item in items:
        # dict-shape (when SDK gives us a plain dict) or attr-shape (when
        # SDK gives us a typed object) — handle both.
        item_type = (
            item.get("type") if isinstance(item, dict)
            else getattr(item, "type", None)
        )
        if item_type != "image":
            continue
        source = (
            item.get("source") if isinstance(item, dict)
            else getattr(item, "source", None)
        )
        if not source:
            continue
        source_type = (
            source.get("type") if isinstance(source, dict)
            else getattr(source, "type", None)
        )
        data = (
            source.get("data") if isinstance(source, dict)
            else getattr(source, "data", None)
        )
        media_type = (
            source.get("media_type") if isinstance(source, dict)
            else getattr(source, "media_type", None)
        ) or "image/png"
        if source_type == "base64" and isinstance(data, str) and data:
            image_id = str(uuid.uuid4())
            events.append(sse_event("image", {
                "imageId": image_id,
                "base64": data,
                "mimeType": media_type,
                "size": len(data),
            }))
            state.has_images = True

    # ── Shape 2: text-wrapped JSON with base64Image field ──────────────────
    texts_to_check: list[str] = []
    for item in items:
        if isinstance(item, str):
            texts_to_check.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content") or ""
            if text:
                texts_to_check.append(str(text))
        else:
            text = getattr(item, "text", None) or getattr(item, "content", None)
            if text:
                texts_to_check.append(str(text))

    for text in texts_to_check:
        if "base64Image" not in text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and parsed.get("base64Image"):
                base64_data = parsed["base64Image"]
                image_id = str(uuid.uuid4())
                events.append(sse_event("image", {
                    "imageId": image_id,
                    "base64": base64_data,
                    "mimeType": "image/png",
                    "size": len(base64_data),
                }))
                state.has_images = True
        except (json.JSONDecodeError, TypeError, ValueError):
            # Regex fallback
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


# ---------------------------------------------------------------------------
# StreamEvent handler — real-time text streaming only
# ---------------------------------------------------------------------------

def _handle_stream_event(msg: Any, state: StreamState, debug_logger: Any = None) -> list[str]:
    """
    Handle StreamEvent: emit text_delta for real-time streaming.
    Tool events are NOT emitted here (handled by AssistantMessage to avoid duplication).
    """
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
                cleaned_text = sanitize_assistant_text(state.full_assistant_text)
                already_sent = state.emitted_assistant_text_len
                if len(cleaned_text) > already_sent:
                    clean_delta = cleaned_text[already_sent:]
                    state.emitted_assistant_text_len = len(cleaned_text)
                    events.append(sse_event("text_delta", {"delta": clean_delta}))

    return events


# ---------------------------------------------------------------------------
# AssistantMessage handler — tool_called, skill_loaded, debug_block
# (text is NOT emitted here — StreamEvent handles it)
# ---------------------------------------------------------------------------

def _handle_assistant_message(msg: Any, state: StreamState, debug_logger: Any = None) -> tuple[list[str], bool]:
    """
    Handle AssistantMessage: emit tool_called, skill_loaded, debug_block.
    Text blocks are skipped (handled by StreamEvent to avoid duplication).
    Matches TS reference: emitAssistantBlocks() minus text emission.
    """
    content = getattr(msg, "content", None)
    error = getattr(msg, "error", None)
    if error:
        err_text = ""
        if isinstance(content, list):
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    err_text = text
                    break
        return [sse_event("error", {
            "message": err_text or str(error),
            "errorType": type(error).__name__,
            "detail": repr(error),
        })], True

    if not isinstance(content, list):
        return [], False

    events: list[str] = []
    for idx, block in enumerate(content):
        if _is_block_type(block, "text", "TextBlock"):
            # Track text length for full_assistant_text accuracy,
            # but do NOT emit — StreamEvent handles text_delta.
            full_text = getattr(block, "text", "") or ""
            state.sent_text_len_by_block[idx] = len(full_text)
            # Update full_assistant_text from the authoritative snapshot
            if full_text:
                state.full_assistant_text = full_text

        elif _is_block_type(block, "tool_use", "ToolUse"):
            tool_name = _extract_tool_name(getattr(block, "name", "") or "")
            raw_name = getattr(block, "name", "") or ""
            tool_id = getattr(block, "id", None)
            tool_input = getattr(block, "input", None)

            # Deduplicate: only emit once per tool_use
            dedup_key = f"tool_use:{tool_id or idx}"
            if dedup_key not in state.logged_tool_events:
                state.logged_tool_events.add(dedup_key)

                _log_tool_debug(debug_logger, "tool_call", {
                    "id": tool_id,
                    "name": tool_name,
                    "raw_name": raw_name,
                    "input": tool_input,
                })

                if tool_name:
                    events.append(sse_event("tool_called", {"tool": tool_name}))

                # Detect skill loading. The Claude Agent SDK's built-in tool
                # is named `Skill` (capital S, current SDK) but `load_skill`
                # exists as a legacy alias / short name in some runtime
                # versions. Match both so an SDK upgrade or rename doesn't
                # silently disable the skill UI.
                is_skill_tool = (
                    tool_name == "Skill"
                    or tool_name == "load_skill"
                    or "load_skill" in raw_name
                    or raw_name.endswith("Skill")
                )
                if is_skill_tool:
                    skill_name = _extract_skill_name_from_tool_input(tool_input)
                    if skill_name:
                        events.append(sse_event("skill_loaded", {
                            "name": skill_name,
                            "status": "loaded",
                        }))

        elif _is_block_type(block, "tool_result", "ToolResult"):
            # Extract images from tool results
            image_events = _extract_images_from_tool_result(block, state)
            events.extend(image_events)

        else:
            # Other block types: emit as debug_block (matches TS reference)
            block_type = getattr(block, "type", type(block).__name__)
            dedup_key = f"debug_block:{idx}:{block_type}"
            if dedup_key not in state.logged_tool_events:
                state.logged_tool_events.add(dedup_key)
                events.append(sse_event("debug_block", {
                    "blockIndex": idx,
                    "blockType": block_type,
                    "block": _safe_json_preview(block, 4000),
                }))

    return events, False


# ---------------------------------------------------------------------------
# UserMessage handler — image extraction + debug_msg
# (matches TS: emitToolResultImages + emitDebugMessage for msg.type === 'user')
# ---------------------------------------------------------------------------

def _handle_user_message(msg: Any, state: StreamState, debug_logger: Any = None) -> list[str]:
    """
    Handle UserMessage (tool_result): extract images and emit debug_msg.
    Matches TS reference: emitToolResultImages() + emitDebugMessage().

    TS logic:
      const toolResults = msg.tool_use_result ?? msg.message?.content ?? [];
      const resultArr = Array.isArray(toolResults) ? toolResults : [toolResults];
      for (const item of resultArr) {
        const text = typeof item === 'string' ? item : (item?.text ?? item?.content ?? '');
        if (text.includes('base64Image')) { ... }
      }
    """
    events: list[str] = []

    # Priority: tool_use_result first (matches TS), then content
    tool_results = getattr(msg, "tool_use_result", None)
    if tool_results is None:
        tool_results = getattr(msg, "content", None)

    # Normalize to list (matches TS: Array.isArray ? x : [x])
    if tool_results is None:
        result_arr: list[Any] = []
    elif isinstance(tool_results, list):
        result_arr = tool_results
    else:
        result_arr = [tool_results]

    for item in result_arr:
        # Extract text from item (matches TS: item?.text ?? item?.content ?? '')
        text = ""
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content") or ""
            # Also check if the dict itself has base64Image directly
            if not text and "base64Image" in item:
                base64_data = item.get("base64Image")
                if isinstance(base64_data, str) and len(base64_data) > 100:
                    image_id = str(uuid.uuid4())
                    events.append(sse_event("image", {
                        "imageId": image_id,
                        "base64": base64_data,
                        "mimeType": "image/png",
                        "size": len(base64_data),
                    }))
                    state.has_images = True
                continue
        else:
            text = getattr(item, "text", None) or getattr(item, "content", None) or ""

        if not isinstance(text, str) or "base64Image" not in text:
            continue

        # Parse JSON to extract base64Image (matches TS: JSON.parse(text))
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and parsed.get("base64Image"):
                base64_data = parsed["base64Image"]
                image_id = str(uuid.uuid4())
                events.append(sse_event("image", {
                    "imageId": image_id,
                    "base64": base64_data,
                    "mimeType": "image/png",
                    "size": len(base64_data),
                }))
                state.has_images = True
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Emit debug_msg for observability (matches TS emitDebugMessage)
    events.append(sse_event("debug_msg", {
        "msgType": "user",
        "preview": _safe_json_preview(msg, 4000),
    }))

    return events


# ---------------------------------------------------------------------------
# Main dispatcher (matches TS: for await (const msg of q) { ... })
# ---------------------------------------------------------------------------

def sdk_message_to_sse(msg: Any, state: StreamState, debug_logger: Any = None) -> tuple[list[str], bool]:
    """
    Convert one Claude SDK message to frontend SSE events.
    Returns (events, should_stop).

    Matches TS reference logic:
      StreamEvent       → text_delta (real-time)
      AssistantMessage  → tool_called, skill_loaded, debug_block
      UserMessage       → image, debug_msg
      ResultMessage     → stop signal
    """
    # --- StreamEvent: real-time text streaming ---
    if _is_sdk_message(msg, StreamEvent, "StreamEvent"):
        return _handle_stream_event(msg, state, debug_logger), False

    # --- AssistantMessage: tool_called, skill_loaded, debug_block ---
    if _is_sdk_message(msg, AssistantMessage, "AssistantMessage"):
        # Reset counters on user→assistant transition (matches TS lastMsgType logic)
        if state.last_msg_type == "user":
            state.sent_text_len_by_block.clear()
        state.last_msg_type = "assistant"
        return _handle_assistant_message(msg, state, debug_logger)

    # --- ResultMessage: end of stream ---
    if _is_sdk_message(msg, ResultMessage, "ResultMessage"):
        _log_tool_debug(debug_logger, "result_message", {
            "subtype": getattr(msg, "subtype", None),
            "duration_ms": getattr(msg, "duration_ms", None),
            "total_cost_usd": getattr(msg, "total_cost_usd", None),
            "usage": getattr(msg, "usage", None),
        })
        return [], True

    # --- UserMessage: image extraction + debug ---
    if type(msg).__name__ == "UserMessage":
        state.last_msg_type = "user"
        return _handle_user_message(msg, state, debug_logger), False

    # --- Unknown message types: emit debug_msg ---
    msg_type = getattr(msg, "type", type(msg).__name__)
    msg_subtype = getattr(msg, "subtype", None)
    if msg_type == "system" and msg_subtype == "thinking_tokens":
        return [], False

    return [sse_event("debug_msg", {
        "msgType": msg_type,
        "preview": _safe_json_preview(msg, 4000),
    })], False


# ---------------------------------------------------------------------------
# Async iteration helper (unchanged)
# ---------------------------------------------------------------------------

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
            try:
                await aclose()
            except (AttributeError, RuntimeError):
                # Suppress platform tracing errors (e.g. _RootChildrenTracker missing _on_ending)
                pass
