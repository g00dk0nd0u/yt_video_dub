#!/usr/bin/env python3
"""Generate Japanese TTS assets with AivisSpeech.

This skeleton intentionally documents the connection contract only.
The exact API calls remain a TODO until the endpoint details are confirmed.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate TTS assets with AivisSpeech for a dubbing job."
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
        "--base-url",
        required=True,
        help="Base URL for the local AivisSpeech API.",
    )
    parser.add_argument(
        "--speaker-id",
        required=True,
        help="AivisSpeech speaker ID to use.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    raise NotImplementedError(
        "TODO: implement AivisSpeech integration after confirming the API contract."
    )


if __name__ == "__main__":
    raise SystemExit(main())
