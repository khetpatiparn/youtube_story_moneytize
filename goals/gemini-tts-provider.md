# Goal: Gemini Thai TTS Provider

Status: completed on 2026-06-30.

## Outcome

Replace synthetic tone narration in normal local runs with controllable Thai speech
from the Gemini API Free Tier while preserving deterministic, credential-free tests.

## Scope

- Add a Gemini TTS adapter behind the existing `TTSProvider` contract.
- Select Google or local TTS from environment configuration.
- Generate scene-aligned Thai narration chunks with one configured voice.
- Retry only transient API failures with a finite bound.
- Publish a validated mono PCM WAV and resume safely from checkpoints.
- Support Gemini 24 kHz WAV alongside the existing local 22.05 kHz fixture.
- Add an explicit live smoke command that never runs in the default test suite.
- Keep API keys in ignored `.env` or environment variables and never log them.

## Acceptance Evidence

- Default tests make no external request and require no API key.
- Provider tests cover request shape, chunk concatenation, retry, permanent errors,
  missing audio, and invalid PCM.
- A live smoke command creates a non-empty, valid 24 kHz Thai WAV using the configured
  Gemini model and voice without printing the key.
- The full pipeline can reach final approval using `TTS_PROVIDER=google`.
- Orchestrator, renderer, dashboard, end-to-end tests, dashboard build, and
  `git diff --check` pass.
- README, AGENTS, and `.env.example` document setup, Free Tier limits, preview risk,
  data-use caveat, and local test fallback.

## Completion Evidence

- 113 orchestrator tests pass with one Windows symlink test skipped; default tests make no API calls.
- Live smoke produced a 24 kHz Charon WAV with a positive 3.64-second duration.
- `gemini_tts_sample` reached final approval with `voice_provider=google`, a validated
  19.24-second WAV, a 3,075,859-byte MP4, QA score 1.0, and dashboard export data.
- Renderer and dashboard tests/build are included in the final verification record.
- AI-generated scene images remain a separate follow-up goal; this slice retains local SVGs.

## Out of Scope

- Voice cloning or custom voice training.
- Paid-tier capacity guarantees.
- Automatic fallback to synthetic tones after a production TTS failure.
- Multi-speaker story generation in this slice.

