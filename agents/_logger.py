"""
Shared logger factory — private module (starts with _), not mapped as a route.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# log 目录位于项目根目录下的 log/
_LOG_DIR = Path(__file__).resolve().parent.parent / "log"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# 工具调用异常的 debug 日志文件
_TOOL_DEBUG_FILE = _LOG_DIR / "tool_debug.md"


def _ensure_tool_debug_header():
    """确保 tool_debug.md 文件有 markdown 标题头。"""
    if not _TOOL_DEBUG_FILE.exists() or _TOOL_DEBUG_FILE.stat().st_size == 0:
        with open(_TOOL_DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write("# Tool Call Debug Log\n\n")
            f.write("> 仅记录工具调用相关的异常/警告信息，方便排查问题。\n\n")
            f.write("---\n\n")


_ensure_tool_debug_header()


def create_logger(tag: str):
    """Create a logger with the given tag prefix."""

    class _Logger:
        @staticmethod
        def _ts() -> str:
            return datetime.now(timezone.utc).isoformat()

        @staticmethod
        def log(*args: object) -> None:
            print(f"[{tag}][{_Logger._ts()}]", *args, flush=True)

        @staticmethod
        def error(*args: object) -> None:
            print(f"[{tag}][{_Logger._ts()}]", *args, file=sys.stderr, flush=True)

        @staticmethod
        def tool_debug(category: str, message: str) -> None:
            """将工具调用异常的 debug 信息写入 log/tool_debug.md。

            Args:
                category: 分类标签，如 "unknown_block", "tool_error", "sdk_error",
                          "tool_start", "tool_use", "tool_result"
                message: 详细信息
            """
            ts = _Logger._ts()
            # 新请求用醒目的分隔线
            if "new_request" in category:
                entry = (
                    f"\n---\n\n"
                    f"# 🔄 新请求 `{ts}`\n"
                    f"```\n{message}\n```\n\n"
                )
            else:
                entry = (
                    f"## `[{tag}]` {category}\n"
                    f"- **时间**: `{ts}`\n"
                    f"- **详情**:\n"
                    f"```\n{message}\n```\n\n"
                )
            with open(_TOOL_DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            # 同时在控制台输出（保留原有行为）
            print(f"[{tag}][{ts}] [tool_debug][{category}] {message}", flush=True)

    return _Logger()
