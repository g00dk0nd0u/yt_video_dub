import pathlib
import os
import sys
import subprocess

# このスクリプトのディレクトリとファイル名を取得
this_dir = pathlib.Path(__file__).parent.absolute()
file_name = "t02_whisper_transcript_tui_v1.py"  # 実際のスクリプト名に変更
file_path = str(this_dir / file_name)

# 第1候補・第2候補の PyInstaller パスを定義
pyinstaller_primary = str(this_dir / "venv" / "Scripts" / "pyinstaller.exe")
pyinstaller_secondary = r"C:\Users\22615\AppData\Roaming\Python\Python312\Scripts\pyinstaller.exe"

# PyInstallerを実行する関数
def run_pyinstaller(pyinstaller_path):
    subprocess.check_call([
        pyinstaller_path,
        "--onefile",
        "--console",  # 黒いTUI画面を表示（questionary用）
        "--hidden-import=questionary",
        "--hidden-import=moviepy.editor",
        "--hidden-import=faster_whisper",
        file_path
    ])


try:
    # PyInstaller のインストール確認
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])

    # 第1候補を試す
    if os.path.exists(pyinstaller_primary):
        print(f"[INFO] 第1候補を使用: {pyinstaller_primary}")
        run_pyinstaller(pyinstaller_primary)
    
    # 第1候補がなければ第2候補を試す
    elif os.path.exists(pyinstaller_secondary):
        print(f"[INFO] 第1候補が見つからなかったため、第2候補を使用: {pyinstaller_secondary}")
        run_pyinstaller(pyinstaller_secondary)
    
    else:
        raise FileNotFoundError("PyInstaller の実行ファイルがどちらの候補にも見つかりません。")

    print(f"[OK] '{file_name}' を実行可能ファイルにパッケージングしました。")

except subprocess.CalledProcessError as e:
    print(f"[ERROR] PyInstaller の実行に失敗しました。\n詳細: {e}")
except FileNotFoundError as fe:
    print(f"[ERROR] {fe}")
