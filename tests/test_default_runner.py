import importlib.util
from pathlib import Path

import pytest
import json


def _module():
    path = Path(__file__).parents[1] / "user_tools/00_dub_youtube.py"
    spec = importlib.util.spec_from_file_location("default_runner", path)
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


@pytest.mark.parametrize("mux_diagnostic", [
    {"source_video_codec": "av1", "output_video_codec": "h264",
     "video_mode": "transcode", "compatibility_fallback_used": True},
    {"source_video_codec": "h264", "output_video_codec": "h264",
     "video_mode": "copy", "compatibility_fallback_used": False},
])
def test_mux_codec_decision_is_in_primary_diagnostics(tmp_path, mux_diagnostic):
    module = _module()
    job = tmp_path / "abc123"

    def audio():
        path = job / "07_audio/dub_audio_manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"warnings_count": 0, "items": []}))

    stages = {name: (lambda: None) for name in
              ("Prepare", "Translation", "Build", "Preflight")}
    stages.update(TTS=lambda: {
        "run_metrics": {"failed_units": 0, "fit_ng_count": 0}, "items": []},
        Audio=audio, Mux=lambda: mux_diagnostic)

    module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)

    summary = json.loads((job / "run_summary.json").read_text())
    mux_result = next(stage for stage in summary["stages"]
                      if stage["name"] == "Mux")["result"]
    diagnostic = (tmp_path / "latest_run.txt").read_text()
    for key, value in mux_diagnostic.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        assert key in mux_result and rendered in mux_result.lower()
        assert key in diagnostic and rendered in diagnostic.lower()
    assert "'video_codec':" not in mux_result
    assert "'video_codec':" not in diagnostic


@pytest.mark.parametrize("acquisition,expected", [
    ({"source_reused": False,
      "attempted_strategies": ["yt-dlp-default", "youtube-android-vr"],
      "strategy_failures": ["yt-dlp-default:download:http_403=true"],
      "successful_strategy": "youtube-android-vr"},
     ["attempted_strategies=yt-dlp-default,youtube-android-vr",
      "successful_strategy=youtube-android-vr"]),
    ({"source_reused": True, "attempted_strategies": [], "strategy_failures": []},
     ["source_reused=true"]),
])
def test_success_diagnostic_has_compact_acquisition_summary(tmp_path, acquisition, expected):
    module = _module()
    job = tmp_path / "abc123"

    def prepare():
        path = job / "01_source/job.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"acquisition": acquisition}))

    def audio():
        path = job / "07_audio/dub_audio_manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"warnings_count": 0, "items": []}))

    stages = {name: (lambda: None) for name in
              ("Translation", "Build", "Preflight", "Mux")}
    stages.update(Prepare=prepare, TTS=lambda: {
        "run_metrics": {"failed_units": 0, "fit_ng_count": 0}, "items": []}, Audio=audio)
    module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)
    diagnostic = (tmp_path / "latest_run.txt").read_text()
    summary = json.loads((job / "run_summary.json").read_text())
    prepare_result = next(stage for stage in summary["stages"]
                          if stage["name"] == "Prepare")["result"]
    for item in expected:
        assert item in diagnostic
        assert item in prepare_result


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


def test_unchanged_repair_stops_without_second_codex_call(tmp_path):
    module = _module(); calls = []
    ng = {"run_metrics": {"failed_units": 0, "fit_ng_count": 1}, "items": [
        {"segment_id": "x", "text": "same", "fit_status": "ng", "final_tts_duration": 2.0}]}
    stages = {name: (lambda name=name: calls.append(name)) for name in
              ("Prepare", "Translation", "Build", "Preflight", "Audio", "Mux")}
    stages["TTS"] = lambda: ng
    stages["Repair"] = lambda: calls.append("Repair") or [{"segment_id": "x",
        "text_before": "same", "text_after": "same"}]
    with pytest.raises(RuntimeError, match="fit_ng_count=1"):
        module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)
    assert calls.count("Repair") == 1
    assert "no_progress_reason" in (tmp_path / "latest_run.txt").read_text()
    assert "Audio" not in calls and "Mux" not in calls


def test_tts_stage_summary_does_not_duplicate_segment_items():
    module = _module()
    result = module._stage_result("TTS", {"tts_provider": "edge", "items": [
        {"segment_id": str(index), "text": "長文" * 100} for index in range(1000)],
        "run_metrics": {"selected_units": 1000, "generated_units": 1000,
                        "reused_units": 0, "failed_units": 0, "fit_ng_count": 0}})
    assert result == {"provider": "edge", "selected_units": 1000, "generated_units": 1000,
                      "reused_units": 0, "failed_units": 0, "fit_ng_count": 0}


def test_failed_tts_details_are_diagnostic_and_stop_audio_mux(tmp_path):
    module = _module()
    calls = []
    stages = {name: (lambda name=name: calls.append(name)) for name in
              ("Prepare", "Translation", "Build", "Preflight", "Audio", "Mux")}
    stages["TTS"] = lambda: {
        "run_metrics": {"failed_units": 1, "fit_ng_count": 0},
        "items": [{"status": "failed", "segment_id": "utt_0002", "start": 7.86,
                   "end": 9.97, "text": ">>", "error_type": "EdgeTTSError",
                   "error_message": "Edge TTS request failed.", "coalesced": False,
                   "provider_internal": "must not leak"}],
    }

    with pytest.raises(RuntimeError, match="TTS failed_units=1"):
        module.run("https://youtu.be/abc123", output_dir=str(tmp_path), stages=stages)

    assert "Audio" not in calls and "Mux" not in calls
    summary = json.loads((tmp_path / "abc123/run_summary.json").read_text())
    assert summary["failed_tts_items"] == [{
        "segment_id": "utt_0002", "start": 7.86, "end": 9.97, "text": ">>",
        "error_type": "EdgeTTSError", "error_message": "Edge TTS request failed.",
        "coalesced": False,
    }]
    diagnostic = (tmp_path / "latest_run.txt").read_text()
    assert "FAILED TTS ITEMS" in diagnostic
    assert "utt_0002" in diagnostic
    assert "provider_internal" not in diagnostic


def test_bare_video_id_is_canonicalized(tmp_path):
    module = _module()
    captured = {}
    stages = {name: (lambda: None) for name in
              ("Translation", "Build", "Preflight", "Audio", "Mux")}
    stages["Prepare"] = lambda: captured.update(url="called")
    stages["TTS"] = lambda: {"run_metrics": {"failed_units": 0, "fit_ng_count": 0}, "items": []}
    def audio():
        path = tmp_path / "OEkxKdhtQng/07_audio/dub_audio_manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"warnings_count": 0, "items": []}))
    stages["Audio"] = audio
    result = module.run("OEkxKdhtQng", output_dir=str(tmp_path), stages=stages)
    summary = json.loads((tmp_path / "OEkxKdhtQng/run_summary.json").read_text())
    assert result == tmp_path / "OEkxKdhtQng/dubbed_video.mp4"
    assert summary["run"]["input_url"] == "https://www.youtube.com/watch?v=OEkxKdhtQng"
