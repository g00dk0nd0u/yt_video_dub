import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_skip_tts_does_not_run_generator_or_reuse_stale_metrics(
    tmp_path, load_script, monkeypatch
):
    module = load_script("91_run_local_tts_pipeline.py")
    manifest = tmp_path / "job/06_tts/tts_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"run_metrics": {"generated_units": 50}}))
    calls = []
    monkeypatch.setattr(module, "_run_step",
                        lambda _label, filename, _args: calls.append(filename))
    monkeypatch.setattr(module, "_probe_video_duration", lambda *args: None)

    module.main(["--job-id", "job", "--output-dir", str(tmp_path),
                 "--skip-build-translated", "--skip-tts"])

    assert "06_generate_tts_segments.py" not in calls
    assert "07_build_dub_audio.py" in calls
    payload = json.loads((tmp_path / "job/10_metrics/benchmark.json").read_text())
    assert payload["stages"]["tts"] == {"status": "skipped", "seconds": 0.0}
    assert payload["tts"]["status"] == "skipped"
    assert payload["tts"]["generated_units"] == 0


def test_user_tool_audio_no_passes_skip_tts_without_resume(monkeypatch):
    path = Path(__file__).parents[1] / "user_tools/02_make_video.py"
    spec = importlib.util.spec_from_file_location("test_user_make_video", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []
    monkeypatch.setattr(module, "_latest_video_id", lambda: "job")
    monkeypatch.setattr(module, "_prompt_with_default", lambda *args: "job")
    answers = iter([False, False])
    monkeypatch.setattr(module, "_prompt_yes_no", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(module, "_load_pipeline_module",
                        lambda: SimpleNamespace(main=lambda args: captured.extend(args)))
    fake_paths = SimpleNamespace(
        dubbed_video_path=Path("output/job/dubbed_video.mp4"),
        job_dir=Path("output/job"),
    )
    monkeypatch.setattr(module, "_load_path_layout_module", lambda: SimpleNamespace(
        build_job_paths=lambda *args: fake_paths
    ))

    module.main()

    assert "--skip-tts" in captured
    assert "--resume" not in captured
