"""
## NVIDIA cuDNN DLLセットアップ手順（同僚向け簡易メモ）
★管理者権限やシステム設定は不要。DLLのコピペだけでOK！
1. **CUDAのバージョンを確認**
   （例：CUDA 12.1 など）
2. **NVIDIA公式cuDNNページにアクセス**
   [https://developer.nvidia.com/rdp/cudnn-archive](https://developer.nvidia.com/rdp/cudnn-archive)
3. **自分のCUDAバージョンに合ったZIPファイルをダウンロード**
   例：`cudnn-windows-x86_64-9.10.1.4_cuda12-archive.zip`
4. **ZIPを解凍して、binフォルダ内のDLLファイルを取得**
   例：`cudnn_ops64_9.dll`など
5. **使うPython仮想環境の Scripts フォルダにDLLをコピー**
   例：`C:\Users\（ユーザー名）\Documents\xxx\.venv\Scripts\`
   ※全DLLファイルをここに貼り付け
6. **Pythonプログラムをその仮想環境で実行**
   → DLLエラーが出なければ完了！
"""