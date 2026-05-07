#!/usr/bin/env python3
"""Run the planned Phase 2 steps.

This wrapper currently runs only the translated-segment rebuild step.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 2 wrapper: rebuild translations, generate TTS, and mux video."
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="Job identifier used as output/<job_id>/.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory. Default: output",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL for the local AivisSpeech API.",
    )
    parser.add_argument(
        "--speaker-id",
        required=True,
        help="AivisSpeech speaker ID to use.",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default="ffmpeg",
        help="ffmpeg binary name or path. Default: ffmpeg",
    )
    return parser


def _load_script_module(filename: str):
    script_path = Path(__file__).with_name(filename)
    module_name = f"phase2_{filename.replace('.', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    build_translated_segments = _load_script_module(
        "04_build_translated_segments.py"
    )
    build_translated_segments.main(
        [
            "--job-id",
            args.job_id,
            "--output-dir",
            args.output_dir,
        ]
    )

    print("")
    print("Phase 2 step 1 completed.")
    print("Next steps not implemented yet: TTS, AivisSpeech, ffmpeg mux.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
