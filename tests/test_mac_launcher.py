import importlib.util, stat
from pathlib import Path
P=Path(__file__).parents[1]/"tools/install_mac_desktop_launcher.py"; S=importlib.util.spec_from_file_location("launcher",P); m=importlib.util.module_from_spec(S); S.loader.exec_module(m)
def test_installs_only_owned_executable_with_quoted_paths(tmp_path):
 home=tmp_path/"home"; desktop=home/"Desktop"; desktop.mkdir(parents=True); unrelated=desktop/"keep.txt"; unrelated.write_text("keep")
 repo=tmp_path/"repo with spaces"; repo.mkdir(); out=m.install(repo=repo,home=home); text=out.read_text()
 assert out==desktop/"YouTube Dub.command" and out.stat().st_mode & stat.S_IXUSR
 assert text.startswith("#!/bin/zsh") and "repo='/" in text and ".venv/bin/python" in text and "user_tools/00_dub_youtube.py" in text
 assert "Press Enter to close" in text and "(( status == 0 )) || failure" in text
 assert unrelated.read_text()=="keep"
