#!/usr/bin/env python3
"""Prepare a job workspace and register source input."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from path_layout import build_job_paths


@dataclass(frozen=True)
class AcquisitionStrategy:
    name: str
    fallback: bool
    youtube_dl_options: dict


PRIMARY_STRATEGY = AcquisitionStrategy(
    "yt-dlp-default", False, {"format": "bestvideo*+bestaudio/best"}
)
# A deliberately single, logged-out fallback. Keep this easy to update as yt-dlp evolves.
YOUTUBE_FALLBACK_STRATEGY = AcquisitionStrategy(
    "youtube-android-vr", True,
    {"format": "bestvideo*+bestaudio/best", "extractor_args": {"youtube": {"player_client": ["android_vr"]}}},
)
ACQUISITION_STRATEGIES = (PRIMARY_STRATEGY, YOUTUBE_FALLBACK_STRATEGY)


def _safe_error(error: object) -> str:
    text = re.sub(r"https?://\S+", "[URL REDACTED]", str(error))
    text = re.sub(
        r"(?i)(cookie|authorization|token|visitor[_-]?data|api[_-]?key)\s*[:=]\s*\S+",
        r"\1=[REDACTED]", text,
    )
    text = " ".join(text.split())
    return text[:500] + ("…" if len(text) > 500 else "")


class SourceAcquisitionError(RuntimeError):
    """A concise, classified source acquisition failure suitable for diagnostics."""

    def __init__(self, stage: str, message: object, *, strategy: str | None = None,
                 http_403: bool = False, attempted: list[str] | None = None,
                 source_reused: bool = False, failures: list[str] | None = None):
        self.stage, self.strategy, self.http_403 = stage, strategy, http_403
        self.attempted, self.source_reused = list(attempted or []), source_reused
        self.failures = list(failures or [])
        self.concise_error = _safe_error(message)
        next_action = (
            "Try a newer/current yt-dlp setup; PO-token-capable configuration or authenticated "
            "access may be required for this video (manual optional actions)."
            if http_403 else "Check the URL, available disk space, and the concise error above."
        )
        details = [f"source acquisition {stage} failure"]
        if strategy:
            details.append(f"failed_strategy={strategy}")
        details.extend((f"attempted_strategies={','.join(self.attempted) or 'none'}",
                        f"strategy_failures={','.join(self.failures) or 'none'}",
                        f"http_403={str(http_403).lower()}",
                        f"source_reused={str(source_reused).lower()}",
                        f"error={self.concise_error}", f"next_action={next_action}"))
        super().__init__("; ".join(details))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare source assets for a dubbing job.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--youtube-url", help="YouTube URL to prepare as the source input.")
    source_group.add_argument("--local-video", help="Local video file to copy into the job.")
    parser.add_argument("--job-id", help="Job identifier. Default: YouTube video ID")
    parser.add_argument("--output-dir", default="output", help="Base output directory.")
    return parser


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _extract_youtube_metadata(youtube_url: str) -> dict:
    try:
        with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
    except Exception as exc:
        raise SourceAcquisitionError("metadata", exc) from exc
    if not info or not info.get("id"):
        raise SourceAcquisitionError("metadata", "yt-dlp returned no video ID")
    return info


def _cleanup_strategy_files(source_dir: Path, prefix: str) -> None:
    for path in source_dir.glob(f"{prefix}*"):
        if path.is_file():
            path.unlink()


def _download_with_strategy(youtube_url: str, source_dir: Path,
                            strategy: AcquisitionStrategy) -> Path:
    prefix = f".acquire-{strategy.name}"
    _cleanup_strategy_files(source_dir, prefix)
    options = {
        "quiet": True, "no_warnings": True,
        "merge_output_format": "mp4",
        "outtmpl": str(source_dir / f"{prefix}.%(ext)s"),
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        **strategy.youtube_dl_options,
    }
    try:
        with YoutubeDL(options) as ydl:
            ydl.extract_info(youtube_url, download=True)
    except DownloadError as exc:
        _cleanup_strategy_files(source_dir, prefix)
        forbidden = bool(re.search(r"(?:HTTP Error\s*)?403|forbidden", str(exc), re.I))
        raise SourceAcquisitionError("download", exc, strategy=strategy.name,
                                     http_403=forbidden) from exc
    except (OSError, RuntimeError) as exc:
        _cleanup_strategy_files(source_dir, prefix)
        raise SourceAcquisitionError("download", exc, strategy=strategy.name) from exc

    try:
        candidates = [p for p in source_dir.glob(f"{prefix}*")
                      if p.is_file() and p.stat().st_size]
    except OSError as exc:
        _cleanup_strategy_files(source_dir, prefix)
        raise SourceAcquisitionError("normalization", exc, strategy=strategy.name) from exc
    mp4 = next((p for p in candidates if p.suffix.lower() == ".mp4"), None)
    if mp4 is None:
        _cleanup_strategy_files(source_dir, prefix)
        raise SourceAcquisitionError("normalization", "yt-dlp did not produce a non-empty mp4",
                                     strategy=strategy.name)
    target = source_dir / "source.mp4"
    try:
        mp4.replace(target)
        _cleanup_strategy_files(source_dir, prefix)
    except OSError as exc:
        _cleanup_strategy_files(source_dir, prefix)
        raise SourceAcquisitionError("normalization", exc, strategy=strategy.name) from exc
    return target


def _acquire_youtube_source(youtube_url: str, source_dir: Path) -> tuple[Path, dict]:
    canonical = source_dir / "source.mp4"
    if canonical.is_file() and canonical.stat().st_size > 0:
        return canonical, {"source_reused": True, "attempted_strategies": []}
    attempted: list[str] = []
    failures: list[str] = []
    any_http_403 = False
    for strategy in ACQUISITION_STRATEGIES:
        attempted.append(strategy.name)
        try:
            source = _download_with_strategy(youtube_url, source_dir, strategy)
            return source, {"source_reused": False, "attempted_strategies": attempted,
                            "strategy_failures": failures,
                            "successful_strategy": strategy.name}
        except SourceAcquisitionError as exc:
            exc.attempted = attempted.copy()
            any_http_403 = any_http_403 or exc.http_403
            failures.append(f"{strategy.name}:{exc.stage}:http_403={str(exc.http_403).lower()}")
            # Only a 403 from the primary download permits the one fallback.
            if strategy is PRIMARY_STRATEGY and exc.stage == "download" and exc.http_403:
                continue
            raise SourceAcquisitionError(exc.stage, exc.concise_error, strategy=exc.strategy,
                                         http_403=any_http_403, attempted=attempted,
                                         failures=failures) from exc
    raise AssertionError("bounded acquisition strategy ladder exhausted unexpectedly")


def _write_job_file(job_path: Path, payload: dict) -> None:
    job_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def initialize_youtube_job(*, youtube_url: str, job_id: str | None,
                           output_dir: str) -> tuple[str, object, dict]:
    """Create the job metadata before downloading its independent source asset."""
    info = _extract_youtube_metadata(youtube_url)
    resolved_job_id = job_id or info["id"]
    paths = build_job_paths(output_dir, resolved_job_id)
    paths.ensure_prepare_dirs()
    payload = {
        "job_id": resolved_job_id, "created_at": _utc_now_iso(), "source_type": "youtube",
        "youtube_url": youtube_url, "video_id": info["id"], "title": info.get("title"),
    }
    _write_job_file(paths.job_json_path, payload)
    return resolved_job_id, paths, payload


def acquire_initialized_youtube_job(*, youtube_url: str, paths, payload: dict) -> None:
    """Download the source for a job whose metadata has already been written."""
    source_path, acquisition = _acquire_youtube_source(youtube_url, paths.source_dir)
    _write_job_file(paths.job_json_path, {
        **payload, "source_path": paths.rel_to_job(source_path), "acquisition": acquisition,
    })


def prepare_source(*, youtube_url: str | None, local_video: str | None,
                   job_id: str | None, output_dir: str) -> str:
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    if youtube_url:
        resolved_job_id, paths, payload = initialize_youtube_job(
            youtube_url=youtube_url, job_id=job_id, output_dir=str(output_dir_path))
        acquire_initialized_youtube_job(youtube_url=youtube_url, paths=paths, payload=payload)
        print(f"Prepared job: {resolved_job_id}")
        print(f"Job directory: {paths.job_dir}")
        return resolved_job_id
    resolved_job_id = job_id or "local-video"
    raise NotImplementedError("Local video input is reserved for a later phase. "
                              f"Received --local-video for job_id='{resolved_job_id}'.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prepare_source(youtube_url=args.youtube_url, local_video=args.local_video,
                   job_id=args.job_id, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
