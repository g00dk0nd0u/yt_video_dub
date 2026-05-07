# pip install pydub matplotlib numpy
# 翻訳済みの日本語テキストから音声を生成し、元のトランスクリプトの時間に合わせた無音を加えて、最後に合成音声を作成します。
# 準備 docker pull voicevox/voicevox_engine:cpu-ubuntu20.04-latest
# 開始 docker run --rm -p '127.0.0.1:50021:50021' voicevox/voicevox_engine:cpu-ubuntu20.04-latest
# 停止 docker stop 1fe7661d2de9
# 参考サイト1: https://hub.docker.com/r/voicevox/voicevox_engine
# 参考サイト2: https://github.com/VOICEVOX/voicevox_engine?tab=readme-ov-file#%E3%83%A6%E3%83%BC%E3%82%B6%E3%83%BC%E3%82%AC%E3%82%A4%E3%83%89
# Dockerを立ち上げなくてもVOICEVOXのアプリを起動すれば Engineを使用することができます。

import requests
import os
from pydub import AudioSegment
import io
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv

# 作業用ファイルを消去 #########################################################################
def remove_all_files_in_directories(directory_paths):
    for directory_path in directory_paths:
        # ディレクトリが存在するかチェック
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            # ディレクトリ内のすべてのファイルを取得
            for file_name in os.listdir(directory_path):
                file_path = os.path.join(directory_path, file_name)
                # ファイルであれば削除
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"'{file_path}' を削除できませんでした: {e}")
        else:
            print(f"'{directory_path}' が存在しないか、ディレクトリではありません。")
    print("*" * 50, f"\n{directory_paths}のファイルを消去しました。\n")


# request テスト ########################################################################################
def is_tts_engine_working(line, speaker_num=1):
    try:
        # HTTP POSTリクエストを送信し、タイムアウトを指定
        response = requests.post(
            "http://127.0.0.1:50021/audio_query",
            params={"text": line, "speaker": speaker_num},
        )

        # ステータスコードが200の場合、応答を返す
        if response.status_code == 200:
            print("\nTTS出力テストは成功しました。\n")
        else:
            print(f"\nステータスコード:{response.status_code}")
            exit()
    except:
        print("\nTTS出力テストは失敗しました。TTSエンジンを起動してください\n")
        exit()


# 翻訳済みテキストファイルパス -> テキスト行リスト(new_lines) ##############################################
def get_lines_from_csv(csv_path, speaker_map):
    lines = []
    speakers = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                speaker, text = row[0].strip(), row[1].strip()
                speaker_id = speaker_map.get(speaker)
                if speaker_id is None:
                    print(f"未定義の話者名: {speaker}")
                    continue
                lines.append(text)
                speakers.append(speaker_id)
    print(f"{len(lines)} 行のセリフを読み込みました。")
    return lines, speakers




# テキスト行リスト(new_lines) -> 音声合成。ファイル保存。音声データリスト tts_segments　######################
def create_lines_voice_parallel(
    lines, speeds, speaker_ids, intonation_scales=None, volume_scales=None, silence_duration=0.1
):
    if intonation_scales is None:
        intonation_scales = [1.0] * len(lines)
    if volume_scales is None:
        volume_scales = [1.0] * len(lines)
        
    tts_segments = [None] * len(lines)

    with ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(
                create_single_voice,
                line,
                speed,
                speaker_id,
                intonation_scale,
                volume_scale,
                silence_duration
            ): i
            for i, (line, speed, speaker_id, intonation_scale, volume_scale) in enumerate(
                zip(lines, speeds, speaker_ids, intonation_scales, volume_scales)
            )
        }

        for future in as_completed(futures):
            i = futures[future]
            tts_segments[i] = future.result()
            print(f"{i}行目の音声を生成しました。", flush=True)

    return tts_segments


# 個別行の再生成を行う関数 ########################################################################
def create_single_voice(
    line, speed, speaker_num=1, intonation_scale=1.0, volume_scale=1.0, silence_duration=0.01
):
    if line == "":
        return AudioSegment.silent(duration=10)  # 0.01秒の無音

    response = requests.post(
        "http://127.0.0.1:50021/audio_query",
        params={"text": line, "speaker": speaker_num},
    )

    if response.status_code != 200:
        raise Exception(f"Error in audio_query: {response.status_code} {response.text}")

    audio_query = response.json()
    # クエリに追加パラメータを設定
    audio_query["speedScale"] = speed
    audio_query["intonationScale"] = intonation_scale
    audio_query["volumeScale"] = volume_scale
    audio_query["prePhonemeLength"] = 0.1
    audio_query["postPhonemeLength"] = 0.5
    audio_query["outputSamplingRate"] = 24000
    audio_query["outputStereo"] = False

    response = requests.post(
        "http://127.0.0.1:50021/synthesis",
        json=audio_query,
        params={"speaker": speaker_num},
    )

    if response.status_code != 200:
        raise Exception(f"Error in synthesis: {response.status_code} {response.text}")

    audio = AudioSegment.from_file(io.BytesIO(response.content), format="wav")
    silence = AudioSegment.silent(duration=int(silence_duration * 1000))  # 秒→ミリ秒変換
    return audio + silence



# 音声セグメントを保存 ################################################################################
def save_audio_segments(audio_tts_dir, tts_segments, speaker_ids):
    for file in os.listdir(audio_tts_dir):
        if file.endswith(".wav"):
            os.remove(os.path.join(audio_tts_dir, file))

    print("\n生成音声を保存します。\n")

    for i, (segment, speaker_id) in enumerate(zip(tts_segments, speaker_ids)):
        if speaker_id == 3:
            prefix = "zundamon"
        elif speaker_id == 2:
            prefix = "shikokumetan"
        else:
            prefix = "unknown"

        filename = f"{i:03d}_{prefix}.wav"
        with open(os.path.join(audio_tts_dir, filename), "wb") as f:
            segment.export(f, format="wav")

    print(f"{len(tts_segments)} 行の音声を {audio_tts_dir} に保存しました。\n")


# 生成した音声セグメント・リスト -> 再生時間リスト　generated_durations　####################################
def get_tts_duration(tts_segments):

    generated_durations = []
    for i, segment in enumerate(tts_segments):
        generated_durations.append(len(segment) / 1000.0)  # ミリ秒から秒へ変換

    total_duration = sum(generated_durations)
    print(f"\n音声の合計時間は{total_duration}秒です。\n")
    return total_duration


# 合計再生時間をcsvファイルに保存 ########################################################################
def save_total_time_to_csv(total_duration, output_path):
    """
    合計再生時間をCSVファイルに1行だけ上書き保存する。
    """
    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([total_duration])
        print(f"合計再生時間を {output_path} に上書き保存しました。\n")
    except Exception as e:
        print(f"CSVファイルへの保存中にエラーが発生しました: {e}")


########################################################################################################
# 実行 #################################################################################################
# docker run --rm -p '127.0.0.1:50021:50021' voicevox/voicevox_engine:cpu-ubuntu20.04-latest
def main():

    # 今後話者が増える場合に備えて
    SPEAKER_MAP = {
        "ずんだもん": 3,
        "四国めたん": 2,
        "春日部つむぎ": 8,
        "冥鳴ひまり": 14,
        "はっきり女性1": 20,
        "WhiteCUL": 23,
        "女性2": 24,
        "しっとり女性3": 25,
        "男性1": 11,
        "男性2": 13,
        "剣崎雌雄": 21,
        "男性4": 52,
        "男性5": 53,
    }
    
    # 話者ごとのパラメータ設定を追加
    SPEAKER_PARAMS = {
        3: {"speed": 1.25, "intonation": 1.0, "volume": 1.2},  # ずんだもん
        2: {"speed": 1.10, "intonation": 1.0, "volume": 1.2},  # 四国めたん
        8: {"speed": 1.15, "intonation": 1.0, "volume": 1.2},  # 春日部つむぎ
        # 必要に応じて他の話者も追加
    }
    
    # 初期設定 (デフォルト値として使用)
    default_speed = 1.15
    default_intonation = 1.0
    default_volume = 1.2
    silence_duration = 0.1  # ここで調整可能（例：0.2にすると0.2秒無音）


    is_tts_engine_working("テスト音声です。", speaker_num=3)  # テスト音声出力

    # パスの設定
    dir_path = os.path.dirname(os.path.abspath(__file__)) + "/data/"
    transcript_csv_path = dir_path + "texts_ymm/ymm_transcript.csv"
    audio_tts_dir = dir_path + "audio_ymm_wav/"
    text_dir = dir_path + "texts_ymm/ymm_total_duration.csv"

    # ファイルの削除
    remove_all_files_in_directories([audio_tts_dir])

    # CSVファイルからテキストと話者番号を読み込む
    lines, speaker_ids = get_lines_from_csv(transcript_csv_path, SPEAKER_MAP)
    
    # 話者IDごとにパラメータを設定
    speeds = []
    intonations = []
    volumes = []
    
    for speaker_id in speaker_ids:
        if speaker_id in SPEAKER_PARAMS:
            speeds.append(SPEAKER_PARAMS[speaker_id]["speed"])
            intonations.append(SPEAKER_PARAMS[speaker_id]["intonation"])
            volumes.append(SPEAKER_PARAMS[speaker_id]["volume"])
        else:
            speeds.append(default_speed)
            intonations.append(default_intonation)
            volumes.append(default_volume)

    # 話者IDごとにTTSを生成
    tts_segments = create_lines_voice_parallel(
        lines, speeds, speaker_ids, intonations, volumes, silence_duration
    )

    # 話者名ごとにファイル保存
    save_audio_segments(audio_tts_dir, tts_segments, speaker_ids)

    # 合計再生時間を計算
    total_tts_duration = get_tts_duration(tts_segments)

    # 合計再生時間をcsvファイルに記入・保存
    save_total_time_to_csv(total_tts_duration, text_dir)  # 引数の順序を修正

    print("*" * 70, f"\nコードの処理が全て完了しました。\n")


if __name__ == "__main__":
    main()
