import scripts_ymm.ymm_00_clean_data as ymm_00_clean_data
import scripts_ymm.ymm_01_get_url_movie_audio_v3 as ymm_01_get_url_movie_audio_v3
import scripts_ymm.ymm_02_get_transcript_request_v2 as ymm_02_get_transcript_request_v2
import scripts_ymm.ymm_03_gpt_story_v1 as ymm_03_gpt_story_v1
import old_py.ymm_04_voicevox_tts_jp_multi_v2 as ymm_04_voicevox_tts_jp_multi_v2
import scripts_ymm.ymm_05_filter_similar_frames_v2 as ymm_05_filter_similar_frames_v2


def main():
    print("実行開始")
    ymm_00_clean_data.main()  # データクリーンアップ
    ymm_01_get_url_movie_audio_v3.main()  # 動画と音声のURL取得 : urlをinput入力する必要あり
    ymm_02_get_transcript_request_v2.main()  # 動画と音声のトランスクリプト取得
    ymm_03_gpt_story_v1.main()  # ストーリー生成
    ymm_04_voicevox_tts_jp_multi_v2.main()  # 音声合成
    ymm_05_filter_similar_frames_v2.main()  # フレーム画像のフィルタリング

    print("すべての処理が完了しました")

if __name__ == "__main__":
    main()
