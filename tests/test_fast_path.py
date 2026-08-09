import json
import struct
import wave


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
