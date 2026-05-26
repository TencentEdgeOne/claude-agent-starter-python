"""
Claude Agent SDK chat handler — EdgeOne Pages agent-python format.

Route: POST /chat
Response: SSE stream (text/event-stream)

SSE event protocol:
  event: text_delta  data: {"delta": "..."}
  event: tool_called data: {"tool": "ToolName"}
  event: ping        data: {"ts": 1710000000000}
  event: error       data: {"message": "..."}
  event: done        data: {"stopped": false}

Session persistence:
  Uses ctx.store to save user/assistant messages for /history recovery.

Tools:
  EdgeOne platform sandbox tools (commands/files/code_interpreter/browser)
  bridged via Claude SDK's MCP Server mechanism.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

from dotenv import load_dotenv

load_dotenv()

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        StreamEvent,
        create_sdk_mcp_server,
        query,
    )
    from claude_agent_sdk._errors import ClaudeSDKError
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

from .._model import collect_gateway_env, resolve_model_name
from .._logger import create_logger


logger = create_logger("chat")
HEARTBEAT_INTERVAL_S = 5
MCP_SERVER_NAME = "edgeone"

SYSTEM_PROMPT = (
    "You are a helpful assistant running inside an EdgeOne sandbox environment.\n"
    "You have access to these EdgeOne platform tools:\n"
    "- commands: execute shell commands in the sandbox (e.g. date, ls, uname).\n"
    "- files: file operations in the sandbox — read, write, list, makeDir, exists, remove.\n"
    "  Parameters: op (required), path (required for most ops), content (for write).\n"
    "- code_interpreter: run code in an isolated interpreter.\n"
    "  Parameters: language (e.g. 'python'), code (the source code to execute).\n"
    "- browser: interact with web pages — fetch, screenshot, click, type, evaluate.\n"
    "  Parameters: op (required), url (for fetch), selector, text, script.\n\n"
    "Use tools whenever they help answer the user's question concretely.\n"
    "Call tools ONE AT A TIME. Do NOT simulate or fake tool outputs — actually call the tool.\n"
    "Do NOT use any tools other than those listed above."
)


REGISTERED_SKILLS = [
    {"name": "code-review", "description": "Review code for quality, bugs, performance issues, and best practices."},
    {"name": "api-docs-generator", "description": "Generate API documentation from source code."},
    {"name": "test-writer", "description": "Write unit tests and integration tests for code."},
]


def _extract_tool_name(raw_name: str) -> str:
    """Extract short name from MCP tool full name (e.g. mcp__edgeone__commands → commands)."""
    if "__" in raw_name:
        return raw_name.split("__")[-1]
    return raw_name


def build_agent_options(
    session_store=None,
    mcp_server=None,
    mcp_server_name: str = MCP_SERVER_NAME,
    allowed_tools: list[str] | None = None,
) -> "ClaudeAgentOptions":
    """Build Claude Agent SDK options. Disables built-in tools; tools provided via MCP server."""
    opts = ClaudeAgentOptions(
        model=resolve_model_name(),
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        allowed_tools=list(set((allowed_tools or []) + ["Read", "Write", "Bash"])),
        setting_sources=["project"],
        add_dirs=[],
        permission_mode="bypassPermissions",
        max_turns=10,
        env=collect_gateway_env(),
        include_partial_messages=True,
    )
    if session_store is not None:
        opts.session_store = session_store
    if mcp_server is not None:
        opts.mcp_servers = {mcp_server_name: mcp_server}
    return opts


def sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def handler(ctx: Any) -> AsyncGenerator[str, None]:
    """EdgeOne Pages Functions entry point (async generator streaming)."""
    cid = getattr(ctx, "conversation_id", None) or ""

    body = ctx.request.body
    user_message: str = body.get("message", "") if isinstance(body, dict) else ""
    if not user_message.strip():
        yield sse_event("error", {"message": "'message' is required"})
        yield sse_event("done", {"stopped": False})
        return

    if not _SDK_AVAILABLE:
        yield sse_event("error", {"message": "claude_agent_sdk is not installed"})
        yield sse_event("done", {"stopped": False})
        return

    cancel_signal = getattr(ctx.request, "signal", None) or asyncio.Event()
    store_adapter = getattr(ctx, "store", None)

    # Session store (enable when ready)
    session_store = None

    # Save user message
    if store_adapter and cid:
        try:
            await store_adapter.append_message(cid, "user", user_message)
        except Exception as e:
            logger.error(f"[store] failed to save user message: {e}")

    # Build EdgeOne platform tools → Claude Agent SDK MCP server
    raw_tools = getattr(ctx, "tools", None)
    if raw_tools is None or not hasattr(raw_tools, "to_claude_mcp_server"):
        yield sse_event("error", {"message": "context.tools.to_claude_mcp_server is unavailable."})
        yield sse_event("done", {"stopped": False})
        return

    edgeone_mcp = raw_tools.to_claude_mcp_server(MCP_SERVER_NAME, {"always_load": True})
    mcp_server = create_sdk_mcp_server(
        name=edgeone_mcp.name,
        tools=edgeone_mcp.tools,
    )

    options = build_agent_options(
        session_store=session_store,
        mcp_server=mcp_server,
        mcp_server_name=edgeone_mcp.name,
        allowed_tools=edgeone_mcp.allowed_tools,
    )

    stopped = False
    full_assistant_text = ""
    sent_text_len_by_block: dict[int, int] = {}

    # Emit skills discovery event before query starts
    yield sse_event("skills_loaded", {
        "count": len(REGISTERED_SKILLS),
        "skills": REGISTERED_SKILLS,
        "setting_sources": ["project"],
    })

    try:
        q = query(prompt=user_message, options=options)
        response_iter = q.__aiter__()
        cancel_task = asyncio.create_task(cancel_signal.wait())
        pending: asyncio.Task[Any] | None = None

        try:
            while True:
                if pending is None:
                    pending = asyncio.create_task(response_iter.__anext__())

                done, _ = await asyncio.wait(
                    {pending, cancel_task},
                    timeout=HEARTBEAT_INTERVAL_S,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if cancel_task in done:
                    stopped = True
                    break

                if not done:
                    yield sse_event("ping", {"ts": int(time.time() * 1000)})
                    continue

                try:
                    msg = pending.result()
                except StopAsyncIteration:
                    break
                pending = None

                # ── Handle StreamEvent (real-time Anthropic API stream events) ──
                if isinstance(msg, StreamEvent):
                    event = msg.event
                    event_type = event.get("type", "")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        delta_type = delta.get("type", "")
                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                full_assistant_text += text
                                yield sse_event("text_delta", {"delta": text})

                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_name = _extract_tool_name(block.get("name", ""))
                            if tool_name:
                                yield sse_event("tool_called", {"tool": tool_name})

                # ── Handle AssistantMessage (accumulated complete/partial messages) ──
                elif isinstance(msg, AssistantMessage):
                    content = getattr(msg, "content", None)

                    # Check for errors
                    error = getattr(msg, "error", None)
                    if error:
                        err_text = ""
                        if isinstance(content, list):
                            for block in content:
                                t = getattr(block, "text", None)
                                if t:
                                    err_text = t
                                    break
                        yield sse_event("error", {"message": err_text or str(error)})
                        break

                    if isinstance(content, list):
                        for idx, block in enumerate(content):
                            block_type = getattr(block, "type", None)
                            block_class = type(block).__name__

                            # Text content
                            if block_type == "text" or (block_type is None and "TextBlock" in block_class):
                                full_text = getattr(block, "text", "") or ""
                                already_sent = sent_text_len_by_block.get(idx, 0)
                                if len(full_text) > already_sent:
                                    delta = full_text[already_sent:]
                                    sent_text_len_by_block[idx] = len(full_text)
                                    full_assistant_text = full_text
                                    yield sse_event("text_delta", {"delta": delta})

                            # Thinking blocks — skip, not sent to frontend
                            elif block_type == "thinking" or (block_type is None and "ThinkingBlock" in block_class):
                                pass

                            elif block_type == "redacted_thinking" or (block_type is None and "RedactedThinking" in block_class):
                                pass

                            # Tool use
                            elif block_type == "tool_use":
                                tool_name = _extract_tool_name(getattr(block, "name", "") or "")
                                if tool_name:
                                    yield sse_event("tool_called", {"tool": tool_name})

                            # Tool result — no action needed on frontend
                            elif block_type == "tool_result":
                                pass

                elif isinstance(msg, ResultMessage):
                    break

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

    except Exception as e:  # noqa: BLE001
        logger.error(f"[error] {e}")
        yield sse_event("error", {"message": str(e)})

    # Save assistant response
    if store_adapter and cid and full_assistant_text.strip():
        try:
            await store_adapter.append_message(cid, "assistant", full_assistant_text)
        except Exception as e:
            logger.error(f"[store] failed to save assistant response: {e}")

    yield sse_event("done", {"stopped": stopped})
