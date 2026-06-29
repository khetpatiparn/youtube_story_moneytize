# End-to-End Local Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a credential-free local workflow that creates content, pauses at both approval gates, generates scene media and narration, renders a real MP4, writes QA reports, and resumes safely from SQLite checkpoints.

**Architecture:** A synchronous `PipelineRunner` coordinates small deterministic services and saves state after every validated transition. Reviewable project files remain the artifact source of truth, SQLite stores resume state, and existing provider protocols, reporting, renderer, and dashboard contracts are extended rather than replaced.

**Tech Stack:** Python 3.11+, `unittest`, SQLite, WAV/PCM standard library, SVG, Node.js, React 19, Remotion 4, Vite.

---

## File Map

- `apps/orchestrator/src/app/services/artifacts.py`: project-relative path validation and atomic JSON/text writes.
- `apps/orchestrator/src/app/providers/local.py`: deterministic structured content, SVG image, and WAV narration providers.
- `apps/orchestrator/src/app/services/content_pipeline.py`: outline, script, and scene artifact creation.
- `apps/orchestrator/src/app/services/image_pipeline.py`: per-scene image jobs and bounded retry.
- `apps/orchestrator/src/app/services/timeline.py`: WAV duration reading and exact frame allocation.
- `apps/orchestrator/src/app/services/rendering.py`: runtime payload staging and Remotion subprocess boundary.
- `apps/orchestrator/src/app/services/quality.py`: deterministic artifact and timeline validation.
- `apps/orchestrator/src/app/services/pipeline_runner.py`: resumable state transitions and approval gates.
- `apps/orchestrator/src/app/cli/main.py`: CLI wiring for run, resume, and approval/checkpoint synchronization.
- `apps/renderer/src/index.tsx`: runtime props and narration audio rendering.
- `apps/orchestrator/tests/test_*.py`: focused unit and integration evidence.
- `apps/orchestrator/tests/test_end_to_end.py`: real CLI-to-MP4 acceptance path.

## Task 1: Safe Artifact Storage

**Files:**
- Create: `apps/orchestrator/src/app/services/artifacts.py`
- Create: `apps/orchestrator/tests/test_artifacts.py`

- [ ] **Step 1: Write failing path and atomic-write tests**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from app.services.artifacts import ArtifactStore


class ArtifactStoreTests(unittest.TestCase):
    def test_writes_json_and_text_inside_project(self):
        with TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            store.write_json("content/outline.json", {"title": "River"})
            store.write_text("content/script.txt", "Narration")
            self.assertEqual(store.read_json("content/outline.json")["title"], "River")
            self.assertEqual(store.read_text("content/script.txt"), "Narration")

    def test_rejects_absolute_and_parent_paths(self):
        with TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            with self.assertRaises(ValueError):
                store.write_text("../escape.txt", "bad")
            with self.assertRaises(ValueError):
                store.write_text(str(Path(directory).resolve() / "absolute.txt"), "bad")
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator.tests.test_artifacts
```

Expected: import failure for `app.services.artifacts`.

- [ ] **Step 3: Implement the artifact store**

```python
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        self.project_dir.mkdir(parents=True, exist_ok=True)

    def path(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("artifact path must be relative and stay inside the project")
        resolved = (self.project_dir / candidate).resolve()
        if self.project_dir != resolved and self.project_dir not in resolved.parents:
            raise ValueError("artifact path must stay inside the project")
        return resolved

    def write_text(self, relative_path: str, value: str) -> str:
        destination = self.path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, destination)
        return relative_path.replace("\\", "/")

    def write_json(self, relative_path: str, value: Any) -> str:
        return self.write_text(relative_path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def read_text(self, relative_path: str) -> str:
        return self.path(relative_path).read_text(encoding="utf-8")

    def read_json(self, relative_path: str) -> Any:
        return json.loads(self.read_text(relative_path))
```

- [ ] **Step 4: Run the test and confirm GREEN**

Run the Task 1 command. Expected: 2 tests pass.

- [ ] **Step 5: Commit the milestone**

```powershell
git add apps/orchestrator/src/app/services/artifacts.py apps/orchestrator/tests/test_artifacts.py
git commit -m "feat: add safe project artifact store"
```

## Task 2: Deterministic Content Artifacts

**Files:**
- Create: `apps/orchestrator/src/app/providers/local.py`
- Create: `apps/orchestrator/src/app/services/content_pipeline.py`
- Create: `apps/orchestrator/tests/test_local_content_pipeline.py`
- Modify: `apps/orchestrator/src/app/schemas/state.py`

- [ ] **Step 1: Write a failing deterministic-content test**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.artifacts import ArtifactStore
from app.services.content_pipeline import ContentPipeline


class LocalContentPipelineTests(unittest.TestCase):
    def test_same_input_writes_same_outline_script_and_scenes(self):
        state = {
            "project_id": "sample_story",
            "topic": "A river spirit teaches patience",
            "target_duration_seconds": 30,
            "target_language": "th",
            "channel_style_profile": "simple_story_th",
            "script_version": 1,
        }
        with TemporaryDirectory() as left, TemporaryDirectory() as right:
            first = ContentPipeline(ArtifactStore(Path(left))).generate(state)
            second = ContentPipeline(ArtifactStore(Path(right))).generate(state)
            self.assertEqual(first["outline"], second["outline"])
            self.assertEqual(first["script"], second["script"])
            self.assertEqual(first["scenes"], second["scenes"])
            self.assertGreaterEqual(len(first["scenes"]), 3)
            self.assertTrue(Path(left, "content", "outline.json").is_file())
            self.assertTrue(Path(left, "content", "script.txt").is_file())
            self.assertTrue(Path(left, "scenes", "scenes.json").is_file())
```

- [ ] **Step 2: Run the content test and confirm RED**

Run:

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator.tests.test_local_content_pipeline
```

Expected: import failure for `ContentPipeline`.

- [ ] **Step 3: Implement deterministic structured content**

Create `local.py` with `LocalLLMProvider.generate_story(...)`. It must normalize the
topic, derive `scene_count = max(3, min(8, round(duration / 10)))`, emit stable scene
IDs `scene_001` onward, and return this exact shape:

```python
{
    "outline": {"title": topic, "beats": [str, ...]},
    "script": "\n\n".join(scene["narration"] for scene in scenes),
    "scenes": [
        {
            "scene_id": "scene_001",
            "title": str,
            "narration": str,
            "prompt": str,
            "motion": "slow_push",
            "focal_point": [0.5, 0.5],
        }
    ],
}
```

`ContentPipeline.generate(state)` must call that provider, atomically write
`content/outline.json`, `content/script.txt`, and `scenes/scenes.json`, and return a
new state containing `outline`, `script`, `scenes`, `scene_count`,
`script_version`, `status="content_ready"`, and `current_node="content"`.

- [ ] **Step 4: Add explicit artifact fields to `VideoProjectState`**

```python
outline_path: str | None
script_path: str | None
scenes_path: str | None
```

- [ ] **Step 5: Run the test and full orchestrator suite**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator.tests.test_local_content_pipeline
python -m unittest discover apps/orchestrator/tests
```

Expected: content test and all existing tests pass.

- [ ] **Step 6: Commit the milestone**

```powershell
git add apps/orchestrator/src/app/providers/local.py apps/orchestrator/src/app/services/content_pipeline.py apps/orchestrator/src/app/schemas/state.py apps/orchestrator/tests/test_local_content_pipeline.py
git commit -m "feat: generate deterministic story content"
```

## Task 3: Script Approval Pause and Restart Resume

**Files:**
- Create: `apps/orchestrator/src/app/services/pipeline_runner.py`
- Create: `apps/orchestrator/tests/test_pipeline_runner.py`
- Modify: `apps/orchestrator/src/app/services/approval_reporting.py`
- Modify: `apps/orchestrator/src/app/cli/main.py`

- [ ] **Step 1: Write failing approval-gate tests**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import CreateProjectRequest
from app.services.pipeline_runner import PipelineRunner


class PipelineRunnerApprovalTests(unittest.TestCase):
    def test_first_run_stops_and_persists_at_script_approval(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            projects = ProjectRepository(root / "projects")
            projects.create_project(CreateProjectRequest("River", 30, "simple_story_th"), "sample")
            checkpoints = CheckpointRepository(root / "checkpoints.sqlite")
            result = PipelineRunner(projects, checkpoints).run("sample")
            self.assertEqual(result["status"], "awaiting_script_approval")
            self.assertEqual(result["waiting_for"], "script")
            self.assertEqual(checkpoints.load_latest("sample").state["status"], "awaiting_script_approval")

    def test_unapproved_resume_does_not_advance(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            projects = ProjectRepository(root / "projects")
            projects.create_project(CreateProjectRequest("River", 30, "simple_story_th"), "sample")
            checkpoints = CheckpointRepository(root / "checkpoints.sqlite")
            runner = PipelineRunner(projects, checkpoints)
            runner.run("sample")
            result = PipelineRunner(projects, checkpoints).resume("sample")
            self.assertEqual(result["status"], "awaiting_script_approval")
```

- [ ] **Step 2: Run the gate tests and confirm RED**

Run:

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator.tests.test_pipeline_runner
```

Expected: import failure for `PipelineRunner`.

- [ ] **Step 3: Implement the initial runner**

`PipelineRunner.run(project_id)` loads project metadata, creates the initial state,
runs `ContentPipeline`, sets `status="awaiting_script_approval"`,
`current_node="script_approval"`, and `waiting_for="script"`, then saves both
checkpoint and metadata. `resume(project_id)` requires a checkpoint and returns the
same state until `reports/approvals.json` contains `script.approved == true`.

Use these constructor dependencies so later tasks can extend without rewriting CLI:

```python
class PipelineRunner:
    def __init__(self, projects, checkpoints, *, image_provider=None, tts_provider=None, renderer=None):
        self.projects = projects
        self.checkpoints = checkpoints
        self.image_provider = image_provider
        self.tts_provider = tts_provider
        self.renderer = renderer
```

- [ ] **Step 4: Synchronize approval commands with checkpoint state**

Add optional `checkpoints: CheckpointRepository | None` to
`ApprovalReportingService`. After an approval is written, load the latest state,
set `script_approved` or `final_approved`, update status/current node, and save it.
Pass the CLI `--checkpoint-db` argument to both approval commands; retain the default
from `CHECKPOINT_DB`.

- [ ] **Step 5: Replace hello-world CLI wiring**

`run` must instantiate `PipelineRunner` and call `run`. `resume` must call `resume`.
Both print the runner result as JSON and return zero at a normal approval pause.

- [ ] **Step 6: Run focused and full tests**

Run the Task 3 test, then `python -m unittest discover apps/orchestrator/tests`.
Expected: all tests pass.

- [ ] **Step 7: Commit the milestone**

```powershell
git add apps/orchestrator/src/app/services/pipeline_runner.py apps/orchestrator/src/app/services/approval_reporting.py apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_pipeline_runner.py
git commit -m "feat: pause and resume at script approval"
```

## Task 4: Scene Images with Bounded Retry

**Files:**
- Create: `apps/orchestrator/src/app/services/image_pipeline.py`
- Create: `apps/orchestrator/tests/test_image_pipeline.py`
- Modify: `apps/orchestrator/src/app/providers/local.py`
- Modify: `apps/orchestrator/src/app/services/pipeline_runner.py`

- [ ] **Step 1: Write failing independent-retry tests**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.providers.base import RetryableProviderError
from app.services.artifacts import ArtifactStore
from app.services.image_pipeline import ImagePipeline


class FailsSceneTwice:
    def __init__(self):
        self.calls = {}

    def generate(self, scene, output_path):
        scene_id = scene["scene_id"]
        self.calls[scene_id] = self.calls.get(scene_id, 0) + 1
        if scene_id == "scene_002" and self.calls[scene_id] < 3:
            raise RetryableProviderError("injected failure")
        Path(output_path).write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
        return {"output_path": f"images/{scene_id}.svg", "mime_type": "image/svg+xml"}


class ImagePipelineTests(unittest.TestCase):
    def test_retries_only_failed_scene_with_finite_bound(self):
        scenes = [{"scene_id": f"scene_{index:03d}", "prompt": "river"} for index in range(1, 4)]
        with TemporaryDirectory() as directory:
            provider = FailsSceneTwice()
            result = ImagePipeline(ArtifactStore(Path(directory)), provider, max_attempts=3).generate(scenes)
            self.assertEqual(provider.calls, {"scene_001": 1, "scene_002": 3, "scene_003": 1})
            self.assertEqual(result["failed_scene_ids"], [])
            self.assertEqual(result["retry_counts"]["scene_002"], 2)
```

- [ ] **Step 2: Run the image test and confirm RED**

Expected: import failure for `ImagePipeline`.

- [ ] **Step 3: Implement local SVG generation**

`LocalImageProvider.generate(scene, output_path)` derives a SHA-256 digest from
`scene_id + prompt`, selects background/accent hex colors from the digest, escapes all
text with `html.escape`, and writes a 1280x720 SVG containing the scene ID, title, and
prompt. It returns project-relative output path and `image/svg+xml`.

- [ ] **Step 4: Implement bounded retry**

`ImagePipeline.generate(scenes)` creates one job per scene, catches only
`RetryableProviderError`, retries that job until `max_attempts`, and immediately
propagates permanent/unexpected errors. It writes `images/jobs.json`, updates each
scene with `image_path`, and writes `scenes/scenes.json`. If failures remain after the
bound, raise `ImageGenerationExhausted(failed_scene_ids)` after persisting job state.

- [ ] **Step 5: Wire approved resume into image generation**

After script approval, `PipelineRunner.resume` runs `ImagePipeline`, saves
`image_jobs`, `generated_images`, `failed_scene_ids`, and `retry_counts`, then advances
to `status="media_ready"` only when no scene failed.

- [ ] **Step 6: Verify and commit**

Run the image test and full orchestrator suite. Expected: all pass.

```powershell
git add apps/orchestrator/src/app/providers/local.py apps/orchestrator/src/app/services/image_pipeline.py apps/orchestrator/src/app/services/pipeline_runner.py apps/orchestrator/tests/test_image_pipeline.py
git commit -m "feat: generate scene images with bounded retry"
```

## Task 5: Local WAV Narration and Exact Timeline

**Files:**
- Create: `apps/orchestrator/src/app/services/timeline.py`
- Create: `apps/orchestrator/tests/test_local_audio_timeline.py`
- Modify: `apps/orchestrator/src/app/providers/local.py`
- Modify: `apps/orchestrator/src/app/services/pipeline_runner.py`

- [ ] **Step 1: Write failing WAV and frame-allocation tests**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from app.providers.local import LocalTTSProvider
from app.services.timeline import build_timeline, wav_duration_seconds


class LocalAudioTimelineTests(unittest.TestCase):
    def test_wav_duration_drives_contiguous_scene_frames(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "narration.wav"
            result = LocalTTSProvider(words_per_second=4).synthesize_sync("one two three four eight words total here", path)
            self.assertAlmostEqual(wav_duration_seconds(path), result.duration_seconds, places=2)
            scenes = [
                {"scene_id": "scene_001", "narration": "one two"},
                {"scene_id": "scene_002", "narration": "three four eight words total here"},
            ]
            timeline = build_timeline(scenes, result.duration_seconds, fps=30)
            self.assertEqual(timeline[0]["start_frame"], 0)
            self.assertEqual(timeline[1]["start_frame"], timeline[0]["duration_in_frames"])
            self.assertEqual(sum(item["duration_in_frames"] for item in timeline), round(result.duration_seconds * 30))
```

- [ ] **Step 2: Run the audio test and confirm RED**

Expected: missing local provider/timeline API.

- [ ] **Step 3: Implement valid deterministic WAV output**

`LocalTTSProvider.synthesize_sync(text, output_path)` uses `wave`, 16-bit mono PCM,
22,050 Hz, and alternating 220/330 Hz low-amplitude tones separated by short silence.
Duration is `max(1.0, word_count / words_per_second)`. It returns the existing
`AudioResult`. The async protocol method delegates to the sync method.

- [ ] **Step 4: Implement exact timeline allocation**

`wav_duration_seconds` reads frames/rate. `build_timeline` assigns at least one frame
per scene proportional to narration word counts, uses cumulative starts, and applies
all rounding remainder to the final scene so total frames equal
`round(audio_duration_seconds * fps)`.

- [ ] **Step 5: Wire narration and timeline into the runner**

Write `audio/narration.wav` and `render/render_payload.json`. Payload fields are
`fps=30`, `width=1280`, `height=720`, `audioPath`, and camelCase scene values expected
by `validateRenderPayload`. Save `voice_path`, `audio_duration_seconds`, `timeline`,
and `render_payload_path` into the checkpoint.

- [ ] **Step 6: Verify and commit**

Run focused/full orchestrator tests. Expected: all pass.

```powershell
git add apps/orchestrator/src/app/providers/local.py apps/orchestrator/src/app/services/timeline.py apps/orchestrator/src/app/services/pipeline_runner.py apps/orchestrator/tests/test_local_audio_timeline.py
git commit -m "feat: build narration-driven timeline"
```

## Task 6: Runtime Remotion Render with Audio

**Files:**
- Create: `apps/orchestrator/src/app/services/rendering.py`
- Create: `apps/orchestrator/tests/test_rendering.py`
- Modify: `apps/renderer/src/index.tsx`
- Modify: `apps/renderer/tests/remotionManifest.test.mjs`
- Modify: `apps/orchestrator/src/app/services/pipeline_runner.py`
- Modify: `package.json`

- [ ] **Step 1: Write failing renderer contract assertions**

Extend `remotionManifest.test.mjs` to require `Audio`, runtime `inputProps`, and no
hard dependency on the sample payload for duration calculation:

```javascript
assert.match(entrySource, /Audio/);
assert.match(entrySource, /inputProps/);
assert.match(entrySource, /audioPath/);
```

Write `test_rendering.py`:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.rendering import RemotionRenderer


class RenderingTests(unittest.TestCase):
    def test_rejects_success_without_nonempty_video(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "render_payload.json"
            payload.write_text("{}", encoding="utf-8")
            renderer = RemotionRenderer(root, command_runner=lambda command: 0)
            with self.assertRaisesRegex(RuntimeError, "non-empty"):
                renderer.render(payload, root / "story.mp4")
```

- [ ] **Step 2: Run renderer tests and confirm RED**

Run:

```powershell
npm.cmd run test:renderer
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator.tests.test_rendering
```

Expected: new assertions/import fail.

- [ ] **Step 3: Make the composition runtime-driven**

Use Remotion `getInputProps()` to validate runtime props when supplied and fall back
to the sample only for Studio/default execution. `StoryVideo` accepts `audioPath` and
renders `<Audio src={staticFile(audioPath)} />` before scene sequences. Composition
dimensions, FPS, and duration derive from the selected validated payload.

- [ ] **Step 4: Implement the subprocess boundary**

`RemotionRenderer.render(payload_path, output_path)` stages project media into
`apps/renderer/public/projects/{project_id}/`, invokes:

```powershell
npm.cmd exec remotion render apps/renderer/src/index.tsx YouTubeStory <output> --props <payload>
```

Use `subprocess.run(..., check=False, capture_output=True, text=True)`. On non-zero
exit raise `RuntimeError` containing stderr. On zero exit require an existing non-empty
MP4. Return its project-relative path. The injected `command_runner` receives the full
argument list for unit tests.

- [ ] **Step 5: Wire rendering and checkpoint semantics**

The runner sets `status="render_ready"` only after payload validation, then calls the
renderer. Save `video_path` and the checkpoint only after the MP4 exists. A failure
leaves the prior render-ready checkpoint so a new `resume` retries exactly once per
invocation.

- [ ] **Step 6: Verify and commit**

Run renderer, focused Python, and full Python suites. Expected: all pass.

```powershell
git add apps/orchestrator/src/app/services/rendering.py apps/orchestrator/src/app/services/pipeline_runner.py apps/orchestrator/tests/test_rendering.py apps/renderer/src/index.tsx apps/renderer/tests/remotionManifest.test.mjs package.json
git commit -m "feat: render runtime project media with audio"
```

## Task 7: Quality Reports and Final Approval Gate

**Files:**
- Create: `apps/orchestrator/src/app/services/quality.py`
- Create: `apps/orchestrator/tests/test_quality_pipeline.py`
- Modify: `apps/orchestrator/src/app/services/pipeline_runner.py`
- Modify: `apps/orchestrator/src/app/services/approval_reporting.py`

- [ ] **Step 1: Write failing quality and final-gate tests**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.quality import validate_project_media


class QualityPipelineTests(unittest.TestCase):
    def test_reports_missing_and_noncontiguous_media(self):
        with TemporaryDirectory() as directory:
            issues = validate_project_media(
                Path(directory),
                scenes=[{"scene_id": "scene_001", "image_path": "images/missing.svg"}],
                timeline=[{"scene_id": "scene_001", "start_frame": 2, "duration_in_frames": 30}],
                audio_path="audio/missing.wav",
                video_path="render/missing.mp4",
            )
            self.assertIn("scene_001 image is missing", issues)
            self.assertIn("timeline must start at frame 0", issues)
            self.assertIn("narration audio is missing", issues)
            self.assertIn("rendered video is missing", issues)
```

Add a runner integration test proving the post-render state is
`awaiting_final_approval` and that final approval plus a fresh `resume` produces
`status="completed"` without changing image/WAV/MP4 modification times.

- [ ] **Step 2: Run focused tests and confirm RED**

Expected: missing quality service and final transition.

- [ ] **Step 3: Implement deterministic QA**

`validate_project_media` checks image presence/non-zero size, timeline start and
contiguity, WAV presence/non-zero size, MP4 presence/non-zero size, and one timeline
entry per scene. `quality_score = passed_checks / total_checks`. Feed issues and score
to the existing `ApprovalReportingService.write_project_reports`.

- [ ] **Step 4: Implement the final gate**

After reports exist, save `status="awaiting_final_approval"`,
`current_node="final_approval"`, and `waiting_for="final"`. Resume cannot advance
without `final.approved == true`. Once approved, set `status="completed"`,
`current_node="complete"`, clear `waiting_for`, persist checkpoint/metadata, and do
not rerun media nodes.

- [ ] **Step 5: Verify and commit**

Run quality, runner, approval-reporting, and full orchestrator tests. Expected: pass.

```powershell
git add apps/orchestrator/src/app/services/quality.py apps/orchestrator/src/app/services/pipeline_runner.py apps/orchestrator/src/app/services/approval_reporting.py apps/orchestrator/tests/test_quality_pipeline.py apps/orchestrator/tests/test_pipeline_runner.py
git commit -m "feat: validate media and gate final approval"
```

## Task 8: Real End-to-End CLI and Dashboard Evidence

**Files:**
- Create: `apps/orchestrator/tests/test_end_to_end.py`
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Modify: `apps/dashboard/tests/loadProjects.test.mjs`
- Modify: `apps/dashboard/src/data/loadProjects.js`

- [ ] **Step 1: Write the failing CLI acceptance test**

The test uses a temporary projects directory and checkpoint DB, calls `main([...])`
in separate invocations, and captures stdout. It must assert:

```python
self.assertEqual(first_run["status"], "awaiting_script_approval")
self.assertEqual(after_script_approval["status"], "awaiting_final_approval")
self.assertEqual(completed["status"], "completed")
self.assertGreater((project_dir / "audio/narration.wav").stat().st_size, 44)
self.assertGreater((project_dir / "render/story.mp4").stat().st_size, 0)
self.assertTrue((project_dir / "reports/quality_report.json").is_file())
```

Mark only the real Remotion assertion with a clear skip when `node_modules` is absent;
the repository verification environment has dependencies installed and must execute it.

- [ ] **Step 2: Run the end-to-end test and confirm RED**

Run:

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator.tests.test_end_to_end
```

Expected: failure at the first incomplete CLI/media behavior.

- [ ] **Step 3: Complete CLI dependency construction**

Create local providers and `RemotionRenderer` inside one `_build_pipeline_runner(args)`
helper. Add `--max-image-attempts` defaulting to 3 and keep all paths rooted in the
selected project directory. JSON output always includes `project_id`, `status`,
`current_node`, and `waiting_for` when paused.

- [ ] **Step 4: Align dashboard metadata filename and fields**

The repository currently writes `project.json`; dashboard live loading expects
`metadata.json`. Make the dashboard accept `project.json` first and retain
`metadata.json` compatibility. Add a test that loads the completed project schema and
asserts its status, scenes, quality score, approvals, and real report availability.

- [ ] **Step 5: Run real acceptance and browser-data suites**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator.tests.test_end_to_end
npm.cmd run test:dashboard
npm.cmd run prepare:dashboard-data
```

Expected: real MP4 acceptance passes and exported dashboard data has `source="live"`.

- [ ] **Step 6: Commit the milestone**

```powershell
git add apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_end_to_end.py apps/dashboard/src/data/loadProjects.js apps/dashboard/tests/loadProjects.test.mjs
git commit -m "test: prove end-to-end local story workflow"
```

## Task 9: Documentation, Sample Render, and Completion Audit

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `goals/e2e-pipeline-poc.md`

- [ ] **Step 1: Add the verified CLI sequence and limitations**

Document the exact create/run/approve/resume sequence from the design, explain both
approval pauses, list all generated artifacts, and state explicitly:

- Local content is deterministic template output, not a production LLM.
- Local SVG images demonstrate orchestration, not production illustration quality.
- Local WAV narration is synthetic tones, not natural speech.
- YouTube upload is not implemented.

- [ ] **Step 2: Add recovery and verification commands to AGENTS**

Document `test_end_to_end`, the bounded image retry rule, render retry-by-resume, and
the requirement to preserve the latest valid checkpoint. Mark the goal file complete
only after every command below passes and the sample artifact is inspected.

- [ ] **Step 3: Run the sample project from a clean sample ID**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m app create --project-id sample_story --topic "A river spirit teaches patience" --duration 30 --profile simple_story_th
python -m app run --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-script --project-id sample_story --approved --reviewer human --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-final --project-id sample_story --approved --reviewer human --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app status --project-id sample_story
```

Expected: the three workflow statuses are script pause, final pause, and completed;
`projects/sample_story/render/story.mp4` is non-empty.

- [ ] **Step 4: Run the complete verification matrix**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
python -m compileall apps/orchestrator/src
npm.cmd run test:renderer
npm.cmd run test:dashboard
npm.cmd run build:dashboard
git diff --check
git status --short --branch
```

Expected: all tests/builds pass, compileall succeeds, no whitespace errors, and only
intentional documentation changes remain before the final commit.

- [ ] **Step 5: Review the complete feature diff against the design**

Confirm every acceptance criterion in
`docs/superpowers/specs/2026-06-29-end-to-end-local-pipeline-design.md` has direct test,
artifact, or command evidence. Record any production-provider limitation in README;
do not infer completion from unit tests alone.

- [ ] **Step 6: Commit documentation and goal completion evidence**

```powershell
git add README.md AGENTS.md goals/e2e-pipeline-poc.md
git commit -m "docs: document end-to-end local workflow"
```

