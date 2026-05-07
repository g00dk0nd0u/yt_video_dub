#!/usr/bin/env python3
"""Generate per-segment WAV files from translated segments via AivisSpeech."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from path_layout import build_job_paths


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
        "--start-index",
        type=int,
        help="1-based translated segment index to start from.",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        help="1-based translated segment index to end at.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N segments for test runs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate WAV files even when they already exist.",
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


def _load_translated_segments(translated_segments_path: Path) -> list[dict[str, Any]]:
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


def _load_existing_manifest_items(manifest_path: Path) -> list[dict[str, Any]] | None:
    if not manifest_path.exists():
        return None

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TTSError(f"Invalid JSON in TTS manifest file: {manifest_path}") from exc

    if not isinstance(payload, dict):
        raise TTSError(f"tts_manifest.json must contain a JSON object: {manifest_path}")

    items = payload.get("items")
    if not isinstance(items, list):
        raise TTSError(f"tts_manifest.json is missing an items list: {manifest_path}")

    validated_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise TTSError(f"Invalid item found in existing manifest: {manifest_path}")
        validated_items.append(item)
    return validated_items


def _select_process_segments(
    segments: list[dict[str, Any]],
    start_index: int | None,
    end_index: int | None,
    limit: int | None,
) -> tuple[list[tuple[int, dict[str, Any]]], bool]:
    indexed_segments = list(enumerate(segments, start=1))
    has_range = start_index is not None or end_index is not None
    if has_range:
        start = start_index if start_index is not None else 1
        end = end_index if end_index is not None else len(indexed_segments)
        indexed_segments = [
            (item_index, segment)
            for item_index, segment in indexed_segments
            if start <= item_index <= end
        ]

    if limit is not None:
        indexed_segments = indexed_segments[:limit]

    return indexed_segments, has_range


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit <= 0:
        raise TTSError("--limit must be a positive integer.")
    if args.start_index is not None and args.start_index <= 0:
        raise TTSError("--start-index must be a positive integer.")
    if args.end_index is not None and args.end_index <= 0:
        raise TTSError("--end-index must be a positive integer.")
    if (
        args.start_index is not None
        and args.end_index is not None
        and args.start_index > args.end_index
    ):
        raise TTSError("--start-index must be less than or equal to --end-index.")

    paths = build_job_paths(args.output_dir, args.job_id)
    legacy_tts_dir = paths.job_dir / "tts"
    tts_dir = paths.tts_dir
    manifest_path = paths.tts_manifest_path
    base_url = _normalize_base_url(args.base_url)
    paths.ensure_tts_dirs()

    segments = _load_translated_segments(paths.resolve_translated_segments_json_path())
    total_segments = len(segments)
    process_segments, has_range = _select_process_segments(
        segments=segments,
        start_index=args.start_index,
        end_index=args.end_index,
        limit=args.limit,
    )
    if not process_segments:
        raise TTSError("No segments matched the requested range.")

    tts_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifest_items: list[dict[str, Any]] = []
    existing_manifest_items = _load_existing_manifest_items(manifest_path)
    if has_range and existing_manifest_items is None:
        print(
            "Warning: partial run requested without an existing tts_manifest.json. "
            "The new manifest will contain only the processed items."
        )

    try:
        for item_index, segment in process_segments:
            wav_filename = f"segment_{item_index:06d}.wav"
            wav_output_path = tts_dir / wav_filename
            reuse_candidates = [wav_output_path]
            if legacy_tts_dir != tts_dir:
                reuse_candidates.append(legacy_tts_dir / wav_filename)
            text = segment["text"]

            if text == "":
                status = "skipped_empty"
                manifest_items.append(
                    _build_manifest_item(item_index, segment, None, status)
                )
                print(f"[{item_index}/{total_segments}] segment_id={segment['segment_id']} status={status}")
                continue

            if args.resume and not args.force:
                for reuse_candidate in reuse_candidates:
                    if reuse_candidate.exists():
                        status = "reused"
                        wav_relative_path = paths.rel_to_job(reuse_candidate)
                        manifest_items.append(
                            _build_manifest_item(item_index, segment, wav_relative_path, status)
                        )
                        print(
                            f"[{item_index}/{total_segments}] "
                            f"segment_id={segment['segment_id']} status={status}"
                        )
                        break
                else:
                    reuse_candidate = None
                if reuse_candidate is not None:
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
            wav_relative_path = paths.rel_to_job(wav_output_path)
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

    if has_range and existing_manifest_items is not None:
        items_by_index: dict[int, dict[str, Any]] = {}
        for item in existing_manifest_items:
            existing_index = item.get("index")
            if isinstance(existing_index, int):
                items_by_index[existing_index] = item
        for item in manifest_items:
            items_by_index[item["index"]] = item
        manifest_items = [items_by_index[index] for index in sorted(items_by_index)]

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
