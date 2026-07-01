import tempfile
import unittest

from app.providers.base import PermanentProviderError, RetryableProviderError


class FakeGeminiStoryClient:
    def __init__(self, responses):
        self.responses = list(responses)
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
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class GeminiStoryProviderTests(unittest.TestCase):
    def _provider(self, responses, **kwargs):
        from app.providers.gemini_story import GeminiStoryProvider

        delays = []

        def sleep(delay):
            delays.append(delay)

        client = FakeGeminiStoryClient(responses)
        provider = GeminiStoryProvider(
            api_key="secret-test-key",
            client=client,
            sleep=sleep,
            **kwargs,
        )
        return provider, client, delays

    def test_generate_story_normalizes_structured_response_into_pipeline_contract(self):
        response = {
            "story_title": "วิญญาณแม่น้ำ",
            "scenes": [
                {
                    "title": "เงาสะท้อนยามเช้า",
                    "narration": "วิญญาณแม่น้ำตื่นขึ้นท่ามกลางหมอกอ่อนเหนือสายน้ำ",
                    "image_prompt": "cinematic river spirit at dawn, centered subject, no text",
                },
                {
                    "title": "เสียงเตือนจากกระแสน้ำ",
                    "narration": "เธอฟังเสียงคลื่นที่พัดข่าวร้ายมาถึงหมู่บ้านริมฝั่ง",
                    "image_prompt": "Thai riverside village, warning ripples, centered composition, no text",
                },
                {
                    "title": "คำสาบานใต้แสงทอง",
                    "narration": "ก่อนแสงอาทิตย์แรงกล้า วิญญาณให้คำมั่นว่าจะปกป้องทุกชีวิต",
                    "image_prompt": "heroic river guardian, sunrise glow, centered framing, no text",
                },
            ],
        }

        provider, client, delays = self._provider([response], model="gemini-2.5-flash", temperature=0.7)
        story = provider.generate_story("  วิญญาณ   แม่น้ำ  ", 1, "th", "simple_story_th", 1)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["model"], "gemini-2.5-flash")
        self.assertEqual(client.calls[0]["response_schema"].__name__, "GeminiStoryResponse")
        self.assertEqual(client.calls[0]["temperature"], 0.7)
        self.assertIn("exactly 3 scenes", client.calls[0]["prompt"])
        self.assertIn("Thai narration", client.calls[0]["prompt"])
        self.assertIn("English image prompts", client.calls[0]["prompt"])
        self.assertNotIn("secret-test-key", client.calls[0]["prompt"])
        self.assertEqual(story["outline"]["title"], "วิญญาณแม่น้ำ")
        self.assertEqual(story["outline"]["beats"], [scene["title"] for scene in story["scenes"]])
        self.assertEqual(story["script"], "\n\n".join(scene["narration"] for scene in story["scenes"]))
        self.assertEqual(
            [scene["scene_id"] for scene in story["scenes"]],
            ["scene_001", "scene_002", "scene_003"],
        )
        self.assertTrue(all(scene["motion"] == "slow_push" for scene in story["scenes"]))
        self.assertTrue(all(scene["focal_point"] == [0.5, 0.5] for scene in story["scenes"]))
        self.assertTrue(all(isinstance(scene["prompt"], str) and scene["prompt"] for scene in story["scenes"]))
        self.assertEqual(delays, [])

    def test_rejects_semantically_invalid_structured_output(self):
        invalid_responses = (
            {},
            {"story_title": "", "scenes": []},
            {
                "story_title": "valid",
                "scenes": [
                    {
                        "title": "duplicate",
                        "narration": "ไม่มีอักษรไทย",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "duplicate",
                        "narration": "still no thai",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "third",
                        "narration": "still no thai",
                        "image_prompt": "english prompt",
                    },
                ],
            },
            {
                "story_title": "x" * 201,
                "scenes": [
                    {
                        "title": "valid",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    }
                ]
                * 3,
            },
            {
                "story_title": "valid",
                "scenes": [
                    {
                        "title": "x" * 201,
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "second",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "third",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                ],
            },
            {
                "story_title": "valid",
                "scenes": [
                    {
                        "title": "first",
                        "narration": "ค" * 4001,
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "second",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "third",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                ],
            },
            {
                "story_title": "valid",
                "scenes": [
                    {
                        "title": "first",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "x" * 2049,
                    },
                    {
                        "title": "second",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "third",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                ],
            },
            {
                "story_title": "valid",
                "scenes": [
                    {
                        "title": "first",
                        "narration": "narration without thai",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "second",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "third",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                ],
            },
            {
                "story_title": "valid",
                "scenes": [
                    {
                        "title": "first",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                    {
                        "title": "second",
                        "narration": "คำบรรยายภาษาไทย",
                        "image_prompt": "english prompt",
                    },
                ],
            },
        )

        for response in invalid_responses:
            with self.subTest(response=response):
                provider, _, _ = self._provider([response])
                with self.assertRaises(PermanentProviderError):
                    provider.generate_story("หัวข้อ", 30, "th", "simple_story_th", 1)

    def test_retryable_failures_use_exact_bound_and_public_errors_are_sanitized(self):
        provider, client, delays = self._provider(
            [
                RetryableProviderError("secret-test-key busy prompt leaked"),
                {
                    "story_title": "เรื่องเล่า",
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
            ],
            max_attempts=2,
        )
        story = provider.generate_story("หัวข้อ", 30, "th", "simple_story_th", 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(delays, [1])
        self.assertEqual(len(story["scenes"]), 3)

        provider, client, delays = self._provider(
            [RetryableProviderError("secret-test-key raw body")] * 2,
            max_attempts=2,
        )
        with self.assertRaisesRegex(RetryableProviderError, "after 2 attempts") as raised:
            provider.generate_story("หัวข้อ", 30, "th", "simple_story_th", 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(delays, [1])
        self.assertNotIn("secret-test-key", str(raised.exception))
        self.assertNotIn("raw body", str(raised.exception))

    def test_permanent_failures_do_not_retry_and_are_sanitized(self):
        provider, client, delays = self._provider(
            [PermanentProviderError("secret-test-key raw prompt story text")],
            max_attempts=3,
        )
        with self.assertRaises(PermanentProviderError) as raised:
            provider.generate_story("หัวข้อ", 30, "th", "simple_story_th", 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(delays, [])
        self.assertNotIn("secret-test-key", str(raised.exception))
        self.assertNotIn("raw prompt", str(raised.exception))

    def test_topic_length_and_constructor_options_are_validated(self):
        from app.providers.gemini_story import GeminiStoryProvider

        with self.assertRaisesRegex(ValueError, "model"):
            GeminiStoryProvider(api_key="secret", model=" ")
        with self.assertRaisesRegex(ValueError, "max_attempts"):
            GeminiStoryProvider(api_key="secret", max_attempts=0)
        with self.assertRaisesRegex(ValueError, "temperature"):
            GeminiStoryProvider(api_key="secret", temperature=3)

        provider, _, _ = self._provider(
            [
                {
                    "story_title": "เรื่องเล่า",
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
            ]
        )
        with self.assertRaises(PermanentProviderError):
            provider.generate_story("x" * 501, 30, "th", "simple_story_th", 1)


if __name__ == "__main__":
    unittest.main()
