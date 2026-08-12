import io
import json
import struct
import wave

import pytest


def _wav(path, frames, rate=1000):
    with wave.open(str(path), "wb") as writer:
        writer.setparams((1, 2, rate, frames, "NONE", "not compressed"))
        writer.writeframes(struct.pack("<h", 1000) * frames)


def _wav_bytes(frames, rate=1000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setparams((1, 2, rate, frames, "NONE", "not compressed"))
        writer.writeframes(struct.pack("<h", 1000) * frames)
    return buffer.getvalue()


def test_absolute_audio_placement_and_overflow_report(tmp_path, load_script):
    module = load_script("07_build_dub_audio.py")
    job = tmp_path / "job"
    tts = job / "06_tts"
    tts.mkdir(parents=True)
    _wav(tts / "one.wav", 2000)
    _wav(tts / "two.wav", 200)
    items = [
        {"index": 1, "segment_id": "utt_0001", "start": 0.0, "end": 1.0,
         "status": "generated", "wav_path": "06_tts/one.wav"},
        {"index": 2, "segment_id": "utt_0002", "start": 1.0, "end": 1.5,
         "status": "generated", "wav_path": "06_tts/two.wav"},
    ]
    (tts / "tts_manifest.json").write_text(json.dumps({"items": items}))
    module.main(["--job-id", "job", "--output-dir", str(tmp_path)])
    manifest = json.loads((job / "07_audio/dub_audio_manifest.json").read_text())
    assert manifest["items"][0]["timing_status"] == "overflow_clipped"
    assert manifest["items"][0]["clipped"] is True
    assert manifest["items"][1]["actual_start"] == 1.0
    assert manifest["items"][1]["timing_status"] == "ok"


def test_fast_mux_command_keeps_video_timeline(load_script, tmp_path):
    module = load_script("08_mux_video.py")
    command = module._build_ffmpeg_command("ffmpeg", tmp_path / "in.mp4",
                                            tmp_path / "dub.wav", tmp_path / "out.mp4")
    joined = " ".join(command)
    assert "-c:v copy" in joined
    assert "volume=-38.0dB" in joined
    assert "amix=inputs=2:duration=first:normalize=0" in joined
    assert "-shortest" not in command


def test_h264_video_codec_keeps_copy_fast_path(tmp_path, load_script, monkeypatch):
    module = load_script("08_mux_video.py")
    source_codec = "h264"
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    (job / "01_source/source.mp4").touch()
    (job / "07_audio/dub_audio.wav").touch()
    codecs = iter([source_codec, source_codec])
    monkeypatch.setattr(module, "_probe_video_stream",
                        lambda *_: {"codec_name": next(codecs)})
    commands = []
    monkeypatch.setattr(module.subprocess, "run",
                        lambda command, **kwargs: commands.append(command))

    assert module.main(["--job-id", "job", "--output-dir", str(tmp_path), "--quiet"]) == 0

    assert "-c:v copy" in " ".join(commands[0])
    manifest = json.loads((job / "07_audio/fast_mux_manifest.json").read_text())
    assert manifest["video_mode"] == "copy"
    assert manifest["compatibility_fallback_used"] is False
    assert manifest["compatibility_synchronous_fallback_used"] is False
    assert "video_codec" not in manifest


@pytest.mark.parametrize("source_codec", ["av1", "vp9", "hevc", "unknown"])
def test_unsafe_video_codec_transcodes_and_validates_h264(
    tmp_path, load_script, monkeypatch, source_codec
):
    module = load_script("08_mux_video.py")
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    (job / "01_source/source.mp4").touch()
    (job / "07_audio/dub_audio.wav").touch()
    codecs = iter([source_codec, "h264"])
    monkeypatch.setattr(module, "_probe_video_stream",
                        lambda *_: {"codec_name": next(codecs)})
    commands = []
    monkeypatch.setattr(module.subprocess, "run",
                        lambda command, **kwargs: commands.append(command))

    module.main(["--job-id", "job", "--output-dir", str(tmp_path), "--quiet"])

    joined = " ".join(commands[0])
    assert "-c:v libx264" in joined
    assert "-pix_fmt yuv420p" in joined
    assert "-movflags +faststart" in joined
    assert "volume=-38.0dB" in joined
    assert "-shortest" not in commands[0]
    manifest = json.loads((job / "07_audio/fast_mux_manifest.json").read_text())
    assert manifest["source_video_codec"] == source_codec
    assert manifest["output_video_codec"] == "h264"
    assert manifest["video_mode"] == "transcode"
    assert manifest["compatibility_fallback_used"] is True
    assert manifest["compatibility_synchronous_fallback_used"] is True
    assert "video_codec" not in manifest


def test_mux_rejects_incompatible_final_codec(tmp_path, load_script, monkeypatch):
    module = load_script("08_mux_video.py")
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    (job / "01_source/source.mp4").touch()
    (job / "07_audio/dub_audio.wav").touch()
    codecs = iter(["av1", "av1"])
    monkeypatch.setattr(module, "_probe_video_stream",
                        lambda *_: {"codec_name": next(codecs)})
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: None)

    with pytest.raises(module.MuxVideoError, match="compatibility validation"):
        module.main(["--job-id", "job", "--output-dir", str(tmp_path), "--quiet"])
    assert not (job / "07_audio/fast_mux_manifest.json").exists()


def test_valid_background_cache_is_copied_with_original_audio_mix(tmp_path, load_script, monkeypatch):
    module = load_script("08_mux_video.py")
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    source = job / "01_source/source.mp4"
    compat = job / "01_source/compat_h264.mp4"
    source.touch(); compat.touch(); (job / "07_audio/dub_audio.wav").touch()
    codecs = iter(["av1", "h264"])
    monkeypatch.setattr(module, "_probe_video_stream", lambda *_: {"codec_name": next(codecs)})
    commands = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: commands.append(command))

    manifest = module.mux_job(job_id="job", output_dir=str(tmp_path), quiet=True,
        compatibility_result={"compatibility_video_path": compat,
            "compatibility_task_started": True, "compatibility_background_used": True,
            "compatibility_transcode_seconds": 67.0, "compatibility_wait_seconds": 0.2})

    joined = " ".join(commands[0])
    assert str(compat) in commands[0] and "-c:v copy" in joined
    assert "volume=-38.0dB" in joined and "amix=inputs=2:duration=first:normalize=0" in joined
    assert "-c:a aac" in joined
    assert manifest["source_video_codec"] == "av1"
    assert manifest["video_mode"] == "copy"
    assert manifest["compatibility_fallback_used"] is True
    assert manifest["compatibility_synchronous_fallback_used"] is False
    assert manifest["compatibility_transcode_seconds"] == 67.0
    assert manifest["compatibility_wait_seconds"] == 0.2


def test_background_failure_uses_original_synchronous_transcode(tmp_path, load_script, monkeypatch):
    module = load_script("08_mux_video.py")
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    (job / "01_source/source.mp4").touch()
    (job / "07_audio/dub_audio.wav").touch()
    codecs = iter(["av1", "h264"])
    monkeypatch.setattr(module, "_probe_video_stream", lambda *_: {"codec_name": next(codecs)})
    commands = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: commands.append(command))

    manifest = module.mux_job(job_id="job", output_dir=str(tmp_path), quiet=True,
        compatibility_result={"compatibility_failure": "encode failed",
                              "compatibility_task_started": True})

    joined = " ".join(commands[0])
    assert "-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p" in joined
    assert "-movflags +faststart" in joined
    assert manifest["compatibility_fallback_used"] is True
    assert manifest["compatibility_synchronous_fallback_used"] is True
    assert manifest["compatibility_failure"] == "encode failed"


def test_cache_copy_mux_failure_retries_original_source_transcode(
    tmp_path, load_script, monkeypatch
):
    module = load_script("08_mux_video.py")
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    source = job / "01_source/source.mp4"
    compat = job / "01_source/compat_h264.mp4"
    source.touch(); compat.touch(); (job / "07_audio/dub_audio.wav").touch()
    codecs = iter(["av1", "h264"])
    monkeypatch.setattr(module, "_probe_video_stream", lambda *_: {"codec_name": next(codecs)})
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        if len(commands) == 1:
            raise module.subprocess.CalledProcessError(1, command, stderr="cache mux error")

    monkeypatch.setattr(module.subprocess, "run", run)

    manifest = module.mux_job(job_id="job", output_dir=str(tmp_path), quiet=True,
        compatibility_result={"compatibility_video_path": compat,
            "compatibility_task_started": True, "compatibility_background_used": True})

    assert len(commands) == 2
    assert str(compat) in commands[0] and "-c:v copy" in " ".join(commands[0])
    fallback = " ".join(commands[1])
    assert str(source) in commands[1]
    assert "-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p" in fallback
    assert "volume=-38.0dB" in fallback and "-c:a aac" in fallback
    assert manifest["video_mode"] == "transcode"
    assert manifest["output_video_codec"] == "h264"
    assert manifest["compatibility_background_used"] is True
    assert manifest["compatibility_synchronous_fallback_used"] is True
    assert "cache mux failed" in manifest["compatibility_failure"]
    assert "synchronous fallback" in manifest["compatibility_failure"]


def test_cache_copy_mux_and_synchronous_fallback_failure_is_bounded(
    tmp_path, load_script, monkeypatch
):
    module = load_script("08_mux_video.py")
    job = tmp_path / "job"
    (job / "01_source").mkdir(parents=True)
    (job / "07_audio").mkdir()
    source = job / "01_source/source.mp4"
    compat = job / "01_source/compat_h264.mp4"
    source.touch(); compat.touch(); (job / "07_audio/dub_audio.wav").touch()
    monkeypatch.setattr(module, "_probe_video_stream", lambda *_: {"codec_name": "av1"})
    commands = []

    def fail(command, **_kwargs):
        commands.append(command)
        raise module.subprocess.CalledProcessError(len(commands), command, stderr="mux failed")

    monkeypatch.setattr(module.subprocess, "run", fail)

    with pytest.raises(module.MuxVideoError, match="synchronous fallback failed"):
        module.mux_job(job_id="job", output_dir=str(tmp_path), quiet=True,
            compatibility_result={"compatibility_video_path": compat,
                "compatibility_task_started": True, "compatibility_background_used": True})

    assert len(commands) == 2
    assert "-c:v copy" in " ".join(commands[0])
    assert "-c:v libx264" in " ".join(commands[1])


def test_legacy_transcript_path_fallback(tmp_path):
    from path_layout import build_job_paths
    legacy = tmp_path / "job/transcript_original.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}")
    assert build_job_paths(tmp_path, "job").resolve_transcript_json_path() == legacy


def test_duration_fit_classification(load_script):
    module = load_script("06_generate_tts_segments.py")
    status, speed, retry = module._classify_duration(3.92, 4.2)
    assert (status, retry) == ("ok", False)
    assert speed == pytest.approx(3.92 / 4.2)
    status, speed, retry = module._classify_duration(4.32, 4.0)
    assert (status, retry) == ("retry", True)
    assert speed == pytest.approx(1.08)
    status, speed, retry = module._classify_duration(5.4, 4.0)
    assert (status, retry) == ("ng", False)
    assert speed == pytest.approx(1.35)


def test_speed_retry_result_must_be_measured(load_script):
    module = load_script("06_generate_tts_segments.py")
    fields = module._fit_fields(4.0, 4.32, 4.05, 1.08, "ng", 1)
    assert fields["fit_status"] == "ng"
    assert fields["translation_retry_required"] is True
    assert fields["retry_count"] == 1


def test_retry_artifact_contains_only_ng_and_shorter_target(tmp_path, load_script):
    module = load_script("06_generate_tts_segments.py")
    path = tmp_path / "duration_retry_required.jsonl"
    common = {"start": 1.0, "end": 5.0, "available_duration": 4.0,
              "raw_tts_duration": 5.4, "text": "これは長すぎる翻訳です"}
    module._write_retry_artifact(path, [
        {**common, "segment_id": "bad", "translation_retry_required": True},
        {**common, "segment_id": "good", "translation_retry_required": False},
    ])
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["segment_id"] for row in rows] == ["bad"]
    assert rows[0]["target_chars"] < len(common["text"])


def test_segment_id_selector_intersects_range_without_changing_timestamps(load_script):
    module = load_script("06_generate_tts_segments.py")
    segments = [
        {"segment_id": "utt_0001", "start": 0.0, "end": 1.0},
        {"segment_id": "utt_0002", "start": 2.0, "end": 3.0},
        {"segment_id": "utt_0003", "start": 4.0, "end": 5.0},
    ]
    selected, partial = module._select_process_segments(
        segments, 2, 3, None, ["utt_0001", "utt_0003"]
    )
    assert partial is True
    assert selected == [(3, segments[2])]
    assert segments[2]["start"] == 4.0


def test_resume_cache_requires_same_segment_and_voice_and_preserves_fit_metadata(load_script):
    module = load_script("06_generate_tts_segments.py")
    segment = {"segment_id": "utt_0001", "text": "同じ翻訳", "start": 0.0, "end": 4.0}
    metadata = module._fit_fields(4.0, 4.32, 3.98, 1.08, "fitted", 1)
    existing = {**segment, **metadata}
    settings = {"base_url": "http://127.0.0.1:10101", "speaker_id": 10}

    assert module._is_reusable_tts(existing, segment, settings, settings) is True
    assert module._is_reusable_tts(existing, {**segment, "text": "短い翻訳"},
                                   settings, settings) is False
    assert module._is_reusable_tts(existing, segment, settings,
                                   {**settings, "speaker_id": 11}) is False
    assert module._reused_fit_metadata(existing, 4.0, 3.98) == metadata


def test_unchanged_resume_reuses_wav_and_keeps_fitted_metadata(tmp_path, load_script, monkeypatch):
    module = load_script("06_generate_tts_segments.py")
    job = tmp_path / "job"
    (job / "05_segments").mkdir(parents=True)
    (job / "06_tts").mkdir()
    segment = {"segment_id": "utt_0001", "start": 0.0, "end": 4.0, "text": "同じ翻訳"}
    (job / "05_segments/translated_segments.json").write_text(
        json.dumps({"segments": [segment]})
    )
    _wav(job / "06_tts/segment_000001.wav", 3980)
    metadata = module._fit_fields(4.0, 4.32, 3.98, 1.08, "fitted", 1)
    (job / "06_tts/tts_manifest.json").write_text(json.dumps({
        "base_url": "http://aivis", "speaker_id": 10, "items": [{
            "index": 1, **segment, "wav_path": "06_tts/segment_000001.wav",
            "status": "generated", **metadata,
        }]
    }))
    monkeypatch.setattr(module, "_post_synthesis",
                        lambda **kwargs: pytest.fail("unchanged cache should be reused"))

    module.main(["--job-id", "job", "--output-dir", str(tmp_path),
                 "--base-url", "http://aivis/", "--speaker-id", "10", "--resume"])

    item = json.loads((job / "06_tts/tts_manifest.json").read_text())["items"][0]
    assert item["status"] == "reused"
    assert {field: item[field] for field in module.FIT_METADATA_FIELDS} == metadata
    run_metrics = json.loads((job / "06_tts/tts_manifest.json").read_text())["run_metrics"]
    assert run_metrics["selected_units"] == 1
    assert run_metrics["reused_units"] == 1
    assert run_metrics["generated_units"] == 0
    assert run_metrics["normal_synthesis_count"] == 0
    assert run_metrics["speed_fit_synthesis_count"] == 0


def test_corrected_text_resume_regenerates_and_updates_selective_retry_artifact(
    tmp_path, load_script, monkeypatch
):
    module = load_script("06_generate_tts_segments.py")
    job = tmp_path / "job"
    segments_dir = job / "05_segments"
    tts_dir = job / "06_tts"
    segments_dir.mkdir(parents=True)
    tts_dir.mkdir()
    current_segment = {
        "segment_id": "utt_0001", "start": 0.0, "end": 4.0, "text": "短い翻訳"
    }
    (segments_dir / "translated_segments.json").write_text(json.dumps({
        "segments": [current_segment, {
            "segment_id": "utt_0002", "start": 4.0, "end": 8.0, "text": "別の長い翻訳"
        }]
    }))
    _wav(tts_dir / "segment_000001.wav", 5400)
    old_ng = module._fit_fields(4.0, 5.4, 5.4, 1.0, "ng", 0)
    (tts_dir / "tts_manifest.json").write_text(json.dumps({
        "base_url": "http://aivis", "speaker_id": 10, "items": [
            {"index": 1, "segment_id": "utt_0001", "start": 0.0, "end": 4.0,
             "text": "長い旧翻訳", "wav_path": "06_tts/segment_000001.wav",
             "status": "generated", **old_ng},
            {"index": 2, "segment_id": "utt_0002", "start": 4.0, "end": 8.0,
             "text": "別の長い翻訳", "wav_path": "06_tts/segment_000002.wav",
             "status": "generated", **old_ng},
        ]
    }))

    syntheses = []
    monkeypatch.setattr(module, "_post_audio_query", lambda **kwargs: {})
    monkeypatch.setattr(module, "_post_synthesis",
                        lambda **kwargs: syntheses.append(kwargs) or _wav_bytes(3000))
    monkeypatch.setattr(module.requests, "Session",
                        lambda: type("Session", (), {"close": lambda self: None})())

    module.main(["--job-id", "job", "--output-dir", str(tmp_path),
                 "--base-url", "http://aivis", "--speaker-id", "10",
                 "--segment-id", "utt_0001", "--resume"])

    manifest = json.loads((tts_dir / "tts_manifest.json").read_text())
    assert len(syntheses) == 1
    assert manifest["items"][0]["status"] == "generated"
    assert manifest["items"][0]["text"] == "短い翻訳"
    assert manifest["items"][0]["fit_status"] == "ok"
    assert manifest["run_metrics"]["selected_units"] == 1
    assert manifest["run_metrics"]["generated_units"] == 1
    assert manifest["run_metrics"]["normal_synthesis_count"] == 1
    assert manifest["run_metrics"]["fit_ok_count"] == 1
    assert manifest["run_metrics"]["manifest_counts"]["fit_ng_count"] == 1
    retry_rows = [json.loads(line) for line in
                  (segments_dir / "duration_retry_required.jsonl").read_text().splitlines()]
    assert [row["segment_id"] for row in retry_rows] == ["utt_0002"]


def test_tts_run_metrics_count_normal_and_speed_fit_synthesis(
    tmp_path, load_script, monkeypatch
):
    module = load_script("06_generate_tts_segments.py")
    job = tmp_path / "job"
    (job / "05_segments").mkdir(parents=True)
    (job / "05_segments/translated_segments.json").write_text(json.dumps({
        "segments": [
            {"segment_id": "ok", "start": 0.0, "end": 1.0, "text": "通常"},
            {"segment_id": "fit", "start": 1.0, "end": 2.0, "text": "調整"},
            {"segment_id": "ng", "start": 2.0, "end": 3.0, "text": "長い"},
            {"segment_id": "empty1", "start": 3.0, "end": 4.0, "text": ""},
            {"segment_id": "empty2", "start": 4.0, "end": 5.0, "text": ""},
        ]
    }))
    wav_results = iter([
        _wav_bytes(900), _wav_bytes(1080), _wav_bytes(950), _wav_bytes(1300)
    ])
    monkeypatch.setattr(module, "_post_audio_query", lambda **kwargs: {})
    monkeypatch.setattr(module, "_post_synthesis", lambda **kwargs: next(wav_results))
    monkeypatch.setattr(module.requests, "Session",
                        lambda: type("Session", (), {"close": lambda self: None})())

    module.main(["--job-id", "job", "--output-dir", str(tmp_path),
                 "--base-url", "http://aivis", "--speaker-id", "10"])

    metrics = json.loads((job / "06_tts/tts_manifest.json").read_text())["run_metrics"]
    assert metrics["selected_units"] == 5
    assert metrics["generated_units"] == 3
    assert metrics["skipped_empty_units"] == 2
    assert metrics["normal_synthesis_count"] == 3
    assert metrics["speed_fit_synthesis_count"] == 1
    assert (metrics["fit_ok_count"], metrics["fit_fitted_count"], metrics["fit_ng_count"]) == (1, 1, 1)
    assert metrics["manifest_counts"] == {
        "fit_ok_count": 1, "fit_fitted_count": 1, "fit_ng_count": 1,
    }


def test_local_pipeline_forwards_repeatable_segment_ids(load_script, monkeypatch, tmp_path):
    module = load_script("91_run_local_tts_pipeline.py")
    calls = []
    monkeypatch.setattr(module, "_run_step",
                        lambda label, filename, args: calls.append((filename, args)))
    module.main(["--job-id", "job", "--output-dir", str(tmp_path), "--skip-build-translated",
                 "--segment-id", "utt_0001", "--segment-id", "utt_0003"])
    tts_args = next(args for filename, args in calls if filename == "06_generate_tts_segments.py")
    assert tts_args.count("--segment-id") == 2
    assert "utt_0001" in tts_args and "utt_0003" in tts_args
