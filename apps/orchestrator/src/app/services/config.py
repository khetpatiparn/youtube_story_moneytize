from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path

from app.providers.base import ImageProvider, PermanentProviderError, TTSProvider
from app.providers.cloudflare_image import (
    DEFAULT_MODEL,
    CloudflareImageProvider,
    CloudflareRESTImageClient,
    _parse_model,
)
from app.providers.gemini_tts import GeminiTTSProvider, GoogleGenAISpeechClient
from app.providers.local import LocalImageProvider, LocalTTSProvider
from app.services.artifacts import ArtifactStore


def load_environment(repository_root: str | Path) -> None:
    env_path = Path(repository_root) / ".env"
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        _load_simple_env(env_path)
    else:
        load_dotenv(env_path, override=False)


def _load_simple_env(path: Path) -> None:
    """Dependency-free fallback for restricted test sandboxes."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name and name not in os.environ:
            os.environ[name] = value.strip().strip("'\"")


def build_image_provider(store: ArtifactStore, environ: Mapping[str, str]) -> ImageProvider:
    provider_name = environ.get("IMAGE_PROVIDER", "local").strip().lower()
    if provider_name == "local":
        return LocalImageProvider(store)
    if provider_name != "cloudflare":
        raise ValueError("IMAGE_PROVIDER must be 'local' or 'cloudflare'")

    account_id = environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    model = environ.get("CLOUDFLARE_IMAGE_MODEL", DEFAULT_MODEL).strip()
    if not account_id:
        raise PermanentProviderError(
            "CLOUDFLARE_ACCOUNT_ID is required for Cloudflare images"
        )
    if not api_token:
        raise PermanentProviderError(
            "CLOUDFLARE_API_TOKEN is required for Cloudflare images"
        )
    if not model:
        raise ValueError("CLOUDFLARE_IMAGE_MODEL must not be empty")
    try:
        _parse_model(model)
    except ValueError as error:
        raise ValueError(
            "CLOUDFLARE_IMAGE_MODEL must use canonical Cloudflare syntax"
        ) from error
    try:
        steps = int(environ.get("CLOUDFLARE_IMAGE_STEPS", "4"))
    except ValueError as error:
        raise ValueError("CLOUDFLARE_IMAGE_STEPS must be an integer") from error
    if not 1 <= steps <= 8:
        raise ValueError("CLOUDFLARE_IMAGE_STEPS must be between 1 and 8")

    client = CloudflareRESTImageClient(account_id, api_token)
    return CloudflareImageProvider(store, client=client, model=model, steps=steps)


def build_tts_provider(store: ArtifactStore, environ: Mapping[str, str]) -> TTSProvider:
    provider_name = environ.get("TTS_PROVIDER", "local").strip().lower()
    if provider_name == "local":
        return LocalTTSProvider(store)
    if provider_name != "google":
        raise ValueError("TTS_PROVIDER must be 'local' or 'google'")

    api_key = environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise PermanentProviderError("GEMINI_API_KEY is required for Google TTS")
    model = environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview").strip()
    voice = environ.get("GEMINI_TTS_VOICE", "Charon").strip()
    try:
        max_attempts = int(environ.get("GEMINI_TTS_MAX_ATTEMPTS", "3"))
    except ValueError as error:
        raise ValueError("GEMINI_TTS_MAX_ATTEMPTS must be an integer") from error
    if not model or not voice:
        raise ValueError("Gemini TTS model and voice must not be empty")
    client = GoogleGenAISpeechClient(api_key)
    return GeminiTTSProvider(
        store,
        api_key=api_key,
        model=model,
        voice=voice,
        max_attempts=max_attempts,
        client=client,
    )
