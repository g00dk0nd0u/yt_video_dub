import json
import struct
import wave

import pytest


def _wav(path, frames, rate=1000):
    with wave.open(str(path), "wb") as writer:
        writer.setparams((1, 2, rate, frames, "NONE", "not compressed"))
        writer.writeframes(struct.pack("<h", 1000) * frames)


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
