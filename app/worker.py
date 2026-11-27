import shutil
import threading
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.transcriber import Transcriber, TranscriptSegment


class TranscribeWorker(QThread):
    status_changed = Signal(str)
    metadata_ready = Signal(float)
    segment_added = Signal(int, object, float)
    finished_ok = Signal(dict)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        transcriber: Transcriber,
        source_path: Path,
        uploads_dir: Path,
        vad_filter: bool = True,
    ) -> None:
        super().__init__()
        self.transcriber = transcriber
        self.source_path = source_path
        self.uploads_dir = uploads_dir
        self.vad_filter = vad_filter
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        item_id = uuid.uuid4().hex[:12]
        ext = self.source_path.suffix.lower() or ".wav"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        saved_path = self.uploads_dir / f"{item_id}{ext}"
        started_at = time.perf_counter()
        segments: list[TranscriptSegment] = []
        duration = 0.0

        try:
            self.status_changed.emit("Preparing audio file...")
            shutil.copy2(self.source_path, saved_path)

            for event in self.transcriber.transcribe_stream(
                audio_path=saved_path,
                vad_filter=self.vad_filter,
                cancel_event=self.cancel_event,
                on_status=lambda msg: self.status_changed.emit(msg),
            ):
                etype = event["type"]
                if etype == "metadata":
                    duration = float(event.get("duration", 0.0))
                    self.metadata_ready.emit(duration)
                elif etype == "segment":
                    seg: TranscriptSegment = event["segment"]
                    segments.append(seg)
                    self.segment_added.emit(event["index"], seg, float(event.get("progress", 0.0)))
                elif etype == "cancelled":
                    saved_path.unlink(missing_ok=True)
                    self.cancelled.emit()
                    return

            if self.cancel_event.is_set():
                saved_path.unlink(missing_ok=True)
                self.cancelled.emit()
                return

            elapsed = round(time.perf_counter() - started_at, 2)
            self.finished_ok.emit(
                {
                    "id": item_id,
                    "title": self.source_path.stem,
                    "file_name": self.source_path.name,
                    "audio_path": str(saved_path),
                    "duration": round(duration, 2),
                    "processing_time": elapsed,
                    "segments": segments,
                }
            )
        except Exception as exc:
            saved_path.unlink(missing_ok=True)
            self.failed.emit(str(exc))
