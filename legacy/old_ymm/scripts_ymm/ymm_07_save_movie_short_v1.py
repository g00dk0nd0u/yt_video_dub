# pip install moviepy==1.0.3
from moviepy.editor import (
    VideoFileClip, 
    vfx, 
    CompositeAudioClip, 
    AudioFileClip, 
    concatenate_videoclips, 
    ImageClip, 
    CompositeVideoClip,
    concatenate_audioclips  # 追加: BGMループ用
)
# from moviepy.audio.AudioClip import concatenate_audioclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os
import gc
import time  # 追加: ファイルハンドル解放待機用
from pathlib import Path
import csv
import textwrap
import concurrent.futures
# from functools import partial
import tempfile  # 追加: 一時ディレクトリ管理用
import random  # 追加: BGMのランダム選択用


# キャッシュ用ディクショナリ
_caption_cache = {}

# テキスト折り返し関数（外部に移動）#########################################
def wrap_text_by_width(text, font, max_width, draw):
    lines = []
    words = text.split()
    current_line = ""
    
    # 日本語の場合は文字単位で処理
    if any(ord(c) > 127 for c in text):
        words = list(text)
        
    for word in words:
        test_line = current_line + word
        # 空白を追加（英語の場合）
        if current_line and not any(ord(c) > 127 for c in current_line):
            test_line = current_line + " " + word
        
        # テキストボックスの幅を取得
        bbox = draw.textbbox((0, 0), test_line, font=font)
        line_width = bbox[2] - bbox[0]
        
        if line_width <= max_width:
            current_line = test_line
        else:
            # 句読点チェック - 行頭に句読点が来ないようにする
            # current_lineチェックを外して、句読点は常に前の行に吸収する
            if word in "。、,.!?！？":
                # 単体の句読点は必ず前の行に含める（空行チェックだけ残す）
                if current_line:
                    current_line += word
                    continue
            
            # 現在の行が空でない場合は追加
            if current_line:
                lines.append(current_line)
            current_line = word
            
    # 最後の行を追加
    if current_line:
        lines.append(current_line)
        
    return lines


# キャプション画像を作成する関数 #######################################################
def create_caption_image(
    text, 
    speaker, 
    font_path, 
    font_size, 
    width, 
    height=400,  # 高さを固定
    text_y_offset=0
):
    cache_key = (text, speaker, font_size, width, height, text_y_offset)
    if (cache_key in _caption_cache):
        return _caption_cache[cache_key]

    font = ImageFont.truetype(font_path, font_size)
    max_text_width = int(width * 0.85)

    # ダミー画像で描画準備
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (width, height)))
    lines = wrap_text_by_width(text, font, max_text_width, dummy_draw)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 行間スペース
    line_spacing = int(font_size * 0.2)

    # 総高さ計算（textbboxベースで）
    total_text_height = 0
    line_sizes = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_sizes.append((line, w, h))
        total_text_height += h + line_spacing
    total_text_height -= line_spacing  # 最後の行間分を引く

    # 中央寄せ開始位置
    y = int((height - total_text_height) / 2) + text_y_offset

    # カラー設定
    stroke_color = {
        "ずんだもん": "#009944",  # ← 元の #00cc66 より濃い緑
        "四国めたん": "#cc0099"  # ← 元の #ff00cc より濃いピンク
    }.get(speaker, "black")
    text_color = "white"

    # 描画
    for line, w, h in line_sizes:
        x = (width - w) // 2

        for dx in range(-6, 6):  # -3〜+3 にすると、縁がもっと太くなる
            for dy in range(-6, 6):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=font, fill=stroke_color)


        draw.text((x, y), line, font=font, fill=text_color)
        y += h + line_spacing

    result = np.array(img)
    _caption_cache[cache_key] = result
    return result


# 単一の動画を処理する関数（並列処理用）###################################################
def process_single_video(wav_path, lines, video_base_dir, font_path, font_size, margin_sec, caption_top_offset, i, temp_dir):
    name = wav_path.stem  # 例: 001_shikokumetan
    try:
        num_str, prefix = name.split("_", 1)
    except ValueError:
        print(f"無効なファイル名形式: {name}")
        return None

    # ベース動画取得
    video_base_path = video_base_dir / f"video_base_{prefix}_short_v1.mp4"
    if not video_base_path.exists():
        print(f"ベース動画が見つかりません: {video_base_path}")
        return None

    # 音声読み込み
    audio_clip = AudioFileClip(str(wav_path))
    total_duration = audio_clip.duration + margin_sec

    # 動画切り出し & 音声追加
    video_clip = VideoFileClip(str(video_base_path)).subclip(0, total_duration).without_audio()
    video_with_audio = video_clip.set_audio(audio_clip)
    
    # 動画の実際のフレームレートを取得
    fps = video_clip.fps if video_clip.fps else 30

    # キャプションテキスト
    if i < len(lines):
        speaker, caption = lines[i]
    else:
        speaker, caption = "", ""

    # Pillowで画像を生成してImageClipに変換
    caption_img = create_caption_image(
        text=caption,
        speaker=speaker,
        font_path=font_path,
        font_size=80,
        width=1080,
        height=400,             # ← ここで固定高さ
        text_y_offset=0         # ← 必要なら微調整可能
    )
    
    # 字幕位置を上部に配置（画面中央から720px上）
    txt_clip = ImageClip(caption_img).set_duration(video_clip.duration).set_position(
        ("center", video_clip.size[1] // 2 + caption_top_offset)
    )

    # シンプルにキャプションだけを追加
    final_video = CompositeVideoClip([video_with_audio, txt_clip])
    
    # 一時ファイルに保存（オブジェクト自体は返さない）
    temp_output_path = temp_dir / f"temp_{name}.mp4"
    # 一時音声ファイルも一時ディレクトリ内に配置
    temp_audiofile_path = temp_dir / f"temp-{name}-audio.m4a"
    
    final_video.write_videofile(
        str(temp_output_path),
        codec='libx264',
        audio_codec='aac',
        temp_audiofile=str(temp_audiofile_path),  # 一時音声ファイルのパスを指定
        remove_temp=True,
        fps=fps,
        threads=4,  # 2から4に変更：安定性と並列処理のバランスを最適化
        logger=None
    )
    
    # メモリ解放
    video_clip.close()
    audio_clip.close()
    final_video.close()
    gc.collect()
    
    print(f"クリップ {name} 処理完了")
    #ここでの処理とは、映画の音声データと字幕データを取得し、指定されたフォーマットで保存する処理を行っています。
    
    # ファイルパスのみを親プロセスに返す（整数番号とパスのタプル）
    return (int(num_str) if num_str.isdigit() else 9999, str(temp_output_path))


# グローバルスコープにヘルパー関数を定義 ###########################################
def run_task(args):
    # シンプルに引数を展開するだけ
    return process_single_video(*args)


# TTSの音声ファイルを動画に重ねる（並列処理対応版）##################################
def combine_audio_with_video(
    wav_dir: Path,
    video_base_dir: Path,
    transcript_csv_path: Path,
    font_path: str,
    final_output_path: Path,
    font_size: int = 30,
    margin_sec: float = 0,
    caption_top_offset: int = 20,
    slide_scale: float = 0.7,
    slide_top_ratio: float = 0.15,
    slide_offset: int = 0  # ← 新規追加
    ):
    
    wav_files = sorted(wav_dir.glob("*.wav"))

    # tempfileを使用して自動クリーンアップされる一時ディレクトリを作成
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        
        # セリフの読み込み
        lines = []
        with open(transcript_csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    lines.append((row[0].strip(), row[1].strip()))

        # 並列処理を実行
        with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            # 一時ディレクトリ情報を追加
            tasks = [
                (wav_path, lines, video_base_dir, font_path, font_size, margin_sec, caption_top_offset, i, temp_dir)
                for i, wav_path in enumerate(wav_files)
            ]
            
            # 並列処理の実行
            print(f"並列処理で{len(tasks)}個の動画を生成しています...")
            results = list(executor.map(run_task, tasks))
        
        # ファイルパスのリストを取得
        valid_results = [result for result in results if result is not None]
        # 番号順にソート
        valid_results.sort(key=lambda x: x[0])  # 番号順にソート
        
        if not valid_results:
            print("結合する動画が見つかりません。")
            return

        print(f"全{len(valid_results)}個のクリップを読み込んで結合しています...")
        
        # ファイルパスからVideoClipを生成
        video_clips = []
        for _, temp_path_str in valid_results:
            clip = VideoFileClip(temp_path_str)
            video_clips.append(clip)
        
        # 全てのVideoClipをメモリ上で結合
        final_clip = concatenate_videoclips(video_clips, method="compose")
        
        # ★ BGM追加処理（音量7%、ループ）
        bgm_dir = Path(__file__).parent / "data" / "audio_music"
        bgm_files = list(bgm_dir.glob("*.mp3"))
        if (bgm_files):
            bgm_path = random.choice(bgm_files)
            print(f"🎵 BGMを選択: {bgm_path.name}")
            bgm_clip = AudioFileClip(str(bgm_path)).volumex(0.1)  # 音量設定
            
            # BGMをループ処理（動画長さに合わせる）
            loop_count = max(1, int(final_clip.duration / bgm_clip.duration) + 1)  # 最低1回は確保
            looped_bgm = concatenate_audioclips([bgm_clip] * loop_count).subclip(0, final_clip.duration)
            # BGMにフェードイン/アウトを適用（例：各1秒）
            looped_bgm = looped_bgm.audio_fadein(1).audio_fadeout(1)
            
            # 映像と音声の合成（例外処理を追加）
            if final_clip.audio:  # 音声があることを確認
                final_audio = CompositeAudioClip([final_clip.audio, looped_bgm])
            else:
                final_audio = looped_bgm  # TTSがない場合はBGMだけ使用
            final_clip = final_clip.set_audio(final_audio)
            print("✅ BGMを追加しました。")
        else:
            print("⚠️ BGMファイルが見つかりません。")
        
        # 最初のクリップのfpsを基準に
        base_fps = video_clips[0].fps if video_clips and video_clips[0].fps else 30
        
        # スライドショー動画を最終出力に重ねる
        slide_video_path = Path(__file__).parent.resolve() / "data" / "video_slides" / "slideshow.mp4"
        if slide_video_path.exists():
            slide_clip = VideoFileClip(str(slide_video_path))

            # スライドをリサイズ（全幅に調整）
            slide_clip = slide_clip.resize(width=final_clip.w)

            # 位置設定（完全中央配置に修正）
            slide_clip = slide_clip.set_position(
                ("center", final_clip.h // 2 + slide_offset)
            )

            # 長さを動画と一致
            slide_clip = slide_clip.set_duration(final_clip.duration)
            
            final_clip = CompositeVideoClip([final_clip, slide_clip])

            print("✅ スライドショー動画を最終動画に合成しました。")
        else:
            print(f"⚠️ スライドショー動画が見つかりません: {slide_video_path}")
        
        # 最終的な動画を一回のみ書き出し
        print("動画ファイルを書き出しています...")
        final_output_path.parent.mkdir(parents=True, exist_ok=True)  # existok → exist_ok に修正

        # 最終動画用の一時音声ファイルも一時ディレクトリ内に配置
        temp_final_audiofile = temp_dir / "temp-final-audio.m4a"

        # RTX 4080 GPU活用のハードウェアエンコーディング
        print("GPUエンコード開始（h264_nvenc）...")
        final_clip.write_videofile(
            str(final_output_path),
            codec="h264_nvenc",          # NVIDIA GPUエンコーダー
            audio_codec="aac",
            temp_audiofile=str(temp_final_audiofile),  
            remove_temp=True,
            fps=base_fps,
            threads=12,                  # GPU処理に最適化
            logger="bar",                # 進捗表示を有効化
            verbose=True,                # 詳細ログ出力を有効化
            ffmpeg_params=[
                "-rc", "vbr",            # 可変ビットレート
                "-cq", "19",             # 品質係数（18-23が推奨範囲）
                "-b:v", "5000k",         # 目標ビットレート
                "-maxrate", "10000k",    # 最大ビットレート
                "-bufsize", "20000k"     # バッファサイズ
            ]
        )

        print(f"\n🚀 GPU高速エンコード完了 → {final_output_path.name}")

        # メモリ解放時の処理改善
        for clip in video_clips:
            clip.close()
        final_clip.close()
        time.sleep(1)  # Windowsでのファイルハンドル解放のための待機
        
        gc.collect()
    # withブロックを抜けると一時ディレクトリが自動的に削除される


# 作業用ファイルを消去 #########################################################################
def remove_all_files_in_directory(directory_path):
    if os.path.exists(directory_path) and os.path.isdir(directory_path):
        for file_name in os.listdir(directory_path):
            file_path = os.path.join(directory_path, file_name)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"'{file_path}' を削除できませんでした: {e}")
    else:
        print(f"{directory_path}\nが存在しないか、ディレクトリではありません。")
    print("*" * 50, f"\n{directory_path}\nのファイルを消去しました。\n")


# 動画IDを取得する関数 ########################################################################
def get_videoid_text(videoid_file_dir: str) -> str:
    with open(videoid_file_dir, "r", encoding="utf-8") as f:
        return f.readline().strip()


# main関数　###################################################################################
def main():
    # dataフォルダの相対パス
    dir_path = Path(__file__).parent.resolve() / "data"

    # 動画IDを取得
    videoid_texts_dir_path = dir_path / "texts" / "videoid.txt" 
    video_id = get_videoid_text(videoid_texts_dir_path)

    # 最終出力先
    final_output_folder = Path(r"C:\Users\22615\OneDrive - Gensler\_iMac_Onedrive\python")
    final_output_path = final_output_folder / f"final_video_{video_id}.mp4"
    final_output_path.parent.mkdir(parents=True, exist_ok=True)

    # ★ 位置調整用パラメータをここに
    subtitle_offset_from_center = -50    # 字幕を中央より下に
    slide_offset_from_center = -650     # スライドを中央より上に

    print("📽️ 動画処理を開始します...")

    combine_audio_with_video(
        wav_dir = dir_path / "audio_ymm_wav",
        video_base_dir = dir_path / "video_ymm_base",
        transcript_csv_path = dir_path / "texts_ymm" / "ymm_transcript.csv",
        font_path = str(dir_path / "font" / "keifont.ttf"),
        final_output_path = final_output_path,
        font_size = 80,
        caption_top_offset = subtitle_offset_from_center,
        slide_scale = 1.0,
        slide_top_ratio = 0.5,
        slide_offset = slide_offset_from_center  # ← 追加！
    )
    
    # キャッシュをクリア
    _caption_cache.clear()
    gc.collect()

    # ポップアップで開く
    os.startfile(str(final_output_folder))

    print("✅ すべての処理が完了しました。")


# 実行 ###########################################################################################
# スクリプトが直接実行された場合にのみ main() を呼び出す
if __name__ == "__main__":
    main()
