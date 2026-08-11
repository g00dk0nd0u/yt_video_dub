import importlib.util
from pathlib import Path

import pytest
import json


def _module():
    path = Path(__file__).parents[1] / "user_tools/00_dub_youtube_experimental.py"
    spec = importlib.util.spec_from_file_location("experimental_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_order_job_propagation_and_canonical_path(tmp_path):
    module = _module()
    calls = []
    stages = {name: (lambda name=name: calls.append(name)) for name in
              ("Prepare", "Translation", "Build", "Preflight", "TTS", "Audio", "Mux")}
    result = module.run("https://www.youtube.com/watch?v=abc123", output_dir=str(tmp_path),
                        stages=stages)
    assert calls == ["Prepare", "Translation", "Build", "Preflight", "TTS", "Audio", "Mux"]
    assert result == tmp_path / "abc123/dubbed_video.mp4"


@pytest.mark.parametrize("failed,not_called", [
    ("Translation", "TTS"), ("Preflight", "TTS"), ("TTS", "Mux"),
])
def test_failure_stops_downstream(failed, not_called):
    module = _module()
    calls = []
    def callback(name):
        calls.append(name)
        if name == failed:
            raise RuntimeError("boom")
    stages = {name: (lambda name=name: callback(name)) for name in
              ("Prepare", "Translation", "Build", "Preflight", "TTS", "Audio", "Mux")}
    with pytest.raises(RuntimeError, match=f"{failed} failed"):
        module.run("https://youtu.be/abc123", stages=stages)
    assert not_called not in calls


def test_url_prompt_once(monkeypatch):
    module = _module()
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "")
    assert module.main([]) == 1
    assert len(prompts) == 1


def test_invalid_url_does_not_advertise_stale_diagnostic(tmp_path, capsys):
    module = _module()
    stale = tmp_path / "latest_run.txt"
    stale.write_text("previous run")
    assert module.main(["--url", "https://example.com/not-youtube",
                        "--output-dir", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "Diagnostic:" not in output
    assert stale.read_text() == "previous run"


def test_success_writes_diagnostics_and_zero_quality_summary(tmp_path):
    module = _module()
    job = tmp_path / "abc123"
    def audio():
        path = job / "07_audio/dub_audio_manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"warnings_count": 0, "items": []}))
    stages = {name: (lambda: None) for name in
              ("Prepare", "Translation", "Build", "Preflight", "Audio", "Mux")}
    stages["TTS"] = lambda: {"run_metrics": {"failed_units": 0, "fit_ng_count": 0}, "items": []}
    stages["Audio"] = audio
    module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)
    summary = json.loads((job / "run_summary.json").read_text())
    assert summary["final"]["success"] is True
    assert summary["audio_qa"] == {"warnings_count": 0, "clipped_count": 0, "overflow_count": 0}
    assert (tmp_path / "latest_run.txt").exists()


def test_ng_fails_before_audio_and_finalizes_diagnostic(tmp_path):
    module = _module()
    calls = []
    stages = {name: (lambda name=name: calls.append(name)) for name in
              ("Prepare", "Translation", "Build", "Preflight", "Audio", "Mux")}
    stages["TTS"] = lambda: {"run_metrics": {"failed_units": 0, "fit_ng_count": 1},
                              "items": [{"segment_id": "s1", "fit_status": "ng"}]}
    with pytest.raises(RuntimeError, match="no repair stage"):
        module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)
    assert "Audio" not in calls and "Mux" not in calls
    text = (tmp_path / "latest_run.txt").read_text()
    assert "failed_stage: Repair #1" in text
    assert "segment_id" in text


def test_closed_repair_loop_reaches_zero_clip_success(tmp_path):
    module = _module()
    job = tmp_path / "abc123"
    calls, tts_round = [], iter([
        {"tts_provider": "edge", "run_metrics": {"failed_units": 0, "fit_ng_count": 1,
          "generated_units": 2, "reused_units": 0}, "items": [
            {"segment_id": "keep", "fit_status": "ok", "final_tts_duration": .7},
            {"segment_id": "repair", "start": 1, "end": 2, "text": "長い文",
             "available_duration": 1, "raw_tts_duration": 1.4,
             "final_tts_duration": 1.4, "rate": "+0%", "fit_status": "ng"}]},
        {"tts_provider": "edge", "run_metrics": {"failed_units": 0, "fit_ng_count": 0,
          "generated_units": 1, "reused_units": 1}, "items": [
            {"segment_id": "keep", "status": "reused", "fit_status": "ok", "final_tts_duration": .7},
            {"segment_id": "repair", "status": "generated", "fit_status": "ok",
             "final_tts_duration": .8}]},
    ])
    def audio():
        calls.append("Audio")
        path = job / "07_audio/dub_audio_manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"warnings_count": 0, "items": [
            {"clipped": False, "timing_status": "ok"}]}))
    stages = {name: (lambda name=name: calls.append(name)) for name in
              ("Prepare", "Translation", "Build", "Preflight", "Mux")}
    stages.update(TTS=lambda: next(tts_round), Repair=lambda: [{"segment_id": "repair",
        "text_before": "長い文", "text_after": "短文", "target_chars": 2}], Audio=audio)
    module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)
    summary = json.loads((job / "run_summary.json").read_text())
    assert "Mux" in calls
    assert summary["tts"]["fit_ng_count"] == 0
    assert summary["tts"]["reused_units"] == 1
    assert summary["audio_qa"] == {"warnings_count": 0, "clipped_count": 0, "overflow_count": 0}
    assert summary["repairs"][0]["duration_after"] == .8
    assert "items" not in next(x for x in summary["stages"] if x["name"] == "TTS")["result"]


def test_remaining_ng_after_limit_never_muxes(tmp_path):
    module = _module()
    calls = []
    ng = {"run_metrics": {"failed_units": 0, "fit_ng_count": 1},
          "items": [{"segment_id": "x", "fit_status": "ng"}]}
    stages = {name: (lambda name=name: calls.append(name)) for name in
              ("Prepare", "Translation", "Build", "Preflight", "Audio", "Mux")}
    stages.update(TTS=lambda: ng, Repair=lambda: [])
    with pytest.raises(RuntimeError, match="after 2 repair rounds"):
        module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)
    assert "Audio" not in calls and "Mux" not in calls


def test_tts_stage_summary_does_not_duplicate_segment_items():
    module = _module()
    result = module._stage_result("TTS", {"tts_provider": "edge", "items": [
        {"segment_id": str(index), "text": "長文" * 100} for index in range(1000)],
        "run_metrics": {"selected_units": 1000, "generated_units": 1000,
                        "reused_units": 0, "failed_units": 0, "fit_ng_count": 0}})
    assert result == {"provider": "edge", "selected_units": 1000, "generated_units": 1000,
                      "reused_units": 0, "failed_units": 0, "fit_ng_count": 0}
