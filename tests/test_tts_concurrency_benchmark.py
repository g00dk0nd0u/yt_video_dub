from __future__ import annotations

import io
import json
import struct
import time
import wave
from pathlib import Path

import pytest


def _wav_bytes(seconds: float, rate: int = 1000) -> bytes:
    buffer = io.BytesIO()
    frames = int(seconds * rate)
    with wave.open(buffer, "wb") as writer:
        writer.setparams((1, 2, rate, frames, "NONE", "not compressed"))
        writer.writeframes(struct.pack("<h", 1000) * frames)
    return buffer.getvalue()


def _segments():
    return [
        {"segment_id": "utt_0001", "text": "一", "start": 0.0, "end": 1.0},
        {"segment_id": "utt_0002", "text": "二", "start": 1.0, "end": 2.0},
        {"segment_id": "utt_0003", "text": "三", "start": 2.0, "end": 3.0},
    ]


def test_workload_selection_and_hash_are_deterministic(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")
    first = module.select_workload(_segments(), segment_ids=["utt_0003", "utt_0001"])
    second = module.select_workload(_segments(), segment_ids=["utt_0001", "utt_0003"])
    assert [item[1]["segment_id"] for item in first] == ["utt_0001", "utt_0003"]
    assert first == second
    assert module.workload_hash(first, 10) == module.workload_hash(second, 10)


def test_workload_hash_changes_with_text_or_selection(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")
    selected = module.select_workload(_segments(), limit=2)
    changed = _segments()
    changed[0]["text"] = "変更"
    assert module.workload_hash(selected, 10) != module.workload_hash(
        module.select_workload(changed, limit=2), 10
    )
    assert module.workload_hash(selected, 10) != module.workload_hash(
        module.select_workload(_segments(), limit=1), 10
    )


def test_worker_validation_and_executor_configuration(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")
    assert module.build_parser().parse_args(["--job-id", "j", "--workers", "1"]).workers == 1
    assert module.build_parser().parse_args(["--job-id", "j", "--workers", "2"]).workers == 2
    assert module.build_parser().parse_args(["--job-id", "j", "--workers", "4"]).workers == 4
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(["--job-id", "j", "--workers", "3"])

    seen = []

    class RecordingExecutor(module.ThreadPoolExecutor):
        def __init__(self, max_workers):
            seen.append(max_workers)
            super().__init__(max_workers=max_workers)

    workload = list(enumerate(_segments(), 1))
    for workers in (1, 2, 4):
        module.run_workload(workload, workers, lambda item: {
            "index": item[0], "segment_id": item[1]["segment_id"], "status": "completed"
        }, RecordingExecutor)
    assert seen == [1, 2, 4]


def test_completion_order_does_not_change_result_order(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")

    def worker(item):
        time.sleep({1: 0.03, 2: 0.02, 3: 0.0}[item[0]])
        return {"index": item[0], "segment_id": item[1]["segment_id"], "status": "completed"}

    results = module.run_workload(list(enumerate(_segments(), 1)), 4, worker)
    assert [result["index"] for result in results] == [1, 2, 3]


def test_failed_unit_is_retained_with_other_results_and_sample_is_valid(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")
    workload = list(enumerate(_segments(), 1))

    def worker(item):
        if item[0] == 2:
            raise RuntimeError("failed bearer secretvalue")
        return {
            "index": item[0], "segment_id": item[1]["segment_id"], "status": "completed",
            "fit_status": "ok", "audio_query_wall_seconds": 0.1,
            "synthesis_wall_seconds": 0.2, "normal_synthesis_count": 1,
            "speed_fit_synthesis_count": 0, "error_type": None, "error_message": None,
        }

    results = module.run_workload(workload, 2, worker)
    sample = module.build_sample("job", 2, "http://aivis", 10, workload, results, 1.0)
    assert [item["status"] for item in results] == ["completed", "failed", "completed"]
    assert sample["status"] == "completed_with_errors"
    assert sample["errors"][0]["segment_id"] == "utt_0002"
    assert "secretvalue" not in json.dumps(sample)


def test_duration_fitting_counters_with_mock_wavs(load_script, monkeypatch):
    module = load_script("92_benchmark_tts_concurrency.py")
    durations = iter([0.9, 1.08, 0.98, 1.3])

    class Response:
        ok = True
        status_code = 200

        def __init__(self, content=b""):
            self.content = content

        def json(self):
            return {}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return Response() if url.endswith("audio_query") else Response(_wav_bytes(next(durations)))

    monkeypatch.setattr(module.requests, "Session", Session)
    workload = list(enumerate(_segments(), 1))
    results = module.run_workload(
        workload, 1, lambda item: module.benchmark_unit(item, "http://aivis", 10, 1.0)
    )
    sample = module.build_sample("job", 1, "http://aivis", 10, workload, results, 1.0)
    assert (sample["fit_ok_count"], sample["fit_fitted_count"], sample["fit_ng_count"]) == (1, 1, 1)
    assert sample["normal_synthesis_count"] == 3
    assert sample["speed_fit_synthesis_count"] == 1


def test_empty_units_are_excluded_from_fit_and_throughput(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")
    segments = _segments() + [
        {"segment_id": "empty_1", "text": "", "start": 3.0, "end": 4.0},
        {"segment_id": "empty_2", "text": "", "start": 4.0, "end": 5.0},
    ]
    workload = list(enumerate(segments, 1))
    fit_statuses = ["ok", "fitted", "ng"]
    results = [{
        "index": index, "segment_id": segment["segment_id"], "status": "completed",
        "fit_status": fit_statuses[index - 1], "audio_query_wall_seconds": 0.0,
        "synthesis_wall_seconds": 0.0, "normal_synthesis_count": 1,
        "speed_fit_synthesis_count": int(index == 2),
        "error_type": None, "error_message": None,
    } for index, segment in workload[:3]]
    results.extend([{
        "index": index, "segment_id": segment["segment_id"], "status": "skipped_empty",
        "fit_status": None, "audio_query_wall_seconds": 0.0,
        "synthesis_wall_seconds": 0.0, "normal_synthesis_count": 0,
        "speed_fit_synthesis_count": 0, "error_type": None, "error_message": None,
    } for index, segment in workload[3:]])

    sample = module.build_sample("job", 1, "http://aivis", 10, workload, results, 2.0)
    assert sample["selected_units"] == 5
    assert sample["speech_units"] == 3
    assert sample["skipped_empty_units"] == 2
    assert sample["successful_speech_units"] == 3
    assert (sample["fit_ok_count"], sample["fit_fitted_count"], sample["fit_ng_count"]) == (1, 1, 1)
    assert sample["units_per_second"] == 1.5


def test_throughput_excludes_empty_and_failed_speech(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")
    segments = _segments() + [
        {"segment_id": f"empty_{number}", "text": "", "start": 3.0, "end": 4.0}
        for number in range(3)
    ]
    workload = list(enumerate(segments, 1))
    results = []
    for index, segment in workload:
        empty = not segment["text"]
        failed = index == 3
        results.append({
            "index": index, "segment_id": segment["segment_id"],
            "status": "skipped_empty" if empty else ("failed" if failed else "completed"),
            "fit_status": None if empty or failed else "ok",
            "audio_query_wall_seconds": 0.0, "synthesis_wall_seconds": 0.0,
            "normal_synthesis_count": 0 if empty else 1, "speed_fit_synthesis_count": 0,
            "error_type": "Timeout" if failed else None,
            "error_message": "timeout" if failed else None,
        })
    sample = module.build_sample("job", 1, "http://aivis", 10, workload, results, 2.0)
    assert sample["successful_speech_units"] == 2
    assert sample["units_per_second"] == 1.0


def test_all_empty_workload_has_zero_throughput(load_script):
    module = load_script("92_benchmark_tts_concurrency.py")
    segments = [{"segment_id": "empty", "text": "", "start": 0.0, "end": 1.0}]
    workload = list(enumerate(segments, 1))
    results = module.run_workload(
        workload, 1, lambda item: module.benchmark_unit(item, "http://aivis", 10, 1.0)
    )
    sample = module.build_sample("job", 1, "http://aivis", 10, workload, results, 1.0)
    assert sample["status"] == "completed"
    assert sample["speech_units"] == 0
    assert sample["skipped_empty_units"] == 1
    assert sample["successful_speech_units"] == 0
    assert sample["units_per_second"] == 0.0
    assert (sample["fit_ok_count"], sample["fit_fitted_count"], sample["fit_ng_count"]) == (0, 0, 0)


def test_speed_fit_failure_preserves_partial_metrics(load_script, monkeypatch):
    module = load_script("92_benchmark_tts_concurrency.py")

    class Response:
        ok = True
        status_code = 200

        def __init__(self, content=b""):
            self.content = content

        def json(self):
            return {}

    class Session:
        syntheses = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            time.sleep(0.001)
            if url.endswith("audio_query"):
                return Response()
            self.syntheses += 1
            if self.syntheses == 2:
                raise TimeoutError("speed fit timeout")
            return Response(_wav_bytes(1.08))

    monkeypatch.setattr(module.requests, "Session", Session)
    result = module.benchmark_unit((1, _segments()[0]), "http://aivis", 10, 1.0)
    assert result["status"] == "failed"
    assert result["normal_synthesis_count"] == 1
    assert result["speed_fit_synthesis_count"] == 0
    assert result["audio_query_wall_seconds"] > 0
    assert result["synthesis_wall_seconds"] > 0


def test_normal_synthesis_failure_preserves_attempt_timing(load_script, monkeypatch):
    module = load_script("92_benchmark_tts_concurrency.py")

    class Response:
        ok = True
        status_code = 200

        def json(self):
            return {}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            time.sleep(0.001)
            if url.endswith("synthesis"):
                raise TimeoutError("normal timeout")
            return Response()

    monkeypatch.setattr(module.requests, "Session", Session)
    result = module.benchmark_unit((1, _segments()[0]), "http://aivis", 10, 1.0)
    assert result["status"] == "failed"
    assert result["normal_synthesis_count"] == 0
    assert result["audio_query_wall_seconds"] > 0
    assert result["synthesis_wall_seconds"] > 0


def test_sample_paths_are_unique(load_script, tmp_path):
    module = load_script("92_benchmark_tts_concurrency.py")
    sample = {"workers": 1}
    first = module.save_sample(tmp_path, sample.copy())
    second = module.save_sample(tmp_path, sample.copy())
    assert first != second
    assert first.exists() and second.exists()


def test_comparison_summary_and_mismatch_warning(load_script):
    module = load_script("93_compare_tts_benchmarks.py")
    samples = []
    for workers in (1, 2, 4):
        samples.append({
            "workers": workers, "selected_units": 3, "tts_wall_seconds": 4.0,
            "units_per_second": 0.75, "normal_synthesis_count": 3,
            "speed_fit_synthesis_count": 1, "fit_ok_count": 1,
            "fit_fitted_count": 1, "fit_ng_count": 1, "errors": [],
            "workload_hash": "same", "speaker_id": 10, "base_url": "http://aivis",
            "benchmark_schema_version": 1, "max_speed_scale": 1.15,
            "timeout_seconds": 30.0, "speech_units": 3, "skipped_empty_units": 0,
            "hardware": {"system": "Darwin", "machine": "arm64"},
        })
    summary = module.format_summary(samples)
    assert all(str(workers) in summary for workers in (1, 2, 4))
    assert "NOT COMPARABLE" not in summary
    samples[-1]["workload_hash"] = "different"
    assert "NOT COMPARABLE: workload_hash" in module.format_summary(samples)


@pytest.mark.parametrize(
    ("field", "value", "warning"),
    [
        ("benchmark_schema_version", 2, "benchmark_schema_version"),
        ("max_speed_scale", 1.1, "max_speed_scale"),
        ("timeout_seconds", 10.0, "timeout_seconds"),
        ("hardware.system", "Linux", "hardware.system"),
        ("hardware.machine", "x86_64", "hardware.machine"),
    ],
)
def test_comparison_reproducibility_metadata_mismatch(load_script, field, value, warning):
    module = load_script("93_compare_tts_benchmarks.py")
    common = {
        "workload_hash": "same", "speaker_id": 10, "base_url": "http://aivis",
        "selected_units": 3, "benchmark_schema_version": 1, "max_speed_scale": 1.15,
        "timeout_seconds": 30.0, "hardware": {"system": "Darwin", "machine": "arm64"},
    }
    changed = json.loads(json.dumps(common))
    target = changed
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    assert any(warning in item for item in module.comparability_warnings([common, changed]))


def test_comparison_formatter_handles_null_failed_sample(load_script):
    module = load_script("93_compare_tts_benchmarks.py")
    sample = {
        "workers": 4, "speech_units": 2, "tts_wall_seconds": None,
        "units_per_second": None, "errors": None, "workload_hash": None,
    }
    summary = module.format_summary([sample])
    assert "      -" in summary
    assert "NOT COMPARABLE" not in summary


def test_production_scripts_remain_single_worker():
    repo_root = Path(__file__).parents[1]
    production = (repo_root / "scripts/06_generate_tts_segments.py").read_text()
    user_tool = (repo_root / "user_tools/02_make_video.py").read_text()
    assert "ThreadPoolExecutor" not in production
    assert "--workers" not in production
    assert "--workers" not in user_tool
