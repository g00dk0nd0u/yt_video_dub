#!/usr/bin/env python3
"""Deprecated review export helper for the old review_outputs workflow."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


FILES_TO_COPY = (
    "01_source/job.json",
    "02_transcript/transcript_original.json",
    "02_transcript/transcript_original.srt",
    "05_segments/translated_segments.json",
    "05_segments/translated_segments.srt",
    "07_audio/dub_audio_manifest.json",
    "03_translation_input/manifest.json",
    "06_tts/tts_manifest.json",
    "08_synced_video/synced_video_manifest.json",
)
GLOBS_TO_COPY = (
    "03_translation_input/chunk_*.txt",
    "04_translation_output/chunk_*.txt",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy lightweight pipeline artifacts into a reviewable directory."
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
        "--review-dir",
        default="review_outputs",
        help="Destination review directory. Default: review_outputs",
    )
    return parser


def _copy_file(source_path: Path, source_job_dir: Path, review_job_dir: Path) -> Path:
    relative_path = source_path.relative_to(source_job_dir)
    destination_path = review_job_dir / relative_path
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return destination_path


def _collect_files(source_job_dir: Path) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()

    for relative_path in FILES_TO_COPY:
        source_path = source_job_dir / relative_path
        if source_path.is_file() and source_path not in seen:
            files.append(source_path)
            seen.add(source_path)

    for pattern in GLOBS_TO_COPY:
        for source_path in sorted(source_job_dir.glob(pattern)):
            if source_path.is_file() and source_path not in seen:
                files.append(source_path)
                seen.add(source_path)

    return files


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    print(
        "Warning: scripts/90_export_review_output.py is deprecated. "
        "Use lightweight files under output/<job_id>/ directly."
    )

    source_job_dir = Path(args.output_dir) / args.job_id
    if not source_job_dir.is_dir():
        raise FileNotFoundError(f"Missing source job directory: {source_job_dir}")

    review_job_dir = Path(args.review_dir) / args.job_id
    files_to_copy = _collect_files(source_job_dir)

    if not files_to_copy:
        print(f"No review files found under: {source_job_dir}")
        return 0

    copied_paths: list[Path] = []
    for source_path in files_to_copy:
        copied_paths.append(_copy_file(source_path, source_job_dir, review_job_dir))

    for path in copied_paths:
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
