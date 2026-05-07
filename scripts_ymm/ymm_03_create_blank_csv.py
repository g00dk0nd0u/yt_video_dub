

from pathlib import Path
this_dir = Path(__file__).resolve().parent  # 現在のスクリプトのディレクトリを取得
output_path = this_dir / "data" / "texts_ymm"  # ディレクトリを指定
output_path.mkdir(parents=True, exist_ok=True)  # ディレクトリが存在しない場合、作成

file_path = output_path / "ymm_transcript.csv"  # ファイルパスを指定
file_path.touch(exist_ok=True)  # ファイルが存在しない場合、空のファイルを作成

# 追記する内容を指定
content = "This is a new line.\n"  # 追記する内容

# ファイルに追記
with file_path.open("a", encoding="utf-8") as f:
	f.write(content)

