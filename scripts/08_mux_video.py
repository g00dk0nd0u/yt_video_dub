#!/usr/bin/env python3
"""Mux the original video stream with generated Japanese audio."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path


class MuxVideoError(RuntimeError):
    """Raised when video muxing fails."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mux source.mp4 with dub_audio.wav into dubbed_video.mp4."
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="Job identifier under output/<job_id>/.",
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
) -> list[str]:
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(source_video_path),
        "-i",
        str(dub_audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_video_path),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    job_dir = Path(args.output_dir) / args.job_id
    source_video_path = job_dir / "source.mp4"
    dub_audio_path = job_dir / "dub_audio.wav"
    output_video_path = job_dir / "dubbed_video.mp4"

    _require_file(source_video_path, "source video")
    _require_file(dub_audio_path, "dub audio")

    command = _build_ffmpeg_command(
        args.ffmpeg_bin,
        source_video_path,
        dub_audio_path,
        output_video_path,
    )
    print(shlex.join(command))

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise MuxVideoError(f"ffmpeg not found: {args.ffmpeg_bin}") from exc
    except subprocess.CalledProcessError as exc:
        raise MuxVideoError(f"ffmpeg command failed with exit code {exc.returncode}.") from exc

    print(f"Created dubbed video: {output_video_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
