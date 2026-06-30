import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ProviderConfigTests(unittest.TestCase):
    def test_load_environment_does_not_override_existing_values(self):
        from app.services.config import load_environment

        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".env").write_text(
                "TTS_PROVIDER=google\nGEMINI_API_KEY=from-file\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {"TTS_PROVIDER": "local"}, clear=True):
                load_environment(Path(temp_dir))
                self.assertEqual(os.environ["TTS_PROVIDER"], "local")
                self.assertEqual(os.environ["GEMINI_API_KEY"], "from-file")

    def test_local_provider_is_default_and_requires_no_key(self):
        from app.providers.local import LocalTTSProvider
        from app.services.artifacts import ArtifactStore
        from app.services.config import build_tts_provider

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = build_tts_provider(ArtifactStore(temp_dir), {})
            self.assertIsInstance(provider, LocalTTSProvider)

    def test_google_provider_uses_validated_configuration(self):
        from app.providers.gemini_tts import GeminiTTSProvider
        from app.services.artifacts import ArtifactStore
        from app.services.config import build_tts_provider

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.services.config.GoogleGenAISpeechClient", return_value=object()):
                provider = build_tts_provider(
                    ArtifactStore(temp_dir),
                    {
                        "TTS_PROVIDER": "google",
                        "GEMINI_API_KEY": "configured-secret",
                        "GEMINI_TTS_MODEL": "test-model",
                        "GEMINI_TTS_VOICE": "Charon",
                        "GEMINI_TTS_MAX_ATTEMPTS": "4",
                    },
                )
            self.assertIsInstance(provider, GeminiTTSProvider)
            self.assertEqual((provider.model, provider.voice, provider.max_attempts), ("test-model", "Charon", 4))

    def test_google_requires_key_and_errors_do_not_disclose_credentials(self):
        from app.providers.base import PermanentProviderError
        from app.services.artifacts import ArtifactStore
        from app.services.config import build_tts_provider

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            for environ in (
                {"TTS_PROVIDER": "google", "GEMINI_API_KEY": ""},
                {"TTS_PROVIDER": "unknown", "GEMINI_API_KEY": "configured-secret"},
                {
                    "TTS_PROVIDER": "google",
                    "GEMINI_API_KEY": "configured-secret",
                    "GEMINI_TTS_MAX_ATTEMPTS": "bad",
                },
            ):
                with self.subTest(provider=environ["TTS_PROVIDER"]):
                    with self.assertRaises((PermanentProviderError, ValueError)) as raised:
                        build_tts_provider(store, environ)
                    self.assertNotIn("configured-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
