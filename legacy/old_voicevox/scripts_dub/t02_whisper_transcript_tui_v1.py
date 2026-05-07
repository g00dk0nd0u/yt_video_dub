import sys
import os
import platform
import ctypes.util
from pathlib import Path
from typing import List
import moviepy.editor as mp
from faster_whisper import WhisperModel
import questionary

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# ----- Windows libc Patch -----
if platform.system() == "Windows":
    original_find_library = ctypes.util.find_library
    def patched_find_library(name):
        if name == "c":
            return "msvcrt"
        return original_find_library(name)
    ctypes.util.find_library = patched_find_library

# ----- Utility functions -----
def find_video_files(folder: Path) -> list:
    exts = ["*.mp4", "*.mkv", "*.mov"]
    files = []
    for ext in exts:
        files.extend(folder.glob(ext))
    files = [f for f in files if f.stat().st_size > 0]
    return sorted(files, key=os.path.getmtime)

def extract_audio_files(video_files: list, audio_dir: Path):
    audio_paths = []
    for video_path in video_files:
        audio_path = audio_dir / (video_path.stem + ".wav")
        try:
            with mp.VideoFileClip(str(video_path)) as video:
                if video.audio:
                    video.audio.write_audiofile(str(audio_path))
                    print(f"Extracted audio: {audio_path}")
                    audio_paths.append(audio_path)
                else:
                    print(f"No audio track: {video_path}")
        except Exception as e:
            print(f"Audio extraction error: {video_path} → {e}")
    return audio_paths

def get_text_lines(audio_path: Path, model) -> List[str]:
    if not isinstance(audio_path, (str, Path)) or not audio_path.exists():
        raise ValueError(f"The specified audio file does not exist or the path is invalid: {audio_path}")

    print("Transcribing ...")
    segments, info = model.transcribe(str(audio_path), beam_size=2, temperature=0.0, condition_on_previous_text=False)
    print("Detected language '%s' with probability %f" % (info.language, info.language_probability))
    text_lines = []
    for segment in segments:
        text = "[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text.strip())
        text_lines.append(text)
        print(text)
    return text_lines

def match_end_with_start(lines: List[str]) -> List[str]:
    new_lines = []
    for i, line in enumerate(lines):
        if i == len(lines) - 1:
            new_lines.append(line)
            break
        parts = line.split("]")
        times = parts[0].replace("[", "").split(" -> ")
        start_time = float(times[0].strip('s'))
        end_time = float(times[1].strip('s'))
        text = parts[1].strip()
        next_parts = lines[i + 1].split("]")
        next_times = next_parts[0].replace("[", "").split(" -> ")
        next_start_time = float(next_times[0].strip('s'))
        if end_time == next_start_time:
            new_lines.append(line)
        else:
            end_time = next_start_time
            new_line = f"[{start_time}s -> {end_time}s] {text}"
            new_lines.append(new_line)
            print(f"Changed end time of line {i} to match start time of line {i+1}.")
    print("\nAdjusted end times to match the start times of the next lines.\n")
    print("*" * 50)
    return new_lines

def save_text_lines(text_lines: List[str], text_path: Path) -> None:
    text_path = Path(text_path)
    with text_path.open('w', encoding='utf-8') as f:
        for text in text_lines:
            f.write(text + "\n")
    print(f"Saved text file: {text_path}")

def open_explorer(path):
    if platform.system() == "Windows":
        os.startfile(str(path))
    elif platform.system() == "Darwin":
        os.system(f"open {str(path)}")
    else:
        os.system(f"xdg-open {str(path)}")

def main():
    download_dir = Path.home() / "Downloads"
    video_files = find_video_files(download_dir)
    if not video_files:
        print("No video files found in your Downloads folder.")
        return

    choices = [f.name for f in video_files]
    idx = questionary.select("Select a video file to transcribe:", choices=choices).ask()
    if idx is None:
        print("No selection. Exiting.")
        return
    selected_idx = choices.index(idx)
    video_path = video_files[selected_idx]

    # モデル初期化
    try:
        model = WhisperModel("large-v3", device="cuda", compute_type="float32")
    except Exception as e:
        print(f"Failed to initialize WhisperModel: {e}")
        return

    print("Extracting audio ...")
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmpdir:
        audio_dir = Path(tmpdir)
        audio_paths = extract_audio_files([video_path], audio_dir)
        if not audio_paths:
            print("No audio files extracted.")
            return

        for audio_path in audio_paths:
            try:
                lines = get_text_lines(audio_path, model)
                lines = match_end_with_start(lines)
                text_path = download_dir / (audio_path.stem + ".txt")
                save_text_lines(lines, text_path)
            except Exception as e:
                print(f"Transcription error: {audio_path} → {e}")

    print("\nTranscription complete.")
    open_explorer(download_dir)

if __name__ == "__main__":
    main()
