"""
Shared base64 redaction utilities for backend history responses.
"""

import re

# Matches a JSON "base64Image":"<long base64 string>" field.
BASE64_IMAGE_REGEX = re.compile(r'"base64Image"\s*:\s*"[A-Za-z0-9+/=]{100,}"')

# Placeholder used when base64Image is stripped from session/history context.
IMAGE_PLACEHOLDER = "[screenshot image saved to client]"


def redact_base64_in_text(text: str, placeholder: str = IMAGE_PLACEHOLDER) -> str:
    """Redact base64Image in a plain string (regex replacement)."""
    if not isinstance(text, str):
        return text
    if "base64Image" not in text:
        return text
    return BASE64_IMAGE_REGEX.sub(f'"base64Image":"{placeholder}"', text)
