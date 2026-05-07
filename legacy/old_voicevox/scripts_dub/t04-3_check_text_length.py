# pip install colorama
from colorama import Fore, Style, init
import re
import pathlib
import sys

# coloramaの初期化
init(autoreset=True)

# ファイルのパスを設定
this_dir = pathlib.Path(__file__).resolve().parent
file_path = str(this_dir / "data" / "texts" / "formatted_translated_texts.txt")

# ファイルの読み込み
with open(file_path, 'r', encoding='utf-8') as file:
    lines = file.readlines()

# 時間を解析して文字数密度を計算し、色付けする関数
def colorize_text(line):
    # 時間の範囲とテキスト部分を分割
    match = re.match(r'\[(\d+\.\d+)s -> (\d+\.\d+)s\] (.*)', line)
    if not match:
        return line  # 該当しない行はそのまま返す
    
    start_time = float(match.group(1))
    end_time = float(match.group(2))
    text = match.group(3)

    # 再生時間と文字数密度の計算
    duration = end_time - start_time
    char_per_sec = len(text) / duration if duration > 0 else 0

    # 色付けの条件分岐
    if char_per_sec >= 10:
        return Fore.RED + line + Style.RESET_ALL
    elif char_per_sec >= 7:
        return Fore.YELLOW + line + Style.RESET_ALL
    elif char_per_sec >= 5:
        return Fore.GREEN + line + Style.RESET_ALL
    else:
        return line

# 各行を処理して色付けし、空行を出力しないように変更
for line in lines:
    sys.stdout.write(colorize_text(line))
