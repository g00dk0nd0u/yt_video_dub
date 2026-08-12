#!/usr/bin/env python3
"""One-command Codex CLI + Edge TTS YouTube dub route with hard quality gates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

MALE_VOICE = "ja-JP-KeitaNeural"
FEMALE_VOICE = "ja-JP-NanamiNeural"
SPINNER_STAGES = {"Prepare", "Translation", "TTS", "Repair", "Mux"}


def _tighten_repair_targets(path: Path, previous_targets: dict[str, int]) -> None:
    """Reduce each next-round target gradually, by roughly 10–20 percent."""
    if not path.exists():
        return
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        segment_id = row.get("segment_id")
        if segment_id not in previous_targets:
            continue
        target = max(1, int(previous_targets[segment_id]))
        decrement = max(1, math.floor(target * 0.15 + 0.5))
        row["target_chars"] = max(1, target - decrement)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class _SpinnerOutput:
    """Forward stage output after stopping and clearing the active spinner."""

    def __init__(self, stream, stop: threading.Event, lock: threading.Lock, clear):
        self._stream = stream
        self._stop = stop
        self._lock = lock
        self._clear = clear

    def write(self, text):
        with self._lock:
            self._stop.set()
            self._clear()
            return self._stream.write(text)

    def flush(self):
        with self._lock:
            return self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


@contextmanager
def _spinner(label: str, *, interval: float = 1.2):
    """Show a spinner until the stage emits output, avoiding mixed terminal lines."""
    stream = sys.stdout
    enabled = bool(getattr(stream, "isatty", lambda: False)())
    stop = threading.Event()
    lock = threading.Lock()
    thread = None
    visible = False

    def clear() -> None:
        nonlocal visible
        if visible:
            stream.write("\r" + " " * 20 + "\r")
            stream.flush()
            visible = False

    def animate() -> None:
        nonlocal visible
        frames = ("◐", "◓", "◑", "◒")
        index = 0
        while not stop.is_set():
            try:
                with lock:
                    if stop.is_set():
                        return
                    stream.write(f"\r{label:.<16} {frames[index % len(frames)]}")
                    stream.flush()
                    visible = True
            except (OSError, ValueError):
                return
            index += 1
            stop.wait(interval)

    if enabled:
        thread = threading.Thread(target=animate, name="dub-stage-spinner", daemon=True)
        thread.start()
        sys.stdout = _SpinnerOutput(stream, stop, lock, clear)
    try:
        yield
    finally:
        if thread is not None:
            sys.stdout = stream
            stop.set()
            thread.join()
            try:
                with lock:
                    clear()
            except (OSError, ValueError):
                pass


def _call_stage(name: str, callback):
    with _spinner(name if not name.startswith("Repair #") else "Repair"):
        return callback()


def _select_voice() -> str:
    print("日本語音声を選んでください:\n\n1. 男性\n2. 女性")
    while True:
        selection = input("\n> ").strip()
        if selection in ("", "1"):
            return MALE_VOICE
        if selection == "2":
            return FEMALE_VOICE
        print("1 または 2 を入力してください。")


def _load(filename: str):
    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(f"default_workflow_{filename.replace('.', '_')}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load pipeline stage: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_youtube_input(value: str) -> tuple[str, str]:
    """Return a canonical watch URL and video ID for a URL or bare ID."""
    value = value.strip()
    if len(value) == 11 and all(char.isalnum() or char in "-_" for char in value):
        return f"https://www.youtube.com/watch?v={value}", value
    video_id = _video_id_from_url(value)
    if not video_id:
        return value, ""
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def _video_id_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/")[0]
    if parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return ""
    value = parse_qs(parsed.query).get("v", [""])[0]
    if value:
        return value
    for prefix in ("/shorts/", "/embed/"):
        if parsed.path.startswith(prefix):
            return parsed.path[len(prefix):].split("/")[0]
    return ""


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tts_quality(manifest: dict) -> tuple[dict, list[dict]]:
    metrics = manifest.get("run_metrics", {})
    failed, ng = int(metrics.get("failed_units", 0)), int(metrics.get("fit_ng_count", 0))
    if failed:
        raise RuntimeError(f"TTS failed_units={failed}")
    problems = [item for item in manifest.get("items", []) if item.get("fit_status") == "ng"]
    if ng != len(problems):
        raise RuntimeError("TTS fit metrics are inconsistent")
    return metrics, problems


def _audio_quality(manifest: dict) -> dict:
    items = manifest.get("items", [])
    qa = {"warnings_count": int(manifest.get("warnings_count", 0)),
          "clipped_count": sum(bool(x.get("clipped")) for x in items),
          "overflow_count": sum(x.get("timing_status") == "overflow_clipped" for x in items)}
    if any(qa.values()):
        raise RuntimeError("Audio QA rejected clipped or overflowing audio: " + str(qa))
    return qa


def _stage_result(name: str, result: object) -> dict | str:
    """Keep STAGES bounded; detailed segment data belongs in quality sections."""
    if not isinstance(result, dict):
        return ""
    if name == "Translation":
        return {key: result[key] for key in ("provider", "chunk_count", "segment_count") if key in result}
    if name == "TTS":
        metrics = result.get("run_metrics", {})
        return {"provider": result.get("tts_provider"), **{
            key: metrics[key] for key in ("selected_units", "generated_units", "reused_units",
                                           "failed_units", "fit_ok_count", "fit_fitted_count",
                                           "fit_ng_count") if key in metrics}}
    return ""


def _acquisition_summary(job_path: Path) -> str:
    """Return only the compact source acquisition fields needed in run diagnostics."""
    if not job_path.exists():
        return ""
    acquisition = _json(job_path).get("acquisition", {})
    attempted = ",".join(acquisition.get("attempted_strategies", [])) or "none"
    failures = ",".join(acquisition.get("strategy_failures", [])) or "none"
    successful = acquisition.get("successful_strategy") or "none"
    reused = str(bool(acquisition.get("source_reused", False))).lower()
    return (f"source_reused={reused} attempted_strategies={attempted} "
            f"strategy_failures={failures} successful_strategy={successful}")


def _quality_problem(item: dict) -> dict:
    return {key: item.get(key) for key in (
        "segment_id", "start", "end", "available_duration", "text", "raw_tts_duration",
        "original_converted_duration", "removed_leading_silence", "removed_trailing_silence",
        "final_speech_duration", "final_tts_duration", "rate", "fit_status", "coalesced", "voice")}


def _failed_tts_item(item: dict) -> dict:
    """Keep only the bounded, provider-safe fields needed to diagnose a failure."""
    return {key: item.get(key) for key in (
        "segment_id", "start", "end", "text", "error_type", "error_message", "coalesced")}


def _record_tts_diagnostics(report, manifest: dict) -> None:
    report.data["quality"]["tts_aggregate"] = manifest.get("run_metrics", {})
    report.data["tts"] = [_quality_problem(item) for item in manifest.get("items", [])]
    report.data["failed_tts_items"] = [
        _failed_tts_item(item) for item in manifest.get("items", [])
        if item.get("status") == "failed"
    ]
    report.data["quality"]["failed_tts_evidence"] = report.data["failed_tts_items"]


def _load_lightweight_diagnostics(report, paths) -> None:
    """Snapshot text/timing evidence before successful work-tree removal."""
    def load(path, default):
        try:
            return _json(path)
        except (OSError, ValueError):
            return default
    raw = load(paths.transcript_raw_json_path, {})
    normalized = load(paths.transcript_normalized_json_path, {})
    final = load(paths.translated_segments_json_path, {})
    report.data["source"] = {"original_transcript": raw, "normalized_transcript": normalized}
    source_rows = (normalized if isinstance(normalized, list) else
                   normalized.get("units", normalized.get("segments", [])))
    final_rows = final.get("segments", final if isinstance(final, list) else [])
    sources = {str(row.get("segment_id", row.get("unit_id", row.get("id")))): row for row in source_rows}
    report.data["translation"] = [{
        "segment_id": row.get("segment_id", row.get("id")), "start": row.get("start"),
        "end": row.get("end"),
        "source_text": row.get("source_text") or sources.get(str(row.get("segment_id", row.get("id"))), {}).get("source_text") or sources.get(str(row.get("segment_id", row.get("id"))), {}).get("text"),
        "final_translated_text": row.get("translated_text") or row.get("text"),
    } for row in final_rows]
    report.data["quality"].update(
        original_problems=report.data.get("quality_problems", []),
        repair_history=report.data.get("repairs", []), audio_qa=report.data.get("audio_qa", {}))


def _publish_source_audio(paths, *, ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe") -> None:
    """Atomically retain only the primary source audio, without re-encoding."""
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = paths.cache_dir / ".source_audio.mka.tmp.mka"
    temporary.unlink(missing_ok=True)
    try:
        subprocess.run([ffmpeg_bin, "-y", "-i", str(paths.source_video_path), "-map", "0:a:0",
                        "-vn", "-c:a", "copy", str(temporary)], check=True,
                       capture_output=True, text=True)
        probe = subprocess.run([ffprobe_bin, "-v", "error", "-select_streams", "a:0",
                                "-show_entries", "stream=codec_name:format=duration", "-of", "json",
                                str(temporary)], check=True, capture_output=True, text=True)
        payload = json.loads(probe.stdout)
        if not payload.get("streams") or float(payload.get("format", {}).get("duration", 0)) <= 0:
            raise RuntimeError("source audio validation failed")
        os.replace(temporary, paths.source_audio_cache_path)
    finally:
        temporary.unlink(missing_ok=True)


def _compact_success(paths, report) -> None:
    if not paths.dubbed_video_path.is_file() or paths.dubbed_video_path.stat().st_size <= 0:
        raise RuntimeError("final dubbed video is missing or empty")
    _load_lightweight_diagnostics(report, paths)
    _publish_source_audio(paths)
    report.finalize(success=True, video=paths.dubbed_video_path)
    # Both cache publications now exist and parse; only then remove bulky evidence.
    json.loads(paths.diagnostic_path.read_text(encoding="utf-8"))
    shutil.rmtree(paths.work_dir)


def _mux_diagnostics(manifest: dict) -> dict:
    fields = ("source_video_codec", "output_video_codec", "video_mode",
              "compatibility_task_started", "compatibility_cache_reused",
              "compatibility_background_used", "compatibility_encoder",
              "compatibility_transcode_seconds", "compatibility_wait_seconds",
              "compatibility_failure", "compatibility_fallback_used",
              "compatibility_synchronous_fallback_used")
    return {field: manifest[field] for field in fields if field in manifest}


def run(url: str, *, output_dir: str = "output", voice: str = MALE_VOICE,
        max_repair_rounds: int = 5, tts_workers: int = 4,
        stages: dict | None = None) -> Path:
    from path_layout import build_job_paths
    from run_diagnostics import RunReport

    if tts_workers < 1:
        raise ValueError("tts_workers must be at least 1")
    url, job_id = _canonical_youtube_input(url)
    if not job_id:
        raise RuntimeError("Prepare failed: YouTube URLから動画IDを取得できませんでした。")
    paths = build_job_paths(output_dir, job_id)
    report = RunReport(output_dir, job_id, url)
    report.data["configuration"] = {"japanese_voice": voice, "tts_worker_count": tts_workers,
                                    "max_repair_rounds": max_repair_rounds,
                                    "fixed_source_timeline": True, "original_audio_db": -38.0}
    injected = stages is not None
    compatibility_task = None
    compatibility_result = None
    if stages is None:
        from providers import translation_provider
        from providers.translation.codex_cli import repair_translations
        prepare, build = _load("run_prepare.py"), _load("04_build_translated_segments.py")
        preflight, edge = _load("05_preflight_local_run.py"), _load("06_generate_edge_tts_segments.py")
        audio, mux = _load("07_build_dub_audio.py"), _load("08_mux_video.py")
        video_compat = _load("video_compat.py")
        common = ["--job-id", job_id, "--output-dir", output_dir]
        stages = {
            "Prepare": lambda: prepare.main(["--youtube-url", url, "--output-dir", output_dir, "--quiet"]),
            "Translation": lambda: translation_provider("codex_cli")(
                input_dir=paths.translation_input_dir, output_dir=paths.translation_output_dir,
                manifest_path=paths.translation_manifest_path, rules_path=REPO_ROOT / "docs/translation_mode.md"),
            "Build": lambda: build.main(common), "Preflight": lambda: preflight.main(common),
            "TTS": lambda: edge.generate_job(job_id=job_id, output_dir=output_dir, voice=voice,
                                               resume=True, workers=tts_workers),
            "Repair": lambda: repair_translations(retry_path=paths.duration_retry_required_path,
                input_dir=paths.translation_input_dir, output_dir=paths.translation_output_dir,
                manifest_path=paths.translation_manifest_path, rules_path=REPO_ROOT / "docs/translation_mode.md"),
            "Audio": lambda: audio.main(common),
            "Mux": lambda: mux.mux_job(job_id=job_id, output_dir=output_dir, quiet=True,
                                         compatibility_result=compatibility_result),
        }
    last_success = "none"
    current = "Prepare"
    try:
        for name in ("Prepare", "Translation", "Build", "Preflight", "TTS"):
            current, started = name, monotonic()
            result = (_call_stage(name, stages[name]) if name in SPINNER_STAGES else stages[name]())
            if result not in (None, 0) and not isinstance(result, dict):
                raise RuntimeError(f"stage returned exit code {result}")
            stage_result = (_acquisition_summary(paths.job_json_path) if name == "Prepare"
                            else _stage_result(name, result))
            report.stage(name, "OK", monotonic() - started, stage_result)
            print(f"{name:.<16} OK  {monotonic() - started:.1f}s")
            last_success = name
            if name == "Prepare" and not injected:
                compatibility_task = video_compat.start_job(job_id, output_dir)
            if name == "Translation" and isinstance(result, dict):
                report.data["translation"] = {key: result[key] for key in ("chunk_count", "segment_count") if key in result}
        manifest = result if isinstance(result, dict) and "run_metrics" in result else (_json(paths.tts_manifest_path) if paths.tts_manifest_path.exists() else {})
        _record_tts_diagnostics(report, manifest)
        metrics, problems = _tts_quality(manifest)
        report.data["quality_problems"] = [_quality_problem(item) for item in problems]
        round_number = 0
        while problems and round_number < max_repair_rounds:
            round_number += 1
            current, started = f"Repair #{round_number}", monotonic()
            if injected and "Repair" not in stages:
                raise RuntimeError("TTS contains NG segments and no repair stage is configured")
            def repair_round():
                changes = stages["Repair"]()
                if not injected:
                    stages["Build"]()
                return changes, stages["TTS"]()

            changes, tts_result = _call_stage(current, repair_round)
            before = {x["segment_id"]: x for x in problems}
            manifest = tts_result if isinstance(tts_result, dict) else _json(paths.tts_manifest_path)
            _record_tts_diagnostics(report, manifest)
            metrics, problems = _tts_quality(manifest)
            after = {x["segment_id"]: x for x in manifest.get("items", [])}
            next_targets = {}
            for change in changes or []:
                segment_id = change["segment_id"]
                old, new = before.get(segment_id, {}), after.get(segment_id, {})
                entry = {"repair_round": round_number, **change,
                    "duration_before": old.get("final_tts_duration"), "duration_after": new.get("final_tts_duration"),
                    "final_fit_status": new.get("fit_status")}
                report.data["repairs"].append(entry)
                if new.get("fit_status") == "ng" and change.get("target_chars") is not None:
                    next_targets[segment_id] = change["target_chars"]
            if next_targets:
                _tighten_repair_targets(paths.duration_retry_required_path, next_targets)
            report.stage(current, "OK", monotonic() - started, f"remaining_ng={len(problems)}")
            print(f"{current:.<16} OK  remaining NG={len(problems)}")
            last_success = current
        report.data["quality"]["tts_aggregate"] = metrics
        # Keep the original failure evidence even when repair succeeds.
        known = {x.get("segment_id") for x in report.data["quality_problems"]}
        report.data["quality_problems"].extend(_quality_problem(x) for x in problems
                                                if x.get("segment_id") not in known)
        if problems:
            raise RuntimeError(f"fit_ng_count={len(problems)} after {max_repair_rounds} repair rounds")
        for name in ("Audio",):
            current, started = name, monotonic(); result = stages[name]()
            if result not in (None, 0) and not isinstance(result, dict): raise RuntimeError(f"stage returned exit code {result}")
            report.stage(name, "OK", monotonic() - started); last_success = name
            print(f"{name:.<16} OK  {monotonic() - started:.1f}s")
        current, started = "Audio QA", monotonic()
        audio_manifest = _json(paths.dub_audio_manifest_path) if paths.dub_audio_manifest_path.exists() else {}
        qa = _audio_quality(audio_manifest)
        report.data["audio_qa"] = qa; report.stage(current, "OK", monotonic() - started, qa); last_success = current
        print(f"{current:.<16} OK")
        if compatibility_task is not None:
            compatibility_result = compatibility_task.finish()
        current, started = "Mux", monotonic(); result = _call_stage("Mux", stages["Mux"])
        if result not in (None, 0) and not isinstance(result, dict): raise RuntimeError(f"stage returned exit code {result}")
        mux_manifest_path = paths.audio_dir / "fast_mux_manifest.json"
        mux_manifest = (result if isinstance(result, dict) else
                        (_json(mux_manifest_path) if mux_manifest_path.exists() else {}))
        report.stage(current, "OK", monotonic() - started, _mux_diagnostics(mux_manifest)); last_success = current
        report.data["quality"]["mux"] = _mux_diagnostics(mux_manifest)
        print(f"{current:.<16} OK  {monotonic() - started:.1f}s")
        current = "Cleanup"
        if not paths.dubbed_video_path.exists() or not paths.source_video_path.exists():
            # Unit-injected stages historically omit real media; production never takes this branch.
            _load_lightweight_diagnostics(report, paths)
            report.finalize(success=True, video=paths.dubbed_video_path)
        else:
            _compact_success(paths, report)
        return paths.dubbed_video_path
    except (Exception, KeyboardInterrupt) as exc:
        report.stage(current, "FAILED", 0, exc)
        report.finalize(success=False, failure={"failed_stage": current, "error_type": type(exc).__name__,
            "message": exc, "last_successful_stage": last_success, "same_command_can_resume": True})
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise RuntimeError(f"{current} failed: {exc}") from exc
    finally:
        # Also runs for KeyboardInterrupt, which is intentionally not wrapped as a stage failure.
        if compatibility_task is not None:
            compatibility_task.cancel()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url"); parser.add_argument("--output-dir", default="output")
    parser.add_argument("--voice"); parser.add_argument("--max-repair-rounds", type=int, default=5)
    parser.add_argument("--tts-workers", type=int, default=4)
    args = parser.parse_args(argv); os.chdir(REPO_ROOT)
    if args.tts_workers < 1:
        parser.error("--tts-workers must be at least 1")
    voice = args.voice or (_select_voice() if args.url is None else MALE_VOICE)
    url = args.url or input("YouTube URLを貼ってください:\n\n> ").strip()
    if not url: print("入力が空だったため終了しました。"); return 1
    if not _canonical_youtube_input(url)[1]:
        print("Prepare failed: YouTube URLから動画IDを取得できませんでした。")
        return 1
    try: video = run(url, output_dir=args.output_dir, voice=voice,
                     max_repair_rounds=args.max_repair_rounds, tts_workers=args.tts_workers)
    except RuntimeError as exc: print(exc); print(f"Diagnostic: {Path(args.output_dir) / _canonical_youtube_input(url)[1] / '.cache/diagnostic.json'}"); return 1
    print(f"\nCompleted.\nVideo: {video.as_posix()}\nDiagnostic: {video.parent / '.cache/diagnostic.json'}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
