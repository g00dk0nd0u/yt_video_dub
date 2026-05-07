#!/usr/bin/env python3
"""Prepare source files, transcripts, and translation chunks."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare source files, transcripts, and translation chunks."
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    prepare_source = _load_script_module("01_prepare_source.py")
    get_transcript = _load_script_module("02_get_transcript.py")
    make_chunks = _load_script_module("03_make_translation_chunks.py")
    job_id = prepare_source.prepare_source(
        youtube_url=args.youtube_url,
        local_video=args.local_video,
        job_id=args.job_id,
        output_dir=args.output_dir,
    )

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
    print("Preparation completed.")
    print(f"Job ID: {job_id}")
    print(
        "Next step in Codex: read docs/translation_mode.md and translate "
        f"output/{job_id}/03_translation_input/chunk_*.txt into "
        f"output/{job_id}/04_translation_output/chunk_*.txt."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
