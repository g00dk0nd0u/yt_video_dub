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
import matplotlib.pyplot as plt
import numpy as np
import json
import io
from concurrent.futures import ProcessPoolExecutor, as_completed


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


# 翻訳済みテキストファイルパス -> テキスト行リスト(new_lines) ##############################################
def get_text_lines(text_file_dir):
    new_lines = []  # テキスト行を格納するリスト
    with open(text_file_dir, "r", encoding="utf-8") as f:  # テキストファイルを読み込む
        lines = f.readlines()  # テキストファイルを1行ずつ読み込む
    for line in lines:  # 1行ずつ処理
        if "]" in line:  # "]" を含む行のみ処理
            line = line.split("]")[1].strip()  # 時間情報を削除
            new_lines.append(line)  # リストに追加

    print(f"翻訳済みtxtファイルから{len(new_lines)}行のテキストを取得しました。")
    return new_lines  # テキスト行のリストを返す


# 翻訳済みテキストリストパス -> 各行の再生時間リスト（original_durations）　#################################
def get_original_duration(transcript_text_path):
    original_durations = []
    with open(transcript_text_path, "r", encoding="utf-8") as file:
        for line in file:
            parts = line.split("]")
            times = parts[0].replace("[", "").split(" -> ")
            start_time = float(times[0].strip("s"))
            end_time = float(times[1].strip("s"))
            duration = end_time - start_time
            original_durations.append(duration)
    return original_durations


# 再生時間リスト -> 合計再生時間(total_duration)　#######################################################
def print_total_time(durations):
    total_duration = sum(durations)
    print(f"\n音声の合計時間は{total_duration}秒です。\n")
    return total_duration


# テキスト行リスト(new_lines) -> 音声合成。ファイル保存。音声データリスト tts_segments　######################
def create_lines_voice_parallel(
    lines, speeds, speaker_num=1, intonation_scale=1.0, volume_scale=1.0
):

    # 各行の音声を生成
    tts_segments = [None] * len(lines)  # サイズを固定して順序が乱れないように初期化

    # 並列処理を行うためのProcessPoolExecutor
    with ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(
                create_single_voice,
                line,
                speed,
                speaker_num,
                intonation_scale,
                volume_scale,
            ): i
            for i, (line, speed) in enumerate(zip(lines, speeds))
        }

        for future in as_completed(futures):
            i = futures[future]
            tts_segments[i] = future.result()
            print(
                f"{i}行目の音声を生成しました。", flush=True
            )  # 生成ごとにリアルタイムで出力

    return tts_segments


# 11 個別行の再生成を行う関数 ########################################################################
def create_single_voice(
    line, speed, speaker_num=1, intonation_scale=1.0, volume_scale=1.0
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

    return AudioSegment.from_file(io.BytesIO(response.content), format="wav")


# 生成した音声セグメント・リスト -> 再生時間リスト　generated_durations　####################################
def get_tts_durations(tts_segments):

    generated_durations = []
    for i, segment in enumerate(tts_segments):
        generated_durations.append(len(segment) / 1000.0)  # ミリ秒から秒へ変換
        print(f"{i}行目: {round(generated_durations[i],3)}s")

    return generated_durations


# 初期設定スピードでの生成音声/翻訳済みテキスト の倍率を計算し、スピードリストを取得　############################
def get_tuned_speeds(generated_durations, original_durations, initial_speed, max_speed):

    print("調整スピードリストを取得します。\n")
    speeds = []  # 速度比率を格納するリスト

    for i, (generated, original) in enumerate(
        zip(generated_durations, original_durations)
    ):
        if original != 0:  # original が 0 でない場合に計算

            if (
                generated > original
            ):  # 予想生成音声がオーバーする場合、スピードを速くする
                tuned_speed = generated / original * initial_speed

                if tuned_speed > max_speed:  # 最大スピードを超える場合
                    tuned_speed = max_speed  # 最大スピードに設定
            else:
                tuned_speed = initial_speed  # 生成音声が短い場合、初期スピードを適用
        else:
            tuned_speed = max_speed  # original が 0 の場合は、最大スピードを適用

        speeds.append(tuned_speed)  # 初期スピードをリストに追加
        print(f"{i}行目: {round(tuned_speed, 3)}")

    return speeds


# 音声セグメントを保存 ################################################################################
def save_audio_segments(audio_tts_dir, tts_segments):

    # 以前の音声ファイルを削除
    for file in os.listdir(audio_tts_dir):
        if file.endswith(".wav"):  # 拡張子が.wavの場合
            os.remove(os.path.join(audio_tts_dir, file))  # ファイルを削除

    print("\n調整生成音声を保存します。\n")

    # 音声ファイルを保存
    for i, segment in enumerate(tts_segments):
        with open(os.path.join(audio_tts_dir, f"tts_{i}.wav"), "wb") as f:
            segment.export(f, format="wav")

    last_num = len(tts_segments) - 1
    print(
        f"最後の{last_num}行目:まで各行の音声ファイルを\n{audio_tts_dir}\nに一時保存しました。\n"
    )


# 最終再生時間リストの取得 #############################################################################
def get_final_durations(original_durations, tuned_tts_durations):

    print("\n", "*" * 50, "\n最終再生時間リストを取得します。\n")
    final_durations = []

    for i, line in enumerate(zip(original_durations, tuned_tts_durations)):
        original, tuned_tts = line

        if original > tuned_tts:  # 翻訳済みテキストの方が長い場合
            final_durations.append(original)  # 翻訳済みテキストの時間をそのまま使う
            print(f"{i}行目: {round(original,3)}s (翻訳テキストの方が長い)")

        else:  # 生成音声の方が長い場合
            final_durations.append(tuned_tts)
            print(f"{i}行目: {round(tuned_tts,3)}s (生成音声の方が長い)")

    return final_durations


# 動画の減速率リストを保存 #############################################################################
def save_slow_rates(
    original_durations, final_durations, slow_rates_text_path, deviation
):

    print("\n", "*" * 50, "\n動画の減速率リストを保存します。\n")
    slow_rates = []

    # original_durations, generated_durationsのリストを同時に処理
    for i, duration in enumerate(zip(original_durations, final_durations)):
        original, generated = duration  # 2つのリストを同時に処理

        if generated > original:  # 生成音声の方が長い場合
            rate = original / generated * (100 - deviation) / 100
            slow_rates.append(rate)
            print(
                f"{i}行目: {round(rate,5)}倍速 = {original}/{generated} * {(100-deviation)/100}"
            )

        else:
            slow_rates.append(1)
            print(f"{i}行目: 1倍速")

    # txtファイルに保存
    with open(slow_rates_text_path, "w") as f:
        for rate in slow_rates:
            f.write(str(rate) + "\n")


# 翻訳済みテキスト、生成音声、結合音声の各行の継続時間を積み上げた折れ線グラフで比較表示　##########################
def map_duration(original_durations, initial_tts_durations, final_durations, path):

    print(
        "\n",
        "*" * 50,
        "\n折れ線グラフを作成します: 翻訳済テキスト、初回生成、最終音声の継続時間\n",
    )

    x = np.arange(len(original_durations))  # データ数に合わせてx軸を設定

    # 累積和を取得
    plt.plot(
        x, np.cumsum(original_durations), label="Original Transcript"
    )  # 翻訳済みテキスト
    plt.plot(x, np.cumsum(initial_tts_durations), label="Initial TTS Audio")  # 予想音声
    plt.plot(x, np.cumsum(final_durations), label="Final Audio")  # 結合音声

    plt.xlabel("Line Number")
    plt.ylabel("Duration (seconds)")
    plt.title("Comparison of Original Transcript and Generated Audio")
    plt.legend()

    # 画像を保存
    os.makedirs(os.path.dirname(path), exist_ok=True)  # 画像保存用ディレクトリを作成
    plt.savefig(path)


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


########################################################################################################
# 実行　#################################################################################################
# docker run --rm -p '127.0.0.1:50021:50021' voicevox/voicevox_engine:cpu-ubuntu20.04-latest
def main(speaker=None):

    if speaker is None:
        print(
            """
    声の設定
    女性 -> 2:四国めたん　3:ずんだもん　8:春日部つむぎ　14:冥鳴ひまり　20:はっきり女性1　23:WhiteCUL　24:女性2　25:しっとり女性3
    男性　-> 11　13　21:剣崎雌雄　52　53:男性
    Number MAXは、60まで。
    """
        )
        speaker = int(input("声番号を入力してください: "))

    # 初期設定
    initial_speed = 1.00  # 初期スピード
    max_speed = 1.15  # 最大スピード
    intonation = 1.0  # 音程スケール
    volume = 1.2  # 音量スケール

    is_tts_engine_working("テスト音声です。", speaker)  # テスト音声出力

    # パスの設定
    dir_path = os.path.dirname(os.path.abspath(__file__)) + "/data/"
    translated_text_path = dir_path + "texts/formatted_translated_texts.txt"
    slow_rates_text_path = dir_path + "texts/slow_rates.txt"
    audio_tts_dir = dir_path + "audio_tts_wav/"
    image_dir = dir_path + "images/time_map.png"

    # ファイルの削除
    remove_all_files_in_directories([audio_tts_dir])

    lines = get_text_lines(translated_text_path)
    original_durations = get_original_duration(translated_text_path)
    print_total_time(original_durations)

    print(
        f"初期設定スピード{initial_speed}倍速で音声セグメント・リストを生成します。\n"
    )
    initial_speeds = [initial_speed] * len(lines)  # 初期スピードリストを生成
    initial_tts_segments = create_lines_voice_parallel(
        lines, initial_speeds, speaker, intonation, volume
    )

    initial_tts_durations = get_tts_durations(initial_tts_segments)
    print_total_time(initial_tts_durations)

    tuned_speeds = get_tuned_speeds(
        initial_tts_durations, original_durations, initial_speed, max_speed
    )

    print("\n必要な部分のみ調整スピードで音声セグメント・リストを再生成します。\n")
    tts_segments = [None] * len(lines)  # 初期化してサイズを確保

    with ProcessPoolExecutor(max_workers=8) as executor:  # 例として最大8ワーカーを指定
        futures = {
            executor.submit(
                create_single_voice, lines[i], tuned_speed, speaker, intonation, volume
            ): i
            for i, (initial_segment, tuned_speed) in enumerate(
                zip(initial_tts_segments, tuned_speeds)
            )
            if tuned_speed != initial_speed
        }

        for future in as_completed(futures):
            i = futures[future]
            try:
                tts_segments[i] = future.result()
                print(
                    f"{i} 行目の音声を調整スピード {round(tuned_speeds[i], 3)} で再生成しました。"
                )
            except Exception as e:
                print(f"{i} 行目でエラーが発生しました: {e}")
                tts_segments[i] = (
                    None  # エラー発生時はNoneを設定（必要に応じて他の処理を検討）
                )

        # 初回生成音声をそのまま使用する部分
        for i, tuned_speed in enumerate(tuned_speeds):
            if tuned_speed == initial_speed:
                tts_segments[i] = initial_tts_segments[i]
                print(f"{i} 行目は再生成せず、初回生成音声を使用しました。")

    tuned_tts_durations = get_tts_durations(tts_segments)

    save_audio_segments(audio_tts_dir, tts_segments)

    final_durations = get_final_durations(original_durations, tuned_tts_durations)

    print_total_time(final_durations)

    save_slow_rates(original_durations, final_durations, slow_rates_text_path, 1)

    map_duration(original_durations, initial_tts_durations, final_durations, image_dir)

    print("*" * 70, f"\nTTSのコードの処理が全て完了しました。\n")


if __name__ == "__main__":
    main()
