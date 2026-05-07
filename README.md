# yt_video_dub

自分用のシンプルな日本語吹替動画生成へ整理中のリポジトリです。

現在の本線は `user_tools/`、`scripts/`、`docs/` です。旧YMM系、旧VOICEVOX系、GPU前提コードは削除せず `legacy/` に退避しています。

この段階では Phase 1 のみ実装済みです。YouTube URL から `source.mp4`、英語優先の字幕、翻訳用 chunk を生成して停止します。Phase 2 の翻訳反映、AivisSpeech、mux はまだ未実装です。

## Current Layout

- `user_tools/`: ユーザーが直接実行するクリック用・手動実行用ランナー
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

Whisper fallback は次フェーズ実装予定です。必要になった時点で `faster-whisper` を追加導入します。

## Entrypoints

```bash
python scripts/run_prepare.py --help
python scripts/run_finish.py --help
python user_tools/run_rebuild_all.py
python user_tools/run_resume.py
python user_tools/run_rebuild_range.py
python user_tools/run_cleanup_outputs.py
```

Phase 1 は次で実行できます。

```bash
python scripts/run_prepare.py --youtube-url "https://www.youtube.com/watch?v=VIDEO_ID"
```

`--job-id` を省略すると YouTube `video_id` がそのまま使われます。`--local-video` は引数だけ用意してあり、実装は次フェーズです。

`user_tools/` 配下はユーザー向けの起点です。内部処理は `../scripts/` の実装を読み込むだけで、パイプラインロジック自体は重複させていません。

`scripts/` 配下は内部ステップ用です。主な流れは `01_prepare_source.py` から `08_mux_video.py`、共有ランナーの `91_run_local_tts_pipeline.py`、内部 cleanup 実装の `92_clean_local_outputs.py` です。

## Fixed Output Layout

```
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

Phase 1 で実際に生成されるのは `translation_output/` までです。`output/` 配下の重い生成物は Git 管理対象に含めません。

ジョブごとの生成物は `output/<job_id>/` にまとまります。`job.json` を含む軽量な進行管理ファイルと、TTS・音声・動画などの重い生成物がここに入ります。

## Notes

- YouTube 字幕取得は `youtube-transcript-api` を本線にする方針です。
- Whisper は YouTube 字幕が取得できない場合やローカル動画向け fallback として次フェーズで実装します。現状は分かりやすいエラーで停止します。
- AivisSpeech はローカル接続前提で、詳細は [docs/workflow.md](docs/workflow.md) にまとめます。
