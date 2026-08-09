import json
from pathlib import Path

import pytest


def test_chunks_use_normalized_units(tmp_path, load_script):
    module = load_script("03_make_translation_chunks.py")
    job = tmp_path / "job" / "02_transcript"
    job.mkdir(parents=True)
    (job / "transcript_raw.json").write_text(json.dumps({"segments": [{
        "segment_id": "seg_0001", "start": 0, "end": 1, "text": "raw"
    }]}))
    (job / "transcript_normalized.json").write_text(json.dumps({"units": [{
        "unit_id": "utt_0001", "source_start": 0.2, "source_end": 1.5,
        "available_duration": 1.3, "source_text": "normalized"
    }]}))
    module.main(["--job-id", "job", "--output-dir", str(tmp_path)])
    item = json.loads((tmp_path / "job/03_translation_input/chunk_0001.txt").read_text())
    assert item == {"segment_id": "utt_0001", "start": 0.2, "end": 1.5,
                    "duration": 1.3, "text": "normalized"}


@pytest.mark.parametrize("mutation", ["count", "segment_id", "start", "end"])
def test_translation_validation_remains_strict(tmp_path, load_script, mutation):
    module = load_script("04_build_translated_segments.py")
    source = [{"segment_id": "utt_0001", "start": 1.0, "end": 2.0,
               "duration": 1.0, "text": "source"}]
    translated = [dict(source[0], text="翻訳")]
    if mutation == "count":
        translated = []
    else:
        translated[0][mutation] = "bad" if mutation == "segment_id" else 9.0
    with pytest.raises(RuntimeError):
        module._validate_chunk_pair(source, translated, Path("source"), Path("translated"))
