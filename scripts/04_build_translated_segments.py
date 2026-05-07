#!/usr/bin/env python3
"""Rebuild translated segment files from translation_output chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


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


def _load_manifest(job_dir: Path) -> dict:
    manifest_path = job_dir / "translation_input" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest file: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("translation_input/manifest.json does not contain any chunks.")
    return manifest


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing chunk file: {path}")

    items: list[dict] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSONL in {path} at line {line_number}.") from exc
        if not isinstance(item, dict):
            raise RuntimeError(f"Expected a JSON object in {path} at line {line_number}.")
        items.append(item)
    return items


def _validate_chunk_pair(
    source_items: list[dict],
    translated_items: list[dict],
    source_path: Path,
    translated_path: Path,
) -> list[dict]:
    if len(source_items) != len(translated_items):
        raise RuntimeError(
            "Chunk line count mismatch: "
            f"{translated_path} has {len(translated_items)} lines, "
            f"but {source_path} has {len(source_items)}."
        )

    merged_items: list[dict] = []
    for index, (source_item, translated_item) in enumerate(
        zip(source_items, translated_items),
        start=1,
    ):
        for field in ("segment_id", "start", "end"):
            if translated_item.get(field) != source_item.get(field):
                raise RuntimeError(
                    f"Chunk validation failed at {translated_path} line {index}: "
                    f"{field} does not match the source chunk."
                )

        merged_items.append(
            {
                "segment_id": source_item["segment_id"],
                "start": source_item["start"],
                "end": source_item["end"],
                "text": translated_item.get("text", ""),
            }
        )
    return merged_items


def _write_translated_segments_json(job_dir: Path, job_id: str, segments: list[dict]) -> None:
    payload = {
        "job_id": job_id,
        "source_manifest": "translation_input/manifest.json",
        "segments": segments,
    }
    (job_dir / "translated_segments.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_translated_segments_srt(job_dir: Path, segments: list[dict]) -> None:
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
    (job_dir / "translated_segments.srt").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    job_dir = Path(args.output_dir) / args.job_id
    manifest = _load_manifest(job_dir)
    translation_input_dir = job_dir / "translation_input"
    translation_output_dir = job_dir / "translation_output"

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

    _write_translated_segments_json(job_dir, args.job_id, translated_segments)
    _write_translated_segments_srt(job_dir, translated_segments)
    print(f"Built translated segment artifacts for job: {args.job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
