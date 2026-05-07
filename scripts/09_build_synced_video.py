#!/usr/bin/env python3
"""Build a per-segment synced dubbed video from source.mp4 and TTS WAV files."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from path_layout import build_job_paths


class SyncedVideoError(RuntimeError):
    """Raised when synced video building fails."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build dubbed_video_synced.mp4 with per-segment audio/video timing sync."
    )
    parser.add_argument("--job-id", required=True, help="Job identifier under output/<job_id>/.")
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Base output directory. Default: output",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default="ffmpeg",
        help='ffmpeg binary name or path. Default: "ffmpeg"',
    )
    parser.add_argument(
        "--ffprobe-bin",
        default="ffprobe",
        help='ffprobe binary name or path. Default: "ffprobe"',
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N segments for test runs.",
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
        "--keep-temp",
        action="store_true",
        help="Keep concat list and other temporary text artifacts.",
    )
    parser.add_argument(
        "--max-audio-speed",
        type=float,
        default=1.25,
        help="Maximum allowed audio speed-up factor. Default: 1.25",
    )
    parser.add_argument(
        "--video-tail-cushion-ratio",
        type=float,
        default=0.01,
        help="Extra duration ratio for slowed video segments. Default: 0.01",
    )
    parser.add_argument(
        "--video-tail-cushion-max-sec",
        type=float,
        default=0.12,
        help="Maximum extra duration for slowed video segments. Default: 0.12",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="libx264 CRF value. Default: 23",
    )
    parser.add_argument(
        "--preset",
        default="veryfast",
        help='libx264 preset. Default: "veryfast"',
    )
    return parser


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if not path.is_file():
        raise SyncedVideoError(f"Expected {label} to be a file: {path}")


def _run_command(command: list[str]) -> None:
    print(shlex.join(command))
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise SyncedVideoError(f"Command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise SyncedVideoError(
            f"Command failed with exit code {exc.returncode}: {shlex.join(command)}"
        ) from exc


def _probe_duration_seconds(ffprobe_bin: str, path: Path) -> float:
    command = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SyncedVideoError(f"ffprobe not found: {ffprobe_bin}") from exc
    except subprocess.CalledProcessError as exc:
        raise SyncedVideoError(
            f"ffprobe failed with exit code {exc.returncode}: {shlex.join(command)}"
        ) from exc

    output = completed.stdout.strip()
    if not output:
        raise SyncedVideoError(f"ffprobe returned an empty duration for: {path}")

    try:
        return float(output)
    except ValueError as exc:
        raise SyncedVideoError(f"Invalid ffprobe duration for {path}: {output!r}") from exc


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    _require_file(path, label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncedVideoError(f"Invalid JSON in {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise SyncedVideoError(f"{label} must contain a JSON object: {path}")
    return payload


def _load_translated_segments(translated_segments_path: Path) -> list[dict[str, Any]]:
    payload = _load_json_object(translated_segments_path, "translated segments file")
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise SyncedVideoError(f"{translated_segments_path.name} is missing a segments list.")

    validated: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise SyncedVideoError(f"Segment {index} in translated_segments.json is not an object.")
        segment_id = segment.get("segment_id")
        start = segment.get("start")
        end = segment.get("end")
        text = segment.get("text")
        if not isinstance(segment_id, str) or not segment_id:
            raise SyncedVideoError(f"Segment {index} is missing a valid segment_id.")
        if not isinstance(start, (int, float)):
            raise SyncedVideoError(f"Segment {index} has an invalid start.")
        if not isinstance(end, (int, float)):
            raise SyncedVideoError(f"Segment {index} has an invalid end.")
        if not isinstance(text, str):
            raise SyncedVideoError(f"Segment {index} has an invalid text.")
        validated.append(
            {
                "index": index,
                "segment_id": segment_id,
                "start": float(start),
                "end": float(end),
                "text": text,
            }
        )
    return validated


def _load_tts_manifest_items(tts_manifest_path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json_object(tts_manifest_path, "TTS manifest file")
    items = payload.get("items")
    if not isinstance(items, list):
        raise SyncedVideoError("tts_manifest.json is missing an items list.")

    manifest_by_segment_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise SyncedVideoError(f"TTS manifest item {index} is not an object.")
        segment_id = item.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id:
            raise SyncedVideoError(f"TTS manifest item {index} is missing a valid segment_id.")
        manifest_by_segment_id[segment_id] = item
    return manifest_by_segment_id


def _build_segment_records(
    segments: list[dict[str, Any]],
    tts_items_by_segment_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for segment in segments:
        tts_item = tts_items_by_segment_id.get(segment["segment_id"])
        if tts_item is None:
            raise SyncedVideoError(
                f"Missing TTS manifest item for segment_id={segment['segment_id']}."
            )
        status = tts_item.get("status")
        wav_path = tts_item.get("wav_path")
        if not isinstance(status, str):
            raise SyncedVideoError(
                f"TTS manifest item for segment_id={segment['segment_id']} has invalid status."
            )
        if wav_path is not None and not isinstance(wav_path, str):
            raise SyncedVideoError(
                f"TTS manifest item for segment_id={segment['segment_id']} has invalid wav_path."
            )
        records.append(
            {
                "index": segment["index"],
                "segment_id": segment["segment_id"],
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"],
                "status": status,
                "wav_path": wav_path,
            }
        )
    return records


def _select_records(
    records: list[dict[str, Any]],
    start_index: int | None,
    end_index: int | None,
    limit: int | None,
) -> tuple[list[dict[str, Any]], bool]:
    has_range = start_index is not None or end_index is not None
    selected = records
    if has_range:
        start = start_index if start_index is not None else 1
        end = end_index if end_index is not None else len(records)
        selected = [
            record
            for record in records
            if start <= int(record["index"]) <= end
        ]

    if limit is not None:
        selected = selected[:limit]

    return selected, has_range


def _ensure_positive_duration(value: float, label: str) -> None:
    if value <= 0:
        raise SyncedVideoError(f"{label} must be greater than zero. Got: {value}")


def _ffmpeg_make_silence(
    ffmpeg_bin: str,
    output_path: Path,
    duration: float,
) -> None:
    command = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=24000:cl=mono",
        "-t",
        f"{duration:.6f}",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    _run_command(command)


def _ffmpeg_adjust_audio(
    ffmpeg_bin: str,
    input_wav_path: Path,
    output_wav_path: Path,
    audio_speed: float | None,
    target_duration: float,
) -> None:
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_wav_path),
    ]
    if audio_speed is None:
        audio_filter = f"apad=whole_dur={target_duration:.6f}"
    else:
        audio_filter = f"atempo={audio_speed:.6f},apad=whole_dur={target_duration:.6f}"
    command.extend(
        [
            "-af",
            audio_filter,
            "-t",
            f"{target_duration:.6f}",
            "-c:a",
            "pcm_s16le",
            str(output_wav_path),
        ]
    )
    _run_command(command)


def _ffmpeg_build_segment_video(
    ffmpeg_bin: str,
    source_video_path: Path,
    adjusted_audio_path: Path,
    output_segment_path: Path,
    source_start: float,
    source_duration: float,
    target_duration: float,
    video_speed: float,
    crf: int,
    preset: str,
) -> None:
    filter_complex = (
        f"[0:v]trim=start={source_start:.6f}:duration={source_duration:.6f},"
        f"setpts=(PTS-STARTPTS)/{video_speed:.12f}[v]"
    )
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(source_video_path),
        "-i",
        str(adjusted_audio_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        "-t",
        f"{target_duration:.6f}",
        str(output_segment_path),
    ]
    _run_command(command)


def _write_concat_list(concat_list_path: Path, segment_paths: list[Path]) -> None:
    lines = [f"file '{path.resolve().as_posix()}'" for path in segment_paths]
    concat_list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ffmpeg_concat_segments(
    ffmpeg_bin: str,
    concat_list_path: Path,
    output_video_path: Path,
    crf: int,
    preset: str,
) -> None:
    command = [
        ffmpeg_bin,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_video_path),
    ]
    _run_command(command)


def _relpath(path: Path, start: Path) -> str:
    return str(path.resolve().relative_to(start.resolve()))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.max_audio_speed <= 0:
        raise SyncedVideoError("--max-audio-speed must be greater than zero.")
    if args.limit is not None and args.limit <= 0:
        raise SyncedVideoError("--limit must be greater than zero when provided.")
    if args.start_index is not None and args.start_index <= 0:
        raise SyncedVideoError("--start-index must be a positive integer.")
    if args.end_index is not None and args.end_index <= 0:
        raise SyncedVideoError("--end-index must be a positive integer.")
    if (
        args.start_index is not None
        and args.end_index is not None
        and args.start_index > args.end_index
    ):
        raise SyncedVideoError("--start-index must be less than or equal to --end-index.")
    if args.video_tail_cushion_ratio < 0:
        raise SyncedVideoError("--video-tail-cushion-ratio must be zero or greater.")
    if args.video_tail_cushion_max_sec < 0:
        raise SyncedVideoError("--video-tail-cushion-max-sec must be zero or greater.")

    paths = build_job_paths(args.output_dir, args.job_id)
    job_dir = paths.job_dir
    source_video_path = paths.resolve_source_video_path()
    synced_dir = paths.synced_segments_dir
    manifest_path = paths.synced_video_manifest_path
    output_video_path = paths.dubbed_video_synced_path
    concat_list_path = synced_dir / "concat_segments.txt"

    _require_file(source_video_path, "source video")

    segments = _load_translated_segments(paths.resolve_translated_segments_json_path())
    tts_items_by_segment_id = _load_tts_manifest_items(paths.resolve_tts_manifest_path())
    records = _build_segment_records(segments, tts_items_by_segment_id)
    records, _ = _select_records(
        records=records,
        start_index=args.start_index,
        end_index=args.end_index,
        limit=args.limit,
    )

    if not records:
        raise SyncedVideoError("No segments matched the requested range.")

    paths.ensure_synced_video_dirs()

    manifest_items: list[dict[str, Any]] = []
    output_segment_paths: list[Path] = []

    for record in records:
        source_duration = float(record["end"]) - float(record["start"])
        _ensure_positive_duration(source_duration, f"source duration for {record['segment_id']}")

        index = int(record["index"])
        segment_id = str(record["segment_id"])
        text = str(record["text"])
        status = str(record["status"])
        wav_rel = record["wav_path"]

        adjusted_audio_path = synced_dir / f"segment_{index:06d}_adjusted.wav"
        output_segment_path = synced_dir / f"segment_{index:06d}.mp4"

        original_wav_duration = 0.0
        original_wav_path: str | None = None
        required_audio_speed = 1.0
        applied_audio_speed = 1.0
        video_speed = 1.0
        target_duration = source_duration
        adjustment = ""
        adjusted_audio_duration_before_padding = source_duration
        video_tail_cushion_sec = 0.0
        warning: str | None = None

        is_skipped_empty = status == "skipped_empty" or text.strip() == ""
        if is_skipped_empty:
            adjustment = "skipped_empty"
            adjusted_audio_duration_before_padding = 0.0
            _ffmpeg_make_silence(args.ffmpeg_bin, adjusted_audio_path, source_duration)
        else:
            if not isinstance(wav_rel, str) or not wav_rel:
                raise SyncedVideoError(
                    f"Segment {segment_id} requires a WAV path but none was provided."
                )
            input_wav_path = job_dir / wav_rel
            _require_file(input_wav_path, f"TTS WAV for {segment_id}")

            original_wav_path = wav_rel
            original_wav_duration = _probe_duration_seconds(args.ffprobe_bin, input_wav_path)
            _ensure_positive_duration(
                original_wav_duration,
                f"original WAV duration for {segment_id}",
            )

            if original_wav_duration <= source_duration:
                adjustment = "padded_audio"
                adjusted_audio_duration_before_padding = original_wav_duration
                _ffmpeg_adjust_audio(
                    args.ffmpeg_bin,
                    input_wav_path,
                    adjusted_audio_path,
                    audio_speed=None,
                    target_duration=source_duration,
                )
            else:
                required_audio_speed = original_wav_duration / source_duration
                if required_audio_speed <= args.max_audio_speed:
                    adjustment = "sped_audio"
                    applied_audio_speed = required_audio_speed
                    adjusted_audio_duration_before_padding = (
                        original_wav_duration / applied_audio_speed
                    )
                    _ffmpeg_adjust_audio(
                        args.ffmpeg_bin,
                        input_wav_path,
                        adjusted_audio_path,
                        audio_speed=applied_audio_speed,
                        target_duration=source_duration,
                    )
                else:
                    adjustment = "sped_audio_and_slowed_video"
                    applied_audio_speed = args.max_audio_speed
                    adjusted_audio_duration_before_padding = (
                        original_wav_duration / applied_audio_speed
                    )
                    video_tail_cushion_sec = min(
                        adjusted_audio_duration_before_padding * args.video_tail_cushion_ratio,
                        args.video_tail_cushion_max_sec,
                    )
                    target_duration = (
                        adjusted_audio_duration_before_padding + video_tail_cushion_sec
                    )
                    video_speed = source_duration / target_duration
                    _ensure_positive_duration(video_speed, f"video speed for {segment_id}")
                    _ffmpeg_adjust_audio(
                        args.ffmpeg_bin,
                        input_wav_path,
                        adjusted_audio_path,
                        audio_speed=applied_audio_speed,
                        target_duration=target_duration,
                    )
                    warning = (
                        f"Audio exceeded source duration and required video slowdown after "
                        f"reaching max audio speed {args.max_audio_speed:.2f}."
                    )

        adjusted_audio_duration = _probe_duration_seconds(args.ffprobe_bin, adjusted_audio_path)
        if adjustment in {"padded_audio", "sped_audio", "skipped_empty"}:
            target_duration = source_duration
            video_speed = 1.0

        _ffmpeg_build_segment_video(
            args.ffmpeg_bin,
            source_video_path,
            adjusted_audio_path,
            output_segment_path,
            source_start=float(record["start"]),
            source_duration=source_duration,
            target_duration=target_duration,
            video_speed=video_speed,
            crf=args.crf,
            preset=args.preset,
        )
        final_segment_duration = _probe_duration_seconds(args.ffprobe_bin, output_segment_path)

        manifest_items.append(
            {
                "index": index,
                "segment_id": segment_id,
                "source_start": float(record["start"]),
                "source_end": float(record["end"]),
                "source_duration": source_duration,
                "original_wav_path": original_wav_path,
                "original_wav_duration": original_wav_duration,
                "adjusted_audio_path": _relpath(adjusted_audio_path, job_dir),
                "adjusted_audio_duration": adjusted_audio_duration,
                "adjusted_audio_duration_before_padding": adjusted_audio_duration_before_padding,
                "final_audio_duration": adjusted_audio_duration,
                "output_segment_path": _relpath(output_segment_path, job_dir),
                "required_audio_speed": required_audio_speed,
                "applied_audio_speed": applied_audio_speed,
                "video_speed": video_speed,
                "target_duration": target_duration,
                "video_tail_cushion_ratio": args.video_tail_cushion_ratio,
                "video_tail_cushion_sec": video_tail_cushion_sec,
                "final_segment_duration": final_segment_duration,
                "accurate_seek": True,
                "adjustment": adjustment,
                "warning": warning,
            }
        )
        output_segment_paths.append(output_segment_path)

    _write_concat_list(concat_list_path, output_segment_paths)
    _ffmpeg_concat_segments(
        args.ffmpeg_bin,
        concat_list_path,
        output_video_path,
        crf=args.crf,
        preset=args.preset,
    )

    manifest_payload = {
        "job_id": args.job_id,
        "max_audio_speed": args.max_audio_speed,
        "video_tail_cushion_ratio": args.video_tail_cushion_ratio,
        "video_tail_cushion_max_sec": args.video_tail_cushion_max_sec,
        "output_video": _relpath(output_video_path, job_dir),
        "total_items": len(segments),
        "processed_items": len(manifest_items),
        "items": manifest_items,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not args.keep_temp and concat_list_path.exists():
        concat_list_path.unlink()
    print(f"Created synced dubbed video: {output_video_path}")
    print(f"Created synced manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
