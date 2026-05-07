# 標準外ライブラリをインポート: pip install youtube_transcript_api
import re
import subprocess
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi
import shutil

# 指定ディレクトリ内のファイルを全て削除 ##############################################################
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


# ダウンロード先のディレクトリを設定　################################################################
def set_dir_path(folder_name, subfolder_name=''):
    dir_path = Path(__file__).resolve().parent / folder_name / subfolder_name
    dir_path.mkdir(parents=True, exist_ok=True)  # ディレクトリが存在しない場合、作成
    return str(dir_path)  # Pathオブジェクトを文字列に変換


# url.txtからURLを取得 ################################################################################
def get_url(texts_dir_path):
    url_path = texts_dir_path / "url.txt"
    with url_path.open('r', encoding='utf-8') as f:
        url = f.read().strip()
    return url


# Video IDを取得する関数　#########################################################################
def get_youtube_id(url):

    # 通常のYouTube動画のパターン
    pattern_normal = r'(?:https?://(?:www\.|m\.)?youtube\.com/(?:embed/|watch\?v=)|https?://youtu\.be/)([^\n\r&?]+)'
    match = re.search(pattern_normal, url)
    
    if not match:
        # ショートのURLのパターン
        pattern_short = r'https?://(?:www\.|m\.)?youtube\.com/shorts/([^\n\r&?]+)'
        match = re.search(pattern_short, url)
    
    if not match:
        # ショートの共有URLのパターン
        pattern_shared_short = r'https?://youtube\.com/shorts/([^\n\r&?]+)'
        match = re.search(pattern_shared_short, url)
    
    video_id = match.group(1) if match else None
    print(f"VIDEO_IDを取得しました: {video_id}\n")
    return video_id


# 言語コードを取得　###############################################################################
def get_language_code(video_id):
    if not video_id:
        return None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['en', 'ja']) # 英語と日本語のトランスクリプトを取得
            print(f"言語コードを取得しました: {transcript.language_code}\n")
            return transcript.language_code
        except Exception:
            transcript = next(t for t in transcript_list)
            print(f"言語コードを取得しました: {transcript.language_code}\n") # 他の言語のトランスクリプトを取得
            return transcript.language_code
    except Exception as e:
        print(f"言語リストを取得できませんでした: {e}")
        return None


# 生トランスクリプト・テキストを未加工で取得　###########################################################
def get_raw_transcripts(video_id, language_code):
    if not language_code:
        print("言語コードが取得できないため、トランスクリプト内容を取得できませんでした")
        return None
    try:
        raw_transcripts = YouTubeTranscriptApi.get_transcript(video_id, languages=[language_code])
        print("*"*50,"\n",f"トランスクリプト・テキストを未加工で取得しました:\n\n{raw_transcripts}\n")
        return raw_transcripts
    
    except Exception as e:
        print(f"トランスクリプト内容を取得できませんでした: {e}")
        return None


# 生トランスクリプト・テキストと時刻情報を含むテキストリストを取得　#########################################
def get_texts_with_timestamps(transcripts):
    if not transcripts:
        print("トランスクリプト・テキストが取得できないため、空のリストを返します")
        return []
    
    text_list = []
    for i, transcript in enumerate(transcripts):
        start_second = transcript['start']
        end_second = start_second + transcript['duration'] if i == len(transcripts) - 1 else transcripts[i + 1]['start']
        text_content = transcript['text'].replace('\n', ' ') # テキストの改行をスペースに変換
        text = f"[{start_second:.2f}s -> {end_second:.2f}s] {text_content}\n" # 時刻情報を追加
        text_list.append(text)
    print(f"\n[タイプスタンプ] テキスト のリストを取得しました\n")
    return text_list


# テキストリストからテキストデータを保存　##############################################################
def save_text_file(text_list, texts_dir_path, transcript_file_name):
    transcript_file_path = texts_dir_path / transcript_file_name
    with transcript_file_path.open('w', encoding='utf-8') as f:
        for text in text_list:
            f.write(text)
    return str(transcript_file_path)  # Pathオブジェクトを文字列に変換


# テキストリストを指定秒以上にまとめて取得　#############################################################
def get_combined_transcripts(text_list, min_second):

    if not text_list: # テキストリストが空の場合
        return None # Noneを返す

    combined_transcripts = []  # トランスクリプトの結合用リスト
    last_text = ''  # 前行のテキスト、初期値は空
    current_duration = 0.0  # 現在の時間、初期値は0
    last_start_time = float(text_list[0].split(' -> ')[0].split('[')[1].split('s')[0])  # 最初の行の開始時刻

    for line in text_list: # テキストリストをループし、指定秒数未満の場合は結合する。lineは各行のテキスト
        this_start = float(line.split(' -> ')[0].split('[')[1].split('s')[0]) # この行の開始時間を取得
        this_end = float(line.split(' -> ')[1].split('s')[0]) # この行の終了時間を取得
        this_duration = this_end - this_start # この行の時間を計算
        this_text = line.split('] ')[1].strip() # 時刻情報を除いたテキストのみを取得
        last_text += this_text + ' ' # テキストのみをスペースで結合
        current_duration += this_duration # 現在の時間に、この行の時間を加算して更新

        # 累積時間が指定秒数を超えたら、新しいセグメントとして追加
        if current_duration >= min_second:
            combined_transcripts.append({'text': last_text.strip(), 'start': last_start_time, 'duration': current_duration})
            last_text = ''  # テキストをリセット
            current_duration = 0.0  # 時間をリセット
            last_start_time = this_end  # 次のセグメントの開始時間を更新

    # 最後のセグメントを追加（まだ追加されていないテキストがあれば）
    if last_text:
        combined_transcripts.append({'text': last_text.strip(), 'start': last_start_time, 'duration': current_duration})

    print("*"*50, "\n", f"トランスクリプト・テキストのリストを指定秒数以上にまとめて取得しました")
    return combined_transcripts


def extract_frames_from_video(video_path, timestamps, output_dir):
    """
    指定されたタイムスタンプに対応するフレームを動画から抽出し、画像として保存する
    
    Args:
        video_path (str): 動画ファイルのパス
        timestamps (list): 抽出したいタイムスタンプのリスト（秒単位の浮動小数点）
        output_dir (str): フレーム画像の保存先ディレクトリ
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nフレーム画像の抽出を開始します...\n")
    
    for i, ts in enumerate(timestamps):
        output_image_path = output_dir / f"frame_{i+1:03d}_{ts:.2f}s.jpg"
        
        # FFmpegコマンドを構築
        command = [
            "ffmpeg",
            "-ss", str(ts),  # シークする位置（秒）
            "-i", str(video_path),  # 入力ファイル
            "-frames:v", "1",  # 1フレームだけ抽出
            "-q:v", "2",  # 画質設定（2は高品質）
            "-y",  # 出力ファイルを上書き
            str(output_image_path)
        ]
        
        try:
            # FFmpegを実行
            subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"フレーム {i+1}/{len(timestamps)} を保存: {output_image_path.name}")
        except Exception as e:
            print(f"フレーム {ts}秒 の抽出中にエラーが発生: {e}")
    
    print(f"\n合計 {len(timestamps)} 個のフレームを保存しました。")


###################################################################################################
# 実行 #############################################################################################
def main():

    this_dir = Path(__file__).resolve().parent
    texts_dir_path = this_dir / "data" / "texts"

    # URLを取得
    url = get_url(texts_dir_path )  # Pathオブジェクトに変換
    print("*"*50,f"\nurlを設定しました：\n\n{url}\n")
    
    min_second = 1  # 再生時間の最小秒数を指定
    print(f"再生時間の最小秒数を設定しました： {min_second} sec\n")

    video_id = get_youtube_id(url) #VIDEO_IDを取得

    videoid_texts_dir_path = texts_dir_path / "videoid.txt"
    
    # video idをtxtファイルに保存, exist_ok=Trueでディレクトリが存在しない場合に作成
    videoid_texts_dir_path.parent.mkdir(parents=True, exist_ok=True)
    with videoid_texts_dir_path.open('w', encoding='utf-8') as f:
        f.write(video_id)

    language_code = get_language_code(video_id) #言語コードを取得
    raw_transcripts = get_raw_transcripts(video_id, language_code) #生トランスクリプト・テキストを未加工で取得

    # 生トランスクリプトと時刻情報を含むテキストリストを取得
    raw_text_list= get_texts_with_timestamps(raw_transcripts)
    
    # リストから生テキストを保存
    raw_text_filename = "raw_transcript" + ".txt"
    save_text_file(raw_text_list, Path(texts_dir_path), raw_text_filename)
    print("*"*50,"\n",f"リストから未加工トランスクリプト {raw_text_filename} を取得・保存しました\n")

    # タイムスタンプ結合処理: raw_text_list -> combined_transcripts -> text_list -> text
    combined_transcripts = get_combined_transcripts(raw_text_list, min_second) # テキストリストを指定秒以上にまとめて取得
    
    # 指定秒数以上に結合したトランスクリプト・テキストと時刻情報を含む、結合済みテキストリストを取得
    combined_text_list= get_texts_with_timestamps(combined_transcripts)
    combined_text = ''.join(combined_text_list)
    print("*"*50,"\n",f"指定秒数以上にまとめたトランスクリプトを取得しました:\n\n{combined_text}\n")

    #06 テキストリストからテキストデータを保存・取得
    combined_text_filename = "combined_transcript" + ".txt"
    save_text_file(combined_text_list, Path(texts_dir_path), combined_text_filename)
    print("*"*50,"\n",f"指定秒数以上にまとめたトランスクリプトを保存しました:  {combined_text_filename}\n")


    ######################################################################################
    ### スライド用フレームの取得処理 ########################################################

    user_direction = input("スライド用フレームを取得しますか？ (y/n): ").strip().lower()
    if user_direction != 'y':
        print("スライド用フレームの取得をスキップします。")
        return
    print("*"*50,"\n",f"スライド用フレームを取得します\n")

    # 動画のパスを設定
    video_dir_path = set_dir_path("data", "video_download")
    video_file_path = Path(video_dir_path) / "downloaded_video.mp4"
    
    if not video_file_path.exists():
        print(f"警告: 動画ファイル {video_file_path} が見つかりません。フレーム抽出をスキップします。")
    else:
        # フレーム画像の保存先を設定
        frames_dir_path = set_dir_path("data", "image_frames")

        clear_directory(frames_dir_path, extensions=['.jpg'])
        print("*"*50)
        print(f"\n動画フレーム画像の保存先をクリーンアップしました: {frames_dir_path}\n")


        # 開始時刻のリストを取り出す
        timestamps = [segment['start'] for segment in combined_transcripts]
        
        print("*"*50)
        print(f"\nトランスクリプトに合わせて {len(timestamps)} 個のフレームを抽出します")
        
        # フレームを抽出して保存
        extract_frames_from_video(video_file_path, timestamps, frames_dir_path)
        
        print("*"*50)
        print(f"\nタイムスタンプ対応の動画フレームを保存しました: {frames_dir_path}")
    
    print("*"*50,f"\nこのコードの処理が全て完了しました。\n")


###################################################################################################
if __name__ == "__main__":
    main()

