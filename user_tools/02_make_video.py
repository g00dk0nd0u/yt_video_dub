#!/usr/bin/env python3
"""Create a dubbed video from translated text files."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = "output"
BASE_URL = "http://127.0.0.1:10101"
SPEAKER_ID = 1937616896
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"
VIDEO_TAIL_CUSHION_RATIO = 0.015
VIDEO_TAIL_CUSHION_MAX_SEC = 0.18


def _load_pipeline_module():
    script_path = REPO_ROOT / "scripts" / "91_run_local_tts_pipeline.py"
    module_name = "user_tool_make_video"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_path_layout_module():
    script_path = REPO_ROOT / "scripts" / "path_layout.py"
    module_name = "user_tool_path_layout_make_video"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _list_video_dirs() -> list[Path]:
    output_dir = REPO_ROOT / OUTPUT_DIR
    if not output_dir.exists():
        return []
    return sorted(
        [
            path
            for path in output_dir.iterdir()
            if path.is_dir() and path.name not in {"__pycache__"}
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _latest_video_id() -> str:
    video_dirs = _list_video_dirs()
    if not video_dirs:
        return ""
    return video_dirs[0].name


def _prompt_with_default(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def _prompt_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    value = input(f"{prompt} {suffix}: ").strip().lower()
    if value == "":
        return default_yes
    return value in {"y", "yes"}


def main() -> int:
    os.chdir(REPO_ROOT)

    latest_video_id = _latest_video_id()
    if latest_video_id == "":
        print("output/ に動画フォルダが見つかりません。")
        print("先に user_tools/01_new_youtube.py を実行してください。")
        return 1

    video_id = _prompt_with_default("動画ID", latest_video_id)
    make_audio = _prompt_yes_no("日本語音声を作成しますか？", default_yes=True)
    make_mp4 = _prompt_yes_no("音と映像を合わせたMP4動画を作りますか？", default_yes=True)

    pipeline = _load_pipeline_module()
    args = [
        "--job-id",
        video_id,
        "--output-dir",
        OUTPUT_DIR,
        "--base-url",
        BASE_URL,
        "--speaker-id",
        str(SPEAKER_ID),
        "--ffmpeg-bin",
        FFMPEG_BIN,
        "--ffprobe-bin",
        FFPROBE_BIN,
        "--video-tail-cushion-ratio",
        str(VIDEO_TAIL_CUSHION_RATIO),
        "--video-tail-cushion-max-sec",
        str(VIDEO_TAIL_CUSHION_MAX_SEC),
    ]
    if make_audio:
        args.append("--force-tts")
    if make_mp4:
        args.append("--mux-video")

    pipeline.main(args)

    path_layout = _load_path_layout_module()
    paths = path_layout.build_job_paths(OUTPUT_DIR, video_id)
    print("")
    print(f"完成動画: {paths.dubbed_video_synced_path.as_posix()}")
    print(
        f"軽量ファイルは {paths.job_dir.as_posix()}/ 配下の json / txt / srt をそのままGitHubにpushできます。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
