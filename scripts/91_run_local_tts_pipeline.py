#!/usr/bin/env python3
"""Run the local dubbing workflow with repo-friendly defaults."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any


DEFAULT_JOB_ID = "phase1_smoke_rick"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_BASE_URL = "http://127.0.0.1:10101"
DEFAULT_SPEAKER_ID = 1937616896
DEFAULT_VIDEO_TAIL_CUSHION_RATIO = 0.015
DEFAULT_VIDEO_TAIL_CUSHION_MAX_SEC = 0.18
SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run translated text rebuild, audio generation, dub-audio build, and optional video creation."
    )
    parser.add_argument(
        "--job-id",
        default=DEFAULT_JOB_ID,
        help=f"Job identifier under output/<job_id>/. Default: {DEFAULT_JOB_ID}",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL for the local AivisSpeech API. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--speaker-id",
        default=DEFAULT_SPEAKER_ID,
        type=int,
        help=f"Speaker ID to use for speech generation. Default: {DEFAULT_SPEAKER_ID}",
    )
    parser.add_argument(
        "--mux-video",
        action="store_true",
        help="Run scripts/09_build_synced_video.py after scripts/07_build_dub_audio.py.",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default="ffmpeg",
        help='ffmpeg binary name or path for synced video build. Default: "ffmpeg"',
    )
    parser.add_argument(
        "--ffprobe-bin",
        default="ffprobe",
        help='ffprobe binary name or path for synced video build. Default: "ffprobe"',
    )
    parser.add_argument(
        "--video-tail-cushion-ratio",
        type=float,
        default=DEFAULT_VIDEO_TAIL_CUSHION_RATIO,
        help=(
            "Extra duration ratio for slowed video segments. "
            f"Default: {DEFAULT_VIDEO_TAIL_CUSHION_RATIO}"
        ),
    )
    parser.add_argument(
        "--video-tail-cushion-max-sec",
        type=float,
        default=DEFAULT_VIDEO_TAIL_CUSHION_MAX_SEC,
        help=(
            "Maximum extra duration for slowed video segments. "
            f"Default: {DEFAULT_VIDEO_TAIL_CUSHION_MAX_SEC}"
        ),
    )
    parser.add_argument(
        "--force-tts",
        action="store_true",
        help="Pass --force to scripts/06_generate_tts_segments.py.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Pass --resume to scripts/06_generate_tts_segments.py.",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        help="1-based translated segment index to start audio generation from.",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        help="1-based translated segment index to end audio generation at.",
    )
    parser.add_argument(
        "--skip-build-translated",
        action="store_true",
        help="Skip scripts/04_build_translated_segments.py.",
    )
    return parser


def _load_script_module(filename: str) -> Any:
    script_path = SCRIPT_DIR / filename
    module_name = f"local_tts_pipeline_{filename.replace('.', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_step(label: str, module_filename: str, step_args: list[str]) -> None:
    module = _load_script_module(module_filename)
    print(f"== {label} ==")
    module.main(step_args)
    print("")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    common_job_args = [
        "--job-id",
        args.job_id,
        "--output-dir",
        args.output_dir,
    ]

    if not args.skip_build_translated:
        _run_step(
            "Step 1: build translated text data",
            "04_build_translated_segments.py",
            common_job_args,
        )

    tts_args = [
        "--job-id",
        args.job_id,
        "--output-dir",
        args.output_dir,
        "--base-url",
        args.base_url,
        "--speaker-id",
        str(args.speaker_id),
    ]
    if args.resume:
        tts_args.append("--resume")
    if args.force_tts:
        tts_args.append("--force")
    if args.start_index is not None:
        tts_args.extend(["--start-index", str(args.start_index)])
    if args.end_index is not None:
        tts_args.extend(["--end-index", str(args.end_index)])

    _run_step(
        "Step 2: generate Japanese audio segments",
        "06_generate_tts_segments.py",
        tts_args,
    )
    _run_step(
        "Step 3: combine Japanese audio",
        "07_build_dub_audio.py",
        common_job_args,
    )
    if args.mux_video:
        _run_step(
            "Step 4: create synced dubbed video",
            "09_build_synced_video.py",
            common_job_args
            + [
                "--ffmpeg-bin",
                args.ffmpeg_bin,
                "--ffprobe-bin",
                args.ffprobe_bin,
                "--video-tail-cushion-ratio",
                str(args.video_tail_cushion_ratio),
                "--video-tail-cushion-max-sec",
                str(args.video_tail_cushion_max_sec),
                "--max-audio-speed",
                "1.25",
            ],
        )
    print("Video build completed.")
    print(f"Lightweight files under output/{args.job_id}/ (*.json, *.txt, *.srt) can be committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
