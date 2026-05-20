"""
私有模块（文件名以 _ 开头）—— 不被 EdgeOne 映射为公开路由。
用于配置 Claude 模型选项。

被 ./index.py 通过 `from ._model import resolve_model_name, collect_gateway_env` 导入。
"""

# ==========================================
# 原通用配置逻辑先保留注释，当前调试版本固定走 AI Gateway。
#
# import os
# from dotenv import load_dotenv
#
# load_dotenv()
#
# CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
#
#
# def collect_gateway_env() -> dict[str, str]:
#     """
#     根据 ACTIVE_PROVIDER 收集传给 Claude Agent SDK 子进程的环境变量。
#
#     两种 provider：
#       ai_gate            — 走 AI 网关（网关必须兼容 Anthropic Messages API
#                            且后端配了真实 Anthropic upstream）
#       anthropic_official — 官方 Anthropic 直连（默认）
#     """
#     provider = os.environ.get("ACTIVE_PROVIDER", "anthropic_official")
#
#     if provider == "ai_gate":
#         base_url = os.environ.get("AI_GATE_BASE_URL", "")
#         api_key = os.environ.get("AI_GATE_API_KEY", "")
#     else:  # anthropic_official
#         base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
#         api_key = os.environ.get("ANTHROPIC_API_KEY", "")
#
#     env: dict[str, str] = {}
#     if base_url:
#         env["ANTHROPIC_BASE_URL"] = base_url
#     if api_key:
#         env["ANTHROPIC_API_KEY"] = api_key
#     if os.environ.get("ANTHROPIC_CUSTOM_HEADERS"):
#         env["ANTHROPIC_CUSTOM_HEADERS"] = os.environ["ANTHROPIC_CUSTOM_HEADERS"]
#
#     # 覆盖 Claude Code CLI 内部子调用使用的"小模型"。
#     small_model = (
#         os.environ.get("AI_GATE_SMALL_MODEL")
#         or os.environ.get("ANTHROPIC_SMALL_FAST_MODEL")
#     )
#     if provider == "ai_gate" and not small_model:
#         small_model = "anthropic/claude-haiku-4-5"
#     if small_model:
#         env["ANTHROPIC_SMALL_FAST_MODEL"] = small_model
#
#     return env
#
#
# def resolve_model_name() -> str:
#     """根据 ACTIVE_PROVIDER 返回最终使用的模型名。"""
#     provider = os.environ.get("ACTIVE_PROVIDER", "anthropic_official")
#     if provider == "ai_gate":
#         return os.environ.get("AI_GATE_MODEL") or CLAUDE_MODEL
#     return CLAUDE_MODEL
# ==========================================

"""
AI Gateway 调试版配置。

Claude Agent SDK 子进程仍读取 Anthropic 协议环境变量，
所以这里把 AI_GATE_* 映射成 ANTHROPIC_* 传给 SDK。
"""

import os
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or os.environ.get("AI_GATEWAY_MODEL") or "@Pages/hy3-preview"


def collect_gateway_env() -> dict[str, str]:
    env: dict[str, str] = {}
    base_url = os.environ.get("AI_GATEWAY_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL", "")
    api_key = os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    small_model = os.environ.get("AI_GATEWAY_SMALL_MODEL") or os.environ.get("ANTHROPIC_SMALL_FAST_MODEL", "")

    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    if small_model:
        env["ANTHROPIC_SMALL_FAST_MODEL"] = small_model
    if os.environ.get("ANTHROPIC_CUSTOM_HEADERS"):
        env["ANTHROPIC_CUSTOM_HEADERS"] = os.environ["ANTHROPIC_CUSTOM_HEADERS"]

    return env


def resolve_model_name() -> str:
    return CLAUDE_MODEL
