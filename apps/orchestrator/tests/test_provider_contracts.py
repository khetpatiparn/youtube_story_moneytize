import asyncio
import unittest


class ProviderContractTests(unittest.TestCase):
    def test_stable_prompt_hash_ignores_whitespace_and_option_order(self):
        from app.providers.contracts import stable_prompt_hash

        first = stable_prompt_hash(
            model="fake-model",
            prompt="  generate   a village scene ",
            options={"seed": 42, "style": "simple"},
        )
        second = stable_prompt_hash(
            model="fake-model",
            prompt="generate a village scene",
            options={"style": "simple", "seed": 42},
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_fake_llm_provider_satisfies_structured_output_contract(self):
        from app.providers.contracts import assert_llm_provider_contract
        from app.providers.fake import FakeLLMProvider

        result = asyncio.run(assert_llm_provider_contract(FakeLLMProvider()))

        self.assertEqual(result.provider, "fake-llm")
        self.assertEqual(result.model, "fake-llm-model")
        self.assertEqual(result.output["status"], "ok")
        self.assertEqual(result.usage["prompt_tokens"], 4)
        self.assertEqual(len(result.prompt_hash), 64)

    def test_fake_image_provider_satisfies_generation_contract(self):
        from app.providers.contracts import assert_image_provider_contract
        from app.providers.fake import FakeImageProvider

        result = asyncio.run(assert_image_provider_contract(FakeImageProvider()))

        self.assertEqual(result.provider, "fake-image")
        self.assertEqual(result.model, "fake-image-model")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.seed, 42)
        self.assertEqual(result.mime_type, "image/png")
        self.assertTrue(result.output_path.endswith(".png"))
        self.assertEqual(len(result.prompt_hash), 64)

    def test_fake_tts_provider_satisfies_audio_contract(self):
        from app.providers.contracts import assert_tts_provider_contract
        from app.providers.fake import FakeTTSProvider

        result = asyncio.run(assert_tts_provider_contract(FakeTTSProvider()))

        self.assertEqual(result.provider, "fake-tts")
        self.assertEqual(result.model, "fake-tts-model")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.voice_id, "narrator-th")
        self.assertEqual(result.output_path, "projects/project_001/audio/narration.wav")
        self.assertGreater(result.duration_seconds, 0)


if __name__ == "__main__":
    unittest.main()
