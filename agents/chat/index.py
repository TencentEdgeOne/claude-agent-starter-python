"""
Claude Agent SDK chat handler — EdgeOne Makers agent-python format.

Route: POST /chat
Response: SSE stream (text/event-stream)

SSE event protocol:
  event: text_delta  data: {"delta": "..."}
  event: tool_called data: {"tool": "ToolName"}
  event: image       data: {"imageId": "...", "base64": "...", "mimeType": "...", "size": ...}
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
import os
import time
from typing import Any, AsyncGenerator
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        create_sdk_mcp_server,
        query,
    )
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

from .._model import collect_gateway_env, resolve_model_name
from .._logger import create_logger
from ._stream import StreamState, iter_query_messages, sdk_message_to_sse, sse_event, PROJECT_SKILLS


logger = create_logger("chat")
HEARTBEAT_INTERVAL_S = 5
MCP_SERVER_NAME = "edgeone"

# SYSTEM_PROMPT = (
#     "You are a helpful assistant running inside an EdgeOne environment.\n"
#     "You have access to these EdgeOne platform tools:\n"
#     "- commands: execute shell commands in the sandbox (e.g. date, ls, uname).\n"
#     "- files: file operations in the sandbox — read, write, list, makeDir, exists, remove.\n"
#     "  Parameters: op (required), path (required for most ops), content (for write).\n"
#     "- code_interpreter: run code in an isolated interpreter.\n"
#     "  Parameters: language (e.g. 'python'), code (the source code to execute).\n"
#     "- browser: interact with web pages — fetch, screenshot, click, type, evaluate.\n"
#     "  Parameters: op (required), url (for fetch), selector, text, script.\n\n"
#     "Use tools whenever they help answer the user's question concretely.\n"
#     "Call tools ONE AT A TIME. Do NOT simulate or fake tool outputs — actually call the tool.\n"
#     "Do NOT use any tools other than those listed above."
# )

SYSTEM_PROMPT = (
  'You are a helpful assistant running inside an EdgeOne sandbox environment.\n' +
  'You have access to these EdgeOne platform tools:\n' +
  '- commands: execute shell commands in the sandbox (e.g. date, ls, uname).\n' +
  '- files: file operations in the sandbox — read, write, list, makeDir, exists, remove.\n' +
  '  Parameters: op (required), path (required for most ops), content (for write).\n' +
  '- code_interpreter: run code in an isolated interpreter.\n' +
  '  Parameters: language (e.g. "python"), code (the source code to execute).\n' +
  '- browser: interact with web pages — fetch, screenshot, click, type, evaluate.\n' +
  '  Parameters: op (required), url (for fetch), selector, text, script.\n\n' +
  'Use tools whenever they help answer the user\'s question concretely.\n' +
  'Call tools ONE AT A TIME. Do NOT simulate or fake tool outputs — actually call the tool.\n' +
  'Do NOT use any external tools other than the EdgeOne platform tools listed above.\n' +
  'If the Claude SDK exposes project skills, you may use its built-in skill-loading mechanism when the user explicitly asks for a skill.'
)


def _normalize_uuid(value: str) -> str | None:
    """Return canonical UUID string, or None if value is not a valid UUID."""
    try:
        return str(UUID(value))
    except (TypeError, ValueError):
        return None


async def resolve_claude_session_binding(
    session_store: Any,
    conversation_id: str,
) -> tuple[str | None, str | None]:
    """
    Bind Claude SDK session to frontend conversation_id.

    First request for a conversation uses session_id=<conversation_id> to create
    a deterministic SDK session. Later requests use resume=<conversation_id>
    when that transcript already exists in session_store.
    """
    session_id = _normalize_uuid(conversation_id)
    if not session_id:
        logger.log(f"[session] skip SDK session binding: invalid conversation_id={conversation_id!r}")
        return None, None

    if session_store is None or not hasattr(session_store, "load"):
        return session_id, None

    try:
        from claude_agent_sdk._internal.sessions import project_key_for_directory

        project_key = project_key_for_directory(os.getcwd())
        entries = await session_store.load({"project_key": project_key, "session_id": session_id})
        if entries:
            logger.log(f"[session] resume Claude SDK session_id={session_id}, entries={len(entries)}")
            return None, session_id
        logger.log(f"[session] create Claude SDK session_id={session_id}")
    except Exception as e:
        logger.error(f"[session] failed to inspect session_store for resume: {e}")

    return session_id, None


def build_agent_options(
    session_store=None,
    mcp_server=None,
    mcp_server_name: str = MCP_SERVER_NAME,
    allowed_tools: list[str] | None = None,
    session_id: str | None = None,
    resume: str | None = None,
) -> "ClaudeAgentOptions":
    """Build Claude Agent SDK options. Disables built-in tools; tools provided via MCP server."""
    opts = ClaudeAgentOptions(
        model=resolve_model_name(),
        system_prompt=SYSTEM_PROMPT,
        cwd=os.getcwd(),
        tools=[],
        allowed_tools=list(set((allowed_tools or []))),
        setting_sources=["project"],
        skills="all",
        permission_mode="bypassPermissions",
        max_turns=10,
        env=collect_gateway_env(),
        include_partial_messages=True,
        max_buffer_size=20 * 1024 * 1024,  # 20MB — enough for browser screenshots
        session_id=session_id,
        resume=resume,
    )
    if session_store is not None:
        opts.session_store = session_store
    if mcp_server is not None:
        opts.mcp_servers = {mcp_server_name: mcp_server}
    return opts


async def handler(ctx: Any) -> AsyncGenerator[str, None]:
    """EdgeOne Makers entry point (async generator streaming)."""
    cid = getattr(ctx, "conversation_id", None) or ""

    body = ctx.request.body
    user_message: str = body.get("message", "") if isinstance(body, dict) else ""
    if not user_message.strip():
        yield sse_event("error", {"message": "'message' is required"})
        yield sse_event("done", {"stopped": False})
        return

    # Extract frontend-generated message IDs for history alignment
    user_msg_id: str = body.get("userMsgId", "") if isinstance(body, dict) else ""
    bot_msg_id: str = body.get("botMsgId", "") if isinstance(body, dict) else ""

    if not _SDK_AVAILABLE:
        yield sse_event("error", {"message": "claude_agent_sdk is not installed"})
        yield sse_event("done", {"stopped": False})
        return

    cancel_signal = getattr(ctx.request, "signal", None) or asyncio.Event()
    store_adapter = getattr(ctx, "store", None)

    # Get Claude session store for transcript persistence (matches TS reference).
    # This gives the SDK multi-turn context, preventing chaotic/repeated tool calls.
    raw_session_store = None
    if store_adapter and hasattr(store_adapter, "claude_session_store"):
        try:
            raw_session_store = store_adapter.claude_session_store()
            logger.log(f"[session_store] enabled, type={type(raw_session_store).__name__}, value={raw_session_store is not None}")
        except Exception as e:
            logger.error(f"[session_store] failed to get claude_session_store: {e}")
    else:
        logger.log(f"[session_store] NOT available, store_adapter={type(store_adapter).__name__ if store_adapter else None}, has_method={hasattr(store_adapter, 'claude_session_store') if store_adapter else False}")
    session_store = raw_session_store

    # Save user message (with frontend-generated ID if available)
    if store_adapter and cid:
        # === DEBUG: dump all store messages for this conversation ===
        try:
            all_msgs = await store_adapter.get_messages(cid, limit=100, order="asc")
            logger.log(f"[debug_store] conversation={cid}, total_messages={len(all_msgs)}")
            for m in all_msgs:
                role = getattr(m, "role", "?")
                msg_id = getattr(m, "message_id", "?")
                content = getattr(m, "content", "")
                preview = str(content)[:200] if content else ""
                created_at = getattr(m, "created_at", 0)
                logger.log(f"[debug_store]   [{role}] id={msg_id} ts={created_at} content={preview}")
        except Exception as e:
            logger.error(f"[debug_store] failed to dump: {e}")
        # === END DEBUG ===

        try:
            if user_msg_id:
                await store_adapter.append_message(cid, "user", user_message, message_id=user_msg_id)
            else:
                await store_adapter.append_message(cid, "user", user_message)
        except TypeError:
            # Fallback if store doesn't support message_id parameter
            try:
                await store_adapter.append_message(cid, "user", user_message)
            except Exception as e:
                logger.error(f"[store] failed to save user message: {e}")
        except Exception as e:
            logger.error(f"[store] failed to save user message: {e}")

    # Build EdgeOne platform tools → Claude Agent SDK MCP server
    raw_tools = getattr(ctx, "tools", None)
    if raw_tools is None or not hasattr(raw_tools, "to_claude_mcp_server"):
        yield sse_event("error", {"message": "context.tools.to_claude_mcp_server is unavailable."})
        yield sse_event("done", {"stopped": False})
        return

    edgeone_mcp = raw_tools.to_claude_mcp_server(MCP_SERVER_NAME, {"always_load": True})
    logger.log("[tool_debug][mcp_server]", {
        "name": getattr(edgeone_mcp, "name", None),
        "allowed_tools": getattr(edgeone_mcp, "allowed_tools", None),
        "tools": [
            {
                "name": getattr(tool, "name", None) if not isinstance(tool, dict) else tool.get("name"),
                "description": getattr(tool, "description", None) if not isinstance(tool, dict) else tool.get("description"),
                "input_schema": getattr(tool, "input_schema", None) if not isinstance(tool, dict) else tool.get("input_schema"),
            }
            for tool in (getattr(edgeone_mcp, "tools", None) or [])
        ],
    })
    mcp_server = create_sdk_mcp_server(
        name=edgeone_mcp.name,
        tools=edgeone_mcp.tools,
    )

    sdk_session_id, sdk_resume = await resolve_claude_session_binding(session_store, cid)
    options = build_agent_options(
        session_store=session_store,
        mcp_server=mcp_server,
        mcp_server_name=edgeone_mcp.name,
        allowed_tools=edgeone_mcp.allowed_tools,
        session_id=sdk_session_id,
        resume=sdk_resume,
    )

    stopped = False
    stream_state = StreamState(bot_msg_id=bot_msg_id)

    # Emit skills config event before query starts
    yield sse_event("skills_loaded", {
        "skills": "all",
        "setting_sources": ["project"],
    })

    # Emit available skills for frontend display
    yield sse_event("skills_available", {
        "skills": PROJECT_SKILLS,
    })

    try:
        response_iter = query(prompt=user_message, options=options).__aiter__()
        async for item_type, msg in iter_query_messages(response_iter, cancel_signal, HEARTBEAT_INTERVAL_S):
            if item_type == "cancelled":
                stopped = True
                break
            if item_type == "finished":
                break
            if item_type == "ping":
                yield sse_event("ping", {"ts": int(time.time() * 1000)})
                continue

            events, should_stop = sdk_message_to_sse(msg, stream_state, logger)
            for event in events:
                yield event
            if should_stop:
                break

    except Exception as e:  # noqa: BLE001
        logger.error(f"[error] {e}")
        yield sse_event("error", {"message": str(e)})

    # Save assistant response (with frontend-generated ID if available)
    # Save even if text is empty but images were sent (use placeholder)
    assistant_content = stream_state.full_assistant_text.strip()
    if not assistant_content and stream_state.has_images:
        assistant_content = "[image]"

    if store_adapter and cid and assistant_content:
        try:
            if bot_msg_id:
                await store_adapter.append_message(cid, "assistant", assistant_content, message_id=bot_msg_id)
            else:
                await store_adapter.append_message(cid, "assistant", assistant_content)
        except TypeError:
            # Fallback if store doesn't support message_id parameter
            try:
                await store_adapter.append_message(cid, "assistant", assistant_content)
            except Exception as e:
                logger.error(f"[store] failed to save assistant response: {e}")
        except Exception as e:
            logger.error(f"[store] failed to save assistant response: {e}")

    yield sse_event("done", {"stopped": stopped})
