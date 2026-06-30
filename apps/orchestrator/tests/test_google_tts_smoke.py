import contextlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


class FakeSpeechClient:
    async def generate_pcm(self, *, model, prompt, voice):
        return b"\x01\x00" * 240


class GoogleTTSSmokeTests(unittest.TestCase):
    def test_smoke_writes_safe_wav_and_prints_only_metadata(self):
        from app.cli.main import _smoke_google_tts

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            args = Namespace(text="ข้อความลับสำหรับทดสอบ", output="tmp/smoke.wav")
            with patch("app.cli.main._repository_root", return_value=Path(temp_dir)):
                with contextlib.redirect_stdout(stdout):
                    result = _smoke_google_tts(
                        args,
                        environ={
                            "GEMINI_API_KEY": "secret-test-key",
                            "GEMINI_TTS_MODEL": "test-model",
                            "GEMINI_TTS_VOICE": "Charon",
                        },
                        client=FakeSpeechClient(),
                    )

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(
                set(payload),
                {"model", "voice", "sample_rate", "duration_seconds", "output_path"},
            )
            self.assertEqual(payload["sample_rate"], 24000)
            self.assertEqual(payload["output_path"], "tmp/smoke.wav")
            self.assertTrue(Path(temp_dir, "tmp/smoke.wav").is_file())
            self.assertNotIn("secret-test-key", stdout.getvalue())
            self.assertNotIn(args.text, stdout.getvalue())

    def test_smoke_rejects_missing_key_before_client_construction(self):
        from app.cli.main import _smoke_google_tts

        args = Namespace(text="ทดสอบ", output="tmp/smoke.wav")
        with patch("app.cli.main.GoogleGenAISpeechClient") as client_type:
            with self.assertRaisesRegex(SystemExit, "GEMINI_API_KEY"):
                _smoke_google_tts(args, environ={})
        client_type.assert_not_called()

    def test_smoke_restricts_output_to_repository_tmp(self):
        from app.cli.main import _smoke_google_tts

        for output in ("audio/out.wav", "../out.wav", str(Path.cwd() / "out.wav")):
            with self.subTest(output=output):
                args = Namespace(text="ทดสอบ", output=output)
                with self.assertRaisesRegex(SystemExit, "tmp"):
                    _smoke_google_tts(
                        args,
                        environ={"GEMINI_API_KEY": "secret-test-key"},
                        client=FakeSpeechClient(),
                    )


if __name__ == "__main__":
    unittest.main()
