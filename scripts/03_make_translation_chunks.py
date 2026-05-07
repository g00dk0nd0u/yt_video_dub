#!/usr/bin/env python3
"""Create translation input chunks from the original transcript."""

from __future__ import annotations

import argparse
import json

from path_layout import build_job_paths


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


def _load_segments(transcript_path) -> list[dict]:
    if not transcript_path.exists():
        raise FileNotFoundError(f"Missing transcript file: {transcript_path}")
    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("transcript_original.json does not contain any segments.")
    return segments


def _chunked(items: list[dict], chunk_size: int):
    for index in range(0, len(items), chunk_size):
        yield index // chunk_size + 1, items[index : index + chunk_size]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be greater than zero.")

    paths = build_job_paths(args.output_dir, args.job_id)
    paths.ensure_prepare_dirs()
    segments = _load_segments(paths.resolve_transcript_json_path())
    translation_input_dir = paths.translation_input_dir
    translation_output_dir = paths.translation_output_dir

    manifest_chunks = []
    for chunk_index, chunk_segments in _chunked(segments, args.chunk_size):
        chunk_name = f"chunk_{chunk_index:04}.txt"
        chunk_path = translation_input_dir / chunk_name
        chunk_lines = [
            json.dumps(
                {
                    "segment_id": segment["segment_id"],
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"],
                },
                ensure_ascii=False,
            )
            for segment in chunk_segments
        ]
        chunk_path.write_text("\n".join(chunk_lines) + "\n", encoding="utf-8")
        manifest_chunks.append(
            {
                "chunk_id": f"chunk_{chunk_index:04}",
                "file": chunk_name,
                "segment_count": len(chunk_segments),
                "segment_ids": [segment["segment_id"] for segment in chunk_segments],
            }
        )

    manifest = {
        "job_id": args.job_id,
        "source_transcript": paths.rel_to_job(paths.transcript_json_path),
        "format": "jsonl",
        "chunk_size": args.chunk_size,
        "total_segments": len(segments),
        "chunks": manifest_chunks,
    }
    paths.translation_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created {len(manifest_chunks)} translation chunk(s) for job: {args.job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
