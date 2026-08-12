#!/usr/bin/env python3
"""Build and validate a resumable QuickTime-compatible H.264 source cache."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import threading
import uuid
from fractions import Fraction
from pathlib import Path
from time import monotonic

from path_layout import build_job_paths

CACHE_SCHEMA_VERSION = 1
ENCODER = "libx264"
PRESET = "medium"
CRF = "20"
OUTPUT_PIXEL_FORMAT = "yuv420p"
CANCEL_TIMEOUT_SECONDS = 2
_IDENTITY_STREAM_FIELDS = (
    "codec_name", "width", "height", "avg_frame_rate", "duration", "pix_fmt",
    "color_space", "color_transfer", "color_primaries", "color_range",
    "sample_aspect_ratio",
)
_REQUIRED_IDENTITY_FIELDS = ("codec_name", "width", "height", "avg_frame_rate", "duration", "pix_fmt")


class VideoCompatibilityError(RuntimeError):
    """Raised for a compatibility-cache operation that may safely fall back."""


def _probe(ffprobe_bin: str, path: Path) -> dict:
    command = [ffprobe_bin, "-v", "error", "-show_entries",
               "stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration,pix_fmt,color_space,color_transfer,color_primaries,color_range,sample_aspect_ratio:format=duration",
               "-of", "json", str(path)]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise VideoCompatibilityError(f"ffprobe failed for {path}: {exc}") from exc
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not isinstance(video, dict):
        raise VideoCompatibilityError(f"No video stream found in {path}")
    video = {field: video.get(field) for field in _IDENTITY_STREAM_FIELDS}
    video["duration"] = video.get("duration") or payload.get("format", {}).get("duration")
    video["audio_stream_present"] = any(item.get("codec_type") == "audio" for item in streams)
    return video


def _ffmpeg_version(ffmpeg_bin: str) -> str:
    try:
        result = subprocess.run([ffmpeg_bin, "-version"], check=True, capture_output=True, text=True)
        return result.stdout.splitlines()[0]
    except (OSError, subprocess.CalledProcessError, IndexError) as exc:
        raise VideoCompatibilityError(f"Unable to determine ffmpeg version: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(source: Path, probe: dict, ffmpeg_version: str) -> dict:
    if any(probe.get(field) in (None, "", "0/0") for field in _REQUIRED_IDENTITY_FIELDS):
        raise VideoCompatibilityError("Source metadata is incomplete; compatibility cache is unsafe")
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "source_sha256": _sha256(source), "source_file_size": source.stat().st_size,
        "source": {field: probe.get(field) for field in _IDENTITY_STREAM_FIELDS},
        "encoder": ENCODER, "preset": PRESET, "crf": CRF,
        "output_pixel_format": OUTPUT_PIXEL_FORMAT, "ffmpeg_version": ffmpeg_version,
    }


def _rate(value: object) -> Fraction:
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return Fraction(0)


def _validate(source_probe: dict, output_probe: dict, path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise VideoCompatibilityError("Compatibility output is empty")
    if output_probe.get("codec_name") != "h264":
        raise VideoCompatibilityError("Compatibility output codec is not h264")
    if output_probe.get("pix_fmt") != OUTPUT_PIXEL_FORMAT:
        raise VideoCompatibilityError("Compatibility output pixel format is not yuv420p")
    for field in ("width", "height", "sample_aspect_ratio", "color_space", "color_transfer",
                  "color_primaries", "color_range"):
        if source_probe.get(field) != output_probe.get(field):
            raise VideoCompatibilityError(f"Compatibility output changed {field}")
    if _rate(source_probe.get("avg_frame_rate")) != _rate(output_probe.get("avg_frame_rate")):
        raise VideoCompatibilityError("Compatibility output changed frame rate")
    try:
        source_duration, output_duration = float(source_probe["duration"]), float(output_probe["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VideoCompatibilityError("Compatibility duration metadata is invalid") from exc
    fps = float(_rate(source_probe.get("avg_frame_rate")))
    tolerance = max(0.1, 2.0 / fps) if fps > 0 else 0.1
    if abs(source_duration - output_duration) > tolerance:
        raise VideoCompatibilityError("Compatibility output changed duration")
    if not output_probe.get("audio_stream_present"):
        raise VideoCompatibilityError("Compatibility output has no original audio stream")


class CompatibilityTask:
    """Own an asynchronous ffmpeg process and its cache publication lifecycle."""

    def __init__(self, *, process=None, stderr_file=None, part_path=None, source_path=None,
                 cache_path=None, manifest_path=None, source_probe=None, identity=None,
                 ffprobe_bin="ffprobe", started=False, reused=False, failure=None):
        self.process, self.stderr_file, self.part_path = process, stderr_file, part_path
        self.source_path, self.cache_path, self.manifest_path = source_path, cache_path, manifest_path
        self.source_probe, self.identity, self.ffprobe_bin = source_probe, identity, ffprobe_bin
        self.started, self.reused, self.failure = started, reused, failure
        self.started_at = monotonic() if started else None
        self.completed_at = None
        self._completed = threading.Event()
        if process is not None:
            threading.Thread(target=self._observe, name="compatibility-ffmpeg-waiter",
                             daemon=True).start()

    def _observe(self) -> None:
        self.process.wait()
        self.completed_at = monotonic()
        self._completed.set()

    def poll(self):
        return self.process.poll() if self.process else 0

    def wait(self) -> dict:
        wait_started = monotonic()
        if self.process is not None:
            self._completed.wait()
            returncode = self.process.returncode
            transcode_seconds = self.completed_at - self.started_at
            self.stderr_file.seek(0)
            stderr = self.stderr_file.read().decode("utf-8", errors="replace")[-4000:]
            self.stderr_file.close()
            self.stderr_file = None
            if returncode:
                self.failure = f"background ffmpeg exited {returncode}: {stderr.strip()}"
            elif not self.failure:
                try:
                    output_probe = _probe(self.ffprobe_bin, self.part_path)
                    _validate(self.source_probe, output_probe, self.part_path)
                    self.part_path.replace(self.cache_path)
                    self.manifest_path.write_text(json.dumps({
                        "identity": self.identity, "output_probe": output_probe,
                    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                except (OSError, VideoCompatibilityError) as exc:
                    self.failure = str(exc)
            if self.failure and self.part_path:
                self.part_path.unlink(missing_ok=True)
            self.process = None
        else:
            transcode_seconds = 0.0
        return {
            "source_video_codec": self.source_probe.get("codec_name") if self.source_probe else None,
            "compatibility_task_started": self.started,
            "compatibility_cache_reused": self.reused,
            "compatibility_background_used": self.started and not self.failure,
            "compatibility_encoder": ENCODER if (self.started or self.reused) else None,
            "compatibility_transcode_seconds": round(transcode_seconds, 3),
            "compatibility_wait_seconds": round(monotonic() - wait_started, 3),
            "compatibility_failure": self.failure,
            "compatibility_video_path": self.cache_path if (self.reused or (self.started and not self.failure)) else None,
        }

    finish = wait

    def cancel(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                if not self._completed.wait(timeout=CANCEL_TIMEOUT_SECONDS):
                    raise subprocess.TimeoutExpired("ffmpeg", CANCEL_TIMEOUT_SECONDS)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if self.process.poll() is None:
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self._completed.wait()
        if self.stderr_file is not None:
            self.stderr_file.close()
            self.stderr_file = None
        if self.part_path is not None:
            self.part_path.unlink(missing_ok=True)
        self.process = None


def start_job(job_id: str, output_dir: str = "output", *, ffmpeg_bin="ffmpeg",
              ffprobe_bin="ffprobe") -> CompatibilityTask:
    paths = build_job_paths(output_dir, job_id)
    source = paths.resolve_source_video_path()
    part = paths.source_dir / f".compat_h264.{uuid.uuid4().hex}.part.mp4"
    try:
        source_probe = _probe(ffprobe_bin, source)
        if source_probe["codec_name"] == "h264":
            return CompatibilityTask(source_path=source, source_probe=source_probe)
        identity = _identity(source, source_probe, _ffmpeg_version(ffmpeg_bin))
        if paths.compatibility_video_path.is_file() and paths.compatibility_manifest_path.is_file():
            try:
                manifest = json.loads(paths.compatibility_manifest_path.read_text(encoding="utf-8"))
                output_probe = _probe(ffprobe_bin, paths.compatibility_video_path)
                cache_metadata_complete = all(
                    source_probe.get(field) not in (None, "", "unknown")
                    for field in _IDENTITY_STREAM_FIELDS
                )
                if manifest.get("identity") == identity and cache_metadata_complete:
                    _validate(source_probe, output_probe, paths.compatibility_video_path)
                    return CompatibilityTask(source_path=source, cache_path=paths.compatibility_video_path,
                        manifest_path=paths.compatibility_manifest_path, source_probe=source_probe,
                        identity=identity, reused=True)
            except (OSError, json.JSONDecodeError, VideoCompatibilityError):
                pass
        stderr_file = tempfile.TemporaryFile()
        command = [ffmpeg_bin, "-nostdin", "-y", "-i", str(source), "-map", "0:v:0",
                   "-map", "0:a:0?", "-c:v", ENCODER, "-preset", PRESET, "-crf", CRF,
                   "-pix_fmt", OUTPUT_PIXEL_FORMAT, "-c:a", "copy", "-movflags", "+faststart",
                   str(part)]
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=stderr_file, start_new_session=True)
        except OSError:
            stderr_file.close()
            raise
        return CompatibilityTask(process=process, stderr_file=stderr_file, part_path=part,
            source_path=source, cache_path=paths.compatibility_video_path,
            manifest_path=paths.compatibility_manifest_path, source_probe=source_probe,
            identity=identity, ffprobe_bin=ffprobe_bin, started=True)
    except (OSError, VideoCompatibilityError) as exc:
        part.unlink(missing_ok=True)
        return CompatibilityTask(source_path=source, source_probe=locals().get("source_probe"),
                                 failure=str(exc))
