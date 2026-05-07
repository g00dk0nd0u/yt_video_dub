r"""
This script transcribes video files in the Downloads folder using the Faster Whisper model.

Python version: 3.10 or later

## [Requirements]
1. Python 3.10 or later (3.11 recommended)
2. Virtual environment (venv) is recommended to avoid conflicts with other Python packages: python -m venv venv
3. Activate the virtual environment: venv\Scripts\activate
4. Install the necessary packages: pip install moviepy==1.0.3 faster-whisper==0.1.0
"""
import sys
sys.stderr = open("whisper_error_log.txt", "w", encoding="utf-8")
sys.stdout = open("whisper_print_log.txt", "w", encoding="utf-8")

import platform
import ctypes.util

# Patch to avoid "c" library not found issue on Windows
if platform.system() == "Windows":
    original_find_library = ctypes.util.find_library
    def patched_find_library(name):
        if name == "c":
            return "msvcrt"
        return original_find_library(name)
    ctypes.util.find_library = patched_find_library

import os
from faster_whisper import WhisperModel
from pathlib import Path
from typing import List
import moviepy.editor as mp
import tkinter as tk
from tkinter import ttk, messagebox
import threading

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# faster-whisper transcription #########################################################################################
def get_text_lines(audio_path: Path, model) -> List[str]:
    if not isinstance(audio_path, (str, Path)) or not audio_path.exists():
        raise ValueError(f"The specified audio file does not exist or the path is invalid: {audio_path}")

    print(f"Transcribing using {model.device}.")
    segments, info = model.transcribe(str(audio_path), beam_size=2, temperature=0.0, condition_on_previous_text=False)
    print("Detected language '%s' with probability %f" % (info.language, info.language_probability))

    text_lines = []
    for segment in segments:
        text = "[%.2fs -> %.2fs] %s\n" % (segment.start, segment.end, segment.text.strip())
        text_lines.append(text)
        print(text)
    return text_lines


# Merge lines where the start time of the next line matches the end time of the current line ###########################
def match_end_with_start(lines: List[str]) -> List[str]:
    new_lines = []
    for i, line in enumerate(lines):

        if i == len(lines) - 1:  # Last line
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

        # If end time matches the start time of the next line
        if end_time == next_start_time:
            new_lines.append(line)
        else:
            end_time = next_start_time
            new_line = f"[{start_time}s -> {end_time}s] {text}"
            new_lines.append(new_line)
            print(f"Changed end time of line {i} to match start time of line {i+1}.")

    print(f"\nAdjusted end times to match the start times of the next lines.\n")
    print("*" * 50)
    return new_lines


# Save text lines to file #############################################################################################
def save_text_lines(text_lines: List[str], text_path: Path) -> None:
    text_path = Path(text_path)
    with text_path.open('w', encoding='utf-8') as f:
        for text in text_lines:
            f.write(text)
    print(f"Saved text file: {text_path}")


# Find video files ####################################################################################################
def find_video_files(folder: Path) -> list:
    exts = ["*.mp4", "*.mkv", "*.mov"]
    files = []
    for ext in exts:
        files.extend(folder.glob(ext))
    # Exclude 0-byte files (if needed)
    files = [f for f in files if f.stat().st_size > 0]
    return sorted(files, key=os.path.getmtime)


# Extract audio from video files (multiple files supported) ###########################################################
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


# Transcribe audio files ##############################################################################################
def transcribe_audio_files(audio_paths: list, text_dir: Path, model):
    for audio_path in audio_paths:
        try:
            lines = get_text_lines(audio_path, model)
            lines = match_end_with_start(lines)
            text_path = text_dir / (audio_path.stem + ".txt")
            save_text_lines(lines, text_path)
        except Exception as e:
            print(f"Transcription error: {audio_path} → {e}")


# New function: Transcribe + update preview area (thread-safe) ########################################################
def transcribe_audio_files_with_preview_threadsafe(audio_paths, text_dir, model, preview_callback):
    for audio_path in audio_paths:
        try:
            lines = []
            segments, info = model.transcribe(str(audio_path), beam_size=2, temperature=0.0, condition_on_previous_text=False)
            for segment in segments:
                line = "[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text.strip())
                lines.append(line)
                preview_callback(line)  # Add new line to preview
            text_path = text_dir / (audio_path.stem + ".txt")
            save_text_lines([l + "\n" for l in lines], text_path)
        except Exception as e:
            print(f"Transcription error: {audio_path} → {e}")


# Update preview widget ###############################################################################################
def update_preview_widget(preview_widget, line):
    preview_widget.config(state="normal")
    preview_widget.insert(tk.END, line + "\n")
    preview_widget.config(state="disabled")
    preview_widget.see(tk.END)
    preview_widget.update_idletasks()


# Open file explorer ##################################################################################################
def open_explorer(path):
    os.startfile(str(path))

#### tkinter GUI part #################################################################################################
def gui_main():
    # Get list of mp4/mkv/mov files in Downloads folder
    download_dir = Path.home() / "Downloads"
    video_files = find_video_files(download_dir)
    video_names = [f.name for f in video_files]

    root = tk.Tk()
    root.withdraw()  # Hide window initially

    if not video_names:
        messagebox.showinfo("Info", "No video files found. Please add videos to your Downloads folder.")
        root.destroy()
        return

    root.deiconify()  # Show window
    root.title("Video Transcribe Tool")
    root.geometry("750x260")

    selected_file = tk.StringVar()
    file_combo = ttk.Combobox(root, textvariable=selected_file, values=video_names, state="readonly", width=30)
    file_combo.current(0)
    file_combo.pack(pady=5)

    # Frame for preview area
    preview_frame = tk.Frame(root)
    preview_frame.pack(pady=5, fill="both", expand=True)

    # Preview area (Text widget)
    preview = tk.Text(preview_frame, height=7, width=70, font=("Meiryo", 9), bg="#f0f0f0", wrap="word")
    preview.pack(side="left", fill="both", expand=True)
    preview.config(state="disabled")

    # Scrollbar
    scrollbar = tk.Scrollbar(preview_frame, command=preview.yview)
    preview.config(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")


    # Model initialization (only once at startup)
    try:
        model = WhisperModel("small", device="cpu", compute_type="float32")
    except Exception as e:
        messagebox.showerror("Model Error", f"Failed to initialize WhisperModel\n{e}")
        root.destroy()
        return

    # Handler for Transcribe button
    def on_transcribe():
        # Initialize preview area
        preview.config(state="normal")
        preview.delete("1.0", tk.END)
        preview.insert(tk.END, "Processing started\n")
        preview.config(state="disabled")
        preview.update_idletasks()

        idx = file_combo.current()
        if idx < 0:
            messagebox.showwarning("Selection Error", "Please select a video file.")
            return
        video_path = video_files[idx]

        def worker():
            from tempfile import TemporaryDirectory
            try:
                root.after(0, lambda: update_preview_widget(preview, "Initializing Whisper model..."))
                # Model initialization (if needed per run)
                # ...skip if reusing model...

                root.after(0, lambda: update_preview_widget(preview, "Extracting audio..."))
                with TemporaryDirectory() as tmpdir:
                    audio_dir = Path(tmpdir)
                    audio_paths = extract_audio_files([video_path], audio_dir)
                    root.after(0, lambda: update_preview_widget(preview, "Starting transcription..."))
                    def safe_update(line):
                        root.after(0, update_preview_widget, preview, line)
                    transcribe_audio_files_with_preview_threadsafe(
                        audio_paths, download_dir, model, safe_update
                    )
                def show_popup_and_open_folder():
                    open_explorer(download_dir)

                root.after(0, show_popup_and_open_folder)
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("Error", f"An error occurred during processing.\n{e}"))


        threading.Thread(target=worker, daemon=True).start()


    trans_btn = ttk.Button(root, text="Transcribe", command=on_transcribe)
    trans_btn.pack(pady=5)

    root.mainloop()

if __name__ == "__main__":
    gui_main()
