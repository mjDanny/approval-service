import re
from typing import Any


SENSITIVE_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "credential",
    "email",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
    "storage_key",
    "storagekey",
    "signed_url",
    "signedurl",
    "provider_url",
    "providerurl",
    "raw_provider_payload",
)

EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
URL_RE = re.compile(r"https?://[^\s]+")
BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_text(value: str) -> str:
    """Keep public responses and events from leaking common secrets or provider URLs."""
    redacted = EMAIL_RE.sub("[redacted-email]", value)
    redacted = URL_RE.sub("[redacted-url]", redacted)
    redacted = BEARER_RE.sub("Bearer [redacted-token]", redacted)
    return redacted


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            sanitized[key] = "[redacted]" if is_sensitive_key(str(key)) else sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return redact_text(stripped) if stripped else None


def clean_required_text(value: str) -> str:
    return redact_text(value.strip())

