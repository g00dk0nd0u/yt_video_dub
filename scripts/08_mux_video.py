#!/usr/bin/env python3
"""Mux the original video stream with generated Japanese audio."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from path_layout import build_job_paths


class MuxVideoError(RuntimeError):
    """Raised when video muxing fails."""


COPY_COMPATIBLE_CODECS = {"h264"}
H264_CRF = "20"
H264_PRESET = "medium"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mux source.mp4 with dub_audio.wav into 09_simple_mux/dubbed_video.mp4."
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="Job identifier under output/<job_id>/.",
    )
    parser.add_argument("--quiet", action="store_true", help="Capture ffmpeg output unless it fails.")
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
    parser.add_argument(
        "--ffprobe-bin",
        default="ffprobe",
        help="ffprobe binary name or path. Default: ffprobe",
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
    video_mode: str = "copy",
) -> list[str]:
    video_args = (["-c:v", "copy"] if video_mode == "copy" else [
        "-c:v", "libx264", "-preset", H264_PRESET, "-crf", H264_CRF,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    ])
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
        *video_args,
        "-c:a",
        "aac",
        str(output_video_path),
    ]


def _probe_video_stream(ffprobe_bin: str, path: Path) -> dict[str, Any]:
    command = [
        ffprobe_bin, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name", "-of", "json", str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        streams = payload.get("streams")
        codec = streams[0].get("codec_name") if isinstance(streams, list) and streams else None
        if not isinstance(codec, str) or not codec.strip():
            raise MuxVideoError(f"No valid video stream found in: {path}")
        return {"codec_name": codec.strip().lower()}
    except FileNotFoundError as exc:
        raise MuxVideoError(f"ffprobe not found: {ffprobe_bin}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[-4000:]
        detail = f" stderr: {stderr}" if stderr else ""
        raise MuxVideoError(
            f"ffprobe command failed for {path} with exit code {exc.returncode}.{detail}"
        ) from exc
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as exc:
        raise MuxVideoError(f"Invalid ffprobe output for: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = build_job_paths(args.output_dir, args.job_id)
    source_video_path = paths.resolve_source_video_path()
    dub_audio_path = paths.resolve_dub_audio_wav_path()
    output_video_path = paths.dubbed_video_path

    _require_file(source_video_path, "source video")
    _require_file(dub_audio_path, "dub audio")

    source_video_codec = _probe_video_stream(args.ffprobe_bin, source_video_path)["codec_name"]
    video_mode = "copy" if source_video_codec in COPY_COMPATIBLE_CODECS else "transcode"

    command = _build_ffmpeg_command(
        args.ffmpeg_bin,
        source_video_path,
        dub_audio_path,
        output_video_path,
        args.original_audio_db,
        video_mode,
    )
    if not args.quiet:
        print(shlex.join(command))

    try:
        result = subprocess.run(command, check=True, capture_output=args.quiet, text=args.quiet)
    except FileNotFoundError as exc:
        raise MuxVideoError(f"ffmpeg not found: {args.ffmpeg_bin}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[-4000:] if args.quiet else ""
        detail = f" stderr: {stderr}" if stderr else ""
        raise MuxVideoError(
            f"ffmpeg command failed with exit code {exc.returncode}.{detail} "
            f"source_video_codec={source_video_codec} video_mode={video_mode}"
        ) from exc

    try:
        output_video_codec = _probe_video_stream(args.ffprobe_bin, output_video_path)["codec_name"]
    except MuxVideoError as exc:
        raise MuxVideoError(
            f"{exc} source_video_codec={source_video_codec} video_mode={video_mode}"
        ) from exc
    expected_output_codec = source_video_codec if video_mode == "copy" else "h264"
    if output_video_codec != expected_output_codec or output_video_codec not in COPY_COMPATIBLE_CODECS:
        raise MuxVideoError(
            "Muxed video failed codec compatibility validation: "
            f"expected {expected_output_codec}, got {output_video_codec}."
        )

    manifest_path = paths.audio_dir / "fast_mux_manifest.json"
    manifest_path.write_text(json.dumps({
        "job_id": args.job_id,
        "output_video": paths.rel_to_job(output_video_path),
        "source_video_codec": source_video_codec,
        "output_video_codec": output_video_codec,
        "video_mode": video_mode,
        "compatibility_fallback_used": video_mode == "transcode",
        "original_audio_db": args.original_audio_db,
        "command": command,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"Created dubbed video: {output_video_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
