import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path


def scenes():
    return [
        {
            "scene_id": f"scene_{index:03d}",
            "title": f"Title <{index}>",
            "narration": f"Narration {index}",
            "prompt": f"Prompt & <unsafe> {index}",
            "motion": "slow_push",
            "focal_point": [0.5, 0.5],
        }
        for index in range(1, 4)
    ]


class ImagePipelineTests(unittest.TestCase):
    def test_local_provider_writes_deterministic_escaped_svg(self):
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            provider = LocalImageProvider(store)
            result = provider.generate(scenes()[0], "images/scene_001.svg")
            first = store.path(result["output_path"]).read_bytes()
            result_again = provider.generate(scenes()[0], "images/scene_001.svg")

            self.assertEqual(first, store.path(result_again["output_path"]).read_bytes())
            self.assertIn(b'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"', first)
            self.assertIn(b"Title &lt;1&gt;", first)
            self.assertIn(b"Prompt &amp; &lt;unsafe&gt; 1", first)
            self.assertNotIn(b"<unsafe>", first)
            self.assertEqual(result["mime_type"], "image/svg+xml")
            self.assertEqual(result["output_path"], "images/scene_001.svg")
            self.assertNotIn(b"\r\n", first)

    def test_retries_only_failed_scene_and_records_retry_count(self):
        from app.providers.base import RetryableProviderError
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        class Flaky(LocalImageProvider):
            def __init__(self, store):
                super().__init__(store)
                self.calls = Counter()

            def generate(self, scene, output_path):
                self.calls[scene["scene_id"]] += 1
                if scene["scene_id"] == "scene_002" and self.calls[scene["scene_id"]] < 3:
                    raise RetryableProviderError("temporary")
                return super().generate(scene, output_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            provider = Flaky(store)
            result = ImagePipeline(store, provider).generate(scenes())

            self.assertEqual(provider.calls, Counter(scene_001=1, scene_002=3, scene_003=1))
            self.assertEqual(result["retry_counts"]["scene_002"], 2)
            self.assertEqual(result["failed_scene_ids"], [])
            self.assertTrue(all(job["status"] == "completed" for job in result["image_jobs"]))
            self.assertTrue(all("image_path" in scene for scene in result["scenes"]))

    def test_exhaustion_persists_consistent_jobs_and_scenes(self):
        from app.providers.base import RetryableProviderError
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImageGenerationExhausted, ImagePipeline

        class AlwaysFails:
            def __init__(self):
                self.calls = Counter()

            def generate(self, scene, output_path):
                self.calls[scene["scene_id"]] += 1
                if scene["scene_id"] == "scene_002":
                    raise RetryableProviderError("still unavailable")
                Path(output_path)  # prove output is opaque to injected providers
                return {"output_path": f"images/{scene['scene_id']}.svg", "mime_type": "image/svg+xml"}

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            provider = AlwaysFails()
            with self.assertRaises(ImageGenerationExhausted) as raised:
                ImagePipeline(store, provider, max_attempts=3).generate(scenes())

            self.assertEqual(raised.exception.failed_scene_ids, ["scene_002"])
            self.assertEqual(provider.calls["scene_002"], 3)
            jobs = store.read_json("images/jobs.json")
            persisted_scenes = store.read_json("scenes/scenes.json")
            failed = next(job for job in jobs if job["scene_id"] == "scene_002")
            self.assertEqual((failed["status"], failed["attempts"], failed["retry_count"]), ("failed", 3, 2))
            self.assertNotIn("image_path", persisted_scenes[1])
            self.assertIn("image_path", persisted_scenes[0])
            self.assertIn("image_path", persisted_scenes[2])

    def test_permanent_error_is_not_retried(self):
        from app.providers.base import PermanentProviderError
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        class PermanentFailure:
            calls = 0

            def generate(self, scene, output_path):
                self.calls += 1
                raise PermanentProviderError("bad input")

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = PermanentFailure()
            with self.assertRaises(PermanentProviderError):
                ImagePipeline(ArtifactStore(temp_dir), provider).generate(scenes())
            self.assertEqual(provider.calls, 1)

    def test_resume_skips_completed_jobs(self):
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        class Counting(LocalImageProvider):
            def __init__(self, store):
                super().__init__(store)
                self.calls = Counter()

            def generate(self, scene, output_path):
                self.calls[scene["scene_id"]] += 1
                return super().generate(scene, output_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            first_provider = Counting(store)
            first = ImagePipeline(store, first_provider).generate(scenes())
            resumed_provider = Counting(store)
            second = ImagePipeline(store, resumed_provider).generate(scenes(), existing_jobs=first["image_jobs"])

            self.assertEqual(resumed_provider.calls, Counter())
            self.assertEqual(second["generated_images"], first["generated_images"])

    def test_resume_does_not_exceed_persisted_attempt_limit(self):
        from app.providers.base import RetryableProviderError
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImageGenerationExhausted, ImagePipeline

        class Failure:
            calls = 0

            def generate(self, scene, output_path):
                self.calls += 1
                raise RetryableProviderError("no")

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = Failure()
            job = {"scene_id": "scene_001", "status": "failed", "attempts": 3, "retry_count": 2, "error": "no"}
            with self.assertRaises(ImageGenerationExhausted):
                ImagePipeline(ArtifactStore(temp_dir), provider).generate(scenes()[:1], existing_jobs=[job])
            self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
