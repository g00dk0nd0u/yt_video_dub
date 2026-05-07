#!/usr/bin/env python3
"""Run the planned Phase 2 steps.

This wrapper is intentionally a skeleton only for now.
"""

from __future__ import annotations

import argparse


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


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    raise NotImplementedError(
        "TODO: wire Phase 2 steps together in a later phase."
    )


if __name__ == "__main__":
    raise SystemExit(main())
