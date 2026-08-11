# Codex Runbook: YouTube Japanese Dub

ユーザーが YouTube URL または video ID を渡して吹替を依頼した場合の default runbook です。

## Command

```bash
python user_tools/00_dub_youtube.py --url "<YouTube URL or video ID>"
```

追加確認や manual translation handoff を挟まず、この一つの入口で次を実行します。

1. YouTube source/transcript preparation
2. Codex CLI translation
3. Edge TTS（resume/cache）
4. fixed source timeline audio assembly
5. Audio QA hard gate
6. codec-compatible mux と final codec validation
7. `output/<video_id>/dubbed_video.mp4`

Codex CLI は ChatGPT account sign-in を使います。paid translation API、API key、local LLM、AivisSpeech の起動は不要です。

## Hard gates

- video を slow/retime/trim/segment-concat しない。source timeline と duration を維持し、cumulative drift を発生させない。
- TTS failed/NG が残れば Audio/Mux へ進まない。
- Audio warnings/clipped/overflow が nonzero なら success を報告しない。
- original English audio は default `-38 dB`。
- source codec を ffprobe し、H.264 は stream-copy、それ以外（AV1/VP9/HEVC/unknown 等）は H.264 transcode。
- output codec を再度 ffprobe して validation する。

## Report

成功時は完成動画 path、失敗時は停止 stage を報告します。詳細の primary handoff は常に `output/latest_run.txt` です。同じ command を再実行すると Edge TTS cache を resume します。

`output/**` はすべて local runtime/cache で Git ignored です。`output/.gitkeep` 以外の生成物を commit/push しません。
