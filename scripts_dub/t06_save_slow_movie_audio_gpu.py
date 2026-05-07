# pip install moviepy==1.0.3
from moviepy.editor import VideoFileClip, vfx, CompositeAudioClip, AudioFileClip, concatenate_videoclips
from pydub import AudioSegment  # pydubを使用して無音セグメントを生成
from tempfile import NamedTemporaryFile
import os
import re
import math
import gc
import pathlib

# テキストファイルから減速率を取得 ############################################################################
def get_slow_rates(slow_rates_text_path):
    slow_rates = []
    with open(slow_rates_text_path, 'r', encoding='utf-8') as file:
        for line in file:  # 1行ずつ読み込む
            slow_rates.append(float(line.strip()))  # 末尾の改行コードを削除してリストに追加
    print("*" * 50, "\n減速率を取得しました。\n")
    return slow_rates


# トランスクリプトに従って動画を分割・減速・保存 ##################################################################
def split_slow_video_segments(video_path, original_transcript_path, split_video_dir, slow_rates):
    
    video = VideoFileClip(str(video_path))
    total_video_duration = video.duration

    with open(original_transcript_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    last_end_time = 0
    split_video_paths = []  # 分割された動画のパスを格納するリスト

    for i, (line, slow_rate) in enumerate(zip(lines, slow_rates)):
        parts = line.split("]")
        times = parts[0].replace("[", "").split(" -> ")
        start_time = float(times[0].strip('s'))
        end_time = float(times[1].strip('s'))
        last_end_time = end_time

        if start_time < total_video_duration:
            output_video_path = split_video_dir / f'segment_{i:02d}.mp4'
            video_segment = video.subclip(start_time, min(end_time, total_video_duration))

            if slow_rate != 1:
                video_segment = video_segment.fx(vfx.speedx, slow_rate)
                print(f"{i}番目の動画を{slow_rate}の速度で処理して保存しました。")
            else:
                print(f"{i}番目の動画は1倍速のため、速度変化なしで保存しました。")

            # ★ 修正：GPUエンコーダ NVENC を使用して動画を書き出し（codecを h264_nvenc に変更）
            video_segment.write_videofile(
                str(output_video_path),
                codec='h264_nvenc',
                logger=None,
                threads=7
            )
            split_video_paths.append(output_video_path)
            del video_segment  # メモリを解放
        else:
            print(f"Warning: Start time {start_time} exceeds video duration {total_video_duration}. Skipping segment.")

    # 最後のトランスクリプトの終了後の映像があれば分割
    if last_end_time < total_video_duration:
        output_video_path = split_video_dir / f'segment_{len(lines):02d}.mp4'
        video_segment = video.subclip(start_time, min(end_time, total_video_duration))
        video_segment.write_videofile(
            str(output_video_path),
            codec='h264_nvenc',
            logger=None,
            threads=7
        )
        split_video_paths.append(output_video_path)
        del video_segment
        print(f"最後のトランスクリプト後の追加動画を分割保存しました")
        
    del video
    gc.collect()
    print("*" * 50, "\n全ての動画を分割しました。\n")
    return split_video_paths


# トランスクリプトに従って背景音楽を分割・減速・保存 ##################################################################
def split_slow_music_segments(original_transcript_path, split_audio_dir, no_vocal_wav_dir, slow_rates):
    audio = AudioSegment.from_file(no_vocal_wav_dir)

    last_end_time = 0
    split_audio_paths = []

    with open(original_transcript_path, 'r', encoding='utf-8') as file:
        for i, line in enumerate(file):
            parts = line.split("]")
            times = parts[0].replace("[", "").split(" -> ")
            start_time = float(times[0].strip('s')) * 1000  # ミリ秒単位に変換
            end_time = float(times[1].strip('s')) * 1000
            last_end_time = end_time

            segment = audio[start_time:end_time]

            if i < len(slow_rates):
                slow_rate = slow_rates[i]
            else:
                slow_rate = 1
                print(f"{i}番目の減速率がないため、速度は無しとしました。")

            slow_music_segment = segment._spawn(segment.raw_data, overrides={
                "frame_rate": int(segment.frame_rate * slow_rate)
            })
            output_audio_path = split_audio_dir / f'segment_{i:02d}.wav'
            slow_music_segment.export(str(output_audio_path), format='wav')
            split_audio_paths.append(output_audio_path)

            del segment
            del slow_music_segment
            print(f"{i}番目の音声を{slow_rate}倍の速度で分割保存しました")
        
        total_duration = len(audio)
        if last_end_time < total_duration:
            segment = audio[last_end_time:total_duration]
            if len(slow_rates) > len(split_audio_paths):
                slow_rate = slow_rates[len(split_audio_paths)]
            else:
                slow_rate = 1
                print(f"最後の減速率がないため、速度は無しとしました。")

            slow_music_segment = segment._spawn(segment.raw_data, overrides={
                "frame_rate": int(segment.frame_rate * slow_rate)
            })
            output_audio_path = str(split_audio_dir / f'segment_{len(split_audio_paths):02d}.wav')
            slow_music_segment.export(str(output_audio_path), format='wav')
            del segment
            del slow_music_segment
            print(f"最後のトランスクリプト後の追加音声を{slow_rate}倍の速度で分割保存しました")

        gc.collect()
        print("*" * 50, "\n全ての背景音楽を分割・減速しました。\n")
        return split_audio_paths


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


# 保存したセグメントのパスリストをテキストファイルに保存 ############################################################
def save_pathes_to_text(txt_file_path, segment_paths_list):
    with open(txt_file_path, "w") as f:
        for path in segment_paths_list:
            f.write(str(path) + "\n")
    print("\n", "*" * 50, f"\nパスのリストを保存しました:\n{txt_file_path}\n")


#############################################################################################################
# main関数　##################################################################################################
def main():
    # dataフォルダの相対パス
    dir_path = pathlib.Path(__file__).parent.resolve() / "data"

    # 動画
    downloaded_video_dir = dir_path / "video_download"
    downloaded_video_file = list(downloaded_video_dir.glob("*.mp4"))[0]
    print(downloaded_video_file)
    if not downloaded_video_file.exists():
        print(f"{downloaded_video_file} が見つかりませんでした。")

    split_video_dir = dir_path / "video_split"  # 分割された動画の保存先
    split_video_paths_text_file = dir_path / "texts/split_video_paths.txt"  # 分割された動画のパス

    # テキスト
    formatted_translated_texts_file = dir_path / "texts/formatted_translated_texts.txt"  # 翻訳済みのトランスクリプト
    slow_rates_text_path = dir_path / "texts/slow_rates.txt"  # 減速率のテキストファイル

    # 処理前のクリーンナップ
    remove_all_files_in_directory(split_video_dir)

    # 減速率リストの取得
    slow_rates = get_slow_rates(slow_rates_text_path)

    # 動画をトランスクリプトに従って分割・減速処理・保存
    split_video_paths = split_slow_video_segments(downloaded_video_file, formatted_translated_texts_file, split_video_dir, slow_rates)
    save_pathes_to_text(split_video_paths_text_file, split_video_paths)


if __name__ == "__main__":
    main()
