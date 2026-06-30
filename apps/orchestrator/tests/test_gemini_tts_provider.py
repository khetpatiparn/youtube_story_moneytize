import asyncio
import tempfile
import unittest
from pathlib import Path


class FakeSpeechClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def generate_pcm(self, *, model, prompt, voice):
        self.calls.append({"model": model, "prompt": prompt, "voice": voice})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class GeminiTTSProviderTests(unittest.TestCase):
    def _provider(self, root, responses, **kwargs):
        from app.providers.gemini_tts import GeminiTTSProvider
        from app.services.artifacts import ArtifactStore

        client = FakeSpeechClient(responses)
        provider = GeminiTTSProvider(
            ArtifactStore(root),
            api_key="secret-test-key",
            client=client,
            sleep=lambda _: asyncio.sleep(0),
            **kwargs,
        )
        return provider, client

    def test_synthesize_preserves_paragraph_order_and_writes_24khz_wav(self):
        from app.services.timeline import wav_metadata

        first_pcm = b"\x01\x00" * 120
        second_pcm = b"\x02\x00" * 240
        with tempfile.TemporaryDirectory() as temp_dir:
            provider, client = self._provider(temp_dir, [first_pcm, second_pcm])
            result = asyncio.run(
                provider.synthesize("ย่อหน้าแรก\n\nย่อหน้าที่สอง", "Charon", "audio/narration.wav", {})
            )

            self.assertEqual((result.provider, result.model), ("google", "gemini-3.1-flash-tts-preview"))
            self.assertEqual(result.voice_id, "Charon")
            self.assertEqual([call["voice"] for call in client.calls], ["Charon", "Charon"])
            self.assertTrue(all("ภาษาไทย" in call["prompt"] for call in client.calls))
            self.assertIn("ย่อหน้าแรก", client.calls[0]["prompt"])
            self.assertIn("ย่อหน้าที่สอง", client.calls[1]["prompt"])
            path = Path(temp_dir, result.output_path)
            metadata = wav_metadata(path)
            self.assertEqual(metadata.sample_rate, 24000)
            self.assertEqual(metadata.frame_count, 360)
            self.assertEqual(result.duration_seconds, 360 / 24000)

    def test_long_text_splits_without_losing_content(self):
        text = "ประโยคหนึ่ง ประโยคสอง ประโยคสาม"
        with tempfile.TemporaryDirectory() as temp_dir:
            provider, client = self._provider(
                temp_dir, [b"\x00\x00"] * 4, chunk_character_limit=12
            )
            asyncio.run(provider.synthesize(text, "Charon", "audio/out.wav", {}))

            chunks = [call["prompt"].split("ข้อความ:\n", 1)[1] for call in client.calls]
            self.assertEqual("".join(chunks).replace(" ", ""), text.replace(" ", ""))
            self.assertTrue(all(len(chunk) <= 12 for chunk in chunks))

    def test_transient_failure_retries_with_exact_bound(self):
        from app.providers.base import RetryableProviderError

        with tempfile.TemporaryDirectory() as temp_dir:
            provider, client = self._provider(
                temp_dir,
                [RetryableProviderError("busy"), b"\x00\x00"],
                max_attempts=2,
            )
            asyncio.run(provider.synthesize("ทดสอบ", "Charon", "audio/out.wav", {}))
            self.assertEqual(len(client.calls), 2)

            provider, client = self._provider(
                temp_dir,
                [RetryableProviderError("secret-test-key raw response")] * 2,
                max_attempts=2,
            )
            with self.assertRaisesRegex(RetryableProviderError, "after 2 attempts") as raised:
                asyncio.run(provider.synthesize("ทดสอบ", "Charon", "audio/out.wav", {}))
            self.assertEqual(len(client.calls), 2)
            self.assertNotIn("secret-test-key", str(raised.exception))

    def test_invalid_pcm_and_permanent_errors_are_sanitized(self):
        from app.providers.base import PermanentProviderError

        failures = [b"", b"\x00", PermanentProviderError("secret-test-key raw")]
        with tempfile.TemporaryDirectory() as temp_dir:
            for failure in failures:
                with self.subTest(failure=type(failure).__name__):
                    provider, _ = self._provider(temp_dir, [failure])
                    with self.assertRaises(PermanentProviderError) as raised:
                        asyncio.run(provider.synthesize("ทดสอบ", "Charon", "audio/out.wav", {}))
                    self.assertNotIn("secret-test-key", str(raised.exception))

    def test_later_chunk_failure_preserves_existing_wav(self):
        from app.providers.base import PermanentProviderError

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir, "audio/out.wav")
            output.parent.mkdir(parents=True)
            output.write_bytes(b"existing")
            provider, _ = self._provider(
                temp_dir, [b"\x00\x00", PermanentProviderError("failed")]
            )
            with self.assertRaises(PermanentProviderError):
                asyncio.run(provider.synthesize("หนึ่ง\n\nสอง", "Charon", "audio/out.wav", {}))
            self.assertEqual(output.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
