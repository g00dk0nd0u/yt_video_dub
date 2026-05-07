import os
import gc  # メモリキャッシュ削除に使用
import pathlib

# 作業用ファイルを消去 #########################################################################
def remove_all_files_in_directories(directory_paths):
    for directory_path in directory_paths:
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            # ディレクトリ内のすべてのファイルを取得し、削除
            for file_name in os.listdir(directory_path):
                file_path = os.path.join(directory_path, file_name)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"ファイル '{file_path}' の削除に失敗しました: {e}")
        else:
            print(f"'{directory_path}' は存在しないか、ディレクトリではありません。")
    
    # ディレクトリ名のみを取得（環境に依存しない安全な方法）
    data_dir_list = [os.path.basename(str(path)) for path in directory_paths]
    
    # 箇条書きのテキストに変換
    text = "\n".join(data_dir_list)
    print(f"\n\n以下のディレクトリ内のファイルを削除しました:\n{text}")


#############################################################################################################
# main関数　##################################################################################################
def main():

    # フォルダパス
    dir_path = pathlib.Path.cwd() / "data"

    # 動画
    video_downloaded_dir = dir_path / "video_download"  # ダウンロードした動画
    video_split_dir = dir_path / "video_split"  # 分割された動画の保存先
    video_slides_dir = dir_path / "video_slides"  # スライド動画の保存先

    # 音声
    audio_downloaded_dir = dir_path / "audio_download"  # ダウンロードした音声の保存先
    audio_tts_dir = dir_path / "audio_tts_wav"  # TTS音声の保存先
    audio_ymm_dir = dir_path / "audio_ymm_wav"  # YMM用音声の保存先

    # テキスト
    text_dir = dir_path / "texts"  # テキストファイルの保存先
    text_ymm_dir = dir_path / "texts_ymm"  # YMM用テキストの保存先

    # 画像
    image_dir = dir_path / "images"  # 画像ファイルの保存先
    image_frames_dir = dir_path / "image_frames"  # フレーム画像の保存先
    image_filtered_frames_dir = dir_path / "image_filtered_frames"  # フィルター処理したフレーム画像の保存先
    image_thumbnail_dir = dir_path / "image_thumbnail"  # サムネイル画像の保存先
        
    # 処理後のクリーンナップ
    removing_dir_list = [   video_downloaded_dir,
                            video_split_dir,
                            video_slides_dir,
                            audio_downloaded_dir,
                            audio_tts_dir,
                            audio_ymm_dir,
                            text_dir,
                            text_ymm_dir,
                            image_dir,
                            image_frames_dir,
                            image_filtered_frames_dir,
                            image_thumbnail_dir
                        ]
    # ファイルを削除
    remove_all_files_in_directories(removing_dir_list)
    # キャッシュされたメモリを削除
    gc.collect()

#############################################################################################################
if __name__ == "__main__":
    main()
