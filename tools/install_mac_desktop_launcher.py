#!/usr/bin/env python3
"""Install the repository's lightweight macOS Desktop launcher."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

LAUNCHER_NAME = "YouTube Dub.command"


def launcher_text(repo: Path) -> str:
    repo = repo.resolve()
    python = repo / ".venv/bin/python"
    entrypoint = repo / "user_tools/00_dub_youtube.py"
    return f"""#!/bin/zsh
repo={shlex.quote(str(repo))}
python={shlex.quote(str(python))}
entrypoint={shlex.quote(str(entrypoint))}
failure() {{
  print -u2 -- "$1"
  read 'reply?Press Enter to close...'
  exit "${{2:-1}}"
}}
[[ -x "$python" ]] || failure "YouTube Dub: missing .venv/bin/python" 1
[[ -f "$entrypoint" ]] || failure "YouTube Dub: missing dubbing entrypoint" 1
cd "$repo" || failure "YouTube Dub: cannot open repository" 1
"$python" "$entrypoint"
exit_status=$?
(( exit_status == 0 )) || failure "YouTube Dub failed (exit $exit_status)." "$exit_status"
exit 0
"""


def install(*, repo: Path | None = None, home: Path | None = None) -> Path:
    repo = (repo or Path(__file__).resolve().parent.parent).resolve()
    desktop = (home or Path.home()) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    launcher = desktop / LAUNCHER_NAME
    temporary = desktop / f".{LAUNCHER_NAME}.tmp"
    try:
        temporary.write_text(launcher_text(repo), encoding="utf-8", newline="\n")
        temporary.chmod(0o755)
        os.replace(temporary, launcher)
    finally:
        temporary.unlink(missing_ok=True)
    launcher.chmod(0o755)
    return launcher


def main() -> int:
    print(install())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
