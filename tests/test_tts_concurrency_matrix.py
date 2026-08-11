from __future__ import annotations

import json
from pathlib import Path


def _segments():
    return [
        {"segment_id": "empty", "text": "", "start": 0.0, "end": 1.0},
        {"segment_id": "utt_1", "text": "一", "start": 1.0, "end": 2.0},
        {"segment_id": "utt_2", "text": "二", "start": 2.0, "end": 3.0},
    ]


def _args(module, tmp_path: Path):
    return module.build_parser().parse_args([
        "--job-id", "job", "--output-dir", str(tmp_path),
    ])


def _sample(module, workload, workers, status="completed", errors=None):
    sample = module.benchmark.build_sample(
        "job", workers, module.benchmark.DEFAULT_BASE_URL,
        module.benchmark.DEFAULT_SPEAKER_ID, workload,
        [{
            "index": index, "segment_id": segment["segment_id"],
            "status": "skipped_empty" if not segment["text"] else "completed",
            "fit_status": None if not segment["text"] else "ok",
            "audio_query_wall_seconds": 0.0, "synthesis_wall_seconds": 0.0,
            "normal_synthesis_count": int(bool(segment["text"])),
            "speed_fit_synthesis_count": 0, "error_type": None,
            "error_message": None,
        } for index, segment in workload], 1.0,
    )
    sample.update(status=status, errors=errors or [])
    return sample


def test_matrix_snapshots_once_warms_first_and_runs_fixed_order(load_script, monkeypatch, tmp_path):
    module = load_script("94_run_tts_concurrency_matrix.py")
    events, workload_ids, summary_workers = [], [], []
    counts = {"load": 0, "select": 0, "save_sample": 0}
    segments = _segments()

    monkeypatch.setattr(module.preflight, "run_preflight", lambda *_: events.append("preflight") or {"status": "ready"})

    def load(_path):
        counts["load"] += 1
        return segments

    def select(items, *_args):
        counts["select"] += 1
        return list(enumerate(items, 1))

    def warmup(item, *_args):
        events.append("warmup")
        assert item[1]["segment_id"] == "utt_1"
        return {"status": "completed"}

    def run_once(**kwargs):
        workers, workload = kwargs["workers"], kwargs["workload"]
        events.append(f"worker{workers}")
        workload_ids.append(id(workload))
        counts["save_sample"] += 1
        sample = _sample(module, workload, workers)
        path = kwargs["benchmark_directory"] / f"w{workers}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sample))
        return sample, path

    monkeypatch.setattr(module.benchmark, "load_segments", load)
    monkeypatch.setattr(module.benchmark, "select_workload", select)
    monkeypatch.setattr(module.benchmark, "benchmark_unit", warmup)
    monkeypatch.setattr(module.benchmark, "run_benchmark_once", run_once)
    monkeypatch.setattr(module.comparison, "format_summary", lambda samples: summary_workers.extend(s["workers"] for s in samples) or "summary")

    artifact, path, code = module.run_matrix(_args(module, tmp_path))
    assert code == 0
    assert events == ["preflight", "warmup", "worker1", "worker2", "worker4"]
    assert counts == {"load": 1, "select": 1, "save_sample": 3}
    assert len(set(workload_ids)) == 1
    assert summary_workers == [1, 2, 4]
    assert artifact["candidate_order"] == [1, 2, 4]
    assert artifact["segment_ids"] == ["empty", "utt_1", "utt_2"]
    assert all(item["path"].startswith("10_metrics/concurrency_benchmarks/") for item in artifact["samples"])
    assert path.parent.name == "matrices"
    assert len(list(path.parent.parent.glob("*.json"))) == 3
    assert artifact["status"] == "completed"
    assert artifact["comparability_status"] == "comparable"


def test_preflight_failure_stops_before_loading_or_aivis(load_script, monkeypatch, tmp_path):
    module = load_script("94_run_tts_concurrency_matrix.py")
    monkeypatch.setattr(module.preflight, "run_preflight", lambda *_: {"status": "not_ready"})
    monkeypatch.setattr(module.benchmark, "load_segments", lambda *_: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(module.benchmark, "benchmark_unit", lambda *_: (_ for _ in ()).throw(AssertionError()))
    artifact, path, code = module.run_matrix(_args(module, tmp_path))
    assert (artifact, path, code) == (None, None, 1)


def test_warmup_failure_saves_only_matrix_and_stops_candidates(load_script, monkeypatch, tmp_path):
    module = load_script("94_run_tts_concurrency_matrix.py")
    monkeypatch.setattr(module.preflight, "run_preflight", lambda *_: {"status": "ready"})
    monkeypatch.setattr(module.benchmark, "load_segments", lambda *_: _segments())
    monkeypatch.setattr(module.benchmark, "benchmark_unit", lambda *_: {
        "status": "failed", "error_type": "Timeout", "error_message": "safe timeout",
    })
    monkeypatch.setattr(module.benchmark, "run_benchmark_once", lambda **_: (_ for _ in ()).throw(AssertionError()))
    artifact, path, code = module.run_matrix(_args(module, tmp_path))
    assert code == 1 and artifact["status"] == "warmup_failed"
    assert artifact["samples"] == [] and path.exists()
    assert list(path.parent.parent.glob("*.json")) == []


def test_candidate_errors_are_summarized_without_losing_comparability(load_script, monkeypatch, tmp_path, capsys):
    module = load_script("94_run_tts_concurrency_matrix.py")
    monkeypatch.setattr(module.preflight, "run_preflight", lambda *_: {"status": "ready"})
    monkeypatch.setattr(module.benchmark, "load_segments", lambda *_: _segments())
    monkeypatch.setattr(module.benchmark, "benchmark_unit", lambda *_: {"status": "completed"})
    seen = []

    def run_once(**kwargs):
        workers, workload = kwargs["workers"], kwargs["workload"]
        seen.append(workers)
        errors = ([
            {"segment_id": "utt_1", "error_type": "Timeout", "error_message": "detail 1"},
            {"segment_id": "utt_2", "error_type": "Timeout", "error_message": "detail 2"},
        ] if workers == 4 else [])
        sample = _sample(
            module, workload, workers,
            "completed_with_errors" if workers == 4 else "completed", errors,
        )
        path = kwargs["benchmark_directory"] / f"w{workers}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        return sample, path

    monkeypatch.setattr(module.benchmark, "run_benchmark_once", run_once)
    artifact, _, code = module.run_matrix(_args(module, tmp_path))
    assert code == 0 and seen == [1, 2, 4]
    assert artifact["status"] == "completed_with_errors"
    assert artifact["comparability_status"] == "comparable"
    candidate = artifact["samples"][2]
    assert candidate["status"] == "completed_with_errors"
    assert candidate["error_count"] == 2
    assert candidate["error_segment_ids"] == ["utt_1", "utt_2"]
    assert candidate["error_types"] == ["Timeout"]
    assert "error_message" not in candidate
    output = capsys.readouterr().out
    assert "Matrix status: completed_with_errors" in output
    assert "Comparability: OK" in output


def test_existing_failed_sample_is_completed_with_errors(load_script, monkeypatch, tmp_path):
    module = load_script("94_run_tts_concurrency_matrix.py")
    monkeypatch.setattr(module.preflight, "run_preflight", lambda *_: {"status": "ready"})
    monkeypatch.setattr(module.benchmark, "load_segments", lambda *_: _segments())
    monkeypatch.setattr(module.benchmark, "benchmark_unit", lambda *_: {"status": "completed"})

    def run_once(**kwargs):
        workers, workload = kwargs["workers"], kwargs["workload"]
        errors = ([{"segment_id": "utt_1", "error_type": "Timeout"}]
                  if workers == 4 else [])
        sample = _sample(module, workload, workers, "failed" if workers == 4 else "completed", errors)
        path = kwargs["benchmark_directory"] / f"w{workers}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        return sample, path

    monkeypatch.setattr(module.benchmark, "run_benchmark_once", run_once)
    artifact, _, code = module.run_matrix(_args(module, tmp_path))
    assert code == 0
    assert artifact["status"] == "completed_with_errors"
    assert artifact["comparability_status"] == "comparable"
    assert artifact["samples"][2]["status"] == "failed"


def test_failed_to_create_sample_is_incomplete_and_nonzero(load_script, monkeypatch, tmp_path):
    module = load_script("94_run_tts_concurrency_matrix.py")
    monkeypatch.setattr(module.preflight, "run_preflight", lambda *_: {"status": "ready"})
    monkeypatch.setattr(module.benchmark, "load_segments", lambda *_: _segments())
    monkeypatch.setattr(module.benchmark, "benchmark_unit", lambda *_: {"status": "completed"})

    def run_once(**kwargs):
        if kwargs["workers"] == 2:
            raise RuntimeError("unsafe bearer token-value")
        sample = _sample(module, kwargs["workload"], kwargs["workers"])
        path = kwargs["benchmark_directory"] / f"w{kwargs['workers']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        return sample, path

    monkeypatch.setattr(module.benchmark, "run_benchmark_once", run_once)
    artifact, _, code = module.run_matrix(_args(module, tmp_path))
    assert code == 1
    assert artifact["status"] == "incomplete"
    assert artifact["comparability_status"] == "not_comparable"
    assert [item["workers"] for item in artifact["samples"]] == [1, 2, 4]
    failed = artifact["samples"][1]
    assert failed["status"] == "failed_to_create_sample"
    assert failed["error_count"] == 1 and failed["path"] is None
    assert failed["error_type"] == "RuntimeError"
    assert "token-value" not in failed["error_message"]


def test_workload_mismatch_is_not_comparable_and_nonzero(load_script, monkeypatch, tmp_path):
    module = load_script("94_run_tts_concurrency_matrix.py")
    monkeypatch.setattr(module.preflight, "run_preflight", lambda *_: {"status": "ready"})
    monkeypatch.setattr(module.benchmark, "load_segments", lambda *_: _segments())
    monkeypatch.setattr(module.benchmark, "benchmark_unit", lambda *_: {"status": "completed"})

    def run_once(**kwargs):
        sample = _sample(module, kwargs["workload"], kwargs["workers"])
        if kwargs["workers"] == 2:
            sample["workload_hash"] = "mismatch"
        path = kwargs["benchmark_directory"] / f"w{kwargs['workers']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        return sample, path

    monkeypatch.setattr(module.benchmark, "run_benchmark_once", run_once)
    artifact, _, code = module.run_matrix(_args(module, tmp_path))
    assert code == 1
    assert artifact["status"] == "completed"
    assert artifact["comparability_status"] == "not_comparable"
    assert any("workload_hash" in warning for warning in artifact["comparability_warnings"])
