import json

import pytest

from codex_models import load_codex_models


def _write_registry(tmp_path, models):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"models": models}), encoding="utf-8")
    return path


def test_default_registry_is_structurally_valid():
    models = load_codex_models()

    assert models
    assert all(isinstance(model["id"], str) and model["id"].strip() for model in models)
    assert all(isinstance(model["label"], str) and model["label"].strip() for model in models)
    assert len({model["id"] for model in models}) == len(models)
    assert len({model["label"] for model in models}) == len(models)


def test_registry_order_and_synthetic_entry_require_no_code_change(tmp_path):
    models = [{"id": "second", "label": "Second"}, {"id": "first", "label": "First"},
              {"id": "third", "label": "Third"}, {"id": "fourth", "label": "Fourth"},
              {"id": "future-model-test", "label": "Future"}]
    assert load_codex_models(_write_registry(tmp_path, models)) == models


@pytest.mark.parametrize(("payload", "message"), [
    ({}, "'models' must be a list"),
    ({"models": []}, "must not be empty"),
    ({"models": [{"id": "", "label": "Label"}]}, "non-empty string 'id'"),
    ({"models": [{"label": "Label"}]}, "non-empty string 'id'"),
    ({"models": [{"id": "model", "label": " "}]}, "non-empty string 'label'"),
    ({"models": [{"id": "model"}]}, "non-empty string 'label'"),
    ({"models": [{"id": "same", "label": "One"},
                  {"id": "same", "label": "Two"}]}, "duplicate id"),
    ({"models": [{"id": "one", "label": "Same"},
                  {"id": "two", "label": "Same"}]}, "duplicate label"),
])
def test_invalid_registry_is_rejected(tmp_path, payload, message):
    path = tmp_path / "models.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_codex_models(path)


def test_registry_root_and_entries_must_be_objects(tmp_path):
    for payload, message in [([], "root must be"), ({"models": ["model"]}, "entry 1 must be")]:
        path = tmp_path / "models.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_codex_models(path)
