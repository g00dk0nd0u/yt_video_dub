from huggingface_hub import snapshot_download
import pathlib

this_dir = pathlib.Path(__file__).parent.resolve()
local_dir = this_dir / "models" / "melotts_en"


# キャッシュディレクトリにモデルをダウンロードして展開
snapshot_download(
    repo_id="myshell-ai/MeloTTS-English-v3",
    local_dir=local_dir,  # 好きな保存場所
    local_dir_use_symlinks=False   # Windowsでは必須
)
