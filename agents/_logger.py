"""
Shared logger factory — private module (starts with _), not mapped as a route.

工具调用的 debug 信息通过 [tool_debug] 前缀标记，
外部 dev:agents:log 脚本会过滤这些行写入 log/tool_debug.md。
"""

import sys
from datetime import datetime, timezone


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
            """输出带 [tool_debug] 标记的日志行，供外部脚本过滤写入文件。

            Args:
                category: 分类标签，如 "unknown_block", "tool_error", "sdk_error",
                          "tool_start", "tool_use", "tool_result"
                message: 详细信息（换行会被替换为 \\n 以保证单行输出）
            """
            ts = _Logger._ts()
            # 确保单行输出，方便 grep 过滤
            safe_msg = message.replace("\n", "\\n")
            print(f"[{tag}][{ts}] [tool_debug][{category}] {safe_msg}", flush=True)

    return _Logger()
