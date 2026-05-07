from pathlib import Path
import re

# テキストファイルから行を読み込む ###########################################################
def lines_from_txt(raw_translated_text_path):
    # 翻訳済みのテキストファイルを読み込む
    raw_translated_text = raw_translated_text_path.read_text(encoding='utf-8')

    # テキストを行ごとに分割, 型はリスト
    lines = raw_translated_text.split('\n')
    return lines


# 開始時刻表記から始まっていない行を前行と結合 ################################################
def merge_unstamped_lines(lines):
    merged_lines = []
    for i, line in enumerate(lines):
        line = line.strip()
        
        if line.startswith('['): # 行が開始時間から始まっている場合
            merged_lines.append(line)
        else: # 行が開始時間から始まっていない場合
            if not merged_lines:
                print(f"{i}行目が開始時刻表記から始まっていないため、無視します。")
                continue
            merged_lines[-1] += " " + line
            print(f"{i}行目が開始時刻表記から始まっていない為、前行と結合しました。")

    print(f"\n開始時刻表記から始まっていない行を全て結合しました。\n")
    print("*"*50)
    return merged_lines if isinstance(merged_lines, list) else [merged_lines]


# 最初の行が0秒から始まっていない場合、無音区間を挿入 ###########################################
def add_zero_start_lines(lines):
    line = lines[0]  # 最初の行の開始時間を取得

    parts = line.split("]")
    times = parts[0].replace("[", "").split(" -> ")
    start_time = float(times[0].strip('s'))
    end_time = float(times[1].strip('s'))
    text = parts[1].strip()

    if text == "" and start_time > 0.00:
        lines[0] = f"[0.00s -> {end_time:.2f}s] "
        print("\n最初の行のテキストが空の為、開始時間を0秒に変更しました。\n")
        print("*"*50)
        return lines  # 条件に当てはまった場合はここで返す

    if start_time > 0.00:
        lines.insert(0, f"[0.00s -> {start_time:.2f}s] ")
        print("\n最初の行が0秒から開始していない為、無音区間を挿入しました。\n")
        print("*"*50)
        return lines  # 条件に当てはまった場合はここで返す

    # 上記のどちらの if にも入らなかった場合
    # ここで必ずリストを返してあげる
    return lines


# 開始時刻が終了時刻と一致している行を前行に統合 ###############################################
def merge_zero_duration_lines(lines):
    merged_lines = []
    for i, line in enumerate(lines):
        parts = line.split("]") # 行を開始時間、終了時間、テキストに分割
        times = parts[0].replace("[", "").split(" -> ") # 開始時間と終了時間を取得, sを削除, 型はリスト
        start_time = float(times[0].strip('s'))
        end_time = float(times[1].strip('s'))
        text = parts[1].strip() # テキストを取得

        # 開始時間と終了時間が一致している場合
        if start_time == end_time:
            # 前の行を取得し、結合
            merged_lines[-1] += " " + text
            print(f"{i}行目の再生時間が0秒の為、前行のテキストに結合しました。")
        else:
            merged_lines.append(line)

    print("*"*50)
    return merged_lines


# 開始時刻が終了時刻よりも後の時刻である行の開始時刻と終了時刻を入れ替える ##########################
def reverse_wrong_timestamps(lines):
    reversed_lines = []

    for i, line in enumerate(lines):
        parts = line.split("]") # 行を開始時間、終了時間、テキストに分割
        times = parts[0].replace("[", "").split(" -> ") # 開始時間と終了時間を取得, sを削除, 型はリスト
        start_time = float(times[0].strip('s'))
        end_time = float(times[1].strip('s'))
        text = parts[1].strip() # テキストを取得

        # 開始時間が終了時間よりも後の時刻である場合
        if start_time > end_time:
            # 開始時間と終了時間を入れ替え
            reversed_line = f"[{end_time:.2f}s -> {start_time:.2f}s]{text}"
            reversed_lines.append(reversed_line)
            print(f"{i}行目の開始時間と終了時間が逆転しているため、修正しました。")

        else:
            reversed_lines.append(line)

    print("*"*50)
    return reversed_lines


# タイムスタンプが重複しており、かつテキストが重複している行を削除 ##################################
def remove_duplicate_lines(lines):
    new_lines = [] # 重複していない行を格納するリスト
    previous_text = "" # 前の行のテキストを格納する変数

    for i, line in enumerate(lines):
        parts = line.split("]") # 行を開始時間、終了時間、テキストに分割
        text = parts[1].strip() # テキストを取得

        # テキストが前の行のテキストと重複し、かつタイムスタンプが重複している場合
        if text == previous_text:
            print(f"{i}行目のテキストが重複しているため、削除しました。")
            continue # 次の行に進む.　この行を追加しない
        # 重複していない場合
        else:
            new_lines.append(line)
            previous_text = text

    print("*"*50)
    return new_lines if isinstance(new_lines, list) else [new_lines]


# 全ての行のテキストがユニークか確認 #############################################################
def is_all_unique_text(lines):
    previous_text = "" # 前の行のテキストを格納する変数

    for i, line in enumerate(lines):
        parts = line.split("]") # 行を開始時間、終了時間、テキストに分割
        text = parts[1].strip() # テキストを取得

        # テキストが前の行のテキストと重複し、かつタイムスタンプが重複している場合
        if text == previous_text:
            print(f"{i}行目のテキストが重複しています。")
            return False
        # 重複していない場合
        else:
            previous_text = text

    return True


# 全ての行が連続しているか確認 ##############################################################
def is_all_continuous(lines):
    for i, line in enumerate(lines):
        parts = line.split("]") # 行を開始時間、終了時間、テキストに分割
        times = parts[0].replace("[", "").split(" -> ") # 開始時間と終了時間を取得, sを削除, 型はリスト
        start_time = float(times[0].strip('s'))
        end_time = float(times[1].strip('s'))
        text = parts[1].strip() # テキストを取得

        if i == 0:
            continue

        if start_time > end_time:
            print(f"{i}行目の開始時間が終了時間よりも後の時刻です。")
            return False
        
        if start_time == end_time:
            print(f"{i}行目の開始時間と終了時間が一致しています。")
            return False
        
        if i > 0:
            previous_line = lines[i-1]
            previous_parts = previous_line.split("]")
            previous_times = previous_parts[0].replace("[", "").split(" -> ")
            previous_end_time = float(previous_times[1].strip('s'))
            if start_time != previous_end_time:
                print(f"{i}行目の開始時間が前行の終了時間と一致しません。\n")
                return False

    print(f"\n全ての行が連続しています。:is_all_continuous\n")
    return True


# 開始時刻が前行の終了時刻と一致しない行を統合 ##############################################
def merge_discontinuous_times(lines):
    formatted_lines = []  # フォーマットされた行を格納するリスト
    last_start_time = "0.00s"  # 初期の開始時間を設定
    last_end_time = "0.00s"  # 初期の終了時間を設定

    for i, line in enumerate(lines):
        parts = line.split("]")  # 行を開始時間、終了時間、テキストに分割
        times = parts[0].replace("[", "").split(" -> ")  # 開始時間と終了時間を取得
        start_time = float(times[0].strip('s'))
        end_time = float(times[1].strip('s'))
        text = parts[1].strip()  # テキストを取得

        # 最初の行はそのまま追加
        if i == 0:
            last_start_time = start_time
            last_end_time = end_time
            formatted_lines.append(line)
            continue

        # 前の終了時間と現在の開始時間が一致しない場合、前の終了時間を修正
        if last_end_time != start_time:
            print(f"{i}行目の開始時間が前行の終了時間と一致しないため、前の終了時間を修正しました。")
            print(f"修正前: [{last_start_time}s -> {last_end_time}s]")
            last_end_time = start_time  # 終了時間を修正
            print(f"修正後: [{last_start_time}s -> {last_end_time}s]")
            print("\n")

        # 修正した終了時間で前の行を更新
        formatted_lines[-1] = f"[{last_start_time}s -> {last_end_time}s] {formatted_lines[-1].split(']')[1].strip()}"

        # 現在の行をそのまま追加
        formatted_lines.append(line)

        # 開始・終了時間を更新
        last_start_time = start_time
        last_end_time = end_time

    print("*" * 50)
    return formatted_lines  # フォーマットされたテキストを返す


# 不要な記号を削除 ########################################################################
def remove_symbols(lines):
    word_list = ["[拍手]", "[拍手", "(拍手)", "（拍手）", "（笑い）", "(笑い)", "[音楽が流れる]", "[音楽]", "[音楽","[外国語]", "[Music]", "[Music", "[music]", "[MUSIC]", "'", "<", ">>", ",", "&"]

    formatted_lines = []


    for i, line in enumerate(lines):

        # 不要な文字や記号のクリーンアップ
        for word in word_list: # word_listの各要素に対して処理
            if word in line: # wordがformatted_lineに含まれている場合
                line = line.replace(word, "") # 不要な文字列を削除
                print(f"{i}行目のTTS未対応文字の不要な記号 {word} を削除しました。")

        formatted_lines.append(line)

    print("*"*50)
    return formatted_lines if isinstance(formatted_lines, list) else [formatted_lines]



# テキストが空の行を削除 ##############################################################################
def remove_empty_lines(lines):
    new_lines = [] # 0秒から始まる行を格納するリスト
    # 空行を削除
    for i, line in enumerate(lines):
        text = line.split(']')[1].strip()  # テキスト内容を取得
        if text == "": # テキストが空の場合
            print(f"01-1: {i}行目が空行のため削除しました。")

        else:
            new_lines.append(line)
    
    print("*"*50)
    return new_lines


# 表記統一 #########################################a#####################################
def normalize_timestamp_format(lines):
    new_lines = []
    for line in lines:
        parts = line.split("]", 1)
        start, end = parts[0].lstrip("[").split("->")
        text = parts[1].strip()
        new_lines.append(
            f"[{float(start.strip().rstrip('s')):.2f}s -> {float(end.strip().rstrip('s')):.2f}s] {text}"
        )
    return new_lines


# フォーマットされたテキストを保存 ###########################################################
def save_lines_to_txt(formatted_text_path, lines):
    if not isinstance(lines, list):
        print("エラー: `lines` がリストではありません。処理を中止します。")
        return
    # リストを文字列に変換
    text = "\n".join(lines)

    print("\nフォーマット済みテキスト:\n")
    print(text,"\n")
    print("*"*50)

    with open(formatted_text_path, 'w', encoding='utf-8') as f:
        f.write(text)

    print("\n翻訳されたテキストを保存しました。")
    print(f"保存ファイルのパス：\n{formatted_text_path}\n")
    print("*"*50)


#########################################################################################
# メイン関数 ##############################################################################
#########################################################################################
def main():

    # 翻訳後のデータ保存パスの設定
    this_dir = Path(__file__).resolve().parent
    data_dir = this_dir / "data" / "texts"

    # 翻訳済みのテキストファイルのパス
    raw_translated_text_path = data_dir / "raw_translated_text.txt"
    formatted_text_path = data_dir / "formatted_translated_texts.txt"
    print("*"*50)
    print(f"翻訳済テキストファイルのパスを設定しました。\n")

    lines = lines_from_txt(raw_translated_text_path) # テキストファイルから行を読み込む
    lines = merge_unstamped_lines(lines) # 開始時刻表記から始まっていないテキスト行を前行と結合
    print("lines:", lines)

    while True:
        lines = remove_duplicate_lines(lines) # テキストが重複している行を削除
        lines = merge_zero_duration_lines(lines) # 開始時刻が終了時刻と一致している行を前行に統合
        lines = reverse_wrong_timestamps(lines) # 開始時刻が終了時刻よりも後の時刻である行の開始時刻と終了時刻を入れ替える
        lines = merge_discontinuous_times(lines) # 開始時刻が前行の終了時刻と一致しない行を統合
        lines = normalize_timestamp_format(lines) # タイムスタンプ表記を小数点以下２桁に統一


        # 全ての行が連続しているかつテキストがユニークか確認
        if is_all_continuous(lines) and is_all_unique_text(lines):
            break # ループを抜ける

    print(f"DEBUG 1: lines の型: {type(lines)}")  # これをデバッグ用に追加

    lines = remove_symbols(lines) # 不要な記号を削除

    print(f"DEBUG 2: lines の型: {type(lines)}")  # これをデバッグ用に追加

    lines = add_zero_start_lines(lines) # 最初の行が0秒から始まっていない場合、無音区間を挿入

    print(f"DEBUG 3: lines の型: {type(lines)}")  # これをデバッグ用に追加


    # 以下、音声ファイルの長さとの比較を追記しました：

    # ディレクトリの設定
    this_dir = Path(__file__).resolve().parent
    audio_dir = this_dir / "data" / "audio_download"
    audio_path = audio_dir / "downloaded_audio.wav"

    # .wavファイルの再生時間を取得
    from pydub import AudioSegment
    audio = AudioSegment.from_wav(audio_path)
    audio_duration = audio.duration_seconds

    # テキストの最終行の終了時刻を取得し、audio_duration と比較して更新する
    last_line = lines[-1]
    parts = last_line.split("]")  # 行を開始時間、終了時間、テキストに分割
    times = parts[0].replace("[", "").split(" -> ")
    start_time = float(times[0].strip('s'))
    end_time = float(times[1].strip('s'))
    text = parts[1].strip()  # テキストを取得

    print(f"最後の行の終了時刻: {end_time:.2f}秒, 音声全体の長さ: {audio_duration:.2f}秒")
    if audio_duration > end_time:
        print("音声全体の長さが最後の行の終了時刻より長いため、最後の行を更新します。")
        # 更新した行を生成
        updated_last_line = f"[{start_time:.2f}s -> {audio_duration:.2f}s] {text}"
        lines[-1] = updated_last_line
        print(f"更新後の最後の行: {updated_last_line}")
    else:
        print("最後の行の終了時刻は音声全体の長さと一致しています。")


    # フォーマットされたテキストを保存
    save_lines_to_txt(formatted_text_path, lines)

    print(f"\nこのコードの処理が全て完了しました。\n")

#########################################################################################
if __name__ == "__main__":
    main()
