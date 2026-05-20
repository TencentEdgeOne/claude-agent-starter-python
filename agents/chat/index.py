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
import inspect
import json
import sys
import time
from typing import Any, Annotated, AsyncGenerator

from dotenv import load_dotenv

load_dotenv()

# 尝试导入 Claude Agent SDK
try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        StreamEvent,
        SdkMcpTool,
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

# ── EdgeOne 平台沙箱工具名 ──
EDGEONE_TOOL_NAMES = ["commands", "files", "code_interpreter", "browser"]

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

# ── 工具输入 Schema（对应 Node 版的 Zod schemas）──
TOOL_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "commands": {
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory"},
        },
        "required": ["cmd"],
    },
    "files": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["read", "write", "list", "exists", "remove", "makeDir"],
                "description": "File operation",
            },
            "path": {"type": "string", "description": "File or directory path"},
            "content": {"type": "string", "description": "Content for write"},
        },
        "required": ["op", "path"],
    },
    "browser": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["fetch", "screenshot", "click", "type", "evaluate"],
                "description": "Browser operation",
            },
            "url": {"type": "string", "description": "Target URL"},
            "selector": {"type": "string", "description": "CSS selector"},
            "text": {"type": "string", "description": "Text to type"},
            "script": {"type": "string", "description": "JavaScript to evaluate"},
        },
        "required": ["op"],
    },
    "code_interpreter": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["python", "javascript", "r", "bash"],
                "description": "Language to execute",
            },
            "code": {"type": "string", "description": "Code to execute"},
        },
        "required": ["language", "code"],
    },
}


def _extract_tool_name(raw_name: str) -> str:
    """从 MCP 工具全名中提取短名（如 mcp__edgeone__commands → commands）"""
    if "__" in raw_name:
        return raw_name.split("__")[-1]
    return raw_name


def _stringify_tool_result(result: Any) -> str:
    """将工具返回值转换为字符串"""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def _call_with_kwargs(fn: Any, args: dict[str, Any]) -> bool:
    """判断函数是否应该以 **kwargs 方式调用"""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False

    params = list(sig.parameters.values())
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params):
        return True

    required = [
        p.name for p in params
        if p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    if required and all(n in args for n in required):
        return True

    try:
        sig.bind(args)
        return False
    except TypeError:
        pass

    try:
        sig.bind(**args)
        return True
    except TypeError:
        return False


def build_edgeone_mcp_tools(ctx: Any) -> tuple[list["SdkMcpTool[Any]"], list[str]]:
    """
    构建 EdgeOne 平台工具 → Claude Agent SDK MCP tools。
    返回 (tools, allowed_tools)。
    """
    raw_tools = getattr(ctx, "tools", None)
    if raw_tools is None or not hasattr(raw_tools, "all"):
        logger.log("[tools] no platform tools available")
        return [], []

    platform_tools = raw_tools.all()
    logger.log(f"[tools] platform tools count: {len(platform_tools)}")

    mcp_tools: list[SdkMcpTool[Any]] = []

    for item in platform_tools:
        if isinstance(item, dict):
            name = item.get("name") or (item.get("function") or {}).get("name")
            description = item.get("description") or (item.get("function") or {}).get("description", "")
            execute = (
                item.get("execute")
                or item.get("handler")
                or item.get("invoke")
            )
        else:
            name = getattr(item, "name", None)
            description = getattr(item, "description", "") or getattr(getattr(item, "function", None), "description", "")
            execute = (
                getattr(item, "execute", None)
                or getattr(item, "handler", None)
                or getattr(item, "invoke", None)
            )

        input_schema = TOOL_INPUT_SCHEMAS.get(name) if name else None

        if not name or not input_schema or not callable(execute):
            logger.log(f"[tools] skipped unsupported platform tool: {name or '<unknown>'}")
            continue

        # 创建闭包捕获 execute 和 item
        def _make_handler(_execute: Any, _item: Any):
            async def handler(args: dict[str, Any]) -> dict[str, Any]:
                try:
                    if _call_with_kwargs(_execute, args):
                        result = _execute(**args)
                    else:
                        result = _execute(args)
                    if inspect.isawaitable(result):
                        result = await result
                    text = _stringify_tool_result(result)
                    return {"content": [{"type": "text", "text": text}]}
                except Exception as e:
                    message = str(e)
                    return {"content": [{"type": "text", "text": message}], "isError": True}
            return handler

        mcp_tool = SdkMcpTool(
            name=name,
            description=description or f"EdgeOne platform tool: {name}",
            input_schema=input_schema,
            handler=_make_handler(execute, item),
        )
        mcp_tools.append(mcp_tool)
        logger.log(f"[tools] registered platform tool: {name}")

    allowed_tools = [f"mcp__{MCP_SERVER_NAME}__{t.name}" for t in mcp_tools]
    return mcp_tools, allowed_tools


def build_agent_options(
    session_store=None,
    mcp_server=None,
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
        opts.mcp_servers = {MCP_SERVER_NAME: mcp_server}
    return opts


def sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def handler(ctx: Any) -> AsyncGenerator[str, None]:
    """EdgeOne Pages Functions 入口（async generator 流式版本）。"""
    cid = getattr(ctx, "conversation_id", None) or ""
    logger.log(f"[debug] cid: {cid}")

    body = ctx.request.body
    user_message: str = body.get("message", "") if isinstance(body, dict) else ""
    if not user_message.strip():
        yield sse_event("error", {"message": "'message' is required"})
        yield sse_event("done", {"stopped": False})
        return

    if not _SDK_AVAILABLE:
        yield sse_event("error", {"message": "claude_agent_sdk 未安装，请检查 requirements.txt"})
        yield sse_event("done", {"stopped": False})
        return

    # 获取平台 cancel signal（asyncio.Event），当 /stop 被调用时会被 set
    cancel_signal = getattr(ctx.request, "signal", None) or asyncio.Event()

    # 获取 store 用于持久化对话
    store_adapter = getattr(ctx, "store", None)

    # 暂时关闭 Claude session 机制，方便调试其他功能
    session_store = None
    # if store_adapter is not None and hasattr(store_adapter, "claude_session_store"):
    #     session_store = store_adapter.claude_session_store()

    # 保存 user message 到 store
    if store_adapter and cid:
        try:
            await store_adapter.append_message(cid, "user", user_message)
        except Exception as e:
            logger.error(f"[store] failed to save user message: {e}")

    # 构建 EdgeOne 平台工具 → Claude Agent SDK MCP server
    mcp_tools, allowed_tools = build_edgeone_mcp_tools(ctx)
    mcp_server = create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        tools=mcp_tools,
    )

    options = build_agent_options(
        session_store=session_store,
        mcp_server=mcp_server,
        allowed_tools=allowed_tools,
    )

    stopped = False
    full_assistant_text = ""
    sent_text_len_by_block: dict[int, int] = {}

    try:
        # 使用 query() API（对应 Node 版的 query({ prompt, options })）
        q = query(prompt=user_message, options=options)

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
                    logger.log(f"[stream] StreamEvent type={event_type}")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                full_assistant_text += text
                                yield sse_event("text_delta", {"delta": text})

                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            raw_name = block.get("name", "")
                            tool_name = _extract_tool_name(raw_name)
                            if tool_name:
                                logger.log(f"[stream] tool_called: {tool_name}")
                                yield sse_event("tool_called", {"tool": tool_name})

                # ── 处理 AssistantMessage（累积的完整/部分消息）──
                # 作为兜底：如果 StreamEvent 未正常工作，从 AssistantMessage 提取增量
                elif isinstance(msg, AssistantMessage):
                    content = getattr(msg, "content", None)

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
                        logger.error(f"[error] SDK error={error}, text={err_text}")
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
                                if tool_name:
                                    logger.log(f"[stream] tool_called: {tool_name}")
                                    yield sse_event("tool_called", {"tool": tool_name})

                elif isinstance(msg, ResultMessage):
                    logger.log("[stream] ResultMessage received, ending stream")
                    break

                else:
                    # 其他消息类型（如 RateLimitEvent），记录但不处理
                    logger.log(f"[stream] unhandled message type: {type(msg).__name__}")

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
