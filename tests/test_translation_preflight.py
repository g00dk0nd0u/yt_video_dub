import json

import pytest


def _write_job(tmp_path, *, source_text="hello", translated_text="こんにちは", second=True):
    job = tmp_path / "job"
    input_dir = job / "03_translation_input"
    output_dir = job / "04_translation_output"
    segments_dir = job / "05_segments"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    segments_dir.mkdir(exist_ok=True)
    source = [{"segment_id": "utt_1", "start": 0.0, "end": 1.0,
               "duration": 1.0, "text": source_text}]
    translated = [{**source[0], "text": translated_text}]
    if second:
        source.append({"segment_id": "utt_2", "start": 0.8, "end": 2.0,
                       "duration": 1.2, "text": "CUDA API"})
        translated.append({**source[1], "text": "CUDA APIを使います"})
    manifest = {"total_segments": len(source), "chunks": [{"file": "chunk_0001.txt"}]}
    (input_dir / "manifest.json").write_text(json.dumps(manifest))
    for directory, rows in ((input_dir, source), (output_dir, translated)):
        (directory / "chunk_0001.txt").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
        )
    final = [{key: row[key] for key in ("segment_id", "start", "end", "duration", "text")}
             for row in translated]
    (segments_dir / "translated_segments.json").write_text(json.dumps({"segments": final}))
    return job, source, translated, final


def _run(module, tmp_path):
    code = module.main(["--job-id", "job", "--output-dir", str(tmp_path)])
    report = json.loads((tmp_path / "job/05_segments/local_run_preflight.json").read_text())
    return code, report


def test_valid_handoff_technical_english_density_and_determinism(tmp_path, load_script):
    module = load_script("05_preflight_local_run.py")
    _write_job(tmp_path)
    code, first = _run(module, tmp_path)
    code_again, second = _run(module, tmp_path)
    assert code == code_again == 0
    assert first == second
    assert first["status"] == "ready"
    assert first["translation_fingerprint"]
    dense = next(item for item in first["density"]["top_segments"]
                 if item["segment_id"] == "utt_2")
    assert dense["character_count"] == len("CUDAAPIを使います")
    assert dense["chars_per_second"] == pytest.approx(dense["character_count"] / 1.2)


def test_missing_output_chunk_writes_not_ready_report(tmp_path, load_script):
    module = load_script("05_preflight_local_run.py")
    job, *_ = _write_job(tmp_path)
    (job / "04_translation_output/chunk_0001.txt").unlink()
    code, report = _run(module, tmp_path)
    assert code == 1 and report["status"] == "not_ready"
    assert "chunk_0001.txt" in report["errors"][0]


@pytest.mark.parametrize("field,value", [("segment_id", "changed"), ("start", 0.1)])
def test_immutable_chunk_mismatch(tmp_path, load_script, field, value):
    module = load_script("05_preflight_local_run.py")
    job, _, translated, _ = _write_job(tmp_path)
    translated[0][field] = value
    (job / "04_translation_output/chunk_0001.txt").write_text(
        "\n".join(json.dumps(row) for row in translated)
    )
    code, report = _run(module, tmp_path)
    assert code == 1
    assert field in report["errors"][0]


@pytest.mark.parametrize("mutation,error", [
    (lambda rows: rows.__setitem__(1, {**rows[1], "segment_id": "utt_1"}), "Duplicate"),
    (lambda rows: rows.__setitem__(0, {**rows[0], "start": float("nan")}), "finite"),
    (lambda rows: rows.__setitem__(0, {**rows[0], "end": float("inf")}), "finite"),
    (lambda rows: rows.__setitem__(0, {**rows[0], "start": -1}), "invalid timing"),
    (lambda rows: rows.__setitem__(0, {**rows[0], "end": 0}), "invalid timing"),
    (lambda rows: rows.reverse(), "timeline order"),
])
def test_final_segment_hard_failures(tmp_path, load_script, mutation, error):
    module = load_script("05_preflight_local_run.py")
    job, _, _, final = _write_job(tmp_path)
    mutation(final)
    (job / "05_segments/translated_segments.json").write_text(
        json.dumps({"segments": final}, allow_nan=True)
    )
    code, report = _run(module, tmp_path)
    assert code == 1
    assert error in report["errors"][0]


def test_blank_translation_fails_but_empty_source_is_allowed(tmp_path, load_script):
    module = load_script("05_preflight_local_run.py")
    _write_job(tmp_path, translated_text="   ", second=False)
    code, _ = _run(module, tmp_path)
    assert code == 1
    job, _, _, final = _write_job(tmp_path, source_text="", translated_text="", second=False)
    (job / "05_segments/translated_segments.json").write_text(json.dumps({"segments": final}))
    code, report = _run(module, tmp_path)
    assert code == 0 and report["source_empty_units"] == 1


def test_fingerprint_changes_and_stale_final_is_rejected(tmp_path, load_script):
    module = load_script("05_preflight_local_run.py")
    job, _, translated, final = _write_job(tmp_path)
    _, original = _run(module, tmp_path)
    translated[0]["text"] += "！"
    (job / "04_translation_output/chunk_0001.txt").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in translated)
    )
    code, report = _run(module, tmp_path)
    assert code == 1 and "stale" in report["errors"][0]
    final[0]["text"] = translated[0]["text"]
    (job / "05_segments/translated_segments.json").write_text(json.dumps({"segments": final}))
    code, changed = _run(module, tmp_path)
    assert code == 0
    assert changed["translation_fingerprint"] != original["translation_fingerprint"]
