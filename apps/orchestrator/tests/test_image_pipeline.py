import json
import tempfile
import unittest
from collections import Counter
from unittest.mock import patch
from xml.etree import ElementTree


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

    def test_local_provider_removes_xml_illegal_characters_before_escaping(self):
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            scene = scenes()[0] | {
                "scene_id": "scene_001\x00",
                "title": "A <tag>\x01\ud800",
                "prompt": "P & Q\x0b\udfff",
            }
            result = LocalImageProvider(store).generate(scene, "images/scene_001.svg")
            content = store.path(result["output_path"]).read_bytes()

            ElementTree.fromstring(content)
            self.assertNotIn(b"\x00", content)
            self.assertIn(b"A &lt;tag&gt;", content)
            self.assertNotIn(b"\r\n", content)
            LocalImageProvider(store).generate(scene, "images/again.svg")
            self.assertEqual(content, store.path("images/again.svg").read_bytes())

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
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImageGenerationExhausted, ImagePipeline

        class AlwaysFails:
            def __init__(self, store):
                self.calls = Counter()
                self.local = LocalImageProvider(store)

            def generate(self, scene, output_path):
                self.calls[scene["scene_id"]] += 1
                if scene["scene_id"] == "scene_002":
                    raise RetryableProviderError("still unavailable")
                return self.local.generate(scene, output_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            provider = AlwaysFails(store)
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

    def test_permanent_error_persists_terminal_job_and_resume_reraises_without_call(self):
        from app.providers.base import PermanentProviderError
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        class Failure:
            calls = 0

            def generate(self, scene, output_path):
                self.calls += 1
                raise PermanentProviderError("invalid prompt")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            provider = Failure()
            with self.assertRaisesRegex(PermanentProviderError, "invalid prompt"):
                ImagePipeline(store, provider).generate(scenes()[:1])
            job = store.read_json("images/jobs.json")[0]
            self.assertEqual((job["status"], job["attempts"], job["error"]), ("permanent_failed", 1, "invalid prompt"))
            self.assertEqual(store.read_json("scenes/scenes.json"), scenes()[:1])

            with self.assertRaisesRegex(PermanentProviderError, "invalid prompt"):
                ImagePipeline(store, provider).generate(scenes()[:1])
            self.assertEqual(provider.calls, 1)

    def test_unexpected_error_persists_terminal_job_then_propagates_same_class(self):
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        class ProviderCrashed(RuntimeError):
            pass

        class Failure:
            def generate(self, scene, output_path):
                raise ProviderCrashed("boom")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            with self.assertRaises(ProviderCrashed):
                ImagePipeline(store, Failure()).generate(scenes()[:1])
            job = store.read_json("images/jobs.json")[0]
            self.assertEqual((job["status"], job["attempts"], job["error"]), ("unexpected_failed", 1, "boom"))
            self.assertEqual(store.read_json("scenes/scenes.json"), scenes()[:1])

    def test_retryable_attempt_is_persisted_before_next_attempt(self):
        from app.providers.base import RetryableProviderError
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        class InterruptAfterPersist:
            calls = 0

            def generate(self, scene, output_path):
                self.calls += 1
                raise RetryableProviderError("later")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            original = store.publish_bytes_set
            publications = 0

            def publish(artifacts):
                nonlocal publications
                result = original(artifacts)
                publications += 1
                if publications == 1:
                    raise KeyboardInterrupt()
                return result

            with patch.object(store, "publish_bytes_set", side_effect=publish):
                with self.assertRaises(KeyboardInterrupt):
                    ImagePipeline(store, InterruptAfterPersist()).generate(scenes()[:1])
            job = store.read_json("images/jobs.json")[0]
            self.assertEqual((job["attempts"], job["status"], job["retry_count"]), (1, "retrying", 0))

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

    def test_missing_completed_image_is_retried_within_attempt_budget(self):
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            job = {"scene_id": "scene_001", "status": "completed", "attempts": 1, "retry_count": 0,
                   "output_path": "images/missing.svg", "mime_type": "image/svg+xml"}
            result = ImagePipeline(store, LocalImageProvider(store)).generate(scenes()[:1], existing_jobs=[job])
            self.assertEqual(result["image_jobs"][0]["attempts"], 2)
            self.assertTrue(store.path(result["image_jobs"][0]["output_path"]).exists())

    def test_traversal_completed_job_is_rejected_without_path_escape(self):
        from app.providers.base import PermanentProviderError
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        class NeverCalled:
            def generate(self, scene, output_path):
                raise AssertionError("provider called")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            job = {"scene_id": "scene_001", "status": "completed", "attempts": 3, "retry_count": 2,
                   "output_path": "../outside.svg", "mime_type": "image/svg+xml"}
            with self.assertRaisesRegex(PermanentProviderError, "corrupt completed image job"):
                ImagePipeline(store, NeverCalled()).generate(scenes()[:1], existing_jobs=[job])
            self.assertEqual(store.read_json("images/jobs.json")[0]["status"], "permanent_failed")

    def test_completed_job_missing_required_mime_metadata_is_retried(self):
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            job = {"scene_id": "scene_001", "status": "completed", "attempts": 0,
                   "output_path": "images/old.svg"}
            result = ImagePipeline(store, LocalImageProvider(store)).generate(scenes()[:1], existing_jobs=[job])
            self.assertEqual(result["image_jobs"][0]["mime_type"], "image/svg+xml")

    def test_completed_job_without_corresponding_scene_is_rejected(self):
        from app.providers.base import PermanentProviderError
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            orphan = {"scene_id": "scene_999", "status": "completed", "attempts": 1,
                      "output_path": "../outside.svg", "mime_type": "image/svg+xml"}
            with self.assertRaisesRegex(PermanentProviderError, "no corresponding scene"):
                ImagePipeline(store, LocalImageProvider(store)).generate(scenes()[:1], existing_jobs=[orphan])

    def test_persisted_non_svg_xml_root_is_not_skipped(self):
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            store.write_text("images/old.svg", "<root/>\n")
            job = {"scene_id": "scene_001", "status": "completed", "attempts": 1,
                   "retry_count": 0, "output_path": "images/old.svg", "mime_type": "image/svg+xml"}
            result = ImagePipeline(store, LocalImageProvider(store)).generate(scenes()[:1], existing_jobs=[job])
            self.assertEqual(result["image_jobs"][0]["attempts"], 2)
            self.assertNotEqual(result["image_jobs"][0]["output_path"], "images/old.svg")

    def test_persisted_svg_requires_namespace_and_exact_canvas_attributes(self):
        from app.providers.local import LocalImageProvider
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImagePipeline

        invalid_svgs = (
            '<svg width="1280" height="720" viewBox="0 0 1280 720"/>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="720" viewBox="0 0 1280 720"/>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="700" viewBox="0 0 1280 720"/>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>',
            '<root xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"/>',
        )
        for svg in invalid_svgs:
            with self.subTest(svg=svg), tempfile.TemporaryDirectory() as temp_dir:
                store = ArtifactStore(temp_dir)
                store.write_text("images/old.svg", svg + "\n")
                job = {"scene_id": "scene_001", "status": "completed", "attempts": 1,
                       "retry_count": 0, "output_path": "images/old.svg", "mime_type": "image/svg+xml"}
                result = ImagePipeline(store, LocalImageProvider(store)).generate(scenes()[:1], existing_jobs=[job])
                self.assertEqual(result["image_jobs"][0]["attempts"], 2)

    def test_fresh_provider_nonexistent_output_exhausts_validation_retries(self):
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImageGenerationExhausted, ImagePipeline

        class MissingOutput:
            calls = 0

            def generate(self, scene, output_path):
                self.calls += 1
                return {"output_path": "images/missing.svg", "mime_type": "image/svg+xml"}

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            provider = MissingOutput()
            with self.assertRaises(ImageGenerationExhausted):
                ImagePipeline(store, provider).generate(scenes()[:1])
            job = store.read_json("images/jobs.json")[0]
            self.assertEqual((provider.calls, job["attempts"], job["status"], job["retry_count"]), (3, 3, "failed", 2))
            self.assertIn("missing or empty", job["error"])

    def test_fresh_provider_malformed_svg_never_completes(self):
        from app.services.artifacts import ArtifactStore
        from app.services.image_pipeline import ImageGenerationExhausted, ImagePipeline

        class MalformedOutput:
            def __init__(self, store):
                self.store = store
                self.calls = 0

            def generate(self, scene, output_path):
                self.calls += 1
                self.store.write_text(output_path, "<svg")
                return {"output_path": output_path, "mime_type": "image/svg+xml"}

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            provider = MalformedOutput(store)
            with self.assertRaises(ImageGenerationExhausted):
                ImagePipeline(store, provider).generate(scenes()[:1])
            job = store.read_json("images/jobs.json")[0]
            self.assertEqual((provider.calls, job["attempts"], job["status"]), (3, 3, "failed"))
            self.assertIn("not parseable", job["error"])


if __name__ == "__main__":
    unittest.main()
