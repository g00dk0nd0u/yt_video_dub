#!/usr/bin/env python3
"""Clickable wrapper for resuming the local TTS and dub-audio pipeline."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_pipeline_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "91_run_local_tts_pipeline.py"
    module_name = "run_local_tts_pipeline_resume"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    pipeline = _load_pipeline_module()
    return pipeline.main(["--resume", "--mux-video"])


if __name__ == "__main__":
    raise SystemExit(main())
