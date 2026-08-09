#!/usr/bin/env python3
"""Build a single dub audio WAV from per-segment TTS WAV files."""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path
from typing import Any

from path_layout import build_job_paths


class DubAudioError(RuntimeError):
    """Raised when dub-audio assembly fails."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build 07_audio/dub_audio.wav from the TTS manifest."
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
    return parser


def _load_tts_manifest(manifest_path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing TTS manifest file: {manifest_path}")

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DubAudioError(f"Invalid JSON in TTS manifest file: {manifest_path}") from exc

    if not isinstance(payload, dict):
        raise DubAudioError(f"tts_manifest.json must contain a JSON object: {manifest_path}")

    items = payload.get("items")
    if not isinstance(items, list):
        raise DubAudioError(f"tts_manifest.json is missing an items list: {manifest_path}")

    return payload


def _validate_item(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise DubAudioError(f"Each manifest item must be a JSON object. Invalid entry at index {index}.")

    start = item.get("start")
    end = item.get("end")
    status = item.get("status")
    wav_path = item.get("wav_path")

    if not isinstance(start, (int, float)):
        raise DubAudioError(f"Manifest item {index} has an invalid start value.")
    if not isinstance(end, (int, float)):
        raise DubAudioError(f"Manifest item {index} has an invalid end value.")
    if end < start:
        raise DubAudioError(f"Manifest item {index} has end earlier than start.")
    if not isinstance(status, str):
        raise DubAudioError(f"Manifest item {index} has an invalid status value.")

    if status == "skipped_empty":
        if wav_path is not None:
            raise DubAudioError(f"Manifest item {index} is skipped_empty but has wav_path.")
    elif status in {"generated", "reused"}:
        if not isinstance(wav_path, str) or not wav_path:
            raise DubAudioError(f"Manifest item {index} with status={status} is missing wav_path.")
    else:
        raise DubAudioError(f"Manifest item {index} has unsupported status: {status}")

    validated = dict(item)
    validated["start"] = float(start)
    validated["end"] = float(end)
    return validated


def _seconds_to_frames(seconds: float, framerate: int) -> int:
    return max(0, int(round(seconds * framerate)))


def _frames_to_seconds(frame_count: int, framerate: int) -> float:
    return frame_count / float(framerate)


def _build_wav_params_dict(params: wave._wave_params) -> dict[str, Any]:
    return {
        "nchannels": params.nchannels,
        "sampwidth": params.sampwidth,
        "framerate": params.framerate,
        "comptype": params.comptype,
        "compname": params.compname,
    }


def _resolve_output_wav_params(job_dir, items: list[dict[str, Any]]) -> wave._wave_params:
    for item in items:
        if item["status"] not in {"generated", "reused"}:
            continue

        wav_file_path = job_dir / item["wav_path"]
        if not wav_file_path.exists():
            raise FileNotFoundError(f"Missing segment WAV file: {wav_file_path}")

        with wave.open(str(wav_file_path), "rb") as wav_reader:
            return wav_reader.getparams()

    raise DubAudioError("No generated or reused WAV items were found in tts_manifest.json.")


def _require_matching_params(
    expected: wave._wave_params | None,
    actual: wave._wave_params,
    wav_path: Path,
) -> wave._wave_params:
    if expected is None:
        return actual

    keys = ("nchannels", "sampwidth", "framerate", "comptype")
    mismatches = [
        f"{key}: expected={getattr(expected, key)!r} actual={getattr(actual, key)!r}"
        for key in keys
        if getattr(expected, key) != getattr(actual, key)
    ]
    if mismatches:
        raise DubAudioError(
            f"WAV parameters do not match for {wav_path}: " + ", ".join(mismatches)
        )
    return expected


def _make_silence(frame_count: int, params: wave._wave_params) -> bytes:
    frame_size = params.nchannels * params.sampwidth
    return b"\x00" * (frame_count * frame_size)


def _fade_out(data: bytes, frames: int, params: wave._wave_params) -> bytes:
    """Apply a short linear fade to clipped PCM without external dependencies."""
    fade_frames = min(frames, max(1, round(params.framerate * 0.03)))
    if fade_frames <= 0:
        return data
    result = bytearray(data)
    frame_size = params.nchannels * params.sampwidth
    first_frame = frames - fade_frames
    for frame in range(first_frame, frames):
        gain = (frames - frame - 1) / fade_frames
        for channel in range(params.nchannels):
            offset = frame * frame_size + channel * params.sampwidth
            raw = result[offset : offset + params.sampwidth]
            if params.sampwidth == 1:
                value = raw[0] - 128
                result[offset] = max(0, min(255, round(value * gain) + 128))
            else:
                value = int.from_bytes(raw, "little", signed=True)
                result[offset : offset + params.sampwidth] = round(value * gain).to_bytes(
                    params.sampwidth, "little", signed=True
                )
    return bytes(result)


def _build_warning(
    item: dict[str, Any],
    target_start_frames: int,
    actual_start_frames: int,
    original_end_frames: int,
    wav_frames: int,
    next_start_frames: int | None,
    framerate: int,
) -> dict[str, Any] | None:
    actual_end_frames = actual_start_frames + wav_frames
    original_duration_frames = max(0, original_end_frames - target_start_frames)
    overlaps_next = next_start_frames is not None and actual_end_frames > next_start_frames
    wav_exceeds_original_duration = wav_frames > original_duration_frames
    if not (overlaps_next and wav_exceeds_original_duration):
        return None

    warning: dict[str, Any] = {
        "index": item.get("index"),
        "segment_id": item.get("segment_id"),
        "target_start": _frames_to_seconds(target_start_frames, framerate),
        "actual_start": _frames_to_seconds(actual_start_frames, framerate),
        "original_end": _frames_to_seconds(original_end_frames, framerate),
        "wav_duration": _frames_to_seconds(wav_frames, framerate),
        "timing_delta": _frames_to_seconds(actual_end_frames - original_end_frames, framerate),
        "timing_status": "overlaps_next_segment",
    }
    if next_start_frames is not None:
        warning["next_target_start"] = _frames_to_seconds(next_start_frames, framerate)
    return warning


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = build_job_paths(args.output_dir, args.job_id)
    manifest_path = paths.resolve_tts_manifest_path()
    manifest = _load_tts_manifest(manifest_path)
    raw_items = manifest["items"]
    items = [_validate_item(item, index) for index, item in enumerate(raw_items, start=1)]

    job_dir = paths.job_dir
    output_wav_path = paths.dub_audio_wav_path
    output_manifest_path = paths.dub_audio_manifest_path
    paths.ensure_audio_dirs()

    wav_params = _resolve_output_wav_params(job_dir, items)
    output_frames = bytearray()
    processed_items: list[dict[str, Any]] = []
    warnings_count = 0

    for index, item in enumerate(items):
        status = item["status"]
        next_item = items[index + 1] if index + 1 < len(items) else None

        if status == "skipped_empty":
            if wav_params is None:
                raise DubAudioError(
                    "Cannot render skipped_empty segments before any WAV establishes output parameters."
                )

            processed_items.append(
                {
                    "index": item.get("index"),
                    "segment_id": item.get("segment_id"),
                    "status": status,
                    "target_start": item["start"],
                    "target_end": item["end"],
                    "source_start": item["start"],
                    "source_end": item["end"],
                    "actual_start": item["start"],
                    "actual_end": item["start"],
                    "actual_tts_duration": 0.0,
                    "end_delta": round(item["start"] - item["end"], 6),
                    "timing_status": "skipped_empty",
                    "clipped": False,
                    "warning": None,
                    **{
                        key: item.get(key)
                        for key in (
                            "available_duration", "raw_tts_duration", "final_tts_duration",
                            "duration_ratio", "speed_scale", "fit_status", "retry_count",
                            "translation_retry_required",
                        )
                        if key in item
                    },
                }
            )
            continue

        wav_relative_path = item["wav_path"]
        wav_file_path = job_dir / wav_relative_path
        if not wav_file_path.exists():
            raise FileNotFoundError(f"Missing segment WAV file: {wav_file_path}")

        with wave.open(str(wav_file_path), "rb") as wav_reader:
            current_params = wav_reader.getparams()
            wav_params = _require_matching_params(wav_params, current_params, wav_file_path)
            wav_frames = wav_reader.getnframes()
            wav_bytes = wav_reader.readframes(wav_frames)

        assert wav_params is not None
        target_start_frames = _seconds_to_frames(item["start"], wav_params.framerate)
        original_end_frames = _seconds_to_frames(item["end"], wav_params.framerate)
        next_start_frames = (
            _seconds_to_frames(next_item["start"], wav_params.framerate)
            if next_item is not None
            else None
        )

        actual_start_frames = target_start_frames
        hard_end_frames = original_end_frames
        if next_start_frames is not None:
            hard_end_frames = min(hard_end_frames, next_start_frames)
        allowed_frames = max(0, hard_end_frames - target_start_frames)
        written_frames = min(wav_frames, allowed_frames)
        clipped = written_frames < wav_frames
        if clipped:
            wav_bytes = _fade_out(
                wav_bytes[: written_frames * wav_params.nchannels * wav_params.sampwidth],
                written_frames,
                wav_params,
            )
            warnings_count += 1
        required_frames = target_start_frames + written_frames
        current_frames = len(output_frames) // (wav_params.nchannels * wav_params.sampwidth)
        if required_frames > current_frames:
            output_frames.extend(_make_silence(required_frames - current_frames, wav_params))
        byte_start = target_start_frames * wav_params.nchannels * wav_params.sampwidth
        output_frames[byte_start : byte_start + len(wav_bytes)] = wav_bytes
        overflow_frames = max(0, wav_frames - allowed_frames)
        timing_status = "overflow_clipped" if clipped else "ok"
        warning = None
        if clipped:
            warning = {
                "timing_status": timing_status,
                "overflow_seconds": _frames_to_seconds(overflow_frames, wav_params.framerate),
                "clipped": True,
            }

        processed_items.append(
            {
                "index": item.get("index"),
                "segment_id": item.get("segment_id"),
                "status": status,
                "wav_path": wav_relative_path,
                "target_start": item["start"],
                "target_end": item["end"],
                "source_start": item["start"],
                "source_end": item["end"],
                "actual_start": _frames_to_seconds(actual_start_frames, wav_params.framerate),
                "actual_end": _frames_to_seconds(
                    actual_start_frames + written_frames,
                    wav_params.framerate,
                ),
                "wav_duration": _frames_to_seconds(wav_frames, wav_params.framerate),
                "actual_tts_duration": _frames_to_seconds(written_frames, wav_params.framerate),
                "end_delta": _frames_to_seconds(
                    actual_start_frames + wav_frames - original_end_frames,
                    wav_params.framerate,
                ),
                "timing_status": timing_status,
                "overflow_seconds": _frames_to_seconds(overflow_frames, wav_params.framerate),
                "clipped": clipped,
                "warning": warning,
                # Preserve duration-fit diagnostics so a fallback clip is traceable.
                **{
                    key: item.get(key)
                    for key in (
                        "available_duration", "raw_tts_duration", "final_tts_duration",
                        "duration_ratio", "speed_scale", "fit_status", "retry_count",
                        "translation_retry_required",
                    )
                    if key in item
                },
            }
        )

    with wave.open(str(output_wav_path), "wb") as wav_writer:
        wav_writer.setparams(wav_params)
        wav_writer.writeframes(bytes(output_frames))

    output_manifest = {
        "job_id": args.job_id,
        "source_manifest": paths.rel_to_job(manifest_path),
        "output_wav": paths.rel_to_job(output_wav_path),
        "wav_params": _build_wav_params_dict(wav_params),
        "total_items": len(items),
        "processed_items": len(processed_items),
        "warnings_count": warnings_count,
        "items": processed_items,
    }
    output_manifest_path.write_text(
        json.dumps(output_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Built dub audio WAV: {output_wav_path}")
    print(f"Wrote manifest: {output_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
