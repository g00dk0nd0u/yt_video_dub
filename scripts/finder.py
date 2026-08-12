"""Small platform-specific helpers for revealing completed job output."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_job_folder_in_finder(path: Path) -> None:
    """Open a completed job folder in macOS Finder, warning without failing."""
    if sys.platform != "darwin":
        return
    job_dir = path.resolve()
    try:
        subprocess.run(
            ["open", str(job_dir)], check=True, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Warning: could not open output folder in Finder: {exc}", file=sys.stderr)
