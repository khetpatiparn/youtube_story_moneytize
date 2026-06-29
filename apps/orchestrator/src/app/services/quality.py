from __future__ import annotations

import json
import hashlib
import math
import shutil
import subprocess
import wave
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.services.artifacts import ArtifactStore
from app.services.timeline import wav_duration_seconds


QUALITY_CACHE_VERSION = 1
SVG_TAG = "{http://www.w3.org/2000/svg}svg"


@dataclass(frozen=True)
class QualityCheck:
    name: str
    passed: bool
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "issues": list(self.issues)}


@dataclass(frozen=True)
class QualityResult:
    passed: bool
    reviewable: bool
    score: float
    issues: list[str]
    checks: list[QualityCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reviewable": self.reviewable,
            "score": self.score,
            "issues": list(self.issues),
            "checks": [check.to_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "QualityResult":
        if not isinstance(value, dict) or not isinstance(value.get("checks"), list):
            raise ValueError("cached quality result is invalid")
        checks = [
            QualityCheck(
                name=check["name"],
                passed=check["passed"],
                issues=tuple(check.get("issues", [])),
            )
            for check in value["checks"]
        ]
        return cls(
            passed=bool(value["passed"]),
            reviewable=bool(value["reviewable"]),
            score=float(value["score"]),
            issues=list(value.get("issues", [])),
            checks=checks,
        )


def validate_project_media(
    project_dir: Path,
    scenes: Any,
    timeline: Any,
    audio_path: Any,
    video_path: Any,
    render_payload_path: Any,
    video_probe: Callable[[Path], float] | None = None,
    *,
    generated_images: Any = None,
) -> QualityResult:
    root = Path(project_dir).resolve()
    checks: list[QualityCheck] = []

    scene_ids = [s.get("scene_id") for s in scenes] if isinstance(scenes, list) else []
    image_issues: list[str] = []
    images = generated_images if isinstance(generated_images, list) else scenes
    for scene_id in scene_ids:
        matches = [item for item in images if isinstance(item, dict) and item.get("scene_id") == scene_id]
        if len(matches) != 1:
            image_issues.append(f"scene_images: {scene_id} must have exactly one image")
            continue
        relative = matches[0].get("output_path") or matches[0].get("image_path")
        path = _contained(root, relative)
        if path is None or not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            image_issues.append(f"scene_images: {scene_id} image is missing")
            continue
        try:
            svg = ET.parse(path).getroot()
            if (
                path.suffix.lower() != ".svg"
                or svg.tag != SVG_TAG
                or svg.get("width") != "1280"
                or svg.get("height") != "720"
            ):
                raise ValueError
        except (ET.ParseError, OSError, ValueError):
            image_issues.append(f"scene_images: {scene_id} image must be a parseable 1280x720 SVG")
    checks.append(_check("scene_images", image_issues))

    timeline_issues: list[str] = []
    expected_start = 0
    if not isinstance(timeline, list) or not timeline:
        timeline_issues.append("timeline: timeline must be nonempty")
    else:
        ids = [item.get("scene_id") if isinstance(item, dict) else None for item in timeline]
        if ids != scene_ids or len(ids) != len(set(ids)):
            timeline_issues.append("timeline: scene IDs must be unique and match scene order")
        for item in timeline:
            scene_id = item.get("scene_id", "unknown") if isinstance(item, dict) else "unknown"
            start = item.get("start_frame") if isinstance(item, dict) else None
            duration = item.get("duration_in_frames") if isinstance(item, dict) else None
            if start != expected_start:
                timeline_issues.append(f"timeline: {scene_id} must start at frame {expected_start}")
            if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
                timeline_issues.append(f"timeline: {scene_id} duration must be a positive integer")
            else:
                expected_start = (start if isinstance(start, int) else expected_start) + duration
    checks.append(_check("timeline", timeline_issues))

    audio_issues: list[str] = []
    audio = _contained(root, audio_path)
    try:
        if audio is None or not audio.is_file() or audio.is_symlink() or audio.stat().st_size == 0:
            raise ValueError("audio is missing")
        wav_duration_seconds(audio)
    except (OSError, wave.Error, ValueError) as error:
        audio_issues.append(f"audio: WAV is invalid: {error}")
    checks.append(_check("audio", audio_issues))

    payload_issues: list[str] = []
    payload = None
    payload_path = _contained(root, render_payload_path)
    try:
        if payload_path is None or not payload_path.is_file() or payload_path.is_symlink():
            raise ValueError("render payload is missing")
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        payload_scenes = payload.get("scenes") if isinstance(payload, dict) else None
        if not isinstance(payload_scenes, list):
            raise ValueError("scenes must be a list")
        expected_payload_scenes = [
            {
                "sceneId": item["scene_id"],
                "startFrame": item["start_frame"],
                "durationInFrames": item["duration_in_frames"],
            }
            for item in timeline
        ]
        actual_payload_scenes = [
            {
                "sceneId": item.get("sceneId"),
                "startFrame": item.get("startFrame"),
                "durationInFrames": item.get("durationInFrames"),
            }
            for item in payload_scenes
            if isinstance(item, dict)
        ]
        if actual_payload_scenes != expected_payload_scenes:
            payload_issues.append("render_payload: scene IDs and timing must match the timeline")
        total = sum(item["durationInFrames"] for item in payload_scenes)
        if total != expected_start:
            payload_issues.append(f"render_payload: total frames {total} do not match timeline {expected_start}")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        payload_issues.append(f"render_payload: invalid payload: {error}")
    checks.append(_check("render_payload", payload_issues))

    video_issues: list[str] = []
    video = _contained(root, video_path)
    try:
        if video is None or not video.is_file() or video.is_symlink() or video.stat().st_size < 12:
            raise ValueError
        with video.open("rb") as handle:
            if handle.read(8)[4:8] != b"ftyp":
                raise ValueError
    except (OSError, ValueError):
        video_issues.append("video: MP4 must be a regular non-symlink file with an ftyp header")
    checks.append(_check("video", video_issues))

    duration_issues: list[str] = []
    if not video_issues and isinstance(payload, dict):
        fps = payload.get("fps")
        try:
            if not isinstance(fps, int) or fps <= 0:
                raise ValueError("payload fps is invalid")
            actual = (video_probe or _ffprobe_duration)(video)
            expected = expected_start / fps
            if not math.isfinite(actual) or actual <= 0:
                raise ValueError("probe returned a non-positive duration")
            if abs(actual - expected) > (1 / fps) + 1e-9:
                duration_issues.append(
                    f"video_duration: rendered duration {actual:.3f}s differs from expected {expected:.3f}s by more than one frame"
                )
        except Exception as error:
            duration_issues.append(f"video_duration: unable to probe rendered duration: {error}")
    else:
        duration_issues.append("video_duration: validation requires a valid video and render payload")
    checks.append(_check("video_duration", duration_issues))

    issues = [issue for check in checks for issue in check.issues]
    passed_count = sum(check.passed for check in checks)
    reviewable = not any(not check.passed for check in checks if check.name in {"audio", "render_payload", "video", "video_duration"})
    return QualityResult(not issues, reviewable, passed_count / len(checks), issues, checks)


def _check(name: str, issues: list[str]) -> QualityCheck:
    return QualityCheck(name, not issues, tuple(issues))


def _contained(root: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    candidate = root / relative
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if root in resolved.parents else None


def ffprobe_duration(video_path: Path, repository_root: Path | None = None) -> float:
    executable = _find_ffprobe(video_path, repository_root)
    if not executable:
        raise RuntimeError("ffprobe is unavailable")
    result = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or "ffprobe failed")[-1000:].strip())
    return float(result.stdout[:100].strip())


def _ffprobe_duration(video_path: Path) -> float:
    return ffprobe_duration(video_path)


def _find_ffprobe(video_path: Path, repository_root: Path | None = None) -> str | None:
    executable = shutil.which("ffprobe")
    if executable:
        return executable
    ancestors = [video_path.parent, *video_path.parents]
    if repository_root is not None:
        ancestors.insert(0, Path(repository_root).resolve())
    for ancestor in ancestors:
        remotion = ancestor / "node_modules" / "@remotion"
        if not remotion.is_dir():
            continue
        matches = sorted(remotion.glob("compositor-*/ffprobe*"))
        for match in matches:
            if match.is_file():
                return str(match)
    return None


def quality_input_fingerprint(project_dir: Path, state: dict[str, Any]) -> str:
    store = ArtifactStore(project_dir)
    digest = hashlib.sha256()
    digest.update(f"quality-cache-v{QUALITY_CACHE_VERSION}\n".encode())
    structured = {
        key: state.get(key)
        for key in (
            "scenes",
            "generated_images",
            "timeline",
            "voice_path",
            "video_path",
            "render_payload_path",
        )
    }
    digest.update(
        json.dumps(structured, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    paths: list[str] = []
    for image in state.get("generated_images") or []:
        if isinstance(image, dict) and isinstance(image.get("output_path"), str):
            paths.append(image["output_path"])
    paths.extend(
        path
        for path in (
            state.get("voice_path"),
            state.get("video_path"),
            state.get("render_payload_path"),
        )
        if isinstance(path, str)
    )
    for relative in sorted(set(paths)):
        digest.update(relative.encode("utf-8") + b"\0")
        try:
            path = store.path(relative)
            digest.update(path.read_bytes())
        except (OSError, ValueError):
            digest.update(b"<missing>")
    return digest.hexdigest()
