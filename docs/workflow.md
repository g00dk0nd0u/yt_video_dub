# Workflow

`yt_video_dub` is being reorganized into a two-phase workflow for simple Japanese dubbing on an iMac 2019 class machine.

## Current Status

- This repository currently provides skeleton scripts only.
- `scripts/*.py` define argument contracts and stop with `TODO` / `NotImplementedError`.
- Phase 1 and Phase 2 implementation will be added in a later step.

## Active Workflow Design

### Phase 1

1. Accept a YouTube URL or a local video path.
2. Store working files under `output/<job_id>/`.
3. If the input is YouTube:
   - Download `source.mp4`.
   - Fetch subtitles via `youtube-transcript-api` as the primary path.
4. If subtitles are unavailable:
   - Leave a Whisper fallback TODO for a future phase.
5. Prepare translation input chunks and stop.

### Phase 2

1. Read translated chunk files from `translation_output/`.
2. Rebuild translated segment data.
3. Generate Japanese TTS audio via AivisSpeech.
4. Mux the original video stream with the generated Japanese audio.
5. Write `dubbed_video.mp4`.

## Fixed Output Layout

```text
output/<job_id>/
  job.json
  source.mp4
  transcript_original.json
  transcript_original.srt
  translation_input/
    manifest.json
    chunk_0001.txt
  translation_output/
  translated_segments.json
  translated_segments.srt
  tts/
  dub_audio.wav
  dubbed_video.mp4
```

## AivisSpeech Connection Assumptions

- AivisSpeech is expected to be available through a local HTTP API.
- Python entrypoints should accept:
  - `--base-url`
  - `--speaker-id`
  - `--output-dir`
- Keep these values explicit in the CLI so the pipeline is easy to rerun.

## AivisSpeech Connection Checks

Before implementing TTS generation, confirm:

1. AivisSpeech is running locally.
2. The local API base URL is known.
3. The speaker ID to use for Japanese dubbing is known.
4. A simple health or test request can be made from the terminal.

Example check flow to document and validate later:

```bash
curl http://127.0.0.1:10101/
```

The exact endpoint and payload contract are still to be confirmed.

## TODO

- Confirm the exact AivisSpeech API endpoints and request bodies.
- Implement YouTube download and transcript fetch logic.
- Implement Whisper fallback for subtitle-missing YouTube videos and local videos.
- Define the exact translation chunk text format and validation rules in code.
- Implement ffmpeg-based muxing with copied video stream and AAC audio output.
