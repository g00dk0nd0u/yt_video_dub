"""Deterministically turn rolling YouTube captions into dubbing utterances."""

from __future__ import annotations

import re
from typing import Any


TOKEN_RE = re.compile(r"\S+")
SENTENCE_END_RE = re.compile(r"[.!?][\]\)\"']*$")


def _key(token: str) -> str:
    return re.sub(r"[^\w']", "", token, flags=re.UNICODE).casefold()


def _deduplicate(existing: list[dict[str, Any]], incoming: list[str]) -> list[str]:
    """Remove the longest rolling-caption prefix already at the stream tail."""
    old = [_key(item["token"]) for item in existing]
    new = [_key(token) for token in incoming]
    limit = min(len(old), len(new), 40)
    for size in range(limit, 0, -1):
        if old[-size:] == new[:size]:
            return incoming[size:]
    # Fully repeated captions may occur slightly behind the current tail.
    if new and len(new) <= len(old):
        for offset in range(max(0, len(old) - 40), len(old) - len(new) + 1):
            if old[offset : offset + len(new)] == new:
                return []
    return incoming


def normalize_segments(
    segments: list[dict[str, Any]],
    *,
    pause_seconds: float = 1.0,
    max_words: int = 35,
    max_duration: float = 15.0,
) -> list[dict[str, Any]]:
    """Return ordered, non-overlapping utterances with raw-caption mappings."""
    stream: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for segment in sorted(segments, key=lambda item: (float(item["start"]), item["segment_id"])):
        words = TOKEN_RE.findall(str(segment.get("text", "")))
        words = _deduplicate(stream, words)
        if not words:
            previous = segment
            continue
        pause_before = bool(
            previous is not None
            and float(segment["start"]) - float(previous["end"]) >= pause_seconds
        )
        for word_index, word in enumerate(words):
            stream.append(
                {
                    "token": word,
                    "segment_id": segment["segment_id"],
                    "start": float(segment["start"]),
                    "end": float(segment["end"]),
                    "pause_before": pause_before and word_index == 0,
                }
            )
        previous = segment

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for token in stream:
        if token["pause_before"] and current:
            groups.append(current)
            current = []
        current.append(token)
        elapsed = token["end"] - current[0]["start"]
        if SENTENCE_END_RE.search(token["token"]) or len(current) >= max_words or elapsed >= max_duration:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    units: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        source_ids = list(dict.fromkeys(token["segment_id"] for token in group))
        units.append(
            {
                "unit_id": f"utt_{index:04}",
                "source_start": round(group[0]["start"], 3),
                "source_end": round(max(token["end"] for token in group), 3),
                "source_text": " ".join(token["token"] for token in group),
                "source_segment_ids": source_ids,
            }
        )

    # Multiple sentences inside one caption have no independent timing anchor.
    # Keep their text together rather than inventing timestamps or losing text.
    consolidated: list[dict[str, Any]] = []
    for unit in units:
        if consolidated and unit["source_start"] == consolidated[-1]["source_start"]:
            prior = consolidated[-1]
            prior["source_end"] = max(prior["source_end"], unit["source_end"])
            prior["source_text"] += " " + unit["source_text"]
            prior["source_segment_ids"] = list(
                dict.fromkeys(prior["source_segment_ids"] + unit["source_segment_ids"])
            )
        else:
            consolidated.append(unit)
    units = consolidated

    # Hard-clamp each utterance at the following absolute anchor; never shift anchors.
    normalized: list[dict[str, Any]] = []
    for index, unit in enumerate(units):
        end = unit["source_end"]
        if index + 1 < len(units):
            end = min(end, units[index + 1]["source_start"])
        if end <= unit["source_start"]:
            # A boundary within one rolling caption has no reliable timestamp.
            # Merge it instead of inventing or shifting time.
            if normalized:
                prior = normalized[-1]
                prior["source_text"] += " " + unit["source_text"]
                prior["source_segment_ids"] = list(
                    dict.fromkeys(prior["source_segment_ids"] + unit["source_segment_ids"])
                )
            continue
        result = dict(unit)
        result["unit_id"] = f"utt_{len(normalized) + 1:04}"
        result["source_end"] = round(end, 3)
        result["available_duration"] = round(end - unit["source_start"], 3)
        normalized.append(result)
    return normalized
