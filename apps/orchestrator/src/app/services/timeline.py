from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any


def wav_duration_seconds(path: str | Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            rate = audio.getframerate()
            frames = audio.getnframes()
            compression = audio.getcomptype()
    except (EOFError, OSError, wave.Error) as error:
        raise ValueError(f"Invalid WAV file: {path}") from error
    if channels < 1 or sample_width < 1 or rate <= 0 or frames <= 0 or compression != "NONE":
        raise ValueError(f"Invalid WAV file: {path}")
    return frames / rate


def build_timeline(
    scenes: list[dict[str, Any]], audio_duration_seconds: float, fps: int = 30
) -> list[dict[str, Any]]:
    if not scenes:
        raise ValueError("Timeline requires at least one scene")
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    if not isinstance(audio_duration_seconds, (int, float)) or not math.isfinite(audio_duration_seconds):
        raise ValueError("audio duration must be finite")
    if audio_duration_seconds <= 0:
        raise ValueError("audio duration must be positive")

    total_frames = round(audio_duration_seconds * fps)
    if total_frames < len(scenes):
        raise ValueError("audio duration is too short to allocate one frame per scene")

    weights = [max(1, len(str(scene.get("narration", "")).split())) for scene in scenes]
    weight_total = sum(weights)
    durations: list[int] = []
    allocated = 0
    for index, weight in enumerate(weights[:-1]):
        slots_after = len(scenes) - index - 1
        proportional = round(total_frames * weight / weight_total)
        duration = max(1, min(proportional, total_frames - allocated - slots_after))
        durations.append(duration)
        allocated += duration
    durations.append(total_frames - allocated)

    timeline: list[dict[str, Any]] = []
    start = 0
    for scene, duration in zip(scenes, durations):
        timeline.append(
            {
                "scene_id": str(scene.get("scene_id", "")),
                "start_frame": start,
                "duration_in_frames": duration,
            }
        )
        start += duration
    return timeline
