#!/usr/bin/env python3
"""Generate per-segment WAV files from translated segments via AivisSpeech."""

from __future__ import annotations

import argparse
import io
import json
import math
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from path_layout import build_job_paths


DEFAULT_TIMEOUT = 30.0
MAX_SPEED_SCALE = 1.15
TARGET_CHARS_SAFETY_MARGIN = 0.9
FIT_METADATA_FIELDS = (
    "available_duration",
    "raw_tts_duration",
    "final_tts_duration",
    "duration_ratio",
    "speed_scale",
    "fit_status",
    "retry_count",
    "translation_retry_required",
)


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
        "--segment-id",
        action="append",
        dest="segment_ids",
        help=("Process only this segment ID. Repeatable; when combined with a range, "
              "only IDs inside that range are selected."),
    )
    parser.add_argument(
        "--max-speed-scale",
        type=float,
        default=MAX_SPEED_SCALE,
        help=f"Maximum AivisSpeech speedScale used for one fitting retry. Default: {MAX_SPEED_SCALE}",
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
    **fit: Any,
) -> dict[str, Any]:
    item = {
        "index": item_index,
        "segment_id": segment["segment_id"],
        "start": segment["start"],
        "end": segment["end"],
        "text": segment["text"],
        "wav_path": wav_path,
        "status": status,
    }
    item.update(fit)
    return item


def _measure_wav_duration(wav_data: bytes | Path) -> float:
    source = io.BytesIO(wav_data) if isinstance(wav_data, bytes) else str(wav_data)
    try:
        with wave.open(source, "rb") as reader:
            framerate = reader.getframerate()
            if framerate <= 0:
                raise TTSError("Synthesized WAV has an invalid sample rate.")
            return reader.getnframes() / float(framerate)
    except (wave.Error, EOFError) as exc:
        raise TTSError("AivisSpeech returned an invalid WAV file.") from exc


def _classify_duration(raw_duration: float, available_duration: float,
                       max_speed_scale: float = MAX_SPEED_SCALE) -> tuple[str, float, bool]:
    if available_duration <= 0:
        return "ng", math.inf, False
    required_speed = raw_duration / available_duration
    if required_speed <= 1.0:
        return "ok", required_speed, False
    if required_speed <= max_speed_scale:
        return "retry", required_speed, True
    return "ng", required_speed, False


def _target_chars(text: str, available_duration: float, raw_tts_duration: float,
                  safety_margin: float = TARGET_CHARS_SAFETY_MARGIN) -> int:
    if not text or raw_tts_duration <= 0 or available_duration <= 0:
        return 0
    estimate = len(text) * available_duration / raw_tts_duration * safety_margin
    return max(1, min(len(text) - 1, math.floor(estimate)))


def _fit_fields(available: float, raw: float, final: float, speed: float,
                fit_status: str, retry_count: int) -> dict[str, Any]:
    return {
        "available_duration": round(available, 6),
        "raw_tts_duration": round(raw, 6),
        "final_tts_duration": round(final, 6),
        "duration_ratio": round(final / available, 6) if available > 0 else None,
        "speed_scale": round(speed, 6),
        "fit_status": fit_status,
        "retry_count": retry_count,
        "translation_retry_required": fit_status == "ng",
    }


def _write_retry_artifact(path: Path, items: list[dict[str, Any]]) -> None:
    rows = []
    for item in items:
        if not item.get("translation_retry_required"):
            continue
        available = float(item["available_duration"])
        raw = float(item["raw_tts_duration"])
        text = str(item.get("text", ""))
        rows.append({
            "segment_id": item["segment_id"], "start": item["start"], "end": item["end"],
            "duration": available, "current_text": text, "raw_tts_duration": raw,
            "required_speed": round(raw / available, 6) if available > 0 else None,
            "target_chars": _target_chars(text, available, raw),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(content, encoding="utf-8")


def _write_manifest(
    manifest_path: Path,
    job_id: str,
    base_url: str,
    speaker_id: int,
    total_segments: int,
    items: list[dict[str, Any]],
    run_metrics: dict[str, Any],
) -> None:
    payload = {
        "job_id": job_id,
        "tts_provider": "aivis",
        "voice": str(speaker_id),
        "base_url": base_url,
        "speaker_id": speaker_id,
        "total_segments": total_segments,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_metrics": run_metrics,
        "items": items,
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_existing_manifest(manifest_path: Path) -> dict[str, Any] | None:
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

    for item in items:
        if not isinstance(item, dict):
            raise TTSError(f"Invalid item found in existing manifest: {manifest_path}")
    return payload


def _is_reusable_tts(
    existing_item: dict[str, Any] | None,
    current_segment: dict[str, Any],
    existing_manifest_settings: dict[str, Any],
    current_settings: dict[str, Any],
) -> bool:
    """Return whether a cached WAV represents the current text, timing, and voice."""
    if existing_item is None:
        return False
    existing_provider = existing_manifest_settings.get("tts_provider", "aivis")
    if existing_provider != current_settings.get("tts_provider", "aivis"):
        return False
    existing_voice = existing_manifest_settings.get(
        "voice", str(existing_manifest_settings.get("speaker_id"))
    )
    current_voice = current_settings.get("voice", str(current_settings.get("speaker_id")))
    if existing_voice != current_voice:
        return False
    for field in ("segment_id", "text", "start", "end"):
        if existing_item.get(field) != current_segment.get(field):
            return False
    if existing_manifest_settings.get("speaker_id") != current_settings.get("speaker_id"):
        return False
    existing_base_url = existing_manifest_settings.get("base_url")
    current_base_url = current_settings.get("base_url")
    if not isinstance(existing_base_url, str) or not isinstance(current_base_url, str):
        return False
    return _normalize_base_url(existing_base_url) == _normalize_base_url(current_base_url)


def _reused_fit_metadata(
    existing_item: dict[str, Any], available_duration: float, measured_duration: float
) -> dict[str, Any]:
    if all(field in existing_item for field in FIT_METADATA_FIELDS):
        return {field: existing_item[field] for field in FIT_METADATA_FIELDS}
    return _fit_fields(
        available_duration,
        measured_duration,
        measured_duration,
        1.0,
        "ok" if measured_duration <= available_duration else "ng",
        0,
    )


def _select_process_segments(
    segments: list[dict[str, Any]],
    start_index: int | None,
    end_index: int | None,
    limit: int | None,
    segment_ids: list[str] | None = None,
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

    if segment_ids:
        selected_ids = set(segment_ids)
        indexed_segments = [item for item in indexed_segments if item[1]["segment_id"] in selected_ids]

    if limit is not None:
        indexed_segments = indexed_segments[:limit]

    return indexed_segments, has_range or bool(segment_ids)


def _fit_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    fitted_items = [item for item in items if item.get("status") != "skipped_empty"]
    return {
        "fit_ok_count": sum(item.get("fit_status") == "ok" for item in fitted_items),
        "fit_fitted_count": sum(item.get("fit_status") == "fitted" for item in fitted_items),
        "fit_ng_count": sum(item.get("fit_status") == "ng" for item in fitted_items),
    }


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
    if args.max_speed_scale < 1.0:
        raise TTSError("--max-speed-scale must be at least 1.0.")

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
        segment_ids=args.segment_ids,
    )
    if args.segment_ids:
        known_ids = {segment["segment_id"] for segment in segments}
        unknown_ids = sorted(set(args.segment_ids) - known_ids)
        if unknown_ids:
            raise TTSError("Unknown --segment-id value(s): " + ", ".join(unknown_ids))
    if not process_segments:
        raise TTSError("No segments matched the requested range.")

    tts_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifest_items: list[dict[str, Any]] = []
    existing_manifest = _load_existing_manifest(manifest_path)
    existing_manifest_items = existing_manifest["items"] if existing_manifest else None
    existing_items_by_index = {
        item["index"]: item
        for item in (existing_manifest_items or [])
        if isinstance(item.get("index"), int)
    }
    current_settings = {"tts_provider": "aivis", "voice": str(args.speaker_id),
                        "base_url": base_url, "speaker_id": args.speaker_id}
    run_started = time.perf_counter()
    run_metrics: dict[str, Any] = {
        "selected_units": len(process_segments),
        "generated_units": 0,
        "reused_units": 0,
        "skipped_empty_units": 0,
        "normal_synthesis_count": 0,
        "speed_fit_synthesis_count": 0,
        "audio_query_wall_seconds": 0.0,
        "synthesis_wall_seconds": 0.0,
    }
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
            available_duration = max(0.0, segment["end"] - segment["start"])

            if text == "":
                status = "skipped_empty"
                run_metrics["skipped_empty_units"] += 1
                manifest_items.append(
                    _build_manifest_item(item_index, segment, None, status,
                                         **_fit_fields(available_duration, 0, 0, 1.0, "ok", 0))
                )
                print(f"[{item_index}/{total_segments}] segment_id={segment['segment_id']} status={status}")
                continue

            if args.resume and not args.force:
                existing_item = existing_items_by_index.get(item_index)
                for reuse_candidate in reuse_candidates:
                    if not reuse_candidate.exists() or not _is_reusable_tts(
                        existing_item,
                        segment,
                        existing_manifest or {},
                        current_settings,
                    ):
                        continue
                    assert existing_item is not None
                    wav_relative_path = paths.rel_to_job(reuse_candidate)
                    if existing_item.get("wav_path") != wav_relative_path:
                        continue
                    status = "reused"
                    run_metrics["reused_units"] += 1
                    reused_duration = _measure_wav_duration(reuse_candidate)
                    manifest_items.append(
                        _build_manifest_item(
                            item_index, segment, wav_relative_path, status,
                            **_reused_fit_metadata(
                                existing_item, available_duration, reused_duration
                            ),
                        )
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

            request_started = time.perf_counter()
            audio_query_payload = _post_audio_query(
                session=session,
                base_url=base_url,
                speaker_id=args.speaker_id,
                text=text,
                timeout=args.timeout,
            )
            run_metrics["audio_query_wall_seconds"] += time.perf_counter() - request_started
            # Always establish the baseline at normal speed before considering a retry.
            audio_query_payload["speedScale"] = 1.0
            request_started = time.perf_counter()
            wav_bytes = _post_synthesis(
                session=session,
                base_url=base_url,
                speaker_id=args.speaker_id,
                audio_query_payload=audio_query_payload,
                timeout=args.timeout,
            )
            run_metrics["synthesis_wall_seconds"] += time.perf_counter() - request_started
            run_metrics["normal_synthesis_count"] += 1
            raw_tts_duration = _measure_wav_duration(wav_bytes)
            classification, required_speed, should_retry = _classify_duration(
                raw_tts_duration, available_duration, args.max_speed_scale
            )
            speed_scale = 1.0
            retry_count = 0
            final_tts_duration = raw_tts_duration
            fit_status = classification
            if should_retry:
                speed_scale = required_speed
                audio_query_payload["speedScale"] = speed_scale
                request_started = time.perf_counter()
                wav_bytes = _post_synthesis(
                    session=session, base_url=base_url, speaker_id=args.speaker_id,
                    audio_query_payload=audio_query_payload, timeout=args.timeout,
                )
                run_metrics["synthesis_wall_seconds"] += time.perf_counter() - request_started
                run_metrics["speed_fit_synthesis_count"] += 1
                retry_count = 1
                final_tts_duration = _measure_wav_duration(wav_bytes)
                fit_status = "fitted" if final_tts_duration <= available_duration else "ng"
            wav_output_path.write_bytes(wav_bytes)

            status = "generated"
            run_metrics["generated_units"] += 1
            wav_relative_path = paths.rel_to_job(wav_output_path)
            manifest_items.append(
                _build_manifest_item(
                    item_index, segment, wav_relative_path, status,
                    **_fit_fields(available_duration, raw_tts_duration, final_tts_duration,
                                  speed_scale, fit_status, retry_count),
                )
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

    run_metrics.update(_fit_counts([
        item for item in manifest_items
        if item.get("index") in {index for index, _segment in process_segments}
    ]))
    run_metrics["manifest_counts"] = _fit_counts(manifest_items)
    for field in ("audio_query_wall_seconds", "synthesis_wall_seconds"):
        run_metrics[field] = round(run_metrics[field], 6)
    run_metrics["tts_wall_seconds"] = round(time.perf_counter() - run_started, 6)

    _write_manifest(
        manifest_path=manifest_path,
        job_id=args.job_id,
        base_url=base_url,
        speaker_id=args.speaker_id,
        total_segments=total_segments,
        items=manifest_items,
        run_metrics=run_metrics,
    )
    _write_retry_artifact(paths.duration_retry_required_path, manifest_items)

    print(f"Wrote manifest: {manifest_path}")
    print(f"Wrote duration retry artifact: {paths.duration_retry_required_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
