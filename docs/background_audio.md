# Optional background-audio post-process

This tool is separate from the standard dubbing workflow. Run it only after
`dubbed_video.mp4` and `07_audio/dub_audio.wav` have been created successfully:

```bash
python user_tools/10_add_background_audio.py --job-id VIDEO_ID
```

It creates `output/VIDEO_ID/dubbed_video_with_bg.mp4`. The standard
`dubbed_video.mp4` is used only as the video input and is never overwritten.
Demucs separates the original source soundtrack with `--two-stems=vocals`; the
resulting `no_vocals.wav` is mixed with the Japanese dub, while `vocals.wav` is
not used in the final mix. The default background gain is `-6 dB` and can be
changed without repeating separation:

```bash
python user_tools/10_add_background_audio.py --job-id VIDEO_ID --background-db -18
```

## Optional Demucs environment

Demucs-related packages are not required dependencies in the standard
`requirements.txt`. They may be installed in the same `.venv` when its Python
version and platform are compatible. A separately managed, Demucs-compatible
Python environment remains supported by providing its interpreter explicitly:

```bash
python user_tools/10_add_background_audio.py \
  --job-id VIDEO_ID \
  --demucs-python /path/to/demucs-venv/bin/python
```

An externally installed `demucs` executable is also supported with
`--demucs-bin /path/to/demucs`. If neither is available, the command exits with
a concise message and leaves the standard video unchanged.

A validated example is Intel Mac x86_64 with Python 3.12, torch 2.2.2,
torchaudio 2.2.2, and demucs 4.1.0.

Successful stems are stored in `09_background/` with a source SHA-256, source
size/path, backend, and model in `separation_manifest.json`. The cache is reused
only when all identity fields and both stems are valid. Each attempt writes its
result to `background_manifest.json`.
