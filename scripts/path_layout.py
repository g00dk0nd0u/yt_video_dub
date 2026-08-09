#!/usr/bin/env python3
"""Central path definitions for job output layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobPaths:
    """Job-scoped output paths with new-layout write targets and legacy fallbacks."""

    output_dir: Path
    job_id: str

    @property
    def job_dir(self) -> Path:
        return self.output_dir / self.job_id

    @property
    def source_dir(self) -> Path:
        return self.job_dir / "01_source"

    @property
    def transcript_dir(self) -> Path:
        return self.job_dir / "02_transcript"

    @property
    def translation_input_dir(self) -> Path:
        return self.job_dir / "03_translation_input"

    @property
    def translation_output_dir(self) -> Path:
        return self.job_dir / "04_translation_output"

    @property
    def segments_dir(self) -> Path:
        return self.job_dir / "05_segments"

    @property
    def tts_dir(self) -> Path:
        return self.job_dir / "06_tts"

    @property
    def audio_dir(self) -> Path:
        return self.job_dir / "07_audio"

    @property
    def synced_video_dir(self) -> Path:
        return self.job_dir / "08_synced_video"

    @property
    def simple_mux_dir(self) -> Path:
        return self.job_dir / "09_simple_mux"

    @property
    def source_video_path(self) -> Path:
        return self.source_dir / "source.mp4"

    @property
    def job_json_path(self) -> Path:
        return self.source_dir / "job.json"

    @property
    def transcript_json_path(self) -> Path:
        return self.transcript_raw_json_path

    @property
    def transcript_srt_path(self) -> Path:
        return self.transcript_raw_srt_path

    @property
    def transcript_raw_json_path(self) -> Path:
        return self.transcript_dir / "transcript_raw.json"

    @property
    def transcript_raw_srt_path(self) -> Path:
        return self.transcript_dir / "transcript_raw.srt"

    @property
    def transcript_normalized_json_path(self) -> Path:
        return self.transcript_dir / "transcript_normalized.json"

    @property
    def transcript_normalized_srt_path(self) -> Path:
        return self.transcript_dir / "transcript_normalized.srt"

    @property
    def translation_manifest_path(self) -> Path:
        return self.translation_input_dir / "manifest.json"

    @property
    def translated_segments_json_path(self) -> Path:
        return self.segments_dir / "translated_segments.json"

    @property
    def translated_segments_srt_path(self) -> Path:
        return self.segments_dir / "translated_segments.srt"

    @property
    def tts_manifest_path(self) -> Path:
        return self.tts_dir / "tts_manifest.json"

    @property
    def dub_audio_wav_path(self) -> Path:
        return self.audio_dir / "dub_audio.wav"

    @property
    def dub_audio_manifest_path(self) -> Path:
        return self.audio_dir / "dub_audio_manifest.json"

    @property
    def synced_video_manifest_path(self) -> Path:
        return self.synced_video_dir / "synced_video_manifest.json"

    @property
    def synced_segments_dir(self) -> Path:
        return self.synced_video_dir / "synced_segments"

    @property
    def dubbed_video_synced_path(self) -> Path:
        """Compatibility alias for the old user-facing result property."""
        return self.dubbed_video_path

    @property
    def dubbed_video_path(self) -> Path:
        return self.job_dir / "dubbed_video.mp4"

    @property
    def dubbed_video_simple_path(self) -> Path:
        return self.simple_mux_dir / "dubbed_video.mp4"

    def ensure_prepare_dirs(self) -> None:
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.translation_input_dir.mkdir(parents=True, exist_ok=True)
        self.translation_output_dir.mkdir(parents=True, exist_ok=True)

    def ensure_tts_dirs(self) -> None:
        self.tts_dir.mkdir(parents=True, exist_ok=True)

    def ensure_audio_dirs(self) -> None:
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def ensure_synced_video_dirs(self) -> None:
        self.synced_segments_dir.mkdir(parents=True, exist_ok=True)

    def ensure_simple_mux_dir(self) -> None:
        self.simple_mux_dir.mkdir(parents=True, exist_ok=True)

    def rel_to_job(self, path: Path) -> str:
        return str(path.relative_to(self.job_dir))

    def resolve_source_video_path(self) -> Path:
        return _prefer_existing(self.source_video_path, self.job_dir / "source.mp4")

    def resolve_job_json_path(self) -> Path:
        return _prefer_existing(self.job_json_path, self.job_dir / "job.json")

    def resolve_transcript_json_path(self) -> Path:
        for candidate in (
            self.transcript_raw_json_path,
            self.transcript_dir / "transcript_original.json",
            self.job_dir / "transcript_original.json",
        ):
            if candidate.exists():
                return candidate
        return self.transcript_raw_json_path

    def resolve_transcript_srt_path(self) -> Path:
        for candidate in (
            self.transcript_raw_srt_path,
            self.transcript_dir / "transcript_original.srt",
            self.job_dir / "transcript_original.srt",
        ):
            if candidate.exists():
                return candidate
        return self.transcript_raw_srt_path

    def resolve_transcript_normalized_json_path(self) -> Path:
        if self.transcript_normalized_json_path.exists():
            return self.transcript_normalized_json_path
        # Old jobs did not distinguish raw and normalized captions.
        return self.resolve_transcript_json_path()

    def resolve_translation_input_dir(self) -> Path:
        return _prefer_existing_dir(self.translation_input_dir, self.job_dir / "translation_input")

    def resolve_translation_output_dir(self) -> Path:
        return _prefer_existing_dir(self.translation_output_dir, self.job_dir / "translation_output")

    def resolve_translation_manifest_path(self) -> Path:
        return _prefer_existing(
            self.translation_manifest_path,
            self.job_dir / "translation_input" / "manifest.json",
        )

    def resolve_translated_segments_json_path(self) -> Path:
        return _prefer_existing(
            self.translated_segments_json_path,
            self.job_dir / "translated_segments.json",
        )

    def resolve_translated_segments_srt_path(self) -> Path:
        return _prefer_existing(
            self.translated_segments_srt_path,
            self.job_dir / "translated_segments.srt",
        )

    def resolve_tts_dir(self) -> Path:
        return _prefer_existing_dir(self.tts_dir, self.job_dir / "tts")

    def resolve_tts_manifest_path(self) -> Path:
        return _prefer_existing(self.tts_manifest_path, self.job_dir / "tts" / "tts_manifest.json")

    def resolve_dub_audio_wav_path(self) -> Path:
        return _prefer_existing(self.dub_audio_wav_path, self.job_dir / "dub_audio.wav")

    def resolve_dub_audio_manifest_path(self) -> Path:
        return _prefer_existing(
            self.dub_audio_manifest_path,
            self.job_dir / "dub_audio_manifest.json",
        )

    def resolve_synced_video_manifest_path(self) -> Path:
        return _prefer_existing(
            self.synced_video_manifest_path,
            self.job_dir / "synced_video_manifest.json",
        )

    def resolve_synced_segments_dir(self) -> Path:
        return _prefer_existing_dir(
            self.synced_segments_dir,
            self.job_dir / "synced_segments",
        )


def _prefer_existing(primary: Path, legacy: Path) -> Path:
    if primary.exists():
        return primary
    if legacy.exists():
        return legacy
    return primary


def _prefer_existing_dir(primary: Path, legacy: Path) -> Path:
    if primary.is_dir():
        return primary
    if legacy.is_dir():
        return legacy
    return primary


def build_job_paths(output_dir: str | Path, job_id: str) -> JobPaths:
    return JobPaths(output_dir=Path(output_dir), job_id=job_id)
