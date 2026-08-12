#!/usr/bin/env python3
"""Generate Edge TTS WAV segments while preserving fixed-timeline semantics."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
import wave
from array import array
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from path_layout import build_job_paths
from providers.tts.edge import DEFAULT_VOICE, EdgeTTSError, EdgeTTSProvider, MAX_RATE_PERCENT


SILENCE_POLICY_VERSION = 1
SILENCE_THRESHOLD_DBFS = -50.0
SILENCE_MIN_SECONDS = 0.08
SILENCE_GUARD_SECONDS = 0.04


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate per-segment WAV files with Edge TTS.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    return parser


def _measure_wav(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as reader:
            sample_rate = reader.getframerate()
            if sample_rate <= 0:
                raise EdgeTTSError("Edge audio measurement failed.")
            return reader.getnframes() / float(sample_rate)
    except (wave.Error, EOFError, OSError) as exc:
        raise EdgeTTSError("Edge audio measurement failed.") from exc


def _convert_to_wav(source: Path, target: Path, ffmpeg_bin: str) -> None:
    try:
        subprocess.run([ffmpeg_bin, "-y", "-loglevel", "error", "-i", str(source),
                        "-ac", "1", "-ar", "24000", str(target)], check=True)
    except FileNotFoundError as exc:
        raise EdgeTTSError("ffmpeg was not found while normalizing Edge audio.") from exc
    except subprocess.CalledProcessError as exc:
        raise EdgeTTSError("Edge audio could not be normalized to WAV.") from exc


def _trim_edge_silence(path: Path) -> dict[str, float]:
    """Conservatively remove only sustained, very quiet PCM at WAV boundaries."""
    try:
        with wave.open(str(path), "rb") as reader:
            params = reader.getparams()
            frames = reader.readframes(params.nframes)
        if params.sampwidth != 2 or params.nchannels != 1 or params.framerate <= 0:
            raise EdgeTTSError("Edge WAV silence cleanup requires mono 16-bit PCM.")
        samples = array("h")
        samples.frombytes(frames)
        original_frames = len(samples)
        threshold = round(32767 * 10 ** (SILENCE_THRESHOLD_DBFS / 20))
        quiet = lambda value: abs(value) <= threshold
        leading = 0
        while leading < original_frames and quiet(samples[leading]):
            leading += 1
        trailing = original_frames
        while trailing > leading and quiet(samples[trailing - 1]):
            trailing -= 1
        minimum = round(params.framerate * SILENCE_MIN_SECONDS)
        guard = round(params.framerate * SILENCE_GUARD_SECONDS)
        remove_leading = max(0, leading - guard) if leading >= minimum else 0
        trailing_quiet = original_frames - trailing
        remove_trailing = max(0, trailing_quiet - guard) if trailing_quiet >= minimum else 0
        kept = samples[remove_leading : original_frames - remove_trailing]
        if remove_leading or remove_trailing:
            temporary = path.with_suffix(".trim.tmp.wav")
            with wave.open(str(temporary), "wb") as writer:
                writer.setparams(params)
                writer.writeframes(kept.tobytes())
            temporary.replace(path)
        return {
            "original_converted_duration": original_frames / params.framerate,
            "removed_leading_silence": remove_leading / params.framerate,
            "removed_trailing_silence": remove_trailing / params.framerate,
            "final_speech_duration": len(kept) / params.framerate,
        }
    except EdgeTTSError:
        raise
    except (wave.Error, EOFError, OSError) as exc:
        raise EdgeTTSError("Edge WAV silence cleanup failed.") from exc


def _cache_matches(manifest: dict, item: dict, segment: dict, voice: str, wav: Path) -> bool:
    return (
        manifest.get("tts_provider") == "edge" and manifest.get("voice") == voice
        and manifest.get("provider_settings", {}).get("max_rate_percent") == MAX_RATE_PERCENT
        and manifest.get("provider_settings", {}).get("silence_policy_version") == SILENCE_POLICY_VERSION
        and item.get("status") in {"generated", "reused"}
        and wav.exists()
        and all(item.get(key) == segment.get(key) for key in ("segment_id", "start", "end", "text"))
    )


def _target_chars(text: str, available: float, raw_duration: float) -> int:
    if not text or available <= 0 or raw_duration <= 0:
        return 0
    estimate = len(text) * available / raw_duration * 0.9
    return max(1, min(len(text) - 1, math.floor(estimate)))


def _write_retry_artifact(path: Path, items: list[dict]) -> None:
    rows = []
    for item in items:
        if item.get("fit_status") != "ng" or not item.get("translation_retry_required"):
            continue
        available = float(item["available_duration"])
        raw_duration = float(item["raw_tts_duration"])
        text = str(item.get("text", ""))
        rows.append({
            "segment_id": item["segment_id"], "start": item["start"], "end": item["end"],
            "duration": available, "current_text": text,
            "raw_tts_duration": raw_duration,
            "required_speed": round(raw_duration / available, 6) if available > 0 else None,
            "target_chars": _target_chars(text, available, raw_duration),
            "coalesced": bool(item.get("coalesced")),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")


def generate_job(*, job_id: str, output_dir: str | Path, voice: str = DEFAULT_VOICE,
                 ffmpeg_bin: str = "ffmpeg", resume: bool = False, force: bool = False,
                 workers: int = 4,
                 provider: EdgeTTSProvider | None = None,
                 converter=_convert_to_wav, measure=_measure_wav,
                 silence_handler=_trim_edge_silence) -> dict:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    paths = build_job_paths(output_dir, job_id)
    payload = json.loads(paths.resolve_translated_segments_json_path().read_text(encoding="utf-8"))
    segments = payload["segments"]
    unit_meta = {}
    normalized_path = paths.resolve_transcript_normalized_json_path()
    if normalized_path.exists():
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
        unit_meta = {unit.get("unit_id"): unit for unit in normalized.get("units", [])}
    paths.ensure_tts_dirs()
    old = {}
    if paths.tts_manifest_path.exists():
        old = json.loads(paths.tts_manifest_path.read_text(encoding="utf-8"))
    old_items = {item.get("segment_id"): item for item in old.get("items", [])}
    provider = provider or EdgeTTSProvider(voice)
    items = []
    with tempfile.TemporaryDirectory(prefix="yt_video_dub_edge_") as temporary:
        temp = Path(temporary)
        def generate_segment(index_and_segment):
            index, segment = index_and_segment
            wav = paths.tts_dir / f"segment_{index:06d}.wav"
            old_item = old_items.get(segment["segment_id"], {})
            if resume and not force and _cache_matches(old, old_item, segment, voice, wav):
                item = dict(old_item)
                item["status"] = "reused"
                return item
            available = float(segment["end"]) - float(segment["start"])
            coalesced = bool(unit_meta.get(segment["segment_id"], {}).get("coalesced"))
            if not segment["text"].strip():
                return {"index": index, **segment, "wav_path": None, "status": "skipped_empty",
                        "fit_status": "ok", "translation_retry_required": False,
                        "coalesced": coalesced}
            native = temp / f"{index:06d}.mp3"
            try:
                provider.synthesize(segment["text"], native, rate_percent=0)
                converter(native, wav, ffmpeg_bin)
                silence = silence_handler(wav)
                raw_duration = float(silence["final_speech_duration"])
                # Measure the actual cleaned artifact, not a parallel estimate.
                final_duration = measure(wav)
                if abs(final_duration - raw_duration) > 1e-4:
                    raise EdgeTTSError("Edge WAV cleanup duration is inconsistent.")
                rate_percent = 0
                retry_count = 0
                if available > 0 and 1.0 < raw_duration / available <= 1.15:
                    rate_percent = min(MAX_RATE_PERCENT,
                                       max(1, math.ceil((raw_duration / available - 1.0) * 100)))
                    provider.synthesize(segment["text"], native, rate_percent=rate_percent)
                    converter(native, wav, ffmpeg_bin)
                    silence = silence_handler(wav)
                    final_duration = measure(wav)
                    if abs(final_duration - float(silence["final_speech_duration"])) > 1e-4:
                        raise EdgeTTSError("Edge WAV cleanup duration is inconsistent.")
                    retry_count = 1
            except (EdgeTTSError, OSError, EOFError, wave.Error,
                    subprocess.CalledProcessError) as exc:
                wav.unlink(missing_ok=True)
                message = str(exc) if isinstance(exc, EdgeTTSError) else "Edge audio processing failed."
                return {
                    "index": index, **segment, "wav_path": None, "status": "failed",
                    "tts_provider": "edge", "voice": voice, "fit_status": None,
                    "translation_retry_required": False, "error_type": type(exc).__name__,
                    "error_message": message, "coalesced": coalesced,
                }
            fit_status = ("ok" if final_duration <= available and retry_count == 0 else
                          "fitted" if final_duration <= available else "ng")
            return {
                "index": index, **segment, "wav_path": paths.rel_to_job(wav), "status": "generated",
                "tts_provider": "edge", "voice": voice, "rate": f"+{rate_percent}%",
                "coalesced": coalesced,
                "available_duration": round(available, 6),
                "raw_tts_duration": round(raw_duration, 6),
                "final_tts_duration": round(final_duration, 6), "retry_count": retry_count,
                **{key: round(float(silence[key]), 6) for key in (
                    "original_converted_duration", "removed_leading_silence",
                    "removed_trailing_silence", "final_speech_duration")},
                "duration_ratio": round(final_duration / available, 6) if available > 0 else None,
                "speed_scale": round(1.0 + rate_percent / 100.0, 6),
                "fit_status": fit_status, "translation_retry_required": fit_status == "ng",
            }
        with ThreadPoolExecutor(max_workers=workers) as executor:
            items = list(executor.map(generate_segment, enumerate(segments, start=1)))
    generated = sum(item.get("status") == "generated" for item in items)
    reused = sum(item.get("status") == "reused" for item in items)
    skipped_empty = sum(item.get("status") == "skipped_empty" for item in items)
    failed = sum(item.get("status") == "failed" for item in items)
    fitted_items = [item for item in items if item.get("status") in {"generated", "reused"}]
    fit_counts = {
        "fit_ok_count": sum(item.get("fit_status") == "ok" for item in fitted_items),
        "fit_fitted_count": sum(item.get("fit_status") == "fitted" for item in fitted_items),
        "fit_ng_count": sum(item.get("fit_status") == "ng" for item in fitted_items),
    }
    manifest = {"job_id": job_id, "tts_provider": "edge", "voice": voice,
                "provider_settings": {"max_rate_percent": MAX_RATE_PERCENT,
                                      "silence_policy_version": SILENCE_POLICY_VERSION,
                                      "silence_threshold_dbfs": SILENCE_THRESHOLD_DBFS,
                                      "silence_min_seconds": SILENCE_MIN_SECONDS,
                                      "silence_guard_seconds": SILENCE_GUARD_SECONDS},
                "total_segments": len(segments),
                "run_metrics": {"selected_units": len(segments), "generated_units": generated,
                                "reused_units": reused, "skipped_empty_units": skipped_empty,
                                "failed_units": failed, **fit_counts}, "items": items}
    paths.tts_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    _write_retry_artifact(paths.duration_retry_required_path, items)
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = generate_job(job_id=args.job_id, output_dir=args.output_dir, voice=args.voice,
                            ffmpeg_bin=args.ffmpeg_bin, resume=args.resume, force=args.force,
                            workers=args.workers)
    print(f"Generated Edge TTS segments for job: {args.job_id}")
    return 1 if manifest["run_metrics"]["failed_units"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
