from __future__ import annotations

import asyncio
import io
import re
import wave
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.providers.base import (
    AudioResult,
    PermanentProviderError,
    RetryableProviderError,
)
from app.services.artifacts import ArtifactStore


class GeminiSpeechClient(Protocol):
    async def generate_pcm(self, *, model: str, prompt: str, voice: str) -> bytes:
        ...


class GoogleGenAISpeechClient:
    """Small adapter around the official Google Gen AI SDK."""

    def __init__(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    async def generate_pcm(self, *, model: str, prompt: str, voice: str) -> bytes:
        try:
            response = await asyncio.to_thread(self._generate, model, prompt, voice)
            parts = response.candidates[0].content.parts
            data = next(
                part.inline_data.data
                for part in parts
                if getattr(part, "inline_data", None) is not None
                and getattr(part.inline_data, "data", None)
            )
            return bytes(data)
        except (IndexError, StopIteration, TypeError, AttributeError) as error:
            raise RetryableProviderError("Gemini returned no audio") from error
        except (RetryableProviderError, PermanentProviderError):
            raise
        except Exception as error:
            status = getattr(error, "status_code", None) or getattr(error, "code", None)
            if status in {429, 500, 502, 503, 504}:
                raise RetryableProviderError("Gemini TTS request temporarily failed") from error
            raise PermanentProviderError("Gemini TTS request was rejected") from error

    def _generate(self, model: str, prompt: str, voice: str) -> Any:
        from google.genai import types

        return self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
            ),
        )


class GeminiTTSProvider:
    provider = "google"
    sample_rate = 24000

    def __init__(
        self,
        store: ArtifactStore,
        api_key: str,
        model: str = "gemini-3.1-flash-tts-preview",
        voice: str = "Charon",
        max_attempts: int = 3,
        client: GeminiSpeechClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        chunk_character_limit: int = 1800,
    ) -> None:
        if not api_key.strip():
            raise PermanentProviderError("Gemini API key is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if chunk_character_limit < 1:
            raise ValueError("chunk_character_limit must be positive")
        self.store = store
        self.model = model
        self.voice = voice
        self.max_attempts = max_attempts
        self.client = client or GoogleGenAISpeechClient(api_key)
        self.sleep = sleep
        self.chunk_character_limit = chunk_character_limit

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        options: dict[str, Any],
    ) -> AudioResult:
        del options
        chunks = self._chunks(text)
        if not chunks:
            raise PermanentProviderError("Narration text is required")
        del voice_id
        voice = self.voice
        pcm_parts = [await self._generate_chunk(chunk, voice) for chunk in chunks]
        pcm = b"".join(pcm_parts)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(self.sample_rate)
            audio.writeframes(pcm)
        relative_path = self.store.publish_bytes_set({output_path: buffer.getvalue()})[output_path]
        return AudioResult(
            provider=self.provider,
            model=self.model,
            voice_id=voice,
            output_path=relative_path,
            duration_seconds=(len(pcm) // 2) / self.sample_rate,
            status="completed",
        )

    async def _generate_chunk(self, chunk: str, voice: str) -> bytes:
        prompt = (
            "อ่านออกเสียงภาษาไทยอย่างเป็นธรรมชาติในสไตล์ผู้เล่าเรื่อง "
            "เว้นจังหวะชัดเจนและรักษาข้อความเดิมทุกคำ\nข้อความ:\n" + chunk
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                pcm = await self.client.generate_pcm(model=self.model, prompt=prompt, voice=voice)
                if not pcm or len(pcm) % 2:
                    raise PermanentProviderError("Gemini returned invalid PCM audio")
                return pcm
            except RetryableProviderError as error:
                if attempt == self.max_attempts:
                    raise RetryableProviderError(
                        f"Gemini TTS failed after {self.max_attempts} attempts"
                    ) from error
                await self.sleep(min(2 ** (attempt - 1), 8))
            except PermanentProviderError as error:
                raise PermanentProviderError("Gemini TTS request failed permanently") from error
            except Exception as error:
                raise PermanentProviderError("Gemini TTS request failed permanently") from error
        raise AssertionError("unreachable")

    def _chunks(self, text: str) -> list[str]:
        chunks: list[str] = []
        for paragraph in re.split(r"(?:\r?\n){2,}", text):
            if not paragraph.strip():
                continue
            remaining = paragraph.strip()
            while len(remaining) > self.chunk_character_limit:
                boundary = self._boundary(remaining, self.chunk_character_limit)
                chunks.append(remaining[:boundary])
                remaining = remaining[boundary:]
            if remaining:
                chunks.append(remaining)
        return chunks

    @staticmethod
    def _boundary(text: str, limit: int) -> int:
        candidates = [text.rfind(mark, 0, limit + 1) for mark in (" ", "。", ".", "!", "?", "ฯ")]
        boundary = max(candidates)
        return boundary + 1 if boundary >= 0 else limit
