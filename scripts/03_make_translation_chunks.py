#!/usr/bin/env python3
"""Create translation input chunks from the original transcript."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create translation_input files from transcript data."
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
        "TODO: implement translation chunk generation in a later phase."
    )


if __name__ == "__main__":
    raise SystemExit(main())
