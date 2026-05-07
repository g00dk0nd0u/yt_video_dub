# AGENTS.md

## Scope
- This repository is currently maintained for `scripts_dub` dubbing workflows.
- `scripts_ymm` exists but is out of active scope unless explicitly requested.

## Environment
- Use a local virtual environment: `.venv`.
- Install dependencies with:
  - `pip install -r requirements.txt`
- If Whisper is needed, install `faster-whisper` separately.

## Security
- Never hardcode API keys or tokens in source files.
- Use environment variables (e.g., `OPENAI_API_KEY`) for secrets.
- Before commit, run a quick secret scan:
  - `rg -n "(sk-[A-Za-z0-9]|OPENAI_API_KEY|api_key\\s*=)" -S .`

## Data Handling
- `data/` contents are ignored by Git and treated as local working assets.
- Large media files (audio/video) must not be committed.

## ZIP Export
- Use `tools/90_zip.py` for review/archive exports.
- Keep text/debug artifacts; exclude heavy media assets.

## Practical Rule
- Keep changes minimal and consistent with existing script-driven workflow.
