#!/usr/bin/env python3
"""Mux the original video stream with generated Japanese audio."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path

from path_layout import build_job_paths


class MuxVideoError(RuntimeError):
    """Raised when video muxing fails."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mux source.mp4 with dub_audio.wav into 09_simple_mux/dubbed_video.mp4."
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="Job identifier under output/<job_id>/.",
    )
    parser.add_argument(
        "--original-audio-db", type=float, default=-38.0,
        help="Volume of the original soundtrack in dB. Default: -38.0",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory. Default: output",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default="ffmpeg",
        help="ffmpeg binary name or path. Default: ffmpeg",
    )
    return parser


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if not path.is_file():
        raise MuxVideoError(f"Expected {label} to be a file: {path}")


def _build_ffmpeg_command(
    ffmpeg_bin: str,
    source_video_path: Path,
    dub_audio_path: Path,
    output_video_path: Path,
    original_audio_db: float = -38.0,
) -> list[str]:
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(source_video_path),
        "-i",
        str(dub_audio_path),
        "-filter_complex",
        f"[0:a:0]volume={original_audio_db}dB[original];[original][1:a:0]amix=inputs=2:duration=first:normalize=0[mixed]",
        "-map", "0:v:0",
        "-map", "[mixed]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        str(output_video_path),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = build_job_paths(args.output_dir, args.job_id)
    source_video_path = paths.resolve_source_video_path()
    dub_audio_path = paths.resolve_dub_audio_wav_path()
    output_video_path = paths.dubbed_video_path

    _require_file(source_video_path, "source video")
    _require_file(dub_audio_path, "dub audio")

    command = _build_ffmpeg_command(
        args.ffmpeg_bin,
        source_video_path,
        dub_audio_path,
        output_video_path,
        args.original_audio_db,
    )
    print(shlex.join(command))

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise MuxVideoError(f"ffmpeg not found: {args.ffmpeg_bin}") from exc
    except subprocess.CalledProcessError as exc:
        raise MuxVideoError(f"ffmpeg command failed with exit code {exc.returncode}.") from exc

    manifest_path = paths.audio_dir / "fast_mux_manifest.json"
    manifest_path.write_text(json.dumps({
        "job_id": args.job_id,
        "output_video": paths.rel_to_job(output_video_path),
        "video_codec": "copy",
        "original_audio_db": args.original_audio_db,
        "command": command,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created dubbed video: {output_video_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
