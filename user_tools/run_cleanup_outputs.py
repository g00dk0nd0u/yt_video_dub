#!/usr/bin/env python3
"""Clickable wrapper for interactive local output cleanup."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_cleanup_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "92_clean_local_outputs.py"
    module_name = "clean_local_outputs_runner"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    cleanup = _load_cleanup_module()
    return cleanup.main()


if __name__ == "__main__":
    raise SystemExit(main())
