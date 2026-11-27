import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import ctranslate2
from faster_whisper import WhisperModel

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4", ".mkv", ".webm"}

def _register_cuda_dlls() -> None:
    """Windows'ta .venv içindeki NVIDIA CUDA/cuDNN DLL klasörlerini tanıtır."""
    if sys.platform != "win32":
        return
    nvidia_dir = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if not nvidia_dir.exists():
        return
    for bin_dir in nvidia_dir.glob("*/bin"):
        if bin_dir.is_dir():
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

@dataclass
class TranscriptSegment:
    """Çözümlenen tek bir altyazı parçasını temsil eder."""
    start: float
    end: float
    text: str


class Transcriber:
    """faster-whisper large-v3 kullanarak yerel İngilizce ses çözümleme yapar."""

    def __init__(self, model_size: str = "large-v3") -> None:
        self.model_size = model_size
        self._model: WhisperModel | None = None

    def _detect_device(self) -> tuple[str, str]:
        """NVIDIA GPU (CUDA) varsa onu, yoksa CPU'yu otomatik seçer."""
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
        return "cpu", "int8"

    def load_model(self) -> None:
        """Modeli yalnızca ilk gerektiğinde (lazy loading) belleğe yükler."""
        if self._model is not None:
            return
        _register_cuda_dlls()
        device, compute_type = self._detect_device()
        self._model = WhisperModel(
            self.model_size,
            device=device,
            compute_type=compute_type,
    )

    def validate_audio_path(self, audio_path: str | Path) -> Path:
        """Dosya yolunu güvenli şekilde doğrular."""
        path = Path(audio_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Ses dosyası bulunamadı: {path}")
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Desteklenmeyen dosya türü: {path.suffix}")
        return path

    def transcribe(
        self,
        audio_path: str | Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[TranscriptSegment]:
        """İngilizce ses dosyasını çözer ve zaman damgalı segment listesi döner."""
        path = self.validate_audio_path(audio_path)
        self.load_model()
        assert self._model is not None

        segments_iter, info = self._model.transcribe(
            str(path),
            language="en",
            vad_filter=True,
        )

        results: list[TranscriptSegment] = []
        duration = info.duration or 0.0

        for seg in segments_iter:
            text = seg.text.strip()
            if text:
                results.append(TranscriptSegment(start=seg.start, end=seg.end, text=text))
            if on_progress and duration > 0:
                progress = min(100.0, (seg.end / duration) * 100.0)
                on_progress(progress)

        if on_progress:
            on_progress(100.0)

        return results