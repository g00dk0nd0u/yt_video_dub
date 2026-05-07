#!/usr/bin/env python3
"""Interactively clean local output directories by job id."""

from __future__ import annotations

import shutil
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path("output")
TEST_JOB_IDS = (
    "test_probe",
    "test_nise",
    "test_nise_long",
    "test_nise_business",
)
MENU_TEXT = """\
Local Output Cleanup
1. List jobs under output/
2. Delete one job from output/
3. Delete all jobs from output/
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


def _collect_jobs(output_dir: Path) -> list[str]:
    return sorted(_job_dirs(output_dir))


def _print_jobs(output_dir: Path) -> None:
    numbered_jobs = _build_numbered_jobs(output_dir)
    if not numbered_jobs:
        print("No jobs found in output/.")
        return

    print("Jobs:")
    for index, job_id, locations in numbered_jobs:
        print(f"{index}. {job_id} [{', '.join(locations)}]")


def _confirm_delete() -> bool:
    typed = input("Type DELETE to confirm: ").strip()
    if typed != "DELETE":
        print("Confirmation did not match. Nothing was deleted.")
        return False
    return True


def _confirm_delete_all() -> bool:
    typed = input("Type DELETE ALL to confirm: ").strip()
    if typed != "DELETE ALL":
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


def _build_numbered_jobs(output_dir: Path) -> list[tuple[int, str, list[str]]]:
    job_ids = _collect_jobs(output_dir)
    output_jobs = _job_dirs(output_dir)
    numbered_jobs: list[tuple[int, str, list[str]]] = []

    for index, job_id in enumerate(job_ids, start=1):
        locations: list[str] = []
        if job_id in output_jobs:
            locations.append("output")
        numbered_jobs.append((index, job_id, locations))

    return numbered_jobs


def _select_job(output_dir: Path) -> str | None:
    numbered_jobs = _build_numbered_jobs(output_dir)
    if not numbered_jobs:
        print("No jobs available.")
        return None

    print("Available jobs:")
    for index, job_id, locations in numbered_jobs:
        print(f"{index}. {job_id} [{', '.join(locations)}]")

    selected = input("Select job number to delete: ").strip()
    if selected == "":
        print("Job number is required.")
        return None
    if not selected.isdigit():
        print("Invalid selection. Please enter a job number.")
        return None

    selected_index = int(selected)
    for index, job_id, _locations in numbered_jobs:
        if index == selected_index:
            if not _is_safe_job_id(job_id):
                print("Selected job ID is invalid.")
                return None
            return job_id

    print("Invalid selection. Please enter a listed job number.")
    return None


def _delete_one_job(output_dir: Path) -> None:
    job_id = _select_job(output_dir)
    if job_id is None:
        return

    job_dir = output_dir / job_id
    if not job_dir.is_dir():
        print(f"Job not found in output/: {job_id}")
        return

    print("You are about to delete:")
    print(f"- output/{job_id}")
    if not _confirm_delete():
        return

    _delete_paths([job_dir])


def _delete_test_jobs(output_dir: Path) -> None:
    present_job_ids = [
        job_id
        for job_id in TEST_JOB_IDS
        if (output_dir / job_id).is_dir()
    ]
    if not present_job_ids:
        print("No test jobs found.")
        return

    print("Test jobs found:")
    for job_id in present_job_ids:
        print(f"- {job_id}")

    for job_id in present_job_ids:
        print(f"Confirm test job cleanup: {job_id}")
        if not _confirm_delete():
            continue
        _delete_paths([output_dir / job_id])


def _delete_all_jobs(output_dir: Path) -> None:
    job_ids = _collect_jobs(output_dir)
    if not job_ids:
        print("No jobs found in output/.")
        return

    print("You are about to delete these output job directories:")
    paths_to_delete: list[Path] = []
    seen_paths: set[Path] = set()
    for job_id in job_ids:
        if not _is_safe_job_id(job_id):
            print(f"Skipping invalid job ID: {job_id}")
            continue
        path = output_dir / job_id
        if path.is_dir() and path not in seen_paths:
            print(f"- {path}")
            paths_to_delete.append(path)
            seen_paths.add(path)

    if not paths_to_delete:
        print("Nothing was deleted.")
        return
    if not _confirm_delete_all():
        return

    _delete_paths(paths_to_delete)


def main() -> int:
    output_dir = DEFAULT_OUTPUT_DIR

    while True:
        print()
        print(MENU_TEXT, end="")
        choice = input("Choose an option [1-5]: ").strip()

        if choice == "1":
            _print_jobs(output_dir)
        elif choice == "2":
            _delete_one_job(output_dir)
        elif choice == "3":
            _delete_all_jobs(output_dir)
        elif choice == "4":
            _delete_test_jobs(output_dir)
        elif choice == "5":
            print("Exit.")
            return 0
        else:
            print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")


if __name__ == "__main__":
    raise SystemExit(main())
