# YouTube Story Automation

POC for a recoverable YouTube story automation workflow. The deterministic local path runs end to end without credentials, while intentional approved runs can use Cloudflare Workers AI for scene images and Gemini for natural Thai narration.

## Current Orchestrator Commands

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
python -m app create --project-id sample_story --topic "A river spirit teaches patience" --duration 30 --profile simple_story_th
python -m app run --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-script --project-id sample_story --approved --reviewer human --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-final --project-id sample_story --approved --reviewer human --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app status --project-id sample_story
python -m app report --project-id project_001 --video-path render/story.mp4 --quality-score 0.91 --issue "No final approval yet"
```

The first `run` stops at script approval. The first `resume` after approval generates images and narration, renders the MP4, validates it, writes reports, and stops at final approval. The last `resume` changes the project to `completed`. Use `--tts-words-per-second 1000` on `resume` only for a fast one-second smoke render; the normal default is `2.5`.

Generated runtime data goes under `projects/{project_id}/`: outline and script in `content/`, scene JSON in `scenes/`, SVG or JPEG scene assets in `images/`, WAV in `audio/`, payload and MP4 in `render/`, and approvals/quality/contact/project reports in `reports/`. Checkpoint data goes under `data/`.

Resume is idempotent. Completed images, audio, renders, and reports are fingerprinted or validated before reuse. A failed render remains at `render_ready`; fix the cause and run `resume` again. Image retry is limited to three total attempts per failed scene by default (`--max-image-attempts` changes the bound).

## Cloudflare AI Scene Images

The credentialed image path uses Cloudflare Workers AI model `@cf/black-forest-labs/flux-1-schnell`. In the Cloudflare dashboard, open **Workers AI**, choose **Use REST API**, and select **Create Workers AI API Token**. Copy the Account ID shown there. For a custom token, Cloudflare's [REST API guide](https://developers.cloudflare.com/workers-ai/get-started/rest-api/) requires Account > Workers AI permissions with both Read and Edit.

Copy `.env.example` to the ignored `.env` and set:

```dotenv
IMAGE_PROVIDER=cloudflare
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_API_TOKEN=your-api-token
CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell
CLOUDFLARE_IMAGE_STEPS=4
CLOUDFLARE_IMAGE_MAX_ATTEMPTS=3
TTS_PROVIDER=google
```

Never commit `.env`, paste its values into commands, or attach it to reports. Verify the image credentials with one explicit request; output is restricted to a relative `.jpg` path under repository `tmp/`:

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m app smoke-cloudflare-image --prompt "cinematic Thai folklore river at dawn, no text" --output tmp/cloudflare-image-smoke.jpg
```

Cloudflare documents a free allocation of 10,000 neurons per day, reset at 00:00 UTC. Flux Schnell currently costs 4.8 neurons per 512-by-512 tile plus 9.6 neurons per generation step and accepts 1–8 steps. Verify the current [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) and [Flux Schnell model contract](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/) before a live run because limits and pricing can change. This application has no automatic paid-provider or local fallback: a Cloudflare failure stops the external image path.

After script approval, `resume` creates one JPEG per scene, validates JPEG decoding and dimensions of 512–4096 pixels per side, and publishes artifacts atomically. Transient timeouts, rate limits, and server failures have a finite retry bound. Valid completed jobs are reused from `images/jobs.json` on resume; corrupt or missing outputs follow the bounded recovery rules. Remotion center-crops each image with `object-fit: cover` to the 16:9 frame. Character and art continuity is prompt-only in this slice, so Flux may vary faces, clothing, and details between scenes.

Default tests use `IMAGE_PROVIDER=local` and `TTS_PROVIDER=local`; they generate deterministic SVG and tone-WAV artifacts without network access or quota usage. To recover from a live failure, keep the project directory and checkpoint database, fix credentials/quota/configuration, and run `resume` again. Do not delete `images/jobs.json` or validated image files unless intentionally forcing regeneration.

## Gemini Thai TTS

Copy `.env.example` to ignored `.env`, set `GEMINI_API_KEY`, and change `TTS_PROVIDER=google`. The defaults use `gemini-3.1-flash-tts-preview` with the `Charon` voice. Verify credentials with one explicit request:

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m app smoke-google-tts --text "สวัสดี นี่คือเสียงทดสอบ" --output tmp/gemini-tts-smoke.wav
```

Normal `run` stops before external TTS. After script approval, `resume` selects the configured provider, splits narration into bounded chunks, retries transient failures up to `GEMINI_TTS_MAX_ATTEMPTS`, concatenates PCM, and atomically publishes a mono PCM16 WAV at 24 kHz. It does not silently fall back to tones when Google fails. Set `TTS_PROVIDER=local` for deterministic, quota-free tests.

Gemini TTS is a Preview model: availability, model names, quality, and Free Tier rate limits can change. Free Tier capacity is not guaranteed. Review the current Google AI Studio pricing, rate limits, and data-use terms before production use; prompts and outputs on unpaid services may be handled differently from paid services. Never commit `.env` or paste credentials into logs.

## Local Provider Limitations

- Story content is deterministic template output, not a production LLM response.
- Local images are deterministic SVG review assets. Cloudflare images are AI-generated but provide only prompt-based, not reference-image-enforced, character continuity.
- Local narration is synthetic tones; Gemini Thai narration is available only for intentional credentialed runs.
- The external story-content LLM adapter still requires implementation; image and TTS adapters require credentials and provider quota.
- YouTube upload, publishing, analytics, and fully autonomous operation are not implemented.

## Current Renderer Commands

```powershell
npm.cmd install
npm.cmd run test:renderer
npm.cmd run render:sample
```

The static sample command reads `apps/renderer/sample/render_payload.json`. The orchestrator uses runtime props and stages validated project assets before writing `projects/{project_id}/render/story.mp4`. Render outputs are ignored by Git.

## Current Dashboard Commands

```powershell
npm.cmd run test:dashboard
npm.cmd run prepare:dashboard-data
npm.cmd run dev:dashboard
npm.cmd run build:dashboard
```

The Media QA dashboard lives in `apps/dashboard/`. The data export step reads local project data from `projects/{project_id}/` when available and writes `apps/dashboard/public/dashboard-data.json`; when no generated projects exist it writes bundled demo data. The first dashboard slice is read-only.
