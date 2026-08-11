import json
from pathlib import Path

import pytest


def test_provider_selection_and_existing_aivis_route():
    from providers import translation_provider, tts_provider

    assert translation_provider("codex_cli").__name__ == "translate_job"
    assert tts_provider("edge").__name__ == "EdgeTTSProvider"
    assert tts_provider("aivis")(base_url="http://aivis/", speaker_id=7) == {
        "tts_provider": "aivis", "base_url": "http://aivis", "voice": "7", "speaker_id": 7,
    }
    with pytest.raises(ValueError, match="Unknown"):
        tts_provider("other")


def _translation_job(tmp_path):
    input_dir = tmp_path / "repo/job/03_translation_input"
    output_dir = tmp_path / "repo/job/04_translation_output"
    input_dir.mkdir(parents=True)
    source = {"segment_id": "u1", "start": 0.0, "end": 1.0,
              "duration": 1.0, "text": "hello"}
    (input_dir / "chunk_0001.txt").write_text(json.dumps(source) + "\n")
    manifest = input_dir / "manifest.json"
    manifest.write_text(json.dumps({"total_segments": 1,
                                    "chunks": [{"file": "chunk_0001.txt"}]}))
    rules = tmp_path / "rules.md"
    rules.write_text("rules")
    return input_dir, output_dir, manifest, rules, source


def test_codex_missing(tmp_path, monkeypatch):
    from providers.translation import codex_cli

    args = _translation_job(tmp_path)
    monkeypatch.setattr(codex_cli.shutil, "which", lambda _: None)
    with pytest.raises(codex_cli.CodexTranslationError, match="not found"):
        codex_cli.translate_job(input_dir=args[0], output_dir=args[1],
                                manifest_path=args[2], rules_path=args[3])


@pytest.mark.parametrize("mode", ["valid", "missing", "metadata", "malformed", "nonzero"])
def test_codex_validation_and_isolation(tmp_path, monkeypatch, mode):
    from providers.translation import codex_cli

    input_dir, output_dir, manifest, rules, source = _translation_job(tmp_path)
    monkeypatch.setattr(codex_cli.shutil, "which", lambda _: "/usr/bin/codex")
    observed = {}

    def runner(command, **kwargs):
        workspace = Path(kwargs["cwd"])
        observed["workspace"] = workspace
        observed["command"] = command
        if mode not in {"missing", "nonzero"}:
            translated = dict(source, text="こんにちは")
            if mode == "metadata":
                translated["start"] = 0.2
            content = "not json\n" if mode == "malformed" else json.dumps(translated) + "\n"
            (workspace / "output/chunk_0001.txt").write_text(content)
        return type("Result", (), {"returncode": 1 if mode == "nonzero" else 0})()

    if mode == "valid":
        metadata = codex_cli.translate_job(
            input_dir=input_dir, output_dir=output_dir, manifest_path=manifest,
            rules_path=rules, runner=runner)
        assert metadata == {"provider": "codex_cli", "chunk_count": 1, "status": "completed"}
        assert json.loads((output_dir / "chunk_0001.txt").read_text())["text"] == "こんにちは"
        assert observed["workspace"] != input_dir.parents[1]
        assert "--skip-git-repo-check" in observed["command"]
        assert observed["command"][observed["command"].index("-C") + 1] == str(
            observed["workspace"]
        )
    else:
        with pytest.raises(codex_cli.CodexTranslationError):
            codex_cli.translate_job(input_dir=input_dir, output_dir=output_dir,
                                    manifest_path=manifest, rules_path=rules, runner=runner)
        assert not (output_dir / "chunk_0001.txt").exists()


def test_codex_cannot_rewrite_validation_source(tmp_path, monkeypatch):
    from providers.translation import codex_cli

    input_dir, output_dir, manifest, rules, source = _translation_job(tmp_path)
    monkeypatch.setattr(codex_cli.shutil, "which", lambda _: "/usr/bin/codex")

    def runner(command, **kwargs):
        workspace = Path(kwargs["cwd"])
        changed = dict(source, start=9.0, text="改変")
        content = json.dumps(changed) + "\n"
        (workspace / "input/chunk_0001.txt").write_text(content)
        (workspace / "output/chunk_0001.txt").write_text(content)
        return type("Result", (), {"returncode": 0})()

    with pytest.raises(codex_cli.CodexTranslationError):
        codex_cli.translate_job(input_dir=input_dir, output_dir=output_dir,
                                manifest_path=manifest, rules_path=rules, runner=runner)
    assert json.loads((input_dir / "chunk_0001.txt").read_text()) == source
    assert not (output_dir / "chunk_0001.txt").exists()


def test_aivis_cache_rejects_edge_manifest(load_script):
    module = load_script("06_generate_tts_segments.py")
    segment = {"segment_id": "u1", "start": 0.0, "end": 1.0, "text": "訳"}
    assert not module._is_reusable_tts(
        segment, segment, {"tts_provider": "edge", "voice": "x"},
        {"tts_provider": "aivis", "voice": "1", "speaker_id": 1,
         "base_url": "http://aivis"})
