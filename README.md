# yt_video_dub

YouTube の英語動画を、元映像の時間軸を変えずに日本語吹替動画へ変換します。
通常利用では YouTube URL（または動画 ID）を一度入力するだけです。

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Codex CLI をインストールし、ChatGPT アカウントで sign in してください。翻訳用の有料 API、API key、local LLM は不要です。`ffmpeg` と `ffprobe` は PATH 上に必要です。Whisper fallback は未実装です。

## Default workflow

```bash
python user_tools/00_dub_youtube.py
```

YouTube URL または bare video ID（例: `OEkxKdhtQng`）を一度入力すると、次を順番に実行します。

1. source と字幕を取得・正規化
2. Codex CLI で英語から日本語へ翻訳
3. Edge TTS で音声生成（resume/cache 対応）
4. 元字幕の絶対 start に音声を配置
5. Audio QA
6. codec-compatible mux
7. `output/<video_id>/dubbed_video.mp4` を生成

音声は `--voice` で変更できます。診断情報は job ごとの `output/<video_id>/.cache/diagnostic.json` です。成功時は final video、diagnostic、source audio だけを残し、失敗時は `.cache/work/` に調査用の作業状態を残します。古い job の削除には `python user_tools/99_cleanup.py` を使います。

## macOS Desktop launcher

上記の手順で `.venv` を作成して依存関係を入れた後、次を一度実行します。

```bash
.venv/bin/python tools/install_mac_desktop_launcher.py
```

以後は `~/Desktop/YouTube Dub.command` をダブルクリックすると、音声選択、YouTube URL 入力、吹替の対話フローを開始できます。この launcher は Python 自体を package せず、この repository の `.venv` を利用します。

## Timeline / quality invariants

- source video timeline は固定し、映像の slowdown、retime、segment concat は行いません。
- 各音声は source の絶対時刻へ配置するため、累積 drift はありません。
- TTS に failed/NG が残る場合、Audio/Mux へ進みません。
- Audio QA の warnings、clipped、overflow が一つでも nonzero なら成功にしません。
- 元英語音声はデフォルト `-38 dB` で日本語音声と mix します。
- `ffprobe` で source codec を判定し、H.264 のみ video stream-copy します。
- AV1、VP9、HEVC、unknown を含むその他 codec は H.264 へ fallback transcode します。
- mux 後にも final video codec を検証します。

詳細は [docs/workflow.md](docs/workflow.md) を参照してください。

## Optional / advanced AivisSpeech tools

AivisSpeech は通常フローでは起動も使用もしません。明示的に AivisSpeech を評価・利用するときだけ、以下の既存ツールを使えます。

- `scripts/05_probe_aivis.py`: 接続確認
- `scripts/06_generate_tts_segments.py`: AivisSpeech segment TTS
- `scripts/91_run_local_tts_pipeline.py`: AivisSpeech 専用 local pipeline
- `scripts/92_benchmark_tts_concurrency.py` ～ `94_run_tts_concurrency_matrix.py`: quality/performance benchmark

## Output and Git policy

`output/**` はすべて runtime/cache であり Git ignored です。tracked file は `output/.gitkeep` だけです。生成した JSON/TXT/SRT を含め、job artifact を commit/push しません。大きな media を repository に追加しないでください。

レビュー用 ZIP が必要な場合は `tools/90_zip.py` を使います。
