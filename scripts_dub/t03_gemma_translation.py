# 標準外部ライブラリのインポート pip install ollama
from pathlib import Path
import os

from ollama import chat
from ollama import ChatResponse

# 翻訳インストラクション　######################################################################
def select_first_instruction(language_symbol): # return instruction

    # 和訳用の翻訳インストラクション
    instruction_jp = """
    あなたは、英語のトランスクリプトから日本語への変換に特化した翻訳機です。

    ### 目的 ###
    * 英語の会話映像から抽出したトランスクリプトを、英語が分からない日本人のために吹き替え音声用のテキストに翻訳します。
    * 翻訳されたテキストは、元の音声再生時刻表示に合わせて配置されるように調整します。
    * 必要な情報と意味を保持しながら、各行の音声再生時間に合わせて、1秒あたりの文字数が6から7文字以下になるように短く簡潔な日本語訳を目指します。
    * 直訳を避け、日本人リスナーが自然に感じる口語体の表現を使用します。

    ### 命令文 ###
    * 各行を自然な口語体の日本語に翻訳してください。
    * チャンク間の文のつながりが自然になるように、前後の文脈を考慮してください。
    * いかなる場合でも元のトランスクリプトの行数（冒頭にタイムスタンプがある行を一単位とした行数）を保持してください。
    * 各行の時刻表示は変更せずに正確に保持し、元のトランスクリプトの時刻表記を忠実に転記してください。
    * 翻訳結果のテキストは、元のトランスクリプトの再生時刻と整合するように配置してください。
    * 重要な数字やキーワードは省略しないでください。
    * 英語の単語は、アルファベットのカタカナへの変換例に従って日本語カタカナに置き換えてください。
    * 出力するのは、翻訳された日本語のテキストと元の時刻情報のみです。追加のコメントや説明は含めないでください。
    * 各セグメントの翻訳結果テキストは元のトランスクリプトが配置されていた時刻枠内に自然に配置し、聞き手が一貫した自然なペースで情報を受け取れるようにしてください。
    * 各チャンクの翻訳に際して、次のチャンクの最初の行を参照し、文のつながりが自然になるように翻訳してください。
    * 文末や文頭が不自然に途切れないように調整してください。
    * 不要な指示語（例：['それ', 'その', 'これ', 'この']）や冗長な表現を避け、文章を簡潔にしてください。
    * 同じ意味を伝えるために、より短い表現や言い換えを検討してください。

    ### 重要ルール ###
    * 元のトランスクリプトの各再生時刻に、翻訳後のテキストを正確に配置させて、同一時刻に配置させてください。
    * 時刻情報、[Music]や[Silent]といったタグは、元のトランスクリプトからそのまま変更せずに保持してください。**
    * 翻訳後の再生時刻が元のトランスクリプトの再生時刻とずれてしまうと、リスナーが混乱する原因となります。
    * すべての行を確実に翻訳し、最後の時刻の行まで正確に出力に含めてください。行数を変えないでください。
    * **[Music]や[Silent]のような音楽や無音部分の時刻情報は、翻訳によって変更されないように特に注意してください。**
    * トランスクリプトの時刻表記の内容と数を、元の英語版と完全に一致するよう厳守してください。
    * 時刻のズレや削除がないように注意深くチェックしてください。
    * 文章が音楽や無音のセグメントを含む場合でも、それらを明示的に記載し、削除しないようにしてください。
    * 翻訳する際は、トランスクリプトの時刻表記に誤りがないように注意します。
    * 各行の前後で重複した翻訳結果を避ける。
    * 元のトランスクリプトの[Music]の時刻は、正確に保持します。**絶対に時間をずらしてはいけません。**
    * 各行の翻訳結果は、元の音声再生時間内に収まるように文字数を調整してください。
    * 可能な限り短い言葉やフレーズを使用し、自然な口語体で簡潔に表現してください。

    ### 禁止事項 ###
    * 下記の入力例や出力例をそのまま使用しないでください。
    * トランスクリプトの元の英語表現を出力に含めないでください。
    * 英語単語はアルファベット表記にしないで、すべてカタカナに置き換えてください。
    * 翻訳結果に元の英語トランスクリプトを含めてはいけません。
    * もし入力したチャンクに文字が含まれていない場合は、何も出力しないでください。
    * トランスクリプト内のどの行のコンテンツも時刻表記も省略しないでください。
    * [Music]や[Silent]などのタグやそれに対応する時刻情報を削除したり、変更したりしないでください。
    * 文章を不必要に長くする表現を避けてください。

    ### 入出力の例1 ###
    英語によるトランスクリプトの入力例：
    [0.00s -> 9.48s] here is the easiest way to create your own gpts without chat GPT plus and 
    [9.48s -> 21.72s] without spending $20 a month not having access to gpts is a massive disadvantage for anyone in the AI space right now as 
    [21.72s -> 34.00s] you're not only unable to build your own gbts for personal and business use but you're also unable to develop your 
    [34.00s -> 45.32s] skills as a gbt developer which I believe will be one of the most valuable skills in 2024 luckily for you in this 
    [45.32s -> 55.28s] video I'll be showing you a dead simple way to get access to build use and share 
    [55.28s -> 65.44s] your own gpts without chat GPT plus and for a fraction of the cost if you're new to the channel and don't know who I am 
    [65.44s -> 76.44s] my name is Liam otley I run my own AI development company called morning site Ai and I also run the largest community 
    [76.44s -> 88.24s] of AI agency owners in the world where my students learn how to make money by selling AI solutions to businesses just 
    [88.24s -> 98.28s] like the gpts that you're about to build let's get started in order to start creating your own gpts without chat GPT 
    [98.28s -> 109.16s] plus you need to sign up to my new platform called agentive which at the moment is free for the time being but 
    [109.16s -> 118.88s] there is about a 48 to 72 hour delay to get in so there's a little bit of a wait list as we onboard users but in the 
    [118.88s -> 130.68s] description you can sign up so that you can follow along with this when you're ready this is the sign up and login screen here so you can click on join 

    自然な日本語へ翻訳した良い出力例：　行数を維持しているため、翻訳後の日本語テキストの長さが短くなっている。
    [0.00s -> 9.48s] チャット ジーピーティー プラスを使わずに自分のジーピーティーを簡単に作る方法です。
    [9.48s -> 21.72s] 月20ドルを使わずにジーピーティーにアクセスしないのは今のエーアイ業界で大きな不利益です。
    [21.72s -> 34.00s] 個人やビジネスで自作ジーピーティーを作れないだけでなく
    [34.00s -> 45.32s] 開発スキルも身に付けられません。このスキルは2024年にとても価値があるとされています。
    [45.32s -> 55.28s] チャット ジーピーティー プラスを使わずに、作り、使い、共有する簡単な方法を紹介します。
    [55.28s -> 65.44s] より安く自作のジーピーティーを作る方法です。もしチャンネルが新しく、私を知らない方のために、
    [65.44s -> 76.44s] 私はリアム・オトリーです。エーアイ開発会社モーニング・サイト・エーアイを経営し、世界最大のエーアイエージェンシーオーナーのコミュニティも運営してます。
    [76.44s -> 88.24s] そこでは私の生徒たちがビジネスにエーアイソリューションを売る方法を学び、収入を得てます。
    [88.24s -> 98.28s] これから作るGPTのようにです。始めよう。自分のジーピーティーを作るために
    [98.28s -> 109.16s] 私の新しいプラットフォーム「アジェンティブ」にサインアップの必要があります。今は無料ですが
    [109.16s -> 118.88s] 参加するのに48から72時間の待ち時間があるので、少し待つ必要があります。しかし説明欄にサインアップすれば
    [118.88s -> 130.68s] 準備ができたらプロセスに沿って進められます。これがサインアップとログインの画面です。参加するにはクリックしてください。

    ### 入出力の例2 ###
    英語によるトランスクリプトの入力例：
    [144.00s -> 148.84s] less than 6,000 people we really believe we can maximize our impact on patient
    [148.84s -> 154.12s] with a few thousand people for using technology and using AI so we can scale
    [154.12s -> 159.32s] the company and so I'm very thankful for the entire openi team and the time and
    [159.32s -> 165.23s] engagement they have with our team so that together we can save more lives
    [165.23s -> 169.84s] [Music]
    
    自然な日本語へ翻訳した良い出力例：　行数を正確に維持し、時刻と記述内容が翻訳前の英語と一致しており、必要最小限の情報が保持されている。
    [144.00s -> 148.84s] 6,000人未満ですが、患者への影響を最大化できると信じています。
    [148.84s -> 154.12s] 数千人を対象に技術とAIを用いることで、私たちは企業の拡大を図ることができます。
    [154.12s -> 159.32s] オープンアイチーム全体との時間と取り組みに感謝しています。
    [159.32s -> 165.23s] そうすることで、より多くの命を救うことができます。
    [165.23s -> 169.84s] [音楽]

    悪い出力例：　勝手に行数を減らしている悪い例です。
    [144.00s -> 148.84s] 6,000人未満です。テクノロジーとAIを使用して、数千人で患者への影響を最大化できると確信しています。
    [148.84s -> 154.12s] 会社を拡大できます。オープンアイチーム全体と、
    [154.12s -> 159.32s] チームとの時間と関わりに感謝しています。そうすることで、より多くの命を救うことができます。
    [159.32s -> 165.23s]

    ### アルファベットのカタカナへの変換例 ###
    OpenAI DevDayの -> オープンエーアイ　デブデイ
    GPT-4 Turbo -> ジーピーティーフォー　ターボ
    JSON -> ジェイソン
    Python -> パイソン
    API -> エーピーアイ
    Revit -> レビット
    REVIT -> レビット
    revit -> レビット
    Avail -> アベイル
    CAD -> キャド
    o1 -> オーワン
    GitHub -> ギットハブ
    """

    # 英訳用の翻訳インストラクション
    instruction_en = """
    You are a translation model specialized in converting Japanese transcripts to English.

    ### Purpose ###
    * Translate transcripts extracted from Japanese conversation videos into text suitable for dubbing for English-speaking audiences.
    * The translated text should be adjusted to align with the original audio's timestamps.
    * Aim for concise English translations, ensuring that the necessary information and meaning are preserved while matching the speech timing. Target approximately 2.5 to 3 English words per second.
    * Use natural spoken English, avoiding literal translations, to ensure English listeners feel the speech is fluid and natural.

    ### Instructions ###
    * Translate each line from the Japanese transcript into natural spoken English, following the input/output examples provided below.
    * Ensure that the transitions between the current and adjacent segments are smooth and natural, preserving the overall flow of the conversation.
    * Always retain the original number of lines in the transcript.
    * Keep the timestamp of each line exactly as it appears in the original transcript.
    * Ensure the translated text is aligned with the original transcript’s playback time, maintaining a smooth and consistent pace for listeners.
    * Do not omit important numbers or keywords from the translation.
    * Convert any katakana or kanji words to their English equivalents.
    * The output should contain only the translated English text and the original timestamp. Do not include your own comments or explanations in the output.
    * Ensure that each translated segment fits naturally within the original transcript's time frames, allowing the listener to follow the content comfortably.
    * Avoid unnecessary words or verbose expressions, and aim for concise phrasing to match the speech duration.

    ### Important Rules ###
    * The translated text must be aligned precisely with the original playback timestamps.
    * Do not modify or remove any tags such as [Music] or [Silent] from the original transcript.** Retain them exactly as they appear in the original transcript.
    * Ensure that [Music] or [Silent] timestamps are preserved exactly as they are. Do not shift or alter these times under any circumstances.**
    * Any misalignment between the translated text and the original timestamps is not acceptable. Make sure to check that all lines are translated, and that the final timestamp is included.
    * If there are music or silent segments in the transcript, explicitly include them in the output without modification or removal.
    * Ensure that no part of the transcript's timestamp or content is omitted or altered during translation.
    * Avoid duplicating content across consecutive lines.
    * When translating adjacent segments, ensure the transitions between them are smooth and natural. Avoid abrupt beginnings or endings.
    * Ensure that the translated text fits naturally within the original time frame, with a target of approximately 2.5 to 3 words per second.

    ### Prohibited Actions ###
    * Do not use the example inputs or outputs directly in your output.
    * Do not include the original Japanese text in the output.
    * Do not retain any Japanese words in katakana or kanji; always translate them into their English equivalents.
    * Do not omit any lines or timestamps from the transcript, including tags like [Music] or [Silent].
    * If the input transcript contains no text for a particular segment, do not output anything for that segment.
    * Do not reduce the number of lines by combining multiple lines into one.

    #### Example Input/Output 1
    Input Japanese transcript example:
    [0.00s -> 9.48s] ここでは、ChatGPT Plusを使用せずにGPTを作成する最も簡単な方法を紹介します。
    [9.48s -> 21.72s] 月額20ドルを払わずにGPTを作成できることは、現在のAI業界において大きなメリットです。
    [21.72s -> 34.00s] GPTを個人またはビジネスで作成できない場合、AI開発者としてのスキルを伸ばすことができません。

    Good translation output example: (The length of the English translation is shortened to match the spoken timing.)
    [0.00s -> 9.48s] Here's the easiest way to create your own GPTs without using ChatGPT Plus.
    [9.48s -> 21.72s] Being able to create GPTs without paying $20 a month is a big advantage in the current AI industry.
    [21.72s -> 34.00s] If you can't create GPTs for personal or business use, you won't be able to grow as a GPT developer.

    #### Example Input/Output 2
    Input Japanese transcript example:
    [144.00s -> 148.84s] 私たちは6,000人未満ですが、患者への影響を最大化できると信じています。
    [148.84s -> 154.12s] 数千人の技術とAIの利用で、企業を拡大することができます。
    [154.12s -> 159.32s] 私たちはOpenAIチーム全体に感謝しています。

    Good translation output example:
    [144.00s -> 148.84s] We have fewer than 6,000 people, but we believe we can maximize our impact on patients.
    [148.84s -> 154.12s] By using AI and technology with just a few thousand people, we can scale our company.
    [154.12s -> 159.32s] We're very thankful to the entire OpenAI team.

    ### Japanese to English Conversion Examples
    ジーピーティー -> GPT
    エーピーアイ -> API
    パイソン -> Python
    キャド -> CAD
    """

    if language_symbol == "jp":
        return instruction_jp
    elif language_symbol == "":
        return instruction_jp
    elif language_symbol == "en":
        return instruction_en
    else:
        return None


# トランスクリプト・テキストの取得　#############################################################
def get_text_contents(combined_transcript_path): # return text_content
    if combined_transcript_path is None:
        print("Invalid path provided.")
        return None

    with open(combined_transcript_path, "r", encoding="utf-8") as input_data:
        text_content = input_data.read()
    print("*"*50,"\n","トランスクリプトのテキストを取得しました。\n")
    return text_content


# チャンクの設定　############################################################################
def set_chunk_text(text_content, chunk_size, overlap=2): # return chunk_list
    lines = text_content.split('\n')
    chunk_list = []
    total_chunks = (len(lines) - overlap) // (chunk_size - overlap) + 1
    chunk_number = 1  # チャンク番号の初期化

    for i in range(0, len(lines), chunk_size - overlap):
        chunk = '\n'.join(lines[i:i+chunk_size])
        chunk_list.append(chunk)
        chunk_number += 1

    print("*" * 50, "\n", f"{total_chunks}個のチャンクリストの設定が完了しました。\n")
    return chunk_list


# 初回のユーザーのコンテンツの設定　###############################################################
def get_first_user_content(i, previous_translated_chunk, this_chunk, line_num, next_chunk, language_symbol): # return user_content

    if language_symbol == "jp":
        language_symbol = "日本語"
    elif language_symbol == "en":
        language_symbol = "English"

    if i == 0:
        user_content = f"""
        Translate only the current target chunk according to the given instructions.
        The translation output MUST have {line_num} lines matching the current target chunk.
        Ensure that the target language for this translation is {language_symbol} as defined in the system instruction.
        Adjust the sentence endings so they naturally connect to the following text segment, while ensuring timestamps remain unchanged.
        There is NO need to output translations for the following reference chunk.

        <Current target chunk>
        {this_chunk}
        </Current target chunk>

        <Following reference chunk>
        {next_chunk}
        """

    else:
        user_content = f"""
        Translate only the current target chunk according to the given instructions.
        The translation output MUST have {line_num} lines matched with the current target chunk.
        Ensure that the target language for this translation is {language_symbol} as defined in the system instruction.
        In any case, maintain the original number of lines in the transcript, considering each line with a timestamp at the beginning as a single unit.
        To begin with this output, copy the last timestamp and text from the previously translated chunk (DO NOT copy the timestamps from the following reference chunk).
        And paste the line as the first line of this output.
        Then, seamlessly continue to translate the timestamp and text from the 2nd line of the current target chunk.
        Adjust the sentence endings so they naturally connect to the following text segment, while ensuring timestamps remain unchanged.
        There is NO need to output translations for the previously translated chunk or the following reference chunk.

        <Previously translated chunk>
        {previous_translated_chunk}
        </Previously translated chunk>

        <Current target chunk>
        {this_chunk}
        </Current target chunk>

        <Following reference chunk>
        {next_chunk}
        </Following reference chunk>
        """
    return user_content


# 見直し用のユーザーのコンテンツの設定　###############################################################
def get_second_user_content(original_chunk, initial_translated_chunk, line_num): # return user_content
    user_content = f"""
    Please review the original transcript and your initial translation, then ensure your translation aligns with the following instructions.
    Adjust the placement of timestamps and translated text to match the original transcript's timeframes.
    The refined output MUST contain {line_num} lines, each corresponding to the original transcript.

    ### Instructions ###
    * Align the translated text exactly with the original audio's timestamps.
    * In any case, please maintain the original number of lines in the transcript, considering each line with a timestamp at the beginning as a single unit.
    * Retain the original number of lines from the transcript.
    * Preserve each timestamp exactly as it appears in the original transcript.
    * Synchronize the translated text with the playback time for a smooth, consistent listening experience.
    * Ensure each translated segment fits naturally within the original time frames, allowing for easy comprehension.
    * Any misalignment between the translated text and the original timestamps is unacceptable. Verify that all lines are translated and the final timestamp is included.
    * Do not omit or alter any part of the transcript’s timestamps or content during translation.
    * Avoid duplicating content across consecutive lines.
    * Ensure smooth transitions between consecutive segments, avoiding abrupt starts or endings.
    * Do not combine multiple lines into one or reduce the overall number of lines.
    * When translating into Japanese, remove unnecessary demonstrative words (e.g., ['それ', 'その', 'これ', 'この']) and redundant expressions. Keep the sentences concise.
    * Where possible, review the original chunk to make text adjustments that improve the natural expression and simplicity of the translation, considering the time duration of each line. This will help refine the translation for a more polished and fluent output.
    * If the text content of a specific line in the initial translation result is not placed in the appropriate timestamp line according to the original transcript, adjust it so that the translated text is positioned at the correct timestamp.
    * Ensure that no lines are left blank in the latter part of the translation. While checking the original transcript content, appropriately split and distribute the translated text so that it is placed evenly across all lines, reaching the final line.
    * Exclude any additional comments or explanations from the output.

    # Original Transcript for Timestamp and Content Reference #
    {original_chunk}

    # Your initial translation draft for refinement #
    {initial_translated_chunk}

    """
    return user_content


# メモリの解放　############################################################################
def del_memory(response):

    del response
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


# トランスクリプト・チャンクごとの翻訳　###############################################################
def get_translated_chunks(chunk_list, instruction_0, model_name, language_symbol, overlap=2): # return translated_chunk_list

    chunk_num = len(chunk_list)  # チャンクの数を取得

    translated_chunk_list = []  # 翻訳されたチャンクを格納するリスト
    for i, this_chunk in enumerate(chunk_list):

        line_num = len(this_chunk.strip().split('\n'))  # チャンクの行数を取得
        print(f"No.{i+1}/{chunk_num} Chunk: {line_num}行" ,"*"*30,"\n")
        print(f"入力文:")
        print(this_chunk, "\n")


        # 1回目のオーバーラップ付き翻訳処理 ***********************************

        if i == 0:  # 最初のチャンクの場合
            previous_translated_chunk = "None as this is the first instance."
        else:  # 2番目以降のチャンクの場合
            previous_translated_chunk = translated_chunk_list[i - 1]  # 前のチャンクの翻訳結果を取得

        if i == chunk_num - 1:  # 最後のチャンクの場合
            next_chunk = "None as this is the last instance."
        else:  # 最後以外のチャンクの場合
            next_chunk = chunk_list[i + 1]  # 次のチャンクを取得



        first_user_content = get_first_user_content(i, previous_translated_chunk, this_chunk, line_num, next_chunk, language_symbol)

        message_list = [
                {"role": "system", "content": instruction_0},
                {"role": "user", "content": first_user_content}
            ]
        
        response = chat(model=model_name, messages=message_list)
        raw_translated_chunk = response.message.content  # 翻訳されたチャンクを取得
        print(f"No.{i+1}/{chunk_num} Chunkの１回目 {overlap}Overlap付 翻訳結果:")
        print(raw_translated_chunk, "\n")

        del_memory(response)

        # 2回目の見直し翻訳処理 ********************************************************
        second_user_content = get_second_user_content(this_chunk, raw_translated_chunk, line_num)

        message_list = [
                {"role": "system", "content": instruction_0},
                {"role": "user", "content": first_user_content},

                # 1回目の翻訳結果をアシスタントに表示して認識させる
                {"role": "assistant", "content": raw_translated_chunk},
                # 見直しの上、再出力の指示
                {"role": "user", "content": second_user_content}
            ]
        
        response = chat(model=model_name, messages=message_list)

        reviewed_translated_chunk = response.message.content  # 翻訳されたチャンクを取得
        print(f"翻訳２回目 {overlap}行Overlap付:")
        print(reviewed_translated_chunk, "\n")

        del_memory(response)

        """
        例：
        - 前回処理済みのチャンクの行が A,B,C,D,E で、overlap=2の時、D,Eを重複して、
          今回チャンクの行が D,E,F,G,H となる。
        - 今回チャンクの翻訳の際に、
          最初の行Dが、前回処理のチャンクの最後から2行目のDと全く同じテキスト内容で始めること。
        - 前回処理のチャンクの最後の行Eを除外して、A,B,C,Dとし、
          今回チャンクの最初の行Dを除外して、E,F,G,Hとして結合する。
        - こうすることで、文のつながりが自然になるように翻訳することができる。
        """

        # 翻訳されたチャンクを行ごとに分割
        translated_lines = reviewed_translated_chunk.strip().split('\n')

        if overlap > 0:
        # オーバーラップの処理
            if i == 0:
                # 最初のチャンク：最後の (overlap - 1) 行を除外。
                # overlap = 1 の場合は(overlap - 1)=0 なので、何も変わらない。
                translated_lines = translated_lines[:-(overlap - 1)]
            elif i < chunk_num - 1:
                # 中間のチャンク：最初の行を除外し、最後の (overlap - 1) 行を除外
                translated_lines = translated_lines[1:-(overlap - 1)]
            else:
                # 最後のチャンク：最初の行を除外
                translated_lines = translated_lines[1:]

        # 翻訳されたチャンクをリストに追加
        this_translated_chunk = '\n'.join(translated_lines)
        translated_chunk_list.append(this_translated_chunk)

    print("*" * 50, "\n", "翻訳・加工済みテキスト\n")
    print('\n'.join(translated_chunk_list), "\n")
    print("*" * 50, "\n", f"全てのチャンクの翻訳が完了しました。\n\n")
    return translated_chunk_list



############################################################################################################
# 翻訳の実行　###############################################################################################
def main(language_symbol=None):

    ##### 各種設定 #####
    chunk_size = 10  # チャンクサイズの設定
    overlap = 0  # オーバーラップ行数の設定
    model_name = "gemma3:12b"  # モデル名の設定 gemma3:12b / gemma3:27b

    language_symbol = "jp" # 言語シンボルの設定 (jp or en)

    first_instruction = select_first_instruction(language_symbol)

    # 翻訳後のデータ保存パスの設定
    this_dir = Path(__file__).resolve().parent
    data_dir = this_dir / "data" / "texts"

    # 入力用のトランスクリプト・テキストのパス
    combined_transcript_path = data_dir / "combined_transcript.txt"
    # 出力用の翻訳テキストのパス
    raw_translated_text_path = data_dir / "raw_translated_text.txt"
    
    # トランスクリプト・テキストの取得
    input_text_content = get_text_contents(combined_transcript_path)

    # チャンクリストの設定
    chunk_list = set_chunk_text(input_text_content, chunk_size, overlap)

    # トランスクリプト・チャンク毎の翻訳と結合
    translated_chunk_list = get_translated_chunks(chunk_list, first_instruction, model_name, language_symbol, overlap)
    translated_text = '\n'.join(translated_chunk_list)  # リストを改行で結合

    # 翻訳されたテキストを保存
    raw_translated_text_path.write_text(translated_text, encoding='utf-8')
    print(f"保存ファイルのパス：\n{raw_translated_text_path}\n")
    print("*"*50,f"\nこのコードの処理が全て完了しました。")


############################################################################################################
if __name__ == "__main__":
    main()
