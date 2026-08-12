# AGENTS.md

## Scope
- The active product is the single script-driven workflow under `user_tools/` and `scripts/`.
- Keep changes minimal and consistent with the fixed-source-timeline workflow.

## Environment
- Use `.venv` and install dependencies with `pip install -r requirements.txt`.
- Whisper fallback is not implemented; do not add it unless explicitly requested.

## Security and data
- Never hardcode API keys or tokens. The default Codex CLI route requires no API key.
- Before commit run `rg -n "(sk-[A-Za-z0-9]|OPENAI_API_KEY|api_key\\s*=)" -S .`.
- `data/` and `output/**` are local runtime/cache assets. Only `output/.gitkeep` is tracked.
- Never commit generated audio/video or job JSON/TXT/SRT artifacts.
- Use `tools/90_zip.py` for review/archive exports.

## Translation
- Translation-specific rules belong in `docs/translation_mode.md`.

## Default YouTube workflow
- For a YouTube URL or bare video ID, follow `docs/codex_run_youtube_dub.md`.
- The only normal entrypoint is `python user_tools/00_dub_youtube.py --url <URL-or-ID>`.
- Default translation is Codex CLI; default TTS is Edge. Neither paid APIs, API keys, local LLMs, nor AivisSpeech startup are required.
- Preserve the fixed source timeline; never slow, retime, trim, or segment-concat video.
- Treat TTS NG and nonzero Audio QA warnings/clipped/overflow as hard failures.
- Use `output/<job_id>/.cache/diagnostic.json` as the primary diagnostic handoff.
- `.cache/work/` is temporary working evidence: delete it only after fully successful normal-dub compaction, and retain it on failure or interruption.
- AivisSpeech tools are explicit optional/advanced tools only and must never be auto-started.
