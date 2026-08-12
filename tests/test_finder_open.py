from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from finder import open_job_folder_in_finder


def _load_tool(filename: str, name: str):
    path = Path(__file__).parents[1] / "user_tools" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_finder_helper_opens_exact_resolved_job_dir_on_macos(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("finder.sys.platform", "darwin")
    monkeypatch.setattr("finder.subprocess.run", lambda command, **kwargs: calls.append((command, kwargs)))

    job_dir = tmp_path / "output" / "video-id"
    open_job_folder_in_finder(job_dir)

    assert calls == [(["open", str(job_dir.resolve())], {
        "check": True, "capture_output": True, "text": True, "timeout": 10,
    })]


def test_finder_helper_is_noop_off_macos(tmp_path, monkeypatch):
    monkeypatch.setattr("finder.sys.platform", "linux")
    monkeypatch.setattr(
        "finder.subprocess.run", lambda *_args, **_kwargs: pytest.fail("open must not run")
    )

    open_job_folder_in_finder(tmp_path)


def test_finder_failure_only_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("finder.sys.platform", "darwin")

    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["open"])

    monkeypatch.setattr("finder.subprocess.run", fail)
    assert open_job_folder_in_finder(tmp_path) is None
    assert "Warning: could not open output folder in Finder" in capsys.readouterr().err


def test_successful_normal_dub_opens_job_dir(tmp_path, monkeypatch):
    runner = _load_tool("00_dub_youtube.py", "finder_default_runner")
    opened = []
    monkeypatch.setattr(runner, "open_job_folder_in_finder", opened.append)
    stages = {name: (lambda: None) for name in (
        "Prepare", "Translation", "Build", "Preflight", "TTS", "Audio", "Mux"
    )}

    result = runner.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)

    assert result == tmp_path / "abc123" / "dubbed_video.mp4"
    assert opened == [tmp_path / "abc123"]


def test_failed_normal_dub_does_not_open_job_dir(tmp_path, monkeypatch):
    runner = _load_tool("00_dub_youtube.py", "finder_failed_default_runner")
    opened = []
    monkeypatch.setattr(runner, "open_job_folder_in_finder", opened.append)
    stages = {name: (lambda: None) for name in (
        "Prepare", "Translation", "Build", "Preflight", "TTS", "Audio", "Mux"
    )}
    stages["Translation"] = lambda: (_ for _ in ()).throw(RuntimeError("translation failed"))

    with pytest.raises(RuntimeError, match="Translation failed"):
        runner.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)
    assert opened == []


def test_background_open_runs_only_after_success(tmp_path, monkeypatch):
    background = _load_tool("10_add_background_audio.py", "finder_background_tool")
    opened = []
    monkeypatch.setattr(background, "open_job_folder_in_finder", opened.append)
    output = tmp_path / "job" / "dubbed_video_with_bg.mp4"
    monkeypatch.setattr(background, "add_background_audio", lambda _args: output)

    assert background.main(["--job-id", "job", "--output-dir", str(tmp_path)]) == 0
    assert opened == [tmp_path / "job"]


def test_failed_background_does_not_open_job_dir(tmp_path, monkeypatch):
    background = _load_tool("10_add_background_audio.py", "finder_failed_background_tool")
    opened = []
    monkeypatch.setattr(background, "open_job_folder_in_finder", opened.append)
    monkeypatch.setattr(
        background, "add_background_audio",
        lambda _args: (_ for _ in ()).throw(background.BackgroundAudioError("mux failed")),
    )

    assert background.main(["--job-id", "job", "--output-dir", str(tmp_path)]) == 1
    assert opened == []


def test_finder_failure_does_not_change_successful_background_exit(tmp_path, monkeypatch):
    background = _load_tool("10_add_background_audio.py", "finder_warning_background_tool")
    output = tmp_path / "job" / "dubbed_video_with_bg.mp4"
    monkeypatch.setattr(background, "add_background_audio", lambda _args: output)
    monkeypatch.setattr(background, "open_job_folder_in_finder", lambda _path: None)

    assert background.main(["--job-id", "job", "--output-dir", str(tmp_path)]) == 0
