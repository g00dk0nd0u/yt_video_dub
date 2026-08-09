import json

import pytest

from performance_metrics import StageTimer, build_benchmark, calculate_rtf, write_benchmark


def test_stage_timer_records_elapsed_and_skipped_status():
    ticks = iter([10.0, 10.375])
    timer = StageTimer(clock=lambda: next(ticks))
    timer.run("tts", lambda: "done")
    timer.skip("mux")
    assert timer.stages["tts"] == {"status": "completed", "seconds": 0.375}
    assert timer.stages["mux"] == {"status": "skipped", "seconds": 0.0}


def test_benchmark_json_required_fields_and_rtf(tmp_path):
    payload = build_benchmark(
        job_id="job", run_mode="resume", total_pipeline_seconds=30,
        stages={"tts": {"status": "completed", "seconds": 20}},
        tts={"generated_units": 1}, video_duration_seconds=120,
    )
    path = tmp_path / "10_metrics/benchmark.json"
    write_benchmark(path, payload)
    saved = json.loads(path.read_text())
    assert {"job_id", "run_mode", "total_pipeline_seconds", "stages", "tts"} <= saved.keys()
    assert saved["rtf"] == pytest.approx(0.25)
    assert calculate_rtf(30, None) is None


def test_pipeline_selective_mode_and_translated_skip(tmp_path, load_script, monkeypatch):
    module = load_script("91_run_local_tts_pipeline.py")
    monkeypatch.setattr(module, "_run_step", lambda *args: None)
    monkeypatch.setattr(module, "_probe_video_duration", lambda *args: None)
    module.main([
        "--job-id", "job", "--output-dir", str(tmp_path),
        "--skip-build-translated", "--segment-id", "utt_0001",
        "--segment-id", "utt_0002",
    ])
    payload = json.loads((tmp_path / "job/10_metrics/benchmark.json").read_text())
    assert payload["run_mode"] == "selective_retry"
    assert payload["stages"]["translated_build"] == {
        "status": "skipped", "seconds": 0.0,
    }
    assert payload["stages"]["mux"]["status"] == "skipped"
