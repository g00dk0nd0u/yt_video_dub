from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "user_tools" / "10_add_background_audio.py"
SPEC = importlib.util.spec_from_file_location("background_audio_tool", MODULE_PATH)
assert SPEC and SPEC.loader
background = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = background
SPEC.loader.exec_module(background)


def _args(tmp_path: Path, *, background_db: float = -12.0):
    return background.build_parser().parse_args([
        "--job-id", "job", "--output-dir", str(tmp_path), "--background-db",
        str(background_db), "--quiet",
    ])


def _job(tmp_path: Path) -> Path:
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    (job / "01_source" / "source.mp4").write_bytes(b"source-audio")
    (job / "07_audio" / "dub_audio.wav").write_bytes(b"japanese")
    (job / "dubbed_video.mp4").write_bytes(b"standard-must-survive")
    return job


def _fake_commands(monkeypatch, calls: list[list[str]]):
    monkeypatch.setattr(background.shutil, "which", lambda value: f"/bin/{value}")

    def fake_run(command, *, quiet=True):
        calls.append(command)
        if command[0].endswith("ffprobe"):
            return subprocess.CompletedProcess(command, 0, stdout="10.0\n", stderr="")
        if "--two-stems=vocals" in command:
            out = Path(command[command.index("-o") + 1]) / "htdemucs" / "source"
            out.mkdir(parents=True)
            (out / "vocals.wav").write_bytes(b"vocals")
            (out / "no_vocals.wav").write_bytes(b"background")
        else:
            Path(command[-1]).write_bytes(b"generated")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(background, "_run", fake_run)


def test_success_mix_excludes_vocals_and_protects_standard(tmp_path, monkeypatch):
    job = _job(tmp_path)
    calls = []
    _fake_commands(monkeypatch, calls)

    output = background.add_background_audio(_args(tmp_path))

    assert output == job / "dubbed_video_with_bg.mp4"
    assert output.read_bytes() == b"generated"
    assert (job / "dubbed_video.mp4").read_bytes() == b"standard-must-survive"
    final = next(command for command in calls if str(command[-1]).endswith(".tmp.mp4"))
    assert str(job / "07_audio" / "dub_audio.wav") in final
    assert str(job / "09_background" / "accompaniment.wav") in final
    assert str(job / "09_background" / "vocals.wav") not in final
    graph = final[final.index("-filter_complex") + 1]
    assert "volume=-12dB" in graph
    assert "duration=10.000000" in graph
    assert final[final.index("-c:v") + 1] == "copy"
    manifest = json.loads((job / "09_background" / "background_manifest.json").read_text())
    assert manifest["success"] is True
    assert manifest["cache_reused"] is False
    assert manifest["final_duration"] == 10.0


def test_cache_reused_when_only_background_volume_changes(tmp_path, monkeypatch):
    job = _job(tmp_path)
    calls = []
    _fake_commands(monkeypatch, calls)
    background.add_background_audio(_args(tmp_path))
    calls.clear()

    background.add_background_audio(_args(tmp_path, background_db=-20))

    assert not any("--two-stems=vocals" in command for command in calls)
    final = next(command for command in calls if str(command[-1]).endswith(".tmp.mp4"))
    assert "volume=-20dB" in final[final.index("-filter_complex") + 1]
    manifest = json.loads((job / "09_background" / "background_manifest.json").read_text())
    assert manifest["cache_reused"] is True


def test_source_change_invalidates_separation_cache(tmp_path, monkeypatch):
    job = _job(tmp_path)
    calls = []
    _fake_commands(monkeypatch, calls)
    background.add_background_audio(_args(tmp_path))
    (job / "01_source" / "source.mp4").write_bytes(b"different source")
    calls.clear()

    background.add_background_audio(_args(tmp_path))

    assert sum("--two-stems=vocals" in command for command in calls) == 1


def test_missing_demucs_fails_cleanly_without_output(tmp_path, monkeypatch, capsys):
    job = _job(tmp_path)
    monkeypatch.setattr(background.shutil, "which", lambda _value: None)

    result = background.main(["--job-id", "job", "--output-dir", str(tmp_path), "--quiet"])

    assert result == 1
    assert not (job / "dubbed_video_with_bg.mp4").exists()
    assert (job / "dubbed_video.mp4").read_bytes() == b"standard-must-survive"
    stderr = capsys.readouterr().err
    assert "Background separation tool is not installed" in stderr
    assert "unchanged" in stderr
    assert "Traceback" not in stderr


def test_failed_final_mux_removes_partial_output(tmp_path, monkeypatch):
    job = _job(tmp_path)
    calls = []
    _fake_commands(monkeypatch, calls)
    real_fake = background._run

    def fail_final(command, *, quiet=True):
        if str(command[-1]).endswith(".tmp.mp4"):
            Path(command[-1]).write_bytes(b"partial")
            raise background.BackgroundAudioError("mux failed")
        return real_fake(command, quiet=quiet)

    monkeypatch.setattr(background, "_run", fail_final)
    try:
        background.add_background_audio(_args(tmp_path))
    except background.BackgroundAudioError:
        pass
    else:
        raise AssertionError("expected mux failure")

    assert not (job / ".dubbed_video_with_bg.tmp.mp4").exists()
    assert not (job / "dubbed_video_with_bg.mp4").exists()
    assert (job / "dubbed_video.mp4").read_bytes() == b"standard-must-survive"
    manifest = json.loads((job / "09_background" / "background_manifest.json").read_text())
    assert manifest["success"] is False
