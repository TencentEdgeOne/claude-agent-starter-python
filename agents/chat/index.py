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
     通过 ctx.tools.to_claude_mcp_server() 直接桥接到 Claude SDK。
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
        ClaudeAgentOptions,
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


def _safe_json_preview(value: Any, max_length: int = 800) -> str:
    """将值转为 JSON 字符串预览，超长截断"""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
        if not text:
            return str(value)
        return f"{text[:max_length]}...<truncated>" if len(text) > max_length else text
    except (TypeError, ValueError):
        return str(value)


def build_agent_options(
    session_store=None,
    mcp_servers: list | None = None,
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
    if mcp_servers is not None:
        opts.mcp_servers = mcp_servers
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

    if store_adapter is not None and hasattr(store_adapter, "claude_session_store"):
        session_store = store_adapter.claude_session_store()

    # 保存 user message 到 store
    if store_adapter and cid:
        try:
            await store_adapter.append_message(cid, "user", user_message)
        except Exception as e:
            logger.error(f"[store] failed to save user message: {e}")

    # 通过平台提供的 to_claude_mcp_server() 直接获取 MCP 工具配置
    # 对应 TypeScript 版的 context.tools.toClaudeMcpServer()
    platform_tools = getattr(ctx, "tools", None)
    if platform_tools is None or not hasattr(platform_tools, "to_claude_mcp_server"):
        yield sse_event("error", {"message": "ctx.tools.to_claude_mcp_server is unavailable. Please upgrade the EdgeOne Pages agent runtime."})
        yield sse_event("done", {"stopped": False})
        return

    edgeone_mcp = platform_tools.to_claude_mcp_server()

    mcp_servers = [
        create_sdk_mcp_server(
            name=edgeone_mcp.name,
            tools=edgeone_mcp.tools,
        )
    ]

    allowed_tools = edgeone_mcp.allowed_tools
    logger.log(f"[tools] registered EdgeOne MCP tools: {allowed_tools}")

    options = build_agent_options(
        session_store=session_store,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
    )

    stopped = False
    full_assistant_text = ""
    sent_text_len_by_block: dict[int, int] = {}
    last_msg_type = ""

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

                # 获取消息类型（兼容 dict 和对象）
                msg_type = msg.get("type", "") if isinstance(msg, dict) else getattr(msg, "type", "")

                # 检测到新一轮 assistant 消息：如果上一条是 user（tool_result），清空计数器
                if msg_type == "assistant" and last_msg_type == "user":
                    sent_text_len_by_block.clear()
                last_msg_type = msg_type

                # ── 拦截 tool_result 中的 base64Image，作为 image 事件推送给前端 ──
                if msg_type == "user":
                    try:
                        msg_obj = msg if isinstance(msg, dict) else msg.__dict__ if hasattr(msg, "__dict__") else {}
                        tool_results = msg_obj.get("tool_use_result") or (msg_obj.get("message", {}) or {}).get("content", [])
                        result_arr = tool_results if isinstance(tool_results, list) else [tool_results]
                        for item in result_arr:
                            text = item if isinstance(item, str) else (
                                item.get("text", "") if isinstance(item, dict) else
                                getattr(item, "text", getattr(item, "content", ""))
                            )
                            if isinstance(text, str) and "base64Image" in text:
                                try:
                                    parsed = json.loads(text)
                                    if parsed.get("base64Image"):
                                        logger.log(f"[image] extracted base64Image from tool_result, size: {len(parsed['base64Image'])}")
                                        yield sse_event("image", {"base64": parsed["base64Image"]})
                                except (json.JSONDecodeError, TypeError):
                                    pass
                    except Exception as e:
                        logger.error(f"[image] failed to extract base64Image: {e}")

                # ── 调试：推送非 assistant/result 消息类型让前端可观测 ──
                if msg_type not in ("assistant", "result"):
                    yield sse_event("debug_msg", {
                        "msgType": msg_type,
                        "preview": _safe_json_preview(msg, 4000),
                    })

                # ── 处理 assistant 消息 ──
                if msg_type == "assistant":
                    # 获取 content blocks（兼容 dict 和对象）
                    if isinstance(msg, dict):
                        blocks = (msg.get("message") or {}).get("content", [])
                    else:
                        message_obj = getattr(msg, "message", None)
                        blocks = getattr(message_obj, "content", None) if message_obj else getattr(msg, "content", None)
                        if blocks is None:
                            blocks = []

                    for idx, block in enumerate(blocks):
                        block_type = block.get("type", "") if isinstance(block, dict) else getattr(block, "type", "")

                        if block_type == "text":
                            full_text = (block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")) or ""
                            already_sent = sent_text_len_by_block.get(idx, 0)
                            if len(full_text) > already_sent:
                                delta = full_text[already_sent:]
                                sent_text_len_by_block[idx] = len(full_text)
                                full_assistant_text = full_text
                                yield sse_event("text_delta", {"delta": delta})

                        elif block_type == "tool_use":
                            raw_tool_name = (block.get("name", "") if isinstance(block, dict) else getattr(block, "name", "")) or ""
                            tool_name = _extract_tool_name(raw_tool_name)
                            tool_id = block.get("id") if isinstance(block, dict) else getattr(block, "id", None)
                            tool_input = block.get("input") if isinstance(block, dict) else getattr(block, "input", None)

                            logger.log(f"[tools] call requested cid={cid} tool={tool_name} raw={raw_tool_name} toolId={tool_id} inputPreview={_safe_json_preview(tool_input)}")
                            yield sse_event("tool_called", {"tool": tool_name})

                        else:
                            # 其他类型 block（如 image）：以 debug_block 事件原样推送给前端
                            yield sse_event("debug_block", {
                                "blockIndex": idx,
                                "blockType": block_type,
                                "block": _safe_json_preview(block, 4000),
                            })

                elif msg_type == "result":
                    logger.log("[stream] result message received, ending stream")
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
