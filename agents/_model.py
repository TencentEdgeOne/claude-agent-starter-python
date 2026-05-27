import os
from dotenv import load_dotenv

load_dotenv()

# ========== Fix SSL for the entire process ==========
# 使用 truststore 让 Python 直接使用系统证书库（macOS Keychain / Windows Certificate Store），
# 解决 macOS 本地开发时 SSL_CERT_FILE 无效导致 sandbox 工具调用失败的问题。
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or os.environ.get("AI_GATEWAY_MODEL") or "@makers/hy3-preview"


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
