import asyncio
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch


class LocalAudioTimelineTests(unittest.TestCase):
    def test_local_tts_writes_deterministic_pcm_wav_with_exact_duration(self):
        from app.providers.local import LocalTTSProvider
        from app.services.artifacts import ArtifactStore
        from app.services.timeline import wav_duration_seconds

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = LocalTTSProvider(ArtifactStore(temp_dir))
            result = asyncio.run(
                provider.synthesize(
                    "one two three four", "narrator-th", "audio/narration.wav", {"words_per_second": 2}
                )
            )
            first = Path(temp_dir, result.output_path).read_bytes()
            provider.synthesize_sync(
                "one two three four", "narrator-th", "audio/copy.wav", {"words_per_second": 2}
            )
            second = Path(temp_dir, "audio/copy.wav").read_bytes()

            self.assertEqual(first, second)
            with wave.open(str(Path(temp_dir, result.output_path)), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), 22050)
                self.assertEqual(audio.getnframes(), 44100)
            self.assertEqual(wav_duration_seconds(Path(temp_dir, result.output_path)), 2.0)
            self.assertEqual(result.duration_seconds, 2.0)

    def test_local_tts_rejects_unsafe_or_invalid_output(self):
        from app.providers.local import LocalTTSProvider
        from app.services.artifacts import ArtifactStore
        from app.services.timeline import wav_duration_seconds

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = LocalTTSProvider(ArtifactStore(temp_dir))
            with self.assertRaises(ValueError):
                provider.synthesize_sync("hello", "voice", "../escape.wav", {})
            broken = Path(temp_dir, "broken.wav")
            broken.write_bytes(b"not a wav")
            with self.assertRaises(ValueError):
                wav_duration_seconds(broken)

    def test_build_timeline_is_proportional_contiguous_and_exact(self):
        from app.services.timeline import build_timeline

        scenes = [
            {"scene_id": "a", "narration": "one"},
            {"scene_id": "b", "narration": "one two three"},
            {"scene_id": "c", "narration": "one two"},
        ]
        timeline = build_timeline(scenes, 2.0, fps=30)

        self.assertEqual([item["start_frame"] for item in timeline], [0, 10, 40])
        self.assertEqual([item["duration_in_frames"] for item in timeline], [10, 30, 20])
        self.assertEqual(sum(item["duration_in_frames"] for item in timeline), 60)

    def test_build_timeline_rejects_invalid_or_impossible_inputs(self):
        from app.services.timeline import build_timeline

        for scenes, duration, fps in [([], 1, 30), ([{"narration": "x"}], 0, 30), ([{"narration": "x"}], 1, 0)]:
            with self.subTest(scenes=scenes, duration=duration, fps=fps):
                with self.assertRaises(ValueError):
                    build_timeline(scenes, duration, fps)
        with self.assertRaisesRegex(ValueError, "too short"):
            build_timeline([{"narration": "a"}, {"narration": "b"}], 0.03, 30)

    def _setup_runner(self, temp_dir):
        from app.repositories.checkpoint_repository import CheckpointRepository
        from app.repositories.project_repository import ProjectRepository
        from app.schemas.project import CreateProjectRequest
        from app.services.pipeline_runner import PipelineRunner

        projects = ProjectRepository(Path(temp_dir) / "projects")
        projects.create_project(
            CreateProjectRequest(topic="River spirit", duration=30, profile="simple_story_th"),
            project_id="project_001",
        )
        checkpoints = CheckpointRepository(Path(temp_dir) / "checkpoints.sqlite")
        PipelineRunner(projects, checkpoints).run("project_001")
        approval = projects.project_dir("project_001") / "reports" / "approvals.json"
        approval.parent.mkdir(parents=True, exist_ok=True)
        approval.write_text(json.dumps({"script": {"approved": True}}), encoding="utf-8")
        return projects, checkpoints

    def test_runner_writes_renderer_payload_and_render_ready_state(self):
        from app.services.pipeline_runner import PipelineRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            projects, checkpoints = self._setup_runner(temp_dir)
            state = PipelineRunner(projects, checkpoints).resume("project_001")
            payload = json.loads((projects.project_dir("project_001") / "render/render_payload.json").read_text())

            self.assertEqual((state["status"], state["current_node"]), ("render_ready", "render"))
            self.assertEqual(payload["fps"], 30)
            self.assertEqual((payload["width"], payload["height"]), (1280, 720))
            self.assertEqual(payload["audioPath"], "audio/narration.wav")
            self.assertEqual(
                set(payload["scenes"][0]),
                {"sceneId", "startFrame", "durationInFrames", "imagePath", "motion", "focalPoint"},
            )
            self.assertEqual(state["render_payload_path"], "render/render_payload.json")
            self.assertEqual(state["voice_path"], "audio/narration.wav")

    def test_runner_reuses_valid_audio_after_metadata_failure_and_repairs_corruption(self):
        from app.providers.local import LocalTTSProvider
        from app.services.artifacts import ArtifactStore
        from app.services.pipeline_runner import PipelineRunner

        class CountingTTS(LocalTTSProvider):
            calls = 0

            def synthesize_sync(self, text, voice_id, output_path, options=None):
                self.calls += 1
                return super().synthesize_sync(text, voice_id, output_path, options)

        with tempfile.TemporaryDirectory() as temp_dir:
            projects, checkpoints = self._setup_runner(temp_dir)
            project_dir = projects.project_dir("project_001")
            first = CountingTTS(ArtifactStore(project_dir))
            with patch.object(projects, "save_project", side_effect=OSError("metadata failed")):
                with self.assertRaisesRegex(OSError, "metadata failed"):
                    PipelineRunner(projects, checkpoints, tts_provider=first).resume("project_001")
            self.assertEqual(first.calls, 1)

            resumed = CountingTTS(ArtifactStore(project_dir))
            state = PipelineRunner(projects, checkpoints, tts_provider=resumed).resume("project_001")
            self.assertEqual(resumed.calls, 0)
            self.assertEqual(state["status"], "render_ready")

            (project_dir / "render/render_payload.json").write_text("{broken", encoding="utf-8")
            payload_repair = CountingTTS(ArtifactStore(project_dir))
            PipelineRunner(projects, checkpoints, tts_provider=payload_repair).resume("project_001")
            self.assertEqual(payload_repair.calls, 0)
            json.loads((project_dir / "render/render_payload.json").read_text(encoding="utf-8"))

            (project_dir / "audio/narration.wav").write_bytes(b"broken")
            repaired = CountingTTS(ArtifactStore(project_dir))
            PipelineRunner(projects, checkpoints, tts_provider=repaired).resume("project_001")
            self.assertEqual(repaired.calls, 1)


if __name__ == "__main__":
    unittest.main()
