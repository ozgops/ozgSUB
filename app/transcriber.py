import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generator

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _register_cuda_dlls() -> None:
    """Register NVIDIA CUDA/cuDNN bin folders from the local venv on Windows."""
    if sys.platform != "win32":
        return
    nvidia_dir = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if not nvidia_dir.exists():
        return
    for bin_dir in nvidia_dir.glob("*/bin"):
        if bin_dir.is_dir():
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                pass
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dlls()

import ctranslate2
from faster_whisper import WhisperModel

ALLOWED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus",
    ".aac", ".wma", ".mp4", ".mkv", ".mov", ".webm",
}


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


def get_gpu_info() -> dict[str, Any]:
    try:
        cuda_count = ctranslate2.get_cuda_device_count()
    except Exception:
        cuda_count = 0

    gpu_name: str | None = None
    vram_mb: int | None = None
    if cuda_count > 0:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                text=True,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            if out:
                parts = [p.strip() for p in out.splitlines()[0].split(",")]
                if len(parts) >= 2:
                    gpu_name = parts[0]
                    vram_mb = int(parts[1])
        except Exception:
            gpu_name = "NVIDIA CUDA GPU"

    return {
        "cuda_available": cuda_count > 0,
        "device": "cuda" if cuda_count > 0 else "cpu",
        "compute_type": "float16" if cuda_count > 0 else "int8",
        "gpu_name": gpu_name or "CPU",
        "vram_gb": round(vram_mb / 1024, 1) if vram_mb else None,
    }


class Transcriber:
    def __init__(self, model_size: str = "large-v3") -> None:
        self.model_size = model_size
        self._lock = threading.Lock()
        self._model: WhisperModel | None = None
        self.gpu_info = get_gpu_info()

    def _detect_device(self) -> tuple[str, str]:
        return self.gpu_info["device"], self.gpu_info["compute_type"]

    def load_model(self) -> WhisperModel:
        with self._lock:
            if self._model is not None:
                return self._model
            _register_cuda_dlls()
            device, compute_type = self._detect_device()
            try:
                self._model = WhisperModel(
                    self.model_size,
                    device=device,
                    compute_type=compute_type,
                )
            except Exception:
                if device == "cuda":
                    self._model = WhisperModel(
                        self.model_size,
                        device="cpu",
                        compute_type="int8",
                    )
                    self.gpu_info["device"] = "cpu"
                    self.gpu_info["compute_type"] = "int8"
                    self.gpu_info["cuda_available"] = False
                else:
                    raise
            return self._model

    def validate_audio_path(self, audio_path: str | Path) -> Path:
        path = Path(audio_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {path.suffix}")
        return path

    def transcribe_stream(
        self,
        audio_path: str | Path,
        vad_filter: bool = True,
        cancel_event: threading.Event | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        path = self.validate_audio_path(audio_path)

        if self._model is None and on_status:
            on_status("Loading Whisper Large v3...")

        model = self.load_model()
        if cancel_event and cancel_event.is_set():
            yield {"type": "cancelled"}
            return

        if on_status:
            on_status("Transcribing audio...")

        segments_iter, info = model.transcribe(
            str(path),
            language="en",
            task="transcribe",
            beam_size=5,
            vad_filter=vad_filter,
            vad_parameters={"min_silence_duration_ms": 500} if vad_filter else None,
            condition_on_previous_text=True,
        )

        duration = float(info.duration or 0.0)
        yield {"type": "metadata", "duration": duration}

        idx = 0
        for seg in segments_iter:
            if cancel_event and cancel_event.is_set():
                yield {"type": "cancelled"}
                return
            text = seg.text.strip()
            if not text:
                continue
            idx += 1
            progress = min(99.0, round((seg.end / duration) * 100.0, 1)) if duration > 0 else 0.0
            yield {
                "type": "segment",
                "index": idx,
                "segment": TranscriptSegment(
                    start=round(float(seg.start), 3),
                    end=round(float(seg.end), 3),
                    text=text,
                ),
                "progress": progress,
            }

    def transcribe(
        self,
        audio_path: str | Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[TranscriptSegment]:
        results: list[TranscriptSegment] = []
        for event in self.transcribe_stream(audio_path):
            if event["type"] == "segment":
                results.append(event["segment"])
                if on_progress:
                    on_progress(event["progress"])
        if on_progress:
            on_progress(100.0)
        return results
