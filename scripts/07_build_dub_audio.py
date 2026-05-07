#!/usr/bin/env python3
"""Build a single dub audio WAV from per-segment TTS WAV files."""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path
from typing import Any


class DubAudioError(RuntimeError):
    """Raised when dub-audio assembly fails."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build dub_audio.wav from output/<job_id>/tts/tts_manifest.json."
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


def _load_tts_manifest(job_dir: Path) -> dict[str, Any]:
    manifest_path = job_dir / "tts" / "tts_manifest.json"
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


def _resolve_output_wav_params(job_dir: Path, items: list[dict[str, Any]]) -> wave._wave_params:
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

    job_dir = Path(args.output_dir) / args.job_id
    manifest = _load_tts_manifest(job_dir)
    raw_items = manifest["items"]
    items = [_validate_item(item, index) for index, item in enumerate(raw_items, start=1)]

    output_wav_path = job_dir / "dub_audio.wav"
    output_manifest_path = job_dir / "dub_audio_manifest.json"

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

            current_frame_count = len(output_frames) // (wav_params.nchannels * wav_params.sampwidth)
            target_end_frames = _seconds_to_frames(item["end"], wav_params.framerate)
            added_silence_frames = max(0, target_end_frames - current_frame_count)
            if added_silence_frames:
                output_frames.extend(_make_silence(added_silence_frames, wav_params))

            processed_items.append(
                {
                    "index": item.get("index"),
                    "segment_id": item.get("segment_id"),
                    "status": status,
                    "target_start": item["start"],
                    "target_end": item["end"],
                    "actual_start": _frames_to_seconds(current_frame_count, wav_params.framerate),
                    "actual_end": _frames_to_seconds(
                        current_frame_count + added_silence_frames,
                        wav_params.framerate,
                    ),
                    "silence_inserted": _frames_to_seconds(
                        added_silence_frames,
                        wav_params.framerate,
                    ),
                    "warning": None,
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
        current_frame_count = len(output_frames) // (wav_params.nchannels * wav_params.sampwidth)
        target_start_frames = _seconds_to_frames(item["start"], wav_params.framerate)
        original_end_frames = _seconds_to_frames(item["end"], wav_params.framerate)
        next_start_frames = (
            _seconds_to_frames(next_item["start"], wav_params.framerate)
            if next_item is not None
            else None
        )

        silence_frames = max(0, target_start_frames - current_frame_count)
        if silence_frames:
            output_frames.extend(_make_silence(silence_frames, wav_params))
            current_frame_count += silence_frames

        actual_start_frames = current_frame_count
        output_frames.extend(wav_bytes)
        warning = _build_warning(
            item=item,
            target_start_frames=target_start_frames,
            actual_start_frames=actual_start_frames,
            original_end_frames=original_end_frames,
            wav_frames=wav_frames,
            next_start_frames=next_start_frames,
            framerate=wav_params.framerate,
        )
        if warning is not None:
            warnings_count += 1

        processed_items.append(
            {
                "index": item.get("index"),
                "segment_id": item.get("segment_id"),
                "status": status,
                "wav_path": wav_relative_path,
                "target_start": item["start"],
                "target_end": item["end"],
                "actual_start": _frames_to_seconds(actual_start_frames, wav_params.framerate),
                "actual_end": _frames_to_seconds(
                    actual_start_frames + wav_frames,
                    wav_params.framerate,
                ),
                "wav_duration": _frames_to_seconds(wav_frames, wav_params.framerate),
                "silence_inserted": _frames_to_seconds(silence_frames, wav_params.framerate),
                "warning": warning,
            }
        )

    with wave.open(str(output_wav_path), "wb") as wav_writer:
        wav_writer.setparams(wav_params)
        wav_writer.writeframes(bytes(output_frames))

    output_manifest = {
        "job_id": args.job_id,
        "source_manifest": "tts/tts_manifest.json",
        "output_wav": "dub_audio.wav",
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
