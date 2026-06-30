import base64
import io
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from PIL import Image


def jpeg_bytes():
    output = io.BytesIO()
    Image.new("RGB", (512, 512), "navy").save(output, format="JPEG")
    return output.getvalue()


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def run(self, *, model, payload):
        self.calls.append({"model": model, "payload": payload})
        if self.error:
            raise self.error
        return self.response


class FakeHTTPResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body[:size]


class CloudflareImageProviderTests(unittest.TestCase):
    _DEFAULT = object()

    def _provider(self, root, response=_DEFAULT, **kwargs):
        from app.providers.cloudflare_image import CloudflareImageProvider
        from app.services.artifacts import ArtifactStore

        if response is self._DEFAULT:
            response = {"result": {"image": base64.b64encode(jpeg_bytes()).decode()}}
        client = FakeClient(response)
        return CloudflareImageProvider(ArtifactStore(root), client, **kwargs), client

    def _scene(self, **changes):
        scene = {
            "scene_id": "scene_007",
            "title": "The clever rabbit",
            "prompt": "a rabbit faces a giant beneath banyan trees",
            "narration": "The small rabbit calmly prepares a clever plan.",
        }
        scene.update(changes)
        return scene

    def test_generates_valid_jpeg_with_deterministic_bounded_prompt_and_seed(self):
        with tempfile.TemporaryDirectory() as root:
            provider, client = self._provider(root)
            result = provider.generate(self._scene(narration="story " * 1000), "images/scene_007.jpg")
            second = provider.generate(self._scene(narration="story " * 1000), "images/again.jpg")

            self.assertEqual(result["provider"], "cloudflare")
            self.assertEqual(result["model"], "@cf/black-forest-labs/flux-1-schnell")
            self.assertEqual(result["mime_type"], "image/jpeg")
            self.assertTrue(result["output_path"].endswith(".jpg"))
            payload = client.calls[0]["payload"]
            self.assertEqual(payload["steps"], 4)
            self.assertIn("no text", payload["prompt"])
            self.assertIn("Thai folktale", payload["prompt"])
            self.assertIn("The clever rabbit", payload["prompt"])
            self.assertIn("banyan trees", payload["prompt"])
            self.assertLessEqual(len(payload["prompt"]), 2048)
            self.assertEqual(payload["seed"], client.calls[1]["payload"]["seed"])
            self.assertLessEqual(payload["seed"], 2**31 - 1)
            self.assertNotIn("credential", json.dumps(payload).lower())
            self.assertEqual(Path(root, result["output_path"]).read_bytes(), jpeg_bytes())

    def test_constructor_and_prompt_bounds_are_enforced(self):
        from app.providers.base import PermanentProviderError

        with tempfile.TemporaryDirectory() as root:
            for steps in (0, 9):
                with self.subTest(steps=steps), self.assertRaises(ValueError):
                    self._provider(root, steps=steps)
            provider, client = self._provider(root, steps=1)
            provider.generate(self._scene(title="T" * 3000, prompt="P" * 3000), "out.jpg")
            self.assertLessEqual(len(client.calls[0]["payload"]["prompt"]), 2048)
            with self.assertRaises(PermanentProviderError):
                provider.generate(self._scene(scene_id=""), "next.jpg")

    def test_invalid_responses_and_paths_preserve_existing_jpeg(self):
        from app.providers.base import PermanentProviderError

        failures = [
            {},
            {"result": {}},
            {"result": {"image": "%%%"}},
            {"result": {"image": base64.b64encode(b"not jpeg").decode()}},
        ]
        with tempfile.TemporaryDirectory() as root:
            output = Path(root, "images/existing.jpg")
            output.parent.mkdir()
            original = jpeg_bytes()
            output.write_bytes(original)
            for response in failures:
                with self.subTest(response=response):
                    provider, _ = self._provider(root, response=response)
                    with self.assertRaises(PermanentProviderError):
                        provider.generate(self._scene(), "images/existing.jpg")
                    self.assertEqual(output.read_bytes(), original)
            provider, client = self._provider(root)
            with self.assertRaises(PermanentProviderError):
                provider.generate(self._scene(), "../escape.jpg")
            self.assertEqual(client.calls, [])

    def test_client_exceptions_are_sanitized_and_preserve_existing_file(self):
        from app.providers.base import PermanentProviderError

        with tempfile.TemporaryDirectory() as root:
            output = Path(root, "out.jpg")
            output.write_bytes(jpeg_bytes())
            provider, client = self._provider(root)
            client.error = RuntimeError("secret-token raw response")
            with self.assertRaises(PermanentProviderError) as raised:
                provider.generate(self._scene(), "out.jpg")
            self.assertNotIn("secret-token", str(raised.exception))
            self.assertNotIn("raw response", str(raised.exception))
            self.assertEqual(output.read_bytes(), jpeg_bytes())


class CloudflareRESTImageClientTests(unittest.TestCase):
    def _client(self, **kwargs):
        from app.providers.cloudflare_image import CloudflareRESTImageClient

        return CloudflareRESTImageClient("account/id", "secret-token", **kwargs)

    def test_posts_json_to_correct_url_and_returns_standard_envelope(self):
        envelope = {"success": True, "result": {"image": "abc"}, "errors": []}
        seen = {}

        def fake_urlopen(request, timeout):
            seen.update(request=request, timeout=timeout)
            return FakeHTTPResponse(json.dumps(envelope).encode())

        with patch("app.providers.cloudflare_image.urlopen", fake_urlopen):
            result = self._client(timeout_seconds=12).run(
                model="@cf/black-forest-labs/flux-1-schnell",
                payload={"prompt": "safe", "steps": 4},
            )
        request = seen["request"]
        self.assertEqual(result, envelope)
        self.assertEqual(seen["timeout"], 12)
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("accounts/account%2Fid/ai/run/@cf/black-forest-labs/flux-1-schnell", request.full_url)
        self.assertEqual(request.headers["Authorization"], "Bearer secret-token")
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertEqual(json.loads(request.data), {"prompt": "safe", "steps": 4})

    def test_retryable_transport_and_http_failures_are_sanitized(self):
        from app.providers.base import RetryableProviderError

        errors = [
            socket.timeout("secret-token raw response"),
            TimeoutError("secret-token"),
            URLError("secret-token"),
            HTTPError("https://secret", 429, "raw response", {}, None),
            HTTPError("https://secret", 503, "raw response", {}, None),
        ]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch(
                "app.providers.cloudflare_image.urlopen", side_effect=error
            ):
                with self.assertRaises(RetryableProviderError) as raised:
                    self._client().run(model="@cf/test/model", payload={"prompt": "private"})
                self.assertNotIn("secret", str(raised.exception).lower())
                self.assertNotIn("private", str(raised.exception).lower())

    def test_permanent_http_json_and_envelope_failures_are_sanitized(self):
        from app.providers.base import PermanentProviderError

        responses = [
            HTTPError("https://secret", 400, "raw response", {}, None),
            FakeHTTPResponse(b"not json secret-token"),
            FakeHTTPResponse(json.dumps({"success": False, "errors": ["secret-token"]}).encode()),
            FakeHTTPResponse(json.dumps({"success": True, "result": "wrong"}).encode()),
        ]
        for response in responses:
            with self.subTest(response=type(response).__name__):
                target = patch("app.providers.cloudflare_image.urlopen", side_effect=response) if isinstance(response, Exception) else patch("app.providers.cloudflare_image.urlopen", return_value=response)
                with target, self.assertRaises(PermanentProviderError) as raised:
                    self._client().run(model="@cf/test/model", payload={"prompt": "private"})
                message = str(raised.exception).lower()
                self.assertNotIn("secret", message)
                self.assertNotIn("private", message)

    def test_rejects_oversized_response_and_invalid_configuration(self):
        from app.providers.cloudflare_image import CloudflareRESTImageClient
        from app.providers.base import PermanentProviderError

        with patch("app.providers.cloudflare_image.urlopen", return_value=FakeHTTPResponse(b"x" * 11)):
            with self.assertRaises(PermanentProviderError):
                self._client(max_response_bytes=10).run(model="@cf/test", payload={})
        for args in (("", "token"), ("account", "")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                CloudflareRESTImageClient(*args)
        for kwargs in ({"timeout_seconds": 0}, {"max_response_bytes": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CloudflareRESTImageClient("account", "token", **kwargs)


if __name__ == "__main__":
    unittest.main()
