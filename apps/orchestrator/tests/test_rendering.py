import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class RemotionRendererTests(unittest.TestCase):
    def _fixture(self, root: Path):
        project = root / "projects" / "project_001"
        (project / "images").mkdir(parents=True)
        (project / "audio").mkdir()
        (project / "render").mkdir()
        (project / "images" / "scene.svg").write_text("<svg/>", encoding="utf-8")
        (project / "audio" / "narration.wav").write_bytes(b"RIFFaudio")
        payload = {"fps": 24, "width": 640, "height": 360, "audioPath": "audio/narration.wav", "scenes": [{"sceneId": "scene_001", "startFrame": 0, "durationInFrames": 24, "imagePath": "images/scene.svg", "motion": "slow_push", "focalPoint": [0.5, 0.5]}]}
        (project / "render" / "render_payload.json").write_text(json.dumps(payload), encoding="utf-8")
        return project

    def test_stages_assets_and_invokes_remotion_without_shell(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root); calls = []
            def run(args, **kwargs):
                calls.append((args, kwargs))
                (project / "render" / "story.mp4").write_bytes(b"mp4")
                return subprocess.CompletedProcess(args, 0, "ok", "")
            result = RemotionRenderer(root, project, "project_001", command_runner=run).render("render/render_payload.json")
            self.assertEqual(result, "render/story.mp4")
            args, kwargs = calls[0]
            self.assertEqual(args[:6], ["npm.cmd", "exec", "remotion", "render", "apps/renderer/src/index.tsx", "YouTubeStory"])
            self.assertNotIn("shell", kwargs)
            self.assertTrue(kwargs["capture_output"]); self.assertTrue(kwargs["text"])
            staged = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
            self.assertTrue(staged["audioPath"].startswith("projects/project_001/"))
            self.assertTrue(staged["scenes"][0]["imagePath"].startswith("projects/project_001/"))

    def test_rejects_traversal_and_wrong_project(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root)
            payload_path = project / "render" / "render_payload.json"
            payload = json.loads(payload_path.read_text())
            payload["scenes"][0]["imagePath"] = "../outside.svg"
            payload_path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError): RemotionRenderer(root, project, "project_001").render("render/render_payload.json")
            with self.assertRaises(ValueError): RemotionRenderer(root, project, "other").render("render/render_payload.json")

    def test_command_failure_and_missing_or_empty_output_fail(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root)
            failed = lambda args, **kw: subprocess.CompletedProcess(args, 2, "", "x" * 10000)
            with self.assertRaisesRegex(RuntimeError, "Remotion render failed") as caught:
                RemotionRenderer(root, project, "project_001", command_runner=failed).render("render/render_payload.json")
            self.assertLess(len(str(caught.exception)), 5000)
            ok = lambda args, **kw: subprocess.CompletedProcess(args, 0, "", "")
            with self.assertRaisesRegex(RuntimeError, "nonempty MP4"):
                RemotionRenderer(root, project, "project_001", command_runner=ok).render("render/render_payload.json")
            (project / "render" / "story.mp4").write_bytes(b"")
            with self.assertRaisesRegex(RuntimeError, "nonempty MP4"):
                RemotionRenderer(root, project, "project_001", command_runner=ok).render("render/render_payload.json")

    def test_manifest_reuses_matching_output_but_changed_payload_rerenders(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root); calls = []
            def run(args, **kwargs):
                calls.append(args)
                (project / "render" / "story.mp4").write_bytes(b"video")
                return subprocess.CompletedProcess(args, 0, "", "")
            renderer = RemotionRenderer(root, project, "project_001", command_runner=run)
            renderer.render("render/render_payload.json")
            renderer.render("render/render_payload.json")
            self.assertEqual(len(calls), 1)
            payload_path = project / "render" / "render_payload.json"
            payload = json.loads(payload_path.read_text()); payload["fps"] = 30
            payload_path.write_text(json.dumps(payload))
            renderer.render("render/render_payload.json")
            self.assertEqual(len(calls), 2)


class RunnerRenderingTests(unittest.TestCase):
    def _setup(self, root: Path):
        from app.repositories.checkpoint_repository import CheckpointRepository
        from app.repositories.project_repository import ProjectRepository
        from app.schemas.project import CreateProjectRequest
        projects = ProjectRepository(root / "projects")
        projects.create_project(CreateProjectRequest(topic="story", duration=10, profile="simple_story_th"), project_id="project_001")
        checkpoints = CheckpointRepository(root / "checkpoints.sqlite")
        state = {"project_id": "project_001", "topic": "story", "status": "render_ready", "current_node": "render", "render_payload_path": "render/render_payload.json"}
        checkpoints.save_checkpoint("project_001", state)
        return projects, checkpoints, state

    def test_runner_renders_once_and_advances_to_quality(self):
        from app.services.pipeline_runner import PipelineRunner
        class Renderer:
            calls = 0
            def render(self, path):
                self.calls += 1
                self.path = path
                return "render/story.mp4"
        with tempfile.TemporaryDirectory() as temp:
            projects, checkpoints, _ = self._setup(Path(temp)); renderer = Renderer()
            state = PipelineRunner(projects, checkpoints, renderer=renderer).resume("project_001")
            self.assertEqual(renderer.calls, 1)
            self.assertEqual(renderer.path, "render/render_payload.json")
            self.assertEqual(state["video_path"], "render/story.mp4")
            self.assertEqual((state["status"], state["current_node"]), ("rendered", "quality"))

    def test_runner_render_failure_keeps_render_ready_checkpoint_for_retry(self):
        from app.services.pipeline_runner import PipelineRunner
        class Renderer:
            def render(self, path): raise RuntimeError("render failed")
        with tempfile.TemporaryDirectory() as temp:
            projects, checkpoints, original = self._setup(Path(temp))
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                PipelineRunner(projects, checkpoints, renderer=Renderer()).resume("project_001")
            self.assertEqual(checkpoints.load_latest("project_001").state, original)
