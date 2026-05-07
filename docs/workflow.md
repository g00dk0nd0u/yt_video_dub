# Workflow

`yt_video_dub` uses a simple user-facing workflow built around `user_tools/`.

## User Flow

1. Run `user_tools/01_new_youtube.py`.
2. Paste a YouTube URL.
3. The repository creates working files under `output/<video_id>/`.
4. Translate `03_translation_input/chunk_*.txt` into Japanese and save them to `04_translation_output/chunk_*.txt`.
5. Start AivisSpeech locally.
6. Run `user_tools/02_make_video.py`.
7. Open `output/<video_id>/dubbed_video_synced.mp4`.
8. Run `user_tools/99_cleanup.py` when you want to remove old video folders.

## Internal Script Mapping

- `scripts/run_prepare.py`
  - `01_prepare_source.py`
  - `02_get_transcript.py`
  - `03_make_translation_chunks.py`
- `scripts/91_run_local_tts_pipeline.py`
  - `04_build_translated_segments.py`
  - `06_generate_tts_segments.py`
  - `07_build_dub_audio.py`
  - `09_build_synced_video.py`

## Fixed Output Layout

```text
output/<video_id>/
  dubbed_video_synced.mp4
  01_source/
    source.mp4
    job.json
  02_transcript/
    transcript_original.json
    transcript_original.srt
  03_translation_input/
    manifest.json
    chunk_0001.txt
  04_translation_output/
  05_segments/
    translated_segments.json
    translated_segments.srt
  06_tts/
  07_audio/
    dub_audio.wav
  08_synced_video/
    synced_segments/
  09_simple_mux/
    dubbed_video.mp4
```

## AivisSpeech Connection Assumptions

- AivisSpeech is expected to be available through a local HTTP API.
- `user_tools/02_make_video.py` uses:
  - `http://127.0.0.1:10101`
  - speaker ID `1937616896`
  - `ffmpeg`

## AivisSpeech Connection Checks

Before creating the final video, confirm:

1. AivisSpeech is running locally.
2. The local API base URL is known.
3. The speaker ID to use for Japanese dubbing is known.
4. A simple health or test request can be made from the terminal.

Example check flow to document and validate later:

```bash
curl http://127.0.0.1:10101/
```

The exact endpoint and payload contract are still to be confirmed.

## Notes

- Whisper fallback for subtitle-missing YouTube videos and local videos is not implemented yet.
- Local video support still needs future work.
