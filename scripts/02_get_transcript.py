#!/usr/bin/env python3
"""Fetch the original transcript for a prepared job."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi

from path_layout import build_job_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch transcript data for a prepared dubbing job."
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
        "--language",
        default="en",
        help="Preferred transcript language code. Default: en",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        help="Reserved for future Whisper fallback support.",
    )
    return parser


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _load_job_payload(job_dir: Path) -> dict:
    job_path = build_job_paths(job_dir.parent, job_dir.name).resolve_job_json_path()
    if not job_path.exists():
        raise FileNotFoundError(f"Missing job file: {job_path}")
    return json.loads(job_path.read_text(encoding="utf-8"))


def _select_transcript(video_id: str, language: str):
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    preferred_languages = [language]
    if language != "en":
        preferred_languages.append("en")

    finders = (
        transcript_list.find_manually_created_transcript,
        transcript_list.find_generated_transcript,
        transcript_list.find_transcript,
    )
    for finder in finders:
        try:
            return finder(preferred_languages)
        except Exception:
            continue
    raise RuntimeError(
        "No usable transcript was found. "
        "Whisper fallback is not implemented in Phase 1."
    )


def _write_transcript_json(job_path, transcript, segments: list[dict]) -> None:
    payload = {
        "video_id": transcript.video_id,
        "language": transcript.language,
        "language_code": transcript.language_code,
        "is_generated": transcript.is_generated,
        "segments": segments,
    }
    job_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_transcript_srt(job_path, segments: list[dict]) -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                (
                    f"{_format_srt_timestamp(segment['start'])} --> "
                    f"{_format_srt_timestamp(segment['end'])}"
                ),
                segment["text"],
                "",
            ]
        )
    job_path.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = build_job_paths(args.output_dir, args.job_id)
    paths.ensure_prepare_dirs()
    job_payload = _load_job_payload(paths.job_dir)
    video_id = job_payload.get("video_id")
    if not video_id:
        raise RuntimeError(
            "job.json does not contain a video_id. "
            "Only YouTube-based Phase 1 jobs are supported."
        )

    try:
        transcript = _select_transcript(video_id, args.language)
        fetched = transcript.fetch(preserve_formatting=True)
    except Exception as exc:
        raise RuntimeError(
            "Failed to fetch a YouTube transcript for this video. "
            "Whisper fallback is not implemented in Phase 1."
        ) from exc

    segments = []
    for index, item in enumerate(fetched, start=1):
        text = html.unescape(item.text).replace("\r\n", "\n").replace("\r", "\n").strip()
        segments.append(
            {
                "segment_id": f"seg_{index:04}",
                "start": round(float(item.start), 3),
                "end": round(float(item.start + item.duration), 3),
                "duration": round(float(item.duration), 3),
                "text": text,
            }
        )

    _write_transcript_json(paths.transcript_raw_json_path, transcript, segments)
    _write_transcript_srt(paths.transcript_raw_srt_path, segments)
    print(f"Saved transcript for job: {args.job_id}")
    print(f"Language: {transcript.language_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
