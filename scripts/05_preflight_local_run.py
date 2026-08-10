#!/usr/bin/env python3
"""Validate translation handoff artifacts without external services."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from path_layout import build_job_paths
from translation_handoff import load_jsonl, load_manifest, validate_chunk_pair


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check whether a job is ready for local TTS.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", default="output")
    return parser


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _canonical_segments(segments: list[dict]) -> list[dict]:
    return [{key: item[key] for key in ("segment_id", "start", "end", "text")} for item in segments]


def _fingerprint(segments: list[dict]) -> str:
    canonical = json.dumps(_canonical_segments(segments), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _density(segments: list[dict]) -> dict:
    items = []
    for order, segment in enumerate(segments):
        duration = segment["end"] - segment["start"]
        count = len("".join(segment["text"].split()))
        items.append({
            "segment_id": segment["segment_id"], "start": segment["start"],
            "end": segment["end"], "duration": duration, "character_count": count,
            "chars_per_second": round(count / duration, 6), "_order": order,
        })
    items.sort(key=lambda item: (-item["chars_per_second"], item["_order"]))
    for item in items:
        item.pop("_order")
    return {
        "max_chars_per_second": items[0]["chars_per_second"] if items else 0.0,
        "top_segments": items[:10],
    }


def _validate_final(path: Path, expected: list[dict], expected_total: int | None) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing translated segments file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in translated segments: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("segments"), list):
        raise RuntimeError("translated_segments.json must contain a segments list.")
    segments = payload["segments"]
    if expected_total is not None and len(segments) != expected_total:
        raise RuntimeError(
            f"Translated segment count does not match manifest total_segments: {len(segments)} != {expected_total}"
        )
    seen: set[str] = set()
    previous_start: float | None = None
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise RuntimeError(f"Translated segment {index} must be a JSON object.")
        segment_id = segment.get("segment_id")
        if not isinstance(segment_id, str):
            raise RuntimeError(f"Translated segment {index} segment_id must be a string.")
        if segment_id in seen:
            raise RuntimeError(f"Duplicate segment_id in translated segments: {segment_id}")
        seen.add(segment_id)
        if not isinstance(segment.get("text"), str):
            raise RuntimeError(f"Translated segment {segment_id} text must be a string.")
        start, end = segment.get("start"), segment.get("end")
        if not _number(start) or not _number(end):
            raise RuntimeError(f"Translated segment {segment_id} timing must be finite numbers.")
        if start < 0 or end <= start:
            raise RuntimeError(f"Translated segment {segment_id} has invalid timing: start={start}, end={end}.")
        if previous_start is not None and start < previous_start:
            raise RuntimeError(f"Translated segment {segment_id} is out of timeline order.")
        previous_start = start
    if _canonical_segments(segments) != _canonical_segments(expected):
        raise RuntimeError("translated_segments.json is stale or does not match translation chunks.")
    return segments


def run_preflight(job_id: str, output_dir: str | Path) -> dict:
    paths = build_job_paths(output_dir, job_id)
    report = {
        "job_id": job_id, "status": "not_ready", "chunk_count": 0, "segment_count": 0,
        "source_empty_units": 0, "translated_empty_units": 0,
        "translation_fingerprint": None, "errors": [], "warnings": [],
        "density": {"max_chars_per_second": 0.0, "top_segments": []},
    }
    try:
        manifest = load_manifest(paths.resolve_translation_manifest_path())
        report["chunk_count"] = len(manifest["chunks"])
        expected = []
        source_dir = paths.resolve_translation_input_dir()
        output_dir_path = paths.resolve_translation_output_dir()
        for chunk in manifest["chunks"]:
            source = load_jsonl(source_dir / chunk["file"])
            translated = load_jsonl(output_dir_path / chunk["file"])
            report["source_empty_units"] += sum(not item.get("text", "").strip() for item in source if isinstance(item.get("text"), str))
            report["translated_empty_units"] += sum(not item.get("text", "").strip() for item in translated if isinstance(item.get("text"), str))
            expected.extend(validate_chunk_pair(
                source, translated, source_dir / chunk["file"], output_dir_path / chunk["file"],
                reject_blank_translation=True,
            ))
        total = manifest.get("total_segments")
        if total is not None and len(expected) != total:
            raise RuntimeError(f"Translation chunks contain {len(expected)} segments; manifest expects {total}.")
        segments = _validate_final(paths.resolve_translated_segments_json_path(), expected, total)
        report.update(status="ready", segment_count=len(segments),
                      translation_fingerprint=_fingerprint(segments), density=_density(segments))
    except (FileNotFoundError, OSError, UnicodeError, RuntimeError, KeyError, TypeError, ValueError) as exc:
        report["errors"].append(str(exc))
    paths.segments_dir.mkdir(parents=True, exist_ok=True)
    paths.local_run_preflight_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_preflight(args.job_id, args.output_dir)
    print(f"Local TTS preflight: {report['status']}")
    for error in report["errors"]:
        print(f"- {error}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
