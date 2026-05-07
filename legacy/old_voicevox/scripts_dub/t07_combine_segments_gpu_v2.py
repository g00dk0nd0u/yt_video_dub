# moviepy==1.0.3 という古いバージョンを使用しています・　pip install moviepy==1.0.3
from moviepy.editor import VideoFileClip, CompositeAudioClip, AudioFileClip, concatenate_videoclips, vfx
from pydub import AudioSegment  # pydubを使用して一時的に無音セグメントを生成
from tempfile import NamedTemporaryFile
import os
import re
import math
import gc
import pathlib
from pathlib import Path

# 音声セグメントを読み込み ###################################################################################
def get_tts_segments(audio_dir):
    tts_audio_segments = []
    files = os.listdir(audio_dir)
    # 'tts_{i}.wav'形式にマッチするファイルの最大インデックスを見つける
    max_index = -1
    pattern = re.compile(r'tts_(\d+)\.wav')

    for file_name in files:
        match = pattern.match(file_name)
        if match:
            index = int(match.group(1))
            max_index = max(max_index, index)

    # ファイルが存在するかどうか確認し、必要に応じて無音セグメントを挿入
    for i in range(max_index + 1):
        audio_path = os.path.join(audio_dir, f'tts_{i}.wav')

        if os.path.exists(audio_path):
            try:
                audio_segment = AudioFileClip(audio_path)
                tts_audio_segments.append(audio_segment)
                print(f"{i}番目の音声を読み込みました")
            except Exception as e:
                print(f"{i}番目の音声ファイルの読み込み中にエラーが発生しました: {e}")
                # エラーが発生した場合は無音セグメントを代わりに追加
                silent_segment = AudioSegment.silent(duration=500)  # 0.2秒の無音を例として追加
                with NamedTemporaryFile(delete=True, suffix='.wav') as tmpfile:
                    silent_segment.export(tmpfile.name, format='wav')
                    silent_audio = AudioFileClip(tmpfile.name)
                    tts_audio_segments.append(silent_audio)
                print(f"{i}番目の音声ファイルが読み込めなかったため、無音セグメントを追加しました")
        else:
            # ファイルが存在しない場合は、無音セグメントを `AudioSegment` で作成し、 `NamedTemporaryFile` に書き込む
            silent_segment = AudioSegment.silent(duration=500)  # 0.2秒の無音を例として追加
            with NamedTemporaryFile(delete=True, suffix='.wav') as tmpfile:
                silent_segment.export(tmpfile.name, format='wav')
                silent_audio = AudioFileClip(tmpfile.name)
                tts_audio_segments.append(silent_audio)
                print(f"{i}番目の音声ファイルが見つからないため、無音セグメントを追加しました")

    gc.collect()  # ガベージコレクタの呼び出し
    print("*" * 50, f"\n{len(tts_audio_segments)} 個のTTS音声を読み込みました。\n")
    return tts_audio_segments


# 減速した動画セグメントと音声セグメントを結合 ###################################################################
def combine_videos_with_audios(split_video_paths, tts_audio_segments):
    """
    TTS音声を動画に合成する。
    指定のインデックスにTTSが無い場合は、そのセグメント全体を無音にする。
    さらに、動画クリップの末尾がTTS音声より短い場合、（最終セグメントのみ）その余り部分を無音で埋める。
    """
    from moviepy.editor import concatenate_audioclips

    combined_video_segments = []

    for i, video_path in enumerate(split_video_paths):
        video_segment = VideoFileClip(video_path)
        video_duration = video_segment.duration

        # 1) TTS音声または無音をベースオーディオとして作成
        if i < len(tts_audio_segments) and tts_audio_segments[i] is not None:
            base_audio_clip = tts_audio_segments[i]
            text = "TTS音声を動画に適用"

        else:
            # 無音セグメントを動画クリップの長さ分作成
            duration_ms = int(video_duration * 1000)
            silent_segment = AudioSegment.silent(duration=duration_ms)
            with NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                silent_segment.export(tmpfile.name, format="wav")
                tmpfile_path = tmpfile.name
            base_audio_clip = AudioFileClip(tmpfile_path)

            # ▼▼▼ 修正ポイント： ここで base_audio_clip のファイルを閉じたり、削除したりしない ▼▼▼
            #  (修正前コードではファイルをクローズ＆os.remove(tmpfile_path)していたが削除)

            text = "該当するTTSなしのため無音を挿入"
            print(f"TTS音声が見つかりませんでした。無音を挿入します。")


        # デバッグ： base_audio_clipの長さ
        audio_duration = base_audio_clip.duration

        # 2) 最終セグメントの場合のみ、base_audio_clip が動画より短い場合、末尾を無音で埋める
        if i == len(split_video_paths) - 1 and audio_duration < video_duration:
            leftover_sec = video_duration - audio_duration
            print(f"最終セグメントで、オーディオ不足: {leftover_sec:.2f}秒の無音を追加します。")
            leftover_segment = AudioSegment.silent(duration=int(leftover_sec * 1000))
            with NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                leftover_segment.export(tmpfile.name, format="wav")
                leftover_path = tmpfile.name
            print(f"残り無音用一時ファイルを作成: {leftover_path}")
            leftover_clip = AudioFileClip(leftover_path)

            # base_audio_clip + leftover_clip を結合
            final_audio_clip = concatenate_audioclips([base_audio_clip, leftover_clip])

            # ▼▼▼ 修正ポイント： leftover_clip.close() 後、ファイルを削除しない ▼▼▼
            # leftover_clip.close()
            # os.remove(leftover_path)
            # (修正前ではclose後にos.remove()していたが削除)

            leftover_text = " (末尾を無音で埋めました)"
        else:
            final_audio_clip = base_audio_clip
            leftover_text = ""
            if i == len(split_video_paths) - 1:
                print("最終セグメント：オーディオは動画の長さと一致しています。")

        combined_video_segment = video_segment.set_audio(final_audio_clip)

        combined_video_segments.append(combined_video_segment)
        del video_segment, combined_video_segment, base_audio_clip
        gc.collect()

        print(f"{i}番目のセグメントで {text}{leftover_text}しました。")

    print("*" * 50, "\n全ての動画とTTS音声を結合しました。\n")
    return combined_video_segments



# 結合した動画セグメントを結合して新しいビデオを作成 #################################################################
def save_combined_videos(combined_video_segments, output_video_path):
    combined_video = concatenate_videoclips(combined_video_segments)
    print("*" * 50, "\n音声付き動画セグメントを、１つのビデオとして結合しました。\n")

    del combined_video_segments
    gc.collect()

    # ★ GPUエンコード(NVENC)を使用するために codec='h264_nvenc' に変更
    combined_video.write_videofile(
        str(output_video_path), codec="h264_nvenc", audio_codec="aac", threads=7
    )
    print("*" * 50, "\n結合済みビデオを保存しました。\n")

    return combined_video


# 最終的なトランスクリプトを保存 #################################################################################
def save_final_trascript(video_segments, formatted_translated_texts_file, final_time_transcript_file):

    with open(formatted_translated_texts_file, 'r', encoding='utf-8') as file:

        formatted_lines = file.readlines()
        formatted_text_contents = [line.split("]")[-1] for line in formatted_lines]

    with open(final_time_transcript_file, 'w', encoding='utf-8') as file:

        start_time = 0
        end_time = 0
        for i, (line, video_segment) in enumerate(zip(formatted_text_contents, video_segments)):

            if end_time != 0: # 最初のトランスクリプトの処理以外
                start_time = end_time

            duration = video_segment.duration
            end_time = start_time + duration

            if i < len(formatted_text_contents): # 最後のトランスクリプトの終了までの処理
                file.write(f"[{start_time:.2f}s -> {end_time:.2f}s] {line}")
            else: # 最後のトランスクリプトの終了後に映像セグメントがある場合
                file.write(f"[{start_time:.2f}s -> {end_time:.2f}s] ")

    print(f"最終トランスクリプトを保存しました: {final_time_transcript_file}")


# テキストファイルからパスを取得 #################################################################################
def get_paths_from_text(text_file):
    paths = []
    with open(text_file, 'r') as f:
        for line in f:
            paths.append(line.strip())
    return paths

# video IDを取得する関数
def get_videoid_text(videoid_file_path):
    try:
        with open(videoid_file_path, 'r', encoding='utf-8') as file:
            video_id = file.read().strip()
        return video_id
    except Exception as e:
        print(f"動画IDの読み込み中にエラーが発生しました: {e}")
        return "unknown"

#############################################################################################################
# main関数　##################################################################################################
def main():
    this_dir = pathlib.Path(__file__).resolve().parent
    data_path = this_dir / "data"

    # 動画IDの取得
    videoid_texts_dir_path = data_path / "texts" / "videoid.txt"
    video_id = get_videoid_text(videoid_texts_dir_path)
    print(f"処理対象の動画ID: {video_id}")

    # 動画パス
    split_video_paths_file = data_path / "texts" / "split_video_paths.txt"
    
    # 保存先とファイル名を指定（OneDriveフォルダ）
    final_output_folder = Path(r"C:\Users\22615\OneDrive - Gensler\_iMac_Onedrive\python")
    final_output_folder.mkdir(parents=True, exist_ok=True)  # フォルダが存在しない場合は作成
    merged_video_file = final_output_folder / f"final_video_{video_id}.mp4"
    print(f"保存先: {merged_video_file}")

    # 音声パス
    tts_audio_dir = data_path / "audio_tts_wav"

    # テキストパス
    formatted_translated_texts_file = data_path / "texts" / "formatted_translated_texts.txt" # 翻訳済みのトランスクリプト
    final_time_transcript_file = data_path / "texts" / "final_time_transcript.txt" # 最終的なタイムスタンプ

    # ここから処理開始 #########################################################################################

    # txtファイルからpaths の読み込み
    split_video_paths = get_paths_from_text(split_video_paths_file) # 動画のパス
    print(f"\nsplit_videoを読み込みました\n")

    # 音声セグメントをジェネレータで処理（メモリ効率化）
    tts_audio_segments = get_tts_segments(tts_audio_dir)

    # 動画と音声の結合（結合後は逐次処理で一時ファイルに保存）
    video_segments = combine_videos_with_audios(split_video_paths, tts_audio_segments)

    del tts_audio_segments  # メモリを解放
    gc.collect()  # ガベージコレクタの呼び出し

    # 動画セグメントを1つの動画に結合・保存
    save_combined_videos(video_segments, merged_video_file)

    save_final_trascript(video_segments, formatted_translated_texts_file, final_time_transcript_file)

    del video_segments  # メモリを解放
    gc.collect()  # ガベージコレクタの呼び出し
    
    # 処理完了後、保存先フォルダをエクスプローラーで開く
    print(f"動画の処理が完了しました。保存先フォルダを開きます。")
    os.startfile(str(final_output_folder))

if __name__ == "__main__":
    main()
