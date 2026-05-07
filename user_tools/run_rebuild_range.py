#!/usr/bin/env python3
"""Clickable wrapper for rebuilding a selectable local TTS range."""

from __future__ import annotations

import importlib.util
from pathlib import Path


JOB_ID = "phase1_smoke_rick"
FORCE_TTS = True
RESUME = False
SKIP_BUILD_TRANSLATED = False
MUX_VIDEO = True


def _load_pipeline_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "91_run_local_tts_pipeline.py"
    module_name = "run_local_tts_pipeline_rebuild_range"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_optional_positive_int(value: str, field_name: str) -> int | None:
    trimmed = value.strip()
    if trimmed == "":
        return None
    if not trimmed.isdigit():
        raise ValueError(f"{field_name} must be a positive integer.")

    parsed = int(trimmed)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


def _prompt_range() -> tuple[int, int | None]:
    start_value = input("Start index [1]: ")
    end_value = input("End index [all]: ")

    start_index = _parse_optional_positive_int(start_value, "Start index")
    end_index = _parse_optional_positive_int(end_value, "End index")

    if start_index is None:
        start_index = 1
    if end_index is not None and start_index > end_index:
        raise ValueError("Start index must be less than or equal to end index.")

    return start_index, end_index


def main() -> int:
    pipeline = _load_pipeline_module()
    start_index, end_index = _prompt_range()
    args = ["--job-id", JOB_ID]

    args.extend(["--start-index", str(start_index)])
    if end_index is not None:
        args.extend(["--end-index", str(end_index)])
    if FORCE_TTS:
        args.append("--force-tts")
    if RESUME:
        args.append("--resume")
    if SKIP_BUILD_TRANSLATED:
        args.append("--skip-build-translated")
    if MUX_VIDEO:
        args.append("--mux-video")

    return pipeline.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
