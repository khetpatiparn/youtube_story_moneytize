import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


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
                Path(args[7]).write_bytes(b"\x00\x00\x00\x18ftypmp42video")
                return subprocess.CompletedProcess(args, 0, "ok", "")
            result = RemotionRenderer(root, project, "project_001", command_runner=run).render("render/render_payload.json")
            self.assertEqual(result, "render/story.mp4")
            args, kwargs = calls[0]
            self.assertEqual(args[:7], ["npm.cmd", "exec", "--", "remotion", "render", "apps/renderer/src/index.tsx", "YouTubeStory"])
            self.assertNotEqual(Path(args[7]).name, "story.mp4")
            self.assertEqual(args[8:10], ["--public-dir", "apps/renderer/public"])
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
                Path(args[7]).write_bytes(b"\x00\x00\x00\x18ftypmp42video")
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

    def test_changed_payload_cannot_bless_preexisting_output_when_temp_is_missing(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root)
            output = project / "render/story.mp4"; output.write_bytes(b"old-video")
            manifest = project / "render/render_manifest.json"; manifest.write_text('{"old": true}')
            ok_without_output = lambda args, **kw: subprocess.CompletedProcess(args, 0, "", "")
            with self.assertRaisesRegex(RuntimeError, "nonempty MP4"):
                RemotionRenderer(root, project, "project_001", command_runner=ok_without_output).render("render/render_payload.json")
            self.assertEqual(output.read_bytes(), b"old-video")
            self.assertEqual(json.loads(manifest.read_text()), {"old": True})
            self.assertEqual(list((project / "render").glob("*.tmp.mp4")), [])

    def test_only_wav_audio_is_accepted(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root); payload_path = project / "render/render_payload.json"
            for path in ("audio/track.mp3", "audio/track.m4a", "audio/track.aac", "audio/track.ogg", "../track.wav", str(root / "track.wav")):
                payload = json.loads(payload_path.read_text()); payload["audioPath"] = path; payload_path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError): RemotionRenderer(root, project, "project_001").render("render/render_payload.json")

    def test_rejects_payload_project_id_mismatch_and_alias_detector_hits(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root); payload_path = project / "render/render_payload.json"
            payload = json.loads(payload_path.read_text()); payload["projectId"] = "project_999"; payload_path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "projectId"):
                RemotionRenderer(root, project, "project_001").render("render/render_payload.json")
            payload.pop("projectId"); payload_path.write_text(json.dumps(payload))
            detector = lambda path: path.name == "images"
            with self.assertRaisesRegex(ValueError, "symlinks or junctions"):
                RemotionRenderer(root, project, "project_001", alias_detector=detector).render("render/render_payload.json")
            destination_detector = lambda path: path.name == "public"
            with self.assertRaisesRegex(ValueError, "symlinks or junctions"):
                RemotionRenderer(root, project, "project_001", alias_detector=destination_detector).render("render/render_payload.json")

    def test_rejects_real_source_symlink_when_platform_allows_it(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root); link = project / "images/link.svg"
            try: link.symlink_to(project / "images/scene.svg")
            except OSError as error: self.skipTest(f"symlinks unavailable: {error}")
            payload_path = project / "render/render_payload.json"; payload = json.loads(payload_path.read_text())
            payload["scenes"][0]["imagePath"] = "images/link.svg"; payload_path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "symlinks or junctions"):
                RemotionRenderer(root, project, "project_001").render("render/render_payload.json")

    def test_asset_and_renderer_source_changes_invalidate_manifest(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root)
            source = root / "apps/renderer/src"; (source / "motions").mkdir(parents=True)
            for path in (source / "index.tsx", source / "renderPayload.js", source / "motions/index.js", root / "package.json", root / "package-lock.json"):
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text("v1")
            calls = []
            def run(args, **kw): calls.append(args); Path(args[7]).write_bytes(b"\x00\x00\x00\x18ftypmp42video"); return subprocess.CompletedProcess(args, 0, "", "")
            renderer = RemotionRenderer(root, project, "project_001", command_runner=run)
            renderer.render("render/render_payload.json"); renderer.render("render/render_payload.json")
            (project / "images/scene.svg").write_text("<svg>changed</svg>"); renderer.render("render/render_payload.json")
            (source / "index.tsx").write_text("v2"); renderer.render("render/render_payload.json")
            (root / "package.json").write_text("v2"); renderer.render("render/render_payload.json")
            self.assertEqual(len(calls), 4)

    def test_same_project_renders_are_serialized(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = self._fixture(root); calls = []; entered = threading.Event(); release = threading.Event()
            def run(args, **kw):
                calls.append(args); entered.set(); release.wait(2); Path(args[7]).write_bytes(b"\x00\x00\x00\x18ftypmp42video"); return subprocess.CompletedProcess(args, 0, "", "")
            renderer = RemotionRenderer(root, project, "project_001", command_runner=run)
            results = []
            threads = [threading.Thread(target=lambda: results.append(renderer.render("render/render_payload.json"))) for _ in range(2)]
            threads[0].start(); entered.wait(1); threads[1].start(); release.set()
            for thread in threads: thread.join(3)
            self.assertEqual(len(calls), 1); self.assertEqual(len(results), 2)

    def test_unrelated_projects_are_not_globally_serialized(self):
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); first = self._fixture(root); second = root / "projects/project_002"
            import shutil
            shutil.copytree(first, second)
            active = 0; maximum = 0; guard = threading.Lock(); both = threading.Event(); release = threading.Event()
            def run(args, **kw):
                nonlocal active, maximum
                with guard: active += 1; maximum = max(maximum, active); both.set() if active == 2 else None
                release.wait(2); Path(args[7]).write_bytes(b"\x00\x00\x00\x18ftypmp42video")
                with guard: active -= 1
                return subprocess.CompletedProcess(args, 0, "", "")
            renderers = [RemotionRenderer(root, first, "project_001", command_runner=run), RemotionRenderer(root, second, "project_002", command_runner=run)]
            threads = [threading.Thread(target=lambda renderer=r: renderer.render("render/render_payload.json")) for r in renderers]
            for thread in threads: thread.start()
            both.wait(1); release.set()
            for thread in threads: thread.join(3)
            self.assertEqual(maximum, 2)


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

    def test_metadata_failure_reuses_manifest_without_duplicate_render(self):
        from app.services.pipeline_runner import PipelineRunner
        from app.services.rendering import RemotionRenderer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); projects, checkpoints, _ = self._setup(root); project = projects.project_dir("project_001")
            (project / "images/scene.svg").write_text("<svg/>"); (project / "audio/narration.wav").write_bytes(b"RIFFaudio")
            payload = {"projectId": "project_001", "fps": 24, "width": 640, "height": 360, "audioPath": "audio/narration.wav", "scenes": [{"sceneId": "scene_001", "startFrame": 0, "durationInFrames": 24, "imagePath": "images/scene.svg", "motion": "slow_push", "focalPoint": [0.5, 0.5]}]}
            (project / "render/render_payload.json").write_text(json.dumps(payload))
            calls = []
            def run(args, **kw): calls.append(args); Path(args[7]).write_bytes(b"\x00\x00\x00\x18ftypmp42video"); return subprocess.CompletedProcess(args, 0, "", "")
            with patch.object(projects, "save_project", side_effect=OSError("metadata failed")):
                with self.assertRaisesRegex(OSError, "metadata failed"):
                    PipelineRunner(projects, checkpoints, renderer=RemotionRenderer(root, project, "project_001", command_runner=run)).resume("project_001")
            state = PipelineRunner(projects, checkpoints, renderer=RemotionRenderer(root, project, "project_001", command_runner=run)).resume("project_001")
            self.assertEqual(len(calls), 1); self.assertEqual(state["status"], "rendered")
