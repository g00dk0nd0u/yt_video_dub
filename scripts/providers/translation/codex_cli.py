"""Translate a complete job through Codex CLI in an isolated workspace."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from translation_handoff import load_jsonl, load_manifest, validate_chunk_pair


class CodexTranslationError(RuntimeError):
    """An actionable automatic-translation failure."""


def _task_text() -> str:
    return (
        "Read translation_mode.md and translate every JSONL file in input/. "
        "Write the translated JSONL to output/ using exactly the same filenames. "
        "Preserve line order and segment_id, start, end, and duration exactly. "
        "Change only text from English to concise natural spoken Japanese. "
        "Do not write commentary or any other files."
    )


def translate_job(
    *, input_dir: Path, output_dir: Path, manifest_path: Path, rules_path: Path,
    codex_bin: str = "codex", runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    executable = shutil.which(codex_bin)
    if executable is None:
        raise CodexTranslationError(
            "Codex CLI was not found.\n"
            "Install/sign in to Codex CLI before using automatic translation."
        )
    manifest = load_manifest(manifest_path)
    chunk_names = [chunk["file"] for chunk in manifest["chunks"]]
    original_sources = {
        name: load_jsonl(input_dir / name)
        for name in chunk_names
    }
    with tempfile.TemporaryDirectory(prefix="yt_video_dub_translation_") as temporary:
        workspace = Path(temporary)
        isolated_input = workspace / "input"
        isolated_output = workspace / "output"
        isolated_input.mkdir()
        isolated_output.mkdir()
        shutil.copy2(rules_path, workspace / "translation_mode.md")
        for name in chunk_names:
            shutil.copy2(input_dir / name, isolated_input / name)
        result = runner(
            [executable, "exec", "--ephemeral", "--sandbox", "workspace-write",
             "--skip-git-repo-check", "-C", str(workspace), _task_text()],
            cwd=workspace, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise CodexTranslationError(
                "Codex CLI exited unsuccessfully. Run Codex CLI once and sign in "
                "with your ChatGPT account."
            )

        validated: dict[str, str] = {}
        try:
            for name in chunk_names:
                source_path = input_dir / name
                translated_path = isolated_output / name
                translated = load_jsonl(translated_path)
                validate_chunk_pair(original_sources[name], translated, source_path, translated_path,
                                    reject_blank_translation=True)
                validated[name] = translated_path.read_text(encoding="utf-8")
        except (FileNotFoundError, RuntimeError) as exc:
            raise CodexTranslationError(
                "Codex output did not pass validation. No translation files were updated."
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        staged = output_dir / ".codex_translation_staging"
        if staged.exists():
            shutil.rmtree(staged)
        staged.mkdir()
        try:
            for name, content in validated.items():
                (staged / name).write_text(content, encoding="utf-8")
            for name in chunk_names:
                (staged / name).replace(output_dir / name)
        finally:
            shutil.rmtree(staged, ignore_errors=True)

    metadata = {"provider": "codex_cli", "chunk_count": len(chunk_names),
                "status": "completed"}
    (output_dir / "translation_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def repair_translations(
    *, retry_path: Path, input_dir: Path, output_dir: Path, manifest_path: Path,
    rules_path: Path, codex_bin: str = "codex",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[dict]:
    """Atomically replace only requested texts, after strict timing/ID validation."""
    executable = shutil.which(codex_bin)
    if executable is None:
        raise CodexTranslationError("Codex CLI was not found. Install/sign in to Codex CLI.")
    requests = load_jsonl(retry_path)
    requested = {row["segment_id"]: row for row in requests}
    if not requested:
        return []
    manifest = load_manifest(manifest_path)
    chunks = [chunk["file"] for chunk in manifest["chunks"]]
    current = {name: load_jsonl(output_dir / name) for name in chunks}
    selected = [item for name in chunks for item in current[name] if item.get("segment_id") in requested]
    if {item["segment_id"] for item in selected} != set(requested):
        raise CodexTranslationError("Repair segment IDs do not match translation output.")
    with tempfile.TemporaryDirectory(prefix="yt_video_dub_repair_") as temporary:
        workspace = Path(temporary)
        (workspace / "input").mkdir()
        (workspace / "output").mkdir()
        shutil.copy2(rules_path, workspace / "translation_mode.md")
        repair_input = []
        for item in selected:
            row = dict(item)
            row["target_chars"] = requested[item["segment_id"]].get("target_chars")
            repair_input.append(row)
        repair_file = workspace / "input" / "duration_retry_required.jsonl"
        repair_file.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in repair_input), encoding="utf-8")
        task = (_task_text().replace("every JSONL file", "duration_retry_required.jsonl")
                + " Use target_chars as strong guidance and rewrite only text. Output the same filename.")
        result = runner([executable, "exec", "--ephemeral", "--sandbox", "workspace-write",
                         "--skip-git-repo-check", "-C", str(workspace), task], cwd=workspace,
                        capture_output=True, text=True)
        if result.returncode != 0:
            raise CodexTranslationError("Codex CLI repair exited unsuccessfully; authentication or usage limit may be the cause.")
        try:
            repaired = load_jsonl(workspace / "output" / repair_file.name)
            validated = validate_chunk_pair(selected, repaired, repair_file, repair_file,
                                            reject_blank_translation=True)
        except (FileNotFoundError, RuntimeError) as exc:
            raise CodexTranslationError("Codex repair output did not pass validation. No files were updated.") from exc
        repaired_by_id = {x["segment_id"]: x for x in validated}
        changes = []
        staged = output_dir / ".codex_repair_staging"
        shutil.rmtree(staged, ignore_errors=True)
        staged.mkdir()
        for name in chunks:
            rows = current[name]
            for row in rows:
                replacement = repaired_by_id.get(row.get("segment_id"))
                if replacement:
                    before = row["text"]
                    row["text"] = replacement["text"]
                    changes.append({"segment_id": row["segment_id"], "text_before": before,
                                    "text_after": row["text"],
                                    "target_chars": requested[row["segment_id"]].get("target_chars")})
            (staged / name).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
        for name in chunks:
            (staged / name).replace(output_dir / name)
        shutil.rmtree(staged, ignore_errors=True)
    return changes
