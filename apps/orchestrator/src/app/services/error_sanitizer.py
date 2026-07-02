from __future__ import annotations


def sanitize_error(error: Exception, secrets: list[str]) -> tuple[str, str]:
    message = str(error) or error.__class__.__name__
    sanitized = message
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "[redacted]")
    return _error_code_for(error), sanitized


def _error_code_for(error: Exception) -> str:
    name = error.__class__.__name__
    if name.endswith("Error"):
        root = name[:-5]
        return f"{_snake_case(root)}_error" if root else "error"
    if name.endswith("Exception"):
        root = name[:-9]
        return _snake_case(root) or "exception"
    return _snake_case(name) or "error"


def _snake_case(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)
