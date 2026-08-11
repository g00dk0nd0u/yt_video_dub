#!/usr/bin/env python3
"""One-command Codex CLI + Edge TTS YouTube dub route with hard quality gates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def _load(filename: str):
    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(f"experimental_{filename.replace('.', '_')}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load pipeline stage: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/")[0]
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
        "final_speech_duration", "final_tts_duration", "rate", "fit_status", "coalesced")}


def run(url: str, *, output_dir: str = "output", voice: str = "ja-JP-KeitaNeural",
        max_repair_rounds: int = 2, stages: dict | None = None) -> Path:
    from path_layout import build_job_paths
    from run_diagnostics import RunReport

    job_id = _video_id(url)
    if not job_id:
        raise RuntimeError("Prepare failed: YouTube URLから動画IDを取得できませんでした。")
    paths = build_job_paths(output_dir, job_id)
    report = RunReport(output_dir, job_id, url)
    injected = stages is not None
    if stages is None:
        from providers import translation_provider
        from providers.translation.codex_cli import repair_translations
        prepare, build = _load("run_prepare.py"), _load("04_build_translated_segments.py")
        preflight, edge = _load("05_preflight_local_run.py"), _load("06_generate_edge_tts_segments.py")
        audio, mux = _load("07_build_dub_audio.py"), _load("08_mux_video.py")
        common = ["--job-id", job_id, "--output-dir", output_dir]
        stages = {
            "Prepare": lambda: prepare.main(["--youtube-url", url, "--output-dir", output_dir, "--quiet"]),
            "Translation": lambda: translation_provider("codex_cli")(
                input_dir=paths.translation_input_dir, output_dir=paths.translation_output_dir,
                manifest_path=paths.translation_manifest_path, rules_path=REPO_ROOT / "docs/translation_mode.md"),
            "Build": lambda: build.main(common), "Preflight": lambda: preflight.main(common),
            "TTS": lambda: edge.generate_job(job_id=job_id, output_dir=output_dir, voice=voice, resume=True),
            "Repair": lambda: repair_translations(retry_path=paths.duration_retry_required_path,
                input_dir=paths.translation_input_dir, output_dir=paths.translation_output_dir,
                manifest_path=paths.translation_manifest_path, rules_path=REPO_ROOT / "docs/translation_mode.md"),
            "Audio": lambda: audio.main(common), "Mux": lambda: mux.main(common + ["--quiet"]),
        }
    last_success = "none"
    current = "Prepare"
    try:
        for name in ("Prepare", "Translation", "Build", "Preflight", "TTS"):
            current, started = name, monotonic()
            result = stages[name]()
            if result not in (None, 0) and not isinstance(result, dict):
                raise RuntimeError(f"stage returned exit code {result}")
            stage_result = (_acquisition_summary(paths.job_json_path) if name == "Prepare"
                            else _stage_result(name, result))
            report.stage(name, "OK", monotonic() - started, stage_result)
            print(f"{name:.<16} OK  {monotonic() - started:.1f}s")
            last_success = name
            if name == "Translation" and isinstance(result, dict):
                report.data["translation"] = {key: result[key] for key in ("chunk_count", "segment_count") if key in result}
        manifest = result if isinstance(result, dict) and "run_metrics" in result else (_json(paths.tts_manifest_path) if paths.tts_manifest_path.exists() else {})
        metrics, problems = _tts_quality(manifest)
        report.data["tts"] = metrics
        report.data["quality_problems"] = [_quality_problem(item) for item in problems]
        round_number = 0
        stopped_for_no_progress = []
        while problems and round_number < max_repair_rounds:
            round_number += 1
            current, started = f"Repair #{round_number}", monotonic()
            if injected and "Repair" not in stages:
                raise RuntimeError("TTS contains NG segments and no repair stage is configured")
            changes = stages["Repair"]()
            if not injected:
                stages["Build"]()
            before = {x["segment_id"]: x for x in problems}
            tts_result = stages["TTS"]()
            manifest = tts_result if isinstance(tts_result, dict) else _json(paths.tts_manifest_path)
            metrics, problems = _tts_quality(manifest)
            after = {x["segment_id"]: x for x in manifest.get("items", [])}
            no_progress = []
            for change in changes or []:
                old, new = before.get(change["segment_id"], {}), after.get(change["segment_id"], {})
                reason = None
                if change.get("text_after") == change.get("text_before"):
                    reason = "repaired text was unchanged"
                elif (new.get("fit_status") == "ng" and
                      float(old.get("final_tts_duration") or 0) - float(new.get("final_tts_duration") or 0) < 0.01):
                    reason = "speech duration improved by less than 0.01s"
                entry = {"repair_round": round_number, **change,
                    "duration_before": old.get("final_tts_duration"), "duration_after": new.get("final_tts_duration"),
                    "final_fit_status": new.get("fit_status")}
                if reason:
                    entry["no_progress_reason"] = reason
                    no_progress.append(change["segment_id"])
                report.data["repairs"].append(entry)
            report.stage(current, "OK", monotonic() - started, f"remaining_ng={len(problems)}")
            print(f"{current:.<16} OK  remaining NG={len(problems)}")
            last_success = current
            if no_progress:
                stopped_for_no_progress = no_progress
                break
        report.data["tts"] = metrics
        # Keep the original failure evidence even when repair succeeds.
        known = {x.get("segment_id") for x in report.data["quality_problems"]}
        report.data["quality_problems"].extend(_quality_problem(x) for x in problems
                                                if x.get("segment_id") not in known)
        if problems:
            if stopped_for_no_progress:
                raise RuntimeError("fit_ng_count=" + str(len(problems)) +
                                   "; repair made no progress for " + ", ".join(stopped_for_no_progress))
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
        current, started = "Mux", monotonic(); result = stages["Mux"]()
        if result not in (None, 0) and not isinstance(result, dict): raise RuntimeError(f"stage returned exit code {result}")
        report.stage(current, "OK", monotonic() - started); last_success = current
        print(f"{current:.<16} OK  {monotonic() - started:.1f}s")
        report.finalize(success=True, video=paths.dubbed_video_path)
        return paths.dubbed_video_path
    except Exception as exc:
        report.stage(current, "FAILED", 0, exc)
        report.finalize(success=False, failure={"failed_stage": current, "error_type": type(exc).__name__,
            "message": exc, "last_successful_stage": last_success, "same_command_can_resume": True})
        raise RuntimeError(f"{current} failed: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url"); parser.add_argument("--output-dir", default="output")
    parser.add_argument("--voice", default="ja-JP-KeitaNeural"); parser.add_argument("--max-repair-rounds", type=int, default=2)
    args = parser.parse_args(argv); os.chdir(REPO_ROOT)
    url = args.url or input("YouTube URLを貼ってください:\n> ").strip()
    if not url: print("入力が空だったため終了しました。"); return 1
    if not _video_id(url):
        print("Prepare failed: YouTube URLから動画IDを取得できませんでした。")
        return 1
    try: video = run(url, output_dir=args.output_dir, voice=args.voice, max_repair_rounds=args.max_repair_rounds)
    except RuntimeError as exc: print(exc); print(f"Diagnostic: {Path(args.output_dir) / 'latest_run.txt'}"); return 1
    print(f"\nCompleted.\nVideo: {video.as_posix()}\nDiagnostic: {Path(args.output_dir) / 'latest_run.txt'}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
