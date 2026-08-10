#!/usr/bin/env python3
"""Benchmark fresh AivisSpeech synthesis with isolated, bounded concurrency."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import re
import sys
import time
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from path_layout import build_job_paths


DEFAULT_BASE_URL = "http://127.0.0.1:10101"
DEFAULT_SPEAKER_ID = 1937616896
DEFAULT_TIMEOUT = 30.0
MAX_SPEED_SCALE = 1.15
ALLOWED_WORKERS = (1, 2, 4)
BENCHMARK_SCHEMA_VERSION = 1


class BenchmarkError(RuntimeError):
    """Raised for invalid benchmark input or setup."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--speaker-id", type=int, default=DEFAULT_SPEAKER_ID)
    parser.add_argument("--workers", type=int, choices=ALLOWED_WORKERS, required=True)
    parser.add_argument("--segment-id", action="append", dest="segment_ids")
    parser.add_argument("--start-index", type=int)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser


def load_segments(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BenchmarkError(f"Missing translated segments file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkError(f"Invalid translated segments JSON: {path}") from exc
    segments = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(segments, list):
        raise BenchmarkError("translated_segments.json must contain a segments list.")
    validated = []
    for index, item in enumerate(segments, 1):
        if not isinstance(item, dict):
            raise BenchmarkError(f"Segment {index} must be an object.")
        if not isinstance(item.get("segment_id"), str) or not item["segment_id"]:
            raise BenchmarkError(f"Segment {index} has an invalid segment_id.")
        if not isinstance(item.get("text"), str):
            raise BenchmarkError(f"Segment {index} has invalid text.")
        if not isinstance(item.get("start"), (int, float)) or not isinstance(
            item.get("end"), (int, float)
        ):
            raise BenchmarkError(f"Segment {index} has invalid timing.")
        validated.append({
            "segment_id": item["segment_id"], "text": item["text"],
            "start": float(item["start"]), "end": float(item["end"]),
        })
    return validated


def select_workload(
    segments: list[dict[str, Any]], start_index: int | None = None,
    end_index: int | None = None, limit: int | None = None,
    segment_ids: list[str] | None = None,
) -> list[tuple[int, dict[str, Any]]]:
    if start_index is not None and start_index <= 0:
        raise BenchmarkError("--start-index must be positive.")
    if end_index is not None and end_index <= 0:
        raise BenchmarkError("--end-index must be positive.")
    if start_index and end_index and start_index > end_index:
        raise BenchmarkError("--start-index must not exceed --end-index.")
    if limit is not None and limit <= 0:
        raise BenchmarkError("--limit must be positive.")
    indexed = list(enumerate(segments, 1))
    start, end = start_index or 1, end_index or len(indexed)
    indexed = [item for item in indexed if start <= item[0] <= end]
    if segment_ids:
        known = {segment["segment_id"] for segment in segments}
        unknown = sorted(set(segment_ids) - known)
        if unknown:
            raise BenchmarkError("Unknown --segment-id value(s): " + ", ".join(unknown))
        wanted = set(segment_ids)
        indexed = [item for item in indexed if item[1]["segment_id"] in wanted]
    if limit is not None:
        indexed = indexed[:limit]
    if not indexed:
        raise BenchmarkError("No segments matched the requested workload.")
    return indexed


def workload_hash(workload: list[tuple[int, dict[str, Any]]], speaker_id: int) -> str:
    canonical = [{
        "index": index, "segment_id": segment["segment_id"],
        "text": segment["text"], "start": segment["start"],
        "end": segment["end"], "speaker_id": speaker_id,
    } for index, segment in workload]
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def measure_wav_duration(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            rate = reader.getframerate()
            if rate <= 0:
                raise BenchmarkError("Synthesized WAV has an invalid sample rate.")
            return reader.getnframes() / float(rate)
    except (wave.Error, EOFError) as exc:
        raise BenchmarkError("AivisSpeech returned invalid WAV data.") from exc


def classify_duration(raw: float, available: float) -> tuple[str, float, bool]:
    if available <= 0:
        return "ng", math.inf, False
    required = raw / available
    if required <= 1.0:
        return "ok", required, False
    if required <= MAX_SPEED_SCALE:
        return "retry", required, True
    return "ng", required, False


def _post(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    response = session.post(url, **kwargs)
    if not response.ok:
        raise BenchmarkError(f"AivisSpeech request failed with HTTP {response.status_code}.")
    return response


def benchmark_unit(
    item: tuple[int, dict[str, Any]], base_url: str, speaker_id: int, timeout: float,
) -> dict[str, Any]:
    index, segment = item
    result: dict[str, Any] = {
        "index": index, "segment_id": segment["segment_id"], "status": "completed",
        "fit_status": None, "audio_query_wall_seconds": 0.0,
        "synthesis_wall_seconds": 0.0, "normal_synthesis_count": 0,
        "speed_fit_synthesis_count": 0, "error_type": None, "error_message": None,
    }
    if not segment["text"]:
        result.update(status="skipped_empty", fit_status=None)
        return result
    try:
        with requests.Session() as session:  # A session is owned by exactly one task/thread.
            started = time.perf_counter()
            try:
                query_response = _post(
                    session, f"{base_url}/audio_query",
                    params={"text": segment["text"], "speaker": speaker_id}, timeout=timeout,
                )
            finally:
                result["audio_query_wall_seconds"] += time.perf_counter() - started
            query = query_response.json()
            if not isinstance(query, dict):
                raise BenchmarkError("audio_query did not return a JSON object.")
            query["speedScale"] = 1.0
            started = time.perf_counter()
            try:
                wav_data = _post(
                    session, f"{base_url}/synthesis", params={"speaker": speaker_id},
                    json=query, timeout=timeout,
                ).content
            finally:
                result["synthesis_wall_seconds"] += time.perf_counter() - started
            result["normal_synthesis_count"] = 1
            raw = measure_wav_duration(wav_data)
            available = max(0.0, segment["end"] - segment["start"])
            classification, speed, retry = classify_duration(raw, available)
            final = raw
            if retry:
                query["speedScale"] = speed
                started = time.perf_counter()
                try:
                    fitted_data = _post(
                        session, f"{base_url}/synthesis", params={"speaker": speaker_id},
                        json=query, timeout=timeout,
                    ).content
                finally:
                    result["synthesis_wall_seconds"] += time.perf_counter() - started
                result["speed_fit_synthesis_count"] = 1
                final = measure_wav_duration(fitted_data)
                classification = "fitted" if final <= available else "ng"
            result.update(
                fit_status=classification, available_duration=round(available, 6),
                raw_tts_duration=round(raw, 6), final_tts_duration=round(final, 6),
                speed_scale=round(speed if retry else 1.0, 6),
            )
    except Exception as exc:
        result.update(
            status="failed", error_type=type(exc).__name__, error_message=_safe_error(exc)
        )
    return result


def _safe_error(exc: BaseException) -> str:
    message = str(exc).replace("\n", " ")[:400]
    message = re.sub(r"sk-[A-Za-z0-9_-]+", "<redacted>", message)
    message = re.sub(r"(?i)(api[_ -]?key|bearer)\s*[:= ]\s*\S+", r"\1=<redacted>", message)
    return message


def run_workload(
    workload: list[tuple[int, dict[str, Any]]], workers: int,
    worker: Callable[[tuple[int, dict[str, Any]]], dict[str, Any]],
    executor_class: type[ThreadPoolExecutor] = ThreadPoolExecutor,
) -> list[dict[str, Any]]:
    if workers not in ALLOWED_WORKERS:
        raise BenchmarkError(f"workers must be one of {ALLOWED_WORKERS}.")
    results = []
    with executor_class(max_workers=workers) as executor:
        futures = {executor.submit(worker, item): item for item in workload}
        for future in as_completed(futures):
            index, segment = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # Retain the other unit results by design.
                results.append({
                    "index": index, "segment_id": segment["segment_id"],
                    "status": "failed", "fit_status": None,
                    "audio_query_wall_seconds": 0.0, "synthesis_wall_seconds": 0.0,
                    "normal_synthesis_count": 0, "speed_fit_synthesis_count": 0,
                    "error_type": type(exc).__name__, "error_message": _safe_error(exc),
                })
    return sorted(results, key=lambda result: (result["index"], result["segment_id"]))


def build_sample(
    job_id: str, workers: int, base_url: str, speaker_id: int,
    workload: list[tuple[int, dict[str, Any]]], results: list[dict[str, Any]],
    elapsed: float, timeout_seconds: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    errors = [{
        "index": item["index"], "segment_id": item["segment_id"],
        "error_type": item["error_type"], "error_message": item["error_message"],
    } for item in results if item["status"] == "failed"]
    skipped_empty_units = sum(item["status"] == "skipped_empty" for item in results)
    speech_units = len(workload) - skipped_empty_units
    successful_speech_units = sum(
        item["status"] not in ("failed", "skipped_empty") for item in results
    )
    status = (
        "failed" if errors and speech_units > 0 and successful_speech_units == 0
        else ("completed_with_errors" if errors else "completed")
    )
    return {
        "job_id": job_id, "run_id": "", "generated_at": datetime.now(timezone.utc).isoformat(),
        "workers": workers, "cache_mode": "forced_fresh",
        "workload_hash": workload_hash(workload, speaker_id),
        "selected_units": len(workload),
        "speech_units": speech_units,
        "skipped_empty_units": skipped_empty_units,
        "successful_speech_units": successful_speech_units,
        "segment_ids": [segment["segment_id"] for _, segment in workload],
        "speaker_id": speaker_id, "base_url": base_url, "status": status,
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "max_speed_scale": MAX_SPEED_SCALE,
        "timeout_seconds": timeout_seconds,
        "tts_wall_seconds": round(elapsed, 6),
        "audio_query_wall_seconds": round(sum(x["audio_query_wall_seconds"] for x in results), 6),
        "synthesis_wall_seconds": round(sum(x["synthesis_wall_seconds"] for x in results), 6),
        "normal_synthesis_count": sum(x["normal_synthesis_count"] for x in results),
        "speed_fit_synthesis_count": sum(x["speed_fit_synthesis_count"] for x in results),
        "fit_ok_count": sum(x["fit_status"] == "ok" for x in results),
        "fit_fitted_count": sum(x["fit_status"] == "fitted" for x in results),
        "fit_ng_count": sum(x["fit_status"] == "ng" for x in results),
        "units_per_second": round(successful_speech_units / elapsed, 6) if elapsed > 0 else 0.0,
        "errors": errors, "results": results,
        "hardware": {"system": platform.system(), "machine": platform.machine(),
                     "python_version": platform.python_version()},
    }


def save_sample(directory: Path, sample: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    while True:
        run_id = f"{timestamp}-w{sample['workers']}-{uuid.uuid4().hex[:8]}"
        path = directory / f"{run_id}.json"
        try:
            with path.open("x", encoding="utf-8") as stream:
                sample["run_id"] = run_id
                json.dump(sample, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            return path
        except FileExistsError:
            continue


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = build_job_paths(args.output_dir, args.job_id)
    segments = load_segments(paths.resolve_translated_segments_json_path())
    workload = select_workload(segments, args.start_index, args.end_index,
                               args.limit, args.segment_ids)
    base_url = args.base_url.rstrip("/")
    started = time.perf_counter()
    results = run_workload(
        workload, args.workers,
        lambda item: benchmark_unit(item, base_url, args.speaker_id, args.timeout),
    )
    elapsed = time.perf_counter() - started
    sample = build_sample(args.job_id, args.workers, base_url, args.speaker_id,
                          workload, results, elapsed, args.timeout)
    path = save_sample(paths.metrics_dir / "concurrency_benchmarks", sample)
    print(path)
    return 0 if sample["status"] == "completed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BenchmarkError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
