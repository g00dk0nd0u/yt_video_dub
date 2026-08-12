from __future__ import annotations

import sys
import threading
import time
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


def _prepare_modules(*, source=None, transcript=None, calls=None):
    calls = calls if calls is not None else []
    source = source or (lambda **kwargs: ("source.mp4", {"source_reused": False}))
    transcript = transcript or (lambda argv: calls.append("transcript"))
    return {
        "01_prepare_source.py": SimpleNamespace(
            prepare_youtube_metadata=lambda **kwargs: ("video-id", {"video_id": "video-id"}),
            acquire_youtube_source=source,
            finalize_youtube_job=lambda **kwargs: calls.append("finalize"),
        ),
        "02_get_transcript.py": SimpleNamespace(main=transcript),
        "02_normalize_transcript.py": SimpleNamespace(main=lambda argv: calls.append("normalize")),
        "03_make_translation_chunks.py": SimpleNamespace(main=lambda argv: calls.append("chunks")),
    }


def test_prepare_acquisitions_overlap_and_dependencies_finish_first(monkeypatch):
    calls, barrier = [], threading.Barrier(2)
    def source(**kwargs):
        calls.append("source-start"); barrier.wait(timeout=1); time.sleep(.04)
        calls.append("source-end"); return "source.mp4", {"source_reused": False}
    def transcript(argv):
        calls.append("transcript-start"); barrier.wait(timeout=1); time.sleep(.04)
        calls.append("transcript-end")
    modules = _prepare_modules(source=source, transcript=transcript, calls=calls)
    monkeypatch.setattr(run_prepare, "_load_script_module", modules.__getitem__)
    started = time.monotonic()
    assert run_prepare.main(["--youtube-url", "url", "--quiet"]) == 0
    assert time.monotonic() - started < .075
    assert calls.index("finalize") > max(calls.index("source-end"), calls.index("transcript-end"))
    assert calls[-2:] == ["normalize", "chunks"]


@pytest.mark.parametrize("failed_side", ["source", "transcript"])
def test_prepare_fails_if_either_acquisition_fails(monkeypatch, failed_side):
    calls = []
    def source(**kwargs):
        if failed_side == "source": raise RuntimeError("source failed")
        return "source.mp4", {"source_reused": True}
    def transcript(argv):
        if failed_side == "transcript": raise RuntimeError("transcript failed")
    modules = _prepare_modules(source=source, transcript=transcript, calls=calls)
    monkeypatch.setattr(run_prepare, "_load_script_module", modules.__getitem__)
    with pytest.raises(RuntimeError, match="failed"):
        run_prepare.main(["--youtube-url", "url", "--quiet"])
    assert "finalize" not in calls
    assert "normalize" not in calls
    assert "chunks" not in calls
