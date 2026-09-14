"""Load the repository-controlled Codex model menu registry."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config/codex_models.json"


def load_codex_models(path: Path = DEFAULT_REGISTRY_PATH) -> list[dict[str, str]]:
    """Return validated model entries in their configured display order."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Codex model registry could not be loaded: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Codex model registry root must be a JSON object.")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError("Codex model registry 'models' must be a list.")
    if not models:
        raise ValueError("Codex model registry 'models' must not be empty.")

    validated: list[dict[str, str]] = []
    ids: set[str] = set()
    labels: set[str] = set()
    for index, entry in enumerate(models, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Codex model registry entry {index} must be an object.")
        model_id, label = entry.get("id"), entry.get("label")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"Codex model registry entry {index} requires a non-empty string 'id'.")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Codex model registry entry {index} requires a non-empty string 'label'.")
        model_id, label = model_id.strip(), label.strip()
        if model_id in ids:
            raise ValueError(f"Codex model registry contains duplicate id: {model_id}")
        if label in labels:
            raise ValueError(f"Codex model registry contains duplicate label: {label}")
        ids.add(model_id)
        labels.add(label)
        validated.append({"id": model_id, "label": label})
    return validated
