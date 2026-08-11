#!/usr/bin/env python3
"""Display stored TTS concurrency samples without recommending a worker count."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from path_layout import build_job_paths


COMPARABILITY_FIELDS = (
    "workload_hash", "segment_ids", "speaker_id", "base_url", "selected_units",
    "benchmark_schema_version", "max_speed_scale", "timeout_seconds",
    "hardware.system", "hardware.machine",
)


def _nested_value(sample: dict[str, Any], field: str) -> Any:
    value: Any = sample
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def load_samples(directory: Path) -> list[dict[str, Any]]:
    samples = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            samples.append(payload)
    return sorted(samples, key=lambda item: (item.get("workers", 0), item.get("run_id", "")))


def comparability_warnings(samples: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for field in COMPARABILITY_FIELDS:
        values = {json.dumps(_nested_value(sample, field), sort_keys=True) for sample in samples}
        if len(values) > 1:
            warnings.append(f"NOT COMPARABLE: {field} differs between samples.")
    return warnings


def format_summary(samples: list[dict[str, Any]]) -> str:
    lines = [
        "Workers  Speech Units  TTS sec  Units/s  Normal  Speed-fit  OK/FIT/NG  Skipped  Errors  Workload hash"
    ]
    for sample in samples:
        fit = f"{sample.get('fit_ok_count', 0)}/{sample.get('fit_fitted_count', 0)}/{sample.get('fit_ng_count', 0)}"
        tts_seconds = sample.get("tts_wall_seconds")
        throughput = sample.get("units_per_second")
        tts_display = f"{tts_seconds:.2f}" if isinstance(tts_seconds, (int, float)) else "-"
        throughput_display = f"{throughput:.2f}" if isinstance(throughput, (int, float)) else "-"
        errors = sample.get("errors")
        error_count = len(errors) if isinstance(errors, list) else 0
        workload = sample.get("workload_hash")
        workload_display = workload[:12] if isinstance(workload, str) else "-"
        lines.append(
            f"{sample.get('workers', '-'):>7}  {sample.get('speech_units', '-'):>12}  "
            f"{tts_display:>7}  {throughput_display:>7}  "
            f"{sample.get('normal_synthesis_count', 0):>6}  "
            f"{sample.get('speed_fit_synthesis_count', 0):>9}  {fit:>9}  "
            f"{sample.get('skipped_empty_units', 0):>7}  {error_count:>6}  {workload_display}"
        )
    warnings = comparability_warnings(samples)
    if warnings:
        lines.extend(["", *warnings])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args(argv)
    directory = build_job_paths(args.output_dir, args.job_id).metrics_dir / "concurrency_benchmarks"
    samples = load_samples(directory)
    if not samples:
        parser.error(f"No benchmark samples found in {directory}")
    print(format_summary(samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
