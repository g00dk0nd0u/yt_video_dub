#!/usr/bin/env python3
"""Rebuild translated segment files from translation_output chunks."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build translated segment artifacts from translation_output."
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
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    raise NotImplementedError(
        "TODO: implement translated segment reconstruction in a later phase."
    )


if __name__ == "__main__":
    raise SystemExit(main())
