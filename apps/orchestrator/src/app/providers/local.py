from __future__ import annotations

import hashlib
import html
import re
from typing import Any

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


def _xml_text(value: str) -> str:
    return "".join(
        character
        for character in value
        if character in "\t\n\r"
        or "\u0020" <= character <= "\ud7ff"
        or "\ue000" <= character <= "\ufffd"
        or "\U00010000" <= character <= "\U0010ffff"
    )
