#!/usr/bin/env python3
"""Pure-Python validation helpers shared by translation handoff stages."""

from __future__ import annotations

import json
from pathlib import Path


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing manifest file: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in manifest: {path}") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Manifest must be a JSON object: {path}")
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError(f"{path} does not contain any chunks.")
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("file"), str) or not chunk["file"]:
            raise RuntimeError(f"Manifest chunk {index} must include a non-empty file entry.")
    total = manifest.get("total_segments")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
        raise RuntimeError("Manifest total_segments must be a non-negative integer.")
    return manifest


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing chunk file: {path}")
    items: list[dict] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSONL in {path} at line {line_number}.") from exc
        if not isinstance(item, dict):
            raise RuntimeError(f"Expected a JSON object in {path} at line {line_number}.")
        items.append(item)
    return items


def validate_chunk_pair(
    source_items: list[dict], translated_items: list[dict],
    source_path: Path, translated_path: Path, *, reject_blank_translation: bool = False,
) -> list[dict]:
    if len(source_items) != len(translated_items):
        raise RuntimeError(
            f"Chunk line count mismatch: {translated_path} has {len(translated_items)} lines, "
            f"but {source_path} has {len(source_items)}."
        )
    merged: list[dict] = []
    for index, (source, translated) in enumerate(zip(source_items, translated_items), start=1):
        for field in ("segment_id", "start", "end", "text"):
            if field not in source:
                raise RuntimeError(
                    f"Chunk validation failed at {source_path} line {index}: {field} is missing."
                )
        for field in ("segment_id", "start", "end") + (("duration",) if "duration" in source else ()):
            if translated.get(field) != source.get(field):
                raise RuntimeError(
                    f"Chunk validation failed at {translated_path} line {index}: "
                    f"{field} does not match the source chunk."
                )
        if "text" not in translated:
            raise RuntimeError(
                f"Chunk validation failed at {translated_path} line {index}: text is missing."
            )
        source_text = source["text"]
        translated_text = translated["text"]
        if reject_blank_translation and not isinstance(source_text, str):
            raise RuntimeError(
                f"Chunk validation failed at {source_path} line {index}: text must be a string."
            )
        if not isinstance(translated_text, str):
            raise RuntimeError(
                f"Chunk validation failed at {translated_path} line {index}: text must be a string."
            )
        if reject_blank_translation and source_text.strip() and not translated_text.strip():
            raise RuntimeError(
                f"Chunk validation failed at {translated_path} line {index}: "
                "translated text is blank for non-empty source text."
            )
        merged.append({
            "segment_id": source["segment_id"], "start": source["start"], "end": source["end"],
            "duration": source.get("duration", round(source["end"] - source["start"], 3)),
            "text": translated_text,
        })
    return merged
