"""Deterministically turn rolling YouTube captions into dubbing utterances."""

from __future__ import annotations

import re
from typing import Any


TOKEN_RE = re.compile(r"\S+")
SENTENCE_END_RE = re.compile(r"[.!?][\]\)\"']*$")
NON_SPEECH_CUES = {"[music]", "[applause]", "[laughter]"}
BOUNDARY_CUE_TOKENS = {">>"}
MIN_TTS_UNIT_SECONDS = 0.75


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
    min_tts_unit_seconds: float = MIN_TTS_UNIT_SECONDS,
) -> list[dict[str, Any]]:
    """Return ordered, non-overlapping utterances with raw-caption mappings."""
    stream: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    ordered_segments = sorted(
        segments, key=lambda item: (float(item["start"]), item["segment_id"])
    )
    for segment_index, segment in enumerate(ordered_segments):
        raw_words = TOKEN_RE.findall(str(segment.get("text", "")))
        words = _deduplicate(stream, raw_words)
        if not words:
            previous = segment
            continue
        removed_prefix = len(raw_words) - len(words)
        window_start = float(segment["start"])
        fallback_end = float(segment["end"])
        next_start = (
            float(ordered_segments[segment_index + 1]["start"])
            if segment_index + 1 < len(ordered_segments)
            else None
        )
        window_end = (
            next_start
            if next_start is not None and next_start > window_start
            else fallback_end
        )
        if window_end <= window_start:
            window_end = max(fallback_end, window_start + 0.001)
        token_count = max(1, len(raw_words))
        token_step = (window_end - window_start) / token_count
        pause_before = bool(
            previous is not None
            and float(segment["start"]) - float(previous["end"]) >= pause_seconds
        )
        first_spoken_word = True
        for word_index, word in enumerate(words):
            raw_word_index = removed_prefix + word_index
            # YouTube uses a standalone ``>>`` token as a speaker/cue marker.
            # Match the whole token so technical text such as ``x > 10``,
            # ``A >= B``, and ``foo -> bar`` remains untouched.
            if word.casefold() in NON_SPEECH_CUES or word in BOUNDARY_CUE_TOKENS:
                continue
            stream.append(
                {
                    "token": word,
                    "segment_id": segment["segment_id"],
                    "start": window_start + raw_word_index * token_step,
                    "end": window_start + (raw_word_index + 1) * token_step,
                    "pause_before": pause_before and first_spoken_word,
                }
            )
            first_spoken_word = False
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
                "source_end": round(group[-1]["end"], 3),
                "source_text": " ".join(token["token"] for token in group),
                "source_segment_ids": source_ids,
            }
        )

    # Degenerate input windows can still share a start; keep all text without
    # inventing a second anchor in that exceptional case.
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

    # Token estimates normally make units disjoint. Clamp only as a final guard
    # against malformed caption windows; never shift a later absolute anchor.
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
    # Windows at or below the observed 0.2--0.71s failure class are not viable
    # independent Japanese TTS units. Prefer the following contiguous unit,
    # then the preceding one, without crossing a real pause or max_duration.
    for unit in normalized:
        unit["source_unit_ids"] = [unit["unit_id"]]
        unit["coalesced"] = False
    index = 0
    while index < len(normalized):
        unit = normalized[index]
        duration = unit["source_end"] - unit["source_start"]
        if duration > min_tts_unit_seconds:
            index += 1
            continue
        candidates = []
        if index + 1 < len(normalized):
            candidates.append(index + 1)
        if index > 0:
            candidates.append(index - 1)
        merged = False
        for neighbor_index in candidates:
            neighbor = normalized[neighbor_index]
            left, right = sorted((unit, neighbor), key=lambda item: item["source_start"])
            gap = right["source_start"] - left["source_end"]
            outer_duration = right["source_end"] - left["source_start"]
            if gap >= pause_seconds or outer_duration > max_duration:
                continue
            combined = {
                **left,
                "source_end": right["source_end"],
                "available_duration": round(outer_duration, 3),
                "source_text": left["source_text"] + " " + right["source_text"],
                "source_segment_ids": list(dict.fromkeys(
                    left["source_segment_ids"] + right["source_segment_ids"])),
                "source_unit_ids": left["source_unit_ids"] + right["source_unit_ids"],
                "coalesced": True,
            }
            low, high = sorted((index, neighbor_index))
            normalized[low : high + 1] = [combined]
            index = max(0, low - 1)
            merged = True
            break
        if not merged:
            index += 1
    for index, unit in enumerate(normalized, start=1):
        unit["unit_id"] = f"utt_{index:04}"
    return normalized
