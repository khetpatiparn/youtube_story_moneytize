# Goal: Gemini Thai TTS Provider

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

## Out of Scope

- Voice cloning or custom voice training.
- Paid-tier capacity guarantees.
- Automatic fallback to synthetic tones after a production TTS failure.
- Multi-speaker story generation in this slice.

