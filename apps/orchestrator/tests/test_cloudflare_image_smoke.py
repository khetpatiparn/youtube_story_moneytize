import argparse
import base64
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.providers.base import PermanentProviderError, RetryableProviderError


def jpeg_bytes():
    output = io.BytesIO()
    Image.new("RGB", (512, 768), "navy").save(output, format="JPEG")
    return output.getvalue()


class FakeClient:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = []

    def run(self, *, model, payload):
        self.calls.append({"model": model, "payload": payload})
        outcome = self.outcomes.pop(0) if self.outcomes else jpeg_bytes()
        if isinstance(outcome, Exception):
            raise outcome
        return {
            "success": True,
            "result": {"image": base64.b64encode(outcome).decode()},
            "errors": [],
        }


class CloudflareImageSmokeTests(unittest.TestCase):
    def _args(self, **changes):
        values = {"prompt": "A rabbit beneath a banyan tree", "output": "tmp/cloudflare-image-smoke.jpg"}
        values.update(changes)
        return argparse.Namespace(**values)

    def _environment(self, **changes):
        values = {
            "CLOUDFLARE_ACCOUNT_ID": "account-secret",
            "CLOUDFLARE_API_TOKEN": "token-secret",
        }
        values.update(changes)
        return values

    def _run(self, args=None, environ=None, client=None, sleep=lambda _: None):
        from app.cli.main import _smoke_cloudflare_image

        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as root, patch("app.cli.main._repository_root", return_value=Path(root)):
            with redirect_stdout(stream):
                result = _smoke_cloudflare_image(
                    args or self._args(),
                    environ=self._environment() if environ is None else environ,
                    client=client or FakeClient(),
                    sleep=sleep,
                )
            output = Path(root, (args or self._args()).output)
            content = output.read_bytes() if output.exists() else None
        return result, stream.getvalue(), content

    def test_success_writes_jpeg_and_prints_only_exact_metadata(self):
        client = FakeClient()
        result, stdout, content = self._run(client=client)
        self.assertEqual(result, 0)
        self.assertEqual(content, jpeg_bytes())
        metadata = json.loads(stdout)
        self.assertEqual(
            set(metadata),
            {"model", "seed", "steps", "width", "height", "mime_type", "output_path"},
        )
        self.assertEqual(metadata["model"], "@cf/black-forest-labs/flux-1-schnell")
        self.assertEqual(metadata["steps"], 4)
        self.assertEqual((metadata["width"], metadata["height"]), (512, 768))
        self.assertEqual(metadata["mime_type"], "image/jpeg")
        self.assertEqual(metadata["output_path"], "tmp/cloudflare-image-smoke.jpg")
        self.assertNotIn("rabbit", stdout.lower())
        self.assertNotIn("account-secret", stdout)
        self.assertNotIn("token-secret", stdout)

    def test_rejects_input_and_configuration_before_client_access(self):
        cases = [
            (self._args(prompt="  "), self._environment()),
            (self._args(output="/tmp/a.jpg"), self._environment()),
            (self._args(output="tmp/../a.jpg"), self._environment()),
            (self._args(output="images/a.jpg"), self._environment()),
            (self._args(output="tmp/a.png"), self._environment()),
            (self._args(), self._environment(CLOUDFLARE_ACCOUNT_ID="")),
            (self._args(), self._environment(CLOUDFLARE_API_TOKEN="")),
            (self._args(), self._environment(CLOUDFLARE_IMAGE_MAX_ATTEMPTS="0")),
            (self._args(), self._environment(CLOUDFLARE_IMAGE_MAX_ATTEMPTS="six")),
            (self._args(), self._environment(CLOUDFLARE_IMAGE_STEPS="9")),
            (self._args(), self._environment(CLOUDFLARE_IMAGE_MODEL="owner/model")),
        ]
        for args, environ in cases:
            client = FakeClient()
            with self.subTest(args=args, environ=environ), self.assertRaises(SystemExit) as raised:
                self._run(args=args, environ=environ, client=client)
            self.assertEqual(client.calls, [])
            message = str(raised.exception)
            self.assertNotIn("account-secret", message)
            self.assertNotIn("token-secret", message)

    def test_retries_only_retryable_failures_with_bounded_backoff(self):
        delays = []
        client = FakeClient([
            RetryableProviderError("raw token-secret"),
            RetryableProviderError("raw prompt"),
            jpeg_bytes(),
        ])
        _, stdout, _ = self._run(client=client, sleep=delays.append)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(delays, [1, 2])
        self.assertNotIn("raw", stdout)

        client = FakeClient([RetryableProviderError("secret")] * 3)
        delays = []
        with self.assertRaises(SystemExit) as raised:
            self._run(client=client, sleep=delays.append)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(delays, [1, 2])
        self.assertNotIn("secret", str(raised.exception))

    def test_permanent_failure_is_not_retried_or_leaked(self):
        client = FakeClient([PermanentProviderError("token-secret raw")])
        with self.assertRaises(SystemExit) as raised:
            self._run(client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("token-secret", str(raised.exception))
        self.assertNotIn("raw", str(raised.exception))

    def test_parser_routes_smoke_command_without_network(self):
        from app.cli.main import _build_parser, main

        args = _build_parser().parse_args(["smoke-cloudflare-image", "--prompt", "safe"])
        self.assertEqual(args.command, "smoke-cloudflare-image")
        self.assertEqual(args.output, "tmp/cloudflare-image-smoke.jpg")
        with patch("app.cli.main.load_environment"), patch(
            "app.cli.main._smoke_cloudflare_image", return_value=17
        ) as smoke:
            self.assertEqual(main(["smoke-cloudflare-image", "--prompt", "safe"]), 17)
        smoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
