import scripts_ymm.ymm_06_frame_slide_v2 as ymm_06_frame_slide_v2
import scripts_ymm.ymm_07_save_movie_v4 as ymm_07_save_movie_v4
import scripts_ymm.ymm_08_upload_explanation as ymm_08_upload_explanation

def main():
    print("実行開始")

    ymm_06_frame_slide_v2.main()  # スライド動画の生成
    ymm_07_save_movie_v4.main()  # 動画、音声、字幕の保存
    ymm_08_upload_explanation.main()  # テキストのアップロード

    print("すべての処理が完了しました")

if __name__ == "__main__":
    main()
