import json
import threading
from pathlib import Path


SOURCE_PROBE = {
    "codec_name": "av1", "width": 1920, "height": 1080,
    "avg_frame_rate": "30/1", "duration": "10.000", "pix_fmt": "yuv420p",
    "color_space": "bt709", "color_transfer": "bt709", "color_primaries": "bt709",
    "color_range": "tv", "sample_aspect_ratio": "1:1", "audio_stream_present": True,
}
OUTPUT_PROBE = {**SOURCE_PROBE, "codec_name": "h264"}


class FakeProcess:
    next_pid = 1000

    def __init__(self, command, **kwargs):
        self.command, self.kwargs, self.returncode = command, kwargs, None
        self.pid = FakeProcess.next_pid
        FakeProcess.next_pid += 1
        Path(command[-1]).write_bytes(b"encoded")

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


def _job(tmp_path, codec="av1"):
    source = tmp_path / "job/.cache/work/01_source/source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(codec.encode())
    return source


def _mock_tools(module, monkeypatch, source, *, output_probe=OUTPUT_PROBE):
    def probe(_binary, path):
        return SOURCE_PROBE if Path(path) == source else output_probe
    monkeypatch.setattr(module, "_probe", probe)
    monkeypatch.setattr(module, "_ffmpeg_version", lambda _binary: "ffmpeg test")


def test_h264_source_does_not_start_background_process(tmp_path, load_script, monkeypatch):
    module = load_script("video_compat.py")
    source = _job(tmp_path, "h264")
    monkeypatch.setattr(module, "_probe", lambda *_: {**SOURCE_PROBE, "codec_name": "h264"})
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("H.264 must not start ffmpeg")))

    result = module.start_job("job", str(tmp_path)).finish()

    assert result["source_video_codec"] == "h264"
    assert result["compatibility_task_started"] is False


def test_background_success_publishes_validated_cache_and_command(tmp_path, load_script, monkeypatch):
    module = load_script("video_compat.py")
    source = _job(tmp_path)
    _mock_tools(module, monkeypatch, source)
    processes = []
    monkeypatch.setattr(module.subprocess, "Popen",
                        lambda command, **kwargs: processes.append(FakeProcess(command, **kwargs)) or processes[-1])

    task = module.start_job("job", str(tmp_path))
    assert task.started is True
    result = task.finish()

    command = processes[0].command
    joined = " ".join(command)
    assert "-nostdin" in command
    assert "-map 0:v:0 -map 0:a:0?" in joined
    assert "-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p" in joined
    assert "-c:a copy" in joined and "-movflags +faststart" in joined
    assert (tmp_path / "job/.cache/work/01_source/compat_h264.mp4").read_bytes() == b"encoded"
    assert result["compatibility_background_used"] is True
    assert result["compatibility_transcode_seconds"] >= 0
    assert result["compatibility_wait_seconds"] >= 0


def test_matching_identity_reuses_cache_without_ffmpeg(tmp_path, load_script, monkeypatch):
    module = load_script("video_compat.py")
    source = _job(tmp_path)
    cache = tmp_path / "job/.cache/work/01_source/compat_h264.mp4"
    cache.write_bytes(b"cached")
    _mock_tools(module, monkeypatch, source)
    identity = module._identity(source, SOURCE_PROBE, "ffmpeg test")
    (cache.with_suffix(".json")).write_text(json.dumps({"identity": identity}))
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("matching cache must not start ffmpeg")))

    result = module.start_job("job", str(tmp_path)).finish()

    assert result["compatibility_cache_reused"] is True
    assert result["compatibility_video_path"] == cache


def test_matching_cache_reuses_when_optional_color_metadata_is_missing(
    tmp_path, load_script, monkeypatch
):
    module = load_script("video_compat.py")
    source = _job(tmp_path)
    cache = tmp_path / "job/.cache/work/01_source/compat_h264.mp4"
    cache.write_bytes(b"cached")
    optional_missing = {
        **SOURCE_PROBE,
        "color_space": None,
        "color_transfer": None,
        "color_primaries": None,
    }
    output_probe = {**optional_missing, "codec_name": "h264"}
    monkeypatch.setattr(module, "_ffmpeg_version", lambda _binary: "ffmpeg test")
    monkeypatch.setattr(
        module,
        "_probe",
        lambda _binary, path: optional_missing if Path(path) == source else output_probe,
    )
    identity = module._identity(source, optional_missing, "ffmpeg test")
    cache.with_suffix(".json").write_text(json.dumps({"identity": identity}))
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("missing optional metadata must not restart ffmpeg")))

    result = module.start_job("job", str(tmp_path)).finish()

    assert result["compatibility_cache_reused"] is True
    assert result["compatibility_video_path"] == cache


def test_source_identity_change_starts_new_encode(tmp_path, load_script, monkeypatch):
    module = load_script("video_compat.py")
    source = _job(tmp_path)
    cache = tmp_path / "job/.cache/work/01_source/compat_h264.mp4"
    cache.write_bytes(b"cached")
    _mock_tools(module, monkeypatch, source)
    stale = module._identity(source, SOURCE_PROBE, "ffmpeg test")
    stale["source_sha256"] = "stale"
    cache.with_suffix(".json").write_text(json.dumps({"identity": stale}))
    processes = []
    monkeypatch.setattr(module.subprocess, "Popen",
                        lambda command, **kwargs: processes.append(FakeProcess(command, **kwargs)) or processes[-1])

    task = module.start_job("job", str(tmp_path))

    assert task.started is True and task.reused is False and len(processes) == 1
    task.cancel()


def test_validation_failure_removes_part_and_reports_fallback(tmp_path, load_script, monkeypatch):
    module = load_script("video_compat.py")
    source = _job(tmp_path)
    _mock_tools(module, monkeypatch, source, output_probe={**OUTPUT_PROBE, "width": 1280})
    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)

    task = module.start_job("job", str(tmp_path))
    part = task.part_path
    result = task.finish()

    assert result["compatibility_failure"]
    assert result["compatibility_video_path"] is None
    assert not part.exists()


def test_cancel_terminates_process_group_and_cleans_part(tmp_path, load_script, monkeypatch):
    module = load_script("video_compat.py")
    source = _job(tmp_path)
    _mock_tools(module, monkeypatch, source)
    stopped = threading.Event()
    process = FakeProcess(["ffmpeg", str(tmp_path / "unused")])
    process.returncode = None
    def wait(timeout=None):
        stopped.wait()
        return process.returncode
    process.wait = wait
    part = tmp_path / "part.mp4"
    part.write_bytes(b"partial")
    task = module.CompatibilityTask(process=process, stderr_file=None, part_path=part,
                                    source_path=source, source_probe=SOURCE_PROBE, started=True)
    signals = []
    def killpg(pid, sig):
        signals.append((pid, sig))
        if sig == module.signal.SIGKILL:
            process.returncode = -9
            stopped.set()
    monkeypatch.setattr(module.os, "killpg", killpg)
    monkeypatch.setattr(module, "CANCEL_TIMEOUT_SECONDS", 0.01)

    task.cancel()

    assert [sig for _, sig in signals] == [module.signal.SIGTERM, module.signal.SIGKILL]
    assert not part.exists() and task.process is None
