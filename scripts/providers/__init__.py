"""Small provider registry used by the provider-based pipeline."""

from __future__ import annotations


def translation_provider(name: str):
    if name == "codex_cli":
        from providers.translation.codex_cli import translate_job

        return translate_job
    raise ValueError(f"Unknown translation provider: {name}")


def tts_provider(name: str):
    if name == "aivis":
        from providers.tts.aivis import provider_settings

        return provider_settings
    if name == "edge":
        from providers.tts.edge import EdgeTTSProvider

        return EdgeTTSProvider
    raise ValueError(f"Unknown TTS provider: {name}")
