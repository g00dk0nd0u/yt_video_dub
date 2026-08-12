# Default workflow

## User flow

```bash
python user_tools/00_dub_youtube.py
```

YouTube URL または bare video ID を一度入力します。default route は、source preparation → Codex CLI translation → Edge TTS → fixed-timeline audio assembly → Audio QA → codec-compatible mux を連続実行し、`output/<video_id>/dubbed_video.mp4` を作ります。paid translation API、API key、local LLM、AivisSpeech process は不要です。

## Fixed source timeline

- 日本語 WAV は各 source caption の絶対 start に配置します。前の発話に依存した shift を行わないため cumulative drift はありません。
- source video の duration/timeline を固定し、映像の速度変更、trim、retime、segment concat を禁止します。
- TTS failed/NG が残れば Audio/Mux を実行しません。
- Audio QA の warnings/clipped/overflow が nonzero なら run は失敗します。
- 元英語音声は default `-38 dB`、`amix` normalization なしで mix します。

## Compatible mux

`scripts/08_mux_video.py` は source video codec を `ffprobe` します。H.264 は stream-copy、AV1/VP9/HEVC/unknown 等は `libx264` fallback transcode を使用し、生成後にも codec が H.264 compatible であることを検証します。

## Output / diagnostics

成功後の永続 layout は次のとおりです。`dubbed_video_with_bg.mp4` と `accompaniment.flac` は背景音生成後のみ存在します。

```text
output/<video_id>/
├── dubbed_video.mp4
├── dubbed_video_with_bg.mp4
└── .cache/
    ├── diagnostic.json
    ├── source_audio.mka
    └── accompaniment.flac
```

primary diagnostic handoff は `output/<video_id>/.cache/diagnostic.json` です。実行中の中間物は `.cache/work/` に置き、normal dub が完全に成功した後だけ削除します。失敗・割込時は resume と調査のため保持します。直前の numbered layout は、新layoutと競合しない場合に限り `.cache/work/` へ安全にadoptします。`output/**` は runtime/cache として Git ignored で、`output/.gitkeep` だけを track します。

## Optional AivisSpeech

AivisSpeech は explicit optional/advanced mode だけです。接続 probe、Aivis segment generation、専用 local pipeline、concurrency benchmark は Issue #7 系の quality/performance comparison を再現できるため残しています。default entrypoint からは参照も自動起動もしません。

Whisper fallback、local video、lip sync、voice cloning は未実装です。
