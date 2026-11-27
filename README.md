# ozgSub

Desktop app for local English audio transcription using `faster-whisper` (`large-v3`) and PySide6.

## Features

- Local English speech-to-text with `faster-whisper` (`large-v3`, CUDA or CPU)
- `.srt` subtitle export
- Built-in audio player
- Local transcription history stored in `data/history.json`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

The `large-v3` model downloads automatically on the first run.