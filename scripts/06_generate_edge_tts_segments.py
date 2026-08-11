#!/usr/bin/env python3
"""Generate Edge TTS WAV segments while preserving fixed-timeline semantics."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
import wave
from pathlib import Path

from path_layout import build_job_paths
from providers.tts.edge import DEFAULT_VOICE, EdgeTTSError, EdgeTTSProvider, MAX_RATE_PERCENT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate per-segment WAV files with Edge TTS.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def _measure_wav(path: Path) -> float:
    with wave.open(str(path), "rb") as reader:
        return reader.getnframes() / float(reader.getframerate())


def _convert_to_wav(source: Path, target: Path, ffmpeg_bin: str) -> None:
    try:
        subprocess.run([ffmpeg_bin, "-y", "-loglevel", "error", "-i", str(source),
                        "-ac", "1", "-ar", "24000", str(target)], check=True)
    except FileNotFoundError as exc:
        raise EdgeTTSError("ffmpeg was not found while normalizing Edge audio.") from exc
    except subprocess.CalledProcessError as exc:
        raise EdgeTTSError("Edge audio could not be normalized to WAV.") from exc


def _cache_matches(manifest: dict, item: dict, segment: dict, voice: str, wav: Path) -> bool:
    return (
        manifest.get("tts_provider") == "edge" and manifest.get("voice") == voice
        and wav.exists()
        and all(item.get(key) == segment.get(key) for key in ("segment_id", "start", "end", "text"))
    )


def generate_job(*, job_id: str, output_dir: str | Path, voice: str = DEFAULT_VOICE,
                 ffmpeg_bin: str = "ffmpeg", resume: bool = False, force: bool = False,
                 provider: EdgeTTSProvider | None = None,
                 converter=_convert_to_wav, measure=_measure_wav) -> dict:
    paths = build_job_paths(output_dir, job_id)
    payload = json.loads(paths.resolve_translated_segments_json_path().read_text(encoding="utf-8"))
    segments = payload["segments"]
    paths.ensure_tts_dirs()
    old = {}
    if paths.tts_manifest_path.exists():
        old = json.loads(paths.tts_manifest_path.read_text(encoding="utf-8"))
    old_items = {item.get("segment_id"): item for item in old.get("items", [])}
    provider = provider or EdgeTTSProvider(voice)
    items = []
    generated = reused = 0
    with tempfile.TemporaryDirectory(prefix="yt_video_dub_edge_") as temporary:
        temp = Path(temporary)
        for index, segment in enumerate(segments, start=1):
            wav = paths.tts_dir / f"segment_{index:06d}.wav"
            old_item = old_items.get(segment["segment_id"], {})
            if resume and not force and _cache_matches(old, old_item, segment, voice, wav):
                item = dict(old_item)
                item["status"] = "reused"
                items.append(item)
                reused += 1
                continue
            available = float(segment["end"]) - float(segment["start"])
            if not segment["text"].strip():
                items.append({"index": index, **segment, "wav_path": None, "status": "skipped_empty",
                              "fit_status": "ok", "translation_retry_required": False})
                continue
            native = temp / f"{index:06d}.mp3"
            provider.synthesize(segment["text"], native, rate_percent=0)
            converter(native, wav, ffmpeg_bin)
            raw_duration = measure(wav)
            final_duration = raw_duration
            rate_percent = 0
            retry_count = 0
            if available > 0 and 1.0 < raw_duration / available <= 1.15:
                rate_percent = min(MAX_RATE_PERCENT,
                                   max(1, math.ceil((raw_duration / available - 1.0) * 100)))
                provider.synthesize(segment["text"], native, rate_percent=rate_percent)
                converter(native, wav, ffmpeg_bin)
                final_duration = measure(wav)
                retry_count = 1
            fit_status = ("ok" if final_duration <= available and retry_count == 0 else
                          "fitted" if final_duration <= available else "ng")
            items.append({
                "index": index, **segment, "wav_path": paths.rel_to_job(wav), "status": "generated",
                "tts_provider": "edge", "voice": voice, "rate": f"+{rate_percent}%",
                "available_duration": round(available, 6),
                "raw_tts_duration": round(raw_duration, 6),
                "final_tts_duration": round(final_duration, 6), "retry_count": retry_count,
                "duration_ratio": round(final_duration / available, 6) if available > 0 else None,
                "speed_scale": round(1.0 + rate_percent / 100.0, 6),
                "fit_status": fit_status, "translation_retry_required": fit_status == "ng",
            })
            generated += 1
    manifest = {"job_id": job_id, "tts_provider": "edge", "voice": voice,
                "provider_settings": {"max_rate_percent": MAX_RATE_PERCENT},
                "total_segments": len(segments),
                "run_metrics": {"selected_units": len(segments), "generated_units": generated,
                                "reused_units": reused}, "items": items}
    paths.tts_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    generate_job(job_id=args.job_id, output_dir=args.output_dir, voice=args.voice,
                 ffmpeg_bin=args.ffmpeg_bin, resume=args.resume, force=args.force)
    print(f"Generated Edge TTS segments for job: {args.job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
