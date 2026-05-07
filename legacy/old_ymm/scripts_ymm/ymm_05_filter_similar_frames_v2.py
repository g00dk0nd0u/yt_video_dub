# 類似フレームの削除用スクリプト
# pip install opencv-python scikit-image
# pip install scikit-image

import cv2
import shutil
from pathlib import Path
from skimage.metrics import structural_similarity as ssim
import numpy as np
import shutil
import os
import csv


# クリーンアップ用の関数 ##############################################################
def clear_directory(directory_path, extensions=None):
    """
    指定ディレクトリ内のファイルを削除
    extensions: ['.jpg', '.txt'] のように拡張子を指定すると絞り込み可能
    """
    path = Path(directory_path)
    if not path.exists():
        print(f"警告: ディレクトリが存在しません: {directory_path}")
        return
    
    deleted_count = 0
    for file in path.iterdir():
        if file.is_file():
            # 拡張子を小文字に変換して比較
            if extensions is None or file.suffix.lower() in [ext.lower() for ext in extensions]:
                try:
                    file.unlink()
                    deleted_count += 1
                    # print(f"削除: {file.name}")  # 詳細なログが必要な場合はコメントを外す
                except Exception as e:
                    print(f"削除エラー: {file.name} ({e})")
    
    print(f"{path.name}ディレクトリから{deleted_count}個のファイルを削除しました")


# フレームの類似度を計算 ##############################################################
def calculate_similarity(img1_path, img2_path):
    img1 = cv2.imread(str(img1_path))
    img2 = cv2.imread(str(img2_path))

    if img1 is None or img2 is None:
        return 0.0

    # サイズを一致させる（念のため）
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    score, _ = ssim(gray1, gray2, full=True)
    return score


# フレームの類似度を比較して保存 ########################################################
def filter_similar_frames(frames_dir, threshold):
    frames_dir = Path(frames_dir)
    
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))

    if not frame_files:
        print("フレームが見つかりません。")
        return []

    kept = [frame_files[0]]  # 最初の1枚は必ず保存
    print(f"保持: {frame_files[0].name}")

    for i in range(1, len(frame_files)):
        score = calculate_similarity(kept[-1], frame_files[i])
        if score < threshold:
            kept.append(frame_files[i])
            print(f"保持: {frame_files[i].name} (類似度: {score:.2f})")
        else:
            print(f"スキップ: {frame_files[i].name} (類似度: {score:.2f})")

    print(f"\n保持するフレーム枚数: {len(kept)} / {len(frame_files)}")
    return kept

# フレームを実際に保存する関数
def save_frames(frames, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for frame in frames:
        shutil.copy2(frame, output_dir / frame.name)
        print(f"保存: {frame.name}")
    
    print(f"合計 {len(frames)}枚のフレームを保存しました")


# csvファイルから総再生時間を取得する関数 ###############################################
def get_duration_from_csv_files(csv_dir):
    """csvファイルには単一の秒数が書かれています。例：131.871"""

    if not csv_dir.exists():
        print(f"CSVファイルが見つかりません: {csv_dir}")

    with open(csv_dir, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            try:
                total_duration_sec = float(row[0])
                if total_duration_sec <= 0:
                    print("CSVファイルの内容が不正です。")
                    return 0.0
                print(f"CSVファイルから取得した総再生時間: {total_duration_sec}秒")
                return total_duration_sec
            except ValueError:
                print("CSVファイルの内容が不正です。")
                return 0.0
    return 0.0


# メイン処理 ########################################################################
def main():
    original_frames_dir = Path(__file__).resolve().parent / "data" / "image_frames"
    filtered_output_dir = Path(__file__).resolve().parent / "data" / "image_filtered_frames"

    csv_dir = Path(__file__).resolve().parent / "data" / "texts_ymm" / "ymm_total_duration.csv"

    # ポップアップで開く
    os.startfile(filtered_output_dir)

    total_duration_sec = get_duration_from_csv_files(csv_dir)
    
    # 再生時間の妥当性チェックを追加
    if total_duration_sec <= 0:
        print("再生時間が無効なため、処理を終了します。")
        return

    # フレームの類似度を比較　◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆
    threshold = 0.5  # 類似度の閾値
    kept_frames = []
    # ◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆
    
    while True:
        kept_frames = filter_similar_frames(original_frames_dir, threshold)
        frame_num = len(kept_frames)
        frame_duration_sec = total_duration_sec / frame_num
        print(f"フレーム数: {frame_num} / フレームの再生時間: {frame_duration_sec:.2f}秒")

        if frame_duration_sec > 3.0:
            break
        else:   
            print("*"*50)
            print(f"フレーム数が多いため、閾値を下げて再実行します。")
            threshold = max(0.1, threshold - 0.1)  # 閾値の下限を設定 (0.1以下にはならない)
            if threshold <= 0.1:
                print("これ以上閾値を下げられません。現在のフレームで処理を続けます。")
                break
            continue
    
    # 最終的なフレームセットを保存
    clear_directory(filtered_output_dir, extensions=[".jpg"])
    print(f"\n最終的な閾値 {threshold} でフレームを保存します。")
    save_frames(kept_frames, filtered_output_dir)

    print("*"*50,f"\nこのコードの処理が全て完了しました。\n")


if __name__ == "__main__":
    main()

