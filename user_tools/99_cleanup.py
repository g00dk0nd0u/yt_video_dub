#!/usr/bin/env python3
"""Interactively clean old video folders under output/."""

from __future__ import annotations

import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
MENU_TEXT = """\
動画フォルダ掃除
1. 動画一覧を見る
2. 1つ削除する
3. すべて削除する
4. 終了
"""


def _video_dirs() -> list[Path]:
    if not OUTPUT_DIR.exists():
        return []
    return sorted(
        [path for path in OUTPUT_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _display_name(path: Path) -> str:
    return path.name


def _is_safe_output_child(path: Path) -> bool:
    try:
        resolved_output = OUTPUT_DIR.resolve()
        resolved_path = path.resolve()
    except FileNotFoundError:
        return False
    return resolved_path.parent == resolved_output


def _print_video_list() -> list[Path]:
    video_dirs = _video_dirs()
    if not video_dirs:
        print("動画フォルダがありません。")
        print("補足: 保存先は output/ です。")
        return []

    print("動画一覧")
    for index, path in enumerate(video_dirs, start=1):
        print(f"{index}. {_display_name(path)}")
    print("補足: これらは output/ 内のフォルダです。")
    return video_dirs


def _delete_dir(path: Path) -> None:
    if not path.is_dir():
        print("削除対象が見つかりませんでした。")
        return
    if not _is_safe_output_child(path):
        print("安全確認に失敗したため削除を中止しました。")
        return
    shutil.rmtree(path)
    print(f"削除しました: output/{path.name}")


def _delete_one() -> None:
    video_dirs = _print_video_list()
    if not video_dirs:
        return

    selected = input("削除する番号: ").strip()
    if not selected.isdigit():
        print("番号で入力してください。")
        return

    index = int(selected)
    if index < 1 or index > len(video_dirs):
        print("一覧にある番号を選んでください。")
        return

    target = video_dirs[index - 1]
    print(f"削除対象: output/{target.name}")
    confirm = input("本当に削除する場合は DELETE と入力: ").strip()
    if confirm != "DELETE":
        print("削除を中止しました。")
        return

    _delete_dir(target)


def _delete_all() -> None:
    video_dirs = _print_video_list()
    if not video_dirs:
        return

    confirm = input("本当にすべて削除する場合は DELETE ALL と入力: ").strip()
    if confirm != "DELETE ALL":
        print("削除を中止しました。")
        return

    for path in video_dirs:
        _delete_dir(path)


def main() -> int:
    while True:
        print("")
        print(MENU_TEXT, end="")
        choice = input("番号を選んでください [1-4]: ").strip()

        if choice == "1":
            _print_video_list()
        elif choice == "2":
            _delete_one()
        elif choice == "3":
            _delete_all()
        elif choice == "4":
            print("終了しました。")
            return 0
        else:
            print("1 から 4 の番号で選んでください。")


if __name__ == "__main__":
    raise SystemExit(main())
