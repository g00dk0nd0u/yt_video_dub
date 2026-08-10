#!/usr/bin/env python3
"""Small, reusable helpers for Fast Path wall-clock metrics."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class StageTimer:
    """Record completed/skipped stages using a monotonic clock."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self.stages: dict[str, dict[str, Any]] = {}

    def run(self, name: str, operation: Callable[[], Any]) -> Any:
        started = self._clock()
        result = operation()
        self.stages[name] = {
            "status": "completed",
            "seconds": round(self._clock() - started, 6),
        }
        return result

    def skip(self, name: str) -> None:
        self.stages[name] = {"status": "skipped", "seconds": 0.0}


def calculate_rtf(total_seconds: float, video_duration_seconds: float | None) -> float | None:
    if video_duration_seconds is None or video_duration_seconds <= 0:
        return None
    return round(total_seconds / video_duration_seconds, 6)


def build_benchmark(
    *, job_id: str, run_mode: str, total_pipeline_seconds: float,
    stages: dict[str, dict[str, Any]], tts: dict[str, Any],
    video_duration_seconds: float | None,
) -> dict[str, Any]:
    total = round(total_pipeline_seconds, 6)
    return {
        "job_id": job_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_mode": run_mode,
        "total_pipeline_seconds": total,
        "video_duration_seconds": video_duration_seconds,
        "rtf": calculate_rtf(total, video_duration_seconds),
        "stages": stages,
        "tts": tts,
    }


def write_benchmark(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_summary(payload: dict[str, Any]) -> str:
    stages = payload["stages"]
    tts = payload.get("tts", {})
    stage_lines = []
    for key, label in (("translated_build", "translated"),
                       ("translation_preflight", "preflight"), ("tts", "TTS"),
                       ("dub_audio_build", "audio"), ("mux", "mux")):
        stage = stages.get(key, {"status": "skipped", "seconds": 0.0})
        value = "skipped" if stage["status"] == "skipped" else f'{stage["seconds"]:.1f} s'
        stage_lines.append(f"{label:<11}: {value}")
    duration = payload.get("video_duration_seconds")
    rtf = payload.get("rtf")
    return "\n".join([
        "Fast Path benchmark", "-------------------", *stage_lines,
        f'total      : {payload["total_pipeline_seconds"]:.1f} s',
        "TTS:",
        f'generated  : {tts.get("generated_units", 0)}',
        f'reused     : {tts.get("reused_units", 0)}',
        f'speed-fit  : {tts.get("speed_fit_synthesis_count", 0)}',
        "OK/FIT/NG  : " + " / ".join(str(tts.get(key, 0)) for key in
                                      ("fit_ok_count", "fit_fitted_count", "fit_ng_count")),
        f'video      : {duration:.1f} s' if duration is not None else "video      : n/a",
        f'RTF        : {rtf:.3f}' if rtf is not None else "RTF        : n/a",
    ])
