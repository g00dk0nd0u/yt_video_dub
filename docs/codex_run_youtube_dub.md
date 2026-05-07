# Codex Runbook: YouTube Japanese Dub

This document is the execution runbook for Codex.
When the user gives a YouTube URL and asks to make a Japanese dubbed video, Codex should follow this document from start to finish.

## 1. Input

- The user provides one YouTube URL.
- Extract `video_id` from the URL.
- Use `output/<video_id>/` as the job folder.

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
output/<video_id>/translation_input/chunk_*.txt
```

Create the matching file:

```text
output/<video_id>/translation_output/chunk_*.txt
```

Rules:

- Preserve JSONL format.
- Preserve line count.
- Preserve `segment_id` / `start` / `end`.
- Translate only `text`.
- Make Japanese natural and short enough for speech.

## 4. Build Synced Dubbed Video

Run:

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

## 5. Verify

Check:

- `translated_segments.json` exists.
- `tts/tts_manifest.json` exists.
- `synced_video_manifest.json` exists.
- `dubbed_video_synced.mp4` exists locally.
- `synced_video_manifest.json` has `total_items == processed_items`.

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
- `synced_segments/*.mp4`
- `synced_segments/*.wav`

## 7. Report

Report:

- `video_id`
- chunk count
- `total_items / processed_items`
- adjustment summary
- output video path
- `git status`
