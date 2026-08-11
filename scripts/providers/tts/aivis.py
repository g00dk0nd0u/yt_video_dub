"""Compatibility description for the existing AivisSpeech implementation."""

from __future__ import annotations


def provider_settings(*, base_url: str, speaker_id: int) -> dict:
    return {"tts_provider": "aivis", "base_url": base_url.rstrip("/"),
            "voice": str(speaker_id), "speaker_id": speaker_id}
