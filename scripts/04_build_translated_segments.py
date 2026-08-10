#!/usr/bin/env python3
"""Rebuild translated segment files from translation_output chunks."""

from __future__ import annotations

import argparse
import json

from path_layout import build_job_paths
from translation_handoff import load_jsonl as _load_jsonl
from translation_handoff import load_manifest as _load_manifest
from translation_handoff import validate_chunk_pair as _validate_chunk_pair


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


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _write_translated_segments_json(output_path, source_manifest: str, job_id: str, segments: list[dict]) -> None:
    payload = {
        "job_id": job_id,
        "source_manifest": source_manifest,
        "segments": segments,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_translated_segments_srt(output_path, segments: list[dict]) -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                (
                    f"{_format_srt_timestamp(segment['start'])} --> "
                    f"{_format_srt_timestamp(segment['end'])}"
                ),
                str(segment["text"]),
                "",
            ]
        )
    output_path.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = build_job_paths(args.output_dir, args.job_id)
    paths.segments_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = paths.resolve_translation_manifest_path()
    manifest = _load_manifest(manifest_path)
    translation_input_dir = paths.resolve_translation_input_dir()
    translation_output_dir = paths.resolve_translation_output_dir()

    translated_segments: list[dict] = []
    for chunk in manifest["chunks"]:
        chunk_file = chunk.get("file")
        if not chunk_file:
            raise RuntimeError("Each manifest chunk must include a file entry.")

        source_path = translation_input_dir / chunk_file
        translated_path = translation_output_dir / chunk_file
        source_items = _load_jsonl(source_path)
        translated_items = _load_jsonl(translated_path)
        translated_segments.extend(
            _validate_chunk_pair(source_items, translated_items, source_path, translated_path)
        )

    expected_total = manifest.get("total_segments")
    if expected_total is not None and len(translated_segments) != expected_total:
        raise RuntimeError(
            "Translated segment count does not match manifest total_segments: "
            f"{len(translated_segments)} != {expected_total}"
        )

    _write_translated_segments_json(
        paths.translated_segments_json_path,
        paths.rel_to_job(manifest_path),
        args.job_id,
        translated_segments,
    )
    _write_translated_segments_srt(paths.translated_segments_srt_path, translated_segments)
    print(f"Built translated segment artifacts for job: {args.job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
