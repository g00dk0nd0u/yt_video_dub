#!/usr/bin/env python3
"""Create translation work files from a YouTube URL."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = "output"


def _load_prepare_module():
    script_path = REPO_ROOT / "scripts" / "run_prepare.py"
    module_name = "user_tool_prepare_youtube"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_video_id(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url.strip())
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.lstrip("/").split("/")[0]

    query_video_id = parse_qs(parsed.query).get("v", [""])[0].strip()
    if query_video_id:
        return query_video_id

    if parsed.path.startswith("/shorts/"):
        return parsed.path.split("/shorts/", 1)[1].split("/")[0]

    if parsed.path.startswith("/embed/"):
        return parsed.path.split("/embed/", 1)[1].split("/")[0]

    return ""


def main() -> int:
    os.chdir(REPO_ROOT)

    youtube_url = input("YouTube URLを貼ってください: ").strip()
    if youtube_url == "":
        print("入力が空だったため終了しました。")
        return 0

    prepare = _load_prepare_module()
    prepare.main(
        [
            "--youtube-url",
            youtube_url,
            "--output-dir",
            OUTPUT_DIR,
        ]
    )

    job_id = _extract_video_id(youtube_url)
    if job_id == "":
        print("準備は完了しましたが、動画IDの表示に失敗しました。")
        print("output/ を開いて作成されたフォルダを確認してください。")
        return 0

    translation_input = f"output/{job_id}/translation_input/"
    translation_output = f"output/{job_id}/translation_output/"

    print("")
    print("準備が完了しました")
    print(f"動画ID: {job_id}")
    print(f"翻訳元ファイル: {translation_input}")
    print(f"翻訳保存先: {translation_output}")
    print("次にやること:")
    print("Codexに docs/translation_mode.md を読ませて、")
    print("translation_input/chunk_*.txt を日本語化し、")
    print("translation_output/chunk_*.txt に保存してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
