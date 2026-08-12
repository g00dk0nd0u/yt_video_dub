from __future__ import annotations
import importlib.util, json, subprocess, sys
from pathlib import Path
import pytest

MODULE_PATH=Path(__file__).parents[1]/"user_tools/10_add_background_audio.py"
SPEC=importlib.util.spec_from_file_location("background_audio_tool", MODULE_PATH); assert SPEC and SPEC.loader
background=importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name]=background; SPEC.loader.exec_module(background)

def args(tmp): return background.build_parser().parse_args(["--job-id","job","--output-dir",str(tmp),"--quiet"])
def job(tmp, new=True):
 p=tmp/"job"; (p/".cache").mkdir(parents=True); (p/"dubbed_video.mp4").write_bytes(b"dub")
 (p/".cache/diagnostic.json").write_text("{}")
 if new: (p/".cache/source_audio.mka").write_bytes(b"source")
 else:
  (p/"01_source").mkdir(); (p/"07_audio").mkdir(); (p/"01_source/source.mp4").write_bytes(b"source"); (p/"07_audio/dub_audio.wav").write_bytes(b"ja")
 return p

def fake(monkeypatch,calls):
 monkeypatch.setattr(background.shutil,"which",lambda x:f"/bin/{x}")
 def run(cmd,quiet=True):
  calls.append(cmd)
  if cmd[0].endswith("ffprobe"):
   out=json.dumps({"streams":[{"codec_name":"aac","sample_rate":"48000","channels":2}]}) if "stream=codec_name,sample_rate,channels" in cmd else "10\n"
   return subprocess.CompletedProcess(cmd,0,stdout=out,stderr="")
  if "--two-stems=vocals" in cmd:
   d=Path(cmd[cmd.index("-o")+1])/"htdemucs/source"; d.mkdir(parents=True); (d/"vocals.wav").write_bytes(b"v"); (d/"no_vocals.wav").write_bytes(b"bg")
  else: Path(cmd[-1]).write_bytes(b"generated")
  return subprocess.CompletedProcess(cmd,0,stdout="",stderr="")
 monkeypatch.setattr(background,"_run",run)

def test_discovers_new_and_legacy_jobs(tmp_path):
 job(tmp_path); old=tmp_path/"old"; (old/"01_source").mkdir(parents=True); (old/"07_audio").mkdir(); (old/"dubbed_video.mp4").touch(); (old/"01_source/source.mp4").touch(); (old/"07_audio/dub_audio.wav").touch()
 assert background.list_background_audio_jobs(tmp_path)==["job","old"]

def test_new_layout_uses_dubbed_audio_and_caches_only_flac(tmp_path,monkeypatch):
 p=job(tmp_path); calls=[]; fake(monkeypatch,calls); out=background.add_background_audio(args(tmp_path))
 assert out.is_file() and (p/".cache/source_audio.mka").is_file() and (p/".cache/accompaniment.flac").is_file()
 mix=next(c for c in calls if str(c[-1]).endswith(".tmp.mp4")); assert str(p/"dubbed_video.mp4") in mix and not any("dub_audio.wav" in str(x) for x in mix)
 assert "[0:a:0]" in mix[mix.index("-filter_complex")+1] and "volume=-6dB" in mix[mix.index("-filter_complex")+1]
 assert not list(p.rglob("vocals.wav")) and not list(p.rglob("source.wav"))
 history=json.loads((p/".cache/diagnostic.json").read_text())["background_runs"]; assert history[-1]["success"] is True

def test_accompaniment_cache_reused(tmp_path,monkeypatch):
 job(tmp_path); calls=[]; fake(monkeypatch,calls); background.add_background_audio(args(tmp_path)); calls.clear(); background.add_background_audio(args(tmp_path))
 assert not any("--two-stems=vocals" in c for c in calls)

def test_legacy_job_still_works(tmp_path,monkeypatch):
 job(tmp_path,new=False); calls=[]; fake(monkeypatch,calls); assert background.add_background_audio(args(tmp_path)).is_file()

def test_failure_preserves_standard_and_source(tmp_path,monkeypatch):
 p=job(tmp_path); monkeypatch.setattr(background,"_run",lambda *a,**k: (_ for _ in ()).throw(background.BackgroundAudioError("boom")))
 with pytest.raises(background.BackgroundAudioError): background.add_background_audio(args(tmp_path))
 assert (p/"dubbed_video.mp4").read_bytes()==b"dub" and (p/".cache/source_audio.mka").is_file()
