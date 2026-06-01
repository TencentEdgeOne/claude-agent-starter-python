"""
Shared logger factory — private module (starts with _), not mapped as a route.
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

    return _Logger()
