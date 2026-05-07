#!/usr/bin/env python3
"""Run the planned Phase 1 steps.

This wrapper is intentionally a skeleton only for now.
"""

from __future__ import annotations

import argparse


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
        required=True,
        help="Job identifier used as output/<job_id>/.",
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


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    raise NotImplementedError(
        "TODO: wire Phase 1 steps together in a later phase."
    )


if __name__ == "__main__":
    raise SystemExit(main())
