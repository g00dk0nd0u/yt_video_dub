# AGENTS.md

## Scope
- This repository is now being reorganized around the new `scripts/` workflow.
- Legacy YMM, VOICEVOX, GPU, and test code lives under `legacy/` and is not the active path unless explicitly requested.

## Environment
- Use a local virtual environment: `.venv`.
- Install dependencies with:
  - `pip install -r requirements.txt`
- If Whisper fallback is implemented later, install `faster-whisper` separately at that time.

## Security
- Never hardcode API keys or tokens in source files.
- Use environment variables (e.g., `OPENAI_API_KEY`) for secrets.
- Before commit, run a quick secret scan:
  - `rg -n "(sk-[A-Za-z0-9]|OPENAI_API_KEY|api_key\\s*=)" -S .`

## Data Handling
- `data/` contents are ignored by Git and treated as local working assets.
- `output/` generated media must remain outside Git tracking.
- Large media files (audio/video) must not be committed.

## ZIP Export
- Use `tools/90_zip.py` for review/archive exports.
- Keep text/debug artifacts; exclude heavy media assets.

## Translation Rules
- Keep translation-specific operating rules out of this file.
- Use `docs/translation_mode.md` when the task explicitly enters translation mode.

## Codex URL Workflow
- If the user input is a standalone YouTube URL, or a request that includes a YouTube URL, treat `docs/codex_run_youtube_dub.md` as the execution runbook.
- In that case, proceed without extra confirmation through prepare, translation, lightweight file commit/push, and final local-run guidance only.
- Stop before long-running local media generation.
- Commit only lightweight files: `json`, `txt`, and `srt`.
- Never commit `mp4`, `wav`, `mov`, `m4a`, or `aac`.
- Never commit `synced_segments/*.mp4` or `synced_segments/*.wav`.
- Do not run AivisSpeech TTS generation, WAV generation, synced segment generation, synced MP4 creation, or long ffmpeg processing when handling a URL-only request.
- The user-side local completion command is `python user_tools/02_make_video.py`.
- The non-interactive local command is `python3 scripts/91_run_local_tts_pipeline.py --job-id <video_id> --output-dir output --base-url http://127.0.0.1:10101 --speaker-id 1937616896 --ffmpeg-bin ffmpeg --ffprobe-bin ffprobe --force-tts --mux-video`.
- Default AivisSpeech settings are `http://127.0.0.1:10101` and `speaker_id 1937616896`.
- Default ffmpeg tools are `ffmpeg` and `ffprobe`.
- If the run fails, report only the step where it stopped and keep the report concise.

## Practical Rule
- Keep changes minimal and consistent with existing script-driven workflow.
