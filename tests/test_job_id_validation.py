from pathlib import Path

import pytest

from path_layout import build_job_paths, validate_job_id


INVALID_JOB_IDS = ["", ".", "..", "../../outside", "../outside", "/tmp/outside",
                   r"..\outside", r"C:\outside"]


@pytest.mark.parametrize("job_id", INVALID_JOB_IDS)
def test_path_layout_rejects_job_paths_without_filesystem_changes(tmp_path, job_id):
    output_dir = tmp_path / "output"
    outside = tmp_path / "outside"
    outside.write_bytes(b"untouched")

    with pytest.raises(ValueError, match="Invalid job ID"):
        build_job_paths(output_dir, job_id)

    assert not output_dir.exists()
    assert outside.read_bytes() == b"untouched"


@pytest.mark.parametrize("job_id", ["job", "existing_job-01", "dQw4w9WgXcQ"])
def test_path_layout_accepts_existing_names_and_youtube_ids(tmp_path, job_id):
    assert build_job_paths(tmp_path, job_id).job_dir == tmp_path / job_id
    assert validate_job_id(job_id) == job_id


@pytest.mark.parametrize("video_id", ["../../outside", "../outside", "/tmp/outside",
                                      r"..\outside", r"C:\outside"])
def test_default_runner_rejects_url_derived_path_ids(load_script, video_id):
    module = load_script("../user_tools/00_dub_youtube.py")
    with pytest.raises(ValueError, match="Invalid job ID"):
        module._canonical_youtube_input(f"https://www.youtube.com/watch?v={video_id}")

