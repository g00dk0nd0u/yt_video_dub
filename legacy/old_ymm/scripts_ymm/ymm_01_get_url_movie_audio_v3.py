# 標準外ライブラリをインポート: pip install yt-dlp Pillow requests
from pathlib import Path
import yt_dlp
from PIL import Image
import requests
import re

# Pillowのバージョンに応じてリサンプリングフィルタを設定 ###################################################
try:
    resampling_filter = Image.Resampling.LANCZOS
except AttributeError:
    resampling_filter = Image.ANTIALIAS

# 指定ディレクトリ内のファイルを全て削除 ##############################################################
def clear_directory(download_path, file_extensions) -> None:
    """
    指定ディレクトリ内のファイルを全て削除
    """
    audio_path = Path(download_path)
    for file in audio_path.iterdir():
        if file.suffix.lstrip('.').lower() in [ext.lower() for ext in file_extensions]:
            try:
                file.unlink()
            except Exception as e:
                print(f"ファイルの削除に失敗しました: {file}, エラー: {e}")


# 映像のみをダウンロードし、mp4に変換してパスを返す ########################################################
def get_only_video(url, video_dir_path, max_height) -> None:
    """
    YouTube から映像のみをダウンロードし、指定フォルダに保存する
    """
    try:
        ydl_opts = {
            "format": f"bestvideo[height<={max_height}][ext=mp4]",  # 音声を含めない設定
            "outtmpl": str(Path(video_dir_path) / "downloaded_video.mp4"),
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "cookiefile": str(
                Path("www.youtube.com_cookies.txt")
            ),  # 取得したクッキーファイルを指定
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            # ダウンロードされたファイルのパスを取得
            filename = ydl.prepare_filename(result)
            file_path = Path(filename)
            only_video_path = file_path.with_suffix('.mp4')

        print(f"映像のmp4ファイルをダウンロードしました。\n")

    except Exception as e:
        print(f"映像をダウンロードできませんでした: {e}")
        if "HTTP Error 400: Bad Request" in str(e):
            print("YouTube側の制限により、このビデオはダウンロードできない可能性があります。")


# 音声のみをダウンロードし、指定フォルダに保存する ########################################################
def get_only_audio(url, audio_dir_path, audio_format="wav") -> None:
    """
    YouTube から音声のみをダウンロードし、指定フォルダに保存する
    """
    try:
        audio_dir_path.mkdir(parents=True, exist_ok=True)
        ydl_opts = {
            "format": f"bestaudio[ext={audio_format}]/bestaudio",  # 音声のみ
            "outtmpl": str(Path(audio_dir_path) / "downloaded_audio.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "cookiefile": str(Path("www.youtube.com_cookies.txt")),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "192",
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(result)
            audio_path = Path(filename).with_suffix(f".{audio_format}")
        print(f"音声ファイルをダウンロードしました: {audio_path}\n")
        return audio_path

    except Exception as e:
        print(f"音声をダウンロードできませんでした: {e}")


# サムネイルをダウンロードする関数 ######################################################################
def download_thumbnail(url, image_file_path, resolution) -> None:
    """
    YouTubeのサムネイルをダウンロードする
    """

    # 正規表現を使用してYouTube動画IDを抽出
    pattern = r'(?:https?:\/\/(?:www\.|m\.)?youtube\.com\/(?:embed\/|watch\?v=)|https?:\/\/youtu\.be\/)([^\n\r&?]+)'
    match = re.search(pattern, url)
    if match: # 動画IDが見つかった場合
        video_id = match.group(1)
    else:
        print("動画IDが見つかりませんでした。")

    # サムネールのURLを構築
    image_url = f'https://img.youtube.com/vi/{video_id}/{resolution}.jpg'
    
    # サムネールを取得
    response = requests.get(image_url)
    if response.status_code == 200:
        with open(image_file_path, 'wb') as f:
            f.write(response.content)
        print(f'サムネールを保存しました。\n')

    else:
        print('サムネールの取得に失敗しました。URL:', url)


########################################################################################################################
# メイン関数 #############################################################################################################
def main():

    max_height = 1080  # 映像の最大解像度  HD画質:1080p  4K:2160p

    # ダウンロード先のディレクトリを設定
    this_dir_path = Path(__file__).resolve().parent
    url_texts_dir_path = this_dir_path / "data" / "texts" / "url.txt"
    video_dir_path = this_dir_path / "data" / "video_download"
    audio_dir_path = this_dir_path / "data" / "audio_download"  # ←追加
    image_dir_path = this_dir_path / "data" / "image_thumbnail"
    thumbnail_file_path = image_dir_path / "thumbnail.jpg"
    original_frames_dir = this_dir_path / "data" / "image_frames"

    print("*" * 50, "\n")


    # URLを取得してtxtファイルに保存
    url = input("URLを入力してください: ").strip()  # インプットのプロンプトにコロンを追加
    if not url:
        print("有効なURLを入力してください。")
        return
    
    # URLをtxtファイルに保存, exist_ok=Trueでディレクトリが存在しない場合に作成
    url_texts_dir_path.parent.mkdir(parents=True, exist_ok=True)
    with url_texts_dir_path.open('w', encoding='utf-8') as f:
        f.write(url)

    print("\n")
    print("*" * 50, f"\nurlを記載したtxtファイルを保存しました。")

    # クリーンアップ
    extention_dic = {
        video_dir_path: ["mp4"],
        audio_dir_path: ["wav", "m4a", "mp3"],
        image_dir_path: ["jpg", "webp", "png", "webm", "mp4"],
        original_frames_dir: ["jpg", "jpeg", "png", "webp", "mp4"]
    }

    for directory_path, file_extensions in extention_dic.items(): #items()でキーと値のペアを取得
        clear_directory(directory_path, file_extensions)
    print("\n実行前にvideo_downloadとimagesフォルダ内のファイルを削除しました。\n")

    # 映像のダウンロード
    get_only_video(url, video_dir_path, max_height)
    # 音声のダウンロード ←追加
    get_only_audio(url, audio_dir_path, audio_format="wav")

    # サムネイルのダウンロード
    download_thumbnail(url, thumbnail_file_path, resolution='maxresdefault')

    print("*" * 50, f"\nget url movie audioのコードの処理が全て完了しました。\n")


# 実行 #######################################################################################################
if __name__ == "__main__":
    main()
