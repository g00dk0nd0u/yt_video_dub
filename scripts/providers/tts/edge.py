"""Synchronous boundary around edge-tts' async Python API."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable


DEFAULT_VOICE = "ja-JP-KeitaNeural"
MAX_RATE_PERCENT = 15


class EdgeTTSError(RuntimeError):
    """Raised when Edge synthesis fails."""


def rate_string(percent: int) -> str:
    bounded = max(0, min(MAX_RATE_PERCENT, int(percent)))
    return f"+{bounded}%"


async def _save(text: str, voice: str, rate: str, path: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text=text, voice=voice, rate=rate).save(str(path))


class EdgeTTSProvider:
    name = "edge"

    def __init__(self, voice: str = DEFAULT_VOICE,
                 save: Callable[[str, str, str, Path], Awaitable[None]] = _save):
        self.voice = voice
        self._save = save

    def synthesize(self, text: str, output_path: Path, *, rate_percent: int = 0) -> dict:
        rate = rate_string(rate_percent)
        try:
            asyncio.run(self._save(text, self.voice, rate, output_path))
        except Exception as exc:
            raise EdgeTTSError("Edge TTS request failed.") from exc
        return {"tts_provider": self.name, "voice": self.voice, "rate": rate,
                "audio_path": str(output_path)}
