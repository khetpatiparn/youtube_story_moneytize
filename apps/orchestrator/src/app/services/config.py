from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path

from app.providers.base import PermanentProviderError, TTSProvider
from app.providers.gemini_tts import GeminiTTSProvider, GoogleGenAISpeechClient
from app.providers.local import LocalTTSProvider
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
