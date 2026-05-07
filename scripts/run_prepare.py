#!/usr/bin/env python3
"""Run the Phase 1 preparation steps."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

from yt_dlp import YoutubeDL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 1 wrapper: prepare source, transcript, and translation chunks."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--youtube-url",
        help="YouTube URL to prepare as the source input.",
    )
    source_group.add_argument(
        "--local-video",
        help="Local video file to prepare as the source input.",
    )
    parser.add_argument(
        "--job-id",
        help="Job identifier used as output/<job_id>/. Default: YouTube video ID",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory. Default: output",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Preferred transcript language code. Default: en",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="Maximum segment count per translation chunk.",
    )
    return parser


def _load_script_module(filename: str):
    script_path = Path(__file__).with_name(filename)
    module_name = f"phase1_{filename.replace('.', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_job_id(youtube_url: str) -> str:
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    video_id = info.get("id") if info else None
    if not video_id:
        raise RuntimeError("Failed to derive job_id from the YouTube URL.")
    return video_id


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    job_id = args.job_id
    if not job_id and args.youtube_url:
        job_id = _resolve_job_id(args.youtube_url)

    prepare_source = _load_script_module("01_prepare_source.py")
    get_transcript = _load_script_module("02_get_transcript.py")
    make_chunks = _load_script_module("03_make_translation_chunks.py")

    prepare_args = ["--output-dir", args.output_dir]
    if job_id:
        prepare_args.extend(["--job-id", job_id])
    if args.youtube_url:
        prepare_args.extend(["--youtube-url", args.youtube_url])
    else:
        prepare_args.extend(["--local-video", args.local_video])
    prepare_source.main(prepare_args)

    if not job_id:
        raise RuntimeError("Phase 1 could not determine a job_id.")

    get_transcript.main(
        [
            "--job-id",
            job_id,
            "--output-dir",
            args.output_dir,
            "--language",
            args.language,
        ]
    )
    make_chunks.main(
        [
            "--job-id",
            job_id,
            "--output-dir",
            args.output_dir,
            "--chunk-size",
            str(args.chunk_size),
        ]
    )

    print("")
    print("Phase 1 completed.")
    print(f"Job ID: {job_id}")
    print("Next step in Codex: read docs/translation_mode.md and translate the files in translation_input/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
