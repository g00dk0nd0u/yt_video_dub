from __future__ import annotations

from pathlib import Path

import pytest

from path_layout import build_job_paths


def test_previous_numbered_interrupted_job_is_adopted_for_resume(tmp_path):
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "01_source/source.mp4").write_bytes(b"source")
    (job / "06_tts").mkdir()
    (job / "06_tts/tts_manifest.json").write_text("{}")

    paths = build_job_paths(tmp_path, "job")

    assert paths.source_video_path.read_bytes() == b"source"
    assert paths.tts_manifest_path.read_text() == "{}"
    assert not (job / "01_source").exists()
    assert not (job / "06_tts").exists()


def test_numbered_adoption_never_moves_finals_or_unrelated_files(tmp_path):
    job = tmp_path / "job"
    (job / "02_transcript").mkdir(parents=True)
    (job / "02_transcript/transcript_raw.json").write_text("{}")
    final = job / "dubbed_video.mp4"
    background = job / "dubbed_video_with_bg.mp4"
    unrelated = job / "notes.txt"
    final.write_bytes(b"final")
    background.write_bytes(b"background")
    unrelated.write_text("keep")

    build_job_paths(tmp_path, "job")

    assert final.read_bytes() == b"final"
    assert background.read_bytes() == b"background"
    assert unrelated.read_text() == "keep"


def test_conflicting_old_and_new_work_is_preserved(tmp_path):
    job = tmp_path / "job"
    old = job / "05_segments/translated_segments.json"
    new = job / ".cache/work/05_segments/translated_segments.json"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text("old")
    new.write_text("new")

    with pytest.raises(RuntimeError, match="Conflicting old and new job work layouts"):
        build_job_paths(tmp_path, "job")

    assert old.read_text() == "old"
    assert new.read_text() == "new"
