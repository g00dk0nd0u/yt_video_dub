import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).parents[1] / "scripts/01_prepare_source.py"
    spec = importlib.util.spec_from_file_location("prepare_source_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_existing_nonempty_source_is_reused_without_download(tmp_path, monkeypatch):
    module = _module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    canonical = source_dir / "source.mp4"
    canonical.write_bytes(b"existing")
    monkeypatch.setattr(module, "_download_with_strategy",
                        lambda *_: pytest.fail("network download must be skipped"))

    result, diagnostics = module._acquire_youtube_source("https://youtu.be/id", source_dir)

    assert result == canonical
    assert diagnostics == {"source_reused": True, "attempted_strategies": []}


def test_primary_success_never_calls_fallback(tmp_path, monkeypatch):
    module = _module()
    calls = []
    tmp_path.mkdir(exist_ok=True)

    def download(url, source_dir, strategy):
        calls.append(strategy.name)
        target = source_dir / "source.mp4"
        target.write_bytes(b"video")
        return target

    monkeypatch.setattr(module, "_download_with_strategy", download)
    result, diagnostics = module._acquire_youtube_source("url", tmp_path)
    assert result.is_file()
    assert calls == [module.PRIMARY_STRATEGY.name]
    assert diagnostics["successful_strategy"] == module.PRIMARY_STRATEGY.name


def test_403_gets_exactly_one_fallback_and_succeeds(tmp_path, monkeypatch):
    module = _module()
    calls = []

    def download(url, source_dir, strategy):
        calls.append(strategy.name)
        if not strategy.fallback:
            raise module.SourceAcquisitionError("download", "HTTP Error 403: Forbidden",
                                                strategy=strategy.name, http_403=True)
        target = source_dir / "source.mp4"
        target.write_bytes(b"video")
        return target

    monkeypatch.setattr(module, "_download_with_strategy", download)
    result, diagnostics = module._acquire_youtube_source("url", tmp_path)
    assert result.stat().st_size
    assert calls == [strategy.name for strategy in module.ACQUISITION_STRATEGIES]
    assert diagnostics["attempted_strategies"] == calls


def test_two_403_failures_are_bounded_and_diagnostic_is_sanitized(tmp_path, monkeypatch):
    module = _module()
    calls = []

    def fail(url, source_dir, strategy):
        calls.append(strategy.name)
        raise module.SourceAcquisitionError(
            "download",
            "HTTP Error 403 https://rr.googlevideo.com/videoplayback?token=secret cookie=abc",
            strategy=strategy.name, http_403=True,
        )

    monkeypatch.setattr(module, "_download_with_strategy", fail)
    with pytest.raises(module.SourceAcquisitionError) as caught:
        module._acquire_youtube_source("url", tmp_path)
    message = str(caught.value)
    assert calls == [strategy.name for strategy in module.ACQUISITION_STRATEGIES]
    assert "attempted_strategies=yt-dlp-default,youtube-android-vr" in message
    assert "http_403=true" in message
    assert "googlevideo" not in message and "secret" not in message and "cookie=abc" not in message
    assert "PO-token-capable" in message


@pytest.mark.parametrize("stage", ["metadata", "normalization"])
def test_nonretryable_errors_do_not_create_retry_storm(tmp_path, monkeypatch, stage):
    module = _module()
    calls = []
    if stage == "metadata":
        class BrokenYDL:
            def __init__(self, options): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, *args, **kwargs): raise ValueError("bad URL")
        monkeypatch.setattr(module, "YoutubeDL", BrokenYDL)
        with pytest.raises(module.SourceAcquisitionError, match="metadata failure"):
            module._extract_youtube_metadata("bad")
    else:
        def fail(url, source_dir, strategy):
            calls.append(strategy.name)
            raise module.SourceAcquisitionError("normalization", "disk full", strategy=strategy.name)
        monkeypatch.setattr(module, "_download_with_strategy", fail)
        with pytest.raises(module.SourceAcquisitionError, match="normalization failure"):
            module._acquire_youtube_source("url", tmp_path)
        assert calls == [module.PRIMARY_STRATEGY.name]


def test_failed_strategy_cleans_partial_and_never_creates_canonical(tmp_path, monkeypatch):
    module = _module()

    class BrokenYDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *args, **kwargs):
            Path(self.options["outtmpl"].replace("%(ext)s", "mp4.part")).write_bytes(b"partial")
            raise module.DownloadError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(module, "YoutubeDL", BrokenYDL)
    with pytest.raises(module.SourceAcquisitionError, match="http_403=true"):
        module._download_with_strategy("url", tmp_path, module.PRIMARY_STRATEGY)
    assert not (tmp_path / "source.mp4").exists()
    assert list(tmp_path.iterdir()) == []


def test_prepare_records_source_contract_and_acquisition(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_extract_youtube_metadata",
                        lambda _: {"id": "video-id", "title": "Title"})

    def acquire(url, source_dir):
        target = source_dir / "source.mp4"
        target.write_bytes(b"video")
        return target, {"source_reused": False, "attempted_strategies": ["yt-dlp-default"]}

    monkeypatch.setattr(module, "_acquire_youtube_source", acquire)
    assert module.prepare_source(youtube_url="url", local_video=None, job_id=None,
                                 output_dir=str(tmp_path)) == "video-id"
    payload = json.loads((tmp_path / "video-id/01_source/job.json").read_text())
    assert payload["source_path"] == "01_source/source.mp4"
    assert payload["acquisition"]["source_reused"] is False
