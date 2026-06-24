from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.providers.base import (
    AudioResult,
    GeneratedImage,
    ImageProvider,
    LLMProvider,
    LLMResult,
    TTSProvider,
)


def stable_prompt_hash(model: str, prompt: str, options: dict[str, Any]) -> str:
    payload = {
        "model": model,
        "options": options,
        "prompt": _normalize_prompt(prompt),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def assert_llm_provider_contract(provider: LLMProvider) -> LLMResult:
    prompt = "Write a structured outline"
    options = {"temperature": 0, "max_tokens": 64}
    schema = {"type": "object", "required": ["status"]}

    result = await provider.generate_structured(prompt, schema, options)

    _require(result.provider, "LLM result provider is required")
    _require(result.model, "LLM result model is required")
    _require(result.prompt_hash == stable_prompt_hash(result.model, prompt, options), "LLM prompt_hash mismatch")
    _require(isinstance(result.output, dict), "LLM output must be a dict")
    _require("status" in result.output, "LLM output must include status")
    _require(isinstance(result.raw_text, str), "LLM raw_text must be text")
    _require(result.usage.get("prompt_tokens", 0) > 0, "LLM usage prompt_tokens must be positive")
    return result


async def assert_image_provider_contract(provider: ImageProvider) -> GeneratedImage:
    prompt = "generate a village scene"
    seed = 42
    options = {"style": "simple", "size": "1024x1024"}

    result = await provider.generate(prompt, seed, options)

    _require(result.provider, "Image result provider is required")
    _require(result.model, "Image result model is required")
    _require(result.prompt_hash == stable_prompt_hash(result.model, prompt, options | {"seed": seed}), "Image prompt_hash mismatch")
    _require(result.prompt == prompt, "Image result must retain original prompt")
    _require(result.seed == seed, "Image result must retain seed")
    _require(result.status in {"completed", "cached"}, "Image status must be completed or cached")
    _require(result.output_path, "Image output_path is required")
    _require(result.mime_type.startswith("image/"), "Image mime_type must be image/*")
    return result


async def assert_tts_provider_contract(provider: TTSProvider) -> AudioResult:
    text = "A calm narrator starts the story."
    voice_id = "narrator-th"
    output_path = "projects/project_001/audio/narration.wav"
    options = {"format": "wav"}

    result = await provider.synthesize(text, voice_id, output_path, options)

    _require(result.provider, "TTS result provider is required")
    _require(result.model, "TTS result model is required")
    _require(result.voice_id == voice_id, "TTS result must retain voice_id")
    _require(result.output_path == output_path, "TTS result must retain output_path")
    _require(result.duration_seconds > 0, "TTS duration_seconds must be positive")
    _require(result.status == "completed", "TTS status must be completed")
    return result


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt).strip()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
