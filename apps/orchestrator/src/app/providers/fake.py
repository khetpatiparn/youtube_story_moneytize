from __future__ import annotations

from typing import Any

from app.providers.base import AudioResult, GeneratedImage, LLMResult
from app.providers.contracts import stable_prompt_hash


class FakeLLMProvider:
    provider = "fake-llm"
    model = "fake-llm-model"

    async def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        options: dict[str, Any],
    ) -> LLMResult:
        return LLMResult(
            provider=self.provider,
            model=self.model,
            prompt_hash=stable_prompt_hash(self.model, prompt, options),
            output={"status": "ok", "schema_required": schema.get("required", [])},
            raw_text='{"status": "ok"}',
            usage={"prompt_tokens": len(prompt.split()), "completion_tokens": 2},
        )


class FakeImageProvider:
    provider = "fake-image"
    model = "fake-image-model"

    async def generate(
        self,
        prompt: str,
        seed: int | None,
        options: dict[str, Any],
    ) -> GeneratedImage:
        hash_options = dict(options)
        hash_options["seed"] = seed
        prompt_hash = stable_prompt_hash(self.model, prompt, hash_options)
        return GeneratedImage(
            provider=self.provider,
            model=self.model,
            prompt_hash=prompt_hash,
            prompt=prompt,
            seed=seed,
            status="completed",
            output_path=f"projects/project_001/images/{prompt_hash[:12]}.png",
            mime_type="image/png",
        )


class FakeTTSProvider:
    provider = "fake-tts"
    model = "fake-tts-model"

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        options: dict[str, Any],
    ) -> AudioResult:
        del options
        return AudioResult(
            provider=self.provider,
            model=self.model,
            voice_id=voice_id,
            output_path=output_path,
            duration_seconds=max(len(text.split()) / 2.5, 0.1),
            status="completed",
        )
