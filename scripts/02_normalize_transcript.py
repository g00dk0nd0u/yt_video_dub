#!/usr/bin/env python3
"""Create deterministic dubbing utterances from raw YouTube captions."""

from __future__ import annotations

import argparse
import json

from path_layout import build_job_paths
from transcript_normalizer import normalize_segments


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args(argv)
    paths = build_job_paths(args.output_dir, args.job_id)
    raw_path = paths.resolve_transcript_json_path()
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    units = normalize_segments(payload.get("segments", []))
    if not units:
        raise RuntimeError("Raw transcript did not produce any normalized utterances.")
    output = {
        "video_id": payload.get("video_id"),
        "source_transcript": paths.rel_to_job(raw_path),
        "units": units,
    }
    paths.transcript_normalized_json_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines: list[str] = []
    for index, unit in enumerate(units, 1):
        lines += [
            str(index),
            f"{_timestamp(unit['source_start'])} --> {_timestamp(unit['source_end'])}",
            unit["source_text"],
            "",
        ]
    paths.transcript_normalized_srt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Created {len(units)} normalized utterance(s) for job: {args.job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
