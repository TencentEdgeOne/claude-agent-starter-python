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
