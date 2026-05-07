import pathlib
import pyperclip
import yt_dlp

# カスタムのサイレントロガー
class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(msg)

def get_url_text(url_file_dir: str) -> str:
    with open(url_file_dir, "r", encoding="utf-8") as f:
        return f.readline().strip()

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

def main():
    this_dir = pathlib.Path(__file__).parent.resolve()
    url_file_dir = this_dir / "data" / "texts" / "url.txt"
    output_text_dir = this_dir / "data" / "texts_ymm" / "ymm_outline.txt"

    url = get_url_text(url_file_dir)
    title = get_video_title(url)

    text = f"""
{title} の紹介【日本語吹替え】

🔗 オリジナル動画：
{title}
{url}

🎙️ 使用音声：
Voicevox

🧠 翻訳・要約：
GPT-4o

📌 ※本動画はオリジナル動画の内容をもとに作成された翻訳＋考察＋解説です。
    """
    print(text)

    # ファイルに保存
    with open(output_text_dir, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"テキストを {output_text_dir} に保存しました。")

    # クリップボードにコピー
    pyperclip.copy(text)

    print(f"テキストをクリップボードにコピーしました。")

if __name__ == "__main__":
    main()
