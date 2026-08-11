import json
import subprocess
from pathlib import Path

import pytest

from providers.translation.codex_cli import CodexTranslationError, repair_translations


def _job(tmp_path):
    source, output = tmp_path / "input", tmp_path / "output"
    source.mkdir(); output.mkdir()
    rows = [
        {"segment_id": "keep", "start": 0.0, "end": 1.0, "duration": 1.0, "text": "keep"},
        {"segment_id": "repair", "start": 1.0, "end": 2.0, "duration": 1.0, "text": "before"},
    ]
    for directory in (source, output):
        (directory / "chunk.txt").write_text("".join(json.dumps(x) + "\n" for x in rows))
    manifest = source / "manifest.json"
    manifest.write_text(json.dumps({"chunks": [{"file": "chunk.txt"}], "total_segments": 2}))
    retry = tmp_path / "retry.jsonl"
    retry.write_text(json.dumps({"segment_id": "repair", "target_chars": 3}) + "\n")
    rules = tmp_path / "rules.md"; rules.write_text("rules")
    return source, output, manifest, retry, rules


def _runner(mutated=None):
    def run(command, cwd, **kwargs):
        row = json.loads((Path(cwd) / "input/duration_retry_required.jsonl").read_text())
        row["text"] = "after"
        if mutated: row[mutated] = 999
        (Path(cwd) / "output/duration_retry_required.jsonl").write_text(json.dumps(row) + "\n")
        return subprocess.CompletedProcess(command, 0, "", "")
    return run


def test_repair_translations_changes_only_selected_text(tmp_path):
    source, output, manifest, retry, rules = _job(tmp_path)
    changes = repair_translations(retry_path=retry, input_dir=source, output_dir=output,
        manifest_path=manifest, rules_path=rules, codex_bin="python", runner=_runner())
    rows = [json.loads(x) for x in (output / "chunk.txt").read_text().splitlines()]
    assert rows[0]["text"] == "keep"
    assert rows[1] == {"segment_id": "repair", "start": 1.0, "end": 2.0,
                       "duration": 1.0, "text": "after"}
    assert [x["segment_id"] for x in changes] == ["repair"]


def test_repair_prompt_prioritizes_spoken_duration_and_japanese_shortening(tmp_path):
    source, output, manifest, retry, rules = _job(tmp_path)
    commands = []
    runner = _runner()

    def capture(command, **kwargs):
        commands.append(command)
        return runner(command, **kwargs)

    repair_translations(retry_path=retry, input_dir=source, output_dir=output,
        manifest_path=manifest, rules_path=rules, codex_bin="python", runner=capture)

    prompt = commands[0][-1]
    assert "strict maximum" in prompt
    assert "reduce spoken duration" in prompt
    assert "よね" in prompt


@pytest.mark.parametrize("field", ["segment_id", "start", "end", "duration"])
def test_repair_rejects_immutable_metadata_changes(tmp_path, field):
    source, output, manifest, retry, rules = _job(tmp_path)
    before = (output / "chunk.txt").read_text()
    with pytest.raises(CodexTranslationError, match="did not pass validation"):
        repair_translations(retry_path=retry, input_dir=source, output_dir=output,
            manifest_path=manifest, rules_path=rules, codex_bin="python", runner=_runner(field))
    assert (output / "chunk.txt").read_text() == before
