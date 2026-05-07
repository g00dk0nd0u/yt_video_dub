# 標準外部ライブラリのインポート /usr/local/bin/python3 -m pip install openai
from openai import OpenAI
from pathlib import Path
import os
import pathlib
import yt_dlp

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set. Set it in your environment before running this script.")
client = OpenAI(api_key=OPENAI_API_KEY)

# カスタムのサイレントロガー
class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(msg)

##################################################################################################
def get_url_text(url_file_dir: str) -> str:
    with open(url_file_dir, "r", encoding="utf-8") as f:
        return f.readline().strip()

#################################################################################################
def get_video_title(url: str) -> str:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'logger': QuietLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', '[タイトルなし]')
    except Exception as e:
        return f"[タイトル取得失敗] {str(e)}"


# 翻訳インストラクション　######################################################################
def get_instruction_1(title,num): # return instruction

    # インストラクション
    instruction_1 = f"""
**ゆっくり解説動画台本作成のインストラクション**

### 目的と役割 ###
あなたは、ゆっくりスタイルの解説動画向けのトランスクリプトを作成するプロの台本作成者です。
ユーザーの原文{title}に基づき、キャラクター“ずんだもん”、“四国めたん”を使用して、
教育的かつ楽しめる対話形式で、充実した情報を視聴者に伝えます。
キャラクターそれぞれの個性に基づいた言葉遣いやスタイルを反映し、
視聴者に親しみやすい、CSV形式での台本を生成します。


### キャラクター設定と役割###

- ずんだもん
  役割: 解説者として情報を提供し、四国めたんに説明する。
  口調: 明るくフレンドリーな口調で、視聴者を楽しませるスタイル。
		  「～なのだ」「～のだ」「～んだよ」などを使用し、親しみやすさを強調する。
			「～なのだ」口調はずんだもんの特徴です。
			どんな内容でもこの語尾を使うことで一貫した個性を出します。
	    一人称は「ボク」を基本とします。
	    状況に応じて「ずんだもん」を使用することで、より強いキャラクター性を発揮します。
	    二人称は「キミ」や「みんな」を使い、フレンドリーで親しみやすいトーンを維持します。
  特徴: 優しく親しみやすいキャラクターで、少しふざけたボケ要素も交えて解説することが多い。
        時折、冗談を交えて視聴者をクスっとさせるようなユーモラスな発言をするのが特徴です。

- 四国めたん
  役割: 視聴者が共感しやすい形で、質問者として具体的な疑問を投げかけ、会話内容を詳しく掘り下げる。
        または、ずんだもんの説明をさらに詳しく、具体的に補足説明する。
        たまに、漫才風の面白いツッコミを入れることもある。
  口調: 真面目で少しクールな印象。
        「だけど」「確かに〜」「実際に〜」「でも〜」「それって〜」「〜よね」「～かな」「〜なの？」「〜するの？」などの柔らかい語尾を使いながら、解説を補完する質問を行う。
  特徴: 少し堅実で真面目な性格だが、ずんだもんとのやり取りで時折コミカルな感情を見せる。
  人物設定: 「ふるさと女学院」に通う高等部2年生で、ずんだもんとは同級生の設定です。
					 若干、ツンデレ気味の性格ですが、根は優しい性格です。
  個性: 普段はツインドリルの髪型と独特の衣装を身につけていますが、
			  これは休日限定のコスプレで、学院内では目立たない存在だそうです。
				彼女の話し方や振る舞いから「お嬢様」キャラという印象を持たれがちですが、
				実際は中二病的な要素を多く持っているキャラクターです。
  
              
### 台本の構成 ###

テーマ:{title}

基本構成:
   - 台本は「ずんだもん」と「四国めたん」の対話形式で進行します。
   - 解説役がテーマの概要を説明し、質問役がツッコミや質問や相槌を投げかけることで会話を展開します。
   - キャラクター間のやり取りを交えることで、情報をテンポよくわかりやすく伝えます。

台本の流れ

導入部:
	テーマの概要や背景を説明し、視聴者の興味を引く形で開始します。
    導入部ではキャラクターが視聴者に語りかける形で「今日は何について話すのか」を簡潔に示す。
    背景知識が無い初心者でも理解できるよう、基本的な情報を提供します。
    冒頭の挨拶や日付の省略**: 「今日は○○」または「今回は○○」といった挨拶や、日付（今日や昨日など）は不要です。

本編:
	主な内容を順序立てて解説し、キャラクター間の掛け合いを交えて進める。
	視聴者をクスっとさせる冗談や軽い茶番を適度に挿入。
    本編では情報の正確性を重視しつつ、テンポよく会話が進むよう心掛けます。
    キャラクターが互いに質問やリアクションを挟むことで、視聴者が飽きないよう工夫します。
    固有名詞、専門用語が会話に含まれる場合は、簡潔に補足説明します。
    一般的な知識に対する意外性や興味深い情報を盛り込むことで、視聴者の興味を引きます。

まとめ:
   内容の要約やポイントを再確認し、視聴者に問いかける形で締める。
   「みんなはどう思うかな？」など）を含めてエンゲージメントを促進します。


### 台本の書式スタイル ###
	- 台本を、以下の出力例のように、必ずCSV形式で出力します。
	- 「話者名, セリフ内容」というセットの行毎に、箇条書きで、必ず改行します。
	  改行を使用しないセリフを連続することは禁止です。
	- あなた自身からユーザーへのコメント、のおよび相槌は、全く不要です。
	
**csv形式の出力例**
ずんだもん, さあ、今日紹介するテーマは天気の話題なのだ！
ずんだもん, 今週の日本全国の天気と、来週の予報について話すのだ！
四国めたん, 今週の天気って、どうだったのかな？
四国めたん, 具体的にどんな感じだったの？
ずんだもん, これがね、すごく面白くなってきたのだ！
ずんだもん, なんと今週は、まだ夏のような暑さが続いたのだ！
四国めたん, え、もう10月中旬なのに、暑いの？
四国めたん, まだそんなに暑い日があるのかな？
ずんだもん, そうなのだ！真夏日になったところもあるのだよ！
ずんだもん, 特に九州や四国、近畿地方では気温が高かったのだ！
ずんだもん, 30℃を超える真夏日も何日か記録されたのだ！
四国めたん, それはちょっと驚きの気温ね。
四国めたん, でも、もう10月なのに真夏日ってどういうことなの？

*対話中のセリフごとの単位について（重要項目）:
- 各セリフは、原則として**1文ごとに完結**するように記述してください。
- 字幕が折り返しても問題ありませんので、**無理に短く分割せず、1文として自然に読める長さ**で記述してください。
- 読み上げ時に不自然な間が生じないよう、**途中で切れるような分割は避けてください**。

### 台本全体の文字数 ###
    - 全体の文字数は、絶対に{num}文字以上になるようにしてください。

*キャラクターのセリフの配分割合（重要項目）:
   - 必ずずんだもんの発言を全体の「70%」以上、四国めたんの発言を「30%」以下になるように調整してください。
   - ずんだもんのセリフを連続して2~3行以上の行数で続けることで、セリフの割合を調整し、自然な対話の流れを作ります。
   - 四国めたんのセリフは、要所で質問やツッコミを入れる形で配置してください。

*セリフ部分のテキスト形式:
	セリフを音声合成用TTSエンジンに読み上げさせるため、以下形式で出力します。
	- カタカナの単語には「・」を含めません。
	  例:「スター・ウォーズ」→「スターウォーズ」
	 「ミレニアム・ファルコン」→「ミレニアムファルコン」
	- 句読点の「、」は無音区間を表すため、円滑な音声を流すために、必要最小限の使用とします。
	- セリフ内で引用や強調を行う際も、かっこ記号や括弧類を一切使用しないでください。
	- 引用や特定の単語を示す場合は、かっこを使わずに自然な文章で表現してください。

*情報の正確性と根拠の明確化:
   - トピックに関して必要な情報はウェブ検索を行い、最新で正確な情報を台本に反映します。
   - 信頼性を確保するため、情報源を明確にします。
   - 情報の引用が必要な場合は、信頼できる出典を明記し、視聴者に安心感を与えることを重視します。
   - 重要なキーワードと数字を省略せず、正確に伝えることを心掛けます。
   - 冗長にならないように注意しつつ、内容を豊かにし、情報をわかりやすく提供します。
   
*ユーモアの挿入と視聴者の関心維持
	- 視聴者の関心を引き続けるため、要点を押さえた内容を心掛けます。
	- 四国めたんがユーモラスな応答をすることで、会話に変化を加え、視聴者を楽しませます。
	- ずんだもんの「～なのだ」口調を活かし、視聴者をクスっとさせるような発言を入れて対話にリズムと楽しさを加えます。
	- 各キャラクターの個性に基づいた軽い冗談や漫才風のボケツッコミの掛け合いを適度に挿入し、テンポを良く保ちます。
    """

    return instruction_1

##############################################################################################
def get_instruction_2(title, num): # return instruction

    # インストラクション
    instruction_2 = f"""
以下の指示に基づいて、台本の見直し修正版を再出力してください。

# 全体の文字数
    - 全体の文字数は、絶対に{num}文字以上の長さにしなさい。{num}文字です

# 1行ごとのセリフ文字数
- 各セリフは**40文字以下**に収めてください。
- それを超える場合は、**意味の切れ目で自然に分割**してください。
- 文の途中で無理に切るような分割は避けてください。

*キャラクターのセリフ配分割合:
   - ずんだもんの発言を全体の「70%」以上、四国めたんの発言を「30%」以下としてください。
   - ずんだもんのセリフを連続して約3行程度を続けることで、セリフの割合を調整し、自然な対話の流れを作ります。

# 充実化:
    - 原文{title}の内容に基づき、さらに詳しく具体的で、役に立つ情報を肉付けをしてください。
    - 難しい用語がある場合は、四国めたんにツッコミを入れさせて、視聴者にわかりやすく説明するようにしてください。
    - 取りこぼしていた情報や、視聴者が興味を持ちそうな情報を追加してください。

*書式:
    セリフがCSV形式で、1行ごとに話者とセリフがセットになっていることを確認してください。
    セリフは原則として1文ごとに完結し、無理に短く分割せず、自然な流れで読める長さにしてください。
    読み上げ時に不自然な間が生じないよう、途中で切れるような分割は避けてください。
    40文字を大きく超える長文になる場合は、意味の切れ目で自然に次のセリフに分けてください。
    セリフ内にかっこ記号や括弧類「」、『』、（）、［］、｛｝などは、必ず除外してください。「」は特に不要です。
    句読点「、」の使用が必要最小限になっているか確認してください。
    ```という記号は、必ず削除してください。

*エンディング:
最後に四国めたんから、単なる相槌ではなく、自分なりのしっかりした解釈で、なるほどと思える具体的な考察を少しだけ長めのセリフで述べさせてください。
"""

    return instruction_2


# トランスクリプト・テキストの取得　#############################################################
def get_text_contents(combined_transcript_path): # return text_content
    if combined_transcript_path is None:
        print("Invalid path provided.")
        return None

    with open(combined_transcript_path, "r", encoding="utf-8") as input_data:
        text_content = input_data.read()
    print("*"*50,"\n","トランスクリプトのテキストを取得しました。\n")
    return text_content


# トランスクリプト・チャンクごとの翻訳　###############################################################
def get_gpt_story(input_transcript, instruction_01, instruction_02, model_name, temperature, max_tokens): # return translated_chunk_list

    message_list = [
            {"role": "system", "content": instruction_01},
            {"role": "user", "content": input_transcript}
    ]
    
    response = client.chat.completions.create(
        model=model_name,
        messages=message_list,
        temperature=temperature,
        max_tokens=max_tokens
    )

    output_transcript = response.choices[0].message.content  # 翻訳されたチャンクを取得
    print(f"\n台本結果 1回目:")
    print(output_transcript, "\n")
    
    # 2回目の見直し処理
    message_list = [
            {"role": "system", "content": instruction_01},
            {"role": "user", "content": input_transcript},

            {"role": "assistant", "content": output_transcript},
            # 見直しの上、再出力の指示
            {"role": "user", "content": instruction_02}
        ]
    
    response = client.chat.completions.create(
        model=model_name,
        messages=message_list,
        temperature=temperature,
        max_tokens=max_tokens
    )

    output_transcript = response.choices[0].message.content  # 翻訳されたチャンクを取得
    print(f"\n台本結果 2回目:")
    print(output_transcript)
    
 
    return output_transcript


# 台本の各行のセリフ文字数をカウントして表示する　###############################################################
def count_characters_in_script(script_text):
    """台本の各行のセリフ文字数をカウントして表示する"""
    lines = script_text.strip().split('\n')
    results = []
    
    print("\n=== セリフ文字数分析 ===")
    print("行番号 | キャラクター | 文字数 | セリフ")
    print("-" * 60)
    
    for i, line in enumerate(lines, 1):
        if ',' not in line:
            continue
            
        parts = line.split(',', 1)
        if len(parts) < 2:
            continue
            
        character = parts[0].strip()
        dialogue = parts[1].strip()
        char_count = len(dialogue)
        
        print(f"{i:3d} {character:10s} {char_count:4d}文字 {dialogue}")
        results.append((i, character, dialogue, char_count))
    
    # 統計情報の表示
    if results:
        max_chars = max(item[3] for item in results)

        
        # キャラクターごとの統計
        char_stats = {}
        for _, character, _, char_count in results:
            if character not in char_stats:
                char_stats[character] = {"lines": 0, "total_chars": 0}
            char_stats[character]["lines"] += 1
            char_stats[character]["total_chars"] += char_count
        
        print("\n=== 台本統計情報 ===")
        print(f"最大文字数: {max_chars}文字")

    return results


############################################################################################################
# 翻訳の実行　###############################################################################################
def main():

    this_dir = Path(__file__).resolve().parent

    # 入力用パス
    input_path = this_dir / "data" / "texts" / "combined_transcript.txt"
    # 出力用パス
    output_path = this_dir / "data" / "texts_ymm" / "ymm_transcript.csv"
    
    url_file_dir = this_dir / "data" / "texts" / "url.txt"
    url = get_url_text(url_file_dir)

    title = get_video_title(url)
    print(f"動画タイトル: {title}\n")


    # 字幕の最小合計文字数
    num = 600

    # トランスクリプト・チャンク毎の翻訳と結合
    output_transcript = get_gpt_story(get_text_contents(input_path), # トランスクリプト・テキストの取得
                                      get_instruction_1(title,num), # インストラクションの取得
                                      get_instruction_2(title,num), # インストラクションの取得
                                      "gpt-4o-mini", # モデル名
                                      0.1, # temperature
                                      4096 # max_tokens
                                      )

    # もし「```」という記号があれば削除
    if "```" in output_transcript:
        # 1行目の「```」を削除
        output_transcript = output_transcript.replace("```", "", 1)
        # 最後の行の「```」を削除
        if output_transcript.endswith("```"):
            output_transcript = output_transcript[:-3]

        # 空行がある場合は削除
        output_transcript = "\n".join([line for line in output_transcript.splitlines() if line.strip()])

    # 翻訳されたテキストをCSVファイルに保存
    output_path.write_text(output_transcript, encoding='utf-8')
    print(f"保存ファイルのパス：\n{output_path}\n")
    
    # 台本の文字数を分析
    count_characters_in_script(output_transcript)
    
    print("*"*50,f"\nこのコードの処理が全て完了しました。")


############################################################################################################
if __name__ == "__main__":
    main()

