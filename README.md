# yt_video_dub

自分用のシンプルな日本語吹替動画生成へ整理中のリポジトリです。

現在の本線は `scripts/` と `docs/` です。旧YMM系、旧VOICEVOX系、GPU前提コードは削除せず `legacy/` に退避しています。

この段階では `Commit 1` と `Commit 2` 相当までを反映しており、Phase 1 / Phase 2 の実処理はまだ未実装です。新規 `scripts/*.py` は引数仕様の固定と TODO の明示までで止まります。

## Current Layout

- `scripts/`: 新しいメイン構成のスケルトン
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

## Planned Entrypoints

```bash
python scripts/run_prepare.py --help
python scripts/run_finish.py --help
```

各スクリプトは現時点では `--help` のみ確認対象です。実行すると TODO / `NotImplementedError` で停止します。

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

`output/` 配下の重い生成物は Git 管理対象に含めません。

## Notes

- YouTube 字幕取得は `youtube-transcript-api` を本線にする方針です。
- Whisper は YouTube 字幕が取得できない場合やローカル動画向け fallback として次フェーズで実装します。
- AivisSpeech はローカル接続前提で、詳細は [docs/workflow.md](docs/workflow.md) にまとめます。
