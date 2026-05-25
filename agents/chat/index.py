"""
Claude Agent SDK chat handler — EdgeOne Pages agent-python 格式。

路由：POST /chat
响应：SSE 流式文本（text/event-stream）

SSE 事件协议：
  event: text_delta  data: {"delta": "..."}
  event: tool_called data: {"tool": "ToolName"}
  event: ping        data: {"ts": 1710000000000}
  event: error       data: {"message": "..."}
  event: done        data: {"stopped": false}

会话持久化：
  通过 ctx.store.claude_session_store() 获取 Claude Session Store 传给 SDK，
  同时用 ctx.store.append_message() 保存 user/assistant 消息供 /history 读取。

工具：使用 EdgeOne 平台提供的沙箱工具（commands/files/code_interpreter/browser），
     通过 Claude SDK 的 MCP Server 机制桥接。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any, AsyncGenerator

from dotenv import load_dotenv

load_dotenv()

# 尝试导入 Claude Agent SDK
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

def _extract_tool_name(raw_name: str) -> str:
    """从 MCP 工具全名中提取短名（如 mcp__edgeone__commands → commands）"""
    if "__" in raw_name:
        return raw_name.split("__")[-1]
    return raw_name


def build_agent_options(
    session_store=None,
    mcp_server=None,
    mcp_server_name: str = MCP_SERVER_NAME,
    allowed_tools: list[str] | None = None,
) -> "ClaudeAgentOptions":
    """构造 Claude Agent SDK 的运行配置。
    禁用所有内置工具，工具通过 MCP server 提供。"""
    opts = ClaudeAgentOptions(
        model=resolve_model_name(),
        system_prompt=SYSTEM_PROMPT,
        tools=[],                   # 禁用所有内置工具
        allowed_tools=allowed_tools or [],
        setting_sources=[],
        add_dirs=[],
        permission_mode="bypassPermissions",
        max_turns=10,
        env=collect_gateway_env(),
        include_partial_messages=True,  # 启用流式部分消息
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
    """EdgeOne Pages Functions 入口（async generator 流式版本）。"""
    cid = getattr(ctx, "conversation_id", None) or ""
    logger.log(f"[debug] cid: {cid}")

    body = ctx.request.body
    logger.log(f"[debug] body type={type(body).__name__}, body={body}")
    user_message: str = body.get("message", "") if isinstance(body, dict) else ""
    logger.log(f"[debug] user_message: '{user_message[:200]}'")
    if not user_message.strip():
        logger.log("[debug] EARLY RETURN: user_message is empty")
        yield sse_event("error", {"message": "'message' is required"})
        yield sse_event("done", {"stopped": False})
        return

    logger.log(f"[debug] _SDK_AVAILABLE={_SDK_AVAILABLE}")
    if not _SDK_AVAILABLE:
        logger.log("[debug] EARLY RETURN: claude_agent_sdk not available")
        yield sse_event("error", {"message": "claude_agent_sdk 未安装，请检查 requirements.txt"})
        yield sse_event("done", {"stopped": False})
        return

    # 获取平台 cancel signal（asyncio.Event），当 /stop 被调用时会被 set
    cancel_signal = getattr(ctx.request, "signal", None) or asyncio.Event()
    logger.log(f"[debug] cancel_signal type={type(cancel_signal).__name__}")

    # 获取 store 用于持久化对话
    store_adapter = getattr(ctx, "store", None)
    logger.log(f"[debug] store_adapter={store_adapter is not None}")

    # 暂时关闭 Claude session 机制，方便调试其他功能
    session_store = None
    # if store_adapter is not None and hasattr(store_adapter, "claude_session_store"):
    #     session_store = store_adapter.claude_session_store()

    # 保存 user message 到 store
    if store_adapter and cid:
        try:
            await store_adapter.append_message(cid, "user", user_message)
            logger.log("[debug] user message saved to store")
        except Exception as e:
            logger.error(f"[store] failed to save user message: {e}")

    # 构建 EdgeOne 平台工具 → Claude Agent SDK MCP server
    raw_tools = getattr(ctx, "tools", None)
    logger.log(f"[debug] raw_tools={raw_tools is not None}, has_to_claude_mcp_server={hasattr(raw_tools, 'to_claude_mcp_server') if raw_tools else False}")
    if raw_tools is None or not hasattr(raw_tools, "to_claude_mcp_server"):
        logger.log("[debug] EARLY RETURN: raw_tools unavailable")
        yield sse_event("error", {"message": "context.tools.to_claude_mcp_server is unavailable. Please upgrade pages-agent-toolkit."})
        yield sse_event("done", {"stopped": False})
        return

    edgeone_mcp = raw_tools.to_claude_mcp_server(MCP_SERVER_NAME, {"always_load": True})
    logger.log(f"[debug][tools] registered platform tools count: {len(edgeone_mcp.tools)}")
    for t in edgeone_mcp.tools:
        t_name = getattr(t, "name", None) or getattr(t, "get", lambda k, d=None: d)("name", "unknown")
        logger.log(f"[debug][tools]   tool: {t_name}")
    logger.log(f"[debug][tools] allowed_tools: {edgeone_mcp.allowed_tools}")
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
    logger.log(f"[debug][options] model={options.model}, max_turns={options.max_turns}, permission_mode={options.permission_mode}")
    logger.log(f"[debug][options] mcp_servers keys={list(options.mcp_servers.keys()) if options.mcp_servers else None}")

    stopped = False
    full_assistant_text = ""
    sent_text_len_by_block: dict[int, int] = {}

    try:
        # 使用 query() API（对应 Node 版的 query({ prompt, options })）
        logger.log(f"[debug][query] starting query with prompt: {user_message[:200]}")
        q = query(prompt=user_message, options=options)
        logger.log(f"[debug][query] query object created, type={type(q).__name__}")

        # 包装 cancel signal 与 streaming 迭代
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
                    logger.log("[stream] cancel signal received; aborting stream")
                    break

                if not done:
                    yield sse_event("ping", {"ts": int(time.time() * 1000)})
                    continue

                try:
                    msg = pending.result()
                except StopAsyncIteration:
                    break
                pending = None

                # ── 处理 StreamEvent（原始 Anthropic API 流事件）──
                # 这是实时流式推送的关键：text_delta 逐字到达
                if isinstance(msg, StreamEvent):
                    event = msg.event
                    event_type = event.get("type", "")
                    logger.log(f"[debug][StreamEvent] type={event_type}, keys={list(event.keys())}")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        delta_type = delta.get("type", "")
                        logger.log(f"[debug][StreamEvent] content_block_delta: delta_type={delta_type}, index={event.get('index')}")
                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                full_assistant_text += text
                                yield sse_event("text_delta", {"delta": text})
                        elif delta_type == "input_json_delta":
                            # 工具输入参数的增量 JSON
                            partial_json = delta.get("partial_json", "")
                            logger.log(f"[debug][StreamEvent] tool input_json_delta: {partial_json[:200]}")

                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        block_type = block.get("type", "")
                        logger.log(f"[debug][StreamEvent] content_block_start: block_type={block_type}, index={event.get('index')}, block={json.dumps(block, ensure_ascii=False)[:300]}")
                        if block_type == "tool_use":
                            raw_name = block.get("name", "")
                            tool_id = block.get("id", "")
                            tool_name = _extract_tool_name(raw_name)
                            logger.log(f"[debug][tool] START tool_use: raw_name={raw_name}, extracted={tool_name}, id={tool_id}")
                            if tool_name:
                                yield sse_event("tool_called", {"tool": tool_name})

                    elif event_type == "content_block_stop":
                        logger.log(f"[debug][StreamEvent] content_block_stop: index={event.get('index')}")

                    elif event_type == "message_start":
                        message = event.get("message", {})
                        logger.log(f"[debug][StreamEvent] message_start: role={message.get('role')}, model={message.get('model')}, usage={message.get('usage')}")

                    elif event_type == "message_delta":
                        delta = event.get("delta", {})
                        usage = event.get("usage", {})
                        logger.log(f"[debug][StreamEvent] message_delta: stop_reason={delta.get('stop_reason')}, usage={usage}")

                    elif event_type == "message_stop":
                        logger.log(f"[debug][StreamEvent] message_stop")

                    else:
                        logger.log(f"[debug][StreamEvent] unhandled event_type={event_type}, event={json.dumps(event, ensure_ascii=False)[:500]}")

                # ── 处理 AssistantMessage（累积的完整/部分消息）──
                # 作为兜底：如果 StreamEvent 未正常工作，从 AssistantMessage 提取增量
                elif isinstance(msg, AssistantMessage):
                    content = getattr(msg, "content", None)
                    is_partial = getattr(msg, "partial", None)
                    logger.log(f"[debug][AssistantMessage] partial={is_partial}, content_blocks={len(content) if isinstance(content, list) else 'N/A'}")

                    # 检查错误
                    error = getattr(msg, "error", None)
                    if error:
                        err_text = ""
                        if isinstance(content, list):
                            for block in content:
                                t = getattr(block, "text", None)
                                if t:
                                    err_text = t
                                    break
                        logger.error(f"[debug][error] SDK error={error}, text={err_text}")
                        yield sse_event("error", {"message": err_text or str(error)})
                        break

                    if isinstance(content, list):
                        for idx, block in enumerate(content):
                            block_type = getattr(block, "type", None)

                            if block_type == "text":
                                full_text = getattr(block, "text", "") or ""
                                already_sent = sent_text_len_by_block.get(idx, 0)
                                if len(full_text) > already_sent:
                                    delta = full_text[already_sent:]
                                    sent_text_len_by_block[idx] = len(full_text)
                                    full_assistant_text = full_text
                                    yield sse_event("text_delta", {"delta": delta})

                            elif block_type == "tool_use":
                                tool_name = _extract_tool_name(getattr(block, "name", "") or "")
                                tool_id = getattr(block, "id", "")
                                tool_input = getattr(block, "input", None)
                                logger.log(f"[debug][AssistantMessage] tool_use block: name={tool_name}, id={tool_id}, input={json.dumps(tool_input, ensure_ascii=False)[:300] if tool_input else None}")
                                if tool_name:
                                    yield sse_event("tool_called", {"tool": tool_name})

                            elif block_type == "tool_result":
                                tool_use_id = getattr(block, "tool_use_id", "")
                                is_error = getattr(block, "is_error", False)
                                result_content = getattr(block, "content", None)
                                result_preview = ""
                                if isinstance(result_content, str):
                                    result_preview = result_content[:500]
                                elif isinstance(result_content, list):
                                    for rb in result_content:
                                        if getattr(rb, "type", None) == "text":
                                            result_preview = (getattr(rb, "text", "") or "")[:500]
                                            break
                                logger.log(f"[debug][AssistantMessage] tool_result: tool_use_id={tool_use_id}, is_error={is_error}, preview={result_preview}")

                            else:
                                logger.log(f"[debug][AssistantMessage] unknown block type={block_type}, block={block}")

                elif isinstance(msg, ResultMessage):
                    result_text = getattr(msg, "text", None) or ""
                    result_role = getattr(msg, "role", None)
                    logger.log(f"[debug][ResultMessage] role={result_role}, text_len={len(result_text)}, ending stream")
                    break

                else:
                    # 其他消息类型（如 RateLimitEvent），记录但不处理
                    logger.log(f"[debug][stream] unhandled message type: {type(msg).__name__}, repr={repr(msg)[:300]}")

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
        if isinstance(e, ClaudeSDKError) if _SDK_AVAILABLE else False:
            prefix = "SDK 错误"
        else:
            prefix = "未知错误"
        logger.error(f"[error] {prefix}: {e}")
        yield sse_event("error", {"message": f"{prefix}: {e}"})

    # 保存 assistant response 到 store
    if store_adapter and cid and full_assistant_text.strip():
        try:
            await store_adapter.append_message(cid, "assistant", full_assistant_text)
            logger.log(f"[store] saved assistant response ({len(full_assistant_text)} chars)")
        except Exception as e:
            logger.error(f"[store] failed to save assistant response: {e}")

    yield sse_event("done", {"stopped": stopped})


# ========== 本地调试 ==========
if __name__ == "__main__":
    import asyncio

    async def _main():
        class _FakeRequest:
            body = {"message": sys.argv[1] if len(sys.argv) > 1 else "用终端命令查看当前系统时间"}
            signal = asyncio.Event()

        class _FakeCtx:
            request = _FakeRequest()
            conversation_id = "test-local"
            store = None
            tools = None

        async for chunk in handler(_FakeCtx()):
            print(chunk, end="", flush=True)

    asyncio.run(_main())
