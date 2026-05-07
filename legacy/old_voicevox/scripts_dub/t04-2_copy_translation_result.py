# pip install pyperclip
import pathlib
import pyperclip

# ファイルからテキストを取得
def get_text_from_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:  # ← UTF-8 を明示的に指定
        return file.read()

# クリップボードにコピー
def copy_prompt_to_clipboard(prompt):
    import pyperclip
    pyperclip.copy(prompt)
    print('クリップボードにコピーしました。')

# メイン処理
def main():
    this_dir = pathlib.Path(__file__).parent
    texts_dolder_path = this_dir / 'data' / 'texts'
    original_trascript_path = texts_dolder_path / 'combined_transcript.txt'
    translated_trascript_path = texts_dolder_path / 'formatted_translated_texts.txt'

    prompt = f"""
    ### 命令文 ###
    動画文字起こし内容の翻訳結果について、出力形式の例に従って添削してください。

    # 注意点：
    - 元のトランスクリプトの再生時間とテキスト内容の時刻応答関係が、翻訳結果において、相違している箇所を指摘・改善提案ください。
    - 元のトランスクリプトのテキスト内容を重複して翻訳してしまっている箇所を指摘・改善提案ください。
    - 翻訳結果のテキスト内容を、より自然なネイティブ表現に改善可能な箇所を指摘・改善提案ください。
    - 添削後の改善案のテキストは、テキスト部のみをコピーアンドペースできる為に、時刻表記を削除して、必ずコード形式で出力してください。
    - 添削後の改善案のテキストは、当行の再生開始時刻と終了時刻を確認し、音声再生秒数の1秒あたり8文字以下の文字数とする必要があります。 字数が非常に多く超過(1秒あたり9文字以上)している行を指摘・改善提案ください。
    - 全体を通して、強調箇所やタイトル部に文字サイズにH2, H3を使用して、さらに解説コメントに絵文字を添えることで、視覚的に読みやすくしてください。

    # 出力形式の例：

    * タイムスタンプの相違検出

    1. [XXX.XXs -> XXX.XXs]
    翻訳結果のタイムスタンプが元のトランスクリプトと一致していませんでした。

    2. [XXX.XXs -> XXX.XXs]
    翻訳結果のタイムスタンプと元のトランスクリプトが部分的に合っていない箇所があります。

    3. [XXX.XXs -> XXX.XXs]
    元のトランスクリプトで記載された箇所が翻訳で欠落しています。

    * 重複翻訳：
    以下の連続する行でテキスト内容の意味が極めて近いため重複表現になっています。
    [XXX.XXs -> XXX.XXs] テキスト1
    [XXX.XXs -> XXX.XXs] テキスト2

    * 冗長表現:
    以下テキストが文脈上で何度も繰り返されており、冗長に感じられる部分がありました。
        ```plain text
    　テキスト


    * 和訳が不自然な部分の改善

    1. [XXX.XXs -> XXX.XXs]
    - 原文:  let me know if you'd like a video where I try it out in depth once it becomes available
    - 翻訳後: もし、詳しく試してみる動画が欲しい方は教えてください。
    - コメント: より自然な表現として、前文の文末に言い回しに合わせて、言葉の流れをスムーズにしました。
    - 改善案:
        ```plain text
        利用可能になり次第、詳しく試してみる動画を見たい方は教えてください。

    2. [XXX.XXs -> XXX.XXs] 
    - 原文: cool anyway let me know your thoughts in the comments
    - 翻訳後: さて、感想をコメントで教えてください。
    - コメント: 文頭をより丁寧で自然な表現にしました。
    - 改善案:
        ```plain text
        ぜひ感想をコメントで教えてください。

    * 字数超過(1秒あたり9文字以上)：
    以下の行で音声再生時間に比べて、文字数が非常に多くなっています。
    [XXX.XXs -> XXX.XXs] テキスト1
    - XX字ほど超過しています、
    - 簡潔化した改善案:
        ```plain text

    では、以下の翻訳前後のトランスクリプトを投稿しますので、添削をお願いいたします。

    * 元の翻訳前のトランスクリプト：
    {get_text_from_file(original_trascript_path)}

    * 添削対象である翻訳後のトランスクリプト：
    {get_text_from_file(translated_trascript_path)}
    """
    copy_prompt_to_clipboard(prompt)

# 実行
if __name__ == '__main__':
    main()