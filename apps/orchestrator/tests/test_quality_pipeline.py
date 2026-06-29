import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch


class QualityPipelineTests(unittest.TestCase):
    def _valid_project(self, root: Path):
        project = root / "project_001"
        (project / "images").mkdir(parents=True, exist_ok=True)
        (project / "audio").mkdir(exist_ok=True)
        (project / "render").mkdir(exist_ok=True)
        scenes = [{"scene_id": "scene_001"}, {"scene_id": "scene_002"}]
        timeline = [
            {"scene_id": "scene_001", "start_frame": 0, "duration_in_frames": 15},
            {"scene_id": "scene_002", "start_frame": 15, "duration_in_frames": 15},
        ]
        images = []
        for scene in scenes:
            relative = f"images/{scene['scene_id']}.svg"
            (project / relative).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"></svg>',
                encoding="utf-8",
            )
            images.append({"scene_id": scene["scene_id"], "output_path": relative})
        with wave.open(str(project / "audio/narration.wav"), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
            wav.writeframes(struct.pack("<h", 0) * 22050)
        payload = {
            "fps": 30, "width": 1280, "height": 720, "audioPath": "audio/narration.wav",
            "scenes": [
                {"sceneId": item["scene_id"], "startFrame": item["start_frame"],
                 "durationInFrames": item["duration_in_frames"],
                 "imagePath": f"images/{item['scene_id']}.svg"}
                for item in timeline
            ],
        }
        (project / "render/render_payload.json").write_text(json.dumps(payload), encoding="utf-8")
        (project / "render/story.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"0" * 32)
        return project, scenes, images, timeline

    def test_valid_media_returns_deterministic_complete_result(self):
        from app.services.quality import validate_project_media
        with tempfile.TemporaryDirectory() as temp:
            project, scenes, images, timeline = self._valid_project(Path(temp))
            result = validate_project_media(
                project, scenes, timeline, "audio/narration.wav", "render/story.mp4",
                "render/render_payload.json", generated_images=images,
                video_probe=lambda _: 1.0,
            )
            self.assertTrue(result.passed)
            self.assertTrue(result.reviewable)
            self.assertEqual(result.score, 1.0)
            self.assertEqual(result.issues, [])
            self.assertEqual([check.name for check in result.checks],
                             ["scene_images", "timeline", "audio", "render_payload", "video", "video_duration"])

    def test_missing_image_and_noncontiguous_timeline_have_stable_issues(self):
        from app.services.quality import validate_project_media
        with tempfile.TemporaryDirectory() as temp:
            project, scenes, images, timeline = self._valid_project(Path(temp))
            (project / "images/scene_002.svg").unlink()
            timeline[1]["start_frame"] = 16
            result = validate_project_media(project, scenes, timeline, "audio/narration.wav",
                "render/story.mp4", "render/render_payload.json", generated_images=images,
                video_probe=lambda _: 1.0)
            self.assertIn("scene_images: scene_002 image is missing", result.issues)
            self.assertIn("timeline: scene_002 must start at frame 15", result.issues)
            self.assertFalse(result.passed)

    def test_duration_mismatch_and_probe_failure_are_reported(self):
        from app.services.quality import validate_project_media
        with tempfile.TemporaryDirectory() as temp:
            project, scenes, images, timeline = self._valid_project(Path(temp))
            mismatch = validate_project_media(project, scenes, timeline, "audio/narration.wav",
                "render/story.mp4", "render/render_payload.json", generated_images=images,
                video_probe=lambda _: 2.0)
            self.assertIn("video_duration: rendered duration 2.000s differs from expected 1.000s by more than one frame", mismatch.issues)
            failure = validate_project_media(project, scenes, timeline, "audio/narration.wav",
                "render/story.mp4", "render/render_payload.json", generated_images=images,
                video_probe=lambda _: (_ for _ in ()).throw(RuntimeError("probe unavailable")))
            self.assertIn("video_duration: unable to probe rendered duration: probe unavailable", failure.issues)
            self.assertFalse(failure.reviewable)

    def test_truncated_wav_and_payload_scene_mismatch_are_not_reviewable(self):
        from app.services.quality import validate_project_media
        with tempfile.TemporaryDirectory() as temp:
            project, scenes, images, timeline = self._valid_project(Path(temp))
            audio = project / "audio/narration.wav"
            audio.write_bytes(audio.read_bytes()[:-10])
            payload_path = project / "render/render_payload.json"
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            payload["scenes"][1]["sceneId"] = "scene_wrong"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            result = validate_project_media(
                project, scenes, timeline, "audio/narration.wav", "render/story.mp4",
                "render/render_payload.json", generated_images=images,
                video_probe=lambda _: 1.0,
            )

            self.assertTrue(any("truncated" in issue for issue in result.issues))
            self.assertIn("render_payload: scene IDs and timing must match the timeline", result.issues)
            self.assertFalse(result.reviewable)

    def _runner_at_rendered(self, root: Path):
        from app.repositories.checkpoint_repository import CheckpointRepository
        from app.repositories.project_repository import ProjectRepository
        from app.schemas.project import CreateProjectRequest
        projects = ProjectRepository(root / "projects")
        projects.create_project(CreateProjectRequest(topic="river", duration=1, profile="simple_story_th"), project_id="project_001")
        project, scenes, images, timeline = self._valid_project(root / "projects")
        (project / "scenes/scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        state = {
            **projects.load_project("project_001").to_graph_state(), "script_approved": True,
            "scenes": scenes, "generated_images": images, "timeline": timeline,
            "voice_path": "audio/narration.wav", "render_payload_path": "render/render_payload.json",
            "video_path": "render/story.mp4", "status": "rendered", "current_node": "quality",
        }
        checkpoints = CheckpointRepository(root / "checkpoints.sqlite")
        checkpoints.save_checkpoint("project_001", state)
        return projects, checkpoints, project

    def test_rendered_state_writes_reports_and_pauses_at_final_gate(self):
        from app.services.pipeline_runner import PipelineRunner
        with tempfile.TemporaryDirectory() as temp:
            projects, checkpoints, project = self._runner_at_rendered(Path(temp))
            state = PipelineRunner(projects, checkpoints, video_probe=lambda _: 1.0).resume("project_001")
            self.assertEqual((state["status"], state["current_node"], state["waiting_for"]),
                             ("awaiting_final_approval", "final_approval", "final"))
            self.assertEqual(state["quality_report"]["score"], 1.0)
            report = json.loads((project / "reports/quality_report.json").read_text())
            self.assertEqual(report["video_path"], "render/story.mp4")

    def test_final_approval_completes_on_resume_without_regenerating_media_or_reports(self):
        from app.services.approval_reporting import ApprovalReportingService, ApprovalRequest
        from app.services.pipeline_runner import PipelineRunner
        with tempfile.TemporaryDirectory() as temp:
            projects, checkpoints, project = self._runner_at_rendered(Path(temp))
            runner = PipelineRunner(projects, checkpoints, video_probe=lambda _: 1.0)
            runner.resume("project_001")
            tracked = [project / "audio/narration.wav", project / "render/story.mp4",
                       project / "reports/quality_report.json"]
            mtimes = [path.stat().st_mtime_ns for path in tracked]
            ApprovalReportingService(projects, checkpoints).record_final_approval(
                ApprovalRequest("project_001", True, "human"))
            approved = checkpoints.load_latest("project_001").state
            self.assertEqual(approved["status"], "final_approved")
            self.assertEqual(approved["current_node"], "final_approval")
            state = PipelineRunner(projects, checkpoints).resume("project_001")
            self.assertEqual((state["status"], state["current_node"]), ("completed", "complete"))
            self.assertNotIn("waiting_for", state)
            self.assertEqual([path.stat().st_mtime_ns for path in tracked], mtimes)

    def test_final_changes_requested_stays_paused(self):
        from app.services.approval_reporting import ApprovalReportingService, ApprovalRequest
        from app.services.pipeline_runner import PipelineRunner
        with tempfile.TemporaryDirectory() as temp:
            projects, checkpoints, _ = self._runner_at_rendered(Path(temp))
            PipelineRunner(projects, checkpoints, video_probe=lambda _: 1.0).resume("project_001")
            ApprovalReportingService(projects, checkpoints).record_final_approval(
                ApprovalRequest("project_001", False, "human"))
            state = PipelineRunner(projects, checkpoints).resume("project_001")
            self.assertEqual(state["status"], "final_changes_requested")
            self.assertEqual(state["waiting_for"], "final")

    def test_quality_reports_reconcile_after_metadata_failure_without_rewrite(self):
        from app.services.pipeline_runner import PipelineRunner
        with tempfile.TemporaryDirectory() as temp:
            projects, checkpoints, project = self._runner_at_rendered(Path(temp))
            with patch.object(projects, "save_project", side_effect=OSError("metadata failed")):
                with self.assertRaisesRegex(OSError, "metadata failed"):
                    PipelineRunner(projects, checkpoints, video_probe=lambda _: 1.0).resume("project_001")
            report_paths = [
                project / "reports/quality_report.json",
                project / "reports/contact_sheet.md",
                project / "reports/project_report.md",
                project / "reports/quality_state.json",
            ]
            before = [path.read_bytes() for path in report_paths]

            state = PipelineRunner(projects, checkpoints, video_probe=lambda _: 1.0).resume("project_001")

            self.assertEqual(state["status"], "awaiting_final_approval")
            self.assertEqual([path.read_bytes() for path in report_paths], before)

    def test_changed_quality_input_invalidates_cached_reports(self):
        from app.services.pipeline_runner import PipelineRunner
        with tempfile.TemporaryDirectory() as temp:
            projects, checkpoints, project = self._runner_at_rendered(Path(temp))
            runner = PipelineRunner(projects, checkpoints, video_probe=lambda _: 1.0)
            runner.resume("project_001")
            cache = project / "reports/quality_state.json"
            first = cache.read_bytes()
            checkpoint = checkpoints.load_latest("project_001").state
            checkpoint.update({"status": "rendered", "current_node": "quality"})
            checkpoint.pop("waiting_for", None)
            checkpoints.save_checkpoint("project_001", checkpoint)
            (project / "render/story.mp4").write_bytes(
                b"\x00\x00\x00\x18ftypisom" + b"changed-video-bytes"
            )

            PipelineRunner(projects, checkpoints, video_probe=lambda _: 1.0).resume("project_001")

            self.assertNotEqual(cache.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
