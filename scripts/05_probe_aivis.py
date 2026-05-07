#!/usr/bin/env python3
"""Probe a local AivisSpeech API with a short fixed text sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


DEFAULT_TEXT = "こんにちは。これは接続テストです。"
DEFAULT_TIMEOUT = 30.0


class ProbeError(RuntimeError):
    """Raised when the probe request fails with useful HTTP context."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe a local AivisSpeech API and save a sample WAV file."
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
    parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL for the local AivisSpeech API.",
    )
    parser.add_argument(
        "--speaker-id",
        required=True,
        type=int,
        help="Speaker ID to use for the probe.",
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help=f"Short Japanese text for the probe. Default: {DEFAULT_TEXT}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds. Default: {DEFAULT_TIMEOUT}",
    )
    return parser


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _truncate_text(value: str, limit: int = 600) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...<truncated>..."


def _format_response_body(response: requests.Response) -> str:
    text = response.text.strip()
    if not text:
        return "<empty>"

    try:
        parsed = response.json()
    except ValueError:
        return _truncate_text(text)

    return _truncate_text(json.dumps(parsed, ensure_ascii=False, indent=2))


def _raise_http_error(step: str, response: requests.Response) -> None:
    raise ProbeError(
        f"{step} failed.\n"
        f"HTTP {response.status_code} {response.reason}\n"
        f"URL: {response.request.method} {response.url}\n"
        f"Response body:\n{_format_response_body(response)}"
    )


def _post_audio_query(
    session: requests.Session,
    base_url: str,
    speaker_id: int,
    text: str,
    timeout: float,
) -> dict[str, Any]:
    response = session.post(
        f"{base_url}/audio_query",
        params={"text": text, "speaker": speaker_id},
        timeout=timeout,
    )
    if not response.ok:
        _raise_http_error("audio_query", response)

    try:
        payload = response.json()
    except ValueError as exc:
        raise ProbeError(
            "audio_query returned a non-JSON response.\n"
            f"HTTP {response.status_code} {response.reason}\n"
            f"Response body:\n{_format_response_body(response)}"
        ) from exc

    if not isinstance(payload, dict):
        raise ProbeError(
            "audio_query returned JSON, but it was not an object.\n"
            f"Response body:\n{_format_response_body(response)}"
        )
    return payload


def _post_synthesis(
    session: requests.Session,
    base_url: str,
    speaker_id: int,
    audio_query_payload: dict[str, Any],
    timeout: float,
) -> bytes:
    response = session.post(
        f"{base_url}/synthesis",
        params={"speaker": speaker_id},
        json=audio_query_payload,
        timeout=timeout,
    )
    if not response.ok:
        _raise_http_error("synthesis", response)

    content_type = response.headers.get("content-type", "")
    if "audio" not in content_type.lower() and not response.content.startswith(b"RIFF"):
        raise ProbeError(
            "synthesis succeeded, but the response did not look like WAV/audio data.\n"
            f"HTTP {response.status_code} {response.reason}\n"
            f"Content-Type: {content_type or '<missing>'}\n"
            f"Response body preview:\n{_format_response_body(response)}"
        )

    return response.content


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    job_dir = Path(args.output_dir) / args.job_id
    tts_dir = job_dir / "tts"
    probe_path = tts_dir / "probe.wav"

    tts_dir.mkdir(parents=True, exist_ok=True)
    base_url = _normalize_base_url(args.base_url)

    session = requests.Session()

    try:
        audio_query_payload = _post_audio_query(
            session=session,
            base_url=base_url,
            speaker_id=args.speaker_id,
            text=args.text,
            timeout=args.timeout,
        )
        wav_bytes = _post_synthesis(
            session=session,
            base_url=base_url,
            speaker_id=args.speaker_id,
            audio_query_payload=audio_query_payload,
            timeout=args.timeout,
        )
    except requests.RequestException as exc:
        raise ProbeError(
            "Failed to connect to the AivisSpeech API.\n"
            f"Base URL: {base_url}\n"
            f"Details: {exc}"
        ) from exc

    probe_path.write_bytes(wav_bytes)

    print("AivisSpeech probe succeeded.")
    print(f"Base URL: {base_url}")
    print(f"Speaker ID: {args.speaker_id}")
    print(f"Saved: {probe_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
