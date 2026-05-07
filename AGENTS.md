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

## Practical Rule
- Keep changes minimal and consistent with existing script-driven workflow.
