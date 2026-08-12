"""Small, secret-safe run report used by the one-command workflow."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

_SECRET = re.compile(r"(?i)(sk-[A-Za-z0-9_-]+|(?:api[_-]?key|token|authorization|cookie)\s*[:=]\s*\S+)")
_TEMP = re.compile(r"(?:/private)?/tmp/(?:yt_video_dub_(?:translation|repair|edge)_[^\s/]+)(?:/[^\s]*)?")


def safe_text(value: object) -> str:
    text = _SECRET.sub("[REDACTED]", str(value))
    text = _TEMP.sub("[temporary workspace]", text).replace("\n", " ").strip()
    return text if len(text) <= 8000 else text[:8000] + "… [truncated]"


def _command_version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        return safe_text((result.stdout or result.stderr).splitlines()[0]) if result.returncode == 0 else "unavailable"
    except (OSError, subprocess.SubprocessError, IndexError):
        return "unavailable"


class RunReport:
    def __init__(self, output_dir: str | Path, job_id: str, url: str):
        self.output_dir, self.job_id = Path(output_dir), job_id
        self.started_clock = monotonic()
        self.data = {
            "run": {"start_timestamp": datetime.now(timezone.utc).isoformat(), "job_id": job_id,
                    "input_url": safe_text(url), **self._git()},
            "environment": {"python": sys.version.split()[0], "codex_cli": _command_version(["codex", "--version"]),
                            "edge_tts": _command_version([sys.executable, "-m", "edge_tts", "--version"]),
                            "ffmpeg": _command_version(["ffmpeg", "-version"])},
            "configuration": {}, "stages": [], "source": {}, "translation": [], "tts": [],
            "quality": {"failed_tts_evidence": [], "original_problems": [],
                        "repair_history": [], "tts_aggregate": {}, "audio_qa": {},
                        "mux": {}, "compatibility": {}},
            # Transitional in-memory keys used by the runner while a job is active.
            "failed_tts_items": [], "quality_problems": [], "repairs": [], "audio_qa": {},
            "final": {"success": False},
        }

    @staticmethod
    def _git() -> dict:
        def run(args):
            result = subprocess.run(args, capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else "unavailable"
        return {"git_commit": run(["git", "rev-parse", "--short", "HEAD"]),
                "git_dirty_state": "dirty" if run(["git", "status", "--porcelain"]) else "clean"}

    def stage(self, name: str, status: str, elapsed: float, result: object = "") -> None:
        self.data["stages"].append({"name": name, "status": status,
                                    "elapsed_seconds": round(elapsed, 3), "result": safe_text(result)})

    def finalize(self, *, success: bool, video: Path | None = None, failure: dict | None = None) -> None:
        elapsed = monotonic() - self.started_clock
        self.data["run"].update(end_timestamp=datetime.now(timezone.utc).isoformat(),
                                total_elapsed_seconds=round(elapsed, 3))
        self.data["final"] = {"success": success, "video_path": str(video) if success and video else None}
        if failure:
            self.data["failure"] = {key: safe_text(value) for key, value in failure.items()}
        job = self.output_dir / self.job_id
        job.mkdir(parents=True, exist_ok=True)
        cache = job / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        diagnostic = cache / "diagnostic.json"
        temporary = cache / ".diagnostic.json.tmp"
        try:
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
            os.replace(temporary, diagnostic)
        finally:
            temporary.unlink(missing_ok=True)

    def _render(self) -> str:
        lines = []
        for section in ("run", "environment"):
            lines.append(section.upper())
            lines += [f"{key}: {safe_text(value)}" for key, value in self.data[section].items()]
            lines.append("")
        lines.append("STAGES")
        lines += [f"{x['name']}: {x['status']} ({x['elapsed_seconds']}s) {x['result']}" for x in self.data["stages"]]
        for key, title in (("translation", "TRANSLATION"), ("tts", "TTS"),
                           ("failed_tts_items", "FAILED TTS ITEMS"),
                           ("quality_problems", "QUALITY PROBLEMS"), ("repairs", "REPAIR"),
                           ("audio_qa", "AUDIO QA"), ("final", "FINAL"), ("failure", "FAILURE")):
            if key not in self.data or not self.data[key]:
                continue
            lines += ["", title]
            value = self.data[key]
            if isinstance(value, list):
                lines += [safe_text(json.dumps(x, ensure_ascii=False)) for x in value]
            else:
                lines += [f"{k}: {safe_text(v)}" for k, v in value.items()]
        return "\n".join(lines) + "\n"
