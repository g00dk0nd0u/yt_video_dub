from __future__ import annotations

import sys

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
