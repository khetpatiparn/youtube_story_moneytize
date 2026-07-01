from __future__ import annotations

import hashlib
import html
import io
import math
import re
import struct
import wave
from typing import Any

from app.providers.base import AudioResult
from app.services.artifacts import ArtifactStore


class LocalLLMProvider:
    provider = "local"
    model = "deterministic-story-v1"

    def generate_story(
        self,
        topic: str,
        duration_seconds: int,
        language: str,
        profile: str,
        script_version: int,
    ) -> dict[str, Any]:
        normalized_topic = re.sub(r"\s+", " ", topic).strip()
        scene_count = max(3, min(8, round(duration_seconds / 10)))
        scenes = []
        for index in range(1, scene_count + 1):
            title = f"{normalized_topic} - Beat {index}"
            narration = (
                f"{normalized_topic}: scene {index} of {scene_count} "
                f"in {language}, styled as {profile}, script version {script_version}."
            )
            scenes.append(
                {
                    "scene_id": f"scene_{index:03d}",
                    "title": title,
                    "narration": narration,
                    "prompt": f"{title}; {profile}; {language}; version {script_version}",
                    "motion": "slow_push",
                    "focal_point": [0.5, 0.5],
                }
            )

        return {
            "outline": {
                "title": normalized_topic,
                "beats": [scene["title"] for scene in scenes],
            },
            "script": "\n\n".join(scene["narration"] for scene in scenes),
            "scenes": scenes,
        }


class LocalImageProvider:
    provider = "local"
    model = "deterministic-svg-v1"
    output_extension = "svg"

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    def generate(self, scene: dict[str, Any], output_path: str) -> dict[str, Any]:
        scene_id = str(scene["scene_id"])
        prompt = str(scene["prompt"])
        digest = hashlib.sha256(f"{scene_id}{prompt}".encode("utf-8", errors="surrogatepass")).hexdigest()
        background = f"#{digest[:6]}"
        accent = f"#{digest[6:12]}"
        escaped_id = html.escape(_xml_text(scene_id))
        escaped_title = html.escape(_xml_text(str(scene["title"])))
        escaped_prompt = html.escape(_xml_text(prompt))
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">\n'
            f'  <rect width="1280" height="720" fill="{background}"/>\n'
            f'  <circle cx="1080" cy="160" r="220" fill="{accent}" opacity="0.75"/>\n'
            '  <g fill="#ffffff" font-family="Arial, sans-serif">\n'
            f'    <text x="80" y="110" font-size="28">{escaped_id}</text>\n'
            f'    <text x="80" y="300" font-size="54">{escaped_title}</text>\n'
            f'    <text x="80" y="390" font-size="26">{escaped_prompt}</text>\n'
            '  </g>\n'
            '</svg>\n'
        )
        relative_path = self.store.write_text(output_path, svg)
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_hash": digest,
            "output_path": relative_path,
            "mime_type": "image/svg+xml",
        }


class LocalTTSProvider:
    provider = "local"
    model = "deterministic-tone-v1"
    sample_rate = 22050

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        options: dict[str, Any],
    ) -> AudioResult:
        return self.synthesize_sync(text, voice_id, output_path, options)

    def synthesize_sync(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        options: dict[str, Any] | None = None,
    ) -> AudioResult:
        options = options or {}
        words_per_second = float(options.get("words_per_second", 2.5))
        if not math.isfinite(words_per_second) or words_per_second <= 0:
            raise ValueError("words_per_second must be positive")
        word_count = len(text.split())
        duration = max(1.0, word_count / words_per_second)
        frame_count = round(duration * self.sample_rate)
        samples = self._samples(frame_count, max(1, word_count))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(self.sample_rate)
            audio.writeframes(samples)
        relative_path = self.store.publish_bytes_set({output_path: buffer.getvalue()})[output_path]
        return AudioResult(
            provider=self.provider,
            model=self.model,
            voice_id=voice_id,
            output_path=relative_path,
            duration_seconds=frame_count / self.sample_rate,
            status="completed",
        )

    def _samples(self, frame_count: int, segment_count: int) -> bytes:
        output = bytearray(frame_count * 2)
        for frame in range(frame_count):
            segment = min(segment_count - 1, frame * segment_count // frame_count)
            segment_start = segment * frame_count // segment_count
            segment_end = (segment + 1) * frame_count // segment_count
            active_end = segment_start + ((segment_end - segment_start) * 4 // 5)
            value = 0
            if frame < active_end:
                frequency = 220 if segment % 2 == 0 else 330
                value = round(2400 * math.sin(2 * math.pi * frequency * frame / self.sample_rate))
            struct.pack_into("<h", output, frame * 2, value)
        return bytes(output)


def _xml_text(value: str) -> str:
    return "".join(
        character
        for character in value
        if character in "\t\n\r"
        or "\u0020" <= character <= "\ud7ff"
        or "\ue000" <= character <= "\ufffd"
        or "\U00010000" <= character <= "\U0010ffff"
    )
