#!/usr/bin/env python3
"""Experimental one-command Codex CLI + Edge TTS YouTube dub route."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def _load(filename: str):
    path = SCRIPT_DIR / filename
    name = f"experimental_dub_{filename.replace('.', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load pipeline stage: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
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


def _stage(name: str, callback) -> None:
    try:
        result = callback()
        if result not in (None, 0) and not isinstance(result, dict):
            raise RuntimeError(f"stage returned exit code {result}")
    except Exception as exc:
        raise RuntimeError(f"{name} failed: {exc}") from exc


def run(url: str, *, output_dir: str = "output", voice: str = "ja-JP-KeitaNeural",
        stages: dict | None = None) -> Path:
    job_id = _video_id(url)
    if not job_id:
        raise RuntimeError("Prepare failed: YouTube URLから動画IDを取得できませんでした。")
    if stages is None:
        from path_layout import build_job_paths
        from providers import translation_provider

        paths = build_job_paths(output_dir, job_id)
        prepare = _load("run_prepare.py")
        build = _load("04_build_translated_segments.py")
        preflight = _load("05_preflight_local_run.py")
        edge = _load("06_generate_edge_tts_segments.py")
        audio = _load("07_build_dub_audio.py")
        mux = _load("08_mux_video.py")
        common = ["--job-id", job_id, "--output-dir", output_dir]
        stages = {
            "Prepare": lambda: prepare.main(["--youtube-url", url, "--output-dir", output_dir]),
            "Translation": lambda: translation_provider("codex_cli")(
                input_dir=paths.translation_input_dir, output_dir=paths.translation_output_dir,
                manifest_path=paths.translation_manifest_path,
                rules_path=REPO_ROOT / "docs/translation_mode.md"),
            "Build": lambda: build.main(common),
            "Preflight": lambda: preflight.main(common),
            "TTS": lambda: edge.main(common + ["--voice", voice, "--resume"]),
            "Audio": lambda: audio.main(common),
            "Mux": lambda: mux.main(common),
        }
        final_path = paths.dubbed_video_path
    else:
        final_path = Path(output_dir) / job_id / "dubbed_video.mp4"
    for name in ("Prepare", "Translation", "Build", "Preflight", "TTS", "Audio", "Mux"):
        _stage(name, stages[name])
    return final_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--voice", default="ja-JP-KeitaNeural")
    args = parser.parse_args(argv)
    os.chdir(REPO_ROOT)
    url = args.url or input("YouTube URLを貼ってください:\n> ").strip()
    if not url:
        print("入力が空だったため終了しました。")
        return 1
    try:
        video = run(url, output_dir=args.output_dir, voice=args.voice)
    except RuntimeError as exc:
        print(exc)
        return 1
    print("\nCompleted.")
    print("Translation: codex_cli")
    print("TTS: edge")
    print(f"Video: {video.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
