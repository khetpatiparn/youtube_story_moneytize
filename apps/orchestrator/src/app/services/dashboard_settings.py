from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.secret_store import SecretProtector

SECRET_FIELDS = {
    "gemini_api_key",
    "cloudflare_account_id",
    "cloudflare_api_token",
}
PUBLIC_SECRET_FIELDS = tuple(sorted(SECRET_FIELDS))
ALLOWED_FIELDS = SECRET_FIELDS | {
    "story_provider",
    "image_provider",
    "projects_dir",
    "image_retry_limit",
}
ALLOWED_STORY_PROVIDERS = {"local", "gemini"}
ALLOWED_IMAGE_PROVIDERS = {"local", "cloudflare"}


class DashboardSettingsService:
    def __init__(self, path: Path, protector: SecretProtector) -> None:
        self.path = Path(path)
        self.protector = protector

    def public_settings(self) -> dict[str, object]:
        raw = self._load_raw()
        public: dict[str, object] = {
            "story_provider": raw.get("story_provider", "local"),
            "image_provider": raw.get("image_provider", "local"),
            "projects_dir": raw.get("projects_dir"),
            "image_retry_limit": raw.get("image_retry_limit", 3),
        }
        for field in PUBLIC_SECRET_FIELDS:
            public[field] = self._public_secret(raw.get(field))
        return public

    def update(self, changes: dict[str, object]) -> dict[str, object]:
        if not isinstance(changes, dict):
            raise ValueError("settings payload must be an object")
        current = self._load_raw()
        for key, value in changes.items():
            if key not in ALLOWED_FIELDS:
                raise ValueError(f"unknown settings field: {key}")
            if key in SECRET_FIELDS:
                self._update_secret(current, key, value)
            elif key == "story_provider":
                current[key] = _normalize_choice(key, value, ALLOWED_STORY_PROVIDERS)
            elif key == "image_provider":
                current[key] = _normalize_choice(key, value, ALLOWED_IMAGE_PROVIDERS)
            elif key == "projects_dir":
                current[key] = _normalize_projects_dir(value)
            elif key == "image_retry_limit":
                current[key] = _normalize_retry_limit(value)
        self._atomic_write(current)
        return self.public_settings()

    def _update_secret(self, current: dict[str, object], key: str, value: object) -> None:
        if value is None:
            current.pop(key, None)
            return
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string or null")
        current[key] = self.protector.protect(value.strip())

    def _load_raw(self) -> dict[str, object]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as error:
            raise ValueError("settings file is not valid JSON") from error
        if not isinstance(data, dict):
            raise ValueError("settings file must contain a JSON object")
        return data

    def _atomic_write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def _public_secret(self, protected_value: object) -> dict[str, object]:
        if not isinstance(protected_value, str) or not protected_value:
            return {"configured": False, "suffix": None}
        plaintext = self.protector.unprotect(protected_value)
        return {
            "configured": True,
            "suffix": plaintext[-4:] if plaintext else None,
        }


def _normalize_choice(name: str, value: object, allowed: set[str]) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {allowed_list}")
    return normalized


def _normalize_projects_dir(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("projects_dir must be a non-empty string")
    return value.strip()


def _normalize_retry_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("image_retry_limit must be an integer")
    if not 1 <= value <= 5:
        raise ValueError("image_retry_limit must be between 1 and 5")
    return value
