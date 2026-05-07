# yt_video_dub

YouTube動画の取得、文字起こし、翻訳、音声生成、動画合成を行うためのスクリプト群です。  
このREADMEは `scripts_dub` を使った「吹き替え動画作成」用途に限定しています（`scripts_ymm` は対象外）。
主に以下のディレクトリを使います。

- `scripts_dub/`: 吹き替え系パイプライン
- `data/`: 入力/中間/出力データ、フォント、BGMなど

## 1. 初期セットアップ

### macOS / Linux

```bash
cd /Users/ryokondo/Documents/iMac_Python/yt_video_dub
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
cd C:\Users\...\yt_video_dub
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Whisper文字起こしを使う場合は追加で以下を実行:

```bash
pip install faster-whisper
```

## 2. 吹き替え作成の基本フロー（scripts_dub）

```bash
# 1) 文字起こし
python scripts_dub/t02_whisper_transcript_tui_v1.py

# 2) 翻訳（OpenAIは使わず Ollama を使用）
python scripts_dub/t03_gemma_translation.py

# 3) 文章整形・チェック
python scripts_dub/t04_format_text.py
python scripts_dub/t04-3_check_text_length.py

# 4) 音声生成（VOICEVOX）
python scripts_dub/t05_voicevox_tts_jp_multi_v2.py

# 5) 動画合成
python scripts_dub/t06_save_slow_movie_audio_gpu.py
python scripts_dub/t07_combine_segments_gpu_v2.py
```

## 3. 注意点

- `faster-whisper` は実行環境により `ffmpeg` が必要です。
- `faster-whisper` は環境によって `av` のビルド依存（`pkg-config` など）が必要です。
- Python 3.14 で依存ビルドが失敗する場合は、Python 3.11 か 3.12 の仮想環境利用を推奨します。
- GPU利用時は環境に応じて CUDA / cuDNN の準備が必要です（`memo.md` 参照）。
- 翻訳は `ollama` 前提です（ローカルで Ollama を起動した状態で実行）。
- `scripts_dub/t03_gpt_translation.py` は OpenAI API 用のため、この構成では使用しません。
