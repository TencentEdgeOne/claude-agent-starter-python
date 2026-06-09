import os
from dotenv import load_dotenv

load_dotenv()

# ========== Fix SSL for the entire process ==========
# Use truststore so Python reads from the system certificate store directly
# (macOS Keychain / Windows Certificate Store). Fixes sandbox tool calls
# failing on local macOS dev when SSL_CERT_FILE doesn't take effect.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or os.environ.get("AI_GATEWAY_MODEL") or "@makers/deepseek-v4-flash"


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
