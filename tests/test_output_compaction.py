from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _runner():
    path = Path(__file__).parents[1] / "user_tools/00_dub_youtube.py"
    spec = importlib.util.spec_from_file_location("compaction_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _paths(tmp_path):
    sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
    from path_layout import build_job_paths
    paths = build_job_paths(tmp_path, "job")
    paths.ensure_prepare_dirs()
    paths.segments_dir.mkdir(parents=True)
    paths.tts_dir.mkdir(parents=True)
    paths.dubbed_video_path.write_bytes(b"video")
    paths.source_video_path.write_bytes(b"source")
    paths.transcript_normalized_json_path.write_text(json.dumps({"units": [{
        "unit_id": "u1", "source_text": "hello", "source_start": 0, "source_end": 1,
    }]}))
    paths.translated_segments_json_path.write_text(json.dumps({"segments": [{
        "segment_id": "u1", "start": 0, "end": 1, "text": "こんにちは",
    }]}))
    return paths


def test_success_compacts_only_after_validated_audio_and_diagnostic(tmp_path, monkeypatch):
    module, paths = _runner(), _paths(tmp_path)
    from run_diagnostics import RunReport
    report = RunReport(tmp_path, "job", "https://www.youtube.com/watch?v=job")
    report.data["tts"] = [{"segment_id": "u1", "fit_status": "ok", "rate": "+0%"}]

    def run(command, **_kwargs):
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"copied-audio")
            assert command[command.index("-c:a") + 1] == "copy"
            assert command[command.index("-map") + 1] == "0:a:0"
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"streams": [{"codec_name": "aac"}],
                                    "format": {"duration": "1.0"}}), "")

    monkeypatch.setattr(module.subprocess, "run", run)
    module._compact_success(paths, report)

    assert {p.name for p in paths.job_dir.iterdir()} == {"dubbed_video.mp4", ".cache"}
    assert {p.name for p in paths.cache_dir.iterdir()} == {"diagnostic.json", "source_audio.mka"}
    diagnostic = json.loads(paths.diagnostic_path.read_text())
    assert diagnostic["translation"] == [{"segment_id": "u1", "start": 0, "end": 1,
                                           "source_text": "hello",
                                           "final_translated_text": "こんにちは"}]
    assert diagnostic["tts"][0]["fit_status"] == "ok"


def test_compaction_failure_keeps_video_and_work_evidence(tmp_path, monkeypatch):
    module, paths = _runner(), _paths(tmp_path)
    from run_diagnostics import RunReport
    report = RunReport(tmp_path, "job", "url")
    monkeypatch.setattr(module, "_publish_source_audio",
                        lambda _paths: (_ for _ in ()).throw(RuntimeError("cache failed")))
    with pytest.raises(RuntimeError, match="cache failed"):
        module._compact_success(paths, report)
    assert paths.dubbed_video_path.read_bytes() == b"video"
    assert paths.work_dir.is_dir()
