from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "user_tools" / "10_add_background_audio.py"
SPEC = importlib.util.spec_from_file_location("background_audio_tool", MODULE_PATH)
assert SPEC and SPEC.loader
background = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = background
SPEC.loader.exec_module(background)


def _args(tmp_path: Path, *, background_db: float | None = None):
    arguments = ["--job-id", "job", "--output-dir", str(tmp_path), "--quiet"]
    if background_db is not None:
        arguments.extend(["--background-db", str(background_db)])
    return background.build_parser().parse_args(arguments)


def _job(tmp_path: Path) -> Path:
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    (job / "01_source" / "source.mp4").write_bytes(b"source-audio")
    (job / "07_audio" / "dub_audio.wav").write_bytes(b"japanese")
    (job / "dubbed_video.mp4").write_bytes(b"standard-must-survive")
    return job


def _named_job(tmp_path: Path, name: str) -> Path:
    job = tmp_path / name
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    (job / "01_source" / "source.mp4").touch()
    (job / "07_audio" / "dub_audio.wav").touch()
    (job / "dubbed_video.mp4").touch()
    return job


def test_job_id_skips_interactive_selection(tmp_path, monkeypatch):
    selected = []
    monkeypatch.setattr(background, "select_job_id", lambda _path: selected.append(True))
    monkeypatch.setattr(background, "add_background_audio", lambda args: tmp_path / args.job_id)

    assert background.main(["--job-id", "direct", "--output-dir", str(tmp_path)]) == 0
    assert selected == []


def test_lists_only_complete_jobs_in_sorted_order(tmp_path):
    _named_job(tmp_path, "video-b")
    _named_job(tmp_path, "video-a")
    incomplete = _named_job(tmp_path, "incomplete")
    (incomplete / "07_audio" / "dub_audio.wav").unlink()
    (tmp_path / "not-a-job.txt").touch()

    assert background.list_background_audio_jobs(tmp_path) == ["video-a", "video-b"]


def test_number_selection_returns_corresponding_job(tmp_path, monkeypatch):
    _named_job(tmp_path, "first")
    _named_job(tmp_path, "second")
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    assert background.select_job_id(tmp_path) == "second"


def test_invalid_selection_prompts_again(tmp_path, monkeypatch, capsys):
    _named_job(tmp_path, "job")
    answers = iter(["x", "0", "3", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    assert background.select_job_id(tmp_path) == "job"
    assert capsys.readouterr().out.count("正しい番号を入力してください。") == 3


def test_exit_selection_returns_none(tmp_path, monkeypatch):
    _named_job(tmp_path, "job")
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    assert background.select_job_id(tmp_path) is None


def test_no_jobs_exits_normally(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        background, "add_background_audio",
        lambda _args: pytest.fail("processing must not start"),
    )

    assert background.main(["--output-dir", str(tmp_path)]) == 0
    assert "背景音を追加できる動画がありません。" in capsys.readouterr().out


def _fake_commands(monkeypatch, calls: list[list[str]], *, audio_format=None):
    monkeypatch.setattr(background.shutil, "which", lambda value: f"/bin/{value}")
    audio_format = audio_format or {"codec_name": "aac", "sample_rate": "48000", "channels": 2}

    def fake_run(command, *, quiet=True):
        calls.append(command)
        if command[0].endswith("ffprobe"):
            if "stream=codec_name,sample_rate,channels" in command:
                return subprocess.CompletedProcess(
                    command, 0, stdout=json.dumps({"streams": [audio_format]}), stderr=""
                )
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


def test_mix_normalizes_inputs_and_outputs_48k_stereo_aac(tmp_path, monkeypatch):
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
    assert "volume=-6dB" in graph
    assert graph.startswith(
        "[1:a:0]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[dub];"
        "[2:a:0]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,"
    )
    assert "[dub][background]amix=" in graph
    assert graph.endswith(
        "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[mixed]"
    )
    assert "duration=10.000000" in graph
    assert final[final.index("-c:v") + 1] == "copy"
    assert final[final.index("-c:a") + 1] == "aac"
    assert final[final.index("-ar") + 1] == "48000"
    assert final[final.index("-ac") + 1] == "2"
    manifest = json.loads((job / "09_background" / "background_manifest.json").read_text())
    assert manifest["success"] is True
    assert manifest["cache_reused"] is False
    assert manifest["final_duration"] == 10.0
    assert manifest["final_audio_format"] == {
        "codec_name": "aac", "sample_rate": 48000, "channels": 2,
    }


def test_default_background_volume_is_minus_six_db(tmp_path):
    assert _args(tmp_path).background_db == -6.0


@pytest.mark.parametrize("audio_format", [
    {"codec_name": "aac", "sample_rate": "24000", "channels": 2},
    {"codec_name": "aac", "sample_rate": "48000", "channels": 1},
    {"codec_name": "mp3", "sample_rate": "48000", "channels": 2},
])
def test_invalid_final_audio_format_preserves_existing_output(
        tmp_path, monkeypatch, audio_format):
    job = _job(tmp_path)
    output = job / "dubbed_video_with_bg.mp4"
    output.write_bytes(b"previous-success")
    calls = []
    _fake_commands(monkeypatch, calls, audio_format=audio_format)

    with pytest.raises(background.BackgroundAudioError, match="Invalid final audio format"):
        background.add_background_audio(_args(tmp_path))

    assert output.read_bytes() == b"previous-success"
    assert not (job / ".dubbed_video_with_bg.tmp.mp4").exists()
    assert (job / "dubbed_video.mp4").read_bytes() == b"standard-must-survive"
    manifest = json.loads((job / "09_background" / "background_manifest.json").read_text())
    assert manifest["success"] is False


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


def test_success_manifest_write_failure_does_not_commit_output(tmp_path, monkeypatch):
    job = _job(tmp_path)
    calls = []
    _fake_commands(monkeypatch, calls)
    original_write_text = Path.write_text

    def fail_success_manifest(path, data, *args, **kwargs):
        if path.name == ".background_manifest.success.tmp":
            raise OSError("success manifest unavailable")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_success_manifest)

    try:
        background.add_background_audio(_args(tmp_path))
    except OSError as exc:
        assert str(exc) == "success manifest unavailable"
    else:
        raise AssertionError("expected manifest write failure")

    assert not (job / "dubbed_video_with_bg.mp4").exists()
    assert not (job / ".dubbed_video_with_bg.tmp.mp4").exists()
    assert (job / "dubbed_video.mp4").read_bytes() == b"standard-must-survive"
    manifest = json.loads((job / "09_background" / "background_manifest.json").read_text())
    assert manifest["success"] is False


def test_failure_manifest_write_does_not_hide_processing_error(tmp_path, monkeypatch):
    job = _job(tmp_path)
    monkeypatch.setattr(background.shutil, "which", lambda value: f"/bin/{value}")

    def processing_failure(_command, *, quiet=True):
        raise background.BackgroundAudioError("original processing failure")

    def manifest_failure(_path, _payload):
        raise OSError("manifest failure")

    monkeypatch.setattr(background, "_run", processing_failure)
    monkeypatch.setattr(background, "_write_manifest_atomic", manifest_failure)

    try:
        background.add_background_audio(_args(tmp_path))
    except background.BackgroundAudioError as exc:
        assert str(exc) == "original processing failure"
    else:
        raise AssertionError("expected original processing failure")

    assert not (job / "dubbed_video_with_bg.mp4").exists()
    assert (job / "dubbed_video.mp4").read_bytes() == b"standard-must-survive"
