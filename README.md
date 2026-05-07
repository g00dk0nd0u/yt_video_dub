# yt_video_dub

自分用のシンプルな日本語吹替動画生成へ整理中のリポジトリです。

現在の本線は `user_tools/`、`scripts/`、`docs/` です。旧YMM系、旧VOICEVOX系、GPU前提コードは削除せず `legacy/` に退避しています。

## Current Layout

- `user_tools/`: ユーザーが直接触る入口
- `scripts/`: 内部パイプライン実装と補助ステップ
- `docs/`: ワークフローと翻訳モードの設計メモ
- `legacy/`: 退避した旧コード
- `tools/90_zip.py`: レビュー用 ZIP 出力
- `data/`: ローカル作業用アセット

## Setup

```bash
cd /Users/ryokondo/Documents/iMac_Python/yt_video_dub
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Whisper fallback は未実装です。必要になった時点で `faster-whisper` を追加導入します。

## Entrypoints

```bash
python user_tools/01_new_youtube.py
python user_tools/02_make_video.py
python user_tools/99_cleanup.py
```

普段ユーザーが触るのは `user_tools/` の3本だけです。

1. `user_tools/01_new_youtube.py` を実行して YouTube URL を貼る
2. Codex で `output/<video_id>/translation_input/chunk_*.txt` を翻訳し、`output/<video_id>/translation_output/chunk_*.txt` に保存する
3. AivisSpeech を起動する
4. `user_tools/02_make_video.py` を実行する
5. `output/<video_id>/dubbed_video.mp4` を開く
6. 掃除したい時は `user_tools/99_cleanup.py` を実行する

`scripts/` は内部処理用として残しています。主な内部入口は `scripts/run_prepare.py` と `scripts/91_run_local_tts_pipeline.py` です。

`user_tools/01_new_youtube.py` は `scripts/run_prepare.py` を呼び、YouTube URL から翻訳用ファイルを作ります。`--job-id` を指定しないため、動画IDがそのまま `output/<video_id>/` に使われます。

`user_tools/02_make_video.py` は `scripts/91_run_local_tts_pipeline.py` を呼び、翻訳済みテキストから日本語音声付き動画を作ります。

`user_tools/99_cleanup.py` は `output/` 配下の動画フォルダだけを安全に削除します。

## Fixed Output Layout

```
output/<video_id>/
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

すべての作業ファイルは `output/<video_id>/` にまとまります。`job.json` を含む軽量な進行管理ファイルと、音声・動画などの重い生成物がここに入ります。

## Git Tracking Policy

- `output/**/*.json`
- `output/**/*.txt`
- `output/**/*.srt`

上の軽量ファイルは Git 管理できます。

- `output/**/*.mp4`
- `output/**/*.wav`
- `output/**/*.mov`
- `output/**/*.m4a`
- `output/**/*.aac`

上の重いメディアは `.gitignore` で無視します。

## Notes

- YouTube 字幕取得は `youtube-transcript-api` を本線にする方針です。
- Whisper は YouTube 字幕が取得できない場合やローカル動画向け fallback として将来追加予定です。現状は分かりやすいエラーで停止します。
- AivisSpeech はローカル接続前提です。詳細は [docs/workflow.md](docs/workflow.md) にあります。
