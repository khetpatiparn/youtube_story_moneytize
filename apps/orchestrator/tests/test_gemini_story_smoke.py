import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.providers.base import PermanentProviderError, RetryableProviderError


class FakeStoryClient:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = []

    def generate_story(self, *, model, prompt, response_schema, temperature):
        self.calls.append(
            {
                "model": model,
                "prompt": prompt,
                "response_schema": response_schema,
                "temperature": temperature,
            }
        )
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return {
            "story_title": "เรื่องเล่าริมน้ำ",
            "scenes": [
                {
                    "title": "หนึ่ง",
                    "narration": "คำบรรยายภาษาไทยฉากหนึ่ง",
                    "image_prompt": "english prompt one",
                },
                {
                    "title": "สอง",
                    "narration": "คำบรรยายภาษาไทยฉากสอง",
                    "image_prompt": "english prompt two",
                },
                {
                    "title": "สาม",
                    "narration": "คำบรรยายภาษาไทยฉากสาม",
                    "image_prompt": "english prompt three",
                },
            ],
        }


class GeminiStorySmokeTests(unittest.TestCase):
    def _args(self, **changes):
        values = {
            "topic": "วิญญาณแม่น้ำผู้พิทักษ์หมู่บ้าน",
            "duration": 30,
            "profile": "simple_story_th",
            "output": "tmp/gemini-story-smoke.json",
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def _environment(self, **changes):
        values = {
            "GEMINI_API_KEY": "secret-test-key",
            "GEMINI_LLM_MODEL": "gemini-2.5-flash",
            "GEMINI_LLM_MAX_ATTEMPTS": "3",
            "GEMINI_LLM_TEMPERATURE": "0.7",
        }
        values.update(changes)
        return values

    def _run(self, args=None, environ=None, client=None, sleep=lambda _: None):
        from app.cli.main import _smoke_google_story

        stream = io.StringIO()
        args = args or self._args()
        with tempfile.TemporaryDirectory() as root, patch(
            "app.cli.main._repository_root", return_value=Path(root)
        ):
            with redirect_stdout(stream):
                result = _smoke_google_story(
                    args,
                    environ=self._environment() if environ is None else environ,
                    client=client or FakeStoryClient(),
                    sleep=sleep,
                )
            output = Path(root, args.output)
            content = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
        return result, stream.getvalue(), content

    def test_success_writes_json_and_prints_only_exact_metadata(self):
        client = FakeStoryClient()
        result, stdout, content = self._run(client=client)
        self.assertEqual(result, 0)
        self.assertEqual(
            set(json.loads(stdout)),
            {"model", "scene_count", "script_characters", "output_path"},
        )
        metadata = json.loads(stdout)
        self.assertEqual(metadata["model"], "gemini-2.5-flash")
        self.assertEqual(metadata["scene_count"], 3)
        self.assertEqual(metadata["output_path"], "tmp/gemini-story-smoke.json")
        self.assertEqual(set(content), {"outline", "script", "scenes"})
        self.assertNotIn("secret-test-key", stdout)
        self.assertNotIn("วิญญาณแม่น้ำผู้พิทักษ์หมู่บ้าน", stdout)
        self.assertNotIn("english prompt one", stdout)
        self.assertNotIn("คำบรรยายภาษาไทยฉากหนึ่ง", stdout)

    def test_rejects_input_and_configuration_before_client_access(self):
        cases = [
            (self._args(topic=""), self._environment()),
            (self._args(topic="x" * 501), self._environment()),
            (self._args(duration=0), self._environment()),
            (self._args(profile=""), self._environment()),
            (self._args(output="/tmp/a.json"), self._environment()),
            (self._args(output="tmp/../a.json"), self._environment()),
            (self._args(output="stories/a.json"), self._environment()),
            (self._args(output="tmp/a.txt"), self._environment()),
            (self._args(), self._environment(GEMINI_API_KEY="")),
            (self._args(), self._environment(GEMINI_LLM_MAX_ATTEMPTS="0")),
        ]
        for args, environ in cases:
            client = FakeStoryClient()
            with self.subTest(args=args, environ=environ), self.assertRaises(SystemExit) as raised:
                self._run(args=args, environ=environ, client=client)
            self.assertEqual(client.calls, [])
            message = str(raised.exception)
            self.assertNotIn("secret-test-key", message)
            if args.topic:
                self.assertNotIn(args.topic, message)

    def test_retries_only_retryable_failures_with_bounded_backoff(self):
        delays = []
        client = FakeStoryClient(
            [
                RetryableProviderError("secret prompt leaked"),
                {
                    "story_title": "เรื่องเล่าริมน้ำ",
                    "scenes": [
                        {
                            "title": "หนึ่ง",
                            "narration": "คำบรรยายภาษาไทยฉากหนึ่ง",
                            "image_prompt": "english prompt one",
                        },
                        {
                            "title": "สอง",
                            "narration": "คำบรรยายภาษาไทยฉากสอง",
                            "image_prompt": "english prompt two",
                        },
                        {
                            "title": "สาม",
                            "narration": "คำบรรยายภาษาไทยฉากสาม",
                            "image_prompt": "english prompt three",
                        },
                    ],
                },
            ]
        )
        _, stdout, _ = self._run(client=client, sleep=delays.append)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(delays, [1])
        self.assertNotIn("secret", stdout)

        client = FakeStoryClient([RetryableProviderError("secret")] * 3)
        delays = []
        with self.assertRaises(SystemExit) as raised:
            self._run(client=client, sleep=delays.append)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(delays, [1, 2])
        self.assertNotIn("secret", str(raised.exception))

    def test_permanent_failure_is_not_retried_or_leaked(self):
        client = FakeStoryClient([PermanentProviderError("secret raw story")])
        with self.assertRaises(SystemExit) as raised:
            self._run(client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("raw story", str(raised.exception))

    def test_parser_routes_smoke_command_without_network(self):
        from app.cli.main import _build_parser, main

        args = _build_parser().parse_args(["smoke-google-story", "--topic", "safe", "--duration", "30", "--profile", "simple_story_th"])
        self.assertEqual(args.command, "smoke-google-story")
        self.assertEqual(args.output, "tmp/gemini-story-smoke.json")
        with patch("app.cli.main.load_environment"), patch(
            "app.cli.main._smoke_google_story", return_value=19
        ) as smoke:
            self.assertEqual(
                main(["smoke-google-story", "--topic", "safe", "--duration", "30", "--profile", "simple_story_th"]),
                19,
            )
        smoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
