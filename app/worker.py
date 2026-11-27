from PySide6.QtCore import QThread, Signal

from app.transcriber import Transcriber


class TranscribeWorker(QThread):
    """Ses çözümlemeyi arayüzü dondurmadan arka planda çalıştırır."""

    progress = Signal(int)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, transcriber: Transcriber, audio_path: str) -> None:
        super().__init__()
        self.transcriber = transcriber
        self.audio_path = audio_path

    def run(self) -> None:
        try:
            segments = self.transcriber.transcribe(
                self.audio_path,
                on_progress=lambda pct: self.progress.emit(int(pct)),
            )
            self.finished.emit(segments)
        except Exception as exc:
            self.error.emit(str(exc))