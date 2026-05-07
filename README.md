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

Codex に YouTube URL だけ渡すと、`AGENTS.md` のルールにより `docs/codex_run_youtube_dub.md` の流れで、翻訳済みソース作成まで進めます。長時間の TTS 生成や ffmpeg による動画生成は Codex では実行しません。

## Entrypoints

```bash
python user_tools/01_new_youtube.py
python user_tools/02_make_video.py
python user_tools/99_cleanup.py
```

普段ユーザーが触るのは `user_tools/` の3本だけです。

1. `user_tools/01_new_youtube.py` を実行して YouTube URL を貼る
2. Codex に URL を渡した場合は、`scripts/run_prepare.py` 実行と `output/<video_id>/03_translation_input/chunk_*.txt` の翻訳を行い、`output/<video_id>/04_translation_output/chunk_*.txt` まで作る
3. 動画生成はユーザーの Mac で AivisSpeech を起動してから `user_tools/02_make_video.py` を実行する
4. `output/<video_id>/dubbed_video_synced.mp4` を開く
5. 掃除したい時は `user_tools/99_cleanup.py` を実行する

`scripts/` は内部処理用として残しています。主な内部入口は `scripts/run_prepare.py` と `scripts/91_run_local_tts_pipeline.py` です。

`user_tools/01_new_youtube.py` は `scripts/run_prepare.py` を呼び、YouTube URL から翻訳用ファイルを作ります。`--job-id` を指定しないため、動画IDがそのまま `output/<video_id>/` に使われます。

`user_tools/02_make_video.py` は `scripts/91_run_local_tts_pipeline.py` を呼び、翻訳済みテキストから音声と映像を合わせた日本語吹替動画を作ります。

Codex URL ワークフローの完了地点は、翻訳済みソースの作成と軽量ファイルの commit/push です。その先の動画生成はローカルで次を実行します。

```bash
python user_tools/02_make_video.py
```

非対話で実行する場合:

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

`user_tools/99_cleanup.py` は `output/` 配下の動画フォルダだけを安全に削除します。

## Fixed Output Layout

```
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
    tts_manifest.json
  07_audio/
    dub_audio.wav
    dub_audio_manifest.json
  08_synced_video/
    synced_video_manifest.json
    synced_segments/
  09_simple_mux/
    dubbed_video.mp4
```

Finder では `output/<video_id>/dubbed_video_synced.mp4` だけが完成動画として直下に見えます。その他の中間成果物は工程順の番号付きフォルダへ入り、`dubbed_video.mp4` を使う場合も `09_simple_mux/` に入ります。

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
