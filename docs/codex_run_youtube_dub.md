# Codex Runbook: YouTube Japanese Dub

This document is the execution runbook for Codex.
When the user gives a YouTube URL and asks to make a Japanese dubbed video, Codex should follow this document through translation handoff only.

## 1. Input

- The user provides one YouTube URL.
- Extract `video_id` from the URL.
- Use `output/<video_id>/` as the job folder.
- Do not continue into long-running local TTS or video generation in this URL-only workflow.

## 2. Prepare

Run:

```bash
python3 scripts/run_prepare.py \
  --youtube-url "<URL>" \
  --output-dir output
```

## 3. Translate

Read:

```text
docs/translation_mode.md
```

For every file:

```text
output/<video_id>/03_translation_input/chunk_*.txt
```

Create the matching file:

```text
output/<video_id>/04_translation_output/chunk_*.txt
```

Rules:

- Preserve JSONL format.
- Preserve line count.
- Preserve `segment_id` / `start` / `end`.
- Translate only `text`.
- Make Japanese natural and short enough for speech.

## 4. Do Not Run Local Media Generation

Do not run:

```bash
python3 scripts/91_run_local_tts_pipeline.py \
  --job-id <video_id> \
  --output-dir output \
  --base-url http://127.0.0.1:10101 \
  --speaker-id 1937616896 \
  --ffmpeg-bin ffmpeg \
  --ffprobe-bin ffprobe \
  --force-tts \
  --mux-video
```

Do not run:

- AivisSpeech TTS generation
- WAV generation
- `synced_segments` generation
- `dubbed_video_synced.mp4` generation
- Long ffmpeg processing

## 5. Verify

- `05_segments/translated_segments.json` exists.
- `05_segments/translated_segments.srt` exists when the translation build step produces it.
- `04_translation_output/chunk_*.txt` exists for every input chunk.

## 6. Git

Commit only lightweight files:

- `output/<video_id>/**/*.json`
- `output/<video_id>/**/*.txt`
- `output/<video_id>/**/*.srt`

Do not commit:

- `mp4`
- `wav`
- `mov`
- `m4a`
- `aac`
- `08_synced_video/synced_segments/*.mp4`
- `08_synced_video/synced_segments/*.wav`

## 7. Push

Commit and push only the lightweight translation artifacts.

## 8. Report

Report:

- `video_id`
- chunk count
- created translation output paths
- committed lightweight file types
- the exact local command the user should run next

Local interactive command:

```bash
python user_tools/02_make_video.py
```

Local non-interactive command:

```bash
python3 scripts/91_run_local_tts_pipeline.py \
  --job-id <video_id> \
  --output-dir output \
  --base-url http://127.0.0.1:10101 \
  --speaker-id 1937616896 \
  --ffmpeg-bin ffmpeg \
  --ffprobe-bin ffprobe \
  --force-tts \
  --mux-video
```
