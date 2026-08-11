import asyncio
import json


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
    assert not module._cache_matches(
        {"tts_provider": "aivis", "voice": "1"}, manifest["items"][0], segments[0],
        "ja-JP-KeitaNeural", tmp_path / "missing.wav")
