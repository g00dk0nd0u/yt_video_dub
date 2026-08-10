#!/usr/bin/env python3
"""Run the local dubbing workflow with repo-friendly defaults."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_JOB_ID = "phase1_smoke_rick"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_BASE_URL = "http://127.0.0.1:10101"
DEFAULT_SPEAKER_ID = 1937616896
SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from path_layout import build_job_paths
from performance_metrics import StageTimer, build_benchmark, format_summary, write_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run translated text rebuild, audio generation, dub-audio build, and optional video creation."
    )
    parser.add_argument(
        "--job-id",
        default=DEFAULT_JOB_ID,
        help=f"Job identifier under output/<job_id>/. Default: {DEFAULT_JOB_ID}",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL for the local AivisSpeech API. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--speaker-id",
        default=DEFAULT_SPEAKER_ID,
        type=int,
        help=f"Speaker ID to use for speech generation. Default: {DEFAULT_SPEAKER_ID}",
    )
    parser.add_argument(
        "--mux-video",
        action="store_true",
        help="Run the fixed-timeline scripts/08_mux_video.py Fast Path.",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default="ffmpeg",
        help='ffmpeg binary name or path for synced video build. Default: "ffmpeg"',
    )
    parser.add_argument(
        "--ffprobe-bin",
        default="ffprobe",
        help='ffprobe binary name or path for synced video build. Default: "ffprobe"',
    )
    parser.add_argument(
        "--force-tts",
        action="store_true",
        help="Pass --force to scripts/06_generate_tts_segments.py.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Pass --resume to scripts/06_generate_tts_segments.py.",
    )
    parser.add_argument(
        "--skip-tts",
        action="store_true",
        help="Skip scripts/06_generate_tts_segments.py and use existing TTS artifacts in later stages.",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        help="1-based translated segment index to start audio generation from.",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        help="1-based translated segment index to end audio generation at.",
    )
    parser.add_argument(
        "--segment-id",
        action="append",
        dest="segment_ids",
        help="Regenerate only this segment ID. Repeatable and passed to script 06.",
    )
    parser.add_argument(
        "--skip-build-translated",
        action="store_true",
        help="Skip scripts/04_build_translated_segments.py.",
    )
    return parser


def _load_script_module(filename: str) -> Any:
    script_path = SCRIPT_DIR / filename
    module_name = f"local_tts_pipeline_{filename.replace('.', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_step(label: str, module_filename: str, step_args: list[str]) -> None:
    module = _load_script_module(module_filename)
    print(f"== {label} ==")
    module.main(step_args)
    print("")


def _probe_video_duration(path: Path, ffprobe_bin: str) -> float | None:
    if not path.exists():
        return None
    try:
        result = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        duration = float(json.loads(result.stdout)["format"]["duration"])
        return round(duration, 6) if duration > 0 else None
    except (FileNotFoundError, subprocess.CalledProcessError, KeyError, TypeError,
            ValueError, json.JSONDecodeError):
        return None


def _load_tts_run_metrics(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    metrics = payload.get("run_metrics")
    return metrics if isinstance(metrics, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.skip_tts and any((args.resume, args.force_tts, args.start_index is not None,
                              args.end_index is not None, args.segment_ids)):
        parser.error("--skip-tts cannot be combined with TTS generation options.")
    pipeline_started = time.perf_counter()
    timer = StageTimer()
    paths = build_job_paths(args.output_dir, args.job_id)

    common_job_args = [
        "--job-id",
        args.job_id,
        "--output-dir",
        args.output_dir,
    ]

    if not args.skip_build_translated:
        timer.run(
            "translated_build",
            lambda: _run_step("Step 1: build translated text data",
                              "04_build_translated_segments.py", common_job_args),
        )
    else:
        timer.skip("translated_build")

    tts_args = [
        "--job-id",
        args.job_id,
        "--output-dir",
        args.output_dir,
        "--base-url",
        args.base_url,
        "--speaker-id",
        str(args.speaker_id),
    ]
    if args.resume:
        tts_args.append("--resume")
    if args.force_tts:
        tts_args.append("--force")
    if args.start_index is not None:
        tts_args.extend(["--start-index", str(args.start_index)])
    if args.end_index is not None:
        tts_args.extend(["--end-index", str(args.end_index)])
    for segment_id in args.segment_ids or []:
        tts_args.extend(["--segment-id", segment_id])

    if args.skip_tts:
        timer.skip("tts")
    else:
        timer.run(
            "tts",
            lambda: _run_step("Step 2: generate Japanese audio segments",
                              "06_generate_tts_segments.py", tts_args),
        )
    timer.run(
        "dub_audio_build",
        lambda: _run_step("Step 3: combine Japanese audio",
                          "07_build_dub_audio.py", common_job_args),
    )
    if args.mux_video:
        timer.run(
            "mux",
            lambda: _run_step(
                "Step 4: create fixed-timeline dubbed video", "08_mux_video.py",
                common_job_args + ["--ffmpeg-bin", args.ffmpeg_bin],
            ),
        )
    else:
        timer.skip("mux")

    video_duration = _probe_video_duration(paths.resolve_source_video_path(), args.ffprobe_bin)
    run_mode = "selective_retry" if args.segment_ids else ("resume" if args.resume else "full")
    tts_metrics = ({
        "status": "skipped",
        "selected_units": 0,
        "generated_units": 0,
        "reused_units": 0,
        "skipped_empty_units": 0,
        "normal_synthesis_count": 0,
        "speed_fit_synthesis_count": 0,
        "fit_ok_count": 0,
        "fit_fitted_count": 0,
        "fit_ng_count": 0,
    } if args.skip_tts else _load_tts_run_metrics(paths.tts_manifest_path))
    benchmark = build_benchmark(
        job_id=args.job_id,
        run_mode=run_mode,
        total_pipeline_seconds=time.perf_counter() - pipeline_started,
        stages=timer.stages,
        tts=tts_metrics,
        video_duration_seconds=video_duration,
    )
    write_benchmark(paths.benchmark_path, benchmark)
    print(format_summary(benchmark))
    print(f"Benchmark: {paths.benchmark_path}")
    print("Video build completed.")
    print(f"Lightweight files under output/{args.job_id}/ (*.json, *.txt, *.srt) can be committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
