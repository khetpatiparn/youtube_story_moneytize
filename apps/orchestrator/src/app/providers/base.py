from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderError(Exception):
    """Base error raised by provider adapters."""


class RetryableProviderError(ProviderError):
    """Provider error that may succeed if retried later."""


class PermanentProviderError(ProviderError):
    """Provider error that should not be retried without changed input."""


@dataclass(frozen=True)
class LLMResult:
    provider: str
    model: str
    prompt_hash: str
    output: dict[str, Any]
    raw_text: str
    usage: dict[str, int]


@dataclass(frozen=True)
class GeneratedImage:
    provider: str
    model: str
    prompt_hash: str
    prompt: str
    seed: int | None
    status: str
    output_path: str
    mime_type: str
    cached: bool = False


@dataclass(frozen=True)
class AudioResult:
    provider: str
    model: str
    voice_id: str
    output_path: str
    duration_seconds: float
    status: str


class LLMProvider(Protocol):
    provider: str
    model: str

    async def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        options: dict[str, Any],
    ) -> LLMResult:
        ...


class ImageProvider(Protocol):
    provider: str
    model: str

    async def generate(
        self,
        prompt: str,
        seed: int | None,
        options: dict[str, Any],
    ) -> GeneratedImage:
        ...


class TTSProvider(Protocol):
    provider: str
    model: str

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        options: dict[str, Any],
    ) -> AudioResult:
        ...
