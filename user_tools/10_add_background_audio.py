#!/usr/bin/env python3
"""Optionally add separated source background audio to a completed dubbed video."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BACKGROUND_DB = -6.0
DEFAULT_MODEL = "htdemucs"
BACKEND = "demucs-two-stems-vocals"


class BackgroundAudioError(RuntimeError):
    """A concise error suitable for this optional command's CLI."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Add separated background audio to an existing dub.")
    parser.add_argument("--job-id", help="Job identifier under output/<job_id>/.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "output"))
    parser.add_argument("--background-db", type=float, default=DEFAULT_BACKGROUND_DB)
    parser.add_argument("--demucs-bin", help="External Demucs executable.")
    parser.add_argument("--demucs-python", help="Optional separate Python used as: PYTHON -m demucs.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--ffprobe-bin", default="ffprobe")
    parser.add_argument("--quiet", action="store_true")
    return parser


def list_background_audio_jobs(output_dir: Path) -> list[str]:
    """Return job IDs containing every input required by this post-process."""
    if not output_dir.is_dir():
        return []
    return sorted(
        job_dir.name
        for job_dir in output_dir.iterdir()
        if job_dir.is_dir() and (job_dir / "dubbed_video.mp4").is_file()
        and ((job_dir / ".cache/source_audio.mka").is_file()
             or ((job_dir / "01_source/source.mp4").is_file()
                 and (job_dir / "07_audio/dub_audio.wav").is_file()))
    )


def select_job_id(output_dir: Path) -> str | None:
    jobs = list_background_audio_jobs(output_dir)
    if not jobs:
        print("背景音を追加できる動画がありません。")
        return None

    print("背景音を追加する動画を選んでください\n")
    for number, job_id in enumerate(jobs, start=1):
        print(f"{number}. {job_id}")
    exit_number = len(jobs) + 1
    print(f"{exit_number}. 終了\n")

    while True:
        choice = input(f"番号を選んでください [1-{exit_number}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= exit_number:
            selected = int(choice)
            return None if selected == exit_number else jobs[selected - 1]
        print("正しい番号を入力してください。")


def _require_file(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise BackgroundAudioError(f"Missing {label}: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, quiet: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=quiet, text=True)
    except FileNotFoundError as exc:
        raise BackgroundAudioError(f"Command is not installed: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-1200:]
        raise BackgroundAudioError(
            f"Command failed ({exc.returncode}): {shlex.join(command[:4])}"
            + (f"\n{detail}" if detail else "")
        ) from exc


def _probe_duration(ffprobe_bin: str, path: Path) -> float:
    result = _run([
        ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        duration = float(result.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise BackgroundAudioError(f"Could not determine duration: {path}") from exc
    if duration <= 0:
        raise BackgroundAudioError(f"Invalid duration for: {path}")
    return duration


def _probe_audio_format(ffprobe_bin: str, path: Path) -> dict[str, object]:
    result = _run([
        ffprobe_bin, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "json", str(path),
    ])
    try:
        stream = json.loads(result.stdout)["streams"][0]
        audio_format = {
            "codec_name": stream["codec_name"],
            "sample_rate": int(stream["sample_rate"]),
            "channels": int(stream["channels"]),
        }
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BackgroundAudioError(f"Could not determine final audio format: {path}") from exc
    expected = {"codec_name": "aac", "sample_rate": 48000, "channels": 2}
    if audio_format != expected:
        raise BackgroundAudioError(
            f"Invalid final audio format: expected {expected}, got {audio_format}"
        )
    return audio_format


def _demucs_prefix(args: argparse.Namespace) -> list[str]:
    if args.demucs_python:
        if not Path(args.demucs_python).is_file() and not shutil.which(args.demucs_python):
            raise BackgroundAudioError("Background separation tool is not installed.")
        return [args.demucs_python, "-m", "demucs"]
    if args.demucs_bin:
        resolved = shutil.which(args.demucs_bin)
        if not resolved:
            raise BackgroundAudioError("Background separation tool is not installed.")
        return [resolved]
    if importlib.util.find_spec("demucs") is not None:
        return [sys.executable, "-m", "demucs"]
    resolved = shutil.which("demucs")
    if not resolved:
        raise BackgroundAudioError("Background separation tool is not installed.")
    return [resolved]


def _identity(source: Path, model: str) -> dict[str, object]:
    return {
        "source_path": str(source.resolve()),
        "source_size": source.stat().st_size,
        "source_sha256": _sha256(source),
        "backend": BACKEND,
        "model": model,
    }


def _valid_cache(cache_dir: Path, identity: dict[str, object]) -> bool:
    diagnostic, background = cache_dir / "diagnostic.json", cache_dir / "accompaniment.flac"
    try:
        saved = json.loads(diagnostic.read_text(encoding="utf-8"))
        runs = saved.get("background_runs", [])
        return background.is_file() and background.stat().st_size > 0 and any(
            run.get("success") and run.get("source_identity") == identity for run in reversed(runs))
    except (OSError, ValueError, TypeError):
        return False


def _write_manifest_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _separate(args: argparse.Namespace, source: Path, cache_dir: Path) -> None:
    prefix = _demucs_prefix(args)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="separate-", dir=cache_dir) as temporary:
        temp = Path(temporary)
        extracted = temp / "source.wav"
        _run([args.ffmpeg_bin, "-y", "-i", str(source), "-vn", "-acodec", "pcm_s16le",
              str(extracted)], quiet=args.quiet)
        _run([*prefix, "--two-stems=vocals", "-n", args.model, "-o", str(temp),
              str(extracted)], quiet=args.quiet)
        result_dir = temp / args.model / extracted.stem
        generated_background = result_dir / "no_vocals.wav"
        _require_file(generated_background, "Demucs background stem")
        staged = cache_dir / ".accompaniment.flac.tmp.flac"
        _run([args.ffmpeg_bin, "-y", "-i", str(generated_background), "-c:a", "flac", str(staged)],
             quiet=args.quiet)
        _require_file(staged, "temporary accompaniment cache")
        _probe_duration(args.ffprobe_bin, staged)
        os.replace(staged, cache_dir / "accompaniment.flac")


def _update_diagnostic(path: Path, run: dict[str, object]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    history = payload.setdefault("background_runs", [])
    history.append(run)
    payload["background_runs"] = history[-20:]
    _write_manifest_atomic(path, payload)


def add_background_audio(args: argparse.Namespace) -> Path:
    started = monotonic()
    job_dir = Path(args.output_dir) / args.job_id
    cache_dir = job_dir / ".cache"
    new_source = cache_dir / "source_audio.mka"
    source = new_source if new_source.is_file() else job_dir / "01_source" / "source.mp4"
    standard = job_dir / "dubbed_video.mp4"
    legacy_dub_audio = job_dir / "07_audio" / "dub_audio.wav"
    output = job_dir / "dubbed_video_with_bg.mp4"
    diagnostic_path = cache_dir / "diagnostic.json"
    temporary_output = job_dir / "dubbed_video_with_bg.tmp.mp4"
    cache_reused = False
    manifest: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(), "source_identity": None,
        "demucs_backend": BACKEND, "model": args.model, "accompaniment_cache_reused": False,
        "background_db": args.background_db, "final_output_path": str(output), "success": False,
    }
    try:
        for path, label in ((source, "source audio"), (standard, "standard dubbed video")):
            _require_file(path, label)
        if source != new_source:
            _require_file(legacy_dub_audio, "legacy Japanese dub audio")
        cache_dir.mkdir(parents=True, exist_ok=True)
        identity = _identity(source, args.model)
        manifest["source_identity"] = identity
        cache_reused = _valid_cache(cache_dir, identity)
        if not cache_reused:
            _separate(args, source, cache_dir)
        duration = _probe_duration(args.ffprobe_bin, standard)
        filter_graph = (
            "[0:a:0]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[dub];"
            "[1:a:0]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,"
            f"volume={args.background_db:g}dB[background];"
            f"[dub][background]amix=inputs=2:duration=longest:normalize=0,"
            f"apad,atrim=duration={duration:.6f},aresample=48000,"
            "aformat=sample_rates=48000:channel_layouts=stereo[mixed]"
        )
        temporary_output.unlink(missing_ok=True)
        command = [
            args.ffmpeg_bin, "-y", "-i", str(standard), "-i", str(cache_dir / "accompaniment.flac"),
            "-filter_complex", filter_graph,
            "-map", "0:v:0", "-map", "[mixed]", "-c:v", "copy", "-c:a", "aac",
            "-ar", "48000", "-ac", "2", "-movflags", "+faststart",
            "-t", f"{duration:.6f}", str(temporary_output),
        ]
        _run(command, quiet=args.quiet)
        _require_file(temporary_output, "temporary output")
        final_duration = _probe_duration(args.ffprobe_bin, temporary_output)
        if abs(final_duration - duration) > 0.25:
            raise BackgroundAudioError(
                f"Final duration mismatch: expected {duration:.3f}s, got {final_duration:.3f}s"
            )
        final_audio_format = _probe_audio_format(args.ffprobe_bin, temporary_output)
        manifest.update({"accompaniment_cache_reused": cache_reused, "duration": final_duration,
                         "final_audio_format": final_audio_format, "success": True,
                         "ffmpeg_command": command})
        manifest["elapsed_time_seconds"] = round(monotonic() - started, 3)
        os.replace(temporary_output, output)
        _update_diagnostic(diagnostic_path, manifest)
        return output
    except Exception as exc:
        temporary_output.unlink(missing_ok=True)
        manifest.update({"accompaniment_cache_reused": cache_reused, "error": str(exc)[-1200:]})
        manifest["success"] = False
        manifest["elapsed_time_seconds"] = round(monotonic() - started, 3)
        if cache_dir.exists():
            try: _update_diagnostic(diagnostic_path, manifest)
            except OSError: pass
        raise


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.job_id is None:
        args.job_id = select_job_id(Path(args.output_dir))
        if args.job_id is None:
            return 0
    standard = Path(args.output_dir) / args.job_id / "dubbed_video.mp4"
    try:
        output = add_background_audio(args)
    except (BackgroundAudioError, OSError) as exc:
        print(f"Background audio post-process failed: {exc}", file=sys.stderr)
        print(f"Standard dubbed video is unchanged:\n{standard}", file=sys.stderr)
        print("Install Demucs in a separate compatible environment and use --demucs-python PATH,"
              " or provide --demucs-bin PATH.", file=sys.stderr)
        return 1
    print(f"Created background-audio dub: {output}")
    print(f"Standard dubbed video is unchanged: {standard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
