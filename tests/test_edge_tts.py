import asyncio
import json

from providers.tts.edge import EdgeTTSError


def test_edge_provider_default_alternate_and_error(tmp_path):
    from providers.tts.edge import DEFAULT_VOICE, EdgeTTSError, EdgeTTSProvider

    calls = []
    async def save(text, voice, rate, path):
        calls.append((text, voice, rate, path))
        path.write_bytes(b"audio")
    provider = EdgeTTSProvider(save=save)
    assert provider.voice == DEFAULT_VOICE
    assert provider.synthesize("文", tmp_path / "a.mp3")["rate"] == "+0%"
    alternate = EdgeTTSProvider("ja-JP-NanamiNeural", save=save)
    alternate.synthesize("文", tmp_path / "b.mp3", rate_percent=15)
    assert calls[-1][1:3] == ("ja-JP-NanamiNeural", "+15%")

    async def fail(*args):
        raise OSError("offline")
    try:
        EdgeTTSProvider(save=fail).synthesize("文", tmp_path / "c.mp3")
    except EdgeTTSError as exc:
        assert "Edge TTS" in str(exc)
    else:
        raise AssertionError("Edge error was not attributed")


def test_edge_duration_fitting_and_provider_cache(tmp_path, load_script):
    module = load_script("06_generate_edge_tts_segments.py")
    job = tmp_path / "job/05_segments"
    job.mkdir(parents=True)
    segments = [
        {"segment_id": "ok", "start": 0.0, "end": 1.0, "text": "a"},
        {"segment_id": "fit", "start": 1.0, "end": 2.0, "text": "b"},
        {"segment_id": "ng", "start": 2.0, "end": 3.0, "text": "c"},
    ]
    (job / "translated_segments.json").write_text(json.dumps({"segments": segments}))
    durations = iter([0.8, 1.1, 0.95, 1.3])
    rates = []
    class Provider:
        def synthesize(self, text, output, rate_percent=0):
            rates.append(rate_percent)
            output.write_bytes(b"mp3")
    def convert(source, target, ffmpeg):
        target.write_bytes(b"wav")
    manifest = module.generate_job(
        job_id="job", output_dir=tmp_path, provider=Provider(), converter=convert,
        measure=lambda _: next(durations))
    assert [item["fit_status"] for item in manifest["items"]] == ["ok", "fitted", "ng"]
    assert manifest["items"][2]["translation_retry_required"] is True
    assert rates == [0, 0, 11, 0]
    retry_rows = [json.loads(line) for line in
                  (tmp_path / "job/05_segments/duration_retry_required.jsonl").read_text().splitlines()]
    assert [row["segment_id"] for row in retry_rows] == ["ng"]
    assert set(retry_rows[0]) == {"segment_id", "start", "end", "duration", "current_text",
                                  "raw_tts_duration", "required_speed", "target_chars"}
    assert not module._cache_matches(
        {"tts_provider": "aivis", "voice": "1"}, manifest["items"][0], segments[0],
        "ja-JP-KeitaNeural", tmp_path / "missing.wav")


def _write_segments(tmp_path):
    directory = tmp_path / "job/05_segments"
    directory.mkdir(parents=True)
    segments = [
        {"segment_id": "one", "start": 0.0, "end": 1.0, "text": "one"},
        {"segment_id": "two", "start": 1.0, "end": 2.0, "text": "two"},
        {"segment_id": "three", "start": 2.0, "end": 3.0, "text": "three"},
    ]
    (directory / "translated_segments.json").write_text(json.dumps({"segments": segments}))
    return segments


def test_edge_partial_failure_continues_and_resume_repairs_only_failure(tmp_path, load_script):
    module = load_script("06_generate_edge_tts_segments.py")
    _write_segments(tmp_path)
    first_calls = []

    class FirstProvider:
        def synthesize(self, text, output, rate_percent=0):
            first_calls.append(text)
            if text == "two":
                raise EdgeTTSError("Edge TTS request failed.")
            output.write_bytes(b"mp3")

    def convert(source, target, ffmpeg):
        target.write_bytes(b"wav")

    first = module.generate_job(job_id="job", output_dir=tmp_path, provider=FirstProvider(),
                                converter=convert, measure=lambda _: 0.8)
    assert first_calls == ["one", "two", "three"]
    assert len(first["items"]) == 3
    assert first["items"][1]["status"] == "failed"
    assert first["items"][1]["wav_path"] is None
    assert first["run_metrics"]["failed_units"] == 1
    assert not (tmp_path / "job/06_tts/segment_000002.wav").exists()

    second_calls = []
    class SecondProvider:
        def synthesize(self, text, output, rate_percent=0):
            second_calls.append(text)
            output.write_bytes(b"mp3")

    second = module.generate_job(job_id="job", output_dir=tmp_path, provider=SecondProvider(),
                                 converter=convert, measure=lambda _: 0.8, resume=True)
    assert second_calls == ["two"]
    assert [item["status"] for item in second["items"]] == ["reused", "generated", "reused"]
    assert second["run_metrics"]["failed_units"] == 0


def test_edge_main_returns_one_after_saving_failure_manifest(tmp_path, load_script, monkeypatch):
    module = load_script("06_generate_edge_tts_segments.py")
    manifest_path = tmp_path / "job/06_tts/tts_manifest.json"

    def failed_job(**kwargs):
        manifest_path.parent.mkdir(parents=True)
        payload = {"run_metrics": {"failed_units": 1}, "items": [{"status": "failed"}]}
        manifest_path.write_text(json.dumps(payload))
        return payload

    monkeypatch.setattr(module, "generate_job", failed_job)
    assert module.main(["--job-id", "job", "--output-dir", str(tmp_path)]) == 1
    assert json.loads(manifest_path.read_text())["items"][0]["status"] == "failed"


def test_edge_cache_rejects_changed_rate_policy(tmp_path, load_script):
    module = load_script("06_generate_edge_tts_segments.py")
    wav = tmp_path / "segment.wav"
    wav.write_bytes(b"wav")
    segment = {"segment_id": "one", "start": 0.0, "end": 1.0, "text": "one"}
    item = {**segment, "status": "generated"}
    manifest = {"tts_provider": "edge", "voice": "ja-JP-KeitaNeural",
                "provider_settings": {"max_rate_percent": 10}}
    assert not module._cache_matches(manifest, item, segment, "ja-JP-KeitaNeural", wav)


def test_edge_resume_reuses_unchanged_and_regenerates_changed_text(tmp_path, load_script):
    module = load_script("06_generate_edge_tts_segments.py")
    segments = _write_segments(tmp_path)
    class Provider:
        def __init__(self): self.calls = []
        def synthesize(self, text, output, rate_percent=0):
            self.calls.append(text); output.write_bytes(b"mp3")
    def convert(source, target, ffmpeg): target.write_bytes(b"wav")
    first = Provider()
    module.generate_job(job_id="job", output_dir=tmp_path, provider=first,
                        converter=convert, measure=lambda _: .5)
    segments[1]["text"] = "changed"
    (tmp_path / "job/05_segments/translated_segments.json").write_text(json.dumps({"segments": segments}))
    second = Provider()
    result = module.generate_job(job_id="job", output_dir=tmp_path, provider=second,
                                 converter=convert, measure=lambda _: .5, resume=True)
    assert second.calls == ["changed"]
    assert [x["status"] for x in result["items"]] == ["reused", "generated", "reused"]
