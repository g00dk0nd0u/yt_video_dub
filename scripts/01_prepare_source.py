#!/usr/bin/env python3
"""Prepare a job workspace and register source input.

Output layout is fixed under `output/<job_id>/`.
This skeleton defines the CLI contract only and intentionally stops before
performing any processing.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare source assets for a dubbing job."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--youtube-url",
        help="YouTube URL to prepare as the source input.",
    )
    source_group.add_argument(
        "--local-video",
        help="Local video file to copy into output/<job_id>/source.mp4.",
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
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    raise NotImplementedError(
        "TODO: implement source preparation in a later phase."
    )


if __name__ == "__main__":
    raise SystemExit(main())
