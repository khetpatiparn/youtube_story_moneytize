# Gemini Thai TTS Provider Design

## Goal

Use Gemini text-to-speech for natural Thai narration in real pipeline runs while
keeping local deterministic audio for tests and offline development. The provider
must preserve checkpoint recovery, never expose credentials, and produce audio that
the existing timeline, quality, and Remotion stages can validate.

## Provider Selection

`TTS_PROVIDER=google` selects `GeminiTTSProvider`; `TTS_PROVIDER=local` selects the
existing `LocalTTSProvider`. There is no silent fallback. Missing Google credentials,
quota exhaustion, invalid responses, or permanent API errors stop the current run
with an actionable provider error and leave the latest valid checkpoint intact.

Configuration is read at runner construction:

- `GEMINI_API_KEY` — required for Google TTS and never included in logs or exceptions.
- `GEMINI_TTS_MODEL` — defaults to `gemini-3.1-flash-tts-preview`.
- `GEMINI_TTS_VOICE` — defaults to `Charon`.
- `GEMINI_TTS_MAX_ATTEMPTS` — defaults to 3 total attempts per chunk.

The committed `.env.example` contains empty credential fields. The ignored `.env`
holds local values.

## API Adapter

The implementation uses the official `google-genai` Python SDK behind a small client
protocol so unit tests inject a fake client. The adapter asks for audio-only output,
one speaker, the configured voice, and a Thai storytelling performance. It validates
that each response contains PCM bytes before accepting it.

The provider maps rate limits, server failures, and rare responses without audio to
`RetryableProviderError`. Authentication, permission, unsupported-model, malformed
request, and exhausted retry errors become `PermanentProviderError` with sanitized
messages. Raw response bodies, headers, API keys, and request authentication values
are never written to project logs or exception strings.

## Chunking and Voice Consistency

The script already separates scene narration with blank lines. The provider uses each
non-empty paragraph as one chunk, preserving order. A paragraph longer than 4,000
characters is split at sentence or whitespace boundaries. Every chunk uses the same
model, voice, performance instruction, and audio format.

The instruction requests clear natural Thai storytelling, a calm informative pace,
consistent volume, and exact transcript recitation. Chunks are synthesized
sequentially to avoid Free Tier bursts. Retry uses bounded exponential delays with an
injectable sleep function; tests run without real delays.

## Audio Contract

Gemini returns raw mono 16-bit PCM at 24,000 Hz. The provider validates byte alignment,
non-empty output, and consistent format for all chunks, concatenates PCM in order,
and atomically publishes one `audio/narration.wav` through `ArtifactStore`.

The shared WAV reader accepts only uncompressed mono 16-bit PCM at either 22,050 Hz
(local deterministic provider) or 24,000 Hz (Gemini). It verifies that declared frame
bytes are present. Timeline duration always comes from the completed WAV rather than
from an API estimate.

`AudioResult` reports provider `google`, the configured model, selected voice, project-
relative output path, measured WAV duration, and status `completed`.

## Pipeline and Recovery

CLI construction loads `.env` without overriding existing process environment values,
selects the configured provider, and injects it into `PipelineRunner`. Project creation
and the first script-approval pause do not require a TTS request. The request occurs
only after script approval during resume.

The WAV is atomically published only after every chunk succeeds. If any chunk fails,
no new partial WAV replaces the last valid artifact. The checkpoint remains before
the audio transition. A later `resume` retries the TTS stage. Once a valid WAV and
matching downstream payload exist, normal artifact reconciliation avoids another API
request.

## Testing

Default unit and end-to-end tests explicitly select the local provider. Fake Gemini
client tests cover:

- Thai request, model, voice, and audio-only configuration.
- Paragraph ordering and long-chunk splitting.
- PCM concatenation and exact 24 kHz WAV duration.
- Transient retry bounds and sanitized permanent errors.
- Missing, empty, odd-length, and malformed audio responses.
- Atomic preservation of an existing WAV when a later chunk fails.
- Environment selection and missing-key behavior.
- Timeline and QA compatibility with both supported sample rates.

An opt-in `python -m app smoke-google-tts` command uses the configured key to create
`tmp/gemini-tts-smoke.wav`, validates it, and prints only model, voice, sample rate,
duration, and output path. It never prints configuration secrets. This command is the
only required live API verification in this slice.

## Limitations

Gemini TTS is a Preview service with Free Tier rate limits. Long output may drift, and
the service can occasionally return no audio or a server error, so chunking and retry
are required. Free Tier requests may be used by Google to improve products. This slice
does not promise production SLA, voice cloning, multi-speaker narration, or unlimited
zero-cost generation.

## Acceptance Criteria

- A configured live smoke command creates a validated 24 kHz Thai WAV.
- A real pipeline run with `TTS_PROVIDER=google` reaches final approval with Gemini
  narration and no synthetic-tone fallback.
- No default test consumes Gemini quota.
- Failures preserve the previous WAV and checkpoint and expose sanitized errors.
- Existing local provider, renderer, dashboard, and end-to-end behavior remain green.
- Documentation states Free Tier, Preview, privacy, rate-limit, and fallback behavior.
