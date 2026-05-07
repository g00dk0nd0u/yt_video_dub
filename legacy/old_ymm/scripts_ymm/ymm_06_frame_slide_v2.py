# スライドショー動画作成スクリプト
# pip install opencv-python

import cv2
import numpy as np
from pathlib import Path
import csv # CSVファイルの読み込み用


# クリーンアップ用の関数 ##############################################################
def clear_directory(directory_path, extensions=None):
    """
    指定ディレクトリ内のファイルを削除
    extensions: ['.jpg', '.txt'] のように拡張子を指定すると絞り込み可能
    """
    path = Path(directory_path)
    if not path.exists():
        return
    for file in path.iterdir():
        if file.is_file():
            if extensions is None or file.suffix.lower() in extensions:
                try:
                    file.unlink()
                except Exception as e:
                    print(f"削除エラー: {file.name} ({e})")


# スライドを作成する関数 ##############################################################
def create_fadein_slideshow(image_dir, output_video_path, total_duration_sec, fps, fade_duration):
    image_dir = Path(image_dir)
    images = sorted(image_dir.glob("frame_*.jpg"))

    if not images:
        print("画像が見つかりません。")
        return

    # 各画像の表示時間（秒）
    num_images = len(images)
    duration_per_image = total_duration_sec / num_images

    # 各パートのフレーム数
    fade_frames = int(fps * fade_duration)
    hold_frames = int(fps * (duration_per_image - fade_duration))
    if hold_frames < 0:
        print("fade_duration が長すぎます。duration_per_image より短くしてください。")
        return

    # 最初の画像サイズ取得
    sample_img = cv2.imread(str(images[0]))
    height, width, _ = sample_img.shape

    # 動画ライター初期化
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video_writer = cv2.VideoWriter(str(output_video_path), fourcc, fps, (width, height))

    prev_img = None

    for idx, img_path in enumerate(images):
        img = cv2.imread(str(img_path)).astype(np.float32) / 255.0
        img = np.clip(img, 0, 1)

        if prev_img is None:
            # 最初の画像 → 通常表示
            frame = (img * 255).astype(np.uint8)
            for _ in range(fade_frames + hold_frames):
                video_writer.write(frame)
            print(f"追加: {img_path.name} -> {fade_frames + hold_frames}フレーム (初期画像)")
        else:
            # フェードイン（クロスフェード）
            for f in range(fade_frames):
                alpha = f / fade_frames
                blended = cv2.addWeighted(prev_img, 1 - alpha, img, alpha, 0)
                blended_frame = (blended * 255).astype(np.uint8)
                video_writer.write(blended_frame)

            # 一定時間表示（ホールド）
            frame = (img * 255).astype(np.uint8)
            for _ in range(hold_frames):
                video_writer.write(frame)

            print(f"追加: {img_path.name} -> {fade_frames + hold_frames}フレーム")

        prev_img = img

    video_writer.release()
    print(f"\n動画を作成しました: {output_video_path}")


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


# メイン処理 ##########################################################################
def main():

    csv_dir = Path(__file__).resolve().parent / "data" / "texts_ymm" / "ymm_total_duration.csv"

    # 入力画像ディレクトリと出力動画ディレクトリの設定
    input_images_dir = Path(__file__).resolve().parent / "data" / "image_filtered_frames"

    output_video_dir = Path(__file__).resolve().parent / "data" / "video_slides"
    output_video_dir.mkdir(parents=True, exist_ok=True)
    clear_directory(output_video_dir, extensions=[".mp4"])

    # 出力動画ファイル名
    output_video_file = output_video_dir / "slideshow.mp4"

    # 時間の指定

    fps = 30  # フレームレート
    fade_duration = 0.1  # 各画像のフェードイン時間（秒）

    total_duration_sec = get_duration_from_csv_files(csv_dir)

    create_fadein_slideshow(
        image_dir=input_images_dir,
        output_video_path=output_video_file,
        total_duration_sec=total_duration_sec,
        fps=fps,
        fade_duration=fade_duration
    )

    print(f"\n動画ファイルを保存しました: {output_video_file}")

if __name__ == "__main__":
    main()
