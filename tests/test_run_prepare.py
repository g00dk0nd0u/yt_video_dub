from __future__ import annotations

import sys
import threading
from types import SimpleNamespace

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
    paths = SimpleNamespace(job_dir=tmp_path / "job")
    prepare = SimpleNamespace(
        initialize_youtube_job=lambda **_kwargs: ("job", paths, {}),
        acquire_initialized_youtube_job=lambda **_kwargs: (barrier.wait(timeout=2), calls.append("source")),
    )
    transcript = SimpleNamespace(main=lambda _args: (barrier.wait(timeout=2), calls.append("transcript")))
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
    assert calls[2:] == ["normalize", "chunks"]
