from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable


class RemotionRenderer:
    def __init__(self, repository_root: Path, project_dir: Path, project_id: str, *, command_runner: Callable[..., Any] = subprocess.run) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.project_dir = Path(project_dir).resolve()
        self.project_id = project_id
        expected = (self.project_dir.parent / project_id).resolve()
        if expected != self.project_dir or self.project_dir.name != project_id:
            raise ValueError("project_id does not match project_dir")
        self.command_runner = command_runner

    def render(self, payload_path: str) -> str:
        source_payload_path = self._contained(payload_path)
        if source_payload_path.suffix.lower() != ".json" or not source_payload_path.is_file():
            raise ValueError("render payload must be a project JSON file")
        payload = json.loads(source_payload_path.read_text(encoding="utf-8"))
        staged = self._stage_payload(payload)
        fingerprint = self._fingerprint(staged)
        output = self.project_dir / "render" / "story.mp4"
        manifest = self.project_dir / "render" / "render_manifest.json"
        if self._valid_output(output) and self._manifest_matches(manifest, fingerprint):
            return "render/story.mp4"

        staged_payload = self.project_dir / "render" / "remotion_payload.json"
        self._atomic_json(staged_payload, staged)
        args = ["npm.cmd", "exec", "remotion", "render", "apps/renderer/src/index.tsx", "YouTubeStory", str(output), "--props", str(staged_payload)]
        result = self.command_runner(args, cwd=self.repository_root, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Remotion render failed ({result.returncode}): {result.stderr[-4000:]}")
        if not self._valid_output(output):
            raise RuntimeError("Remotion did not create a regular nonempty MP4")
        self._atomic_json(manifest, {"project_id": self.project_id, "fingerprint": fingerprint, "video_path": "render/story.mp4"})
        return "render/story.mp4"

    def _stage_payload(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict) or not all(isinstance(payload.get(k), int) and payload[k] > 0 for k in ("fps", "width", "height")):
            raise ValueError("invalid render payload metadata")
        if payload.get("projectId", self.project_id) != self.project_id:
            raise ValueError("render payload projectId does not match project_id")
        scenes = payload.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("render payload requires scenes")
        result = dict(payload)
        result["audioPath"] = self._stage_asset(payload.get("audioPath"), {".wav", ".mp3", ".m4a", ".aac", ".ogg"})
        staged_scenes = []
        scene_ids: set[str] = set()
        for scene in scenes:
            if not isinstance(scene, dict): raise ValueError("invalid scene")
            scene_id = scene.get("sceneId")
            if not isinstance(scene_id, str) or not scene_id or scene_id in scene_ids:
                raise ValueError("sceneId must be a unique nonempty string")
            scene_ids.add(scene_id)
            if not isinstance(scene.get("startFrame"), int) or scene["startFrame"] < 0:
                raise ValueError("startFrame must be a nonnegative integer")
            if not isinstance(scene.get("durationInFrames"), int) or scene["durationInFrames"] <= 0:
                raise ValueError("durationInFrames must be a positive integer")
            if scene.get("motion", "slow_push") not in {"slow_push", "pan_left", "pan_right", "zoom_in", "zoom_out"}:
                raise ValueError("unsupported scene motion")
            focal = scene.get("focalPoint", [0.5, 0.5])
            if not isinstance(focal, list) or len(focal) != 2 or any(not isinstance(value, (int, float)) or value < 0 or value > 1 for value in focal):
                raise ValueError("focalPoint must contain two values between zero and one")
            item = dict(scene)
            item["imagePath"] = self._stage_asset(scene.get("imagePath"), {".svg"})
            staged_scenes.append(item)
        result["scenes"] = staged_scenes
        return result

    def _stage_asset(self, relative: Any, extensions: set[str]) -> str:
        if not isinstance(relative, str): raise ValueError("asset path must be a string")
        source = self._contained(relative)
        if source.suffix.lower() not in extensions or not source.is_file() or source.is_symlink():
            raise ValueError("asset type is not allowed")
        public = self.repository_root / "apps" / "renderer" / "public"
        destination = public / "projects" / self.project_id / relative.replace("\\", "/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temp = Path(handle.name)
        try:
            shutil.copyfile(source, temp)
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)
        return destination.relative_to(public).as_posix()

    def _contained(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute(): raise ValueError("absolute paths are not allowed")
        candidate = (self.project_dir / path).resolve()
        if self.project_dir not in candidate.parents: raise ValueError("path escapes project")
        return candidate

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        public = self.repository_root / "apps" / "renderer" / "public"
        asset_paths = [payload["audioPath"], *(scene["imagePath"] for scene in payload["scenes"])]
        asset_hashes = {
            relative: hashlib.sha256((public / relative).read_bytes()).hexdigest()
            for relative in asset_paths
        }
        canonical = {"payload": payload, "assets": asset_hashes}
        return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _valid_output(path: Path) -> bool:
        return path.is_file() and not path.is_symlink() and path.stat().st_size > 0 and path.suffix.lower() == ".mp4"

    def _manifest_matches(self, path: Path, fingerprint: str) -> bool:
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return False
        return data == {"project_id": self.project_id, "fingerprint": fingerprint, "video_path": "render/story.mp4"}

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle: json.dump(value, handle, ensure_ascii=False, indent=2)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
