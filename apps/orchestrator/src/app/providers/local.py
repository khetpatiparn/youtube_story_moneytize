from __future__ import annotations

import re
from typing import Any


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
