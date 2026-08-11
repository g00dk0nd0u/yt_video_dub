#!/usr/bin/env python3
"""Run the fixed AivisSpeech 1/2/4-worker benchmark matrix."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from path_layout import build_job_paths


CANDIDATE_ORDER = (1, 2, 4)
MATRIX_SCHEMA_VERSION = 1


def _load_script(name: str) -> ModuleType:
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(f"matrix_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper script: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load_script("92_benchmark_tts_concurrency.py")
comparison = _load_script("93_compare_tts_benchmarks.py")
preflight = _load_script("05_preflight_local_run.py")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--base-url", default=benchmark.DEFAULT_BASE_URL)
    parser.add_argument("--speaker-id", type=int, default=benchmark.DEFAULT_SPEAKER_ID)
    parser.add_argument("--timeout", type=float, default=benchmark.DEFAULT_TIMEOUT)
    parser.add_argument("--segment-id", action="append", dest="segment_ids")
    parser.add_argument("--start-index", type=int)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--limit", type=int)
    return parser


def _matrix_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{uuid.uuid4().hex[:12]}"


def save_matrix(directory: Path, artifact: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    while True:
        path = directory / f"{artifact['matrix_run_id']}.json"
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(artifact, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            return path
        except FileExistsError:
            artifact["matrix_run_id"] = _matrix_run_id()


def _artifact(args: argparse.Namespace, workload: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    return {
        "matrix_schema_version": MATRIX_SCHEMA_VERSION,
        "job_id": args.job_id,
        "matrix_run_id": _matrix_run_id(),
        "candidate_order": list(CANDIDATE_ORDER),
        "workload_hash": benchmark.workload_hash(workload, args.speaker_id),
        "selected_units": len(workload),
        "segment_ids": [segment["segment_id"] for _, segment in workload],
        "base_url": args.base_url.rstrip("/"),
        "speaker_id": args.speaker_id,
        "timeout_seconds": args.timeout,
        "warmup": {"status": "pending", "segment_id": None},
        "samples": [],
        "comparability_status": "not_checked",
        "comparability_warnings": [],
    }


def _check_comparability(
    samples: list[dict[str, Any]], artifact: dict[str, Any],
) -> list[str]:
    warnings = comparison.comparability_warnings(samples)
    for field in ("workload_hash", "segment_ids", "selected_units"):
        if any(sample.get(field) != artifact[field] for sample in samples):
            warnings.append(f"NOT COMPARABLE: {field} differs from matrix workload snapshot.")
    return list(dict.fromkeys(warnings))


def _candidate_entry(
    workers: int, sample: dict[str, Any], sample_path: Path, job_directory: Path,
) -> dict[str, Any]:
    errors = sample.get("errors")
    errors = errors if isinstance(errors, list) else []
    return {
        "workers": workers,
        "status": sample["status"],
        "path": sample_path.relative_to(job_directory).as_posix(),
        "error_count": len(errors),
        "error_segment_ids": [
            error.get("segment_id") for error in errors
            if isinstance(error, dict) and isinstance(error.get("segment_id"), str)
        ],
        "error_types": list(dict.fromkeys(
            error["error_type"] for error in errors
            if isinstance(error, dict) and isinstance(error.get("error_type"), str)
        )),
    }


def run_matrix(args: argparse.Namespace) -> tuple[dict[str, Any] | None, Path | None, int]:
    report = preflight.run_preflight(args.job_id, args.output_dir)
    if report.get("status") != "ready":
        print("Benchmark matrix aborted: translation preflight not ready.", file=sys.stderr)
        return None, None, 1

    paths = build_job_paths(args.output_dir, args.job_id)
    segments = benchmark.load_segments(paths.resolve_translated_segments_json_path())
    workload = benchmark.select_workload(
        segments, args.start_index, args.end_index, args.limit, args.segment_ids,
    )
    artifact = _artifact(args, workload)
    benchmark_directory = paths.metrics_dir / "concurrency_benchmarks"
    matrices_directory = benchmark_directory / "matrices"
    warmup_item = next((item for item in workload if item[1]["text"]), None)
    if warmup_item is None:
        raise benchmark.BenchmarkError("Selected workload has no non-empty speech unit.")

    warmup = benchmark.benchmark_unit(
        warmup_item, artifact["base_url"], args.speaker_id, args.timeout,
    )
    artifact["warmup"] = {
        "status": "completed" if warmup.get("status") != "failed" else "failed",
        "segment_id": warmup_item[1]["segment_id"],
    }
    if warmup.get("status") == "failed":
        artifact["status"] = "warmup_failed"
        artifact["warmup"]["error_type"] = warmup.get("error_type")
        artifact["warmup"]["error_message"] = warmup.get("error_message")
        path = save_matrix(matrices_directory, artifact)
        print("Benchmark matrix aborted: AivisSpeech warm-up failed.", file=sys.stderr)
        return artifact, path, 1

    matrix_samples: list[dict[str, Any]] = []
    for workers in CANDIDATE_ORDER:
        try:
            sample, sample_path = benchmark.run_benchmark_once(
                job_id=args.job_id, benchmark_directory=benchmark_directory,
                workload=workload, workers=workers, base_url=artifact["base_url"],
                speaker_id=args.speaker_id, timeout=args.timeout,
            )
            matrix_samples.append(sample)
            artifact["samples"].append(
                _candidate_entry(workers, sample, sample_path, paths.job_dir)
            )
        except Exception as exc:  # Record setup/programming failure and retain later candidates.
            artifact["samples"].append({
                "workers": workers, "status": "failed_to_create_sample",
                "path": None, "error_count": 1,
                "error_segment_ids": [], "error_types": [type(exc).__name__],
                "error_type": type(exc).__name__,
                "error_message": benchmark._safe_error(exc),
            })

    warnings = _check_comparability(matrix_samples, artifact)
    if len(matrix_samples) != len(CANDIDATE_ORDER):
        warnings.append("NOT COMPARABLE: one or more candidate samples were not created.")
    artifact["comparability_warnings"] = warnings
    artifact["comparability_status"] = "comparable" if not warnings else "not_comparable"
    if len(matrix_samples) != len(CANDIDATE_ORDER):
        artifact["status"] = "incomplete"
    elif any(sample.get("status") != "completed" for sample in matrix_samples):
        artifact["status"] = "completed_with_errors"
    else:
        artifact["status"] = "completed"
    matrix_path = save_matrix(matrices_directory, artifact)

    print("AivisSpeech concurrency matrix")
    print("------------------------------\n")
    print(comparison.format_summary(matrix_samples))
    print(f"\nMatrix status: {artifact['status']}")
    print("\nComparability: " + ("OK" if not warnings else "NOT COMPARABLE"))
    print(f"\nMatrix:\n{matrix_path}")
    return artifact, matrix_path, 0 if not warnings else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _, _, exit_code = run_matrix(args)
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except benchmark.BenchmarkError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
