#!/usr/bin/env python3
"""Clickable wrapper for rebuilding a selectable local TTS range."""

from __future__ import annotations

import importlib.util
from pathlib import Path


JOB_ID = "phase1_smoke_rick"
START_INDEX = 7
END_INDEX = 8
FORCE_TTS = True
RESUME = False
SKIP_BUILD_TRANSLATED = False


def _load_pipeline_module():
    script_path = Path(__file__).with_name("91_run_local_tts_pipeline.py")
    module_name = "run_local_tts_pipeline_rebuild_range"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    pipeline = _load_pipeline_module()
    args = ["--job-id", JOB_ID]

    if START_INDEX is not None:
        args.extend(["--start-index", str(START_INDEX)])
    if END_INDEX is not None:
        args.extend(["--end-index", str(END_INDEX)])
    if FORCE_TTS:
        args.append("--force-tts")
    if RESUME:
        args.append("--resume")
    if SKIP_BUILD_TRANSLATED:
        args.append("--skip-build-translated")

    return pipeline.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
