#!/usr/bin/env python3
"""Generate per-segment WAV files from translated segments via AivisSpeech."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_TIMEOUT = 30.0


class TTSError(RuntimeError):
    """Raised when TTS generation fails with useful context."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate per-segment WAV files with AivisSpeech."
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
        "--base-url",
        required=True,
        help="Base URL for the local AivisSpeech API.",
    )
    parser.add_argument(
        "--speaker-id",
        required=True,
        type=int,
        help="Speaker ID to use for TTS generation.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N segments for test runs.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse existing WAV files instead of calling the API again.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds. Default: {DEFAULT_TIMEOUT}",
    )
    return parser


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _truncate_text(value: str, limit: int = 600) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...<truncated>..."


def _format_response_body(response: requests.Response) -> str:
    text = response.text.strip()
    if not text:
        return "<empty>"

    try:
        parsed = response.json()
    except ValueError:
        return _truncate_text(text)

    return _truncate_text(json.dumps(parsed, ensure_ascii=False, indent=2))


def _raise_http_error(step: str, response: requests.Response) -> None:
    raise TTSError(
        f"{step} failed.\n"
        f"HTTP {response.status_code} {response.reason}\n"
        f"URL: {response.request.method} {response.url}\n"
        f"Response body:\n{_format_response_body(response)}"
    )


def _load_translated_segments(job_dir: Path) -> list[dict[str, Any]]:
    translated_segments_path = job_dir / "translated_segments.json"
    if not translated_segments_path.exists():
        raise FileNotFoundError(f"Missing translated segments file: {translated_segments_path}")

    try:
        payload = json.loads(translated_segments_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TTSError(f"Invalid JSON in translated segments file: {translated_segments_path}") from exc

    if not isinstance(payload, dict):
        raise TTSError(
            f"translated_segments.json must contain a JSON object: {translated_segments_path}"
        )

    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise TTSError(
            f"translated_segments.json is missing a segments list: {translated_segments_path}"
        )

    validated: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise TTSError(
                "Each segment in translated_segments.json must be a JSON object. "
                f"Invalid entry at index {index}."
            )

        segment_id = segment.get("segment_id")
        start = segment.get("start")
        end = segment.get("end")
        text = segment.get("text")

        if not isinstance(segment_id, str) or not segment_id:
            raise TTSError(f"Segment {index} is missing a valid segment_id.")
        if not isinstance(start, (int, float)):
            raise TTSError(f"Segment {index} has an invalid start value.")
        if not isinstance(end, (int, float)):
            raise TTSError(f"Segment {index} has an invalid end value.")
        if not isinstance(text, str):
            raise TTSError(f"Segment {index} has an invalid text value.")

        validated.append(
            {
                "segment_id": segment_id,
                "start": float(start),
                "end": float(end),
                "text": text,
            }
        )

    return validated


def _post_audio_query(
    session: requests.Session,
    base_url: str,
    speaker_id: int,
    text: str,
    timeout: float,
) -> dict[str, Any]:
    response = session.post(
        f"{base_url}/audio_query",
        params={"text": text, "speaker": speaker_id},
        timeout=timeout,
    )
    if not response.ok:
        _raise_http_error("audio_query", response)

    try:
        payload = response.json()
    except ValueError as exc:
        raise TTSError(
            "audio_query returned a non-JSON response.\n"
            f"HTTP {response.status_code} {response.reason}\n"
            f"Response body:\n{_format_response_body(response)}"
        ) from exc

    if not isinstance(payload, dict):
        raise TTSError(
            "audio_query returned JSON, but it was not an object.\n"
            f"Response body:\n{_format_response_body(response)}"
        )
    return payload


def _post_synthesis(
    session: requests.Session,
    base_url: str,
    speaker_id: int,
    audio_query_payload: dict[str, Any],
    timeout: float,
) -> bytes:
    response = session.post(
        f"{base_url}/synthesis",
        params={"speaker": speaker_id},
        json=audio_query_payload,
        timeout=timeout,
    )
    if not response.ok:
        _raise_http_error("synthesis", response)

    content_type = response.headers.get("content-type", "")
    if "audio" not in content_type.lower() and not response.content.startswith(b"RIFF"):
        raise TTSError(
            "synthesis succeeded, but the response did not look like WAV/audio data.\n"
            f"HTTP {response.status_code} {response.reason}\n"
            f"Content-Type: {content_type or '<missing>'}\n"
            f"Response body preview:\n{_format_response_body(response)}"
        )

    return response.content


def _build_manifest_item(
    item_index: int,
    segment: dict[str, Any],
    wav_path: str | None,
    status: str,
) -> dict[str, Any]:
    return {
        "index": item_index,
        "segment_id": segment["segment_id"],
        "start": segment["start"],
        "end": segment["end"],
        "text": segment["text"],
        "wav_path": wav_path,
        "status": status,
    }


def _write_manifest(
    manifest_path: Path,
    job_id: str,
    base_url: str,
    speaker_id: int,
    total_segments: int,
    items: list[dict[str, Any]],
) -> None:
    payload = {
        "job_id": job_id,
        "base_url": base_url,
        "speaker_id": speaker_id,
        "total_segments": total_segments,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit <= 0:
        raise TTSError("--limit must be a positive integer.")

    job_dir = Path(args.output_dir) / args.job_id
    tts_dir = job_dir / "tts"
    manifest_path = tts_dir / "tts_manifest.json"
    base_url = _normalize_base_url(args.base_url)

    segments = _load_translated_segments(job_dir)
    total_segments = len(segments)
    process_segments = segments[: args.limit] if args.limit is not None else segments

    tts_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifest_items: list[dict[str, Any]] = []

    try:
        for item_index, segment in enumerate(process_segments, start=1):
            wav_filename = f"segment_{item_index:06d}.wav"
            wav_relative_path = f"tts/{wav_filename}"
            wav_output_path = tts_dir / wav_filename
            text = segment["text"]

            if text == "":
                status = "skipped_empty"
                manifest_items.append(
                    _build_manifest_item(item_index, segment, None, status)
                )
                print(f"[{item_index}/{total_segments}] segment_id={segment['segment_id']} status={status}")
                continue

            if args.resume and wav_output_path.exists():
                status = "reused"
                manifest_items.append(
                    _build_manifest_item(item_index, segment, wav_relative_path, status)
                )
                print(f"[{item_index}/{total_segments}] segment_id={segment['segment_id']} status={status}")
                continue

            audio_query_payload = _post_audio_query(
                session=session,
                base_url=base_url,
                speaker_id=args.speaker_id,
                text=text,
                timeout=args.timeout,
            )
            wav_bytes = _post_synthesis(
                session=session,
                base_url=base_url,
                speaker_id=args.speaker_id,
                audio_query_payload=audio_query_payload,
                timeout=args.timeout,
            )
            wav_output_path.write_bytes(wav_bytes)

            status = "generated"
            manifest_items.append(
                _build_manifest_item(item_index, segment, wav_relative_path, status)
            )
            print(f"[{item_index}/{total_segments}] segment_id={segment['segment_id']} status={status}")
    except requests.RequestException as exc:
        raise TTSError(
            "Failed to connect to the AivisSpeech API.\n"
            f"Base URL: {base_url}\n"
            f"Details: {exc}"
        ) from exc
    finally:
        session.close()

    _write_manifest(
        manifest_path=manifest_path,
        job_id=args.job_id,
        base_url=base_url,
        speaker_id=args.speaker_id,
        total_segments=total_segments,
        items=manifest_items,
    )

    print(f"Wrote manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
