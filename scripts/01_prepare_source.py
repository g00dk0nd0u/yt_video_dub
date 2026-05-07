#!/usr/bin/env python3
"""Prepare a job workspace and register source input."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from yt_dlp import YoutubeDL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare source assets for a dubbing job."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--youtube-url",
        help="YouTube URL to prepare as the source input.",
    )
    source_group.add_argument(
        "--local-video",
        help="Local video file to copy into output/<job_id>/source.mp4.",
    )
    parser.add_argument(
        "--job-id",
        help="Job identifier used as output/<job_id>/. Default: YouTube video ID",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory. Default: output",
    )
    return parser


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _extract_youtube_metadata(youtube_url: str) -> dict:
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    if not info or not info.get("id"):
        raise RuntimeError("Failed to resolve YouTube metadata from the provided URL.")
    return info


def _download_youtube_source(youtube_url: str, job_dir: Path) -> Path:
    outtmpl = str(job_dir / "source.%(ext)s")
    options = {
        "quiet": True,
        "no_warnings": True,
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
    }
    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(youtube_url, download=True)
        downloaded_path = Path(ydl.prepare_filename(result))

    candidates = [job_dir / "source.mp4", downloaded_path]
    for candidate in candidates:
        if candidate.exists():
            if candidate.name != "source.mp4":
                if candidate.suffix.lower() != ".mp4":
                    raise RuntimeError(
                        "yt-dlp did not produce an mp4 file for this video. "
                        "Phase 1 currently requires source.mp4."
                    )
                target = job_dir / "source.mp4"
                if target.exists():
                    target.unlink()
                candidate.rename(target)
                return target
            return candidate

    matches = sorted(job_dir.glob("source.*"))
    if matches:
        candidate = matches[0]
        if candidate.suffix.lower() != ".mp4":
            raise RuntimeError(
                "yt-dlp produced a non-mp4 source file. "
                "Phase 1 currently requires source.mp4."
            )
        target = job_dir / "source.mp4"
        if target.exists():
            target.unlink()
        candidate.rename(target)
        return target

    raise RuntimeError("yt-dlp finished without producing a source video file.")


def _write_job_file(job_path: Path, payload: dict) -> None:
    job_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare_source(
    *,
    youtube_url: str | None,
    local_video: str | None,
    job_id: str | None,
    output_dir: str,
) -> str:
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    if youtube_url:
        info = _extract_youtube_metadata(youtube_url)
        resolved_job_id = job_id or info["id"]
        job_dir = output_dir_path / resolved_job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        source_path = _download_youtube_source(youtube_url, job_dir)
        (job_dir / "translation_output").mkdir(exist_ok=True)
        job_payload = {
            "job_id": resolved_job_id,
            "created_at": _utc_now_iso(),
            "source_type": "youtube",
            "youtube_url": youtube_url,
            "video_id": info["id"],
            "title": info.get("title"),
            "source_path": str(source_path.relative_to(job_dir)),
        }
        _write_job_file(job_dir / "job.json", job_payload)
        print(f"Prepared job: {resolved_job_id}")
        print(f"Job directory: {job_dir}")
        return resolved_job_id

    resolved_job_id = job_id or "local-video"
    raise NotImplementedError(
        "Local video input is reserved for a later phase. "
        f"Received --local-video for job_id='{resolved_job_id}'."
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    prepare_source(
        youtube_url=args.youtube_url,
        local_video=args.local_video,
        job_id=args.job_id,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
