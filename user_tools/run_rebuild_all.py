#!/usr/bin/env python3
"""Clickable wrapper for rebuilding all local TTS and dub-audio outputs."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_pipeline_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "91_run_local_tts_pipeline.py"
    module_name = "run_local_tts_pipeline_rebuild_all"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    pipeline = _load_pipeline_module()
    return pipeline.main(["--force-tts", "--mux-video"])


if __name__ == "__main__":
    raise SystemExit(main())
