#!/usr/bin/env python3
"""Fetch the original transcript for a prepared job.

Primary path: `youtube-transcript-api`.
Whisper fallback is intentionally left as a TODO for a later phase.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch transcript data for a prepared dubbing job."
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="Job identifier under output/<job_id>/.",
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
        "--whisper-model",
        default="small",
        help="Reserved for future Whisper fallback support.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    raise NotImplementedError(
        "TODO: implement youtube-transcript-api path first; Whisper fallback later."
    )


if __name__ == "__main__":
    raise SystemExit(main())
