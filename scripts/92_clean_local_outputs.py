#!/usr/bin/env python3
"""Interactively clean local output and review directories by job id."""

from __future__ import annotations

import shutil
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_REVIEW_DIR = Path("review_outputs")
TEST_JOB_IDS = (
    "test_probe",
    "test_nise",
    "test_nise_long",
    "test_nise_business",
)
MENU_TEXT = """\
Local Output Cleanup
1. List jobs
2. Delete one job from output and review_outputs
3. Delete only review_outputs for one job
4. Delete test_probe/test_nise/test_nise_long/test_nise_business if present
5. Exit
"""


def _is_safe_job_id(job_id: str) -> bool:
    if job_id in {"", ".", ".."}:
        return False
    return Path(job_id).name == job_id


def _job_dirs(base_dir: Path) -> dict[str, Path]:
    if not base_dir.exists():
        return {}
    return {
        path.name: path
        for path in sorted(base_dir.iterdir())
        if path.is_dir() and path.name not in {".gitkeep", "__pycache__"}
    }


def _collect_jobs(output_dir: Path, review_dir: Path) -> list[str]:
    job_ids = set(_job_dirs(output_dir))
    job_ids.update(_job_dirs(review_dir))
    return sorted(job_ids)


def _print_jobs(output_dir: Path, review_dir: Path) -> None:
    job_ids = _collect_jobs(output_dir, review_dir)
    if not job_ids:
        print("No jobs found in output/ or review_outputs/.")
        return

    print("Jobs:")
    output_jobs = _job_dirs(output_dir)
    review_jobs = _job_dirs(review_dir)
    for job_id in job_ids:
        locations: list[str] = []
        if job_id in output_jobs:
            locations.append("output")
        if job_id in review_jobs:
            locations.append("review_outputs")
        print(f"- {job_id} [{', '.join(locations)}]")


def _confirm_job_id(job_id: str) -> bool:
    typed = input("Type the exact job_id to confirm: ").strip()
    if typed != job_id:
        print("Confirmation did not match. Nothing was deleted.")
        return False
    return True


def _delete_paths(paths: list[Path]) -> None:
    deleted_any = False
    for path in paths:
        if not path.is_dir():
            continue
        shutil.rmtree(path)
        print(f"Deleted: {path}")
        deleted_any = True
    if not deleted_any:
        print("Nothing was deleted.")


def _prompt_job_id(output_dir: Path, review_dir: Path) -> str | None:
    job_ids = _collect_jobs(output_dir, review_dir)
    if not job_ids:
        print("No jobs available.")
        return None

    print("Available jobs:")
    for job_id in job_ids:
        print(f"- {job_id}")

    job_id = input("Job ID: ").strip()
    if job_id == "":
        print("Job ID is required.")
        return None
    if not _is_safe_job_id(job_id):
        print("Job ID must be a single directory name.")
        return None
    return job_id


def _delete_job_everywhere(output_dir: Path, review_dir: Path) -> None:
    job_id = _prompt_job_id(output_dir, review_dir)
    if job_id is None:
        return

    paths = [output_dir / job_id, review_dir / job_id]
    existing_paths = [path for path in paths if path.is_dir()]
    if not existing_paths:
        print(f"Job not found in output/ or review_outputs/: {job_id}")
        return
    if not _confirm_job_id(job_id):
        return

    _delete_paths(existing_paths)


def _delete_review_only(review_dir: Path, output_dir: Path) -> None:
    job_id = _prompt_job_id(output_dir, review_dir)
    if job_id is None:
        return

    review_job_dir = review_dir / job_id
    if not review_job_dir.is_dir():
        print(f"Job not found in review_outputs/: {job_id}")
        return
    if not _confirm_job_id(job_id):
        return

    _delete_paths([review_job_dir])


def _delete_test_jobs(output_dir: Path, review_dir: Path) -> None:
    present_job_ids = [
        job_id
        for job_id in TEST_JOB_IDS
        if (output_dir / job_id).is_dir() or (review_dir / job_id).is_dir()
    ]
    if not present_job_ids:
        print("No test jobs found.")
        return

    print("Test jobs found:")
    for job_id in present_job_ids:
        print(f"- {job_id}")

    for job_id in present_job_ids:
        print(f"Confirm test job cleanup: {job_id}")
        if not _confirm_job_id(job_id):
            continue
        paths = [output_dir / job_id, review_dir / job_id]
        _delete_paths([path for path in paths if path.is_dir()])


def main() -> int:
    output_dir = DEFAULT_OUTPUT_DIR
    review_dir = DEFAULT_REVIEW_DIR

    while True:
        print()
        print(MENU_TEXT, end="")
        choice = input("Choose an option [1-5]: ").strip()

        if choice == "1":
            _print_jobs(output_dir, review_dir)
        elif choice == "2":
            _delete_job_everywhere(output_dir, review_dir)
        elif choice == "3":
            _delete_review_only(review_dir, output_dir)
        elif choice == "4":
            _delete_test_jobs(output_dir, review_dir)
        elif choice == "5":
            print("Exit.")
            return 0
        else:
            print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")


if __name__ == "__main__":
    raise SystemExit(main())
