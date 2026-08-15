import importlib.util, stat, subprocess
from pathlib import Path
P=Path(__file__).parents[1]/"tools/install_mac_desktop_launcher.py"; S=importlib.util.spec_from_file_location("launcher",P); m=importlib.util.module_from_spec(S); S.loader.exec_module(m)
def test_installs_only_owned_executable_with_quoted_paths(tmp_path):
 home=tmp_path/"home"; desktop=home/"Desktop"; desktop.mkdir(parents=True); unrelated=desktop/"keep.txt"; unrelated.write_text("keep")
 repo=tmp_path/"repo with spaces"; repo.mkdir(); out=m.install(repo=repo,home=home); text=out.read_text()
 assert out==desktop/"YouTube Dub.command" and out.stat().st_mode & stat.S_IXUSR
 assert text.startswith("#!/bin/zsh") and "repo='/" in text and ".venv/bin/python" in text and "user_tools/00_dub_youtube.py" in text
 assert "Press Enter to close" in text and "exit_status=$?" in text
 assert "(( exit_status == 0 )) || failure" in text and "\nstatus=$?" not in text
 assert unrelated.read_text()=="keep"


def test_launcher_reports_child_failure_without_zsh_readonly_status_error(tmp_path):
 home=tmp_path/"home"; (home/"Desktop").mkdir(parents=True)
 repo=tmp_path/"repo"; python=repo/".venv/bin/python"; python.parent.mkdir(parents=True)
 python.write_text("#!/bin/zsh\nexit 7\n"); python.chmod(0o755)
 entrypoint=repo/"user_tools/00_dub_youtube.py"; entrypoint.parent.mkdir(); entrypoint.write_text("")
 launcher=m.install(repo=repo,home=home)
 result=subprocess.run(["/bin/zsh",str(launcher)],input="\n",capture_output=True,text=True)
 assert result.returncode==7
 assert "YouTube Dub failed (exit 7)." in result.stderr
 assert "read-only variable: status" not in result.stderr
