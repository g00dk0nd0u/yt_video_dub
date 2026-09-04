from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import run_prepare


def test_phase1_dynamic_loader_imports_current_pipeline_modules():
    loaded = {
        filename: run_prepare._load_script_module(filename)
        for filename in (
            "01_prepare_source.py",
            "02_get_transcript.py",
            "02_normalize_transcript.py",
            "03_make_translation_chunks.py",
        )
    }

    assert loaded["01_prepare_source.py"].AcquisitionStrategy
    for module in loaded.values():
        assert sys.modules[module.__name__] is module


def test_youtube_source_and_transcript_are_prepared_in_parallel(monkeypatch, tmp_path):
    barrier = threading.Barrier(2)
    calls = []
    transcript_args = []
    paths = SimpleNamespace(job_dir=tmp_path / "job")
    prepare = SimpleNamespace(
        initialize_youtube_job=lambda **_kwargs: ("-TTyyY3VWh8", paths, {}),
        acquire_initialized_youtube_job=lambda **_kwargs:
            (barrier.wait(timeout=2), calls.append("source"), (Path("source.mp4"), {}))[-1],
        finalize_youtube_job=lambda **_kwargs: calls.append("finalize"),
    )
    def transcript(args):
        transcript_args.extend(args)
        barrier.wait(timeout=2)
        calls.append("transcript")

    transcript = SimpleNamespace(main=transcript)
    modules = {
        "01_prepare_source.py": prepare,
        "02_get_transcript.py": transcript,
        "02_normalize_transcript.py": SimpleNamespace(main=lambda _args: calls.append("normalize")),
        "03_make_translation_chunks.py": SimpleNamespace(main=lambda _args: calls.append("chunks")),
    }
    monkeypatch.setattr(run_prepare, "_load_script_module", modules.__getitem__)

    assert run_prepare.main(["--youtube-url", "https://youtu.be/job", "--output-dir",
                             str(tmp_path), "--quiet"]) == 0
    assert set(calls[:2]) == {"source", "transcript"}
    assert calls[2:] == ["finalize", "normalize", "chunks"]
    assert "--job-id=-TTyyY3VWh8" in transcript_args


def test_immediate_source_completion_does_not_rewrite_job_during_transcript(monkeypatch, tmp_path):
    calls = []
    job_file = tmp_path / "job.json"
    job_file.write_text("initial")
    paths = SimpleNamespace(job_dir=tmp_path / "job", job_json_path=job_file)

    def transcript(_args):
        calls.append(("transcript_read", job_file.read_text()))

    def finalize(**_kwargs):
        calls.append("finalize")
        job_file.write_text("final")

    prepare = SimpleNamespace(
        initialize_youtube_job=lambda **_kwargs: ("job", paths, {"job_id": "job"}),
        acquire_initialized_youtube_job=lambda **_kwargs:
            (Path("source.mp4"), {"source_reused": True}),
        finalize_youtube_job=finalize,
    )
    modules = {
        "01_prepare_source.py": prepare,
        "02_get_transcript.py": SimpleNamespace(main=transcript),
        "02_normalize_transcript.py": SimpleNamespace(main=lambda _args: None),
        "03_make_translation_chunks.py": SimpleNamespace(main=lambda _args: None),
    }
    monkeypatch.setattr(run_prepare, "_load_script_module", modules.__getitem__)

    assert run_prepare.main(["--youtube-url", "url", "--quiet"]) == 0
    assert calls == [("transcript_read", "initial"), "finalize"]
    assert job_file.read_text() == "final"


@pytest.mark.parametrize("failed_stage", ["source", "transcript"])
def test_acquisition_failure_does_not_finalize_job(monkeypatch, tmp_path, failed_stage):
    finalized = []
    paths = SimpleNamespace(job_dir=tmp_path / "job")

    def source(**_kwargs):
        if failed_stage == "source":
            raise RuntimeError("source failed")
        return Path("source.mp4"), {}

    def transcript(_args):
        if failed_stage == "transcript":
            raise RuntimeError("transcript failed")

    prepare = SimpleNamespace(
        initialize_youtube_job=lambda **_kwargs: ("job", paths, {}),
        acquire_initialized_youtube_job=source,
        finalize_youtube_job=lambda **_kwargs: finalized.append(True),
    )
    modules = {
        "01_prepare_source.py": prepare,
        "02_get_transcript.py": SimpleNamespace(main=transcript),
        "02_normalize_transcript.py": SimpleNamespace(main=lambda _args: None),
        "03_make_translation_chunks.py": SimpleNamespace(main=lambda _args: None),
    }
    monkeypatch.setattr(run_prepare, "_load_script_module", modules.__getitem__)

    with pytest.raises(RuntimeError, match=f"{failed_stage} failed"):
        run_prepare.main(["--youtube-url", "url", "--quiet"])
    assert finalized == []
