#!/usr/bin/env python3
"""Move lightweight artifacts from the legacy layout into the numbered layout."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from path_layout import build_job_paths


LIGHTWEIGHT_MOVES = (
    ("job.json", "01_source/job.json"),
    ("transcript_original.json", "02_transcript/transcript_original.json"),
    ("transcript_original.srt", "02_transcript/transcript_original.srt"),
    ("translation_input", "03_translation_input"),
    ("translation_output", "04_translation_output"),
    ("translated_segments.json", "05_segments/translated_segments.json"),
    ("translated_segments.srt", "05_segments/translated_segments.srt"),
    ("tts/tts_manifest.json", "06_tts/tts_manifest.json"),
    ("dub_audio_manifest.json", "07_audio/dub_audio_manifest.json"),
    ("synced_video_manifest.json", "08_synced_video/synced_video_manifest.json"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate lightweight files from legacy output/<job_id>/ layout."
    )
    parser.add_argument(
        "--job-id",
        default="HFM3se4lNiw",
        help="Job identifier under output/<job_id>/. Default: HFM3se4lNiw",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory. Default: output",
    )
    return parser


def _move_path(source_path: Path, target_path: Path) -> str:
    if not source_path.exists():
        return f"skip missing: {source_path}"
    if target_path.exists():
        return f"skip exists: {target_path}"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(target_path))
    return f"moved: {source_path} -> {target_path}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = build_job_paths(args.output_dir, args.job_id)
    if not paths.job_dir.is_dir():
        raise FileNotFoundError(f"Missing job directory: {paths.job_dir}")

    for legacy_rel, new_rel in LIGHTWEIGHT_MOVES:
        print(_move_path(paths.job_dir / legacy_rel, paths.job_dir / new_rel))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
